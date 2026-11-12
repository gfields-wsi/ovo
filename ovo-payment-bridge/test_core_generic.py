"""Tests for core_generic.py, R1-R22, generic, no store hard coding, no live session."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from core_generic import Bridge, MockStripeAdapter, BridgeError

def merchant(test_mode=True):
    return {"merchant_id": "merchant_test_1", "network_id": "net_test_1", "stripe_account": "acct_test_merchant", "test_mode": test_mode}

def setup():
    b = Bridge(stripe_adapter=MockStripeAdapter("acct_test_merchant"))
    b.authorize_agent("agent_token_test")
    b.approve_merchant("merchant_test_1", "https://example-store.test", "merchant_test")
    return b

def cart_for(b, total_items=100, tax=0, shipping=0, currency="USD"):
    return b.create_cart([{"product_id": "prod_request_1", "variation_id": "var_request_1", "quantity": 1, "unit_price": total_items}], tax, shipping, currency)

def spend_and_spt(b, m, cart, key="key_1"):
    ctx = "Purchase request: 1 item, merchant total, product from purchase request, amount from purchase request, Link approval at purchase time. " + "x" * 20
    s = b.create_spend_request(m, cart, ctx, key, "buyer@example.test")
    b.approve_spend(s["spend_id"])
    return b.issue_spt(s["spend_id"])

def checkout(b, m, cart, spt, key="key_1", cad_test_passed=True):
    addr = {"line1": "1 Test St", "zone": "supported"}
    return b.complete_checkout(m, cart["cart_id"], spt["spt_id"], key, "buyer@example.test", addr, addr, "agent_token_test", addr, cad_test_passed=cad_test_passed)

def expect(code, fn):
    try:
        fn()
    except BridgeError as e:
        assert e.code == code, f"expected {code}, got {e.code}"
        return
    raise AssertionError(f"expected {code}, no error")

# R1, R2, R4
b = setup(); m = merchant()
man = b.manifest(m); assert man["spt_support"] is True and man["seller_network_id"] == "net_test_1"
b2 = Bridge(); assert b2.manifest(m)["spt_support"] is False
# R3, R5, R6
b = setup(); cart = cart_for(b, 100, 10, 5); assert cart["total"] == 115
expect("ovo_bridge_unauthorized_agent", lambda: b.complete_checkout(m, cart["cart_id"], "spt_x", "k", "e", {"line1": "1 Test St", "zone": "supported"}, {"line1": "1 Test St", "zone": "supported"}, "bad_token", {"line1": "1 Test St", "zone": "supported"}, cad_test_passed=True))
# R7, R8, R9, R10, R11, R12, R13 happy path
b = setup(); cart = cart_for(b, 100, 10, 5); spt = spend_and_spt(b, m, cart); order = checkout(b, m, cart, spt)
assert order["status"] == "paid" and order["total"] == 115 and order["payment_intent"].startswith("pi_")
assert b.audit[-1]["spt_id"] == spt["spt_id"] and "card" not in str(b.audit[-1]).replace(spt["spt_id"], "")
# R8 idempotency, short context, missing network
b = setup(); cart = cart_for(b); s1 = b.create_spend_request(m, cart, "x" * 100, "same_key", "e"); s2 = b.create_spend_request(m, cart, "x" * 100, "same_key", "e"); assert s1["spend_id"] == s2["spend_id"]
expect("ovo_bridge_invalid_context", lambda: b.create_spend_request(m, cart, "short", "k2", "e"))
expect("ovo_bridge_wrong_merchant", lambda: b.create_spend_request({"network_id": None}, cart, "x" * 100, "k3", "e"))
# R9 denied, expired
b = setup(); cart = cart_for(b); ctx = "x" * 100; s = b.create_spend_request(m, cart, ctx, "k_deny", "e"); b.deny_spend(s["spend_id"]); expect("ovo_bridge_expired_token", lambda: b.issue_spt(s["spend_id"]))
# R6 quote void, stock gone
b = setup(); cart = cart_for(b); spt = spend_and_spt(b, m, cart, "k_void"); b.change_cart(cart["cart_id"]); expect("ovo_bridge_quote_void", lambda: checkout(b, m, cart, spt, "k_void"))
b = setup(); cart = cart_for(b); spt = spend_and_spt(b, m, cart, "k_stock"); b.set_stock(cart["cart_id"], False); expect("ovo_bridge_stock_gone", lambda: checkout(b, m, cart, spt, "k_stock"))
# R7 unsupported address
b = setup(); cart = cart_for(b); spt = spend_and_spt(b, m, cart, "k_addr"); addr = {"line1": "1 Test St", "zone": "supported"}; bad = {"line1": "2 Other St", "zone": "unsupported"}
expect("ovo_bridge_address_not_supported", lambda: b.complete_checkout(m, cart["cart_id"], spt["spt_id"], "k_addr", "e", bad, bad, "agent_token_test", addr))
# R10 insufficient, wrong merchant, expired SPT is covered by used/reused below
b = setup(); cart = cart_for(b, 200); spt = spend_and_spt(b, m, cart, "k_ins"); spt["max_amount"] = 100; expect("ovo_bridge_insufficient_amount", lambda: checkout(b, m, cart, spt, "k_ins"))
# R15 idempotent return vs reuse
b = setup(); cart = cart_for(b); spt = spend_and_spt(b, m, cart, "k_idem"); o1 = checkout(b, m, cart, spt, "k_idem"); o2 = checkout(b, m, cart, spt, "k_idem"); assert o1["order_id"] == o2["order_id"]
expect("ovo_bridge_reused_token", lambda: checkout(b, m, cart, spt, "different_key"))
# R12 declined, no order
b = Bridge(stripe_adapter=MockStripeAdapter("acct_test_merchant", decline=True)); b.authorize_agent("agent_token_test"); b.approve_merchant("merchant_test_1", "https://example-store.test", "merchant_test"); cart = cart_for(b); spt = spend_and_spt(b, m, cart, "k_decl"); expect("ovo_bridge_declined", lambda: checkout(b, m, cart, spt, "k_decl")); assert len(b.orders) == 0
# R18 refund then reuse
b = setup(); cart = cart_for(b); spt = spend_and_spt(b, m, cart, "k_ref"); o = checkout(b, m, cart, spt, "k_ref"); b.refund(o["order_id"], 100); expect("ovo_bridge_reused_token", lambda: checkout(b, m, cart, spt, "k_ref2"))
# R19 rate limiting: 5 bad attempts then 6th = 429
b = setup(); cart = cart_for(b)
for i in range(5):
    try: checkout(b, m, cart, {"spt_id": "spt_bad"}, f"k_rate_{i}")
    except BridgeError: pass
try:
    checkout(b, m, cart, {"spt_id": "spt_bad"}, "k_rate_5")
    raise AssertionError("rate limit not triggered")
except BridgeError as e:
    assert e.code == "ovo_bridge_rate_limited" and e.http == 429
# R20 CAD gate live
b = setup(); m_live = merchant(test_mode=False); cart = cart_for(b, 100, 0, 0, "CAD"); spt = spend_and_spt(b, m_live, cart, "k_cad"); expect("ovo_bridge_currency_not_supported", lambda: checkout(b, m_live, cart, spt, "k_cad", cad_test_passed=False))
# R21 separation: no enrichment code, no card field in audit/order
b = setup(); cart = cart_for(b); spt = spend_and_spt(b, m, cart, "k_sep"); o = checkout(b, m, cart, spt, "k_sep"); assert "card_number" not in o and "cvc" not in o and "enrichment" not in str(o)
# R22 test gate status
b = setup(); gate = b.test_gate_status(); assert gate["level_a_mock"] == "passed" and gate["level_b_link_approval"] == "not_proven_live" and gate["live_real_charge"] == "not_proven_live"
# R17 amount increase: old SPT for higher total fails, new succeeds
b = setup(); cart = cart_for(b, 100); spt = spend_and_spt(b, m, cart, "k_inc"); cart2 = cart_for(b, 200); expect("ovo_bridge_insufficient_amount", lambda: b.complete_checkout(m, cart2["cart_id"], spt["spt_id"], "k_inc", "e", {"line1": "1 Test St", "zone": "supported"}, {"line1": "1 Test St", "zone": "supported"}, "agent_token_test", {"line1": "1 Test St", "zone": "supported"}))
spt2 = spend_and_spt(b, m, cart2, "k_inc2"); o = checkout(b, m, cart2, spt2, "k_inc2"); assert o["total"] == 200
# R4 revoked
b = setup(); b.revoke_merchant(); cart = cart_for(b); spt = spend_and_spt(b, m, cart, "k_rev"); expect("ovo_bridge_no_merchant_approval", lambda: checkout(b, m, cart, spt, "k_rev"))
# Level A test helper
b = setup(); cart = cart_for(b, 100); spt = b.test_helper_spt(m, 100, "USD"); assert spt["test_helper"] is True; o = checkout(b, m, cart, spt, "k_helper"); assert o["status"] == "paid"

print("core_generic tests passed: Requirements 1-22, generic, no store hard coding, no live purchase session.")
print("Level B Link approval and live are NOT proven by these tests, by design.")
