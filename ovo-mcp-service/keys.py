#!/usr/bin/env python3
"""Scoped keys for the OvO MCP service.

One key per store. A key works for one store address only, and
for one merchant. The plaintext key is shown once, when it is
issued, and never stored. Only its SHA-256 hash lives in the
store. A key for store A, used on store B, is refused and logged.

Key shape: ovo_sk_ followed by 32 hex characters from a random
32-byte secret. The prefix lets a reader tell an OvO key at a
glance, and lets a log scrubber find one without seeing the
secret part.
"""
import hashlib
import secrets

PREFIX = "ovo_sk_"


def issue_key(store, merchant_id, store_url, created_at):
    """Create a key for one store. Returns the plaintext key once.
    Only the hash is recorded."""
    plaintext = PREFIX + secrets.token_hex(16)
    key_hash = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    store.record_key(key_hash, merchant_id, store_url, created_at)
    return plaintext


def verify_key(store, plaintext, store_url):
    """Check a key against one store address. Returns the key row
    when the key exists, is not revoked, and belongs to this
    store. Returns None otherwise, with a reason string."""
    if not plaintext or not plaintext.startswith(PREFIX):
        return None, "key missing or not an OvO key"
    key_hash = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    row = store.get_key(key_hash)
    if row is None:
        return None, "unknown key"
    if row["revoked"]:
        return None, "key revoked"
    if (row["store_url"] or "").rstrip("/") != (store_url or "").rstrip("/"):
        return None, "key belongs to another store"
    return row, ""
