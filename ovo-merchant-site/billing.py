#!/usr/bin/env python3
"""Billing for the OvO merchant site.

The rate is 1.5 percent of the order subtotal, before tax and
shipping, in store currency. The rate sits on a switch: the
default is 1.5 percent, and the launch edition is 1 percent
for the first 100 customers. Billing reads the rate in force
at the paid order. Old orders keep their old rate. Every rate
change is logged with who changed it and when.

The fee is earned at a paid order. A later refund gives no
credit, like a payment processor fee. Billing runs each month
and lists paid orders only. A card sign-in happens in the flow
as the go-live gate: without a card authorization on file, no
monthly bill runs.

Money is integer cents. Rates are decimals. Fees round half up
to the cent.
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

DEFAULT_RATE = Decimal("1.5")
LAUNCH_RATE = Decimal("1.0")
LAUNCH_CUSTOMERS = 100


def _parse_iso(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def now_utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fee_cents(subtotal_cents, rate_percent):
    """Fee in cents for a subtotal in cents at a rate in percent.
    Rounds half up to the cent."""
    if subtotal_cents < 0:
        raise ValueError("subtotal cannot be negative")
    rate = Decimal(str(rate_percent))
    fee = (Decimal(subtotal_cents) * rate / Decimal(100)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP)
    return int(fee)


def rate_in_force(store, merchant_id, at=None):
    """Rate in force for a merchant at a time. The launch edition
    (first 100 customers) starts at 1 percent; everyone else
    starts at 1.5 percent. A recorded rate change after that
    replaces it from its own time onward."""
    merchant = store.get_merchant(merchant_id)
    if not merchant:
        raise ValueError(f"unknown merchant: {merchant_id}")
    base = LAUNCH_RATE if merchant["customer_index"] <= LAUNCH_CUSTOMERS \
        else DEFAULT_RATE
    at_dt = _parse_iso(at) if at else None
    rate = base
    for change in store.rate_changes(merchant_id):
        changed_dt = _parse_iso(change["changed_at_utc"])
        if at_dt is None or (changed_dt is not None
                             and changed_dt <= at_dt):
            rate = Decimal(change["new_rate"])
    return rate


def set_rate(store, merchant_id, new_rate, changed_by, reason, at=None):
    """Change the rate. The old rate, the new rate, who changed
    it, and when are all logged. Returns the change record."""
    merchant = store.get_merchant(merchant_id)
    if not merchant:
        raise ValueError(f"unknown merchant: {merchant_id}")
    try:
        rate = Decimal(str(new_rate))
    except Exception:
        raise ValueError(f"rate is not a number: {new_rate}")
    if rate <= 0 or rate > 100:
        raise ValueError("rate must be over 0 and at most 100 percent")
    old = rate_in_force(store, merchant_id)
    at = at or now_utc()
    store.record_rate_change(merchant_id, str(old), str(rate), changed_by,
                             at, reason)
    return {"merchant_id": merchant_id, "old_rate": str(old),
            "new_rate": str(rate), "changed_by": changed_by,
            "changed_at_utc": at, "reason": reason}


def go_live_ok(store, merchant_id):
    """The go-live gate: a card authorization must be on file.
    Without it, billing does not run."""
    return store.latest_card_auth(merchant_id) is not None


def record_paid_order(store, merchant_id, order_id, subtotal_cents,
                      currency, store_url, session_id=None, cart_id=None,
                      actor="agent", paid_at=None, billable=True):
    """Record a paid order. The fee is fixed at the rate in force
    when the order was paid. A later rate change never changes
    this order's fee. When billable is false, the order carries
    a zero fee: a paid order with no agent link is recorded, but
    it is never billed. Attribution decides billable; billing
    only does the math."""
    if store.get_order(order_id):
        raise ValueError(f"order already recorded: {order_id}")
    if not store_url:
        raise ValueError("store address is required")
    if not isinstance(subtotal_cents, int) or subtotal_cents < 0:
        raise ValueError("subtotal must be a whole number of cents,"
                         " zero or more")
    if not currency or len(currency) != 3:
        raise ValueError("currency must be a three-letter code")
    paid_at = paid_at or now_utc()
    rate = rate_in_force(store, merchant_id, at=paid_at) if billable \
        else Decimal("0")
    order = {
        "order_id": order_id,
        "merchant_id": merchant_id,
        "store_url": store_url,
        "subtotal_cents": subtotal_cents,
        "currency": currency.upper(),
        "rate_percent": str(rate),
        "fee_cents": fee_cents(subtotal_cents, rate) if billable else 0,
        "session_id": session_id,
        "cart_id": cart_id,
        "actor": actor,
        "status": "paid",
        "paid_at_utc": paid_at,
        "refunded_at_utc": None,
    }
    store.save_order(order)
    return order


def record_refund(store, order_id, refunded_at=None):
    """Record a refund. The fee stays: a later refund gives no
    credit. Returns the order with its fee unchanged."""
    order = store.get_order(order_id)
    if not order:
        raise ValueError(f"unknown order: {order_id}")
    if order["status"] == "refunded":
        raise ValueError(f"order already refunded: {order_id}")
    fee_before = order["fee_cents"]
    refunded_at = refunded_at or now_utc()
    store.mark_refunded(order_id, refunded_at)
    order = store.get_order(order_id)
    assert order["fee_cents"] == fee_before, "refund changed the fee"
    return order


def monthly_bill(store, merchant_id, year, month):
    """The monthly bill. Lists paid orders only, each at the rate
    in force when it was paid. Refunded orders stay on the bill
    with their fee and a zero credit: the fee was earned when
    the order was paid. Blocked until the go-live gate passes."""
    if not go_live_ok(store, merchant_id):
        return {"merchant_id": merchant_id, "year": year, "month": month,
                "blocked": "no card authorization on file: the"
                           " go-live gate has not passed",
                "lines": [], "total_fee_cents": 0}
    orders = store.orders_in_month(merchant_id, year, month)
    lines = []
    total = 0
    for order in orders:
        lines.append({
            "order_id": order["order_id"],
            "subtotal_cents": order["subtotal_cents"],
            "currency": order["currency"],
            "rate_percent": order["rate_percent"],
            "fee_cents": order["fee_cents"],
            "status": order["status"],
            "refunded_at_utc": order.get("refunded_at_utc"),
            "refund_credit_cents": 0,
            "paid_at_utc": order["paid_at_utc"],
        })
        total += order["fee_cents"]
    return {"merchant_id": merchant_id, "year": year, "month": month,
            "blocked": None, "lines": lines,
            "total_fee_cents": total,
            "order_count": len(lines)}
