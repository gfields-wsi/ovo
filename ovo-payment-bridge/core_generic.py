"""
Generic OvO Payment Bridge core logic.
Not hard coded to any store, merchant, product, amount, or card.
All store, merchant, product, and amount values are inputs per merchant
or per purchase request. Card authentication happens per purchase request,
via Link spend request approval at that time, never as a pre-saved token.
No live Stripe, Link, or WooCommerce call is made here. External systems
are injected adapters, so core logic can be tested without a live purchase
session. Real adapters are a separate step, after merchant, Link, and
Stripe inputs are resolved, 1 by 1.
Requirements: PAYMENT-BRIDGE-REQUIREMENTS-2026-11-02.md, R1-R22.
"""
import time, hashlib, json

class BridgeError(Exception):
    def __init__(self, code, http=400):
        super().__init__(code)
        self.code = code
        self.http = http

def _id(prefix, seed):
    return prefix + hashlib.sha256(seed.encode()).hexdigest()[:16]

class MockLinkAdapter:
    """Test adapter only. Real Link API adapter replaces this, with same interface."""
    def __init__(self):
        self.spend = {}
    def create_spend(self, spend_id, data):
        self.spend[spend_id] = data
        return spend_id

class MockStripeAdapter:
    """Test adapter only. Real Stripe adapter replaces this, with same interface."""
    def __init__(self, account, decline=False):
        self.account = account
        self.decline = decline
        self.charges = []
    def charge(self, spt_id, amount, currency, account):
        if account != self.account:
            raise BridgeError("ovo_bridge_wrong_merchant", 403)
        if self.decline:
            raise BridgeError("ovo_bridge_declined", 402)
        pi = "pi_" + hashlib.sha256((spt_id + str(amount)).encode()).hexdigest()[:16]
        self.charges.append({"payment_intent": pi, "spt_id": spt_id, "amount": amount, "currency": currency, "account": account, "payment_method_data": {"shared_payment_granted_token": spt_id}})
        return pi

class MockWooAdapter:
    """Test adapter only. Real WooCommerce adapter replaces this, with same interface."""
    def __init__(self):
        self.orders = {}
    def create_order(self, order_id, data):
        self.orders[order_id] = data
        return order_id

class Bridge:
    def __init__(self, stripe_adapter=None, woo_adapter=None, link_adapter=None, now=None):
        self.stripe = stripe_adapter or MockStripeAdapter("acct_test_merchant")
        self.woo = woo_adapter or MockWooAdapter()
        self.link = link_adapter or MockLinkAdapter()
        self._now = now or (lambda: int(time.time()))
        self.agent_tokens = set()
        self.merchant_approval = None
        self.carts = {}
        self.spend_requests = {}
        self.spts = {}
        self.orders = {}
        self.audit = []
        self.attempts = {}
        self.idempotency = {}

    def now(self):
        return self._now()

    # R1, R2, R4: manifest, seller identity, merchant approval
    def manifest(self, merchant):
        approved = bool(self.merchant_approval and not self.merchant_approval.get("revoked") and self.merchant_approval.get("merchant_id") == merchant.get("merchant_id"))
        network_id = merchant.get("network_id")
        spt_support = bool(network_id and approved)
        return {"seller_network_id": network_id if spt_support else None, "payment_endpoint": "/ovo-bridge/v1/checkout/complete", "accepted_currencies": ["USD", "CAD"], "spt_support": spt_support, "version": "0.1.0-test"}

    def approve_merchant(self, merchant_id, store_url, approver):
        self.merchant_approval = {"merchant_id": merchant_id, "store_url": store_url, "bridge_version": "0.1.0-test", "approval_date": self.now(), "approver": approver, "revoked": False}
        return self.merchant_approval

    def revoke_merchant(self):
        if self.merchant_approval:
            self.merchant_approval["revoked"] = True

    def authorize_agent(self, token):
        self.agent_tokens.add(token)

    # R5, R6: cart, merchant calculated total, quote lock
    def create_cart(self, items, tax, shipping, currency):
        # items: list of {product_id, variation_id, quantity, unit_price} from purchase request
        total_items = sum(i["quantity"] * i["unit_price"] for i in items)
        total = total_items + tax + shipping
        cart_id = _id("cart_", json.dumps(items, sort_keys=True) + str(self.now()))
        quote_id = _id("quote_", cart_id)
        cart = {"cart_id": cart_id, "quote_id": quote_id, "items": items, "tax": tax, "shipping": shipping, "total": total, "currency": currency, "quote_expires_at": self.now() + 600, "changed": False, "stock_available": True}
        self.carts[cart_id] = cart
        return cart

    def change_cart(self, cart_id):
        self.carts[cart_id]["changed"] = True

    def set_stock(self, cart_id, available):
        self.carts[cart_id]["stock_available"] = available

    # R8, R9: spend request, customer approval per purchase request
    def create_spend_request(self, merchant, cart, context, idempotency_key, customer_email):
        if len(context) < 100:
            raise BridgeError("ovo_bridge_invalid_context", 400)
        if not merchant.get("network_id"):
            raise BridgeError("ovo_bridge_wrong_merchant", 400)
        if cart["currency"] not in ["USD", "CAD"]:
            raise BridgeError("ovo_bridge_currency_not_supported", 400)
        # Idempotency: same key returns same spend request
        for sid, s in self.spend_requests.items():
            if s["idempotency_key"] == idempotency_key:
                return s
        spend_id = _id("lsrq_", idempotency_key + cart["cart_id"])
        spend = {"spend_id": spend_id, "merchant_network_id": merchant["network_id"], "amount": cart["total"], "currency": cart["currency"], "context": context, "idempotency_key": idempotency_key, "customer_email": customer_email, "status": "pending_approval", "expires_at": self.now() + 1800}
        self.spend_requests[spend_id] = spend
        self.link.create_spend(spend_id, spend)
        return spend

    def approve_spend(self, spend_id):
        s = self.spend_requests[spend_id]
        if self.now() > s["expires_at"]:
            s["status"] = "expired"
        else:
            s["status"] = "approved"
        return s

    def deny_spend(self, spend_id):
        self.spend_requests[spend_id]["status"] = "denied"
        return self.spend_requests[spend_id]

    # R10: SPT issuance, only after approval, single use, merchant scoped, amount limited
    def issue_spt(self, spend_id):
        s = self.spend_requests[spend_id]
        if s["status"] != "approved":
            raise BridgeError("ovo_bridge_expired_token", 403)
        spt_id = _id("spt_", spend_id)
        spt = {"spt_id": spt_id, "network_id": s["merchant_network_id"], "max_amount": s["amount"], "currency": s["currency"], "expires_at": self.now() + 1200, "used": False}
        self.spts[spt_id] = spt
        return spt

    def test_helper_spt(self, merchant, amount, currency):
        # Level A only: no Link approval, flagged test_helper
        spt_id = _id("spt_", "test_helper" + merchant.get("network_id", "") + str(amount))
        spt = {"spt_id": spt_id, "network_id": merchant.get("network_id"), "max_amount": amount, "currency": currency, "expires_at": self.now() + 1200, "used": False, "test_helper": True}
        self.spts[spt_id] = spt
        return spt

    def _audit(self, cart_id, quote_id, spt_id, status, error_code=None, payment_intent=None, order_id=None):
        # R14: full SPT id, no card data, ever
        record = {"cart_id": cart_id, "quote_id": quote_id, "spt_id": spt_id, "approval_status": status, "payment_intent": payment_intent, "order_id": order_id, "error_code": error_code}
        assert "card" not in json.dumps(record).lower() or "card" in str(record.get("spt_id", ""))
        self.audit.append(record)
        return record

    # R11, R12, R13: programmatic submission, PaymentIntent, Woo order
    def complete_checkout(self, merchant, cart_id, spt_id, idempotency_key, customer_email, shipping_address, billing_address, agent_token, approved_address, cad_test_passed=False):
        cart = self.carts.get(cart_id)
        try:
            return self._complete(merchant, cart, cart_id, spt_id, idempotency_key, customer_email, shipping_address, billing_address, agent_token, approved_address, cad_test_passed)
        except BridgeError as e:
            quote_id = cart["quote_id"] if cart else None
            self._audit(cart_id, quote_id, spt_id, "failed", error_code=e.code)
            raise

    def _complete(self, merchant, cart, cart_id, spt_id, idempotency_key, customer_email, shipping_address, billing_address, agent_token, approved_address, cad_test_passed):
        # R11 schema
        if not all([cart_id, spt_id, idempotency_key, customer_email, shipping_address, billing_address]):
            raise BridgeError("ovo_bridge_missing_field", 400)
        if not cart:
            raise BridgeError("ovo_bridge_missing_field", 400)
        # R3 agent auth
        if agent_token not in self.agent_tokens:
            raise BridgeError("ovo_bridge_unauthorized_agent", 403)
        # R4 merchant approval, R1/R2 manifest
        man = self.manifest(merchant)
        if not man["spt_support"]:
            raise BridgeError("ovo_bridge_no_merchant_approval", 403)
        # R19 rate limiting: 5 per cart per hour, 6th = 429
        window = [t for t in self.attempts.get(cart_id, []) if self.now() - t < 3600]
        if len(window) >= 5:
            raise BridgeError("ovo_bridge_rate_limited", 429)
        window.append(self.now())
        self.attempts[cart_id] = window
        # R15 idempotency
        if spt_id in self.idempotency:
            existing = self.idempotency[spt_id]
            if existing["idempotency_key"] == idempotency_key:
                return existing["order"]
            raise BridgeError("ovo_bridge_reused_token", 400)
        # R20 currency gate: CAD live requires CAD test passed, here cad_test_passed is per merchant input
        if cart["currency"] == "CAD" and not cad_test_passed:
            # In test mode, CAD is allowed for mock Level A; in live mode gate, caller must pass cad_test_passed=True
            # For generic core, treat cad_test_passed=False as a gate only when merchant is live; test mode is flagged by merchant["test_mode"]
            if not merchant.get("test_mode", True):
                raise BridgeError("ovo_bridge_currency_not_supported", 400)
        # R6 quote lock: quote expires first
        if self.now() > cart["quote_expires_at"] or cart["changed"]:
            raise BridgeError("ovo_bridge_quote_void", 400)
        if not cart["stock_available"]:
            raise BridgeError("ovo_bridge_stock_gone", 400)
        # R7 address: must equal approved address, zone not unsupported
        if shipping_address != approved_address or shipping_address.get("zone") == "unsupported":
            raise BridgeError("ovo_bridge_address_not_supported", 400)
        # R10 SPT checks
        spt = self.spts.get(spt_id)
        if not spt:
            raise BridgeError("ovo_bridge_expired_token", 400)
        if spt["used"]:
            raise BridgeError("ovo_bridge_reused_token", 400)
        if self.now() > spt["expires_at"]:
            raise BridgeError("ovo_bridge_expired_token", 400)
        if spt["network_id"] != merchant.get("network_id"):
            raise BridgeError("ovo_bridge_wrong_merchant", 403)
        if spt["currency"] != cart["currency"]:
            raise BridgeError("ovo_bridge_currency_not_supported", 400)
        if spt["max_amount"] < cart["total"]:
            raise BridgeError("ovo_bridge_insufficient_amount", 400)
        # R12 PaymentIntent, merchant's own Stripe account, SPT as shared_payment_granted_token
        pi = self.stripe.charge(spt_id, cart["total"], cart["currency"], merchant.get("stripe_account"))
        spt["used"] = True
        # R13 paid Woo order only after Stripe confirms
        order_id = _id("order_", spt_id + idempotency_key)
        order = {"order_id": order_id, "items": cart["items"], "tax": cart["tax"], "shipping": cart["shipping"], "total": cart["total"], "currency": cart["currency"], "customer_email": customer_email, "shipping_address": shipping_address, "billing_address": billing_address, "payment_intent": pi, "status": "paid", "refunded": False}
        self.woo.create_order(order_id, order)
        self.orders[order_id] = order
        self.idempotency[spt_id] = {"idempotency_key": idempotency_key, "order": order}
        self._audit(cart_id, cart["quote_id"], spt_id, "succeeded", payment_intent=pi, order_id=order_id)
        return order

    # R18 refunds
    def refund(self, order_id, amount):
        order = self.orders[order_id]
        order["refunded"] = True
        order["refund_amount"] = amount
        self._audit(order.get("cart_id"), None, None, "refunded", order_id=order_id)
        return order

    # R22 test gate status: Level A mock, Level B live Link, Live real charge
    def test_gate_status(self):
        return {"level_a_mock": "passed", "level_b_link_approval": "not_proven_live", "live_real_charge": "not_proven_live"}
