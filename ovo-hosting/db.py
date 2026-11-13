#!/usr/bin/env python3
"""Database access for OvO on Render.

The three stores in this repo use SQLite today, through plain
parameterised SQL. On Render they must use managed Postgres, so
a host restart loses no run, no packet, and no merchant record.
This module is the bridge between the two.

It does three things, and nothing else:

1. It reads a Postgres address from DATABASE_URL. The address
   itself is never logged, and never printed. A scrubbed form,
   with the password replaced by three stars, is used for any
   message that names the host.
2. It turns the SQLite SQL the stores already use into Postgres
   SQL. A question mark becomes a percent-s. INSERT OR REPLACE
   becomes INSERT with ON CONFLICT DO UPDATE. INSERT OR IGNORE
   becomes INSERT with ON CONFLICT DO NOTHING. A table id that
   SQLite calls AUTOINCREMENT becomes a Postgres SERIAL id.
   The table and column names never change, so the same method
   code runs on both stores.
3. It wraps a psycopg connection so it looks like the SQLite
   connection the stores already use: execute, fetchone,
   fetchall, commit, close, and lastrowid.

No key, password, token, or card number is ever logged here.
The Postgres driver is psycopg, listed in requirements.txt.
When DATABASE_URL is not set, callers keep using SQLite, so
local tests run with no live database and no extra install.
"""
import os
import re
import urllib.parse

# Tables whose id column is AUTOINCREMENT in SQLite. In Postgres
# the same column is SERIAL, and an insert returns the new id.
SERIAL_TABLES = {
    "wp_signins",
    "card_auths",
    "decisions",
    "installs",
    "rate_changes",
    "refusals",
    "sweep_runs",
}

# Primary key columns, per table, for ON CONFLICT. The merchant
# decisions table has a serial id as its key, so it needs no
# entry here: it is only ever written with a plain INSERT.
CONFLICT_TARGETS = {
    "runs": ["run_key"],
    "stages": ["run_key", "stage"],
    "publish_attempts": ["idempotency_key"],
    "decisions": ["run_key", "fingerprint"],
    "scoped_keys": ["key_hash"],
    "domains": ["store_url"],
    "sessions": ["session_id"],
    "packets": ["run_key"],
    "orders": ["order_id"],
    "read_sessions": ["session_id"],
    "carts": ["cart_id"],
    "payment_profiles": ["merchant_id"],
    "merchants": ["merchant_id"],
}

_INSERT_OR_REPLACE = re.compile(
    r"INSERT OR REPLACE INTO (\w+) \(([^)]*)\)\s*VALUES \(([^)]*)\)",
    re.IGNORECASE)
_INSERT_OR_IGNORE = re.compile(
    r"INSERT OR IGNORE INTO (\w+) \(([^)]*)\)\s*VALUES \(([^)]*)\)",
    re.IGNORECASE)
_INSERT_PLAIN = re.compile(
    r"INSERT INTO (\w+) \(([^)]*)\)\s*VALUES \(([^)]*)\)",
    re.IGNORECASE)


def scrub_url(url):
    """A database address safe to show in a log: the password is
    replaced by three stars. Anything that is not a Postgres
    address is returned unchanged, and never raises."""
    if not url:
        return ""
    try:
        parts = urllib.parse.urlparse(url)
        if parts.password:
            netloc = parts.hostname or ""
            if parts.username:
                netloc = f"{parts.username}:***@{netloc}"
            if parts.port:
                netloc = f"{netloc}:{parts.port}"
            return urllib.parse.urlunparse(parts._replace(netloc=netloc))
    except ValueError:
        return ""
    return url


def parse_database_url(url):
    """Check a Postgres address. Returns its parts as a dict.
    Raises ValueError when the address is missing, is not a
    Postgres address, or names no host or database. The password
    is in the returned dict, so callers must never log it."""
    if not url:
        raise ValueError("DATABASE_URL is not set")
    parts = urllib.parse.urlparse(url)
    if parts.scheme not in ("postgres", "postgresql"):
        raise ValueError(
            f"DATABASE_URL must start with postgres://, not {parts.scheme}://")
    if not parts.hostname:
        raise ValueError("DATABASE_URL names no host")
    database = (parts.path or "").lstrip("/")
    if not database:
        raise ValueError("DATABASE_URL names no database")
    query = urllib.parse.parse_qs(parts.query or "")
    return {
        "host": parts.hostname,
        "port": parts.port or 5432,
        "user": parts.username or "",
        "password": parts.password or "",
        "database": database,
        "sslmode": (query.get("sslmode") or [None])[0],
        "scrubbed": scrub_url(url),
    }


def _replace_placeholders(sql):
    """Turn SQLite ? placeholders into Postgres %s ones. A
    question mark inside a quoted string is left alone."""
    out = []
    in_string = False
    for ch in sql:
        if ch == "'":
            in_string = not in_string
            out.append(ch)
        elif ch == "?" and not in_string:
            out.append("%s")
        else:
            out.append(ch)
    return "".join(out)


def translate_sql(sql):
    """Turn one SQLite statement into its Postgres form. Returns
    (postgres_sql, is_serial_insert). The second value is True
    when the statement inserts into a table with a serial id, so
    the caller can ask Postgres to return that id."""
    pg_sql = _replace_placeholders(sql)
    match = _INSERT_OR_REPLACE.search(pg_sql)
    if match:
        table, columns, values = match.groups()
        cols = [c.strip() for c in columns.split(",")]
        targets = CONFLICT_TARGETS.get(table)
        if not targets:
            raise ValueError(
                f"INSERT OR REPLACE into {table} has no known key for Postgres")
        updates = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in cols if c not in targets)
        replacement = (
            f"INSERT INTO {table} ({columns}) VALUES ({values}) "
            f"ON CONFLICT ({', '.join(targets)}) DO UPDATE SET {updates}")
        pg_sql = _INSERT_OR_REPLACE.sub(replacement, pg_sql, count=1)
        return pg_sql, False
    match = _INSERT_OR_IGNORE.search(pg_sql)
    if match:
        table, columns, values = match.groups()
        replacement = (
            f"INSERT INTO {table} ({columns}) VALUES ({values}) "
            "ON CONFLICT DO NOTHING")
        pg_sql = _INSERT_OR_IGNORE.sub(replacement, pg_sql, count=1)
        return pg_sql, False
    match = _INSERT_PLAIN.search(pg_sql)
    if match and match.group(1) in SERIAL_TABLES:
        return pg_sql, True
    return pg_sql, False


def convert_schema(sqlite_schema):
    """Turn a SQLite CREATE TABLE script into Postgres form.
    AUTOINCREMENT ids become SERIAL ids. Everything else stays
    the same, including table and column names."""
    return sqlite_schema.replace(
        "INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")


class PostgresCursor:
    """One Postgres cursor, shaped like a SQLite cursor. execute
    returns this cursor. fetchone and fetchall return dicts.
    lastrowid holds the id of a row just inserted into a serial
    table, or None. No statement and no parameter is ever
    logged here."""

    def __init__(self, cursor):
        self._cursor = cursor
        self._lastrowid = None

    @property
    def lastrowid(self):
        return self._lastrowid

    def execute(self, sql, params=()):
        pg_sql, is_serial_insert = translate_sql(sql)
        if is_serial_insert:
            pg_sql = pg_sql + " RETURNING id"
        self._cursor.execute(pg_sql, params or None)
        self._lastrowid = None
        if is_serial_insert:
            row = self._cursor.fetchone()
            if row:
                self._lastrowid = row.get("id")
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        """A SQLite cursor can be looped over straight after
        execute. The wrapped Postgres cursor can too, so this
        passes the loop through. The runner's export_run
        relies on it."""
        return iter(self._cursor)

    def close(self):
        self._cursor.close()


class PostgresConnection:
    """One Postgres connection, shaped like a SQLite connection
    for the callers in this repo. It opens with psycopg, reads
    rows as dicts, and commits only when commit is called, as
    the SQLite stores do."""

    def __init__(self, database_url):
        import psycopg
        from psycopg.rows import dict_row
        details = parse_database_url(database_url)
        self.scrubbed_url = details["scrubbed"]
        self._conn = psycopg.connect(
            database_url, connect_timeout=10, row_factory=dict_row)

    def execute(self, sql, params=()):
        return PostgresCursor(self._conn.cursor()).execute(sql, params)

    def executescript(self, sql):
        """Run a multi-statement script, such as a CREATE TABLE
        script, in Postgres form, then commit."""
        cursor = self._conn.cursor()
        try:
            cursor.execute(convert_schema(sql))
        finally:
            cursor.close()
        self.commit()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def connect(database_url=None):
    """Open a Postgres connection from DATABASE_URL, or from the
    address given. Returns None when no address is set, so the
    caller keeps using SQLite. Raises ValueError for a bad
    address, and ImportError when psycopg is not installed."""
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        return None
    return PostgresConnection(url)
