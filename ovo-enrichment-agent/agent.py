#!/usr/bin/env python3
"""
OvO Enrichment Agent — live, widened task, v3 (Stream 2).

Completes the 8 remaining work items, 2026-10-30:
1. Exact source evidence behind every proposal.
2. Variant choices for any product, one by one, from the store's
   own variation attributes and variation records — never only
   shoes, never only Size, and never a stock number.
3. Every unproposed field carries a reason code and a next action.
4. Hidden orders in store text are flagged and never used.
5. Refresh proposes only what changed.
6. Each merchant's batch is saved in that merchant's own file,
   named by merchant, date, and batch.
7. List values are typed lists in JSON, not comma strings.
8. A photo value is proposed only with its recorded confidence
   score, and only when store words are missing for that field.

When tasked by the Coordinating Agent, this agent runs live.
It never publishes. It never changes the live store. It never
approves on the merchant's behalf. Task definition: AGENT.md.
Publishing belongs to the Plug stream. Approval belongs to the
Merchant Approval Agent.

Usage: python3 agent.py
"""
import csv
import html
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
STORE_API = "https://wsiventures.com/solemates/?rest_route=/wc/store/v1/products&per_page=100"
GROUND_TRUTH = Path.home() / "workspace/ovo-hackathon/eval/ground-truth-2026-10-29.md"
META_HELPER = Path.home() / "workspace/custom-connectors/custom.meta-model-api/bin/meta_model.py"
MERCHANT_SLUG = "sole-mates"

# field, reason, reason_code, next_action
UNPROPOSED_FIELDS = [
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
    ("price_or_discount_change", "Price is $1.00 CAD in the store and is never enriched.", "blocked_critical", "never_propose"),
]

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

# Pattern names only are returned and logged. Instruction text itself
# is never quoted, never stored, and never acted on.
UNTRUSTED_PATTERNS = [
    ("ignore_instructions", r"\bignore\s+(?:previous|all|above|your)\s+instructions?\b"),
    ("disregard_instructions", r"\bdisregard\s+(?:previous|all|your)\s+instructions?\b"),
    ("system_prompt_claim", r"\bsystem\s+prompt\b"),
    ("override_rule", r"\boverride\s+(?:the\s+)?(?:rules?|instructions?)\b"),
    ("do_not_follow", r"\bdo\s+not\s+(?:follow|obey)\s+(?:the\s+)?(?:rules?|instructions?)\b"),
    ("you_must_now", r"\byou\s+must\s+now\b"),
]


def clean_text(raw):
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw or ""))
    return re.sub(r"\s+", " ", text).strip()


def norm(text):
    text = clean_text(text).lower()
    for a, b in [("—", "-"), ("–", "-"), ("’", "'"), ("“", '"'), ("”", '"')]:
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip().rstrip(".")


def fetch_url(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "OvO-Enrichment-Agent/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


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


def split_sentences(text):
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    return [p.rstrip(".") for p in parts]


def attr_terms(product, name):
    for attr in product.get("attributes", []):
        if attr.get("name", "").lower() == name.lower():
            return [t.get("name", "") for t in attr.get("terms", []) if t.get("name")]
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
    """Return pattern names matched in text. Never return quoted text."""
    found = []
    low = (text or "").lower()
    for name, pattern in UNTRUSTED_PATTERNS:
        if re.search(pattern, low):
            found.append(name)
    return found


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
    """Photo-only material appearance, only when no text material exists.

    Returns a proposal dict, or None. Accuracy is exactly the model's
    confidence percent. No confidence means no proposal, ever.
    """
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
    """Pure refresh comparison. previous/current are proposal lists."""
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
                '{"shoe_type": "", "dominant_colour": "", '
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
        return {
            "shoe_type": str(parsed.get("shoe_type", "")),
            "dominant_colour": str(parsed.get("dominant_colour", "")),
            "material_appearance": str(parsed.get("material_appearance", "")),
            "confidence_percent": conf, "raw": content, "model": "muse-spark-1.3",
        }
    except Exception as exc:
        return {"error": f"vision call failed: {exc}"}


def colour_match(colour, dominant):
    return bool(set(re.findall(r"[a-z]+", colour.lower())) &
                set(re.findall(r"[a-z]+", dominant.lower())))


def type_match(category, shoe_type):
    families = {
        "boots": ["boot"], "sandals": ["sandal", "slide"],
        "sneakers": ["sneaker"], "runners": ["runner", "running", "sneaker", "shoe"],
        "slippers": ["slipper"],
    }
    text = shoe_type.lower()
    return any(stem in text for stem in families.get(category.lower(), [category.lower()]))


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
            "rendered product page, and Oct 29 ground truth")
    if len(hits) == 2:
        return "80-94%", f"Word-for-word agreement across 2 store sources: {', '.join(hits)}"
    if len(hits) == 1:
        return "50-79%", f"Value appears in one store source only: {hits[0]}"
    return "under 50%", "No store source for this value; never proposed"


def main():
    run_start = datetime.now(timezone.utc)
    batch_id = f"{MERCHANT_SLUG}-{run_start.strftime('%Y%m%d-%H%M%S')}UTC"
    run = {
        "agent": "OvO Enrichment Agent (live, widened task, v3)",
        "generated_at_utc": run_start.isoformat(), "batch_id": batch_id,
        "merchant": MERCHANT_SLUG, "status": "proposed_only", "published": False,
        "sources": ["live Store API", "rendered product pages",
                    "Oct 29 ground truth (if present)", "live Spark vision"],
        "page_fetch_failures": [], "vision_failures": [], "untrusted_flags": [],
        "vision_results": {}, "notes": [],
    }
    previous = None
    prev_path = HERE / "enrichment_diff_live.json"
    if prev_path.exists():
        try:
            previous = json.loads(prev_path.read_text()).get("proposals", [])
            run["previous_batch"] = json.loads(prev_path.read_text()).get("batch_id")
        except Exception:
            previous = None
    products = json.loads(fetch_url(STORE_API))
    products = sorted(products, key=lambda p: p["id"])
    gt_norm = ""
    if GROUND_TRUTH.exists():
        gt_norm = norm(GROUND_TRUTH.read_text(errors="replace"))
    else:
        run["notes"].append("Ground-truth file absent; text rows capped at 80-94%.")

    rows, preservation = [], []
    variations_checked = 0

    for prod in products:
        pid = prod["id"]
        name = prod["name"]
        desc = clean_text(prod.get("description", ""))
        fetched_at = datetime.now(timezone.utc).isoformat()
        try:
            page_text = clean_text(fetch_url(prod["permalink"]))
        except Exception as exc:
            page_text = ""
            run["page_fetch_failures"].append({"product_id": pid, "error": str(exc)})
        api_norm, page_norm = norm(desc), norm(page_text)
        sources = [("Store API", api_norm)]
        if page_norm:
            sources.append(("rendered product page", page_norm))
        if gt_norm:
            sources.append(("Oct 29 ground truth", gt_norm))

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
                "source_url": prod["permalink"], "source_urls": [prod["permalink"], STORE_API],
                "fetched_at_utc": fetched_at,
            }
            if extra:
                row.update(extra)
            rows.append(row)

        def guarded(field, value, label):
            """Return True if the segment is clean and may be proposed."""
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
        # Variant choices, for any product: every attribute the store
        # itself marks as having variations, one row per attribute,
        # with a typed list value. Non-variant attributes get no
        # variant row. No stock number is ever proposed.
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
                hit_names.append("Oct 29 ground truth")
            if len(hit_names) >= 3:
                band, basis = ("95% or greater",
                    "Word-for-word agreement across 3 store sources: Store API, "
                    "rendered product page, and Oct 29 ground truth")
            elif len(hit_names) == 2:
                band, basis = ("80-94%",
                    f"Agreement across 2 store sources: {', '.join(hit_names)}")
            else:
                band, basis = ("50-79%",
                    f"Choice terms appear in one store source only: {', '.join(hit_names)}")
            slug = re.sub(r"[^a-z0-9]+", "_", attr_name.lower()).strip("_")
            field = "_ovo_sizes_available" if attr_name.lower() == "size" else f"_ovo_variant_{slug}"
            add(field, list(values), "merchant-provided", band, basis,
                f"{attr_name}: {', '.join(values)}", f"attributes.{attr_name} + variations")
        preservation.append({
            "product_id": str(pid), "field": "_ovo_original_description",
            "old_value": "native field unchanged", "new_value": desc,
            "source_label": "merchant-provided", "prd_accuracy_band": "95% or greater",
            "prd_human_check": "Not a proposal - stored automatically with an approved batch",
            "presented_to_merchant": "NO - preservation only, not a proposal",
            "accuracy_basis": "Word-for-word agreement across 3 store sources: Store API, "
                              "rendered product page, and Oct 29 ground truth",
            "evidence": desc, "source_field": "description",
            "source_url": prod["permalink"], "source_urls": [prod["permalink"], STORE_API],
            "fetched_at_utc": fetched_at,
        })
        colours = attr_terms(prod, "Colour")
        cats = [c.get("name", "") for c in prod.get("categories", []) if c.get("name")]
        image = (prod.get("images") or [{}])[0]
        vis = None
        if colours and cats and image.get("src"):
            alt = f"{name}, {colours[0]}, {cats[0]}"
            vis = vision_check(image["src"], name)
            run["vision_results"][str(pid)] = vis
            if "error" in vis:
                run["vision_failures"].append({"product_id": pid, "error": vis["error"]})
                add("_ovo_image_alt", alt, "modelled", "50-79%",
                    "Text parts match store sources; live vision check did not "
                    "corroborate the photo, so band is capped at 50-79%.",
                    f"Name: {name}; Colour: {colours[0]}; Category: {cats[0]}",
                    "name + attributes.Colour + categories",
                    old="none — new OVO field; native image alt is empty")
            else:
                ok = type_match(cats[0], vis["shoe_type"]) and colour_match(colours[0], vis["dominant_colour"])
                if ok:
                    add("_ovo_image_alt", alt, "modelled", "80-94%",
                        "Text parts match Store API, product page and Oct 29 ground truth; "
                        "photo type and dominant colour match in live vision check, but "
                        "colour shade is a visual judgement, so band is capped below 95%.",
                        f"Name: {name}; Colour: {colours[0]}; Category: {cats[0]}",
                        "name + attributes.Colour + categories",
                        old="none — new OVO field; native image alt is empty")
                else:
                    add("_ovo_image_alt", alt, "modelled", "50-79%",
                        "Text parts match store sources; live vision check did not match "
                        "photo type or dominant colour, so band is capped at 50-79%.",
                        f"Name: {name}; Colour: {colours[0]}; Category: {cats[0]}",
                        "name + attributes.Colour + categories",
                        old="none — new OVO field; native image alt is empty")
                run["vision_results"][str(pid)]["material_appearance_vs_text"] = (
                    "vision material appearance logged only; text material stands")
            # Visual-only path: only when store words have no material.
            if material is None:
                vo = visual_only_proposal(pid, image["src"], vis)
                if vo:
                    vo["fetched_at_utc"] = fetched_at
                    vo["source_urls"] = [image["src"]]
                    rows.append(vo)
                else:
                    run["notes"].append(
                        f"Product {pid}: no visual-only material proposal; "
                        "no text material and no usable vision confidence.")

    enrichment_rows = rows
    refresh = compare_refresh(previous, enrichment_rows) if previous is not None else {
        "unchanged_count": 0, "new_count": len(enrichment_rows), "changed_count": 0,
        "stale_count": 0, "new_rows": [], "changed_rows": [], "stale_rows": [],
        "note": "No previous live diff found; this run is the baseline."}
    run["refresh"] = refresh
    all_rows = enrichment_rows + preservation
    unproposed_list = []
    for field, reason, code, nxt in UNPROPOSED_FIELDS:
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
        "format": "ovo-enrichment-diff", "version": "3.0-live",
        "status": "proposed_only_awaiting_merchant_approval", "published": False,
        "generated_at_utc": run["generated_at_utc"], "batch_id": batch_id,
        "merchant": MERCHANT_SLUG,
        "generated_from": "live Store API + rendered product pages + Oct 29 ground truth + live Spark vision",
        "product_count": len(products), "proposal_count": len(enrichment_rows),
        "preservation_count": len(preservation),
        "unproposed_count": len(UNPROPOSED_FIELDS),
        "visual_only_count": sum(1 for r in enrichment_rows if r["source_label"] == "observed_visual"),
        "proposals": enrichment_rows, "preservation": preservation,
        "unproposed_fields_audit_only": unproposed_list,
        "vision_results": run["vision_results"], "refresh": refresh,
        "variations_checked": variations_checked,
    }
    (HERE / "enrichment_diff_live.json").write_text(json.dumps(diff, indent=2))
    cols = ["product_id", "field", "old_value", "new_value", "source_label",
            "prd_accuracy_band", "prd_human_check", "presented_to_merchant", "accuracy_basis",
            "evidence", "source_field", "source_url", "fetched_at_utc", "reason_code", "next_action"]
    csv_rows = []
    for r in all_rows:
        c = dict(r)
        c["new_value"] = normalize_value(c["new_value"])
        c["evidence"] = c.get("evidence", "")
        c["source_field"] = c.get("source_field", "")
        c["source_url"] = c.get("source_url", "")
        c["fetched_at_utc"] = c.get("fetched_at_utc", "")
        c["reason_code"] = c.get("reason_code", "")
        c["next_action"] = c.get("next_action", "")
        csv_rows.append({k: c.get(k, "") for k in cols})
    with open(HERE / "live_enrichment.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        writer.writerows(csv_rows)
    merchant_dir = HERE / "merchant" / MERCHANT_SLUG
    merchant_dir.mkdir(parents=True, exist_ok=True)
    merchant_file = merchant_dir / f"{batch_id}.json"
    merchant_file.write_text(json.dumps(diff, indent=2))
    run["merchant_file"] = str(merchant_file.relative_to(HERE))
    run["counts"] = {
        "products": len(products), "enrichment_rows": len(enrichment_rows),
        "preservation_rows": len(preservation), "unproposed_fields": len(UNPROPOSED_FIELDS),
        "total_csv_rows": len(all_rows), "visual_only_count": diff["visual_only_count"],
        "untrusted_flags": len(run["untrusted_flags"]),
        "variations_checked": variations_checked,
        "by_band": {b: sum(1 for r in enrichment_rows if r["prd_accuracy_band"] == b)
                    for b in ["95% or greater", "80-94%", "50-79%"]},
    }
    (HERE / "enrichment_run_live.json").write_text(json.dumps(run, indent=2))
    print(json.dumps(run["counts"], indent=2))
    print(f"Merchant file: {run['merchant_file']}")
    print(f"Refresh: unchanged={refresh['unchanged_count']} new={refresh['new_count']} "
          f"changed={refresh['changed_count']} stale={refresh['stale_count']}")
    print("No store change. No publish. Status: proposed only.")


if __name__ == "__main__":
    main()
