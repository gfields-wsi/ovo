#!/usr/bin/env python3
"""Store for the OvO MCP service.

Keys, domain checks, and refused calls live here, not in loose
files. SQLite is the store now, the same shape as the runner store
in ovo-runner/store.py, so managed Postgres on Render replaces this
module in Phase 7 without changing the callers.

Tables:
- scoped_keys: one row per key hash. A key belongs to one store
  only. The plaintext key is never stored, only its SHA-256 hash.
- domains: one row per store address, with the ownership check
  status. "verified" means the merchant proved they own the
  address. "unchecked" means no proof yet. Only verified stores
  appear in a listing.
- runs: one row per run the service started, with the run key, the
  store, the merchant, and the status. The runner's own store
  holds the stage detail; this table is the service's index of
  what it started.
- refusals: every refused call, with the tool name, the reason,
  and the time. A blocked approve, publish, or pay lands here.
"""
import hashlib
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS scoped_keys (
  key_hash TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL,
  store_url TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS domains (
  store_url TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL,
  status TEXT NOT NULL,
  method TEXT,
  checked_at_utc TEXT,
  detail TEXT
);
CREATE TABLE IF NOT EXISTS runs (
  run_key TEXT PRIMARY KEY,
  store_url TEXT NOT NULL,
  merchant_id TEXT NOT NULL,
  status TEXT NOT NULL,
  test_only INTEGER NOT NULL DEFAULT 0,
  started_at_utc TEXT NOT NULL,
  finished_at_utc TEXT,
  result_json TEXT
);
CREATE TABLE IF NOT EXISTS refusals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at_utc TEXT NOT NULL,
  tool TEXT NOT NULL,
  reason TEXT NOT NULL,
  store_url TEXT,
  merchant_id TEXT,
  detail TEXT
);
"""


def hash_key(plaintext):
    """SHA-256 of a key. The plaintext is never stored."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


class McpStore:
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

    # -- scoped keys --

    def record_key(self, key_hash, merchant_id, store_url, created_at):
        self.conn.execute(
            "INSERT INTO scoped_keys (key_hash, merchant_id, store_url, created_at_utc) "
            "VALUES (?, ?, ?, ?)",
            (key_hash, merchant_id, store_url, created_at))
        self.conn.commit()

    def get_key(self, key_hash):
        row = self.conn.execute(
            "SELECT * FROM scoped_keys WHERE key_hash = ?", (key_hash,)).fetchone()
        return dict(row) if row else None

    def revoke_key(self, key_hash):
        self.conn.execute(
            "UPDATE scoped_keys SET revoked = 1 WHERE key_hash = ?", (key_hash,))
        self.conn.commit()

    # -- domains --

    def record_domain(self, store_url, merchant_id, status, method, checked_at, detail=""):
        self.conn.execute(
            "INSERT OR REPLACE INTO domains "
            "(store_url, merchant_id, status, method, checked_at_utc, detail) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (store_url, merchant_id, status, method, checked_at, detail))
        self.conn.commit()

    def get_domain(self, store_url):
        row = self.conn.execute(
            "SELECT * FROM domains WHERE store_url = ?", (store_url,)).fetchone()
        return dict(row) if row else None

    def verified_stores(self):
        """Store addresses with a passed ownership check. Only these
        appear in a listing. Unchecked stores never appear."""
        rows = self.conn.execute(
            "SELECT store_url FROM domains WHERE status = 'verified'").fetchall()
        return [r["store_url"] for r in rows]

    # -- runs --

    def record_run(self, run_key, store_url, merchant_id, status, test_only, started_at):
        self.conn.execute(
            "INSERT INTO runs (run_key, store_url, merchant_id, status, test_only, started_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_key, store_url, merchant_id, status, 1 if test_only else 0, started_at))
        self.conn.commit()

    def get_run(self, run_key):
        row = self.conn.execute(
            "SELECT * FROM runs WHERE run_key = ?", (run_key,)).fetchone()
        if not row:
            return None
        out = dict(row)
        if out.get("result_json"):
            out["result"] = json.loads(out["result_json"])
        return out

    def update_run(self, run_key, status, finished_at, result=None):
        self.conn.execute(
            "UPDATE runs SET status = ?, finished_at_utc = ?, result_json = ? "
            "WHERE run_key = ?",
            (status, finished_at,
             json.dumps(result) if result is not None else None, run_key))
        self.conn.commit()

    # -- refusals --

    def record_refusal(self, at_utc, tool, reason, store_url=None, merchant_id=None, detail=""):
        self.conn.execute(
            "INSERT INTO refusals (at_utc, tool, reason, store_url, merchant_id, detail) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (at_utc, tool, reason, store_url, merchant_id, detail))
        self.conn.commit()

    def refusals(self, tool=None):
        if tool:
            rows = self.conn.execute(
                "SELECT * FROM refusals WHERE tool = ? ORDER BY id", (tool,)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM refusals ORDER BY id").fetchall()
        return [dict(r) for r in rows]
