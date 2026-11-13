#!/usr/bin/env python3
"""Phase 6 tests: bridge attribution events and billing.

The bridge records the session to cart to paid order link.
The host verifies the signed event, then records the order
through Phase 4 billing: a linked agent order bills at the
rate in force (1.5 percent for a standard merchant, 1 percent
for a launch merchant), a test order bills zero, and a human
order with no agent link bills zero. No link means no bill.
"""
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE.parent / "ovo-merchant-site"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SITE))

import importlib.util  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Both components have a module named attribution. Each is loaded
# by file path, so the two modules do not collide.
bridge_attribution = _load("bridge_attribution", HERE / "bridge_attribution.py")
site_attribution = _load("site_attribution", SITE / "attribution.py")
billing = _load("site_billing", SITE / "billing.py")
auth = _load("site_auth", SITE / "auth.py")
from store import MerchantStore  # noqa: E402

STORE_A = "https://store-a.example.com"
STORE_B = "https://store-b.example.com"
KEY = "test-signing-key-only"


def _order(session_id="read-1", cart_id="cart-1", order_id="order-1",
           subtotal_cents=10000, store_url=STORE_A):
    return {
        "session_id": session_id, "cart_id": cart_id,
        "order_id": order_id, "subtotal_cents": subtotal_cents,
        "currency": "USD", "store_url": store_url,
        "merchant_id": "m1", "paid_at_utc": "2026-11-12T10:00:00Z",
    }


class EventTest(unittest.TestCase):
    def test_event_carries_the_link(self):
        event = bridge_attribution.build_attribution_event(
            _order(), "agent", "human-1")
        self.assertEqual(event["session_id"], "read-1")
        self.assertEqual(event["cart_id"], "cart-1")
        self.assertEqual(event["order_id"], "order-1")
        self.assertEqual(event["agent_route"], "agent")
        self.assertEqual(event["human_approval_id"], "human-1")
        self.assertEqual(event["subtotal_cents"], 10000)
        self.assertNotIn("fee_cents", event)

    def test_event_missing_session_refused(self):
        order = _order(session_id=None)
        with self.assertRaises(ValueError):
            bridge_attribution.build_attribution_event(
                order, "agent", "human-1")

    def test_unlinked_event_has_no_session_or_cart(self):
        event = bridge_attribution.build_unlinked_event(_order())
        self.assertIsNone(event["session_id"])
        self.assertIsNone(event["cart_id"])
        self.assertEqual(event["agent_route"], "human")

    def test_sign_and_verify(self):
        event = bridge_attribution.build_attribution_event(
            _order(), "agent", "human-1")
        signature = bridge_attribution.sign_event(event, KEY)
        self.assertTrue(
            bridge_attribution.verify_event(event, signature, KEY))

    def test_changed_event_fails_verification(self):
        event = bridge_attribution.build_attribution_event(
            _order(), "agent", "human-1")
        signature = bridge_attribution.sign_event(event, KEY)
        event["subtotal_cents"] = 9999
        self.assertFalse(
            bridge_attribution.verify_event(event, signature, KEY))

    def test_wrong_key_fails_verification(self):
        event = bridge_attribution.build_attribution_event(
            _order(), "agent", "human-1")
        signature = bridge_attribution.sign_event(event, KEY)
        self.assertFalse(
            bridge_attribution.verify_event(event, signature, "other"))

    def test_signing_without_key_refused(self):
        event = bridge_attribution.build_attribution_event(
            _order(), "agent", "human-1")
        with self.assertRaises(ValueError):
            bridge_attribution.sign_event(event, "")


class RecordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MerchantStore(Path(self.tmp.name) / "test.db")
        # Merchant m1 is a launch customer (index 1): 1 percent.
        auth.create_merchant(self.store, "m1", "Launch Merchant",
                             "m1@example.com", "correct-horse")
        # Merchant m102 is past the launch edition (index 101):
        # 1.5 percent. The row is written directly so the test
        # does not hash 100 passwords to get there.
        self.store.create_merchant(
            "m102", "Standard Merchant", "m102@example.com",
            "hash-not-used-in-this-test", "salt-not-used", 101,
            "2026-11-12T10:00:00Z")
        read = site_attribution.log_read_session(
            self.store, STORE_A, "muse", [12])
        self.read = read
        cart = site_attribution.create_cart(
            self.store, read["session_id"],
            [{"product_id": 12, "quantity": 1}])
        self.cart = cart

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _event(self, merchant_id="m102", order_id="order-1",
               test_mode=False, store_url=STORE_A):
        return {
            "session_id": self.read["session_id"],
            "cart_id": self.cart["cart_id"],
            "order_id": order_id,
            "agent_route": "agent",
            "human_approval_id": "human-1",
            "subtotal_cents": 10000,
            "currency": "USD",
            "store_url": store_url,
            "merchant_id": merchant_id,
            "test_mode": test_mode,
            "paid_at_utc": "2026-11-12T10:00:00Z",
        }

    def test_linked_order_bills_at_1_5_percent(self):
        event = self._event()
        signature = bridge_attribution.sign_event(event, KEY)
        order = site_attribution.receive_attribution_event(
            self.store, "m102", event, signature, KEY)
        self.assertEqual(order["rate_percent"], "1.5")
        self.assertEqual(order["fee_cents"], 150)
        self.assertEqual(order["session_id"], self.read["session_id"])
        self.assertEqual(order["cart_id"], self.cart["cart_id"])

    def test_launch_merchant_bills_at_1_percent(self):
        event = self._event(merchant_id="m1")
        signature = bridge_attribution.sign_event(event, KEY)
        order = site_attribution.receive_attribution_event(
            self.store, "m1", event, signature, KEY)
        self.assertEqual(order["rate_percent"], "1.0")
        self.assertEqual(order["fee_cents"], 100)

    def test_test_order_bills_zero_with_link_kept(self):
        event = self._event(test_mode=True)
        signature = bridge_attribution.sign_event(event, KEY)
        order = site_attribution.receive_attribution_event(
            self.store, "m102", event, signature, KEY)
        self.assertEqual(order["fee_cents"], 0)
        self.assertEqual(order["session_id"], self.read["session_id"])
        self.assertEqual(order["cart_id"], self.cart["cart_id"])

    def test_human_order_bills_zero(self):
        event = bridge_attribution.build_unlinked_event(_order())
        signature = bridge_attribution.sign_event(event, KEY)
        order = site_attribution.receive_attribution_event(
            self.store, "m102", event, signature, KEY)
        self.assertEqual(order["fee_cents"], 0)
        self.assertIsNone(order["session_id"])

    def test_wrong_signature_refused_before_recording(self):
        event = self._event()
        with self.assertRaises(ValueError):
            site_attribution.receive_attribution_event(
                self.store, "m102", event, "bad-signature", KEY)
        self.assertIsNone(self.store.get_order("order-1"))

    def test_unknown_session_refused(self):
        event = self._event()
        event["session_id"] = "read-does-not-exist"
        signature = bridge_attribution.sign_event(event, KEY)
        with self.assertRaises(ValueError):
            site_attribution.receive_attribution_event(
                self.store, "m102", event, signature, KEY)

    def test_event_for_other_store_refused(self):
        event = self._event(store_url=STORE_B)
        signature = bridge_attribution.sign_event(event, KEY)
        with self.assertRaises(ValueError):
            site_attribution.receive_attribution_event(
                self.store, "m102", event, signature, KEY)

    def test_half_link_refused(self):
        event = self._event()
        event["cart_id"] = None
        signature = bridge_attribution.sign_event(event, KEY)
        with self.assertRaises(ValueError):
            site_attribution.receive_attribution_event(
                self.store, "m102", event, signature, KEY)

    def test_monthly_bill_counts_linked_and_zero_lines(self):
        auth.record_card_authorization(
            self.store, "m102", "pm_test_reference", "visa", "4242")
        event = self._event()
        signature = bridge_attribution.sign_event(event, KEY)
        site_attribution.receive_attribution_event(
            self.store, "m102", event, signature, KEY)
        site_attribution.record_human_order(
            self.store, "m102", "order-human-1", 10000, "USD", STORE_A,
            paid_at="2026-11-12T11:00:00Z")
        bill = billing.monthly_bill(self.store, "m102", 2026, 11)
        self.assertEqual(bill["order_count"], 2)
        self.assertEqual(bill["total_fee_cents"], 150)


if __name__ == "__main__":
    unittest.main()
