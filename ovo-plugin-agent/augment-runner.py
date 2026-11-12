#!/usr/bin/env python3
"""Augment runner: Plugin-side publish step for the Coordinating Agent.

This is NOT a live publish by itself. Default mode is dry-run: it
verifies, maps, and writes an augment_run.json, and makes no POST.
Live POST mode is deliberately not enabled here, because plugin
version 0.1 has no token auth and the plugin is not installed on
Sole Mates yet. Version 0.2 token auth is in the plugin code, but
it has not been tested on WordPress yet, so --post is refused
until a WordPress test proves it.

Fail-closed rules, in order:
1. Accuracy must be present and at or above 85 percent, or stop.
2. The diff fingerprint must match the approval record fingerprint,
   using the approval agent's exact algorithm: SHA-256 of JSON
   rows {product_id, field, proposed_value, current_value},
   sorted by product_id then field, sort_keys, ensure_ascii False.
3. The approval record must not be awaiting_merchant_decision,
   and it must name approved rows. Awaiting means no POST, no write.
4. Only approved rows are mapped. Rejected, held, and unapproved
   rows are never mapped.
5. Mapping to plugin fields is additional_property only, because
   framework fields (material_structured, fit_structured,
   returns_structured) do not match plugin native fields, and
   writing them natively would risk a policy or attribute claim.
   The organizer must confirm this mapping before any live POST.

Mapping:
  material_structured -> additional_property "Material|<value>"
  fit_structured      -> additional_property "Fit|<value>"
  returns_structured  -> additional_property "Returns|<value>"
Source for mapped rows is "observed", because framework proposals
are restated from store prose. Confidence is carried as the
approval record status, not invented as a percent.

Usage:
  python3 augment-runner.py --diff <enrichment_diff.json> \
    --approval <approval_record.json> --accuracy <accuracy_scorecard.json> \
    --out <augment_run.json>
  Add --post only after a WordPress token test proves it; today
  --post exits with an error and makes no request.
"""
import argparse, hashlib, json, sys
from pathlib import Path

MAP = {
    "material_structured": "Material",
    "fit_structured": "Fit",
    "returns_structured": "Returns",
}

def fingerprint(proposed):
    rows = sorted(
        [{"product_id": p.get("product_id"), "field": p.get("field"),
          "proposed_value": p.get("proposed_value"), "current_value": p.get("current_value")}
         for p in proposed],
        key=lambda r: (r["product_id"], r["field"]),
    )
    blob = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diff", required=True)
    ap.add_argument("--approval", required=True)
    ap.add_argument("--accuracy", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--post", action="store_true")
    args = ap.parse_args()

    diff = json.loads(Path(args.diff).read_text())
    approval = json.loads(Path(args.approval).read_text())
    accuracy = json.loads(Path(args.accuracy).read_text())

    proposed = [p for p in diff.get("proposals", []) if p.get("status") == "proposed"]
    result = {
        "agent": "Augment runner, Plugin side",
        "status": "blocked",
        "published": False,
        "posted": False,
        "fingerprint_match": False,
        "accuracy_percent": accuracy.get("accuracy_percent") or accuracy.get("percent"),
        "approved_rows": [],
        "plugin_diff": None,
        "errors": [],
    }

    # 1. Accuracy gate
    acc = result["accuracy_percent"]
    if acc is None:
        result["errors"].append("accuracy_percent missing from scorecard")
    elif float(acc) < 85:
        result["errors"].append(f"accuracy {acc} is below the 85 percent PRD target")

    # 2. Fingerprint gate
    computed = fingerprint(proposed)
    target = approval.get("diff_fingerprint")
    result["computed_fingerprint"] = computed
    result["approval_fingerprint"] = target
    result["fingerprint_match"] = (computed == target)
    if not result["fingerprint_match"]:
        result["errors"].append("diff fingerprint does not match approval record fingerprint")

    # 3. Approval gate
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

    # 4-5. Map approved rows only, additional_property only.
    by_key = {(p["product_id"], p["field"]): p for p in proposed}
    changes = []
    for row in approved:
        # Approved rows may be full rows or {product_id, field} keys.
        key = (row.get("product_id"), row.get("field"))
        prop = by_key.get(key) or row
        if prop.get("field") not in MAP:
            result["errors"].append(f"unmapped field, not published: {prop.get('field')}")
            continue
        changes.append({
            "product_id": prop["product_id"],
            "field": "additional_property",
            "old_value": "",
            "new_value": f"{MAP[prop['field']]}|{prop.get('proposed_value') or row.get('proposed_value')}",
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
        result["errors"].append("--post is refused: plugin token auth has not been tested on WordPress yet, and the plugin is not installed on Sole Mates")
        result["status"] = "blocked_post_not_enabled"
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return 2

    Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
