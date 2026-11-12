#!/usr/bin/env python3
"""Tests for scoped keys: one key per store, hash only, refusal
on the wrong store."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from keys import PREFIX, issue_key, verify_key
from mcp_store import McpStore

STORE_A = "https://store-a.example"
STORE_B = "https://store-b.example"


class KeysTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = McpStore(Path(self.tmp.name) / "mcp.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_key_shape(self):
        key = issue_key(self.store, "m1", STORE_A, "2026-11-12T00:00:00+00:00")
        self.assertTrue(key.startswith(PREFIX))
        self.assertEqual(len(key), len(PREFIX) + 32)

    def test_key_verifies_for_its_store(self):
        key = issue_key(self.store, "m1", STORE_A, "2026-11-12T00:00:00+00:00")
        row, reason = verify_key(self.store, key, STORE_A)
        self.assertIsNotNone(row)
        self.assertEqual(reason, "")
        self.assertEqual(row["merchant_id"], "m1")

    def test_key_refused_on_another_store(self):
        key = issue_key(self.store, "m1", STORE_A, "2026-11-12T00:00:00+00:00")
        row, reason = verify_key(self.store, key, STORE_B)
        self.assertIsNone(row)
        self.assertIn("another store", reason)

    def test_unknown_key_refused(self):
        row, reason = verify_key(self.store, PREFIX + "0" * 32, STORE_A)
        self.assertIsNone(row)
        self.assertEqual(reason, "unknown key")

    def test_revoked_key_refused(self):
        import hashlib
        key = issue_key(self.store, "m1", STORE_A, "2026-11-12T00:00:00+00:00")
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        self.store.revoke_key(key_hash)
        row, reason = verify_key(self.store, key, STORE_A)
        self.assertIsNone(row)
        self.assertEqual(reason, "key revoked")

    def test_plaintext_never_stored(self):
        key = issue_key(self.store, "m1", STORE_A, "2026-11-12T00:00:00+00:00")
        dump = (Path(self.tmp.name) / "mcp.db").read_bytes()
        self.assertNotIn(key.encode(), dump)
        self.assertNotIn(key[len(PREFIX):].encode(), dump)

    def test_trailing_slash_does_not_matter(self):
        key = issue_key(self.store, "m1", STORE_A, "2026-11-12T00:00:00+00:00")
        row, _ = verify_key(self.store, key, STORE_A + "/")
        self.assertIsNotNone(row)


if __name__ == "__main__":
    unittest.main()
