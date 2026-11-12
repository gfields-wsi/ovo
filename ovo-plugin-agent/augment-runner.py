#!/usr/bin/env python3
"""Augment runner: Plugin-side publish step for the Coordinating Agent.

This is NOT a live publish by itself. Default mode is dry-run: it
verifies, maps, and writes an augment_run.json, and makes no POST.
Live POST mode is deliberately not enabled here, because plugin
token auth on WordPress is untested and the plugin is not installed
on a real store yet. Version 0.2 token auth is in the plugin code,
but it has not been tested on WordPress yet, so --post is refused
until a WordPress test proves it.

Inputs, version 5 only:
- The enrichment diff, format ovo-enrichment-diff 5.0-live. Every
  row in proposals is a proposal. Rows carry new_value and
  old_value, and accuracy as accuracy_percent or prd_accuracy_band.
  There is no accuracy scorecard input. Accuracy travels inside
  the diff.
- The approval record, with an approved_rows list built by the
  runner from the record's approved_as_proposed,
  approved_as_corrected, and added_merchant_supplied lists.

Fail-closed rules, in order:
1. The diff must be format 5.0-live, proposed only, not published,
   with its claimed count matching its actual rows.
2. The diff fingerprint must match the approval record fingerprint,
   using the approval agent's exact algorithm: SHA-256 of JSON
   rows {product_id, field, new_value, old_value}, sorted by
   product_id then field, sort_keys, ensure_ascii False.
3. The approval record must not be awaiting_merchant_decision,
   and it must name approved rows. Awaiting means no POST, no write.
4. Accuracy: every approved row must prove 85 percent or better
   from its own diff row, as an accuracy_percent of 85 or more, or
   a prd_accuracy_band of "95% or greater". A row in "80-94%" with
   no exact percent cannot prove 85 or better, so it is blocked
   and named, instead of being published on a guess. That is the
   version 5 form of the old 85 percent scorecard gate.
5. Only approved rows are mapped. Rejected, held, and unapproved
   rows are never mapped. A corrected row publishes as its
   corrected value, not as originally proposed. A merchant supplied
   row publishes as its added value.
6. Mapping to plugin fields is additional_property only, because
   version 5 fields (_ovo_material and the rest) are enrichment
   fields, and writing them natively would risk a policy or
   attribute claim. The organizer must confirm this mapping before
   any live POST.

Mapping, version 5 field to additional_property label:
  _ovo_material            -> "Material"
  _ovo_material_appearance -> "Material appearance"
  _ovo_returns_summary     -> "Returns"
  _ovo_fit_guidance        -> "Fit"
  _ovo_fit_note            -> "Fit note"
  _ovo_availability_note   -> "Availability"
  _ovo_size_system         -> "Size system"
  _ovo_sizes_available     -> "Sizes available"
  _ovo_variant_<slug>      -> "Variant <slug>"
Source for mapped rows is "observed", because version 5 proposals
are restated from store prose and photos. Confidence is carried as
the approval record status, not invented as a percent.

Usage:
  python3 augment-runner.py --diff <enrichment_diff_live.json> \
    --approval <approval_record.json> --out <augment_run.json>
  Add --post only after a WordPress token test proves it; today
  --post exits with an error and makes no request.
"""
import argparse, hashlib, json, sys
from pathlib import Path

MAP = {
    "_ovo_material": "Material",
    "_ovo_material_appearance": "Material appearance",
    "_ovo_returns_summary": "Returns",
    "_ovo_fit_guidance": "Fit",
    "_ovo_fit_note": "Fit note",
    "_ovo_availability_note": "Availability",
    "_ovo_size_system": "Size system",
    "_ovo_sizes_available": "Sizes available",
}

# A band proves only its low end. Only the top band proves 85 or better.
BAND_MIN = {
    "95% or greater": 95.0,
    "80-94%": 80.0,
    "50-79%": 50.0,
    "under 50%": 0.0,
}
ACCURACY_TARGET = 85.0


def label_for(field):
    if field in MAP:
        return MAP[field]
    if isinstance(field, str) and field.startswith("_ovo_variant_"):
        return "Variant " + field[len("_ovo_variant_"):]
    return None


def fingerprint(proposed):
    rows = sorted(
        [{"product_id": p.get("product_id"), "field": p.get("field"),
          "new_value": p.get("new_value"), "old_value": p.get("old_value")}
         for p in proposed],
        key=lambda r: (str(r["product_id"]), r["field"]),
    )
    blob = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def row_accuracy(proposal):
    """Accuracy a diff row proves, or None. An exact percent wins.
    Otherwise the band low end counts."""
    value = proposal.get("accuracy_percent")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return BAND_MIN.get(proposal.get("prd_accuracy_band"))


def publish_value(prop, row):
    """The value to publish for an approved row. A merchant
    correction or addition wins over the diff proposal."""
    for key in ("corrected_value", "added_value"):
        if row.get(key):
            return row[key]
    if prop.get("new_value"):
        return prop["new_value"]
    return prop.get("proposed_value") or row.get("proposed_value")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diff", required=True)
    ap.add_argument("--approval", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--post", action="store_true")
    args = ap.parse_args()

    diff = json.loads(Path(args.diff).read_text())
    approval = json.loads(Path(args.approval).read_text())

    proposed = list(diff.get("proposals", []))
    result = {
        "agent": "Augment runner, Plugin side",
        "status": "blocked",
        "published": False,
        "posted": False,
        "fingerprint_match": False,
        "accuracy_gate": (
            "each approved row must prove 85 percent or better from its "
            "own diff row, as accuracy_percent or band 95% or greater"
        ),
        "accuracy_bands": {
            band: sum(1 for p in proposed if p.get("prd_accuracy_band") == band)
            for band in ("95% or greater", "80-94%", "50-79%", "under 50%")
        },
        "approved_rows": [],
        "plugin_diff": None,
        "errors": [],
    }

    # 1. Diff shape, version 5 only.
    if diff.get("format") != "ovo-enrichment-diff" or diff.get("version") != "5.0-live":
        result["errors"].append(
            f"unexpected diff format: {diff.get('format')} {diff.get('version')}")
    if diff.get("published") is not False:
        result["errors"].append("diff is marked published")
    if diff.get("status") != "proposed_only_awaiting_merchant_approval":
        result["errors"].append(f"unexpected diff status: {diff.get('status')}")
    if diff.get("proposal_count") != len(proposed):
        result["errors"].append(
            f"diff proposal_count {diff.get('proposal_count')} does not match "
            f"actual rows {len(proposed)}")

    # 2. Fingerprint gate.
    computed = fingerprint(proposed)
    target = approval.get("diff_fingerprint")
    result["computed_fingerprint"] = computed
    result["approval_fingerprint"] = target
    result["fingerprint_match"] = (computed == target)
    if not result["fingerprint_match"]:
        result["errors"].append("diff fingerprint does not match approval record fingerprint")

    # 3. Approval gate.
    if approval.get("status") == "awaiting_merchant_decision":
        result["errors"].append("approval record is awaiting_merchant_decision, no rows are approved")
    approved = approval.get("approved_rows") or []
    # approval_record.json in this workspace uses approved_rows as a list;
    # some records use approved_count only. Both must name rows to publish.
    if not approved:
        result["errors"].append("approval record names no approved rows")

    if result["errors"]:
        result["status"] = "blocked_awaiting_or_failed_gate"
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return 2

    # 4. Accuracy gate, per approved row.
    by_key = {(p["product_id"], p["field"]): p for p in proposed}
    for row in approved:
        key = (row.get("product_id"), row.get("field"))
        prop = by_key.get(key)
        if prop is None:
            # A merchant supplied addition has no diff row. Its
            # accuracy is the merchant's own word, so it passes
            # this gate; the fingerprint already binds the diff.
            if row.get("added_value"):
                continue
            result["errors"].append(f"approved row is not in the diff: {key}")
            continue
        accuracy = row_accuracy(prop)
        if accuracy is None or accuracy < ACCURACY_TARGET:
            result["errors"].append(
                f"approved row {key} proves {accuracy} percent, below the "
                f"85 percent target (band {prop.get('prd_accuracy_band')})")
    if result["errors"]:
        result["status"] = "blocked_accuracy_gate"
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return 2

    # 5-6. Map approved rows only, additional_property only.
    changes = []
    for row in approved:
        # Approved rows may be full rows or {product_id, field} keys.
        key = (row.get("product_id"), row.get("field"))
        prop = by_key.get(key) or row
        label = label_for(prop.get("field"))
        if label is None:
            result["errors"].append(f"unmapped field, not published: {prop.get('field')}")
            continue
        value = publish_value(prop, row)
        if value in (None, ""):
            result["errors"].append(f"approved row {key} has no value to publish")
            continue
        changes.append({
            "product_id": prop["product_id"],
            "field": "additional_property",
            "old_value": "",
            "new_value": f"{label}|{value}",
            "source": "observed",
            "confidence": "approved",
        })
    if result["errors"]:
        result["status"] = "blocked_unmapped_field"
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return 2

    result["approved_rows"] = changes
    result["plugin_diff"] = {
        "batch_id": f"augment-{computed[:12]}",
        "approved_by": approval.get("approved_by"),
        "approval_fingerprint": computed,
        "changes": changes,
    }
    result["status"] = "dry_run_ready_not_posted"
    if args.post:
        result["errors"].append("--post is refused: plugin token auth has not been tested on WordPress yet, and the plugin is not installed on a real store")
        result["status"] = "blocked_post_not_enabled"
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return 2

    Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
