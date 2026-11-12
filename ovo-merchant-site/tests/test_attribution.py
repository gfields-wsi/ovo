#!/usr/bin/env python3
"""Tests for item 5: attribution. The link from agent session
to cart to paid order is the proof. No link means no bill.
Test data only; no real money moves."""
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE.parent
sys.path.insert(0, str(SITE))

import attribution  # noqa: E402
import auth  # noqa: E402
import billing  # noqa: E402
from store import MerchantStore  # noqa: E402

STORE_A = "https://store-a.example.com"
STORE_B = "https://store-b.example.com"


class AttributionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MerchantStore(Path(self.tmp.name) / "test.db")
        auth.create_merchant(self.store, "m1", "Launch Merchant",
                             "m1@example.com", "correct-horse")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _linked_order(self, order_id="order-agent-1", subtotal=20000,
                      store_url=STORE_A, paid_at="2026-11-12T10:00:00Z"):
        read = attribution.log_read_session(
            self.store, store_url, "muse", [12, 13])
        cart = attribution.create_cart(
            self.store, read["session_id"],
            [{"product_id": 12, "quantity": 1}])
        order = attribution.record_linked_order(
            self.store, "m1", order_id, subtotal, "CAD", store_url,
            cart["cart_id"], paid_at=paid_at)
        return read, cart, order

    def test_full_link_bills_at_right_rate(self):
        read, cart, order = self._linked_order()
        self.assertEqual(order["session_id"], read["session_id"])
        self.assertEqual(order["cart_id"], cart["cart_id"])
        self.assertTrue(attribution.billable(self.store, order))
        # Launch merchant at 1 percent: $200.00 bills $2.00.
        self.assertEqual(order["rate_percent"], "1.0")
        self.assertEqual(order["fee_cents"], 200)
        self.assertEqual(attribution.fee_for(order), 200)

    def test_human_order_bills_zero(self):
        order = attribution.record_human_order(
            self.store, "m1", "order-human-1", 20000, "CAD", STORE_A,
            paid_at="2026-11-12T10:00:00Z")
        self.assertIsNone(order["session_id"])
        self.assertIsNone(order["cart_id"])
        self.assertFalse(attribution.billable(self.store, order))
        self.assertEqual(order["fee_cents"], 0)
        self.assertEqual(attribution.fee_for(order), 0)

    def test_session_without_cart_bills_zero(self):
        read = attribution.log_read_session(
            self.store, STORE_A, "muse", [12])
        order = billing.record_paid_order(
            self.store, "m1", "order-nocart", 20000, "CAD", STORE_A,
            session_id=read["session_id"], cart_id=None,
            paid_at="2026-11-12T10:00:00Z", billable=False)
        self.assertFalse(attribution.billable(self.store, order))
        self.assertEqual(order["fee_cents"], 0)

    def test_cart_needs_a_read_session(self):
        with self.assertRaises(ValueError):
            attribution.create_cart(
                self.store, "read-does-not-exist",
                [{"product_id": 12, "quantity": 1}])

    def test_session_for_store_a_refused_on_store_b(self):
        read, cart, _ = self._linked_order()
        self.assertEqual(read["store_url"], STORE_A)
        with self.assertRaises(ValueError) as ctx:
            attribution.record_linked_order(
                self.store, "m1", "order-wrong-store", 20000, "CAD",
                STORE_B, cart["cart_id"],
                paid_at="2026-11-12T10:00:00Z")
        self.assertIn("different store", str(ctx.exception))
        self.assertIsNone(self.store.get_order("order-wrong-store"))

    def test_monthly_bill_counts_only_linked_orders(self):
        auth.record_card_authorization(
            self.store, "m1", "pm_test_reference", "visa", "4242")
        self._linked_order(order_id="order-agent-1", subtotal=20000)
        attribution.record_human_order(
            self.store, "m1", "order-human-1", 20000, "CAD", STORE_A,
            paid_at="2026-11-12T11:00:00Z")
        bill = billing.monthly_bill(self.store, "m1", 2026, 11)
        self.assertEqual(bill["order_count"], 2)
        self.assertEqual(bill["total_fee_cents"], 200)
        human_line = [line for line in bill["lines"]
                      if line["order_id"] == "order-human-1"][0]
        self.assertEqual(human_line["fee_cents"], 0)

    def test_order_carries_session_and_cart_ids(self):
        read, cart, order = self._linked_order()
        saved = self.store.get_order(order["order_id"])
        self.assertEqual(saved["session_id"], read["session_id"])
        self.assertEqual(saved["cart_id"], cart["cart_id"])
        saved_read = self.store.get_read_session(read["session_id"])
        self.assertEqual(saved_read["agent_id"], "muse")
        self.assertEqual(saved_read["product_ids"], [12, 13])
        saved_cart = self.store.get_cart(cart["cart_id"])
        self.assertEqual(saved_cart["session_id"], read["session_id"])


if __name__ == "__main__":
    unittest.main()
