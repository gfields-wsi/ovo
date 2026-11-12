#!/bin/sh
# Verify OvO enrichment on the raw server response. No browser, no JavaScript.
# Usage: sh verify-live.sh STORE_URL [PRODUCT_SLUG]
# This script reports status. It does not claim success when a surface is absent.
set -u
BASE="${1:?Usage: sh verify-live.sh STORE_URL [PRODUCT_SLUG]}"
BASE="$(printf '%s' "$BASE" | sed 's:/$::')"
echo "Base: $BASE"
echo "--- Store API (store's own data) ---"
curl -s "$BASE/?rest_route=/wc/store/v1/products&per_page=100" -o /tmp/ovo-verify-products.json
python3 -c "import json; d=json.load(open('/tmp/ovo-verify-products.json')); print('products:', len(d)); print('all prices minor units:', sorted(set(p['prices']['price'] for p in d))); print('currencies:', sorted(set(p['prices']['currency_code'] for p in d))); print('in_stock flags:', sorted(set(str(p['is_in_stock']) for p in d))); print('low_stock_remaining values:', sorted(set(str(p['low_stock_remaining']) for p in d)))"
FIRST_SLUG="${2:-$(python3 -c "import json; d=json.load(open('/tmp/ovo-verify-products.json')); print(d[0]['slug'] if d else '')")}"
FIRST_ID="$(python3 -c "import json; d=json.load(open('/tmp/ovo-verify-products.json')); print(d[0]['id'] if d else '')")"
echo "--- Product page, raw HTML ---"
curl -s "$BASE/?product=$FIRST_SLUG" -o /tmp/ovo-verify-product.html
echo "has WooCommerce JSON-LD: $(grep -c 'application/ld+json' /tmp/ovo-verify-product.html || true)"
echo "has ovo-enrichment block: $(grep -c 'ovo-enrichment' /tmp/ovo-verify-product.html || true)"
echo "has ovo tool link: $(grep -c 'ovo/v1/products' /tmp/ovo-verify-product.html || true)"
echo "--- Checkout page, raw HTML (must have no ovo-enrichment) ---"
curl -s "$BASE/?checkout" -o /tmp/ovo-verify-checkout.html
echo "has ovo-enrichment block: $(grep -c 'ovo-enrichment' /tmp/ovo-verify-checkout.html || true)"
echo "--- OvO REST surfaces ---"
echo "manifest:"
curl -s -w "\nHTTP:%{http_code}\n" "$BASE/?rest_route=/ovo/v1/manifest" | head -c 800; echo
echo "products:"
curl -s -w "\nHTTP:%{http_code}\n" "$BASE/?rest_route=/ovo/v1/products" | head -c 800; echo
echo "product $FIRST_ID:"
curl -s -w "\nHTTP:%{http_code}\n" "$BASE/?rest_route=/ovo/v1/products/$FIRST_ID" | head -c 1200; echo
echo "--- Reading ---"
echo "If manifest returns 404 rest_no_route, the plugin is not installed yet. That is the expected state before install, not a pass."
echo "Enrichment is verified only when the product page raw HTML contains the ovo-enrichment script AND the ovo product endpoint returns the same fields."
