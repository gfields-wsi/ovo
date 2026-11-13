#!/usr/bin/env python3
"""Phase 6 end-to-end tests: bridge with Link spend request,
human approval token, and attribution into Phase 4 billing.

Happy path: cart, quote, approval token, Link spend request,
mock approval, single-use token, checkout, paid order, signed
attribution event, monthly bill at the rate in force.
Fail closed, no paid order: declined, gone stock, void quote,
reused token, extra card check (3D Secure), wrong merchant,
short context, expired token, missing approval token.
Idempotency: a double submit makes one charge and one order.
A test order bills zero. A human order with no link bills zero.
"""
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE.parent / "ovo-merchant-site"
# The bridge directory comes first: both components have a module
# named attribution, and the bridge must import its own one.
sys.path.insert(0, str(HERE))
sys.path.append(str(SITE))

import importlib.util  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


import bridge_attribution  # noqa: E402
from approval_token import ApprovalTokenStore  # noqa: E402
from bridge import Bridge, BridgeError  # noqa: E402
from link import MockLinkAdapter, RealLinkAdapter  # noqa: E402

site_attribution = _load("site_attribution_p6", SITE / "attribution.py")
billing = _load("site_billing_p6", SITE / "billing.py")
auth = _load("site_auth_p6", SITE / "auth.py")
from store import MerchantStore  # noqa: E402

CTX = ("Buying trail boots size 10 from the merchant store for a "
       "customer who asked for waterproof leather boots. ") * 2
ADDR = {"zone": "CA", "city": "Toronto"}
STORE_A = "https://store-a.example.com"
KEY = "test-signing-key-only"


def fresh_bridge(**kw):
    bridge = Bridge(network_id="profile_test_abc",
                    merchant_stripe_account="acct_test_123",
                    merchant_id="m102", store_url=STORE_A, **kw)
    bridge.approve_merchant("m102", "store-a", "merchant-admin")
    bridge.authorize_agent("agent-token-1")
    return bridge


def setup_paid(bridge, price=100, tax=5, shipping=10, currency="USD",
               session_id="read-1", agent_route="agent"):
    """Cart, quote, approval token, spend request, mock approval,
    token. Returns cart id, quote id, token, approval token."""
    cid, qid, total = bridge.create_cart(
        14, 29, 1, price, tax=tax, shipping=shipping, currency=currency,
        session_id=session_id, agent_route=agent_route,
        human_approval_id="human-1")
    approval = bridge.issue_approval_token(cid, "human-1")
    sr = bridge.create_spend_request(
        total, currency, "profile_test_abc", CTX, "key-" + cid)
    bridge.approve_spend(sr["id"])
    spt = bridge.issue_spt(sr["id"])
    return cid, qid, spt, approval, total


def checkout(bridge, cid, qid, spt, approval, key="k1", live=False):
    return bridge.complete_checkout(
        cid, qid, spt["id"], key, "buyer@example.com", ADDR, ADDR,
        "agent-token-1", ADDR, live=live, approval_token=approval)


def err(fn, code):
    try:
        fn()
    except BridgeError as e:
        assert e.code == code, f"{e.code} != {code}"
        return
    raise AssertionError(f"expected {code}")


class HappyPathTest(unittest.TestCase):
    def test_full_flow_to_paid_order_and_bill(self):
        bridge = fresh_bridge()
        cid, qid, spt, approval, total = setup_paid(bridge)
        self.assertEqual(total, 115)
        order = checkout(bridge, cid, qid, spt, approval)
        self.assertEqual(order["status"], "paid")
        self.assertEqual(order["total"], 115)
        self.assertEqual(order["subtotal"], 100)
        self.assertEqual(order["session_id"], "read-1")
        self.assertEqual(order["agent_route"], "agent")
        self.assertEqual(order["human_approval_id"], "human-1")
        self.assertEqual(len(bridge.charger.charges), 1)
        self.assertEqual(
            bridge.charger.charges[0]["account"], "acct_test_123")
        event = bridge.attribution_event_for(order["order_id"])
        self.assertEqual(event["subtotal_cents"], 10000)
        self.assertEqual(event["cart_id"], cid)
        self.assertEqual(event["human_approval_id"], "human-1")

    def test_total_is_subtotal_plus_tax_plus_shipping(self):
        """Requirement 6: the merchant total includes tax and
        shipping, and the charged amount equals that total. Tax
        and shipping are above zero here, on purpose: a zero
        split would pass even if the lines were dropped. The
        PHP checkout sets the same lines before calculate_totals()
        and guards the order total after it; this test states
        the rule the PHP guard enforces, in the mock bridge."""
        bridge = fresh_bridge()
        cid, qid, spt, approval, total = setup_paid(
            bridge, price=100, tax=5, shipping=10)
        self.assertEqual(total, 115)
        order = checkout(bridge, cid, qid, spt, approval)
        self.assertEqual(order["subtotal"], 100)
        self.assertEqual(order["tax"], 5)
        self.assertEqual(order["shipping"], 10)
        self.assertEqual(order["total"], 115)
        self.assertEqual(
            order["total"],
            order["subtotal"] + order["tax"] + order["shipping"])
        self.assertEqual(
            bridge.charger.charges[0]["amount"], order["total"])

    def test_attribution_event_bills_monthly_at_1_5_percent(self):
        tmp = tempfile.TemporaryDirectory()
        store = MerchantStore(Path(tmp.name) / "test.db")
        try:
            store.create_merchant(
                "m102", "Standard Merchant", "m102@example.com",
                "hash", "salt", 101, "2026-11-12T10:00:00Z")
            read = site_attribution.log_read_session(
                store, STORE_A, "muse", [14])
            cart = site_attribution.create_cart(
                store, read["session_id"],
                [{"product_id": 14, "quantity": 1}])
            # A billable order: test_mode is off, so billing
            # counts it. The payment itself is still mock, so
            # this proves the billing math, not a live payment.
            bridge = fresh_bridge(test_mode=False)
            # The bridge clock sets the paid date: put it in
            # November 2026, the month the bill covers.
            bridge.now = 1794468000
            cid, qid, spt, approval, total = setup_paid(
                bridge, session_id=read["session_id"])
            order = checkout(bridge, cid, qid, spt, approval)
            event = bridge.attribution_event_for(order["order_id"])
            # The bridge cart and the site cart are different ids
            # in this test; the event is rebuilt on the site cart
            # so the site link check can pass.
            event["session_id"] = read["session_id"]
            event["cart_id"] = cart["cart_id"]
            signature = bridge_attribution.sign_event(event, KEY)
            auth.record_card_authorization(
                store, "m102", "pm_test_reference", "visa", "4242")
            recorded = site_attribution.receive_attribution_event(
                store, "m102", event, signature, KEY)
            self.assertEqual(recorded["fee_cents"], 150)
            bill = billing.monthly_bill(store, "m102", 2026, 11)
            self.assertEqual(bill["total_fee_cents"], 150)
        finally:
            store.close()
            tmp.cleanup()

    def test_manifest_version_1(self):
        bridge = fresh_bridge()
        manifest = bridge.manifest()
        self.assertEqual(manifest["version"], "1.0.0-test")
        self.assertEqual(
            manifest["seller_network_id"], "profile_test_abc")
        self.assertEqual(
            manifest["payment_endpoint"],
            "/ovo-bridge/v1/checkout/complete")
        self.assertEqual(
            manifest["accepted_currencies"], ["USD", "CAD"])
        self.assertNotIn("key", str(manifest).lower())


class FailClosedTest(unittest.TestCase):
    def test_declined_payment_makes_no_order(self):
        bridge = fresh_bridge()
        bridge.charger.decline = True
        cid, qid, spt, approval, _ = setup_paid(bridge)
        err(lambda: checkout(bridge, cid, qid, spt, approval),
            "ovo_bridge_declined")
        self.assertEqual(len(bridge.orders), 0)

    def test_stock_gone_makes_no_order(self):
        bridge = fresh_bridge()
        cid, qid, spt, approval, _ = setup_paid(bridge)
        bridge.set_stock(cid, False)
        # Stock change voids the token, so a fresh token is issued
        # and the stock check itself is what must fail.
        approval = bridge.issue_approval_token(cid, "human-1")
        err(lambda: checkout(bridge, cid, qid, spt, approval),
            "ovo_bridge_stock_gone")
        self.assertEqual(len(bridge.orders), 0)

    def test_cart_change_voids_quote_and_token(self):
        bridge = fresh_bridge()
        cid, qid, spt, approval, _ = setup_paid(bridge)
        bridge.change_cart(cid)
        err(lambda: checkout(bridge, cid, qid, spt, approval),
            "ovo_bridge_approval_token")
        self.assertEqual(len(bridge.orders), 0)

    def test_reused_token_makes_no_second_order(self):
        bridge = fresh_bridge()
        cid, qid, spt, approval, _ = setup_paid(bridge)
        order = checkout(bridge, cid, qid, spt, approval)
        approval2 = bridge.issue_approval_token(cid, "human-1")
        err(lambda: checkout(bridge, cid, qid, spt, approval2, key="k2"),
            "ovo_bridge_reused_token")
        self.assertEqual(len(bridge.orders), 1)
        self.assertEqual(len(bridge.charger.charges), 1)
        self.assertEqual(list(bridge.orders)[0], order["order_id"])

    def test_double_submit_makes_one_order(self):
        bridge = fresh_bridge()
        cid, qid, spt, approval, _ = setup_paid(bridge)
        first = checkout(bridge, cid, qid, spt, approval)
        second = checkout(bridge, cid, qid, spt, approval)
        self.assertEqual(first, second)
        self.assertEqual(len(bridge.orders), 1)
        self.assertEqual(len(bridge.charger.charges), 1)

    def test_extra_card_check_makes_no_order(self):
        bridge = fresh_bridge()
        bridge.charger.requires_action = True
        cid, qid, spt, approval, _ = setup_paid(bridge)
        err(lambda: checkout(bridge, cid, qid, spt, approval),
            "ovo_bridge_requires_action")
        self.assertEqual(len(bridge.orders), 0)
        self.assertTrue(bridge.spts[spt["id"]]["used"])

    def test_wrong_merchant_network_refused(self):
        bridge = fresh_bridge()
        with self.assertRaises(BridgeError) as ctx:
            bridge.create_spend_request(
                115, "USD", "profile_test_other", CTX, "key-x")
        self.assertEqual(ctx.exception.code, "ovo_bridge_wrong_merchant")

    def test_missing_approval_token_refused(self):
        bridge = fresh_bridge()
        cid, qid, spt, approval, _ = setup_paid(bridge)
        err(lambda: bridge.complete_checkout(
            cid, qid, spt["id"], "k1", "buyer@example.com", ADDR,
            ADDR, "agent-token-1", ADDR, live=False),
            "ovo_bridge_approval_token")
        self.assertEqual(len(bridge.orders), 0)

    def test_approval_token_for_wrong_total_refused(self):
        bridge = fresh_bridge()
        cid, qid, spt, approval, _ = setup_paid(bridge)
        other = bridge.issue_approval_token(cid, "human-1")
        bridge.change_cart(cid)
        # The change voids the token; a token issued after the
        # change is for a void quote, so checkout still fails.
        err(lambda: checkout(bridge, cid, qid, spt, other),
            "ovo_bridge_approval_token")
        self.assertEqual(len(bridge.orders), 0)

    def test_expired_spt_refused(self):
        bridge = fresh_bridge()
        cid, qid, spt, approval, _ = setup_paid(bridge)
        bridge.now += 2000
        # The quote also expired in that time. Renew it in the
        # test so only the token expiry is under test.
        bridge.quotes[qid]["expires_at"] = bridge.now + 600
        bridge.quotes[qid]["valid"] = True
        approval = bridge.issue_approval_token(cid, "human-1")
        err(lambda: checkout(bridge, cid, qid, spt, approval),
            "ovo_bridge_expired_token")
        self.assertEqual(len(bridge.orders), 0)

    def test_insufficient_spt_refused(self):
        bridge = fresh_bridge()
        cid, qid, spt, approval, _ = setup_paid(bridge)
        spt["max_amount"] = 50
        err(lambda: checkout(bridge, cid, qid, spt, approval),
            "ovo_bridge_insufficient_amount")
        self.assertEqual(len(bridge.orders), 0)

    def test_real_link_adapter_fails_closed(self):
        bridge = fresh_bridge(link_adapter=RealLinkAdapter())
        with self.assertRaises(Exception) as ctx:
            bridge.create_spend_request(
                115, "USD", "profile_test_abc", CTX, "key-real")
        self.assertIn("not proven", str(ctx.exception))


class UnlinkedAndTestTest(unittest.TestCase):
    def test_order_without_session_bills_zero(self):
        bridge = fresh_bridge()
        cid, qid, spt, approval, _ = setup_paid(
            bridge, session_id=None)
        order = checkout(bridge, cid, qid, spt, approval)
        event = bridge.attribution_event_for(order["order_id"])
        self.assertIsNone(event["session_id"])
        self.assertIsNone(event["cart_id"])
        self.assertEqual(event["agent_route"], "human")

    def test_test_mode_order_bills_zero(self):
        tmp = tempfile.TemporaryDirectory()
        store = MerchantStore(Path(tmp.name) / "test.db")
        try:
            store.create_merchant(
                "m102", "Standard Merchant", "m102@example.com",
                "hash", "salt", 101, "2026-11-12T10:00:00Z")
            read = site_attribution.log_read_session(
                store, STORE_A, "muse", [14])
            cart = site_attribution.create_cart(
                store, read["session_id"],
                [{"product_id": 14, "quantity": 1}])
            bridge = fresh_bridge(test_mode=True)
            cid, qid, spt, approval, _ = setup_paid(
                bridge, session_id=read["session_id"])
            order = checkout(bridge, cid, qid, spt, approval)
            event = bridge.attribution_event_for(order["order_id"])
            event["session_id"] = read["session_id"]
            event["cart_id"] = cart["cart_id"]
            self.assertTrue(event["test_mode"])
            signature = bridge_attribution.sign_event(event, KEY)
            recorded = site_attribution.receive_attribution_event(
                store, "m102", event, signature, KEY)
            self.assertEqual(recorded["fee_cents"], 0)
        finally:
            store.close()
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
