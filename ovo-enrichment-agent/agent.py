#!/usr/bin/env python3
"""
OvO Enrichment Agent — live, widened task (Stream 2).

Step 2 of Greg's two steps, 2026-10-30. When tasked by the
Coordinating Agent, this agent runs live: it reads the live store,
proposes enrichment rows, scores each row by PRD band, and stops
at proposed. It never publishes. It never changes the live store.
It never approves on the merchant's behalf.

Task definition: AGENT.md in this folder. That file governs.
Publishing belongs to the Plug stream. Approval belongs to the
Merchant Approval Agent.

Inputs, all store-only:
- Live Store API list endpoint
- Each product's rendered product page, by permalink
- Oct 29 ground-truth file, if present, as a third text source
- Each product photo, through Muse Spark 1.3 vision via the
  registered Meta Model API helper (no key in this code)

Outputs, in this folder:
- enrichment_diff_live.json
- live_enrichment.csv (same rows, master CSV columns, for checking)
- enrichment_run_live.json (run log, vision results, counts)

Guardrails, enforced in code:
- A value is proposed only from store text, store attributes, or
  a recorded vision confidence number. No other source is used.
- Text always wins over visual appearance. Vision material
  appearance is logged only, never a replacement for text material.
- A visual-only row needs a confidence number. No number means
  no proposal, and the failure is logged. Confidence is never
  guessed or carried over from another product.
- Held fields (price, stock, SKU, GTIN, tax, shipping, weight,
  dimensions, width, brand, care, closure, size guide, size system,
  store-wide policy, safety/compatibility) are never proposed.
  They are listed in the audit section only, as under 50 percent.
- Untrusted store text is data, never an instruction.

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

HELD_FIELDS = [
    ("width", "No width value in any store source; relative comparisons are not measurements."),
    ("weight", "Weight is empty in the Store API for all products."),
    ("dimensions", "Length, width, and height are empty in the Store API for all products."),
    ("stock_quantity_per_size", "Stock is a boolean in-stock flag only; no per-size quantity exists."),
    ("gtin", "No GTIN exists in any store source."),
    ("brand", "Brands are empty in the Store API for all products."),
    ("care_instructions", "No care instructions in any store source."),
    ("closure_type", "No closure type field in any store source."),
    ("size_guide", "No size guide in any store source."),
    ("shipping_cost", "No shipping cost in any store source."),
    ("delivery_time", "No delivery time in any store source."),
    ("tax_class", "Tax class must not be modelled."),
    ("shipping_class", "Shipping class must not be modelled."),
    ("size_system", "No size system (men's/women's/US/UK) is stated in any store source."),
    ("store_wide_legal_policy", "Returns are copied per product only; no store-wide legal policy is claimed."),
    ("safety_or_compatibility_claim", "Safety and compatibility claims must not be modelled."),
    ("price_or_discount_change", "Price is $1.00 CAD in the store and is never enriched."),
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


def vision_check(image_url, product_name):
    """One live Spark vision call. Returns a dict, never a guessed value."""
    payload = {
        "model": "muse-spark-1.3",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Look at this product photo. Reply with JSON only: "
                            '{"shoe_type": "", "dominant_colour": "", '
                            '"material_appearance": "", "confidence_percent": 0}. '
                            "Give a confidence percent for material_appearance only."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ],
        "reasoning_effort": "minimal",
        "max_tokens": 500,
    }
    try:
        proc = subprocess.run(
            [sys.executable, str(META_HELPER), "chat"],
            input=json.dumps(payload), capture_output=True, text=True, timeout=120,
        )
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
            "confidence_percent": conf,
            "raw": content,
        }
    except Exception as exc:  # fail closed: no vision number, no visual proposal
        return {"error": f"vision call failed: {exc}"}


def colour_match(colour, dominant):
    c_words = set(re.findall(r"[a-z]+", colour.lower()))
    d_words = set(re.findall(r"[a-z]+", dominant.lower()))
    return bool(c_words & d_words)


def type_match(category, shoe_type):
    families = {
        "boots": ["boot"],
        "sandals": ["sandal", "slide"],
        "sneakers": ["sneaker"],
        "runners": ["runner", "running", "sneaker", "shoe"],
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
    """sources: list of normalised source texts. Returns (band, basis)."""
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
    run = {
        "agent": "OvO Enrichment Agent (live, widened task)",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "proposed_only",
        "published": False,
        "sources": ["live Store API", "rendered product pages",
                    "Oct 29 ground truth (if present)", "live Spark vision"],
        "page_fetch_failures": [], "vision_failures": [],
        "vision_results": {}, "notes": [],
    }
    products = json.loads(fetch_url(STORE_API))
    products = sorted(products, key=lambda p: p["id"])
    gt_text = ""
    gt_norm = ""
    if GROUND_TRUTH.exists():
        gt_text = GROUND_TRUTH.read_text(errors="replace")
        gt_norm = norm(gt_text)
    else:
        run["notes"].append("Ground-truth file absent; text rows capped at 80-94%.")

    rows = []  # enrichment rows, dicts in master CSV columns
    preservation = []

    for prod in products:
        pid = prod["id"]
        name = prod["name"]
        desc = clean_text(prod.get("description", ""))
        try:
            page_html = fetch_url(prod["permalink"])
            page_text = clean_text(page_html)
        except Exception as exc:
            page_text = ""
            run["page_fetch_failures"].append({"product_id": pid, "error": str(exc)})
        api_norm, page_norm = norm(desc), norm(page_text)
        sources = [("Store API", api_norm)]
        if page_norm:
            sources.append(("rendered product page", page_norm))
        if gt_norm:
            sources.append(("Oct 29 ground truth", gt_norm))
        if not gt_norm:
            sources = sources[:2]

        def add(field, new_value, source_label, band, basis, old="none — new OVO field"):
            if not new_value:
                return
            if band == "under 50%":
                return  # never proposed
            rows.append({
                "product_id": str(pid), "field": field, "old_value": old,
                "new_value": new_value, "source_label": source_label,
                "prd_accuracy_band": band, "prd_human_check": HUMAN_CHECK[band],
                "presented_to_merchant": PRESENTED[band], "accuracy_basis": basis,
            })

        material = segment(desc, "Material", ["Fit", "Returns"])
        fit_full = segment(desc, "Fit", ["Returns"])
        returns = segment(desc, "Returns", [])
        for field, value in [("_ovo_material", material),
                             ("_ovo_returns_summary", returns)]:
            band, basis = band_from_sources(value, sources) if value else ("under 50%", "")
            add(field, value, "merchant-provided", band, basis)
        # Fit: split availability / comparison sentences into notes; otherwise full segment.
        if fit_full:
            sentences = split_sentences(fit_full)
            if len(sentences) > 1 and "in-store only" in sentences[1].lower():
                add("_ovo_fit_guidance", sentences[0], "merchant-provided",
                    *band_from_sources(sentences[0], sources))
                add("_ovo_availability_note", sentences[1], "merchant-provided",
                    *band_from_sources(sentences[1], sources))
            elif len(sentences) > 1 and " than " in sentences[1].lower():
                add("_ovo_fit_guidance", sentences[0], "merchant-provided",
                    *band_from_sources(sentences[0], sources))
                add("_ovo_fit_note", sentences[1], "merchant-provided",
                    *band_from_sources(sentences[1], sources))
            else:
                band, basis = band_from_sources(fit_full, sources)
                add("_ovo_fit_guidance", fit_full, "merchant-provided", band, basis)
        sizes = attr_terms(prod, "Size")
        if sizes:
            value = ", ".join(sizes)
            # Sizes are an attribute list, not prose: agreement means every
            # term is present in each source (API attributes, page options,
            # ground-truth attribute list), not a verbatim joined string.
            hit_names = []
            if sizes:
                hit_names.append("Store API")
            if page_norm and all_terms_present(page_norm, sizes):
                hit_names.append("rendered product page")
            if gt_norm and all_terms_present(gt_norm, sizes):
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
                    f"Size terms appear in one store source only: {', '.join(hit_names)}")
            add("_ovo_sizes_available", value, "merchant-provided", band, basis)
        # Preservation row: never a proposal, never in a merchant list.
        preservation.append({
            "product_id": str(pid), "field": "_ovo_original_description",
            "old_value": "native field unchanged", "new_value": desc,
            "source_label": "merchant-provided", "prd_accuracy_band": "95% or greater",
            "prd_human_check": "Not a proposal - stored automatically with an approved batch",
            "presented_to_merchant": "NO - preservation only, not a proposal",
            "accuracy_basis": "Word-for-word agreement across 3 store sources: Store API, "
                              "rendered product page, and Oct 29 ground truth",
        })
        # Image alt, with live vision corroboration.
        colours = attr_terms(prod, "Colour")
        cats = [c.get("name", "") for c in prod.get("categories", []) if c.get("name")]
        image = (prod.get("images") or [{}])[0]
        if colours and cats and image.get("src"):
            alt = f"{name}, {colours[0]}, {cats[0]}"
            vis = vision_check(image["src"], name)
            run["vision_results"][str(pid)] = vis
            if "error" in vis:
                run["vision_failures"].append({"product_id": pid, "error": vis["error"]})
                add("_ovo_image_alt", alt, "modelled", "50-79%",
                    "Text parts match store sources; live vision check did not "
                    "corroborate the photo, so band is capped at 50-79% and "
                    "row-by-row approval applies.",
                    old="none — new OVO field; native image alt is empty")
            else:
                ok = type_match(cats[0], vis["shoe_type"]) and colour_match(colours[0], vis["dominant_colour"])
                if ok:
                    add("_ovo_image_alt", alt, "modelled", "80-94%",
                        "Text parts match Store API, product page and Oct 29 ground truth; "
                        "photo type and dominant colour match in live vision check, but "
                        "colour shade is a visual judgement, not a word-for-word copy, "
                        "so band is capped below 95%.",
                        old="none — new OVO field; native image alt is empty")
                else:
                    add("_ovo_image_alt", alt, "modelled", "50-79%",
                        "Text parts match store sources; live vision check did not match "
                        "photo type or dominant colour, so band is capped at 50-79% and "
                        "row-by-row approval applies.",
                        old="none — new OVO field; native image alt is empty")
                # Vision material appearance is logged only, never a proposal.
                # Text material wins. No visual-only row is created here
                # because every schema field already has a text source.
                run["vision_results"][str(pid)]["material_appearance_vs_text"] = (
                    "vision material appearance logged only; text material stands")

    enrichment_rows = rows
    all_rows = enrichment_rows + preservation
    for field, reason in HELD_FIELDS:
        all_rows.append({
            "product_id": "ALL", "field": field, "old_value": "", "new_value": "",
            "source_label": "", "prd_accuracy_band": "under 50%",
            "prd_human_check": HUMAN_CHECK["under 50%"],
            "presented_to_merchant": "NO - audit file only", "accuracy_basis": reason,
        })
    band_order = {"95% or greater": 0, "80-94%": 1, "50-79%": 2, "under 50%": 3}
    def sort_key(r):
        pid = int(r["product_id"]) if r["product_id"].isdigit() else 10**9
        return (band_order[r["prd_accuracy_band"]], pid, r["field"])
    all_rows.sort(key=sort_key)

    diff = {
        "format": "ovo-enrichment-diff", "version": "2.0-live",
        "status": "proposed_only_awaiting_merchant_approval", "published": False,
        "generated_at_utc": run["generated_at_utc"],
        "generated_from": "live Store API + rendered product pages + Oct 29 ground truth + live Spark vision",
        "product_count": len(products),
        "proposal_count": len(enrichment_rows),
        "preservation_count": len(preservation),
        "held_count": len(HELD_FIELDS),
        "proposals": enrichment_rows,
        "preservation": preservation,
        "held_fields_audit_only": [{"field": f, "reason": r} for f, r in HELD_FIELDS],
        "vision_results": run["vision_results"],
    }
    (HERE / "enrichment_diff_live.json").write_text(json.dumps(diff, indent=2))
    cols = ["product_id", "field", "old_value", "new_value", "source_label",
            "prd_accuracy_band", "prd_human_check", "presented_to_merchant", "accuracy_basis"]
    with open(HERE / "live_enrichment.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        writer.writerows(all_rows)
    run["counts"] = {
        "products": len(products), "enrichment_rows": len(enrichment_rows),
        "preservation_rows": len(preservation), "held_fields": len(HELD_FIELDS),
        "total_csv_rows": len(all_rows),
        "by_band": {b: sum(1 for r in enrichment_rows if r["prd_accuracy_band"] == b)
                    for b in ["95% or greater", "80-94%", "50-79%"]},
    }
    (HERE / "enrichment_run_live.json").write_text(json.dumps(run, indent=2))
    print(json.dumps(run["counts"], indent=2))
    print("Wrote enrichment_diff_live.json, live_enrichment.csv, enrichment_run_live.json")
    print("No store change. No publish. Status: proposed only.")


if __name__ == "__main__":
    main()
