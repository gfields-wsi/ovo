"""OvO Payment Bridge core logic, test mode only, programmatic only.

No card data. No Stripe network call here. Stripe charging is a separate
step, gated on a secret key supplied via environment, and is not in this
module. This module implements the pure, testable guards from
PAYMENT-BRIDGE-REQUIREMENTS-2026-11-02.md: quote lock, SPT limits,
idempotency, failure codes, expiry order, and audit record shape.
"""
import time

ERRORS = {
    "wrong_merchant": "ovo_bridge_wrong_merchant",
    "unauthorized_agent": "ovo_bridge_unauthorized_agent",
    "no_merchant_approval": "ovo_bridge_no_merchant_approval",
    "quote_void": "ovo_bridge_quote_void",
    "expired_token": "ovo_bridge_expired_token",
    "reused_token": "ovo_bridge_reused_token",
    "insufficient_amount": "ovo_bridge_insufficient_amount",
    "declined": "ovo_bridge_declined",
    "stock_gone": "ovo_bridge_stock_gone",
    "address_not_supported": "ovo_bridge_address_not_supported",
    "currency_not_supported": "ovo_bridge_currency_not_supported",
}

class BridgeError(Exception):
    def __init__(self, code_key):
        self.code = ERRORS[code_key]
        super().__init__(self.code)

def validate_context(context):
    if not context or len(context) < 100:
        raise ValueError("context must be at least 100 characters")

def validate_spend_request(amount, currency, order_currency, network_id, manifest_network_id, context, idempotency_key):
    validate_context(context)
    if not network_id:
        raise ValueError("network_id is required")
    if network_id != manifest_network_id:
        raise BridgeError("wrong_merchant")
    if currency != order_currency:
        raise BridgeError("currency_not_supported")
    if not idempotency_key:
        raise ValueError("idempotency_key is required")
    return {"spend_request_id_prefix": "lsrq_", "amount": amount, "currency": currency, "network_id": network_id}

def validate_spt(spt_id, max_amount, currency, order_currency, order_total, seller_network_id, manifest_network_id, expires_at, now=None, used=False):
    now = now or int(time.time())
    if not spt_id or not spt_id.startswith("spt_"):
        raise ValueError("spt_id must start with spt_")
    if seller_network_id != manifest_network_id:
        raise BridgeError("wrong_merchant")
    if currency != order_currency:
        raise BridgeError("currency_not_supported")
    if max_amount < order_total:
        raise BridgeError("insufficient_amount")
    if used:
        raise BridgeError("reused_token")
    if expires_at and now > expires_at:
        raise BridgeError("expired_token")
    return True

def validate_quote(quote_total, order_total, quote_valid, stock_in_stock, cart_changed):
    if cart_changed or not quote_valid:
        raise BridgeError("quote_void")
    if not stock_in_stock:
        raise BridgeError("stock_gone")
    if quote_total != order_total:
        raise BridgeError("insufficient_amount")
    return True

class IdempotencyStore:
    """In-memory only, for tests. Production use must persist this."""
    def __init__(self):
        self.seen = {}
    def check(self, spt_id, idempotency_key):
        key = (spt_id, idempotency_key)
        if key in self.seen:
            return self.seen[key]
        return None
    def record(self, spt_id, idempotency_key, order_id):
        self.seen[(spt_id, idempotency_key)] = order_id

def audit_record(cart_id, quote_id, spt_id, approval_status, payment_intent_id=None, order_id=None, error_code=None):
    # SPT id is logged in full: an SPT is not PCI sensitive. No card data ever.
    return {
        "cart_id": cart_id,
        "quote_id": quote_id,
        "spt_id": spt_id,
        "approval_status": approval_status,
        "payment_intent_id": payment_intent_id,
        "order_id": order_id,
        "error_code": error_code,
    }
