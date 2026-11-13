#!/usr/bin/env python3
"""Phase 6 tests: single-use human approval tokens.

A token binds one human approval to one cart and one total.
It is single use. A cart change, price change, or stock
change voids it. An expired token, a reused token, or a token
for another cart or total is refused.
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from approval_token import ApprovalTokenError, ApprovalTokenStore  # noqa: E402

NOW = 1700000000


class ApprovalTokenTest(unittest.TestCase):
    def setUp(self):
        self.store = ApprovalTokenStore()

    def _token(self, cart="cart-1", total=100, currency="USD",
               human="human-1"):
        return self.store.issue(cart, total, currency, "read-1",
                                human, now=NOW)

    def test_issue_and_validate_once(self):
        token = self._token()
        record = self.store.validate(
            token, "cart-1", 100, "USD", now=NOW + 10)
        self.assertEqual(record["human_approval_id"], "human-1")
        self.assertEqual(record["session_id"], "read-1")

    def test_second_use_refused(self):
        token = self._token()
        self.store.validate(token, "cart-1", 100, "USD", now=NOW + 10)
        with self.assertRaises(ApprovalTokenError):
            self.store.validate(
                token, "cart-1", 100, "USD", now=NOW + 20)

    def test_wrong_cart_refused(self):
        token = self._token()
        with self.assertRaises(ApprovalTokenError):
            self.store.validate(
                token, "cart-2", 100, "USD", now=NOW + 10)

    def test_wrong_total_refused(self):
        token = self._token()
        with self.assertRaises(ApprovalTokenError):
            self.store.validate(
                token, "cart-1", 101, "USD", now=NOW + 10)

    def test_wrong_currency_refused(self):
        token = self._token()
        with self.assertRaises(ApprovalTokenError):
            self.store.validate(
                token, "cart-1", 100, "CAD", now=NOW + 10)

    def test_expired_token_refused(self):
        token = self._token()
        with self.assertRaises(ApprovalTokenError):
            self.store.validate(
                token, "cart-1", 100, "USD", now=NOW + 601)

    def test_unknown_token_refused(self):
        with self.assertRaises(ApprovalTokenError):
            self.store.validate(
                "appr_doesnotexist", "cart-1", 100, "USD", now=NOW)

    def test_cart_change_voids_token(self):
        token = self._token()
        self.store.void_for_cart("cart-1")
        with self.assertRaises(ApprovalTokenError):
            self.store.validate(
                token, "cart-1", 100, "USD", now=NOW + 10)

    def test_void_for_cart_leaves_other_cart_alone(self):
        token_a = self._token(cart="cart-1")
        token_b = self._token(cart="cart-2")
        self.store.void_for_cart("cart-1")
        with self.assertRaises(ApprovalTokenError):
            self.store.validate(
                token_a, "cart-1", 100, "USD", now=NOW + 10)
        self.store.validate(token_b, "cart-2", 100, "USD", now=NOW + 10)

    def test_human_approval_id_required(self):
        with self.assertRaises(ValueError):
            self.store.issue("cart-1", 100, "USD", "read-1", "",
                             now=NOW)


if __name__ == "__main__":
    unittest.main()
