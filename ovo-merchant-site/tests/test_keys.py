#!/usr/bin/env python3
"""Tests for the merchant site key routes: sign-up, issue, status,
and revoke. The key is shown once and only its hash is stored.
A new key takes back the old one. A key works for one store only.
No live store, no live Stripe."""
import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE.parent
MCP_SERVICE = SITE.parent / "ovo-mcp-service"
sys.path.insert(0, str(SITE))
sys.path.insert(0, str(MCP_SERVICE))

TMP = tempfile.TemporaryDirectory()
os.environ["OVO_MERCHANT_DB"] = str(Path(TMP.name) / "app.db")

import app as merchant_app  # noqa: E402
from keys import verify_key  # noqa: E402
from mcp_store import McpStore  # noqa: E402

STORE_URL = "https://store.example.com"
OTHER_URL = "https://other.example.com"


class KeyRoutesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.pop("DATABASE_URL", None)
        merchant_app.MCP_DB_PATH = str(Path(TMP.name) / "mcp.db")
        # The app module is shared with any other test module that
        # imported it first, and that module's temp database is
        # gone by now. Point the app at this module's own file.
        from store import MerchantStore
        merchant_app.STORE = MerchantStore(
            str(Path(TMP.name) / "app.db"))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0),
                                         merchant_app.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()
        cls.store = merchant_app.STORE
        cls.mcp_path = Path(TMP.name) / "mcp.db"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        # The merchant store is shared with any other test module
        # that imported the app first. Close it only when it is
        # the file this module created.
        if str(cls.store.db_path).startswith(str(Path(TMP.name))):
            cls.store.close()
        TMP.cleanup()

    def _req(self, method, path, body=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def _mcp(self):
        return McpStore(self.mcp_path)

    def _signup_and_signin(self, merchant_id=None):
        # A fresh id per test: the merchant store is shared with
        # any other test module that imported the app first.
        merchant_id = merchant_id or "m-" + uuid.uuid4().hex[:8]
        status, body = self._req("POST", "/api/signup", {
            "merchant_id": merchant_id, "name": "Test Merchant",
            "email": f"{merchant_id}@example.com",
            "password": "correct-horse"})
        self.assertEqual(status, 201, body)
        status, body = self._req("POST", "/api/signin", {
            "merchant_id": merchant_id, "password": "correct-horse",
            "store_id": STORE_URL})
        self.assertEqual(status, 200, body)
        return json.loads(body)["token"], merchant_id

    def _issue(self, token, store_url=STORE_URL):
        return self._req("POST", "/api/keys", {
            "session_token": token, "store_url": store_url})

    def test_signup_duplicate_and_short_password_refused(self):
        mid = "m-" + uuid.uuid4().hex[:8]
        status, body = self._req("POST", "/api/signup", {
            "merchant_id": mid, "name": "Second",
            "email": f"{mid}@example.com", "password": "correct-horse"})
        self.assertEqual(status, 201, body)
        status, body = self._req("POST", "/api/signup", {
            "merchant_id": mid, "name": "Second",
            "email": f"{mid}@example.com", "password": "correct-horse"})
        self.assertEqual(status, 400)
        status, body = self._req("POST", "/api/signup", {
            "merchant_id": "m-" + uuid.uuid4().hex[:8], "name": "Third",
            "email": "m3@example.com", "password": "short"})
        self.assertEqual(status, 400)
        status, body = self._req("POST", "/api/signup", {
            "merchant_id": "m-" + uuid.uuid4().hex[:8], "name": "Fourth"})
        self.assertEqual(status, 400)

    def test_issue_needs_signin(self):
        status, body = self._issue("no-such-token")
        self.assertEqual(status, 401)

    def test_issue_returns_key_once_and_stores_only_hash(self):
        token, merchant_id = self._signup_and_signin()
        status, body = self._issue(token)
        self.assertEqual(status, 200, body)
        data = json.loads(body)
        key = data["key"]
        self.assertTrue(key.startswith("ovo_sk_"))
        self.assertEqual(len(key), len("ovo_sk_") + 32)
        self.assertTrue(data["shown_once"])
        mcp = self._mcp()
        try:
            row, reason = verify_key(mcp, key, STORE_URL)
            self.assertIsNotNone(row, reason)
            self.assertEqual(row["merchant_id"], merchant_id)
            self.assertEqual(row["store_url"], STORE_URL)
            # Only the hash is stored: the key itself is nowhere
            # in the stored row.
            blob = json.dumps(row)
            self.assertNotIn(key, blob)
            self.assertIn(
                hashlib.sha256(key.encode()).hexdigest(), blob)
        finally:
            mcp.close()

    def test_second_issue_revokes_first(self):
        token, merchant_id = self._signup_and_signin()
        _, body = self._issue(token)
        first = json.loads(body)["key"]
        status, body = self._issue(token)
        self.assertEqual(status, 200, body)
        second = json.loads(body)["key"]
        self.assertNotEqual(first, second)
        mcp = self._mcp()
        try:
            row, reason = verify_key(mcp, first, STORE_URL)
            self.assertIsNone(row)
            self.assertEqual(reason, "key revoked")
            row, reason = verify_key(mcp, second, STORE_URL)
            self.assertIsNotNone(row, reason)
        finally:
            mcp.close()

    def test_key_refused_on_another_store(self):
        token, merchant_id = self._signup_and_signin()
        _, body = self._issue(token)
        key = json.loads(body)["key"]
        mcp = self._mcp()
        try:
            row, reason = verify_key(mcp, key, OTHER_URL)
            self.assertIsNone(row)
            self.assertEqual(reason, "key belongs to another store")
        finally:
            mcp.close()

    def test_revoke_and_status(self):
        token, merchant_id = self._signup_and_signin()
        _, body = self._issue(token)
        key = json.loads(body)["key"]
        status, body = self._req("POST", "/api/keys/status", {
            "session_token": token, "store_url": STORE_URL})
        self.assertEqual(status, 200, body)
        data = json.loads(body)
        self.assertTrue(data["has_live_key"])
        self.assertIsNotNone(data["created_at_utc"])
        self.assertNotIn("key", data)
        status, body = self._req("POST", "/api/keys/revoke", {
            "session_token": token, "store_url": STORE_URL})
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["keys_revoked"], 1)
        mcp = self._mcp()
        try:
            row, reason = verify_key(mcp, key, STORE_URL)
            self.assertIsNone(row)
            self.assertEqual(reason, "key revoked")
        finally:
            mcp.close()
        status, body = self._req("POST", "/api/keys/status", {
            "session_token": token, "store_url": STORE_URL})
        self.assertFalse(json.loads(body)["has_live_key"])

    def test_issue_refused_for_bad_store_address(self):
        token, merchant_id = self._signup_and_signin()
        status, body = self._issue(token, "store.example.com")
        self.assertEqual(status, 400)

    def test_issue_refused_for_session_of_another_store(self):
        token, merchant_id = self._signup_and_signin()
        status, body = self._issue(token, OTHER_URL)
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
