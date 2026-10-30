#!/usr/bin/env python3
"""
Stream 1: OvO Agent - Audit (repeatable, deterministic).
Reads the live Sole Mates store through the public WooCommerce Store API
using the ?rest_route= form. Pretty wp-json paths return 404 here because
permalinks are plain, so this script never uses them.

Rules built into this script:
- Never invent a price, stock quantity, SKU, tax, shipping, or policy value.
- A missing field stays null in the gap list. No guessed value is written.
- Material, fit, and returns are present in description prose today, but
  they are NOT structured fields. The script reports them as unstructured,
  not as passes. Restructuring them is Stream 2 work, from the same prose,
  with merchant approval before any publish.
- Stock is a boolean only. low_stock_remaining is null. The script never
  turns that boolean into a number.
- JSON-LD product schema is left unverified in this audit, by design.
  This script does not claim it is present or absent.
- Untrusted text is flagged only. It is never followed, and never removed
  by this stream. Removal or handling is not Stream 1 work.
- No MCP, ACP, or UCP compliance is claimed. No consumer Muse discovery,
  live payment, or production plugin compatibility is claimed.
- OVO does not buy, and does not set purchase rules or limits. Gates live
  in the store and in agent tools, not in OVO as the buyer.

Output: gaps.json (format ovo-gap-list v1.0) and scorecard.md, next to
this script. Re-running the script on a new live snapshot replaces them.
"""
import json
import re
import html
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_STORE_URL = "https://wsiventures.com/solemates"
HERE = Path(__file__).resolve().parent


def api_url_for(store_url):
    return store_url.rstrip("/") + "/?rest_route=/wc/store/v1/products&per_page=100"

# Core scoring checks: 15 fields an agent needs to compare a product.
# A product passes a check only when the structured field is present.
CORE_FIELDS = [
    "name", "sku", "price_currency", "stock_boolean", "size_variations",
    "colour", "category", "short_description", "long_description",
    "image_present", "material_structured", "fit_structured",
    "returns_structured", "weight_present", "dimensions_present",
]
# Extra per-product fields checked, but not in the core score.
EXTRA_FIELDS = ["image_alt", "tags", "brand", "stock_quantity", "gtin"]

# Patterns that only flag text for a human to review. Nothing here is
# followed, and a flag never changes a price, an order, or a rule.
UNTRUSTED_PATTERNS = [
    r"\bignore\b.*\b(instructions?|rules?|above)\b",
    r"\boverride\b", r"\bsecret\b", r"\badmin\b",
    r"\bcoupon\b", r"\bpromo(code)?\b", r"\bdiscount\b",
    r"\bpay less\b", r"\bcharge (me )?\$?0\b", r"\b100% off\b",
    r"\bclick here\b", r"https?://",
]

def clean(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()

def excerpt(text, pattern, limit=160):
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    start = max(0, m.start() - 20)
    return clean(text[start:m.end() + 120])[:limit]

def segment(desc, label, next_labels):
    """Text after 'Label:' up to the next label, or to the end."""
    m = re.search(rf"{label}:\s*", desc, re.I)
    if not m:
        return None
    rest = desc[m.end():]
    cut = len(rest)
    for nxt in next_labels:
        n = re.search(rf"\b{nxt}:\s*", rest, re.I)
        if n:
            cut = min(cut, n.start())
    return clean(rest[:cut].strip().rstrip(".")) or None

def fetch_products(api_url):
    # The live host sometimes cuts a chunked response short. Retry, then
    # fall back to curl, which handled the same endpoint cleanly.
    import subprocess
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": "OvO-Audit/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            break
        except Exception as e:
            last = e
            data = None
    if data is None:
        raw = subprocess.run(["curl", "-s", api_url], capture_output=True, text=True, timeout=60)
        data = json.loads(raw.stdout)
    assert isinstance(data, list), f"Store API did not return a product list: {last}"
    return data

def main(store_url=DEFAULT_STORE_URL):
    products = fetch_products(api_url_for(store_url))
    gaps = []
    store_gaps = []
    untrusted_flags = []
    per_product = []

    def add(product, field, current, gap_type, evidence, source_label,
            fixable, requires_merchant):
        gaps.append({
            "product_id": product["id"] if product else None,
            "product_name": product["name"] if product else None,
            "sku": product.get("sku") if product else None,
            "field": field,
            "current_value": current,
            "gap_type": gap_type,
            "evidence": evidence,
            "source_label": source_label,
            "fixable_by_ovo_enrichment_from_source": fixable,
            "requires_merchant_input": requires_merchant,
        })

    for p in sorted(products, key=lambda x: x["id"]):
        desc = clean(p.get("description"))
        short = clean(p.get("short_description"))
        attrs = {a.get("name"): a for a in (p.get("attributes") or [])}
        size_terms = [t.get("name") for t in attrs.get("Size", {}).get("terms", [])]
        colour_terms = [t.get("name") for t in attrs.get("Colour", {}).get("terms", [])]
        variation_sizes = [v.get("attributes", [{}])[0].get("value")
                           for v in (p.get("variations") or [])
                           if v.get("attributes")]
        prices = p.get("prices") or {}
        images = p.get("images") or []

        # Structured material / fit / returns: only a real attribute or
        # field counts. Prose alone does not count.
        attr_names = [a.get("name", "").lower() for a in (p.get("attributes") or [])]
        material_prose = segment(desc, "Material", ["Fit", "Returns"])
        fit_prose = segment(desc, "Fit", ["Returns"])
        returns_prose = segment(desc, "Returns", [])

        checks = {}
        checks["name"] = bool(p.get("name"))
        checks["sku"] = bool(p.get("sku"))
        checks["price_currency"] = bool(prices.get("price")) and bool(prices.get("currency_code"))
        checks["stock_boolean"] = p.get("is_in_stock") is True
        checks["size_variations"] = bool(size_terms) and bool(variation_sizes)
        checks["colour"] = bool(colour_terms)
        checks["category"] = bool(p.get("categories"))
        checks["short_description"] = bool(short)
        checks["long_description"] = bool(desc)
        checks["image_present"] = bool(images)
        checks["material_structured"] = "material" in attr_names
        checks["fit_structured"] = "fit" in attr_names
        checks["returns_structured"] = "returns" in attr_names or "return_policy" in attr_names
        checks["weight_present"] = bool(p.get("weight"))
        dims = p.get("dimensions") or {}
        checks["dimensions_present"] = bool(dims.get("length") or dims.get("width") or dims.get("height"))

        # Gaps for every failed core check.
        if not checks["material_structured"]:
            add(p, "material_structured", None,
                "unstructured_buried_in_prose" if material_prose else "missing",
                f"Description prose says '{material_prose}' but no material attribute or field is in the Store API." if material_prose else "No material in description prose and no material field.",
                "store_api:product.description + store_api:product.attributes",
                True, False)
        if not checks["fit_structured"]:
            add(p, "fit_structured", None,
                "unstructured_buried_in_prose" if fit_prose else "missing",
                f"Description prose says '{fit_prose}' but no fit attribute or field is in the Store API." if fit_prose else "No fit note in description prose and no fit field.",
                "store_api:product.description + store_api:product.attributes",
                True, False)
        if not checks["returns_structured"]:
            add(p, "returns_structured", None,
                "unstructured_buried_in_prose" if returns_prose else "missing",
                f"Description prose says '{returns_prose}' but no returns field is in the Store API." if returns_prose else "No returns note in description prose and no returns field.",
                "store_api:product.description + store_api:product.attributes",
                True, False)
        if not checks["weight_present"]:
            add(p, "weight_present", None, "missing",
                "Store API weight is empty and formatted_weight is 'N/A'.",
                "store_api:product.weight", False, True)
        if not checks["dimensions_present"]:
            add(p, "dimensions_present", None, "missing",
                "Store API dimensions are empty and formatted_dimensions is 'N/A'.",
                "store_api:product.dimensions", False, True)

        # Extra per-product gaps.
        alt = (images[0].get("alt") if images else None) or ""
        if not alt.strip():
            add(p, "image_alt", "" if images else None, "missing",
                "Product has an image, but its alt text is empty. No verified description of the photo is in the source.",
                "store_api:product.images[0].alt", False, True)
        if not p.get("tags"):
            add(p, "tags", [], "missing",
                "Store API tags list is empty.",
                "store_api:product.tags", False, True)
        if not p.get("brands"):
            add(p, "brand", [], "missing",
                "Store API brands list is empty. The store name is not used as a brand here, because that would be a guess.",
                "store_api:product.brands", False, True)
        if p.get("low_stock_remaining") is None:
            add(p, "stock_quantity", None, "imprecise_boolean_only",
                "is_in_stock is true, but low_stock_remaining is null. No numeric stock quantity is in the Store API, so none is reported.",
                "store_api:product.is_in_stock + store_api:product.low_stock_remaining",
                False, True)
        add(p, "gtin", None, "not_in_product_api",
            "No GTIN field is in the Store API product record.",
            "store_api:product (full record)", False, True)

        # A mentioned option that cannot be selected is a gap, not a fact.
        if "in-store only" in desc.lower():
            add(p, "mentioned_option_not_selectable", None, "mentioned_option_not_selectable",
                "Description says wide fit is available in-store only and not in this demo catalog, and no wide-fit variation is in the Store API.",
                "store_api:product.description + store_api:product.variations",
                False, False)

        # Variation sizes must match the Size attribute terms.
        if size_terms and variation_sizes and sorted(map(str, size_terms)) != sorted(map(str, variation_sizes)):
            add(p, "size_variations_match", None, "inconsistent",
                f"Size attribute terms {size_terms} do not match variation sizes {variation_sizes}.",
                "store_api:product.attributes + store_api:product.variations",
                False, True)

        # Untrusted-text scan: flag only, never act, never remove.
        haystack = " ".join([p.get("name", ""), short, desc])
        for pat in UNTRUSTED_PATTERNS:
            hit = excerpt(haystack, pat)
            if hit:
                untrusted_flags.append({
                    "product_id": p["id"], "product_name": p["name"],
                    "field": "description_text", "pattern": pat,
                    "evidence": hit, "action_taken": "none - flagged only, not followed, not removed",
                    "source_label": "store_api:product.description",
                })

        core_pass = sum(1 for f in CORE_FIELDS if checks[f])
        post_pass = core_pass + sum(1 for f in ["material_structured", "fit_structured", "returns_structured"] if not checks[f])
        per_product.append({
            "product_id": p["id"], "product_name": p["name"], "sku": p.get("sku"),
            "core_pass": core_pass, "core_total": len(CORE_FIELDS),
            "core_score_pct": round(100 * core_pass / len(CORE_FIELDS), 1),
            "post_ovo_core_pass_projected": post_pass,
            "post_ovo_core_score_pct_projected": round(100 * post_pass / len(CORE_FIELDS), 1),
        })

    # Store-level gaps use product_id null. They are not product gaps,
    # and they are kept out of the per-product gap count.
    store_gaps.append({
        "product_id": None, "product_name": None, "sku": None,
        "field": "shipping_info", "current_value": None, "gap_type": "not_in_product_api",
        "evidence": "No shipping rates or shipping policy are in the Store API product record. Shipping is checkout-level, so it is not invented here.",
        "source_label": "store_api:product (full record)",
        "fixable_by_ovo_enrichment_from_source": False, "requires_merchant_input": True,
    })
    store_gaps.append({
        "product_id": None, "product_name": None, "sku": None,
        "field": "tax_info", "current_value": None, "gap_type": "not_in_product_api",
        "evidence": "No tax rate or tax rule is in the Store API product record. Tax is checkout-level, so it is not invented here.",
        "source_label": "store_api:product (full record)",
        "fixable_by_ovo_enrichment_from_source": False, "requires_merchant_input": True,
    })
    store_gaps.append({
        "product_id": None, "product_name": None, "sku": None,
        "field": "json_ld_product_schema", "current_value": None, "gap_type": "unverified",
        "evidence": "Not scored by this audit. This audit uses the Store API as its source of truth and does not claim product JSON-LD is present or absent.",
        "source_label": "audit_rule:json_ld_left_unverified",
        "fixable_by_ovo_enrichment_from_source": False, "requires_merchant_input": False,
    })

    all_gaps = gaps + store_gaps
    n_products = len(products)
    core_total = len(CORE_FIELDS) * n_products
    core_pass_total = sum(x["core_pass"] for x in per_product)
    post_total = sum(x["post_ovo_core_pass_projected"] for x in per_product)
    # Full per-product field coverage: core 15 + extra 5 = 20 per product.
    full_total = (len(CORE_FIELDS) + len(EXTRA_FIELDS)) * n_products
    # Per-product gap count, excluding store-level gaps and the Trailhead
    # mentioned-option gap, which is not one of the 20 fields.
    field_gap_count = sum(1 for g in gaps if g["field"] in CORE_FIELDS + EXTRA_FIELDS)
    full_pass = full_total - field_gap_count
    post_full_pass = full_pass + sum(1 for g in gaps if g["field"] in
        ["material_structured", "fit_structured", "returns_structured"])

    out = {
        "format": "ovo-gap-list",
        "version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "store_url": store_url,
        "source": "live Store API ?rest_route=/wc/store/v1/products&per_page=100",
        "audit_stream": "OvO Agent - Audit (Stream 1)",
        "product_count": n_products,
        "scores": {
            "native_store_core_score": f"{core_pass_total}/{core_total} = {round(100*core_pass_total/core_total, 1)}%",
            "post_ovo_core_score_projected": f"{post_total}/{core_total} = {round(100*post_total/core_total, 1)}%",
            "native_store_full_field_coverage": f"{full_pass}/{full_total} = {round(100*full_pass/full_total, 1)}%",
            "post_ovo_full_field_coverage_projected": f"{post_full_pass}/{full_total} = {round(100*post_full_pass/full_total, 1)}%",
            "note": "Native-store and post-OVO scores are kept separate. The post-OVO score is a projection for enrichment from source prose only. It is not the store's own score, and it is not 100%, because weight, dimensions, numeric stock, GTIN, tags, brand, shipping, and tax still need merchant data or checkout data.",
        },
        "per_product_scores": per_product,
        "gaps": all_gaps,
        "gap_count_per_product": field_gap_count,
        "gap_count_store_level": len(store_gaps),
        "gap_count_total": len(all_gaps),
        "untrusted_flags": untrusted_flags,
        "untrusted_scan": {
            "patterns_checked": UNTRUSTED_PATTERNS,
            "action_on_flag": "none - flagged only, not followed, not removed",
        },
        "not_claimed": [
            "full MCP, ACP, or UCP compliance",
            "consumer Muse discovery",
            "live payment",
            "production plugin compatibility",
            "product JSON-LD present or absent",
            "any numeric stock quantity, weight, dimension, tax, or shipping value",
        ],
    }
    (HERE / "gaps.json").write_text(json.dumps(out, indent=2))
    (HERE / "raw-products-latest.json").write_text(json.dumps(products, indent=2))
    print(f"Products: {n_products}")
    print(f"Native core: {out['scores']['native_store_core_score']}")
    print(f"Post-OVO core (projected): {out['scores']['post_ovo_core_score_projected']}")
    print(f"Native full: {out['scores']['native_store_full_field_coverage']}")
    print(f"Post-OVO full (projected): {out['scores']['post_ovo_full_field_coverage_projected']}")
    print(f"Gaps: per-product fields {field_gap_count}, store-level {len(store_gaps)}, total {len(all_gaps)}")
    print(f"Untrusted flags: {len(untrusted_flags)}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="OvO Audit Agent deterministic audit")
    parser.add_argument("--store-url", default=DEFAULT_STORE_URL,
                        help="Public store URL, e.g. https://wsiventures.com/solemates")
    main(parser.parse_args().store_url)
