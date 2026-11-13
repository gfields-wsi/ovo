#!/usr/bin/env python3
"""Migrate OvO state to Postgres on Render.

This script creates the tables the three stores need, in
managed Postgres. It runs once per deploy, from the Render
pre-deploy step, and it is safe to run again: every table is
created only when it is missing, and no row is ever changed
by this script on its own.

Usage, on Render or on a machine with a Postgres address:

    DATABASE_URL=postgresql://... python3 migrate.py

    python3 migrate.py --database-url postgresql://...

    python3 migrate.py --print-sql
        Print the Postgres tables, and connect to nothing.

    python3 migrate.py --from-sqlite ovo-runner/ovo_runs.db
        After creating the tables, copy the runner's run
        records from a local SQLite file into Postgres.
        Rows that already exist are left alone. Only the
        runner store is copied: its runs are the records a
        host restart must not lose. The local MCP and merchant
        files hold test records only, and are not copied.

The Postgres address is never printed and never logged. A
failure prints the host name only, with the password removed.
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from db import PostgresConnection, convert_schema, parse_database_url, scrub_url  # noqa: E402
import postgres_store  # noqa: E402

SCHEMAS = [
    ("runner", postgres_store._runner_store_mod.SCHEMA),
    ("mcp", postgres_store._mcp_store_mod.SCHEMA),
    ("merchant", postgres_store._merchant_store_mod.SCHEMA),
]

RUNNER_TABLES = ["runs", "stages", "publish_attempts", "decisions", "sweep_runs"]


def postgres_schema():
    """The full Postgres table script, for all three stores."""
    parts = []
    for name, schema in SCHEMAS:
        parts.append(f"-- {name} store")
        parts.append(convert_schema(schema))
    return "\n".join(parts)


def list_tables(conn):
    """Table names in the public schema, from Postgres itself."""
    cur = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' ORDER BY table_name")
    return [row["table_name"] for row in cur.fetchall()]


def migrate(database_url):
    """Create the tables. Returns the table names found after
    the run."""
    conn = PostgresConnection(database_url)
    try:
        for _name, schema in SCHEMAS:
            conn.executescript(schema)
        return list_tables(conn)
    finally:
        conn.close()


def copy_runner_sqlite(sqlite_path, database_url):
    """Copy runner rows from a SQLite file into Postgres. Rows
    that already exist are left alone. Returns the row counts
    copied, per table."""
    source = sqlite3.connect(str(sqlite_path))
    source.row_factory = sqlite3.Row
    conn = PostgresConnection(database_url)
    counts = {}
    try:
        for table in RUNNER_TABLES:
            rows = [dict(r) for r in source.execute(
                f"SELECT * FROM {table}").fetchall()]
            copied = 0
            for row in rows:
                columns = list(row.keys())
                placeholders = ", ".join(["%s"] * len(columns))
                sql = (
                    f"INSERT INTO {table} ({', '.join(columns)}) "
                    f"VALUES ({placeholders}) ON CONFLICT DO NOTHING")
                cur = conn.execute(sql, [row[c] for c in columns])
                copied += 1
            conn.commit()
            counts[table] = copied
        # Keep the sweep id counter ahead of the copied rows.
        conn.execute(
            "SELECT setval(pg_get_serial_sequence('sweep_runs', 'id'), "
            "(SELECT COALESCE(MAX(id), 1) FROM sweep_runs))")
        conn.commit()
        return counts
    finally:
        conn.close()
        source.close()


def main():
    parser = argparse.ArgumentParser(description="OvO Postgres migration")
    parser.add_argument("--database-url", default=None,
                        help="Postgres address. Defaults to DATABASE_URL.")
    parser.add_argument("--print-sql", action="store_true",
                        help="Print the Postgres tables and exit.")
    parser.add_argument("--from-sqlite", default=None,
                        help="Runner SQLite file to copy after migrating.")
    args = parser.parse_args()

    if args.print_sql:
        print(postgres_schema())
        return 0

    url = args.database_url or os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set. Nothing was migrated.",
              file=sys.stderr)
        return 2
    try:
        details = parse_database_url(url)
    except ValueError as exc:
        print(f"DATABASE_URL is not usable: {exc}", file=sys.stderr)
        return 2
    try:
        tables = migrate(url)
    except Exception as exc:  # noqa: BLE001 - report the host, never the address
        print(f"Migration failed for {details['host']}: {exc}",
              file=sys.stderr)
        return 1
    print(f"Postgres tables ready on {details['host']}: "
          f"{', '.join(tables)}")
    if args.from_sqlite:
        sqlite_path = Path(args.from_sqlite)
        if not sqlite_path.exists():
            print(f"SQLite file not found: {sqlite_path}", file=sys.stderr)
            return 2
        try:
            counts = copy_runner_sqlite(sqlite_path, url)
        except Exception as exc:  # noqa: BLE001 - report the host, never the address
            print(f"Copy from SQLite failed for {details['host']}: {exc}",
                  file=sys.stderr)
            return 1
        print("Runner rows copied from SQLite: "
              + json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
