#!/usr/bin/env python3
"""Bridge attribution events, Phase 6.

The bridge records the link from session to cart to paid
order. The event carries the session id, the cart id, the
order id, the agent route, the human approval id, the subtotal
before tax and shipping, and the currency. The fee is not set
here: the OVO host sets it from the rate in force when the
order was paid, through Phase 4 billing. A test order carries
no fee, and a human order with no agent link carries no fee.

The event is signed with HMAC-SHA256 and a per-host signing
key. The key comes from the environment only, never from code
and never from a log. The host verifies the signature before
it records the event for billing. An unsigned or wrongly
signed event is refused.

No card data ever appears in an event. No buyer email is
needed in an event: the order id is the link back to the
merchant store, where the merchant already holds the buyer.
"""
import hashlib
import hmac
import json
import os
import urllib.request

REQUIRED_FIELDS = (
    "session_id", "cart_id", "order_id", "agent_route",
    "human_approval_id", "subtotal_cents", "currency",
    "store_url", "merchant_id", "test_mode", "paid_at_utc",
)


def build_attribution_event(order, agent_route, human_approval_id,
                            test_mode=False):
    """Build the attribution event for a paid bridge order.
    The order must carry the link: session id, cart id, and
    subtotal in cents before tax and shipping."""
    for field in ("session_id", "cart_id", "order_id",
                  "subtotal_cents", "currency", "store_url",
                  "merchant_id", "paid_at_utc"):
        if order.get(field) in (None, ""):
            raise ValueError(f"order is missing {field} for attribution")
    if order["subtotal_cents"] < 0:
        raise ValueError("subtotal cannot be negative")
    if not agent_route:
        raise ValueError("agent route is required")
    if not human_approval_id:
        raise ValueError("human approval id is required")
    return {
        "session_id": order["session_id"],
        "cart_id": order["cart_id"],
        "order_id": order["order_id"],
        "agent_route": agent_route,
        "human_approval_id": human_approval_id,
        "subtotal_cents": order["subtotal_cents"],
        "currency": order["currency"],
        "store_url": order["store_url"],
        "merchant_id": order["merchant_id"],
        "test_mode": bool(test_mode),
        "paid_at_utc": order["paid_at_utc"],
    }


def build_unlinked_event(order, test_mode=False):
    """Build the event for a paid order with no agent link, for
    example a human order through the bridge. It carries no
    session and no cart, so it can never be billed."""
    for field in ("order_id", "subtotal_cents", "currency",
                  "store_url", "merchant_id", "paid_at_utc"):
        if order.get(field) in (None, ""):
            raise ValueError(f"order is missing {field} for attribution")
    return {
        "session_id": None,
        "cart_id": None,
        "order_id": order["order_id"],
        "agent_route": "human",
        "human_approval_id": None,
        "subtotal_cents": order["subtotal_cents"],
        "currency": order["currency"],
        "store_url": order["store_url"],
        "merchant_id": order["merchant_id"],
        "test_mode": bool(test_mode),
        "paid_at_utc": order["paid_at_utc"],
    }


def _canonical(event):
    return json.dumps(event, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sign_event(event, signing_key):
    """Sign an event. Returns the hex signature. The key is
    never stored with the event."""
    if not signing_key:
        raise ValueError("attribution signing key is required")
    return hmac.new(signing_key.encode("utf-8"), _canonical(event),
                    hashlib.sha256).hexdigest()


def verify_event(event, signature, signing_key):
    """True only when the signature matches the event and the
    key. A wrong signature, a changed event, or a missing key
    is false."""
    if not signing_key or not signature:
        return False
    expected = sign_event(event, signing_key)
    return hmac.compare_digest(expected, signature)


def signing_key_from_env():
    """The attribution signing key, from the environment only.
    Raises when it is not set: an unsigned event must never be
    sent as if it were signed."""
    key = os.environ.get("OVO_ATTRIBUTION_SIGNING_KEY")
    if not key:
        raise ValueError(
            "OVO_ATTRIBUTION_SIGNING_KEY is not set. Set it in the"
            " host settings store. The key is never stored in code.")
    return key


def fetch_attribution_event(base_url, order_id, timeout=10):
    """Fetch a signed attribution event for an order from a
    store bridge endpoint. Returns the event dict and its
    signature. The caller must verify the signature."""
    url = base_url.rstrip("/") + "/ovo-bridge/v1/attribution/" + str(order_id)
    with urllib.request.urlopen(url, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["event"], body["signature"]
