#!/usr/bin/env python3
"""Tests for the domain ownership check: a check file or a
WordPress admin proof, and an unowned domain refused."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain import check_domain, check_file, check_wordpress_admin
from mcp_store import McpStore

STORE = "https://shop.example"
MERCHANT = "m1"


def fake_get_factory(status, body):
    def fake_get(url, headers=None):
        return status, body
    return fake_get


class DomainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = McpStore(Path(self.tmp.name) / "mcp.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_check_file_passes_on_exact_line(self):
        passed, detail = check_file(
            STORE, MERCHANT,
            http_get=fake_get_factory(200, "ovo-ownership m1\n"))
        self.assertTrue(passed)
        self.assertIn("matches merchant m1", detail)

    def test_check_file_fails_on_wrong_merchant(self):
        passed, _ = check_file(
            STORE, MERCHANT,
            http_get=fake_get_factory(200, "ovo-ownership someone-else\n"))
        self.assertFalse(passed)

    def test_check_file_fails_on_404(self):
        passed, detail = check_file(
            STORE, MERCHANT, http_get=fake_get_factory(404, ""))
        self.assertFalse(passed)
        self.assertIn("HTTP 404", detail)

    def test_wordpress_admin_proof_passes(self):
        body = ('{"id": 1, "slug": "owner", "capabilities": '
                '{"install_plugins": true}}')
        passed, detail = check_wordpress_admin(
            STORE, "owner", "app-password",
            http_get=fake_get_factory(200, body))
        self.assertTrue(passed)
        self.assertIn("WordPress admin proof", detail)

    def test_wordpress_proof_fails_without_plugin_right(self):
        body = ('{"id": 2, "slug": "editor", "capabilities": '
                '{"edit_posts": true}}')
        passed, _ = check_wordpress_admin(
            STORE, "editor", "app-password",
            http_get=fake_get_factory(200, body))
        self.assertFalse(passed)

    def test_wordpress_proof_fails_on_401(self):
        passed, detail = check_wordpress_admin(
            STORE, "owner", "wrong",
            http_get=fake_get_factory(401, ""))
        self.assertFalse(passed)
        self.assertIn("401", detail)

    def test_passed_check_records_verified(self):
        passed, status, _ = check_domain(
            self.store, STORE, MERCHANT,
            http_get=fake_get_factory(200, "ovo-ownership m1\n"),
            checked_at="2026-11-12T00:00:00+00:00")
        self.assertTrue(passed)
        self.assertEqual(status, "verified")
        row = self.store.get_domain(STORE)
        self.assertEqual(row["status"], "verified")
        self.assertEqual(row["method"], "check_file")
        self.assertIn(STORE, self.store.verified_stores())

    def test_failed_check_records_unchecked_and_is_not_listed(self):
        passed, status, _ = check_domain(
            self.store, STORE, MERCHANT,
            http_get=fake_get_factory(404, ""),
            checked_at="2026-11-12T00:00:00+00:00")
        self.assertFalse(passed)
        self.assertEqual(status, "unchecked")
        self.assertNotIn(STORE, self.store.verified_stores())


if __name__ == "__main__":
    unittest.main()
