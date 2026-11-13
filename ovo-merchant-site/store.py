#!/usr/bin/env python3
"""State store for the OvO merchant site.

Merchants, sign-in sessions, WordPress sign-ins, card
authorizations, packets, decisions, installs, rate changes,
orders, and bills live here, not in loose files, so a host
restart loses no merchant record. SQLite is the store now.
The callers use only the MerchantStore methods below. Managed
Postgres on Render replaces this module in Phase 7 without
changing those callers: same method names, same record shapes.
The SQL here stays to plain parameterised statements, so the
move is a straight port.

No password, token, or card number is ever stored in plain
text here. Session tokens are stored as a SHA-256 hash only.
WordPress passwords and app passwords are never stored at
all: they are used once, for one call, then dropped. Card
authorizations store a reference only: brand and last four
digits, never the card number.
"""
import hashlib
import json
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS merchants (
  merchant_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  password_salt TEXT NOT NULL,
  customer_index INTEGER NOT NULL,
  created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL,
  store_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  issued_at_utc TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS wp_signins (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  merchant_id TEXT NOT NULL,
  store_url TEXT NOT NULL,
  wp_username TEXT NOT NULL,
  verified_at_utc TEXT NOT NULL,
  method TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS card_auths (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  merchant_id TEXT NOT NULL,
  auth_ref TEXT NOT NULL,
  brand TEXT NOT NULL,
  last4 TEXT NOT NULL,
  authorized_at_utc TEXT NOT NULL,
  revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS packets (
  run_key TEXT PRIMARY KEY,
  store_id TEXT NOT NULL,
  merchant_id TEXT,
  packet_json TEXT NOT NULL,
  created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_key TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  decision_json TEXT NOT NULL,
  record_json TEXT NOT NULL,
  recorded_at_utc TEXT NOT NULL,
  recorded_by TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS installs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  store_url TEXT NOT NULL,
  plugin TEXT NOT NULL,
  version TEXT NOT NULL,
  status TEXT NOT NULL,
  activated INTEGER NOT NULL DEFAULT 0,
  installed_at_utc TEXT NOT NULL,
  detail_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  merchant_id TEXT NOT NULL,
  old_rate TEXT NOT NULL,
  new_rate TEXT NOT NULL,
  changed_by TEXT NOT NULL,
  changed_at_utc TEXT NOT NULL,
  reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL,
  store_url TEXT NOT NULL,
  subtotal_cents INTEGER NOT NULL,
  currency TEXT NOT NULL,
  rate_percent TEXT NOT NULL,
  fee_cents INTEGER NOT NULL,
  session_id TEXT,
  cart_id TEXT,
  actor TEXT NOT NULL,
  status TEXT NOT NULL,
  paid_at_utc TEXT NOT NULL,
  refunded_at_utc TEXT
);
CREATE TABLE IF NOT EXISTS read_sessions (
  session_id TEXT PRIMARY KEY,
  store_url TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  product_ids_json TEXT NOT NULL,
  at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS carts (
  cart_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  items_json TEXT NOT NULL,
  created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payment_profiles (
  merchant_id TEXT PRIMARY KEY,
  store_url TEXT NOT NULL,
  stripe_account_id TEXT NOT NULL,
  seller_network_id TEXT NOT NULL,
  derived_from TEXT NOT NULL,
  derived_at_utc TEXT NOT NULL,
  revoked INTEGER NOT NULL DEFAULT 0
);
"""


def token_hash(token):
    """Hash of a session token. The token itself is never stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class MerchantStore:
    """One store. Open it, use it, close it. Callers never write SQL.

    Each thread gets its own connection to the same file, so the
    HTTP server can serve requests from worker threads while
    tests use the main thread. The schema is created on every
    new connection, idempotently."""

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        _ = self.conn

    @property
    def conn(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            conn.executescript(SCHEMA)
            conn.commit()
            self._local.conn = conn
        return conn

    def close(self):
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # -- merchants -------------------------------------------------
    def create_merchant(self, merchant_id, name, email, password_hash,
                        password_salt, customer_index, created_at_utc):
        self.conn.execute(
            "INSERT INTO merchants (merchant_id, name, email, password_hash,"
            " password_salt, customer_index, created_at_utc)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (merchant_id, name, email, password_hash, password_salt,
             customer_index, created_at_utc))
        self.conn.commit()

    def get_merchant(self, merchant_id):
        row = self.conn.execute(
            "SELECT * FROM merchants WHERE merchant_id = ?",
            (merchant_id,)).fetchone()
        return dict(row) if row else None

    def merchant_count(self):
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM merchants").fetchone()
        return row["n"]

    # -- sessions --------------------------------------------------
    def create_session(self, session_id, merchant_id, store_id, kind,
                       token, issued_at_utc, expires_at_utc):
        self.conn.execute(
            "INSERT INTO sessions (session_id, merchant_id, store_id, kind,"
            " token_hash, issued_at_utc, expires_at_utc, revoked)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            (session_id, merchant_id, store_id, kind, token_hash(token),
             issued_at_utc, expires_at_utc))
        self.conn.commit()

    def get_session(self, session_id):
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,)).fetchone()
        return dict(row) if row else None

    def get_session_by_token(self, token):
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE token_hash = ?",
            (token_hash(token),)).fetchone()
        return dict(row) if row else None

    def revoke_session(self, session_id):
        self.conn.execute(
            "UPDATE sessions SET revoked = 1 WHERE session_id = ?",
            (session_id,))
        self.conn.commit()

    # -- WordPress sign-ins ----------------------------------------
    def record_wp_signin(self, merchant_id, store_url, wp_username,
                         verified_at_utc, method):
        cur = self.conn.execute(
            "INSERT INTO wp_signins (merchant_id, store_url, wp_username,"
            " verified_at_utc, method) VALUES (?, ?, ?, ?, ?)",
            (merchant_id, store_url, wp_username, verified_at_utc, method))
        self.conn.commit()
        return cur.lastrowid

    def latest_wp_signin(self, merchant_id, store_url):
        row = self.conn.execute(
            "SELECT * FROM wp_signins WHERE merchant_id = ? AND store_url = ?"
            " ORDER BY id DESC LIMIT 1",
            (merchant_id, store_url)).fetchone()
        return dict(row) if row else None

    # -- card authorizations ---------------------------------------
    def record_card_auth(self, merchant_id, auth_ref, brand, last4,
                         authorized_at_utc):
        cur = self.conn.execute(
            "INSERT INTO card_auths (merchant_id, auth_ref, brand, last4,"
            " authorized_at_utc, revoked) VALUES (?, ?, ?, ?, ?, 0)",
            (merchant_id, auth_ref, brand, last4, authorized_at_utc))
        self.conn.commit()
        return cur.lastrowid

    def latest_card_auth(self, merchant_id):
        row = self.conn.execute(
            "SELECT * FROM card_auths WHERE merchant_id = ? AND revoked = 0"
            " ORDER BY id DESC LIMIT 1",
            (merchant_id,)).fetchone()
        return dict(row) if row else None

    def revoke_card_auth(self, auth_id):
        self.conn.execute(
            "UPDATE card_auths SET revoked = 1 WHERE id = ?",
            (auth_id,))
        self.conn.commit()

    # -- packets and decisions -------------------------------------
    def save_packet(self, run_key, store_id, merchant_id, packet,
                    created_at_utc):
        self.conn.execute(
            "INSERT OR REPLACE INTO packets (run_key, store_id, merchant_id,"
            " packet_json, created_at_utc) VALUES (?, ?, ?, ?, ?)",
            (run_key, store_id, merchant_id, json.dumps(packet),
             created_at_utc))
        self.conn.commit()

    def get_packet(self, run_key):
        row = self.conn.execute(
            "SELECT * FROM packets WHERE run_key = ?",
            (run_key,)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["packet"] = json.loads(out["packet_json"])
        return out

    def save_decision(self, run_key, fingerprint, decision, record,
                      recorded_at_utc, recorded_by):
        cur = self.conn.execute(
            "INSERT INTO decisions (run_key, fingerprint, decision_json,"
            " record_json, recorded_at_utc, recorded_by)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (run_key, fingerprint, json.dumps(decision),
             json.dumps(record), recorded_at_utc, recorded_by))
        self.conn.commit()
        return cur.lastrowid

    def latest_decision(self, run_key, fingerprint):
        row = self.conn.execute(
            "SELECT * FROM decisions WHERE run_key = ? AND fingerprint = ?"
            " ORDER BY id DESC LIMIT 1",
            (run_key, fingerprint)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["decision"] = json.loads(out["decision_json"])
        out["record"] = json.loads(out["record_json"])
        return out

    # -- installs ---------------------------------------------------
    def record_install(self, store_url, plugin, version, status, activated,
                       installed_at_utc, detail):
        cur = self.conn.execute(
            "INSERT INTO installs (store_url, plugin, version, status,"
            " activated, installed_at_utc, detail_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (store_url, plugin, version, status, 1 if activated else 0,
             installed_at_utc, json.dumps(detail)))
        self.conn.commit()
        return cur.lastrowid

    def latest_install(self, store_url, plugin):
        row = self.conn.execute(
            "SELECT * FROM installs WHERE store_url = ? AND plugin = ?"
            " ORDER BY id DESC LIMIT 1",
            (store_url, plugin)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["detail"] = json.loads(out["detail_json"])
        return out

    # -- rate changes ----------------------------------------------
    def record_rate_change(self, merchant_id, old_rate, new_rate,
                           changed_by, changed_at_utc, reason):
        cur = self.conn.execute(
            "INSERT INTO rate_changes (merchant_id, old_rate, new_rate,"
            " changed_by, changed_at_utc, reason) VALUES (?, ?, ?, ?, ?, ?)",
            (merchant_id, old_rate, new_rate, changed_by,
             changed_at_utc, reason))
        self.conn.commit()
        return cur.lastrowid

    def rate_changes(self, merchant_id):
        rows = self.conn.execute(
            "SELECT * FROM rate_changes WHERE merchant_id = ?"
            " ORDER BY id ASC",
            (merchant_id,)).fetchall()
        return [dict(r) for r in rows]

    # -- orders -----------------------------------------------------
    def save_order(self, order):
        self.conn.execute(
            "INSERT INTO orders (order_id, merchant_id, store_url,"
            " subtotal_cents, currency, rate_percent, fee_cents, session_id,"
            " cart_id, actor, status, paid_at_utc, refunded_at_utc)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (order["order_id"], order["merchant_id"], order["store_url"],
             order["subtotal_cents"], order["currency"],
             order["rate_percent"], order["fee_cents"],
             order.get("session_id"), order.get("cart_id"),
             order["actor"], order["status"], order["paid_at_utc"],
             order.get("refunded_at_utc")))
        self.conn.commit()

    def get_order(self, order_id):
        row = self.conn.execute(
            "SELECT * FROM orders WHERE order_id = ?",
            (order_id,)).fetchone()
        return dict(row) if row else None

    def mark_refunded(self, order_id, refunded_at_utc):
        self.conn.execute(
            "UPDATE orders SET status = 'refunded', refunded_at_utc = ?"
            " WHERE order_id = ?",
            (refunded_at_utc, order_id))
        self.conn.commit()

    def orders_in_month(self, merchant_id, year, month):
        """Paid orders for a merchant in a calendar month, by paid date."""
        rows = self.conn.execute(
            "SELECT * FROM orders WHERE merchant_id = ?"
            " AND substr(paid_at_utc, 1, 7) = ? ORDER BY paid_at_utc ASC",
            (merchant_id, f"{year:04d}-{month:02d}")).fetchall()
        return [dict(r) for r in rows]

    # -- attribution: read sessions and carts ----------------------
    def save_read_session(self, session_id, store_url, agent_id,
                          product_ids, at_utc):
        self.conn.execute(
            "INSERT INTO read_sessions (session_id, store_url, agent_id,"
            " product_ids_json, at_utc) VALUES (?, ?, ?, ?, ?)",
            (session_id, store_url, agent_id, json.dumps(product_ids),
             at_utc))
        self.conn.commit()

    def get_read_session(self, session_id):
        row = self.conn.execute(
            "SELECT * FROM read_sessions WHERE session_id = ?",
            (session_id,)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["product_ids"] = json.loads(out["product_ids_json"])
        return out

    def save_cart(self, cart_id, session_id, items, created_at_utc):
        self.conn.execute(
            "INSERT INTO carts (cart_id, session_id, items_json,"
            " created_at_utc) VALUES (?, ?, ?, ?)",
            (cart_id, session_id, json.dumps(items), created_at_utc))
        self.conn.commit()

    def get_cart(self, cart_id):
        row = self.conn.execute(
            "SELECT * FROM carts WHERE cart_id = ?",
            (cart_id,)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["items"] = json.loads(out["items_json"])
        return out

    # -- payment profiles: one per merchant, never shared ---------
    def save_payment_profile(self, merchant_id, store_url,
                             stripe_account_id, seller_network_id,
                             derived_from, derived_at_utc):
        self.conn.execute(
            "INSERT OR REPLACE INTO payment_profiles (merchant_id,"
            " store_url, stripe_account_id, seller_network_id,"
            " derived_from, derived_at_utc, revoked)"
            " VALUES (?, ?, ?, ?, ?, ?, 0)",
            (merchant_id, store_url, stripe_account_id,
             seller_network_id, derived_from, derived_at_utc))
        self.conn.commit()

    def get_payment_profile(self, merchant_id):
        row = self.conn.execute(
            "SELECT * FROM payment_profiles WHERE merchant_id = ?",
            (merchant_id,)).fetchone()
        return dict(row) if row else None

    def revoke_payment_profile(self, merchant_id):
        self.conn.execute(
            "UPDATE payment_profiles SET revoked = 1 WHERE merchant_id = ?",
            (merchant_id,))
        self.conn.commit()
