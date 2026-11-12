"""Acceptance tests, one per criterion, Requirements 1-22. Test mode only, mocks only."""
import sys
sys.path.insert(0, ".")
from bridge import Bridge, BridgeError

CTX = "Purchasing Trailhead boots size 10 from the merchant store for a customer who asked for waterproof leather boots with returns. " * 2
ADDR = {"zone": "CA", "city": "Toronto"}

def fresh(**kw):
    b = Bridge(**kw)
    b.approve_merchant("m1", "mock-merchant", "merchant-admin")
    b.authorize_agent("agent-token-1")
    return b

def setup(b, total=100, currency="USD"):
    cid, qid, tot = b.create_cart(14, 29, 1, total, tax=0, shipping=0, currency=currency)
    sr = b.create_spend_request(total, currency, "net_test_1", CTX, "key-" + cid)
    b.approve_spend(sr["id"])
    spt = b.issue_spt(sr["id"])
    return cid, qid, spt

def err(fn, code):
    try: fn()
    except BridgeError as e: assert e.code == code, f"{e.code} != {code}"; return
    raise AssertionError(f"expected {code}")

# Req 1,2,4
b = fresh(); m = b.manifest(); assert m["spt_support"] and m["seller_network_id"] == "net_test_1" and "<" not in str(m)
b2 = Bridge(network_id=None); assert b2.manifest()["spt_support"] is False
# Req 3,4
b = fresh(); cid, qid, spt = setup(b)
err(lambda: b.complete_checkout(cid, qid, spt["id"], "k1", "a@b.com", ADDR, ADDR, "bad-token", ADDR, live=False), "ovo_bridge_unauthorized_agent")
b.revoke_merchant(); err(lambda: b.complete_checkout(cid, qid, spt["id"], "k1", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=False), "ovo_bridge_no_merchant_approval")
# Req 5,6 happy + void + stock
b = fresh(); cid, qid, spt = setup(b); o = b.complete_checkout(cid, qid, spt["id"], "k1", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=False)
assert o["total"] == 100 and o["status"] == "paid"
b = fresh(); cid, qid, spt = setup(b); b.change_cart(cid); err(lambda: b.complete_checkout(cid, qid, spt["id"], "k1", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=False), "ovo_bridge_quote_void")
b = fresh(); cid, qid, spt = setup(b); b.set_stock(cid, False); err(lambda: b.complete_checkout(cid, qid, spt["id"], "k1", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=False), "ovo_bridge_stock_gone")
# Req 7 address
b = fresh(); cid, qid, spt = setup(b); err(lambda: b.complete_checkout(cid, qid, spt["id"], "k1", "a@b.com", {"zone": "unsupported"}, ADDR, "agent-token-1", ADDR, live=False), "ovo_bridge_address_not_supported")
# Req 8 spend: idempotency, short context, missing network
b = fresh(); s1 = b.create_spend_request(100, "USD", "net_test_1", CTX, "dup"); s2 = b.create_spend_request(100, "USD", "net_test_1", CTX, "dup"); assert s1["id"] == s2["id"]
try: b.create_spend_request(100, "USD", "net_test_1", "short", "x"); raise AssertionError("short context")
except ValueError: pass
try: b.create_spend_request(100, "USD", None, CTX, "x2"); raise AssertionError("missing network")
except ValueError: pass
# Req 9 approval: denied, expired
b = fresh(); sr = b.create_spend_request(100, "USD", "net_test_1", CTX, "denied"); b.deny_spend(sr["id"])
try: b.issue_spt(sr["id"]); raise AssertionError("denied")
except BridgeError as e: assert e.code == "ovo_bridge_expired_token"
b = fresh(); sr = b.create_spend_request(100, "USD", "net_test_1", CTX, "exp"); b.now += 2000; b.approve_spend(sr["id"]); assert sr["status"] == "expired"
# Req 10 SPT limits, 16 insufficient, 17 amount increase
b = fresh(); cid, qid, spt = setup(b, total=100); spt["max_amount"] = 99
err(lambda: b.complete_checkout(cid, qid, spt["id"], "k1", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=False), "ovo_bridge_insufficient_amount")
# Req 11 schema missing
b = fresh(); cid, qid, spt = setup(b)
try: b.complete_checkout(None, qid, spt["id"], "k1", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=False); raise AssertionError("missing")
except ValueError: pass
# Req 12 charger account
b = fresh(); cid, qid, spt = setup(b); o = b.complete_checkout(cid, qid, spt["id"], "k1", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=False)
assert b.charger.charges[0]["account"] == "acct_merchant_test"
# Req 13 failed payment = no paid order
b = fresh(); b.charger.decline = True; cid, qid, spt = setup(b)
err(lambda: b.complete_checkout(cid, qid, spt["id"], "k1", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=False), "ovo_bridge_declined")
assert len(b.orders) == 0
# Req 14 audit
b = fresh(); cid, qid, spt = setup(b); o = b.complete_checkout(cid, qid, spt["id"], "k1", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=False)
a = b.audit[-1]; assert a["spt_id"] == spt["id"] and a["order_id"] == o["order_id"] and "card" not in a
# Req 15 idempotency / reuse
b = fresh(); cid, qid, spt = setup(b); o1 = b.complete_checkout(cid, qid, spt["id"], "k1", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=False)
o2 = b.complete_checkout(cid, qid, spt["id"], "k1", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=False); assert o1 == o2
err(lambda: b.complete_checkout(cid, qid, spt["id"], "k2", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=False), "ovo_bridge_reused_token")
# Req 18 refund
b.refund(o1["order_id"], 100); assert b.orders[o1["order_id"]]["refund"] == 100
err(lambda: b.complete_checkout(cid, qid, spt["id"], "k3", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=False), "ovo_bridge_reused_token")
# Req 19 rate limit: 5 attempts, 6th 429
b = fresh(); cid, qid, spt = setup(b)
for i in range(5):
    try: b.complete_checkout(cid, qid, "spt_bad", f"k{i}", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=False)
    except BridgeError: pass
try: b.complete_checkout(cid, qid, "spt_bad", "k5", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=False); raise AssertionError("rate")
except BridgeError as e: assert e.http == 429
# Req 20 currency gate
b = fresh(cad_test_passed=False); cid, qid, spt = setup(b, total=100, currency="CAD")
err(lambda: b.complete_checkout(cid, qid, spt["id"], "k1", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=True), "ovo_bridge_currency_not_supported")
b = fresh(cad_test_passed=True); cid, qid, spt = setup(b, total=100, currency="CAD"); o = b.complete_checkout(cid, qid, spt["id"], "k1", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=True); assert o["currency"] == "CAD"
# Req 21 separation
b = fresh(enrichment_active=False); assert b.manifest()["spt_support"] is True
# Req 22 Level A test helper
b = fresh(); cid, qid, tot = b.create_cart(14, 29, 1, 100, currency="USD"); spt = b.test_helper_spt(100, "USD", "net_test_1")
o = b.complete_checkout(cid, qid, spt["id"], "k1", "a@b.com", ADDR, ADDR, "agent-token-1", ADDR, live=False); assert o["status"] == "paid"
print("bridge_full tests passed: Requirements 1-22, Level A mock only. Level B Link approval and live are NOT proven.")
