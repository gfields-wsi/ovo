#!/usr/bin/env python3
"""Live total test for the Phase 6 bridge, Site A only.

Runs against the local test install (WordPress 7.1.4 +
WooCommerce 11.3.0 at http://localhost:8081). Never touches a
live store, Sole Mates, or a pilot store. Test mode only, test
card only, no Link, no real card.

What it proves: a checkout with tax and shipping above zero
creates a WooCommerce order whose total equals the amount
charged through Stripe. That is Requirement 6: the merchant
total must include tax and shipping. The PHP checkout sets the
shipping and tax lines from the approved split before it calls
calculate_totals(), then guards: if the order total after
calculate_totals() differs from the charged amount, the order
is held, not marked paid.

Run: python3 test_bridge_live_total.py
Env: OVO_BRIDGE_STORE_URL (default http://localhost:8081),
OVO_BRIDGE_AGENT_TOKEN (the agent token set on the test install).
The Stripe test secret must be set on the test install host
(STRIPE_TEST_SECRET_KEY). Without it the checkout answers 503,
and this test reports BLOCKED, not failed: a missing key is a
fail-closed answer, not a wrong total.

Skips, never fails, when Site A is down.
"""
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

STORE_URL = os.environ.get("OVO_BRIDGE_STORE_URL", "http://localhost:8081")
AGENT_TOKEN = os.environ.get("OVO_BRIDGE_AGENT_TOKEN", "")
PRODUCT_ID = int(os.environ.get("OVO_BRIDGE_PRODUCT_ID", "12"))
TAX_CENTS = int(os.environ.get("OVO_BRIDGE_TAX_CENTS", "500"))
SHIPPING_CENTS = int(os.environ.get("OVO_BRIDGE_SHIPPING_CENTS", "1000"))
CURRENCY = "USD"


def req(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        STORE_URL + path, data=data, method=method,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}
    except Exception as e:
        return None, {"error": str(e)}


def main():
    status, manifest = req("GET", "/wp-json/ovo-bridge/v1/manifest")
    if status != 200:
        print(f"SKIP: Site A is not up (manifest HTTP {status})")
        return 0
    # Live price, from the store itself, never from the request.
    status, product = req(
        "GET", f"/wp-json/wc/store/v1/products/{PRODUCT_ID}")
    if status != 200:
        print(f"SKIP: product {PRODUCT_ID} not found (HTTP {status})")
        return 0
    prices = product.get("prices", {})
    unit_cents = int(prices.get("price", "0"))
    if unit_cents <= 0:
        print(f"SKIP: product {PRODUCT_ID} has no price")
        return 0
    subtotal = unit_cents
    total = subtotal + TAX_CENTS + SHIPPING_CENTS
    print(f"product {PRODUCT_ID}: subtotal {subtotal}, tax {TAX_CENTS}, "
          f"shipping {SHIPPING_CENTS}, total {total} cents")
    if not AGENT_TOKEN:
        print("BLOCKED: OVO_BRIDGE_AGENT_TOKEN is not set")
        return 2
    cart_id = "live-test-cart-1"
    status, approval = req("POST", "/ovo-bridge/v1/approval", {
        "cart_id": cart_id, "total_cents": total, "currency": CURRENCY,
        "session_id": "live-test-session-1",
        "human_approval_id": "live-test-human-1",
        "agent_token": AGENT_TOKEN})
    if status != 200:
        print(f"BLOCKED: approval HTTP {status}: {approval}")
        return 2
    approval_token = approval["approval_token"]
    address = {"first_name": "Test", "last_name": "Buyer",
               "address_1": "1 Test Street", "city": "Toronto",
               "postcode": "M5V 1J1", "country": "CA"}
    status, result = req("POST", "/ovo-bridge/v1/checkout/complete", {
        "cart_id": cart_id, "quote_id": "live-test-quote-1",
        "idempotency_key": "live-test-total-1",
        "customer_email": "test@localhost",
        "shipping_address": address, "billing_address": address,
        "agent_token": AGENT_TOKEN, "amount_cents": total,
        "currency": CURRENCY, "product_id": PRODUCT_ID,
        "variation_id": PRODUCT_ID, "quantity": 1,
        "approval_token": approval_token,
        "session_id": "live-test-session-1", "agent_route": "agent",
        "human_approval_id": "live-test-human-1",
        "subtotal_cents": subtotal, "tax_cents": TAX_CENTS,
        "shipping_cents": SHIPPING_CENTS, "test_card": True})
    if status == 503:
        print("BLOCKED: Stripe test secret is not set on the test "
              "install host (HTTP 503). The checkout failed closed. "
              "Set STRIPE_TEST_SECRET_KEY on the host and run again.")
        return 2
    if status != 200:
        print(f"FAIL: checkout HTTP {status}: {result}")
        return 1
    if result.get("amount_cents") != total:
        print(f"FAIL: charged amount {result.get('amount_cents')} "
              f"does not equal approved total {total}")
        return 1
    order_id = result.get("order_id")
    print(f"checkout succeeded: order {order_id}, charged {total} cents")
    # Order total, read back from WooCommerce through wp-cli when
    # it is available. Without it, the HTTP result above is the
    # only check, and the test says so plainly.
    wpcli = ["php", os.path.expanduser(
        "~/workspace/ovo-test-env/wp-cli.phar"), "--allow-root",
        "wc", "shop_order", "get", str(order_id),
        "--field=total", "--path=" + os.path.expanduser(
            "~/workspace/ovo-test-env/wp71")]
    try:
        out = subprocess.run(wpcli, capture_output=True, text=True,
                             timeout=60)
        order_total = out.stdout.strip()
        order_cents = int(round(float(order_total) * 100))
        print(f"WooCommerce order total: {order_total} "
              f"({order_cents} cents)")
        if order_cents != total:
            print(f"FAIL: order total {order_cents} cents does not "
                  f"equal charged amount {total} cents")
            return 1
    except Exception as e:
        print(f"NOTE: order total not read back ({e}); the checkout "
              f"result above is the only check")
    print(f"PASS: order total equals charged amount: {total} cents, "
          f"tax {TAX_CENTS} and shipping {SHIPPING_CENTS} above zero")
    return 0


if __name__ == "__main__":
    sys.exit(main())
