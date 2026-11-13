#!/usr/bin/env python3
"""Link spend requests and merchant payment profiles, Phase 6.

A merchant payment profile holds one merchant's payment
identity: the merchant Stripe account id and the seller
network id (the Link profile id) derived from it. One profile
per merchant, stored per merchant, never shared across stores.
A profile for one store is refused on another store.

The seller network id is derived, not typed in by hand. In
test mode the derivation is a fixed, labelled test derivation
from the Stripe account id. The real derivation, from Stripe,
is not proven in this phase: no real Link endpoint is called
here, and the real adapter fails closed on every call until a
verified Link spend request route and Greg's approval for a
real Link test are both in place.

A Link spend request asks Link for a single-use payment token
for the exact merchant total. The agent sends that token, with
no card data, and the merchant creates the payment in its own
Stripe account. Money stays with the merchant. The merchant
stays the seller. OvO stores no card data.
"""
import hashlib
import secrets
import time
from datetime import datetime, timezone


def now_utc():
    """The current time in UTC, as an ISO string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class LinkNotProven(Exception):
    """Raised when a real Link call would be needed. The real
    Link route is not proven in this phase, so the call fails
    closed instead of guessing an endpoint."""


def derive_profile_id(stripe_account_id, test_mode=True):
    """Derive the seller network id from a merchant Stripe
    account id. Test mode only: the id is labelled test and
    comes from a hash of the account id, so the same account
    always gives the same test profile id. Real mode raises:
    the real derivation from Stripe is not proven."""
    if not stripe_account_id or not isinstance(stripe_account_id, str):
        raise ValueError("Stripe account id is required")
    if not stripe_account_id.startswith("acct_"):
        raise ValueError("Stripe account id must start with acct_")
    if not test_mode:
        raise LinkNotProven(
            "real seller network id derivation is not proven: "
            "no verified Stripe lookup exists yet")
    digest = hashlib.sha256(
        stripe_account_id.encode("utf-8")).hexdigest()[:16]
    return "profile_test_" + digest


def save_profile(store, merchant_id, store_url, stripe_account_id,
                 test_mode=True, at=None):
    """Derive and store a merchant payment profile. One profile
    per merchant. A profile already stored for a different store
    address is refused, never overwritten."""
    if not merchant_id:
        raise ValueError("merchant id is required")
    if not store_url:
        raise ValueError("store address is required")
    existing = store.get_payment_profile(merchant_id)
    if existing and existing["store_url"] != store_url:
        raise ValueError(
            "payment profile is for a different store")
    if existing and existing["revoked"]:
        raise ValueError("payment profile is revoked")
    network_id = derive_profile_id(stripe_account_id, test_mode)
    derived_from = ("test-derivation from Stripe account id"
                    if test_mode else "stripe")
    store.save_payment_profile(
        merchant_id, store_url, stripe_account_id, network_id,
        derived_from, at or now_utc())
    return store.get_payment_profile(merchant_id)


def profile_for_store(store, merchant_id, store_url):
    """The payment profile for a merchant on one store. A profile
    for another store, or a revoked profile, is refused."""
    profile = store.get_payment_profile(merchant_id)
    if not profile:
        raise ValueError(f"no payment profile: {merchant_id}")
    if profile["store_url"] != store_url:
        raise ValueError("payment profile is for a different store")
    if profile["revoked"]:
        raise ValueError("payment profile is revoked")
    return profile


class MockLinkAdapter:
    """Test Link adapter. No real Link call. A spend request is
    approved by a mock approval, and the token it issues is
    labelled mock. It proves the flow, not a real Link payment."""

    def __init__(self):
        self.requests = {}
        self.tokens = {}
        self.now = int(time.time())

    def create_spend_request(self, amount_cents, currency, network_id,
                             context, idempotency_key, merchant_id,
                             store_url):
        if idempotency_key in self.requests:
            return self.requests[idempotency_key]
        if amount_cents <= 0:
            raise ValueError("spend amount must be over zero")
        if currency not in ("USD", "CAD"):
            raise ValueError("currency must be USD or CAD")
        if not network_id:
            raise ValueError("seller network id is required")
        if not context or len(context) < 100:
            raise ValueError("context must be at least 100 characters")
        if not idempotency_key:
            raise ValueError("idempotency key is required")
        request = {
            "id": "lsrq_" + secrets.token_hex(6),
            "status": "pending_approval",
            "amount_cents": amount_cents,
            "currency": currency,
            "network_id": network_id,
            "credential_type": "shared_payment_token",
            "merchant_id": merchant_id,
            "store_url": store_url,
            "created_at": self.now,
            "expires_at": self.now + 1800,
            "mock_link": True,
            "test_mode": True,
        }
        self.requests[idempotency_key] = request
        return request

    def approve_spend_request(self, request_id):
        for request in self.requests.values():
            if request["id"] == request_id:
                if self.now > request["expires_at"]:
                    request["status"] = "expired"
                else:
                    request["status"] = "approved"
                return request
        raise ValueError("spend request not found")

    def deny_spend_request(self, request_id):
        for request in self.requests.values():
            if request["id"] == request_id:
                request["status"] = "denied"
                return request
        raise ValueError("spend request not found")

    def issue_token(self, request_id):
        request = next(
            (r for r in self.requests.values() if r["id"] == request_id),
            None)
        if not request or request["status"] != "approved":
            raise ValueError("spend request is not approved")
        token = {
            "id": "spt_" + secrets.token_hex(6),
            "max_amount_cents": request["amount_cents"],
            "currency": request["currency"],
            "network_id": request["network_id"],
            "merchant_id": request["merchant_id"],
            "store_url": request["store_url"],
            "expires_at": self.now + 1200,
            "used": False,
            "mock_link": True,
            "test_mode": True,
        }
        self.tokens[token["id"]] = token
        return token


class RealLinkAdapter:
    """Real Link adapter. Not proven in this phase. Every call
    fails closed. No Link endpoint is called, and no endpoint
    is guessed here. A real adapter needs a verified Link
    spend request route and Greg's approval for a real Link
    test before it can replace this class."""

    def create_spend_request(self, *args, **kwargs):
        raise LinkNotProven(
            "real Link spend request is not proven")

    def approve_spend_request(self, *args, **kwargs):
        raise LinkNotProven(
            "real Link spend request is not proven")

    def deny_spend_request(self, *args, **kwargs):
        raise LinkNotProven(
            "real Link spend request is not proven")

    def issue_token(self, *args, **kwargs):
        raise LinkNotProven(
            "real Link spend request is not proven")
