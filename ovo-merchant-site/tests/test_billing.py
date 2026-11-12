#!/usr/bin/env python3
"""Tests for item 4: billing. Exact numbers throughout. A paid
order bills at the rate in force when it was paid. A refund
gives no credit. A rate change never changes an old order's
fee. No real money moves: these are test records only."""
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE.parent
sys.path.insert(0, str(SITE))

import auth  # noqa: E402
import billing  # noqa: E402
from store import MerchantStore  # noqa: E402

STORE_URL = "https://store.example.com"


class BillingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MerchantStore(Path(self.tmp.name) / "test.db")
        auth.create_merchant(self.store, "m1", "Launch Merchant",
                             "m1@example.com", "correct-horse")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _card_on_file(self, merchant="m1"):
        auth.record_card_authorization(
            self.store, merchant, "pm_test_reference", "visa", "4242")

    def test_fee_math_exact(self):
        self.assertEqual(billing.fee_cents(10000, Decimal("1.5")), 150)
        self.assertEqual(billing.fee_cents(3333, Decimal("1.5")), 50)
        self.assertEqual(billing.fee_cents(1000, Decimal("1.0")), 10)
        self.assertEqual(billing.fee_cents(0, Decimal("1.5")), 0)
        self.assertEqual(billing.fee_cents(199, Decimal("1.5")), 3)

    def test_launch_customer_bills_1_percent(self):
        # Merchant m1 is customer 1 of 100: launch edition.
        self.assertEqual(
            billing.rate_in_force(self.store, "m1"), Decimal("1.0"))
        order = billing.record_paid_order(
            self.store, "m1", "order-1", 10000, "CAD", STORE_URL,
            paid_at="2026-11-12T10:00:00Z")
        self.assertEqual(order["rate_percent"], "1.0")
        self.assertEqual(order["fee_cents"], 100)

    def test_customer_101_bills_1_5_percent(self):
        for i in range(2, 102):
            self.store.create_merchant(
                f"m{i}", f"Merchant {i}", f"m{i}@example.com",
                "hash", "salt", i, "2026-11-12T00:00:00Z")
        self.assertEqual(
            billing.rate_in_force(self.store, "m100"), Decimal("1.0"))
        self.assertEqual(
            billing.rate_in_force(self.store, "m101"), Decimal("1.5"))
        order = billing.record_paid_order(
            self.store, "m101", "order-101", 10000, "CAD", STORE_URL,
            paid_at="2026-11-12T10:00:00Z")
        self.assertEqual(order["fee_cents"], 150)

    def test_rate_change_does_not_change_old_order(self):
        first = billing.record_paid_order(
            self.store, "m1", "order-before", 10000, "CAD", STORE_URL,
            paid_at="2026-11-12T10:00:00Z")
        self.assertEqual(first["fee_cents"], 100)  # launch 1%
        change = billing.set_rate(
            self.store, "m1", "2.0", "greg", "test change",
            at="2026-11-13T00:00:00Z")
        self.assertEqual(change["old_rate"], "1.0")
        self.assertEqual(change["new_rate"], "2.0")
        self.assertEqual(change["changed_by"], "greg")
        second = billing.record_paid_order(
            self.store, "m1", "order-after", 10000, "CAD", STORE_URL,
            paid_at="2026-11-14T10:00:00Z")
        self.assertEqual(second["fee_cents"], 200)  # new 2%
        again = self.store.get_order("order-before")
        self.assertEqual(again["fee_cents"], 100)
        self.assertEqual(again["rate_percent"], "1.0")
        changes = self.store.rate_changes("m1")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["reason"], "test change")

    def test_refund_gives_no_credit(self):
        order = billing.record_paid_order(
            self.store, "m1", "order-refund", 10000, "CAD", STORE_URL,
            paid_at="2026-11-12T10:00:00Z")
        self.assertEqual(order["fee_cents"], 100)
        refunded = billing.record_refund(
            self.store, "order-refund", refunded_at="2026-11-13T10:00:00Z")
        self.assertEqual(refunded["status"], "refunded")
        self.assertEqual(refunded["fee_cents"], 100)
        self._card_on_file()
        bill = billing.monthly_bill(self.store, "m1", 2026, 11)
        self.assertEqual(len(bill["lines"]), 1)
        self.assertEqual(bill["lines"][0]["fee_cents"], 100)
        self.assertEqual(bill["lines"][0]["refund_credit_cents"], 0)
        self.assertEqual(bill["total_fee_cents"], 100)

    def test_monthly_bill_lists_paid_orders_only(self):
        self._card_on_file()
        billing.record_paid_order(
            self.store, "m1", "order-nov-1", 10000, "CAD", STORE_URL,
            paid_at="2026-11-05T10:00:00Z")
        billing.record_paid_order(
            self.store, "m1", "order-nov-2", 20000, "CAD", STORE_URL,
            paid_at="2026-11-20T10:00:00Z")
        billing.record_paid_order(
            self.store, "m1", "order-oct", 50000, "CAD", STORE_URL,
            paid_at="2026-10-15T10:00:00Z")
        bill = billing.monthly_bill(self.store, "m1", 2026, 11)
        self.assertEqual(bill["order_count"], 2)
        self.assertEqual(bill["total_fee_cents"], 100 + 200)
        self.assertEqual(
            [line["order_id"] for line in bill["lines"]],
            ["order-nov-1", "order-nov-2"])

    def test_bill_blocked_without_card_authorization(self):
        billing.record_paid_order(
            self.store, "m1", "order-nocard", 10000, "CAD", STORE_URL,
            paid_at="2026-11-12T10:00:00Z")
        bill = billing.monthly_bill(self.store, "m1", 2026, 11)
        self.assertIsNotNone(bill["blocked"])
        self.assertIn("go-live gate", bill["blocked"])
        self.assertEqual(bill["total_fee_cents"], 0)
        self._card_on_file()
        bill = billing.monthly_bill(self.store, "m1", 2026, 11)
        self.assertIsNone(bill["blocked"])
        self.assertEqual(bill["total_fee_cents"], 100)

    def test_duplicate_order_refused(self):
        billing.record_paid_order(
            self.store, "m1", "order-dup", 10000, "CAD", STORE_URL,
            paid_at="2026-11-12T10:00:00Z")
        with self.assertRaises(ValueError):
            billing.record_paid_order(
                self.store, "m1", "order-dup", 10000, "CAD", STORE_URL,
                paid_at="2026-11-12T11:00:00Z")

    def test_bad_rate_refused(self):
        with self.assertRaises(ValueError):
            billing.set_rate(self.store, "m1", "0", "greg", "zero")
        with self.assertRaises(ValueError):
            billing.set_rate(self.store, "m1", "101", "greg", "too big")


if __name__ == "__main__":
    unittest.main()
