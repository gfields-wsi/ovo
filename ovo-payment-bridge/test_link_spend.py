#!/usr/bin/env python3
"""Phase 6 tests: merchant payment profiles and Link spend requests.

One profile per merchant, derived from the merchant Stripe
account id, stored per merchant, never shared across stores.
Spend requests go through an adapter: mock in test mode, real
fails closed. No real Link call is made here.
"""
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "ovo-merchant-site"))

import link  # noqa: E402
from store import MerchantStore  # noqa: E402

CTX = ("Buying trail boots size 10 from the merchant store for a "
       "customer who asked for waterproof leather boots. ") * 2
STORE_A = "https://store-a.example.com"
STORE_B = "https://store-b.example.com"


class ProfileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MerchantStore(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_profile_derived_and_stored_per_merchant(self):
        profile = link.save_profile(
            self.store, "m1", STORE_A, "acct_test_123")
        self.assertTrue(
            profile["seller_network_id"].startswith("profile_test_"))
        self.assertEqual(profile["stripe_account_id"], "acct_test_123")
        self.assertEqual(profile["store_url"], STORE_A)
        self.assertEqual(profile["revoked"], 0)
        same = link.save_profile(
            self.store, "m1", STORE_A, "acct_test_123")
        self.assertEqual(
            same["seller_network_id"], profile["seller_network_id"])

    def test_profile_same_account_same_id(self):
        a = link.derive_profile_id("acct_test_123")
        b = link.derive_profile_id("acct_test_123")
        self.assertEqual(a, b)
        self.assertNotEqual(
            a, link.derive_profile_id("acct_test_456"))

    def test_profile_for_other_store_refused(self):
        link.save_profile(self.store, "m1", STORE_A, "acct_test_123")
        with self.assertRaises(ValueError):
            link.save_profile(
                self.store, "m1", STORE_B, "acct_test_123")
        with self.assertRaises(ValueError):
            link.profile_for_store(self.store, "m1", STORE_B)

    def test_profile_bad_account_refused(self):
        with self.assertRaises(ValueError):
            link.save_profile(self.store, "m1", STORE_A, "not-an-acct")
        with self.assertRaises(ValueError):
            link.save_profile(self.store, "m1", STORE_A, "")

    def test_real_derivation_fails_closed(self):
        with self.assertRaises(link.LinkNotProven):
            link.derive_profile_id("acct_test_123", test_mode=False)

    def test_revoked_profile_refused(self):
        link.save_profile(self.store, "m1", STORE_A, "acct_test_123")
        self.store.revoke_payment_profile("m1")
        with self.assertRaises(ValueError):
            link.profile_for_store(self.store, "m1", STORE_A)


class SpendRequestTest(unittest.TestCase):
    def setUp(self):
        self.adapter = link.MockLinkAdapter()

    def _request(self, amount_cents=10000, currency="USD",
                 network_id="profile_test_abc", key="key-1"):
        return self.adapter.create_spend_request(
            amount_cents, currency, network_id, CTX, key,
            "m1", STORE_A)

    def test_spend_request_for_exact_total(self):
        request = self._request()
        self.assertEqual(request["amount_cents"], 10000)
        self.assertEqual(request["currency"], "USD")
        self.assertEqual(request["network_id"], "profile_test_abc")
        self.assertEqual(request["status"], "pending_approval")
        self.assertTrue(request["mock_link"])
        self.assertTrue(request["test_mode"])

    def test_spend_request_idempotent_by_key(self):
        first = self._request()
        second = self._request()
        self.assertEqual(first["id"], second["id"])

    def test_spend_request_short_context_refused(self):
        with self.assertRaises(ValueError):
            self.adapter.create_spend_request(
                10000, "USD", "profile_test_abc", "short", "k2",
                "m1", STORE_A)

    def test_spend_request_bad_currency_refused(self):
        with self.assertRaises(ValueError):
            self.adapter.create_spend_request(
                10000, "EUR", "profile_test_abc", CTX, "k3",
                "m1", STORE_A)

    def test_spend_request_zero_amount_refused(self):
        with self.assertRaises(ValueError):
            self.adapter.create_spend_request(
                0, "USD", "profile_test_abc", CTX, "k4", "m1", STORE_A)

    def test_mock_token_tied_to_request(self):
        request = self._request()
        self.adapter.approve_spend_request(request["id"])
        token = self.adapter.issue_token(request["id"])
        self.assertTrue(token["id"].startswith("spt_"))
        self.assertEqual(token["max_amount_cents"], 10000)
        self.assertEqual(token["network_id"], "profile_test_abc")
        self.assertTrue(token["mock_link"])

    def test_token_needs_approval(self):
        request = self._request()
        with self.assertRaises(ValueError):
            self.adapter.issue_token(request["id"])

    def test_denied_request_issues_no_token(self):
        request = self._request()
        self.adapter.deny_spend_request(request["id"])
        with self.assertRaises(ValueError):
            self.adapter.issue_token(request["id"])

    def test_real_adapter_fails_closed(self):
        real = link.RealLinkAdapter()
        with self.assertRaises(link.LinkNotProven):
            real.create_spend_request(
                10000, "USD", "profile_test_abc", CTX, "k9",
                "m1", STORE_A)
        with self.assertRaises(link.LinkNotProven):
            real.issue_token("lsrq_anything")


if __name__ == "__main__":
    unittest.main()
