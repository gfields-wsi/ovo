#!/usr/bin/env python3
"""Attribution: the link from agent session to cart to paid order.

When an agent reads product data, the plugin logs a read
session. When an agent builds a cart, the cart carries the
session id. When the order is paid, the order carries the
session id and the cart id. That link is the proof. No link
means no bill: a human order on a ready store, with no linked
agent session and no cart link, bills at zero.

The link is checked per store. A read session for one store
never links an order on another store.
"""
import secrets

import billing


def log_read_session(store, store_url, agent_id, product_ids, at=None):
    """Log an agent read session. Returns the session id. The
    agent id names the agent that read the data; the product ids
    name what it read."""
    if not store_url:
        raise ValueError("store address is required")
    if not agent_id:
        raise ValueError("agent id is required")
    if not isinstance(product_ids, list):
        raise ValueError("product ids must be a list")
    session_id = "read-" + secrets.token_hex(12)
    store.save_read_session(session_id, store_url, agent_id, product_ids,
                            at or billing.now_utc())
    return {"session_id": session_id, "store_url": store_url,
            "agent_id": agent_id, "product_ids": product_ids}


def create_cart(store, session_id, items, at=None):
    """Build a cart. The cart carries the session id of the read
    session it came from. A cart with no read session is refused."""
    read = store.get_read_session(session_id)
    if not read:
        raise ValueError(f"unknown read session: {session_id}")
    if not isinstance(items, list) or not items:
        raise ValueError("a cart needs at least one item")
    cart_id = "cart-" + secrets.token_hex(12)
    store.save_cart(cart_id, session_id, items, at or billing.now_utc())
    return {"cart_id": cart_id, "session_id": session_id, "items": items,
            "store_url": read["store_url"]}


def billable(store, order):
    """True only when the order carries a full link: a session id
    and a cart id, a read session that exists, and a cart that
    belongs to that session on the same store."""
    session_id = order.get("session_id")
    cart_id = order.get("cart_id")
    if not session_id or not cart_id:
        return False
    read = store.get_read_session(session_id)
    if not read:
        return False
    if read["store_url"] != order.get("store_url"):
        return False
    cart = store.get_cart(cart_id)
    if not cart or cart["session_id"] != session_id:
        return False
    return True


def fee_for(order):
    """The fee OvO bills for an order. A linked order bills its
    recorded fee. An unlinked order bills zero."""
    return order["fee_cents"] if order.get("fee_cents") else 0


def record_linked_order(store, merchant_id, order_id, subtotal_cents,
                        currency, store_url, cart_id, actor="agent",
                        paid_at=None):
    """Record a paid order that came through a cart. The cart
    supplies the session id, and the link is checked before the
    order is recorded. A cart from another store is refused."""
    cart = store.get_cart(cart_id)
    if not cart:
        raise ValueError(f"unknown cart: {cart_id}")
    read = store.get_read_session(cart["session_id"])
    if not read:
        raise ValueError("cart has no read session")
    if read["store_url"] != store_url:
        raise ValueError("cart is for a different store")
    return billing.record_paid_order(
        store, merchant_id, order_id, subtotal_cents, currency,
        store_url, session_id=cart["session_id"], cart_id=cart_id,
        actor=actor, paid_at=paid_at, billable=True)


def record_human_order(store, merchant_id, order_id, subtotal_cents,
                       currency, store_url, paid_at=None):
    """Record a paid human order: no agent session, no cart link.
    It is recorded with a zero fee. It is never billed."""
    return billing.record_paid_order(
        store, merchant_id, order_id, subtotal_cents, currency,
        store_url, session_id=None, cart_id=None, actor="human",
        paid_at=paid_at, billable=False)
