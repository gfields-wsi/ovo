#!/usr/bin/env python3
"""Tests for the merchant site app: the HTTP routes end to end
against a throwaway database. No live store, no live Stripe.
The install route is tested for its gates here; the live
install itself is proven in test_install_live."""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE.parent
sys.path.insert(0, str(SITE))

TMP = tempfile.TemporaryDirectory()
os.environ["OVO_MERCHANT_DB"] = str(Path(TMP.name) / "app.db")

import app as merchant_app  # noqa: E402
import approval  # noqa: E402
import auth  # noqa: E402

PHASE3_DIFF = Path.home() / "workspace" / "ovo-test-env" / "phase3-diff.json"


class AppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0),
                                         merchant_app.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()
        cls.store = merchant_app.STORE
        auth.create_merchant(cls.store, "m1", "Test Merchant",
                             "m1@example.com", "correct-horse")
        diff = json.loads(PHASE3_DIFF.read_text())
        cls.packet = approval.build_packet(diff)
        # The Phase 3 diff came from the demo store. This test
        # reviews it as the test store's packet.
        cls.packet["store_id"] = "https://store.example.com"
        cls.store.save_packet("run-1", "https://store.example.com",
                              "m1", cls.packet, "2026-11-12T00:00:00Z")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.store.close()
        TMP.cleanup()

    def _req(self, method, path, body=None, headers=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json",
                                              **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def _signin(self):
        status, body = self._req("POST", "/api/signin", {
            "merchant_id": "m1", "password": "correct-horse",
            "store_id": "https://store.example.com"})
        self.assertEqual(status, 200, body)
        return json.loads(body)["token"]

    def test_health(self):
        status, body = self._req("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"ok": True})

    def test_signin_wrong_password(self):
        status, body = self._req("POST", "/api/signin", {
            "merchant_id": "m1", "password": "wrong",
            "store_id": "https://store.example.com"})
        self.assertEqual(status, 401)

    def test_review_page_shows_62_rows(self):
        status, body = self._req("GET", "/review/run-1")
        self.assertEqual(status, 200)
        page = body.decode()
        self.assertIn("Review your store fixes", page)
        self.assertEqual(page.count("<tr>"), 62 + 1)
        status, body = self._req("GET", "/api/review/run-1")
        self.assertEqual(status, 200)
        packet = json.loads(body)
        self.assertEqual(packet["presented_count"], 62)

    def test_decide_one_group_via_http(self):
        token = self._signin()
        status, body = self._req("POST", "/api/decide", {
            "session_token": token, "run_key": "run-1",
            "approved_by": "Merchant One",
            "groups": [{"band": "95_plus", "submitted": True,
                        "rejections": [
                            {"product_id": 12,
                             "field": "_ovo_material"}]}]})
        self.assertEqual(status, 200, body)
        record = json.loads(body)["record"]
        self.assertEqual(record["status"], "approved_partial")
        self.assertEqual(record["publishable_count"], 61)
        keys = {(r["product_id"], r["field"])
                for r in record["approved_rows"]}
        self.assertNotIn((12, "_ovo_material"), keys)

    def test_decide_without_session_refused(self):
        status, body = self._req("POST", "/api/decide", {
            "run_key": "run-1", "approved_by": "Merchant One",
            "groups": [{"band": "95_plus", "submitted": True,
                        "rejections": []}]})
        self.assertEqual(status, 401)

    def test_downloads_serve_the_plugin_zip(self):
        status, body = self._req("GET",
                                 "/downloads/ovo-enrichment-1.0.0.zip")
        # The zip is built on install; before any install the
        # download is missing. Build it here the way install does.
        self.assertEqual(status, 404)
        import install as install_mod
        zip_path, digest, _ = install_mod.build_package(
            merchant_app.PACKAGE_DIR)
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/downloads/{zip_path.name}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                self.assertEqual(resp.status, 200)
                self.assertEqual(resp.headers["X-SHA256"], digest)
                self.assertEqual(resp.headers["Content-Type"],
                                 "application/zip")
                self.assertTrue(len(resp.read()) > 10000)
        finally:
            zip_path.unlink()

    def test_billing_gate_then_bill(self):
        status, body = self._req(
            "GET", "/api/billing/m1?year=2026&month=11")
        self.assertEqual(status, 200)
        bill = json.loads(body)
        self.assertIsNotNone(bill["blocked"])
        token = self._signin()
        status, body = self._req("POST", "/api/card-auth", {
            "session_token": token, "auth_ref": "pm_test_reference",
            "brand": "visa", "last4": "4242"})
        self.assertEqual(status, 200, body)
        status, body = self._req(
            "GET", "/api/billing/m1?year=2026&month=11")
        bill = json.loads(body)
        self.assertIsNone(bill["blocked"])
        self.assertEqual(bill["total_fee_cents"], 0)

    def test_install_refused_without_wordpress_signin(self):
        token = self._signin()
        status, body = self._req("POST", "/api/install", {
            "session_token": token,
            "store_url": "https://store.example.com",
            "wp_username": "admin", "wp_password": "secret"})
        self.assertEqual(status, 403)
        self.assertIn("WordPress", json.loads(body)["error"])

    def test_wordpress_signin_refused_for_unreachable_store(self):
        token = self._signin()
        status, body = self._req("POST", "/api/wordpress-signin", {
            "session_token": token,
            "store_url": "https://store.example.com",
            "wp_username": "admin", "app_password": "secret"})
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
