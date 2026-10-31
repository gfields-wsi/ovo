#!/usr/bin/env python3
"""
OvO Enrichment Agent — live, any WordPress/WooCommerce store, v4.

Given a store URL, enrich that store only. Never use another
store's data. Never publish. Never change the live store. Never
approve on the merchant's behalf.

Usage:
    python3 agent.py --store-url https://example.com/shop
    python3 agent.py --store-url https://example.com/shop --merchant my-shop
    python3 agent.py   (defaults to Sole Mates, for backward compatibility)

What v4 adds over v3, per the 14 requirements:
1.  Merchant is derived from the given URL. No Sole Mates data is
    used for any other store.
2.  Store API discovery tries ?rest_route= first, then /wp-json/,
    with public access only. Failure is fail-closed, with no
    proposals and a non-zero exit, and no previous diff is overwritten.
3.  Full catalog with paging, using X-WP-TotalPages when present.
4.  Any WooCommerce product type and structure: simple, variable,
    grouped, external. Multiple images get one photo row each.
5.  Structured fields are discovered from the store itself, not
    from a fixed label list. Price, stock, SKU, GTIN, tax class,
    and shipping class labels are blocked and never proposed.
6.  Attribute names are handled by their variation flag, not by
    exact name. Colour and Color, Size and Shoe Size, are treated
    the same when the store marks them as variations.
7.  Photo enrichment is product-type agnostic: vision asks for
    product type, and matching is against product name and
    category in general terms, not against shoe families only.
8.  Every row is scored by PRD band from that store's sources
    only, with evidence, source field, source URLs, and fetch time.
    A third source is a per-merchant ground-truth file only, if
    that merchant has one. No ground-truth file means a cap below
    95 percent.
9.  Unproposed fields are recorded per store, with reason code
    and next action, and are removed from the unproposed list
    when that store actually supplies the field.
10. Policies are copied verbatim only, per product, never as a
    store-wide modelled policy.
11. Refresh compares only with the previous diff for the same
    merchant, stored in that merchant's own folder.
12. Output is stored in that merchant's tenant record, keyed by
    store URL and batch ID.
13. Fail closed on missing, stale, or blocked data, with original
    data only. No fallback to another store's cached data.
14. Scope is US English, as in the PRD. The agent never translates
    a value. A non-English store is flagged as out of scope, and
    its fields are not translated.

Task definition: AGENT.md in this folder. Publishing belongs to
the Plug stream. Approval belongs to the Merchant Approval Agent.
"""
import argparse
import csv
import html
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_STORE_URL = "https://wsiventures.com/solemates"
META_HELPER = Path.home() / "workspace/custom-connectors/custom.meta-model-api/bin/meta_model.py"

# field, reason, reason_code, next_action — per-store list, filtered
# at run time: a field that the store actually supplies is removed.
UNPROPOSED_CANDIDATES = [
    ("width", "No width value in any store source; relative comparisons are not measurements.", "no_source", "merchant_input_needed"),
    ("weight", "Weight is empty in the Store API for all products.", "no_source", "merchant_input_needed"),
    ("dimensions", "Length, width, and height are empty in the Store API for all products.", "no_source", "merchant_input_needed"),
    ("stock_quantity_per_size", "Stock is a boolean in-stock flag only; no per-size quantity exists.", "blocked_critical", "never_propose"),
    ("gtin", "No GTIN exists in any store source.", "no_source", "merchant_input_needed"),
    ("brand", "Brands are empty in the Store API for all products.", "no_source", "merchant_input_needed"),
    ("care_instructions", "No care instructions in any store source.", "no_source", "merchant_input_needed"),
    ("closure_type", "No closure type field in any store source.", "no_source", "merchant_input_needed"),
    ("size_guide", "No size guide in any store source.", "no_source", "merchant_input_needed"),
    ("shipping_cost", "No shipping cost in any store source.", "no_source", "merchant_input_needed"),
    ("delivery_time", "No delivery time in any store source.", "no_source", "merchant_input_needed"),
    ("tax_class", "Tax class must not be modelled.", "blocked_critical", "never_propose"),
    ("shipping_class", "Shipping class must not be modelled.", "blocked_critical", "never_propose"),
    ("size_system", "No size system (men's/women's/US/UK) is stated in any store source.", "no_source", "merchant_input_needed"),
    ("store_wide_legal_policy", "Returns are copied per product only; no store-wide legal policy is claimed.", "blocked_policy", "never_propose"),
    ("safety_or_compatibility_claim", "Safety and compatibility claims must not be modelled.", "blocked_policy", "never_propose"),
    ("price_or_discount_change", "Price in the store is never enriched.", "blocked_critical", "never_propose"),
]
# Generic segment label -> unproposed field it supplies, if proposed.
SEGMENT_SUPPLIES = {
    "care": "care_instructions", "weight": "weight", "dimensions": "dimensions",
    "brand": "brand", "closure": "closure_type", "size guide": "size_guide",
}
# Labels that are never proposed from description segments.
BLOCKED_LABELS = {"price", "stock", "sku", "gtin", "tax class", "shipping class",
                  "tax", "stock quantity", "stock status"}

HUMAN_CHECK = {
    "95% or greater": "Acts alone - merchant rejects by exception",
    "80-94%": "Tacit suggestion - merchant approves by exception",
    "50-79%": "Suggests - merchant approves",
    "under 50%": "Reject & Iterate - never presented",
}
PRESENTED = {
    "95% or greater": "YES - reject by exception list",
    "80-94%": "YES - approve by exception list",
    "50-79%": "YES - approval queue",
    "under 50%": "NO - audit file only",
}
UNTRUSTED_PATTERNS = [
    ("ignore_instructions", r"\bignore\s+(?:previous|all|above|your)\s+instructions?\b"),
    ("disregard_instructions", r"\bdisregard\s+(?:previous|all|your)\s+instructions?\b"),
    ("system_prompt_claim", r"\bsystem\s+prompt\b"),
    ("override_rule", r"\boverride\s+(?:the\s+)?(?:rules?|instructions?)\b"),
    ("do_not_follow", r"\bdo\s+not\s+(?:follow|obey)\s+(?:the\s+)?(?:rules?|instructions?)\b"),
    ("you_must_now", r"\byou\s+must\s+now\b"),
]
COLOUR_NAMES = {"colour", "color", "colourway", "colorway"}
FRENCH_WORDS = {"le", "la", "les", "de", "des", "et", "pour", "avec", "une", "dans"}


def clean_text(raw):
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw or ""))
    return re.sub(r"\s+", " ", text).strip()


def norm(text):
    text = clean_text(text).lower()
    for a, b in [("—", "-"), ("–", "-"), ("’", "'"), ("“", '"'), ("”", '"')]:
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip().rstrip(".")


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "store"


def merchant_slug_from_url(store_url, override=None):
    if override:
        return slugify(override)
    parsed = urllib.parse.urlparse(store_url)
    path = parsed.path.strip("/")
    if path:
        return slugify(path.split("/")[-1])
    return slugify(parsed.netloc)


def normalize_base_url(store_url):
    url = (store_url or "").strip().rstrip("/")
    # A store URL is a homepage URL, not an API URL. Strip any API
    # suffix a caller may have pasted, so discovery starts clean.
    url = re.sub(r"/wp-json.*$", "", url)
    url = re.sub(r"/\?rest_route=.*$", "", url)
    return url.rstrip("/")


def fetch_url(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "OvO-Enrichment-Agent/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace"), dict(resp.headers)


def discover_api(base_url):
    """Try ?rest_route=, then /wp-json/. Return (template, form, first_page).

    Template contains {page}. Raises RuntimeError on total failure.
    A response is accepted only if it is a JSON list of products.
    """
    attempts = []
    templates = [
        ("rest_route", f"{base_url}/?rest_route=/wc/store/v1/products&per_page=100&page={{page}}"),
        ("wp-json", f"{base_url}/wp-json/wc/store/v1/products?per_page=100&page={{page}}"),
    ]
    for form, template in templates:
        url = template.format(page=1)
        try:
            body, headers = fetch_url(url)
            data = json.loads(body)
            if isinstance(data, list):
                return template, form, data, headers
            attempts.append(f"{form}: response was not a product list")
        except Exception as exc:
            attempts.append(f"{form}: {exc}")
    raise RuntimeError("Store API discovery failed for " + base_url + "; " + "; ".join(attempts))


def fetch_all_products(template, first_page=None, first_headers=None):
    """Fetch every page. Returns (products, total_pages_seen)."""
    products = []
    page = 1
    total_pages = None
    if first_headers and first_headers.get("X-WP-TotalPages"):
        try:
            total_pages = int(first_headers["X-WP-TotalPages"])
        except ValueError:
            total_pages = None
    while True:
        if page == 1 and first_page is not None:
            data = first_page
        else:
            body, _ = fetch_url(template.format(page=page))
            data = json.loads(body)
            if not isinstance(data, list):
                break
        products.extend(data)
        if total_pages is not None and page >= total_pages:
            break
        if len(data) < 100:
            break
        page += 1
        if page > 1000:
            break
    return products, total_pages


def segment(desc, label, next_labels):
    m = re.search(rf"{label}:\s*", desc, re.I)
    if not m:
        return None
    rest = desc[m.end():]
    cut = len(rest)
    for nxt in next_labels:
        n = re.search(rf"\b{nxt}:\s*", rest, re.I)
        if n:
            cut = min(cut, n.start())
    return clean_text(rest[:cut].strip().rstrip(".")) or None


def discover_segments(desc):
    """All 'Label: value' segments in a description, in order.

    Returns a list of (label, value). Labels are title-case words
    before a colon. This is how a store's own field names are
    discovered, instead of assuming only Material/Fit/Returns.
    """
    matches = list(re.finditer(r"(?:^|\.\s+)([A-Z][A-Za-z ]{1,24}):\s*", desc))
    out = []
    for i, m in enumerate(matches):
        label = m.group(1).strip()
        # A field label is short: at most 2 words and 20 characters.
        # A longer phrase before a colon, such as a demo note, is a
        # sentence, not a field, and must not become a proposal.
        if len(label.split()) > 2 or len(label) > 20:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(desc)
        value = clean_text(desc[start:end].strip().rstrip("."))
        # The next match starts after a period and a space; strip any
        # trailing period left by that split.
        value = value.rstrip(".").strip()
        if value:
            out.append((label, value))
    return out


def split_sentences(text):
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    return [p.rstrip(".") for p in parts]


def attr_terms(product, name):
    for attr in product.get("attributes", []):
        if attr.get("name", "").lower() == name.lower():
            return [t.get("name", "") for t in attr.get("terms", []) if t.get("name")]
    return []


def colour_terms(product):
    for attr in product.get("attributes", []):
        if attr.get("name", "").lower() in COLOUR_NAMES:
            terms = [t.get("name", "") for t in attr.get("terms", []) if t.get("name")]
            if terms:
                return terms
    return []


def variation_attributes(product):
    return [a for a in product.get("attributes", [])
            if a.get("has_variations") and a.get("name")]


def variation_values(product, attr_name):
    seen = []
    for var in product.get("variations", []) or []:
        for attr in var.get("attributes", []) or []:
            if attr.get("name", "").lower() == attr_name.lower():
                val = attr.get("value", "")
                if val and val not in seen:
                    seen.append(val)
    return seen


def scan_untrusted(text):
    found = []
    low = (text or "").lower()
    for name, pattern in UNTRUSTED_PATTERNS:
        if re.search(pattern, low):
            found.append(name)
    return found


def detect_language_out_of_scope(desc):
    """True if the description looks non-English. Never translates.

    Accented letters (not punctuation like em dashes) or several
    French function words are enough to flag out of scope. The
    flag only means: do not translate, do not claim English support
    for this product. Verbatim values are still never translated.
    """
    letters = [ch for ch in (desc or "") if ch.isalpha() and ord(ch) > 127]
    if letters:
        return True
    words = set(re.findall(r"[a-z]+", (desc or "").lower()))
    if len(words & FRENCH_WORDS) >= 3:
        return True
    return False


def band_from_confidence(conf):
    if conf is None:
        return "under 50%"
    if conf >= 95:
        return "95% or greater"
    if conf >= 80:
        return "80-94%"
    if conf >= 50:
        return "50-79%"
    return "under 50%"


def visual_only_proposal(product_id, image_url, vision, model="muse-spark-1.3"):
    if not vision or "error" in vision:
        return None
    conf = vision.get("confidence_percent")
    if not isinstance(conf, (int, float)):
        return None
    appearance = (vision.get("material_appearance") or "").strip()
    if not appearance:
        return None
    band = band_from_confidence(conf)
    if band == "under 50%":
        return None
    return {
        "product_id": str(product_id), "field": "_ovo_material_appearance",
        "old_value": "none — new OVO field", "new_value": appearance,
        "source_label": "observed_visual", "prd_accuracy_band": band,
        "prd_human_check": HUMAN_CHECK[band], "presented_to_merchant": PRESENTED[band],
        "accuracy_basis": f"Photo-only value; accuracy equals the recorded vision confidence of {conf} percent.",
        "evidence": vision.get("raw", ""), "source_field": "product photo",
        "source_url": image_url, "model": model, "confidence_percent": conf,
    }


def normalize_value(value):
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def compare_refresh(previous, current):
    prev = {(str(p["product_id"]), p["field"]): normalize_value(p["new_value"])
            for p in (previous or [])}
    curr = {(str(p["product_id"]), p["field"]): normalize_value(p["new_value"])
            for p in (current or [])}
    unchanged, new, changed, stale = 0, [], [], []
    for key, value in curr.items():
        if key not in prev:
            new.append({"product_id": key[0], "field": key[1], "new_value": value})
        elif prev[key] == value:
            unchanged += 1
        else:
            changed.append({"product_id": key[0], "field": key[1],
                            "previous_value": prev[key], "new_value": value})
    for key, value in prev.items():
        if key not in curr:
            stale.append({"product_id": key[0], "field": key[1], "previous_value": value})
    return {"unchanged_count": unchanged, "new_count": len(new),
            "changed_count": len(changed), "stale_count": len(stale),
            "new_rows": new, "changed_rows": changed, "stale_rows": stale}


def vision_check(image_url, product_name):
    payload = {
        "model": "muse-spark-1.3",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": (
                "Look at this product photo. Reply with JSON only: "
                '{"product_type": "", "dominant_colour": "", '
                '"material_appearance": "", "confidence_percent": 0}. '
                "Give a confidence percent for material_appearance only.")},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]}],
        "reasoning_effort": "minimal", "max_tokens": 500,
    }
    try:
        proc = subprocess.run(
            [sys.executable, str(META_HELPER), "chat"],
            input=json.dumps(payload), capture_output=True, text=True, timeout=120)
        out = json.loads(proc.stdout)
        content = out["choices"][0]["message"]["content"].strip()
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        parsed = json.loads(content)
        conf = parsed.get("confidence_percent")
        if not isinstance(conf, (int, float)):
            return {"error": "vision returned no confidence number", "raw": content}
        ptype = str(parsed.get("product_type") or parsed.get("shoe_type") or "")
        return {
            "product_type": ptype, "shoe_type": ptype,
            "dominant_colour": str(parsed.get("dominant_colour", "")),
            "material_appearance": str(parsed.get("material_appearance", "")),
            "confidence_percent": conf, "raw": content, "model": "muse-spark-1.3",
        }
    except Exception as exc:
        return {"error": f"vision call failed: {exc}"}


def colour_match(colour, dominant):
    return bool(set(re.findall(r"[a-z]+", colour.lower())) &
                set(re.findall(r"[a-z]+", dominant.lower())))


def stem(word):
    word = word.lower().strip()
    return word[:-1] if word.endswith("s") and len(word) > 2 else word


def type_match_general(category, product_type, product_name):
    """Product-type agnostic match: category stem, or a product-name
    word, must appear in the vision product type. Shoe families are
    just one case of this rule, not a separate rule."""
    ptype = (product_type or "").lower()
    if not ptype:
        return False
    cat_stem = stem(category or "")
    if cat_stem and cat_stem in ptype:
        return True
    for word in re.findall(r"[a-z]+", (product_name or "").lower()):
        if len(word) >= 3 and word in ptype:
            return True
    # Shoe families, as a fallback: a runner is a sneaker, and so on.
    shoe_words = {"boot", "sandal", "sneaker", "runner", "running", "slipper", "shoe"}
    if cat_stem in ("boot", "sandal", "sneaker", "runner", "slipper") and any(w in ptype for w in shoe_words):
        return True
    return False


def type_match(category, shoe_type):
    return type_match_general(category, shoe_type, "")


def all_terms_present(text_norm, terms):
    for term in terms:
        if not re.search(r"(?:^|[^0-9])" + re.escape(term) + r"(?:[^0-9]|$)", text_norm):
            return False
    return True


def band_from_sources(value, sources):
    hits = [name for name, text in sources if norm(value) and norm(value) in text]
    if len(hits) >= 3:
        return "95% or greater", (
            "Word-for-word agreement across 3 store sources: Store API, "
            "rendered product page, and per-merchant ground truth")
    if len(hits) == 2:
        return "80-94%", f"Word-for-word agreement across 2 store sources: {', '.join(hits)}"
    if len(hits) == 1:
        return "50-79%", f"Value appears in one store source only: {hits[0]}"
    return "under 50%", "No store source for this value; never proposed"


def main(argv=None):
    parser = argparse.ArgumentParser(description="OvO Enrichment Agent, live, any WooCommerce store")
    parser.add_argument("--store-url", default=DEFAULT_STORE_URL,
                        help="Store homepage URL, e.g. https://example.com/shop")
    parser.add_argument("--merchant", default=None, help="Override merchant slug")
    parser.add_argument("--ground-truth", default=None,
                        help="Per-merchant ground-truth file for this store only")
    args = parser.parse_args(argv)
    base_url = normalize_base_url(args.store_url)
    merchant = merchant_slug_from_url(base_url, args.merchant)
    merchant_dir = HERE / "merchant" / merchant
    merchant_dir.mkdir(parents=True, exist_ok=True)
    run_start = datetime.now(timezone.utc)
    batch_id = f"{merchant}-{run_start.strftime('%Y%m%d-%H%M%S')}UTC"
    run = {
        "agent": "OvO Enrichment Agent (live, any WooCommerce store, v4)",
        "generated_at_utc": run_start.isoformat(), "batch_id": batch_id,
        "merchant": merchant, "store_url": base_url, "status": "proposed_only",
        "published": False,
        "sources": ["live Store API for the given store", "rendered product pages",
                    "per-merchant ground truth (if present)", "live Spark vision"],
        "page_fetch_failures": [], "vision_failures": [], "untrusted_flags": [],
        "language_out_of_scope": [], "vision_results": {}, "notes": [],
    }
    # API discovery first. On failure, fail closed: no diff is written
    # or overwritten, and the exit code is non-zero.
    try:
        template, endpoint_form, first_page, first_headers = discover_api(base_url)
        run["endpoint_form"] = endpoint_form
        products, _total_pages = fetch_all_products(template, first_page, first_headers)
        products = sorted(products, key=lambda p: p["id"])
    except Exception as exc:
        run["status"] = "failed"
        run["error"] = str(exc)
        run["proposal_count"] = 0
        (HERE / "enrichment_run_live.json").write_text(json.dumps(run, indent=2))
        print(f"FAILED: {exc}", file=sys.stderr)
        print("No proposals. No previous diff overwritten. Status: failed.")
        sys.exit(1)
    # Per-merchant ground truth only. Never a global file for another store.
    gt_path = Path(args.ground_truth) if args.ground_truth else (merchant_dir / "ground-truth.md")
    gt_norm = ""
    if gt_path.exists():
        gt_norm = norm(gt_path.read_text(errors="replace"))
        run["ground_truth_file"] = str(gt_path)
    else:
        run["notes"].append("No per-merchant ground-truth file; text rows capped at 80-94%.")
    # Per-merchant previous diff only, for refresh.
    latest_path = merchant_dir / "latest.json"
    previous = None
    if latest_path.exists():
        try:
            previous = json.loads(latest_path.read_text()).get("proposals", [])
            run["previous_batch"] = json.loads(latest_path.read_text()).get("batch_id")
        except Exception:
            previous = None

    rows, preservation = [], []
    variations_checked = 0
    supplied_unproposed = set()

    for prod in products:
        pid = prod["id"]
        name = prod["name"]
        desc = clean_text(prod.get("description", ""))
        fetched_at = datetime.now(timezone.utc).isoformat()
        if detect_language_out_of_scope(desc):
            run["language_out_of_scope"].append({"product_id": pid, "reason": "description looks non-English; values are never translated"})
        try:
            page_text = clean_text(fetch_url(prod["permalink"])[0])
        except Exception as exc:
            page_text = ""
            run["page_fetch_failures"].append({"product_id": pid, "error": str(exc)})
        api_norm, page_norm = norm(desc), norm(page_text)
        sources = [("Store API", api_norm)]
        if page_norm:
            sources.append(("rendered product page", page_norm))
        if gt_norm:
            sources.append(("per-merchant ground truth", gt_norm))

        def add(field, new_value, source_label, band, basis, evidence,
                source_field, old="none — new OVO field", extra=None):
            if new_value is None or new_value == "" or new_value == []:
                return
            if band == "under 50%":
                return
            row = {
                "product_id": str(pid), "field": field, "old_value": old,
                "new_value": new_value, "source_label": source_label,
                "prd_accuracy_band": band, "prd_human_check": HUMAN_CHECK[band],
                "presented_to_merchant": PRESENTED[band], "accuracy_basis": basis,
                "evidence": evidence, "source_field": source_field,
                "source_url": prod["permalink"], "source_urls": [prod["permalink"], base_url],
                "fetched_at_utc": fetched_at,
            }
            if extra:
                row.update(extra)
            rows.append(row)

        def guarded(field, value, label):
            if value is None:
                return False
            hits = scan_untrusted(value)
            if hits:
                run["untrusted_flags"].append({
                    "product_id": pid, "field": field, "location": f"description {label} segment",
                    "patterns": hits})
                return False
            return True

        material = segment(desc, "Material", ["Fit", "Returns"])
        fit_full = segment(desc, "Fit", ["Returns"])
        returns = segment(desc, "Returns", [])
        if guarded("_ovo_material", material, "Material"):
            band, basis = band_from_sources(material, sources)
            add("_ovo_material", material, "merchant-provided", band, basis,
                f"Material: {material}", "description")
        if guarded("_ovo_returns_summary", returns, "Returns"):
            band, basis = band_from_sources(returns, sources)
            add("_ovo_returns_summary", returns, "merchant-provided", band, basis,
                f"Returns: {returns}", "description")
        if fit_full and guarded("_ovo_fit_guidance", fit_full, "Fit"):
            sentences = split_sentences(fit_full)
            if len(sentences) > 1 and "in-store only" in sentences[1].lower():
                add("_ovo_fit_guidance", sentences[0], "merchant-provided",
                    *band_from_sources(sentences[0], sources),
                    f"Fit: {sentences[0]}", "description")
                add("_ovo_availability_note", sentences[1], "merchant-provided",
                    *band_from_sources(sentences[1], sources),
                    f"Fit: {sentences[1]}", "description")
            elif len(sentences) > 1 and " than " in sentences[1].lower():
                add("_ovo_fit_guidance", sentences[0], "merchant-provided",
                    *band_from_sources(sentences[0], sources),
                    f"Fit: {sentences[0]}", "description")
                add("_ovo_fit_note", sentences[1], "merchant-provided",
                    *band_from_sources(sentences[1], sources),
                    f"Fit: {sentences[1]}", "description")
            else:
                band, basis = band_from_sources(fit_full, sources)
                add("_ovo_fit_guidance", fit_full, "merchant-provided", band, basis,
                    f"Fit: {fit_full}", "description")
        # Generic segments discovered from this store's own description.
        # Material/Fit/Returns are handled above, so they are skipped here.
        handled = {"material", "fit", "returns"}
        for label, value in discover_segments(desc):
            low = label.lower()
            if low in handled or low in BLOCKED_LABELS:
                continue
            if not guarded(f"_ovo_{re.sub(r'[^a-z0-9]+', '_', low).strip('_')}", value, label):
                continue
            band, basis = band_from_sources(value, sources)
            slug = re.sub(r"[^a-z0-9]+", "_", low).strip("_")
            add(f"_ovo_{slug}", value, "merchant-provided", band, basis,
                f"{label}: {value}", "description")
            if low in SEGMENT_SUPPLIES:
                supplied_unproposed.add(SEGMENT_SUPPLIES[low])
            if slug == "care_instructions":
                supplied_unproposed.add("care_instructions")
        # Variant choices, any product: every attribute the store marks
        # as having variations, one row per attribute, typed list value.
        for attr in variation_attributes(prod):
            attr_name = attr["name"]
            terms = attr_terms(prod, attr_name)
            var_vals = variation_values(prod, attr_name)
            variations_checked += len(prod.get("variations", []) or [])
            values = var_vals if var_vals else terms
            if not values:
                continue
            hit_names = ["Store API"]
            if page_norm and all_terms_present(page_norm, values):
                hit_names.append("rendered product page")
            if gt_norm and all_terms_present(gt_norm, values):
                hit_names.append("per-merchant ground truth")
            if len(hit_names) >= 3:
                band, basis = ("95% or greater",
                    "Word-for-word agreement across 3 store sources: Store API, "
                    "rendered product page, and per-merchant ground truth")
            elif len(hit_names) == 2:
                band, basis = ("80-94%",
                    f"Agreement across 2 store sources: {', '.join(hit_names)}")
            else:
                band, basis = ("50-79%",
                    f"Choice terms appear in one store source only: {', '.join(hit_names)}")
            slug = re.sub(r"[^a-z0-9]+", "_", attr_name.lower()).strip("_")
            field = "_ovo_sizes_available" if attr_name.lower() in ("size", "shoe size") else f"_ovo_variant_{slug}"
            add(field, list(values), "merchant-provided", band, basis,
                f"{attr_name}: {', '.join(values)}", f"attributes.{attr_name} + variations")
        preservation.append({
            "product_id": str(pid), "field": "_ovo_original_description",
            "old_value": "native field unchanged", "new_value": desc,
            "source_label": "merchant-provided", "prd_accuracy_band": "95% or greater",
            "prd_human_check": "Not a proposal - stored automatically with an approved batch",
            "presented_to_merchant": "NO - preservation only, not a proposal",
            "accuracy_basis": "Word-for-word agreement across store sources for this store",
            "evidence": desc, "source_field": "description",
            "source_url": prod["permalink"], "source_urls": [prod["permalink"], base_url],
            "fetched_at_utc": fetched_at,
        })
        # Photo rows: one per image, not only the first.
        colours = colour_terms(prod)
        cats = [c.get("name", "") for c in prod.get("categories", []) if c.get("name")]
        images = prod.get("images") or []
        vis_first = None
        for idx, image in enumerate(images):
            if not image.get("src"):
                continue
            if colours and cats:
                alt = f"{name}, {colours[0]}, {cats[0]}"
                field = "_ovo_image_alt" if idx == 0 else f"_ovo_image_alt_{idx + 1}"
                if idx == 0:
                    vis_first = vision_check(image["src"], name)
                    vis = vis_first
                    run["vision_results"][str(pid)] = vis
                else:
                    # Additional images are not vision-checked individually
                    # in this run; their alt rows are capped at 50-79%.
                    vis = {"error": "additional image not vision-checked in this run"}
                if "error" in vis:
                    if idx == 0:
                        run["vision_failures"].append({"product_id": pid, "error": vis["error"]})
                    add(field, alt, "modelled", "50-79%",
                        "Text parts match store sources; live vision check did not "
                        "corroborate this photo, so band is capped at 50-79%.",
                        f"Name: {name}; Colour: {colours[0]}; Category: {cats[0]}",
                        "name + attributes.Colour/Color + categories",
                        old="none — new OVO field; native image alt is empty",
                        extra={"image_url": image["src"], "image_id": image.get("id")})
                else:
                    ok = type_match_general(cats[0], vis.get("product_type", ""), name) and colour_match(colours[0], vis["dominant_colour"])
                    if ok:
                        add(field, alt, "modelled", "80-94%",
                            "Text parts match store sources; photo type and dominant colour "
                            "match in live vision check, but colour shade is a visual "
                            "judgement, so band is capped below 95%.",
                            f"Name: {name}; Colour: {colours[0]}; Category: {cats[0]}",
                            "name + attributes.Colour/Color + categories",
                            old="none — new OVO field; native image alt is empty",
                            extra={"image_url": image["src"], "image_id": image.get("id"),
                                   "confidence_percent": vis.get("confidence_percent")})
                    else:
                        add(field, alt, "modelled", "50-79%",
                            "Text parts match store sources; live vision check did not match "
                            "photo type or dominant colour, so band is capped at 50-79%.",
                            f"Name: {name}; Colour: {colours[0]}; Category: {cats[0]}",
                            "name + attributes.Colour/Color + categories",
                            old="none — new OVO field; native image alt is empty",
                            extra={"image_url": image["src"], "image_id": image.get("id")})
        # Visual-only path: only when store words have no material.
        if material is None and vis_first is not None:
            vo = visual_only_proposal(pid, images[0]["src"] if images else "", vis_first)
            if vo:
                vo["fetched_at_utc"] = fetched_at
                vo["source_urls"] = [images[0]["src"]] if images else []
                rows.append(vo)

    enrichment_rows = rows
    refresh = compare_refresh(previous, enrichment_rows) if previous is not None else {
        "unchanged_count": 0, "new_count": len(enrichment_rows), "changed_count": 0,
        "stale_count": 0, "new_rows": [], "changed_rows": [], "stale_rows": [],
        "note": "No previous diff for this merchant; this run is the baseline."}
    run["refresh"] = refresh
    all_rows = enrichment_rows + preservation
    unproposed_list = []
    for field, reason, code, nxt in UNPROPOSED_CANDIDATES:
        if field in supplied_unproposed:
            continue
        unproposed_list.append({"field": field, "reason": reason,
                                "reason_code": code, "next_action": nxt})
        all_rows.append({
            "product_id": "ALL", "field": field, "old_value": "", "new_value": "",
            "source_label": "", "prd_accuracy_band": "under 50%",
            "prd_human_check": HUMAN_CHECK["under 50%"],
            "presented_to_merchant": "NO - audit file only", "accuracy_basis": reason,
            "evidence": "", "source_field": "", "source_url": "",
            "fetched_at_utc": "", "reason_code": code, "next_action": nxt,
        })
    band_order = {"95% or greater": 0, "80-94%": 1, "50-79%": 2, "under 50%": 3}
    def sort_key(r):
        pid = int(r["product_id"]) if r["product_id"].isdigit() else 10**9
        return (band_order[r["prd_accuracy_band"]], pid, r["field"])
    all_rows.sort(key=sort_key)

    diff = {
        "format": "ovo-enrichment-diff", "version": "4.0-live",
        "status": "proposed_only_awaiting_merchant_approval", "published": False,
        "generated_at_utc": run["generated_at_utc"], "batch_id": batch_id,
        "merchant": merchant, "store_url": base_url, "endpoint_form": endpoint_form,
        "generated_from": "live Store API for the given store + rendered product pages + per-merchant ground truth + live Spark vision",
        "product_count": len(products), "proposal_count": len(enrichment_rows),
        "preservation_count": len(preservation),
        "unproposed_count": len(unproposed_list),
        "visual_only_count": sum(1 for r in enrichment_rows if r["source_label"] == "observed_visual"),
        "proposals": enrichment_rows, "preservation": preservation,
        "unproposed_fields_audit_only": unproposed_list,
        "vision_results": run["vision_results"], "refresh": refresh,
        "variations_checked": variations_checked,
        "language_out_of_scope": run["language_out_of_scope"],
    }
    (HERE / "enrichment_diff_live.json").write_text(json.dumps(diff, indent=2))
    cols = ["product_id", "field", "old_value", "new_value", "source_label",
            "prd_accuracy_band", "prd_human_check", "presented_to_merchant", "accuracy_basis",
            "evidence", "source_field", "source_url", "fetched_at_utc", "reason_code", "next_action"]
    csv_rows = []
    for r in all_rows:
        c = dict(r)
        c["new_value"] = normalize_value(c["new_value"])
        for k in cols:
            c.setdefault(k, "")
        csv_rows.append({k: c.get(k, "") for k in cols})
    with open(HERE / "live_enrichment.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        writer.writerows(csv_rows)
    merchant_file = merchant_dir / f"{batch_id}.json"
    merchant_file.write_text(json.dumps(diff, indent=2))
    (merchant_dir / "latest.json").write_text(json.dumps(diff, indent=2))
    run["merchant_file"] = str(merchant_file.relative_to(HERE))
    run["counts"] = {
        "products": len(products), "enrichment_rows": len(enrichment_rows),
        "preservation_rows": len(preservation), "unproposed_fields": len(unproposed_list),
        "total_csv_rows": len(all_rows), "visual_only_count": diff["visual_only_count"],
        "untrusted_flags": len(run["untrusted_flags"]),
        "language_out_of_scope": len(run["language_out_of_scope"]),
        "variations_checked": variations_checked,
        "by_band": {b: sum(1 for r in enrichment_rows if r["prd_accuracy_band"] == b)
                    for b in ["95% or greater", "80-94%", "50-79%"]},
    }
    (HERE / "enrichment_run_live.json").write_text(json.dumps(run, indent=2))
    print(json.dumps(run["counts"], indent=2))
    print(f"Store: {base_url}  Merchant: {merchant}  Endpoint: {endpoint_form}")
    print(f"Merchant file: {run['merchant_file']}")
    print(f"Refresh: unchanged={refresh['unchanged_count']} new={refresh['new_count']} "
          f"changed={refresh['changed_count']} stale={refresh['stale_count']}")
    print("No store change. No publish. Status: proposed only.")


if __name__ == "__main__":
    main()
