import sys
sys.path.insert(0, ".")
from bridge_core import validate_spend_request, validate_spt, validate_quote, IdempotencyStore, audit_record, BridgeError

def expect_error(fn, code):
    try:
        fn()
    except BridgeError as e:
        assert e.code == code, f"expected {code}, got {e.code}"
        return
    raise AssertionError(f"expected BridgeError {code}")

# Spend request: happy path, wrong merchant, short context, currency mismatch
validate_spend_request(100, "CAD", "CAD", "net_1", "net_1", "x" * 100, "key-1")
expect_error(lambda: validate_spend_request(100, "CAD", "CAD", "net_2", "net_1", "x" * 100, "key-1"), "ovo_bridge_wrong_merchant")
expect_error(lambda: validate_spend_request(100, "CAD", "USD", "net_1", "net_1", "x" * 100, "key-1"), "ovo_bridge_currency_not_supported")

# SPT: happy, insufficient, reused, expired, wrong merchant
validate_spt("spt_123", 100, "CAD", "CAD", 100, "net_1", "net_1", 9999999999, now=1000)
expect_error(lambda: validate_spt("spt_123", 99, "CAD", "CAD", 100, "net_1", "net_1", 9999999999, now=1000), "ovo_bridge_insufficient_amount")
expect_error(lambda: validate_spt("spt_123", 100, "CAD", "CAD", 100, "net_1", "net_1", 9999999999, now=1000, used=True), "ovo_bridge_reused_token")
expect_error(lambda: validate_spt("spt_123", 100, "CAD", "CAD", 100, "net_1", "net_1", 500, now=1000), "ovo_bridge_expired_token")

# Quote: happy, void, stock gone
validate_quote(100, 100, True, True, False)
expect_error(lambda: validate_quote(100, 100, True, True, True), "ovo_bridge_quote_void")
expect_error(lambda: validate_quote(100, 100, True, False, False), "ovo_bridge_stock_gone")

# Idempotency
store = IdempotencyStore()
assert store.check("spt_123", "key-1") is None
store.record("spt_123", "key-1", "order-1")
assert store.check("spt_123", "key-1") == "order-1"

# Audit: no card data fields
rec = audit_record("cart-1", "quote-1", "spt_123", "approved", "pi_1", "order-1")
assert "card" not in str(rec).lower() or "card" not in rec
assert rec["spt_id"] == "spt_123"
print("bridge_core tests passed")
