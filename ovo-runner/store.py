#!/usr/bin/env python3
"""Run store for the OvO runner.

Runs, packets, decisions, and publish attempts live here, not in
loose files, so a host restart loses no run. SQLite is the store
now. The callers in runner.py use only the RunStore methods below.
Managed Postgres on Render replaces this module in Phase 7 without
changing those callers: same method names, same record shapes, same
idempotency keys. The SQL here stays to plain parameterised
statements, so the move is a straight port.

Tables:
- runs: one row per run key, with the run status and result.
- stages: one row per run and stage, with the stage status, the
  hash of the output file it validated, and a snapshot of that
  output. A completed stage whose output file still matches its
  recorded hash is not run again on a retry.
- publish_attempts: one row per idempotency key. A retry with the
  same run key reuses the recorded publish attempt instead of
  publishing again.
- decisions: merchant decision files, keyed by run and diff
  fingerprint, so a decision is never recorded twice for the
  same diff.
"""
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_key TEXT PRIMARY KEY,
  store_url TEXT NOT NULL,
  merchant_slug TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at_utc TEXT NOT NULL,
  finished_at_utc TEXT,
  result_json TEXT
);
CREATE TABLE IF NOT EXISTS stages (
  run_key TEXT NOT NULL,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  input_hash TEXT,
  output_hash TEXT,
  output_json TEXT,
  finished_at_utc TEXT,
  PRIMARY KEY (run_key, stage)
);
CREATE TABLE IF NOT EXISTS publish_attempts (
  idempotency_key TEXT PRIMARY KEY,
  run_key TEXT NOT NULL,
  status TEXT NOT NULL,
  result_json TEXT,
  finished_at_utc TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
  run_key TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  decision_json TEXT NOT NULL,
  recorded_at_utc TEXT NOT NULL,
  PRIMARY KEY (run_key, fingerprint)
);
CREATE TABLE IF NOT EXISTS sweep_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at_utc TEXT NOT NULL,
  finished_at_utc TEXT,
  stores_checked TEXT NOT NULL,
  runs_resumed INTEGER NOT NULL DEFAULT 0,
  stuck_runs INTEGER NOT NULL DEFAULT 0,
  failed_runs INTEGER NOT NULL DEFAULT 0,
  detail_json TEXT
);
"""

TERMINAL_PUBLISH = ("dry_run_complete", "blocked")


class RunStore:
    """One store. Open it, use it, close it. Callers never write SQL."""

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def create_or_resume_run(self, run_key, store_url, merchant_slug, started_at):
        """Return the run row. A run key is bound to one store address:
        the same key for a different store is an error, never a
        silent second run."""
        row = self.conn.execute(
            "SELECT * FROM runs WHERE run_key = ?", (run_key,)).fetchone()
        if row is not None:
            if row["store_url"] != store_url:
                raise ValueError(
                    f"Run key {run_key} already belongs to {row['store_url']}, "
                    f"not {store_url}. Use a new run key for a new store.")
            return dict(row)
        self.conn.execute(
            "INSERT INTO runs (run_key, store_url, merchant_slug, status, started_at_utc) "
            "VALUES (?, ?, ?, 'running', ?)",
            (run_key, store_url, merchant_slug, started_at))
        self.conn.commit()
        return dict(self.conn.execute(
            "SELECT * FROM runs WHERE run_key = ?", (run_key,)).fetchone())

    def get_run(self, run_key):
        row = self.conn.execute(
            "SELECT * FROM runs WHERE run_key = ?", (run_key,)).fetchone()
        return dict(row) if row else None

    def list_runs(self):
        """All runs, newest first. The health watch reads this.
        It returns run rows only, never stage detail."""
        rows = self.conn.execute(
            "SELECT * FROM runs ORDER BY started_at_utc DESC").fetchall()
        return [dict(r) for r in rows]

    def record_sweep(self, started_at, finished_at, stores_checked,
                     runs_resumed, stuck_runs, failed_runs, detail):
        """One daily sweep, recorded. Stores_checked is a list of
        store addresses the sweep looked at. The sweep never
        starts a check for a store that is not on that list."""
        cur = self.conn.execute(
            "INSERT INTO sweep_runs (started_at_utc, finished_at_utc,"
            " stores_checked, runs_resumed, stuck_runs, failed_runs,"
            " detail_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (started_at, finished_at, json.dumps(stores_checked),
             runs_resumed, stuck_runs, failed_runs,
             json.dumps(detail) if detail is not None else None))
        self.conn.commit()
        return cur.lastrowid

    def list_sweeps(self):
        """Sweep records, newest first."""
        rows = self.conn.execute(
            "SELECT * FROM sweep_runs ORDER BY id DESC").fetchall()
        out = []
        for row in rows:
            item = dict(row)
            if item.get("stores_checked"):
                item["stores_checked"] = json.loads(item["stores_checked"])
            if item.get("detail_json"):
                item["detail"] = json.loads(item.pop("detail_json"))
            out.append(item)
        return out

    def update_run(self, run_key, status, finished_at, result):
        self.conn.execute(
            "UPDATE runs SET status = ?, finished_at_utc = ?, result_json = ? "
            "WHERE run_key = ?",
            (status, finished_at, json.dumps(result), run_key))
        self.conn.commit()

    def record_stage(self, run_key, stage, status, output_hash, output, finished_at,
                     input_hash=None):
        self.conn.execute(
            "INSERT OR REPLACE INTO stages "
            "(run_key, stage, status, input_hash, output_hash, output_json, finished_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_key, stage, status, input_hash, output_hash,
             json.dumps(output) if output is not None else None, finished_at))
        self.conn.commit()

    def get_stage(self, run_key, stage):
        row = self.conn.execute(
            "SELECT * FROM stages WHERE run_key = ? AND stage = ?",
            (run_key, stage)).fetchone()
        if not row:
            return None
        out = dict(row)
        if out.get("output_json"):
            out["output"] = json.loads(out["output_json"])
        return out

    def get_publish_attempt(self, idempotency_key):
        row = self.conn.execute(
            "SELECT * FROM publish_attempts WHERE idempotency_key = ?",
            (idempotency_key,)).fetchone()
        if not row:
            return None
        out = dict(row)
        if out.get("result_json"):
            out["result"] = json.loads(out["result_json"])
        return out

    def record_publish_attempt(self, idempotency_key, run_key, status, result, finished_at):
        """First write wins for a key. A later call with the same key
        does not overwrite the recorded attempt."""
        self.conn.execute(
            "INSERT OR IGNORE INTO publish_attempts "
            "(idempotency_key, run_key, status, result_json, finished_at_utc) "
            "VALUES (?, ?, ?, ?, ?)",
            (idempotency_key, run_key, status,
             json.dumps(result) if result is not None else None, finished_at))
        self.conn.commit()
        return self.get_publish_attempt(idempotency_key)

    def update_publish_attempt(self, idempotency_key, status, result, finished_at):
        self.conn.execute(
            "UPDATE publish_attempts SET status = ?, result_json = ?, finished_at_utc = ? "
            "WHERE idempotency_key = ?",
            (status, json.dumps(result) if result is not None else None,
             finished_at, idempotency_key))
        self.conn.commit()

    def record_decision(self, run_key, fingerprint, decision, recorded_at):
        self.conn.execute(
            "INSERT OR REPLACE INTO decisions "
            "(run_key, fingerprint, decision_json, recorded_at_utc) "
            "VALUES (?, ?, ?, ?)",
            (run_key, fingerprint, json.dumps(decision), recorded_at))
        self.conn.commit()

    def export_run(self, run_key):
        """Full run record, for a run file or a status check."""
        run = self.get_run(run_key)
        if not run:
            return None
        stages = [dict(r) for r in self.conn.execute(
            "SELECT * FROM stages WHERE run_key = ? ORDER BY stage", (run_key,))]
        for stage in stages:
            if stage.get("output_json"):
                stage["output"] = json.loads(stage.pop("output_json"))
        attempts = [dict(r) for r in self.conn.execute(
            "SELECT * FROM publish_attempts WHERE run_key = ?", (run_key,))]
        for attempt in attempts:
            if attempt.get("result_json"):
                attempt["result"] = json.loads(attempt.pop("result_json"))
        decisions = [dict(r) for r in self.conn.execute(
            "SELECT * FROM decisions WHERE run_key = ?", (run_key,))]
        for decision in decisions:
            decision["decision"] = json.loads(decision.pop("decision_json"))
        if run.get("result_json"):
            run["result"] = json.loads(run.pop("result_json"))
        run["stages"] = stages
        run["publish_attempts"] = attempts
        run["decisions"] = decisions
        return run


def main():
    import argparse
    parser = argparse.ArgumentParser(description="OvO run store")
    parser.add_argument("--db", required=True, help="SQLite file, created if missing")
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="Write one run as JSON")
    exp.add_argument("--run-key", required=True)
    exp.add_argument("--out", default=None, help="Output file, or stdout when omitted")
    args = parser.parse_args()
    with RunStore(args.db) as store:
        if args.command == "export":
            record = store.export_run(args.run_key)
            if record is None:
                print(f"No run with key {args.run_key}", file=sys.stderr)
                raise SystemExit(1)
            text = json.dumps(record, indent=2)
            if args.out:
                Path(args.out).write_text(text + "\n")
                print(f"Run exported to {args.out}")
            else:
                print(text)


if __name__ == "__main__":
    import sys
    main()
