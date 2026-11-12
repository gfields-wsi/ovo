"""OvO Payment Bridge — full programmatic implementation, test mode only.

No browser step. No card data. No live Stripe call in this module.
Stripe charging is through an injected charger interface; the default
test charger records a PaymentIntent and can be set to decline.
Production use must replace MockCharger with a server-side Stripe
PaymentIntent call using payment_method_data[shared_payment_granted_token],
confirm=true, on the merchant's own Stripe account, with a key supplied
via environment, never stored in this code.

Covers Requirements 1-22 in PAYMENT-BRIDGE-REQUIREMENTS-2026-11-02.md.
"""
import time, uuid

CODES = {
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
    "rate_limited": "ovo_bridge_rate_limited",
}

class BridgeError(Exception):
    def __init__(self, key, http=400):
        self.key = key
        self.code = CODES[key]
        self.http = http
        super().__init__(self.code)

class MockCharger:
    """Test charger. account is the merchant Stripe account, not OvO."""
    def __init__(self, account="acct_merchant_test", decline=False):
        self.account = account
        self.decline = decline
        self.charges = []
    def charge(self, amount, currency, spt_id):
        if self.decline:
            raise BridgeError("declined")
        pi = {"id": "pi_" + uuid.uuid4().hex[:12], "amount": amount, "currency": currency,
              "payment_method_data": {"shared_payment_granted_token": spt_id},
              "account": self.account, "status": "succeeded"}
        self.charges.append(pi)
        return pi

class Bridge:
    def __init__(self, network_id="net_test_1", currencies=("USD", "CAD"),
                 merchant_stripe_account="acct_merchant_test", cad_test_passed=False,
                 enrichment_active=True, test_mode=True):
        self.network_id = network_id
        self.currencies = list(currencies)
        self.merchant_stripe_account = merchant_stripe_account
        self.cad_test_passed = cad_test_passed
        self.enrichment_active = enrichment_active
        self.test_mode = test_mode
        self.merchant_approval = None  # Req 4, separate from enrichment
        self.agent_tokens = set()  # valid payment_methods.agentic tokens, test only
        self.carts = {}
        self.quotes = {}
        self.spend_requests = {}  # by idempotency key
        self.spts = {}
        self.orders = {}
        self.audit = []
        self.attempts = {}  # cart_id -> [timestamps]
        self.charger = MockCharger(account=merchant_stripe_account)
        self.now = 1700000000

    # Req 1, 2, 4: manifest
    def manifest(self):
        spt_support = bool(self.network_id and self.merchant_approval and not self.merchant_approval.get("revoked"))
        return {"seller_network_id": self.network_id if spt_support else None,
                "payment_endpoint": "/ovo-bridge/v1/checkout/complete",
                "accepted_currencies": self.currencies, "spt_support": spt_support, "version": "0.1.0-test"}
    def approve_merchant(self, merchant_id, store_id, approver):
        self.merchant_approval = {"merchant_id": merchant_id, "store_id": store_id,
            "bridge_version": "0.1.0-test", "approval_date": self.now, "approver": approver, "revoked": False}
        return self.merchant_approval
    def revoke_merchant(self):
        if self.merchant_approval: self.merchant_approval["revoked"] = True
    def authorize_agent(self, token):
        self.agent_tokens.add(token)

    # Req 5, 6: cart + quote, expiry order quote < spt < spend request
    def create_cart(self, product_id, variation_id, quantity, unit_price, tax=0, shipping=0, currency="USD", stock=True):
        cid = "cart_" + uuid.uuid4().hex[:8]
        total = quantity * unit_price + tax + shipping
        self.carts[cid] = {"cart_id": cid, "product_id": product_id, "variation_id": variation_id,
            "quantity": quantity, "unit_price": unit_price, "tax": tax, "shipping": shipping,
            "currency": currency, "stock": stock, "changed": False}
        qid = "quote_" + uuid.uuid4().hex[:8]
        self.quotes[qid] = {"quote_id": qid, "cart_id": cid, "total": total, "currency": currency,
            "valid": True, "expires_at": self.now + 600}  # quote expires first
        return cid, qid, total
    def change_cart(self, cart_id):
        self.carts[cart_id]["changed"] = True
        for q in self.quotes.values():
            if q["cart_id"] == cart_id: q["valid"] = False
    def set_stock(self, cart_id, stock):
        self.carts[cart_id]["stock"] = stock

    # Req 8, 9: spend request, Link SPT path only
    def create_spend_request(self, amount, currency, network_id, context, idempotency_key, payment_method_id=None):
        if idempotency_key in self.spend_requests:
            return self.spend_requests[idempotency_key]
        if not network_id: raise ValueError("network_id is required")
        if network_id != self.network_id: raise BridgeError("wrong_merchant")
        if len(context or "") < 100: raise ValueError("context must be at least 100 characters")
        sr = {"id": "lsrq_" + uuid.uuid4().hex[:12], "status": "pending_approval",
              "amount": amount, "currency": currency, "network_id": network_id,
              "credential_type": "shared_payment_token", "created_at": self.now,
              "expires_at": self.now + 1800, "payment_method_id": payment_method_id}
        self.spend_requests[idempotency_key] = sr
        return sr
    def approve_spend(self, spend_request_id):
        for sr in self.spend_requests.values():
            if sr["id"] == spend_request_id:
                if self.now > sr["expires_at"]: sr["status"] = "expired"
                else: sr["status"] = "approved"
                return sr
        raise ValueError("spend request not found")
    def deny_spend(self, spend_request_id):
        for sr in self.spend_requests.values():
            if sr["id"] == spend_request_id: sr["status"] = "denied"; return sr
        raise ValueError("spend request not found")
    def issue_spt(self, spend_request_id):
        sr = next((s for s in self.spend_requests.values() if s["id"] == spend_request_id), None)
        if not sr or sr["status"] != "approved": raise BridgeError("expired_token")
        spt_id = "spt_" + uuid.uuid4().hex[:12]
        self.spts[spt_id] = {"id": spt_id, "max_amount": sr["amount"], "currency": sr["currency"],
            "network_id": sr["network_id"], "expires_at": self.now + 1200, "used": False}
        return self.spts[spt_id]
    def test_helper_spt(self, max_amount, currency, network_id):
        # Level A only: merchant redemption test, no Link approval.
        spt_id = "spt_" + uuid.uuid4().hex[:12]
        self.spts[spt_id] = {"id": spt_id, "max_amount": max_amount, "currency": currency,
            "network_id": network_id, "expires_at": self.now + 1200, "used": False, "test_helper": True}
        return self.spts[spt_id]

    # Req 19: rate limiting, 5 attempts per cart per hour, 6th = 429
    def _rate_check(self, cart_id):
        ts = [t for t in self.attempts.get(cart_id, []) if self.now - t < 3600]
        if len(ts) >= 5: raise BridgeError("rate_limited", http=429)
        ts.append(self.now); self.attempts[cart_id] = ts

    # Req 11-18, 20-22: programmatic checkout complete
    def complete_checkout(self, cart_id, quote_id, spt_id, idempotency_key, customer_email,
                          shipping_address, billing_address, agent_token, approved_shipping_address,
                          live=False):
        try:
            return self._complete(cart_id, quote_id, spt_id, idempotency_key, customer_email,
                shipping_address, billing_address, agent_token, approved_shipping_address, live)
        except BridgeError as e:
            self.audit.append({"cart_id": cart_id, "quote_id": quote_id, "spt_id": spt_id,
                "approval_status": "failed", "payment_intent_id": None, "order_id": None, "error_code": e.code})
            raise

    def _complete(self, cart_id, quote_id, spt_id, idempotency_key, customer_email,
                  shipping_address, billing_address, agent_token, approved_shipping_address, live):
        if not cart_id or not quote_id or not spt_id: raise ValueError("cart_id, quote_id and spt_id are required")
        if agent_token not in self.agent_tokens: raise BridgeError("unauthorized_agent")
        if not self.merchant_approval or self.merchant_approval.get("revoked"): raise BridgeError("no_merchant_approval")
        if not self.manifest()["spt_support"]: raise BridgeError("no_merchant_approval")
        cart = self.carts.get(cart_id); quote = self.quotes.get(quote_id)
        if not cart or not quote or quote["cart_id"] != cart_id: raise BridgeError("quote_void")
        self._rate_check(cart_id)
        # idempotency, Req 15: same SPT+key returns existing order, different key reuses -> fail
        for o in self.orders.values():
            if o["spt_id"] == spt_id:
                if o["idempotency_key"] == idempotency_key: return o
                raise BridgeError("reused_token")
        if live and cart["currency"] == "CAD" and not self.cad_test_passed:
            raise BridgeError("currency_not_supported")
        if self.now > quote["expires_at"] or not quote["valid"] or cart["changed"]: raise BridgeError("quote_void")
        if not cart["stock"]: raise BridgeError("stock_gone")
        if shipping_address != approved_shipping_address: raise BridgeError("address_not_supported")
        if shipping_address.get("zone") == "unsupported": raise BridgeError("address_not_supported")
        spt = self.spts.get(spt_id)
        if not spt: raise BridgeError("expired_token")
        if spt["used"]: raise BridgeError("reused_token")
        if spt["network_id"] != self.network_id: raise BridgeError("wrong_merchant")
        if spt["currency"] != cart["currency"]: raise BridgeError("currency_not_supported")
        if spt["max_amount"] < quote["total"]: raise BridgeError("insufficient_amount")
        if self.now > spt["expires_at"]: raise BridgeError("expired_token")
        # charge, Req 12: PaymentIntent form locked, merchant account only
        pi = self.charger.charge(quote["total"], cart["currency"], spt_id)
        assert pi["payment_method_data"]["shared_payment_granted_token"] == spt_id
        assert pi["account"] == self.merchant_stripe_account
        spt["used"] = True
        oid = "order_" + uuid.uuid4().hex[:8]
        order = {"order_id": oid, "cart_id": cart_id, "quote_id": quote_id, "spt_id": spt_id,
            "idempotency_key": idempotency_key, "product_id": cart["product_id"],
            "variation_id": cart["variation_id"], "quantity": cart["quantity"],
            "price": cart["unit_price"], "tax": cart["tax"], "shipping": cart["shipping"],
            "total": quote["total"], "currency": cart["currency"], "customer_email": customer_email,
            "status": "paid", "payment_intent_id": pi["id"]}
        self.orders[oid] = order
        self.audit.append({"cart_id": cart_id, "quote_id": quote_id, "spt_id": spt_id,
            "approval_status": "approved", "payment_intent_id": pi["id"], "order_id": oid, "error_code": None})
        return order

    def refund(self, order_id, amount):
        order = self.orders.get(order_id)
        if not order: raise ValueError("order not found")
        order["refund"] = amount
        self.audit.append({"cart_id": order["cart_id"], "quote_id": order["quote_id"], "spt_id": order["spt_id"],
            "approval_status": "refunded", "payment_intent_id": order["payment_intent_id"],
            "order_id": order_id, "error_code": None, "refund_amount": amount})
        return order
