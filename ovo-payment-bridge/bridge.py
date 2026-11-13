"""OvO Payment Bridge — full programmatic implementation, test mode only.

Version 1.0.0-test. No browser step. No card data. No live Stripe
call in this module. Stripe charging is through an injected charger
interface; the default test charger records a PaymentIntent and can
be set to decline, or to need an extra card check (3D Secure),
which fails closed with no paid order. Production use must replace
MockCharger with a server-side Stripe PaymentIntent call using
payment_method_data[shared_payment_granted_token], confirm=true,
on the merchant's own Stripe account, with a key supplied via
environment, never stored in this code.

Phase 6 adds: a Link spend request through an adapter (mock in
test mode, real fails closed), a single-use human approval token
bound to cart and total, and the attribution link on every paid
order (session to cart to paid order, with subtotal before tax
and shipping). The fee itself is set by Phase 4 billing from
the rate in force, not by this module.

Covers Requirements 1-22 in PAYMENT-BRIDGE-REQUIREMENTS-2026-11-02.md.
"""
import time, uuid
from datetime import datetime, timezone

from approval_token import ApprovalTokenError, ApprovalTokenStore
from bridge_attribution import build_attribution_event, build_unlinked_event
from link import MockLinkAdapter

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
    "approval_token": "ovo_bridge_approval_token",
    "requires_action": "ovo_bridge_requires_action",
}

class BridgeError(Exception):
    def __init__(self, key, http=400):
        self.key = key
        self.code = CODES[key]
        self.http = http
        super().__init__(self.code)

class MockCharger:
    """Test charger. account is the merchant Stripe account, not OvO."""
    def __init__(self, account="acct_merchant_test", decline=False,
                 requires_action=False):
        self.account = account
        self.decline = decline
        self.requires_action = requires_action
        self.charges = []
    def charge(self, amount, currency, spt_id):
        if self.decline:
            raise BridgeError("declined")
        status = "requires_action" if self.requires_action else "succeeded"
        pi = {"id": "pi_" + uuid.uuid4().hex[:12], "amount": amount, "currency": currency,
              "payment_method_data": {"shared_payment_granted_token": spt_id},
              "account": self.account, "status": status}
        self.charges.append(pi)
        return pi

class Bridge:
    def __init__(self, network_id="net_test_1", currencies=("USD", "CAD"),
                 merchant_stripe_account="acct_merchant_test", cad_test_passed=False,
                 enrichment_active=True, test_mode=True,
                 merchant_id="merchant", store_url=None,
                 link_adapter=None, approval_tokens=None):
        self.network_id = network_id
        self.currencies = list(currencies)
        self.merchant_stripe_account = merchant_stripe_account
        self.cad_test_passed = cad_test_passed
        self.enrichment_active = enrichment_active
        self.test_mode = test_mode
        self.merchant_id = merchant_id
        self.store_url = store_url
        self.link_adapter = link_adapter or MockLinkAdapter()
        self.approval_tokens = approval_tokens or ApprovalTokenStore()
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

    def _paid_at_utc(self):
        return datetime.fromtimestamp(
            self.now, tz=timezone.utc).isoformat().replace("+00:00", "Z")

    # Req 1, 2, 4: manifest
    def manifest(self):
        spt_support = bool(self.network_id and self.merchant_approval and not self.merchant_approval.get("revoked"))
        return {"seller_network_id": self.network_id if spt_support else None,
                "payment_endpoint": "/ovo-bridge/v1/checkout/complete",
                "accepted_currencies": self.currencies, "spt_support": spt_support, "version": "1.0.0-test"}
    def approve_merchant(self, merchant_id, store_id, approver):
        self.merchant_approval = {"merchant_id": merchant_id, "store_id": store_id,
            "bridge_version": "1.0.0-test", "approval_date": self.now, "approver": approver, "revoked": False}
        return self.merchant_approval
    def revoke_merchant(self):
        if self.merchant_approval: self.merchant_approval["revoked"] = True
    def authorize_agent(self, token):
        self.agent_tokens.add(token)

    # Req 5, 6: cart + quote, expiry order quote < spt < spend request
    def create_cart(self, product_id, variation_id, quantity, unit_price, tax=0, shipping=0, currency="USD", stock=True,
                    session_id=None, agent_route="agent", human_approval_id=None):
        cid = "cart_" + uuid.uuid4().hex[:8]
        subtotal = quantity * unit_price
        total = subtotal + tax + shipping
        self.carts[cid] = {"cart_id": cid, "product_id": product_id, "variation_id": variation_id,
            "quantity": quantity, "unit_price": unit_price, "tax": tax, "shipping": shipping,
            "subtotal": subtotal, "currency": currency, "stock": stock, "changed": False,
            "session_id": session_id, "agent_route": agent_route,
            "human_approval_id": human_approval_id}
        qid = "quote_" + uuid.uuid4().hex[:8]
        self.quotes[qid] = {"quote_id": qid, "cart_id": cid, "total": total, "currency": currency,
            "valid": True, "expires_at": self.now + 600}  # quote expires first
        return cid, qid, total
    def change_cart(self, cart_id):
        self.carts[cart_id]["changed"] = True
        for q in self.quotes.values():
            if q["cart_id"] == cart_id: q["valid"] = False
        # A changed cart voids every unused human approval token for it.
        self.approval_tokens.void_for_cart(cart_id)
    def set_stock(self, cart_id, stock):
        self.carts[cart_id]["stock"] = stock
        if not stock:
            # Gone stock voids every unused human approval token for it.
            self.approval_tokens.void_for_cart(cart_id)

    # Phase 6: human approval token, single use, bound to cart and total.
    def issue_approval_token(self, cart_id, human_approval_id):
        cart = self.carts.get(cart_id)
        if not cart: raise ValueError("cart not found")
        quote = next((q for q in self.quotes.values() if q["cart_id"] == cart_id), None)
        if not quote: raise ValueError("quote not found")
        return self.approval_tokens.issue(
            cart_id, quote["total"], cart["currency"],
            cart["session_id"], human_approval_id, now=self.now)

    # Req 8, 9: spend request, Link SPT path only, through the adapter.
    # Amounts here are in whole dollars, as in the 0.5 bridge; the
    # adapter takes cents, so the bridge converts on the way in.
    def create_spend_request(self, amount, currency, network_id, context, idempotency_key, payment_method_id=None,
                             merchant_id=None, store_url=None):
        if idempotency_key in self.spend_requests:
            return self.spend_requests[idempotency_key]
        if not network_id: raise ValueError("network_id is required")
        if network_id != self.network_id: raise BridgeError("wrong_merchant")
        self.link_adapter.now = self.now  # adapter clock follows the bridge clock
        sr = self.link_adapter.create_spend_request(
            int(round(amount * 100)), currency, network_id, context,
            idempotency_key, merchant_id or self.merchant_id,
            store_url or self.store_url)
        sr["amount"] = amount
        sr["payment_method_id"] = payment_method_id
        sr["created_at"] = self.now
        sr["expires_at"] = self.now + 1800
        self.spend_requests[idempotency_key] = sr
        return sr
    def approve_spend(self, spend_request_id):
        self.link_adapter.now = self.now
        sr = self.link_adapter.approve_spend_request(spend_request_id)
        if self.now > sr["expires_at"]: sr["status"] = "expired"
        return sr
    def deny_spend(self, spend_request_id):
        self.link_adapter.now = self.now
        return self.link_adapter.deny_spend_request(spend_request_id)
    def issue_spt(self, spend_request_id):
        self.link_adapter.now = self.now
        try:
            token = self.link_adapter.issue_token(spend_request_id)
        except ValueError:
            # A denied, expired, or unknown spend request cannot
            # issue a token: fail closed, same code as 0.5.
            raise BridgeError("expired_token")
        spt = {"id": token["id"], "max_amount": token["max_amount_cents"] / 100,
               "max_amount_cents": token["max_amount_cents"],
               "currency": token["currency"], "network_id": token["network_id"],
               "expires_at": self.now + 1200, "used": False,
               "mock_link": token.get("mock_link", False)}
        self.spts[spt["id"]] = spt
        return spt
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
                          live=False, approval_token=None):
        try:
            return self._complete(cart_id, quote_id, spt_id, idempotency_key, customer_email,
                shipping_address, billing_address, agent_token, approved_shipping_address, live,
                approval_token)
        except BridgeError as e:
            self.audit.append({"cart_id": cart_id, "quote_id": quote_id, "spt_id": spt_id,
                "approval_status": "failed", "payment_intent_id": None, "order_id": None, "error_code": e.code})
            raise

    def _complete(self, cart_id, quote_id, spt_id, idempotency_key, customer_email,
                  shipping_address, billing_address, agent_token, approved_shipping_address, live,
                  approval_token=None):
        if not cart_id or not quote_id or not spt_id: raise ValueError("cart_id, quote_id and spt_id are required")
        if agent_token not in self.agent_tokens: raise BridgeError("unauthorized_agent")
        if not self.merchant_approval or self.merchant_approval.get("revoked"): raise BridgeError("no_merchant_approval")
        if not self.manifest()["spt_support"]: raise BridgeError("no_merchant_approval")
        cart = self.carts.get(cart_id); quote = self.quotes.get(quote_id)
        if not cart or not quote or quote["cart_id"] != cart_id: raise BridgeError("quote_void")
        # idempotency first, Req 15: a double submit with the same
        # SPT and key returns the existing order before the approval
        # token is checked, because the token was already used up
        # by the first submit. A different key reuses -> fail.
        for o in self.orders.values():
            if o["spt_id"] == spt_id:
                if o["idempotency_key"] == idempotency_key: return o
                raise BridgeError("reused_token")
        # Phase 6: a human approval token is required, single use,
        # bound to this cart and this total. A missing or bad token
        # fails closed with no paid order.
        if not approval_token: raise BridgeError("approval_token")
        try:
            self.approval_tokens.validate(
                approval_token, cart_id, quote["total"], cart["currency"],
                now=self.now)
        except ApprovalTokenError:
            raise BridgeError("approval_token")
        self._rate_check(cart_id)
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
        if pi["status"] == "requires_action":
            # An extra card check, such as 3D Secure, fails closed:
            # the token was presented, so it is used up, and no
            # paid order is created. The buyer must approve again.
            spt["used"] = True
            raise BridgeError("requires_action")
        if pi["status"] != "succeeded": raise BridgeError("declined")
        spt["used"] = True
        oid = "order_" + uuid.uuid4().hex[:8]
        order = {"order_id": oid, "cart_id": cart_id, "quote_id": quote_id, "spt_id": spt_id,
            "idempotency_key": idempotency_key, "product_id": cart["product_id"],
            "variation_id": cart["variation_id"], "quantity": cart["quantity"],
            "price": cart["unit_price"], "tax": cart["tax"], "shipping": cart["shipping"],
            "subtotal": cart["subtotal"], "total": quote["total"], "currency": cart["currency"],
            "customer_email": customer_email,
            "status": "paid", "payment_intent_id": pi["id"],
            "session_id": cart["session_id"], "agent_route": cart["agent_route"],
            "human_approval_id": cart["human_approval_id"],
            "merchant_id": self.merchant_id, "store_url": self.store_url,
            "test_mode": self.test_mode, "paid_at_utc": self._paid_at_utc()}
        self.orders[oid] = order
        self.audit.append({"cart_id": cart_id, "quote_id": quote_id, "spt_id": spt_id,
            "approval_status": "approved", "payment_intent_id": pi["id"], "order_id": oid, "error_code": None})
        return order

    def attribution_event_for(self, order_id):
        """The attribution event for a paid order: session to cart
        to paid order, with subtotal before tax and shipping. A
        linked order carries the event; an order with no session
        carries the unlinked event, which can never be billed.
        The fee is set by Phase 4 billing, not here."""
        order = self.orders.get(order_id)
        if not order: raise ValueError("order not found")
        if order.get("session_id"):
            return build_attribution_event(
                {"session_id": order["session_id"], "cart_id": order["cart_id"],
                 "order_id": order["order_id"],
                 "subtotal_cents": int(round(order["subtotal"] * 100)),
                 "currency": order["currency"], "store_url": order["store_url"],
                 "merchant_id": order["merchant_id"],
                 "paid_at_utc": order["paid_at_utc"]},
                order["agent_route"], order["human_approval_id"],
                test_mode=order["test_mode"])
        return build_unlinked_event(
            {"order_id": order["order_id"],
             "subtotal_cents": int(round(order["subtotal"] * 100)),
             "currency": order["currency"], "store_url": order["store_url"],
             "merchant_id": order["merchant_id"],
             "paid_at_utc": order["paid_at_utc"]},
            test_mode=order["test_mode"])

    def refund(self, order_id, amount):
        order = self.orders.get(order_id)
        if not order: raise ValueError("order not found")
        order["refund"] = amount
        self.audit.append({"cart_id": order["cart_id"], "quote_id": order["quote_id"], "spt_id": order["spt_id"],
            "approval_status": "refunded", "payment_intent_id": order["payment_intent_id"],
            "order_id": order_id, "error_code": None, "refund_amount": amount})
        return order
