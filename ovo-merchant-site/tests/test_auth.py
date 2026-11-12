#!/usr/bin/env python3
"""Tests for item 1: merchant sign-in, WordPress sign-in, card
sign-in. No live store, no live Stripe, no real secrets. The
WordPress check uses a stubbed HTTP getter."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE.parent
sys.path.insert(0, str(SITE))
sys.path.insert(0, str(SITE.parent))

import auth  # noqa: E402
from store import MerchantStore  # noqa: E402


class AuthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MerchantStore(Path(self.tmp.name) / "test.db")
        auth.create_merchant(self.store, "m1", "Test Merchant",
                             "m1@example.com", "correct-horse")
        auth.create_merchant(self.store, "m2", "Second Merchant",
                             "m2@example.com", "correct-horse")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_sign_in_ok(self):
        result, error = auth.sign_in_ovo(self.store, "m1",
                                         "correct-horse", "store-a")
        self.assertIsNone(error)
        self.assertIn("token", result)
        session = result["session"]
        self.assertEqual(session["merchant_id"], "m1")
        self.assertEqual(session["store_id"], "store-a")
        self.assertEqual(session["submitted_by"], "merchant")
        self.assertFalse(session["revoked"])

    def test_wrong_password_fails(self):
        result, error = auth.sign_in_ovo(self.store, "m1",
                                         "wrong-password", "store-a")
        self.assertIsNone(result)
        self.assertEqual(error, "wrong password")

    def test_unknown_merchant_fails(self):
        result, error = auth.sign_in_ovo(self.store, "nope",
                                         "correct-horse", "store-a")
        self.assertIsNone(result)
        self.assertEqual(error, "unknown merchant")

    def test_store_address_required(self):
        result, error = auth.sign_in_ovo(self.store, "m1",
                                         "correct-horse", "")
        self.assertIsNone(result)
        self.assertEqual(error, "store address is required")

    def test_session_verifies_for_same_store(self):
        result, _ = auth.sign_in_ovo(self.store, "m1",
                                     "correct-horse", "store-a")
        session, error = auth.verify_session(self.store, result["token"],
                                             "store-a")
        self.assertIsNone(error)
        self.assertEqual(session["merchant_id"], "m1")

    def test_session_refused_for_other_store(self):
        result, _ = auth.sign_in_ovo(self.store, "m1",
                                     "correct-horse", "store-a")
        session, error = auth.verify_session(self.store, result["token"],
                                             "store-b")
        self.assertIsNone(session)
        self.assertIn("different store", error)

    def test_revoked_session_refused(self):
        result, _ = auth.sign_in_ovo(self.store, "m1",
                                     "correct-horse", "store-a")
        auth.revoke_session(self.store, result["session"]["session_id"])
        session, error = auth.verify_session(self.store, result["token"],
                                             "store-a")
        self.assertIsNone(session)
        self.assertIn("revoked", error)

    def test_expired_session_refused(self):
        result, _ = auth.sign_in_ovo(self.store, "m1",
                                     "correct-horse", "store-a")
        row = self.store.get_session(result["session"]["session_id"])
        self.store.conn.execute(
            "UPDATE sessions SET expires_at_utc = '2020-01-01T00:00:00Z'"
            " WHERE session_id = ?", (row["session_id"],))
        self.store.conn.commit()
        session, error = auth.verify_session(self.store, result["token"],
                                             "store-a")
        self.assertIsNone(session)
        self.assertIn("expired", error)

    def test_token_is_stored_hashed_only(self):
        result, _ = auth.sign_in_ovo(self.store, "m1",
                                     "correct-horse", "store-a")
        row = self.store.get_session(result["session"]["session_id"])
        self.assertNotIn(result["token"], row["token_hash"])
        self.assertEqual(len(row["token_hash"]), 64)

    def test_password_is_stored_hashed_only(self):
        merchant = self.store.get_merchant("m1")
        self.assertNotIn("correct-horse", merchant["password_hash"])
        self.assertNotEqual(merchant["password_hash"], "correct-horse")

    def test_wordpress_signin_verified(self):
        def fake_get(url, headers):
            self.assertTrue(url.endswith("/wp-json/wp/v2/users/me"))
            self.assertTrue(headers["Authorization"].startswith("Basic "))
            return 200, json.dumps({
                "id": 1, "slug": "admin",
                "capabilities": {"install_plugins": True,
                                 "activate_plugins": True}})
        verification, error = auth.verify_wordpress_signin(
            "https://store.example.com", "admin", "app-password-here",
            http_get=fake_get)
        self.assertIsNone(error)
        self.assertEqual(verification["wp_username"], "admin")
        self.assertEqual(verification["method"],
                         "wordpress_app_password")
        auth_id = auth.record_wordpress_signin(self.store, "m1",
                                               verification)
        self.assertTrue(auth_id)
        saved = self.store.latest_wp_signin(
            "m1", "https://store.example.com")
        self.assertEqual(saved["wp_username"], "admin")
        self.assertNotIn("app-password-here", json.dumps(saved))

    def test_wordpress_signin_refused_on_401(self):
        def fake_get(url, headers):
            return 401, "Unauthorized"
        verification, error = auth.verify_wordpress_signin(
            "https://store.example.com", "admin", "bad-password",
            http_get=fake_get)
        self.assertIsNone(verification)
        self.assertIn("401", error)

    def test_wordpress_signin_needs_plugin_rights(self):
        def fake_get(url, headers):
            return 200, json.dumps({
                "id": 2, "slug": "editor",
                "capabilities": {"install_plugins": False}})
        verification, error = auth.verify_wordpress_signin(
            "https://store.example.com", "editor", "app-password-here",
            http_get=fake_get)
        self.assertIsNone(verification)
        self.assertIn("cannot install plugins", error)

    def test_wordpress_signin_is_not_card_signin(self):
        # The two sign-ins are separate records, in separate
        # tables, with separate fields. One never stands in for
        # the other.
        def fake_get(url, headers):
            return 200, json.dumps({"id": 1, "capabilities": {}})
        verification, _ = auth.verify_wordpress_signin(
            "https://store.example.com", "admin", "app-password-here",
            http_get=fake_get)
        auth.record_wordpress_signin(self.store, "m1", verification)
        self.assertIsNone(self.store.latest_card_auth("m1"))
        self.assertIsNotNone(self.store.latest_wp_signin(
            "m1", "https://store.example.com"))

    def test_card_authorization_reference_only(self):
        result, error = auth.record_card_authorization(
            self.store, "m1", "pm_test_reference", "visa", "4242")
        self.assertIsNone(error)
        self.assertEqual(result["brand"], "visa")
        self.assertEqual(result["last4"], "4242")
        saved = self.store.latest_card_auth("m1")
        self.assertEqual(saved["auth_ref"], "pm_test_reference")
        self.assertNotIn("4242424242424242", json.dumps(saved))

    def test_card_authorization_needs_four_digits(self):
        result, error = auth.record_card_authorization(
            self.store, "m1", "pm_test_reference", "visa", "42")
        self.assertIsNone(result)
        self.assertIn("four digits", error)

    def test_customer_index_counts_merchants(self):
        first = self.store.get_merchant("m1")
        second = self.store.get_merchant("m2")
        self.assertEqual(first["customer_index"], 1)
        self.assertEqual(second["customer_index"], 2)


if __name__ == "__main__":
    unittest.main()
