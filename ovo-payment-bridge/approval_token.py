#!/usr/bin/env python3
"""Single-use approval tokens, Phase 6.

A human approval token binds one human approval to one cart
and one total. The token is issued when the buyer approves
the exact merchant total. It is single use: the first
checkout that presents it uses it up. Any change to the cart,
the price, or the stock voids every unused token for that
cart, so a changed cart can never be paid on an old approval.
An expired token is refused. A token for one cart is refused
on another cart, and a token for one total is refused on a
different total.

A declined payment uses the token up too: the buyer must
approve again before a retry. That is fail closed on purpose:
one approval covers one payment attempt, never a second one
after a failure.
"""
import secrets
import time

TOKEN_TTL_SECONDS = 600


class ApprovalTokenError(ValueError):
    """A token is unknown, used, expired, void, or for a
    different cart or total."""


class ApprovalTokenStore:
    """In-memory token store, for tests and for the bridge run.
    Production use must persist this, so a host restart cannot
    revive a used token."""

    def __init__(self):
        self.tokens = {}

    def _now(self):
        return int(time.time())

    def issue(self, cart_id, total_cents, currency, session_id,
              human_approval_id, ttl_seconds=TOKEN_TTL_SECONDS,
              now=None):
        """Issue a token for one cart and one total. Returns the
        token string. The human approval id names the approval
        this token carries."""
        if not cart_id:
            raise ValueError("cart id is required")
        if total_cents <= 0:
            raise ValueError("total must be over zero")
        if not currency or len(currency) != 3:
            raise ValueError("currency must be a three-letter code")
        if not human_approval_id:
            raise ValueError("human approval id is required")
        now = now if now is not None else self._now()
        token = "appr_" + secrets.token_hex(12)
        self.tokens[token] = {
            "token": token,
            "cart_id": cart_id,
            "total_cents": total_cents,
            "currency": currency.upper(),
            "session_id": session_id,
            "human_approval_id": human_approval_id,
            "used": False,
            "void": False,
            "issued_at": now,
            "expires_at": now + ttl_seconds,
        }
        return token

    def validate(self, token, cart_id, total_cents, currency,
                 now=None):
        """Check a token and use it up. Returns the token record.
        Any mismatch, use, expiry, or void is refused."""
        now = now if now is not None else self._now()
        record = self.tokens.get(token)
        if not record:
            raise ApprovalTokenError("unknown approval token")
        if record["used"]:
            raise ApprovalTokenError("approval token already used")
        if record["void"]:
            raise ApprovalTokenError("approval token void")
        if now > record["expires_at"]:
            raise ApprovalTokenError("approval token expired")
        if record["cart_id"] != cart_id:
            raise ApprovalTokenError(
                "approval token is for a different cart")
        if record["total_cents"] != total_cents:
            raise ApprovalTokenError(
                "approval token is for a different total")
        if record["currency"] != currency.upper():
            raise ApprovalTokenError(
                "approval token is for a different currency")
        record["used"] = True
        return record

    def void_for_cart(self, cart_id):
        """Void every unused token for a cart. Call this when
        the cart, its price, or its stock changes."""
        for record in self.tokens.values():
            if record["cart_id"] == cart_id and not record["used"]:
                record["void"] = True
