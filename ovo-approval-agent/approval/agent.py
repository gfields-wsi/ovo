#!/usr/bin/env python3
"""
OvO Merchant Approval Agent, built on the shared OvO agent framework.

Confirmed definition, 30 October 2026, by Greg:
- Group enrichments by accuracy, and present one card per group.
- At 95 percent or better, lack of rejection in a submitted group
  review equals approval. This is rejection by exception.
- At 80 to 94 percent, and at 50 to 79 percent, the merchant
  approves individual enrichments. A row not explicitly approved
  in those bands is not approved.
- Under 50 percent, no row is presented, and no row is approved.
- The merchant can correct a proposed value, or add information
  where it applies. The agent records the merchant value exactly
  as given, marked merchant supplied, separate from the enrichment
  value. Full card edit design comes later. The record supports
  corrections and additions now.
- RACI: the Enrichment Agent is Responsible for enrichment and
  its accuracy. The Coordinating Agent is Accountable for the
  enrichment output. This agent is neither Responsible nor
  Accountable for enrichment accuracy. It is Responsible only for
  recording merchant decisions accurately, in aggregate, by group.
- R4, only their data: a packet, a card, and a record carry a
  merchant ID and a store ID when those IDs are supplied. A
  decision whose merchant ID or store ID does not match the
  packet is rejected. No packet lists rows from more than one
  store. Today the live inputs supply a store URL and no merchant
  ID, so the live packet is marked store only, with no merchant
  ID. That gap is recorded, not hidden.
- R5, questions: a merchant can ask a question on a row or a
  group. The question is recorded, with product, field, proposed
  value, merchant, and time. A row with an open question is not
  approved, and it is not rejected. The merchant can close a
  question, then approve, reject, or correct the row. Answering
  a question is Enrichment and Coordinator work, not this agent.
- R6, authority: a decision is recorded only from a merchant
  session for that store. A typed name alone is not authority.
  The session must name a merchant ID and a store ID, must be
  submitted by the merchant, must not be revoked, and must not
  be expired. The record shows the merchant ID from the session.
  Session check limit: this code checks the session fields,
  expiry, revocation flag, and ID match. It does not verify a
  cryptographic signature, because no platform issuer or key is
  supplied yet. That proof is platform work, not yet built.

Trust boundary, by design:
This agent trusts the enrichments it is given. It does not re-check
enrichment values against source text, and it does not recompute
accuracy. If enrichment is wrong, that is Enrichment and Coordinator
work to fix, not this agent's work. This agent's own checks are
limited to the packet and record: the diff format, the not-published
flags, the approval flags, the fingerprint binding, and the decision
file itself. A changed diff still fails by fingerprint, because an
approval record for an old diff must not be reused.

Job: prepare the approval packet and cards, and record only the
merchant's own decision, in aggregate, by group. This agent never
approves anything on its own. It never publishes. It never changes
the live store. It never changes gaps.json, enrichment_diff.json,
or accuracy_scorecard.json. It only writes its own files here.

Inputs, read only:
- ../stream2-enrichment/enrichment_diff.json,
  format ovo-enrichment-diff 1.0-proposed
- ../accuracy/accuracy_scorecard.json,
  format ovo-accuracy-scorecard 1.0, used only to group rows
- ../coordinator/coordinator_run.json, when present, checked only
  for a published flag. It is not changed.

Accuracy grouping:
A row's accuracy percent is taken, in order, from:
1. accuracy_percent on the diff proposal itself, when present, or
2. the accuracy scorecard result for that row: accurate true maps
   to 100 percent, accurate false maps to 0 percent.
The scorecard today marks each row accurate or not accurate only,
so it gives no finer percent. Finer percent groups need the
Coordinating Agent to supply a percent for each row in future.
A row with no accuracy value is ungrouped. It is not presented.

Modes:
1. Packet mode, no decision yet:
       python3 agent.py
   Writes approval_packet.json, approval_packet.md,
   approval_cards.html, decision_template.json, and
   approval_record.json with status awaiting_merchant_decision
   and publish_allowed false.

2. Record mode, with a merchant decision file:
       python3 agent.py --decision-file /path/to/decision.json
   The decision file must use format ovo-merchant-decision 1.0.
   It must name the merchant in approved_by, it must carry a
   session object from the merchant, and it must carry
   the exact diff_fingerprint from the packet. A group counts as
   submitted only when its submitted flag is true. A group that
   is not submitted gives no approval for any row in that group.
   Silence, and a missed deadline, never count as approval.
   A decision may also carry questions, and close_questions.
   A question alone is a valid submission, with no approval.

Binding: the diff fingerprint is a SHA-256 hash of the exact
proposed rows, sorted by product and field. Augment must re-check
that fingerprint against the live diff before it publishes
anything. A new diff needs a new approval record.

Usage:
    python3 agent.py
    python3 agent.py --decision-file decision.json
"""
import argparse
import hashlib
import html as htmlmod
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ENRICH_DIR = ROOT / "stream2-enrichment"
ACCURACY_DIR = ROOT / "accuracy"
COORD_DIR = ROOT / "coordinator"
FRAMEWORK = ROOT / "framework"
sys.path.insert(0, str(FRAMEWORK))

from ovo_agent import OvoAgent, APPROVAL_PHASE  # noqa: E402

SYSTEM_PROMPT = """You are the OvO Merchant Approval Agent. You group
enrichments by accuracy. You present cards. You record only the
merchant's own decision, in aggregate, by group. You never approve
anything yourself. You never publish."""

ALLOWED_FIELDS = {"material_structured", "fit_structured", "returns_structured"}
BANDS = [
    {"band": "95_plus", "label": "95 percent or better", "min": 95.0, "max": 100.0,
     "action": "reject_by_exception",
     "rule": "In a submitted group review, rows the merchant does not reject are approved."},
    {"band": "80_94", "label": "80 to 94 percent", "min": 80.0, "max": 94.999,
     "action": "approve_individual",
     "rule": "The merchant approves each row they want. Rows not explicitly approved are not approved."},
    {"band": "50_79", "label": "50 to 79 percent", "min": 50.0, "max": 79.999,
     "action": "approve_individual",
     "rule": "The merchant approves each row they want. Rows not explicitly approved are not approved."},
]
NOT_CLAIMED = [
    "full MCP, ACP, or UCP compliance",
    "consumer Muse discovery",
    "live payment",
    "production plugin compatibility",
    "any published store change",
    "any merchant decision made by an agent",
    "responsibility or accountability for enrichment accuracy",
]


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def key_of(row):
    return (row.get("product_id"), row.get("field"))


def fingerprint(proposed):
    rows = sorted(
        (
            {
                "product_id": p.get("product_id"),
                "field": p.get("field"),
                "proposed_value": p.get("proposed_value"),
                "current_value": p.get("current_value"),
            }
            for p in proposed
        ),
        key=lambda r: (r["product_id"], r["field"]),
    )
    blob = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def band_for(accuracy):
    if accuracy is None:
        return None
    for band in BANDS:
        if band["min"] <= accuracy <= band["max"]:
            return band
    return None


def row_accuracy(proposal, score_index):
    value = proposal.get("accuracy_percent")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    result = score_index.get(key_of(proposal))
    if result is None:
        return None
    if result.get("accurate") is True:
        return 100.0
    if result.get("accurate") is False:
        return 0.0
    return None


def parse_iso(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def resolve_tenant(diff, scorecard, cli_merchant, cli_store):
    """Tenant IDs, in order: diff, then scorecard, then gaps store
    URL for the store, then a CLI value. No ID is invented. A
    missing merchant ID is kept as None, and recorded as such."""
    gaps_store = None
    gaps_path = ROOT / "stream1-audit" / "gaps.json"
    if gaps_path.exists():
        try:
            gaps_store = json.loads(gaps_path.read_text()).get("store_url")
        except (ValueError, OSError):
            gaps_store = None
    merchant = diff.get("merchant_id") or scorecard.get("merchant_id") or cli_merchant or None
    store = (
        diff.get("store_id") or diff.get("store_url")
        or scorecard.get("store_id") or scorecard.get("store_url")
        or gaps_store or cli_store or None
    )
    if merchant and store:
        status = "full"
    elif store:
        status = "store_only_no_merchant_id"
    else:
        status = "no_tenant_id_supplied"
    return {"merchant_id": merchant, "store_id": store, "tenant_status": status}


def questions_path():
    return HERE / "questions.json"


def load_questions():
    path = questions_path()
    if not path.exists():
        return {"format": "ovo-approval-questions", "version": "1.0",
                "merchant_id": None, "store_id": None, "questions": []}
    try:
        data = json.loads(path.read_text())
    except ValueError:
        return {"format": "ovo-approval-questions", "version": "1.0",
                "merchant_id": None, "store_id": None, "questions": []}
    if not isinstance(data.get("questions"), list):
        data["questions"] = []
    return data


def open_questions(data):
    return [q for q in data.get("questions", []) if q.get("status") == "open"]


def check_gate(diff, scorecard):
    """Own-responsibility checks only. Accuracy correctness is not
    re-checked here, by design. Returns (checks, passed)."""
    checks = []

    def add(name, passed, detail):
        checks.append({"check": name, "passed": passed, "detail": detail})
        return passed

    proposed = [p for p in diff.get("proposals", []) if p.get("status") == "proposed"]
    ok = True
    ok &= add("diff_format",
              diff.get("format") == "ovo-enrichment-diff" and diff.get("version") == "1.0-proposed",
              f"{diff.get('format')} {diff.get('version')}")
    ok &= add("diff_not_published",
              diff.get("published") is False and diff.get("status") == "proposed_only_awaiting_merchant_approval",
              f"published={diff.get('published')} status={diff.get('status')}")
    ok &= add("diff_count_matches",
              diff.get("proposal_count") == len(proposed),
              f"claimed {diff.get('proposal_count')}, actual {len(proposed)}")
    bad_fields = sorted({p.get("field") for p in proposed if p.get("field") not in ALLOWED_FIELDS})
    ok &= add("proposed_fields_allowed",
              not bad_fields,
              f"disallowed fields: {bad_fields}" if bad_fields else "material, fit, returns only")
    bad_rows = [
        p for p in proposed
        if p.get("requires_merchant_approval") is not True
        or p.get("published") is not False
        or not p.get("source_label")
        or not p.get("proposed_value")
    ]
    ok &= add("proposed_rows_require_approval",
              not bad_rows,
              f"{len(bad_rows)} rows fail the approval flags" if bad_rows else "all proposed rows require approval")
    ok &= add("scorecard_format",
              scorecard.get("format") == "ovo-accuracy-scorecard" and scorecard.get("version") == "1.0",
              f"{scorecard.get('format')} {scorecard.get('version')}")
    ok &= add("scorecard_not_published",
              scorecard.get("published") is False,
              f"published={scorecard.get('published')}")
    diff_merchant = diff.get("merchant_id")
    score_merchant = scorecard.get("merchant_id")
    diff_store = diff.get("store_id") or diff.get("store_url")
    score_store = scorecard.get("store_id") or scorecard.get("store_url")
    tenant_conflict = (
        (diff_merchant and score_merchant and diff_merchant != score_merchant)
        or (diff_store and score_store and diff_store != score_store)
    )
    ok &= add("tenant_ids_do_not_conflict",
              not tenant_conflict,
              "diff and scorecard tenant IDs differ" if tenant_conflict else "no tenant conflict in inputs")
    coord_path = COORD_DIR / "coordinator_run.json"
    if coord_path.exists():
        coord = json.loads(coord_path.read_text())
        ok &= add("coordinator_not_published",
                  coord.get("published") is False,
                  f"coordinator published={coord.get('published')} status={coord.get('status')}")
    return checks, ok


def write_record(agent, status, fp, diff, scorecard, groups_data, approved_proposed,
                 approved_corrected, added, rejected, not_approved, excluded, ungrouped,
                 approved_by, decision_file, decided_at,
                 tenant=None, session_info=None, questions_asked=None,
                 questions_closed=None, questions_open=None):
    publishable = len(approved_proposed) + len(approved_corrected) + len(added)
    tenant = tenant or {"merchant_id": None, "store_id": None, "tenant_status": "no_tenant_id_supplied"}
    if session_info and status not in ("invalid_decision", "blocked_gate_failed", "awaiting_merchant_decision"):
        authority = "merchant_session"
    else:
        authority = "none"
    if session_info:
        record_merchant = session_info.get("merchant_id")
        record_store = session_info.get("store_id")
    else:
        record_merchant = tenant.get("merchant_id")
        record_store = tenant.get("store_id")
    record = {
        "format": "ovo-approval-record",
        "version": "1.0",
        "status": status,
        "published": False,
        "diff_fingerprint": fp,
        "diff_source": "stream2-enrichment:enrichment_diff.json ovo-enrichment-diff 1.0-proposed",
        "accuracy_source": "accuracy:accuracy_scorecard.json ovo-accuracy-scorecard 1.0",
        "accuracy_note": (
            "Accuracy values are taken as given. This agent does not "
            "re-check enrichment values, and it does not recompute accuracy."
        ),
        "raci": {
            "responsible_enrichment_and_accuracy": "OvO Enrichment Agent",
            "accountable_enrichment_output": "OvO Coordinating Agent",
            "merchant_approval_agent": "Records merchant decisions only. Not responsible or accountable for enrichment accuracy.",
        },
        "approved_by": approved_by,
        "merchant_id": record_merchant,
        "store_id": record_store,
        "tenant_status": tenant.get("tenant_status"),
        "tenant_note": (
            "Merchant ID is not supplied in the live inputs, so the live packet is store only. "
            "A decision for that packet still needs a session with a store ID that matches the packet."
            if tenant.get("tenant_status") == "store_only_no_merchant_id" else
            "Tenant IDs are checked against the packet when they are supplied."
        ),
        "authority_status": authority,
        "session": session_info,
        "session_note": (
            "Session fields, expiry, revocation flag, and ID match are checked. "
            "No cryptographic signature is verified, because no platform issuer or key is supplied yet."
            if session_info else
            "No merchant session was recorded for this record."
        ),
        "questions_asked_in_this_decision": questions_asked or [],
        "questions_closed_in_this_decision": questions_closed or [],
        "questions_open_after": questions_open or [],
        "decision_file": decision_file,
        "decided_at_utc": decided_at,
        "groups_summary": groups_data,
        "approved_as_proposed": approved_proposed,
        "approved_as_corrected": approved_corrected,
        "added_merchant_supplied": added,
        "rejected_rows": rejected,
        "not_approved_rows": not_approved,
        "excluded_under_50": excluded,
        "ungrouped_no_accuracy": ungrouped,
        "publishable_count": publishable,
        "publish_allowed": status in ("approved_all_presented", "approved_partial"),
        "publish_scope": (
            "Augment may publish only approved_as_proposed as proposed, "
            "approved_as_corrected as the corrected value, and "
            "added_merchant_supplied as the merchant value, and only after "
            "it re-checks that the live diff fingerprint still matches this "
            "record. A new diff needs a new approval record."
            if status in ("approved_all_presented", "approved_partial") else
            "Nothing may be published from this record."
        ),
        "not_claimed": NOT_CLAIMED,
    }
    (HERE / "approval_record.json").write_text(json.dumps(record, indent=2))
    agent.log_step("record_written", f"status {status}, publishable {publishable}",
                   "approval:approval_record.json")
    return record


def packet_row(p, accuracy, band):
    return {
        "product_id": p.get("product_id"),
        "product_name": p.get("product_name"),
        "sku": p.get("sku"),
        "field": p.get("field"),
        "current_value": p.get("current_value"),
        "proposed_value": p.get("proposed_value"),
        "evidence": p.get("evidence"),
        "source_label": p.get("source_label"),
        "accuracy_percent": accuracy,
        "band": band["band"] if band else None,
    }


def main():
    parser = argparse.ArgumentParser(description="OvO Merchant Approval Agent")
    parser.add_argument("--decision-file", default=None,
                        help="Merchant decision file, format ovo-merchant-decision 1.0")
    parser.add_argument("--merchant-id", default=None,
                        help="Merchant ID, used only when inputs do not supply one")
    parser.add_argument("--store-id", default=None,
                        help="Store ID, used only when inputs do not supply one")
    args = parser.parse_args()

    agent = OvoAgent(
        name="OvO Merchant Approval Agent",
        phase=APPROVAL_PHASE,
        system_prompt=SYSTEM_PROMPT,
        workdir=HERE,
    )
    agent.log_step("start", "Merchant Approval Agent run started", "framework:ovo_agent.py")

    diff_path = ENRICH_DIR / "enrichment_diff.json"
    score_path = ACCURACY_DIR / "accuracy_scorecard.json"
    for path in (diff_path, score_path):
        if not path.exists():
            raise SystemExit(f"Missing input: {path}. Run Audit, Enrichment, and Accuracy first.")
    diff = json.loads(diff_path.read_text())
    scorecard = json.loads(score_path.read_text())
    tenant = resolve_tenant(diff, scorecard, args.merchant_id, args.store_id)
    checks, gate_ok = check_gate(diff, scorecard)
    proposed = [p for p in diff.get("proposals", []) if p.get("status") == "proposed"]
    held = [p for p in diff.get("proposals", []) if p.get("status") != "proposed"]
    held_index = {key_of(p): p for p in held}
    score_index = {(r.get("product_id"), r.get("field")): r for r in scorecard.get("results", [])}
    if scorecard.get("proposed_count") != len(proposed):
        agent.log_discrepancy(
            f"Scorecard proposed_count {scorecard.get('proposed_count')} does not match "
            f"diff proposed rows {len(proposed)}",
            kept="rows are grouped only when an accuracy value is found for that row",
        )
    fp = fingerprint(proposed)

    # Group presented rows by accuracy band. Under 50 and ungrouped
    # rows are never presented, by definition.
    groups = []
    excluded = []
    ungrouped = []
    presented_index = {}
    for band in BANDS:
        rows = []
        for p in proposed:
            accuracy = row_accuracy(p, score_index)
            if accuracy is None:
                continue
            if band_for(accuracy) is band:
                row = packet_row(p, accuracy, band)
                rows.append(row)
                presented_index[key_of(p)] = row
        groups.append({
            "band": band["band"],
            "label": band["label"],
            "action": band["action"],
            "rule": band["rule"],
            "presented_count": len(rows),
            "rows": rows,
        })
    for p in proposed:
        accuracy = row_accuracy(p, score_index)
        if accuracy is None:
            ungrouped.append({"product_id": p.get("product_id"), "field": p.get("field")})
        elif accuracy < 50.0:
            excluded.append({"product_id": p.get("product_id"), "field": p.get("field"),
                             "accuracy_percent": accuracy})

    if not gate_ok:
        for name in ("approval_packet.json", "approval_packet.md", "approval_cards.html"):
            path = HERE / name
            if path.exists():
                path.unlink()
        groups_summary = [
            {"band": g["band"], "submitted": False, "presented_count": g["presented_count"],
             "approved_as_proposed": 0, "approved_as_corrected": 0, "rejected": 0, "not_approved": g["presented_count"]}
            for g in groups
        ]
        write_record(agent, "blocked_gate_failed", fp, diff, scorecard, groups_summary,
                     [], [], [], [], [r for g in groups for r in g["rows"]], excluded, ungrouped,
                     None, None, None, tenant=tenant, session_info=None,
                     questions_asked=[], questions_closed=[],
                     questions_open=open_questions(load_questions()))
        agent.write_audit_log(filename="approval_run.json", extra={
            "status": "blocked_gate_failed", "gate_checks": checks, "publish_allowed": False,
            "diff_fingerprint": fp,
        })
        print("Gate closed: blocked_gate_failed. Nothing may be published.")
        for check in checks:
            if not check["passed"]:
                print(f"  FAILED: {check['check']} - {check['detail']}")
        print(f"Record: {HERE / 'approval_record.json'}")
        raise SystemExit(1)

    agent.log_step("gate_checked", f"{sum(1 for c in checks if c['passed'])} of {len(checks)} checks passed",
                   "stream2-enrichment:enrichment_diff.json")

    # Packet mode: prepare, do not approve.
    if args.decision_file is None:
        packet_open = open_questions(load_questions())
        packet = {
            "format": "ovo-approval-packet",
            "version": "1.0",
            "status": "awaiting_merchant_decision",
            "published": False,
            "merchant_id": tenant["merchant_id"],
            "store_id": tenant["store_id"],
            "tenant_status": tenant["tenant_status"],
            "tenant_note": (
                "Store ID comes from the audit store URL. Merchant ID is not supplied in the live inputs, "
                "so a decision for this packet still needs a session with a store ID that matches the packet."
                if tenant["tenant_status"] == "store_only_no_merchant_id" else
                "Tenant IDs are checked against the packet when a decision is recorded."
            ),
            "open_questions": packet_open,
            "diff_fingerprint": fp,
            "diff_source": "stream2-enrichment:enrichment_diff.json ovo-enrichment-diff 1.0-proposed",
            "accuracy_source": "accuracy:accuracy_scorecard.json ovo-accuracy-scorecard 1.0",
            "accuracy_note": (
                "Accuracy values are taken as given. This agent does not "
                "re-check enrichment values, and it does not recompute accuracy."
            ),
            "raci": {
                "responsible_enrichment_and_accuracy": "OvO Enrichment Agent",
                "accountable_enrichment_output": "OvO Coordinating Agent",
                "merchant_approval_agent": "Records merchant decisions only. Not responsible or accountable for enrichment accuracy.",
            },
            "product_count": diff.get("product_count"),
            "total_gaps": diff.get("total_gaps"),
            "proposed_count": len(proposed),
            "presented_count": len(presented_index),
            "excluded_under_50_count": len(excluded),
            "ungrouped_count": len(ungrouped),
            "held_count": len(held),
            "scores_as_given": {
                "native_store_core_score": diff.get("scores_projected", {}).get("native_store_core_score"),
                "projected_core_score_if_proposals_approved": diff.get("scores_projected", {}).get("projected_core_score_if_proposals_approved"),
                "note": "Projected only, as given in the diff. Nothing is published until the merchant approves and Augment runs.",
            },
            "gate_checks": checks,
            "groups": groups,
            "excluded_under_50": excluded,
            "ungrouped_no_accuracy": ungrouped,
            "held_rows": [
                {"product_id": p.get("product_id"), "field": p.get("field"), "status": p.get("status")}
                for p in held
            ],
            "not_claimed": NOT_CLAIMED,
        }
        (HERE / "approval_packet.json").write_text(json.dumps(packet, indent=2))
        lines = [
            "# OvO Merchant Approval Packet",
            "",
            "Nothing in this packet is approved yet. Nothing is published.",
            "",
            f"Store: {tenant['store_id']}.",
            f"Merchant: {tenant['merchant_id'] if tenant['merchant_id'] else 'not supplied'}.",
            f"Tenant status: {tenant['tenant_status']}.",
            f"Open questions: {len(packet_open)}.",
            "",
            f"Presented rows: {len(presented_index)}.",
            f"Rows under 50 percent, not presented: {len(excluded)}.",
            f"Rows with no accuracy value, not presented: {len(ungrouped)}.",
            f"Held rows: {len(held)}.",
            "",
            "Accuracy values are taken as given. This agent does not re-check them.",
            "The Enrichment Agent does the work.",
            "The Coordinator owns the output.",
            "",
        ]
        for g in groups:
            lines.append(f"## Card: {g['label']} ({g['action']})")
            lines.append(g["rule"])
            lines.append("")
            for r in g["rows"]:
                lines.append(
                    f"- {r['product_name']}, {r['field']}: now {r['current_value']}, "
                    f"proposed {r['proposed_value']}. Accuracy: {r['accuracy_percent']} percent."
                )
            lines.append("")
        lines += [
            "The merchant can correct a value.",
            "The merchant can add information for a held row.",
            "Corrections and additions are recorded exactly as given.",
            "They are marked merchant supplied.",
            "Full card edit design comes later.",
            "The decision file supports corrections and additions now.",
            "The merchant can ask a question on a row or a group.",
            "A row with an open question is not approved.",
            "A row with an open question is not rejected.",
            "The merchant can close a question, then decide the row.",
            "",
            "Copy decision_template.json.",
            "Fill approved_by.",
            "Fill the session object with your merchant session.",
            "A typed name alone is not authority.",
            "The session store ID must match this packet.",
            "Submit each group you decide.",
            "In the 95 percent or better group, list rejections only.",
            "Rows not rejected are approved.",
            "In the 80 to 94 and 50 to 79 groups, list each row you approve.",
            "Rows not listed are not approved.",
            "A group that is not submitted gives no approval.",
        ]
        (HERE / "approval_packet.md").write_text("\n".join(lines) + "\n")
        # Visual cards, one per group. Read only for now. Edit fields
        # in cards are later design work, not in this file.
        card_parts = [
            "<!doctype html><html><head><meta charset='utf-8'>",
            "<title>OvO Merchant Approval Cards</title>",
            "<style>body{font-family:Arial,sans-serif;max-width:900px;margin:24px auto;padding:0 16px}"
            ".card{border:1px solid #ccc;border-radius:12px;padding:16px;margin:16px 0}"
            "h2{margin:0 0 8px} li{margin:6px 0}</style></head><body>",
            "<h1>OvO Merchant Approval Cards</h1>",
            "<p>Nothing here is approved yet. Nothing is published.</p>",
            f"<p>Store: {htmlmod.escape(str(tenant['store_id']))}. "
            f"Merchant: {htmlmod.escape(str(tenant['merchant_id'])) if tenant['merchant_id'] else 'not supplied'}. "
            f"Tenant status: {htmlmod.escape(str(tenant['tenant_status']))}.</p>",
            "<p>Accuracy values are taken as given. Card edit fields come later.</p>",
            "<p>Question field: ask a question in the decision file, in the questions list. "
            "A row with an open question is held, not approved and not rejected.</p>",
            f"<p>Open questions: {len(packet_open)}.</p>",
        ]
        for q in packet_open:
            card_parts.append(
                f"<p>Open question {htmlmod.escape(str(q.get('question_id')))}: "
                f"product {htmlmod.escape(str(q.get('product_id')))}, "
                f"field {htmlmod.escape(str(q.get('field')))}: "
                f"{htmlmod.escape(str(q.get('question')))}</p>"
            )
        for g in groups:
            card_parts.append(f"<section class='card'><h2>Card: {htmlmod.escape(g['label'])}</h2>")
            card_parts.append(f"<p>Action: {htmlmod.escape(g['action'])}. {htmlmod.escape(g['rule'])}</p>")
            card_parts.append(f"<p>Rows in this card: {g['presented_count']}</p><ul>")
            for r in g["rows"]:
                card_parts.append(
                    f"<li>{htmlmod.escape(str(r['product_name']))}, {htmlmod.escape(str(r['field']))}: "
                    f"now {htmlmod.escape(str(r['current_value']))}, "
                    f"proposed {htmlmod.escape(str(r['proposed_value']))}. "
                    f"Accuracy: {r['accuracy_percent']} percent.</li>"
                )
            card_parts.append("</ul></section>")
        card_parts.append(f"<p>Rows under 50 percent, not presented: {len(excluded)}.</p>")
        card_parts.append(f"<p>Rows with no accuracy value, not presented: {len(ungrouped)}.</p>")
        card_parts.append("</body></html>")
        (HERE / "approval_cards.html").write_text("\n".join(card_parts))
        template = {
            "format": "ovo-merchant-decision",
            "version": "1.0",
            "diff_fingerprint": fp,
            "approved_by": "",
            "merchant_id": tenant["merchant_id"],
            "store_id": tenant["store_id"],
            "session": {
                "session_id": "",
                "merchant_id": tenant["merchant_id"],
                "store_id": tenant["store_id"],
                "submitted_by": "merchant",
                "expires_at_utc": "",
                "revoked": False,
                "note": (
                    "Fill this from your merchant session. A typed name alone is not authority. "
                    "The session store ID must match the packet store ID. The session merchant ID must match "
                    "the packet merchant ID when the packet has one. An expired or revoked session is rejected. "
                    "A session submitted by an agent is rejected. No signature is verified yet, because no "
                    "platform issuer or key is supplied yet."
                ),
            },
            "questions": [],
            "close_questions": [],
            "note": (
                "Fill approved_by with your name, and fill the session object. Set submitted true for each group you decide. "
                "In the 95 percent or better group, list rejections only. Rows not rejected are approved. "
                "In the 80 to 94 and 50 to 79 groups, list each row you approve. Rows not listed are not approved. "
                "A group that is not submitted gives no approval. Corrections go in corrections, with corrected_value. "
                "Additions go in additions, for a held row only, with added_value from the merchant. "
                "Questions go in questions, with product_id, field, and question. A row with an open question is held. "
                "Close a question in close_questions, with its question_id, then decide the row."
            ),
            "groups": [
                {
                    "band": g["band"],
                    "action": g["action"],
                    "submitted": False,
                    "rows": g["rows"],
                    "rejections": [],
                    "approvals": [],
                    "corrections": [],
                }
                for g in groups
            ],
            "additions": [],
        }
        (HERE / "decision_template.json").write_text(json.dumps(template, indent=2))
        groups_summary = [
            {"band": g["band"], "submitted": False, "presented_count": g["presented_count"],
             "approved_as_proposed": 0, "approved_as_corrected": 0, "rejected": 0, "not_approved": g["presented_count"]}
            for g in groups
        ]
        write_record(agent, "awaiting_merchant_decision", fp, diff, scorecard, groups_summary,
                     [], [], [], [], [r for g in groups for r in g["rows"]], excluded, ungrouped,
                     None, None, None, tenant=tenant, session_info=None,
                     questions_asked=[], questions_closed=[], questions_open=packet_open)
        agent.write_audit_log(filename="approval_run.json", extra={
            "status": "awaiting_merchant_decision", "gate_checks": checks, "publish_allowed": False,
            "diff_fingerprint": fp, "presented_count": len(presented_index),
            "excluded_under_50_count": len(excluded), "ungrouped_count": len(ungrouped),
        })
        print(f"Approval packet ready. Presented {len(presented_index)} rows in {len(groups)} cards.")
        print(f"Excluded under 50 percent: {len(excluded)}. Ungrouped: {len(ungrouped)}. Held: {len(held)}.")
        print("Status: awaiting_merchant_decision. Publish allowed: false.")
        print(f"Packet: {HERE / 'approval_packet.json'}")
        print(f"Cards: {HERE / 'approval_cards.html'}")
        print(f"Template: {HERE / 'decision_template.json'}")
        print("Nothing approved. Nothing published.")
        return

    # Record mode: validate the merchant decision, fail closed on any flaw.
    decision_path = Path(args.decision_file)
    if not decision_path.exists():
        raise SystemExit(f"Decision file not found: {decision_path}")
    decision = json.loads(decision_path.read_text())
    errors = []
    if decision.get("format") != "ovo-merchant-decision" or decision.get("version") != "1.0":
        errors.append(f"unexpected decision format: {decision.get('format')} {decision.get('version')}")
    approved_by = decision.get("approved_by")
    if not approved_by or not isinstance(approved_by, str) or not approved_by.strip():
        errors.append("approved_by is missing or blank")
    if decision.get("diff_fingerprint") != fp:
        errors.append("diff_fingerprint does not match the current packet")

    # R6: a typed name alone is not authority. The session must be
    # from the merchant, for this store, not revoked, not expired.
    # This checks session fields only. No signature is verified yet,
    # because no platform issuer or key is supplied yet.
    session = decision.get("session")
    session_info = None
    if not isinstance(session, dict):
        errors.append("session is missing: a typed name alone is not authority, a merchant session is required")
    else:
        s_merchant = session.get("merchant_id")
        s_store = session.get("store_id")
        s_id = session.get("session_id")
        if not s_merchant or not isinstance(s_merchant, str):
            errors.append("session merchant_id is missing")
        if not s_store or not isinstance(s_store, str):
            errors.append("session store_id is missing")
        if not s_id or not isinstance(s_id, str):
            errors.append("session session_id is missing")
        if session.get("submitted_by") != "merchant":
            errors.append("session submitted_by must be merchant; an agent cannot approve")
        if session.get("revoked") is True:
            errors.append("session is revoked")
        expires = parse_iso(session.get("expires_at_utc"))
        if expires is None:
            errors.append("session expires_at_utc is missing or not a date")
        else:
            ref = parse_iso(decision.get("decided_at_utc")) or datetime.now(timezone.utc)
            if expires <= ref:
                errors.append("session is expired")
        if tenant["merchant_id"] and s_merchant and s_merchant != tenant["merchant_id"]:
            errors.append("session merchant_id does not match the packet merchant_id")
        if tenant["store_id"] and s_store and s_store != tenant["store_id"]:
            errors.append("session store_id does not match the packet store_id")
        for top_key, s_value in (("merchant_id", s_merchant), ("store_id", s_store)):
            top_value = decision.get(top_key)
            if top_value and s_value and top_value != s_value:
                errors.append(f"decision {top_key} does not match the session {top_key}")
        if isinstance(session, dict) and s_merchant and s_store and s_id:
            session_info = {
                "session_id": s_id, "merchant_id": s_merchant, "store_id": s_store,
                "submitted_by": session.get("submitted_by"),
                "expires_at_utc": session.get("expires_at_utc"),
                "revoked": session.get("revoked") is True,
            }

    decision_groups = decision.get("groups")
    if not isinstance(decision_groups, list):
        errors.append("groups list is missing")
        decision_groups = []
    group_by_band = {}
    for entry in decision_groups:
        if not isinstance(entry, dict) or not entry.get("band"):
            errors.append("a group entry is missing its band")
            continue
        if entry["band"] in group_by_band:
            errors.append(f"duplicate group for band {entry['band']}")
        group_by_band[entry["band"]] = entry

    approved_proposed = []
    approved_corrected = []
    rejected = []
    not_approved = []
    groups_summary = []
    any_submitted = False
    for g in groups:
        band = g["band"]
        band_index = {key_of(r): r for r in g["rows"]}
        entry = group_by_band.get(band)
        if entry is None:
            groups_summary.append({"band": band, "submitted": False, "presented_count": len(g["rows"]),
                                   "approved_as_proposed": 0, "approved_as_corrected": 0,
                                   "rejected": 0, "not_approved": len(g["rows"])})
            not_approved.extend(g["rows"])
            continue
        if band not in [b["band"] for b in BANDS] or g["presented_count"] == 0 and entry.get("submitted"):
            errors.append(f"decision for an empty or unknown band: {band}")
        submitted = entry.get("submitted")
        if not isinstance(submitted, bool):
            errors.append(f"submitted for band {band} must be true or false")
            submitted = False
        rejections = entry.get("rejections", [])
        approvals = entry.get("approvals", [])
        corrections = entry.get("corrections", [])
        if not isinstance(rejections, list) or not isinstance(approvals, list) or not isinstance(corrections, list):
            errors.append(f"rejections, approvals, and corrections for band {band} must be lists")
            rejections, approvals, corrections = [], [], []
        if not submitted and (rejections or approvals or corrections):
            errors.append(f"band {band} has decisions but submitted is false")
        if submitted:
            any_submitted = True
        if band == "95_plus" and approvals:
            errors.append("95 percent or better band uses rejections only, not an approvals list")
        seen = set()
        band_rejected = []
        band_corrected = []
        band_approved = []

        def check_key(item, kind):
            if not isinstance(item, dict):
                errors.append(f"{kind} entry in band {band} is not an object")
                return None
            k = (item.get("product_id"), item.get("field"))
            if k in seen:
                errors.append(f"duplicate decision for {k} in band {band}")
            seen.add(k)
            if k not in band_index:
                errors.append(f"decision for a row not in band {band}: {k}")
                return None
            return k

        for item in rejections:
            k = check_key(item, "rejection")
            if k:
                band_rejected.append({"product_id": k[0], "field": k[1],
                                      "proposed_value": band_index[k]["proposed_value"], "band": band})
        for item in corrections:
            k = check_key(item, "correction")
            if k:
                value = item.get("corrected_value")
                if not value or not isinstance(value, str):
                    errors.append(f"correction for {k} is missing corrected_value")
                else:
                    band_corrected.append({"product_id": k[0], "field": k[1],
                                           "proposed_value": band_index[k]["proposed_value"],
                                           "corrected_value": value, "band": band,
                                           "source": "merchant_supplied"})
        for item in approvals:
            k = check_key(item, "approval")
            if k:
                if item.get("corrected_value") is not None:
                    errors.append(f"approval for {k} carries corrected_value; use corrections instead")
                else:
                    band_approved.append({"product_id": k[0], "field": k[1],
                                          "proposed_value": band_index[k]["proposed_value"], "band": band})
        if submitted and band == "95_plus":
            band_approved = [
                {"product_id": r["product_id"], "field": r["field"],
                 "proposed_value": r["proposed_value"], "band": band}
                for r in g["rows"]
                if key_of(r) not in {key_of(x) for x in band_rejected}
                and key_of(r) not in {key_of(x) for x in band_corrected}
            ]
        band_not_approved = [
            r for r in g["rows"]
            if key_of(r) not in {key_of(x) for x in band_approved}
            and key_of(r) not in {key_of(x) for x in band_corrected}
            and key_of(r) not in {key_of(x) for x in band_rejected}
        ] if submitted else list(g["rows"])
        # For a submitted 95 band, not_approved must be empty, by rule.
        # For submitted individual bands, not_approved holds rows neither
        # approved, corrected, nor rejected.
        if not submitted:
            band_approved, band_corrected, band_rejected = [], [], []
            band_not_approved = list(g["rows"])
        approved_proposed.extend(band_approved)
        approved_corrected.extend(band_corrected)
        rejected.extend(band_rejected)
        not_approved.extend(band_not_approved)
        groups_summary.append({"band": band, "submitted": submitted, "presented_count": len(g["rows"]),
                               "approved_as_proposed": len(band_approved),
                               "approved_as_corrected": len(band_corrected),
                               "rejected": len(band_rejected),
                               "not_approved": len(band_not_approved)})

    # R5: questions. A row with an open question is held: it is
    # not approved and not rejected, until the merchant closes the
    # question and decides the row in a later decision. Changes to
    # questions are saved only when the whole decision is valid.
    questions_work = json.loads(json.dumps(load_questions()))
    questions_open_before = open_questions(questions_work)
    questions_asked_new = []
    questions_closed_new = []
    decided_keys = (
        {key_of(x) for x in approved_proposed}
        | {key_of(x) for x in approved_corrected}
        | {key_of(x) for x in rejected}
    )
    questions = decision.get("questions", [])
    if not isinstance(questions, list):
        errors.append("questions must be a list")
        questions = []
    for item in questions:
        if not isinstance(item, dict):
            errors.append("a question entry is not an object")
            continue
        q_text = item.get("question")
        if not q_text or not isinstance(q_text, str) or not q_text.strip():
            errors.append("a question entry is missing question text")
            continue
        q_product = item.get("product_id")
        q_field = item.get("field")
        q_band = item.get("band")
        if not q_product or (not q_field and not q_band):
            errors.append("a question must name a product and a field, or a group band")
            continue
        if q_field:
            q_key = (q_product, q_field)
            if q_key not in presented_index and q_key not in held_index:
                errors.append(f"question for a row not in the packet: {q_key}")
                continue
            if q_key in decided_keys:
                errors.append(f"row {q_key} has a question and a decision in the same file; ask or decide, not both")
                continue
            proposed_value = presented_index[q_key]["proposed_value"] if q_key in presented_index else None
        else:
            proposed_value = None
        q_id = f"Q{len(questions_work['questions']) + 1:03d}"
        entry = {
            "question_id": q_id, "product_id": q_product, "field": q_field, "band": q_band,
            "question": q_text.strip(), "proposed_value": proposed_value,
            "status": "open", "asked_at_utc": decision.get("decided_at_utc") or now_utc(),
            "asked_by_merchant_id": session_info["merchant_id"] if session_info else None,
            "store_id": tenant["store_id"],
        }
        questions_work["questions"].append(entry)
        questions_asked_new.append(entry)
    close_questions = decision.get("close_questions", [])
    if not isinstance(close_questions, list):
        errors.append("close_questions must be a list")
        close_questions = []
    closed_ids = set()
    for item in close_questions:
        if not isinstance(item, dict) or not item.get("question_id"):
            errors.append("a close_questions entry is missing question_id")
            continue
        q_id = item["question_id"]
        found = next((q for q in questions_work["questions"]
                      if q.get("question_id") == q_id and q.get("status") == "open"), None)
        if found is None:
            errors.append(f"close for a question that is not open: {q_id}")
            continue
        found["status"] = "closed"
        found["closed_at_utc"] = decision.get("decided_at_utc") or now_utc()
        found["closed_by_merchant_id"] = session_info["merchant_id"] if session_info else None
        closed_ids.add(q_id)
        questions_closed_new.append({"question_id": q_id, "product_id": found.get("product_id"),
                                     "field": found.get("field")})
    for key in decided_keys:
        still_open = [q for q in questions_open_before
                      if (q.get("product_id"), q.get("field")) == key
                      and q.get("question_id") not in closed_ids]
        if still_open:
            errors.append(f"row {key} has an open question; close it first, then decide the row")
    if questions_asked_new or questions_closed_new:
        any_submitted = True

    # Additions: merchant supplied values for held rows only.
    added = []
    additions = decision.get("additions", [])
    if not isinstance(additions, list):
        errors.append("additions must be a list")
        additions = []
    seen_add = set()
    for item in additions:
        if not isinstance(item, dict):
            errors.append("an addition entry is not an object")
            continue
        k = (item.get("product_id"), item.get("field"))
        if k in seen_add:
            errors.append(f"duplicate addition for {k}")
        seen_add.add(k)
        if k not in held_index:
            errors.append(f"addition for a row that is not a held gap: {k}")
            continue
        value = item.get("added_value")
        if not value or not isinstance(value, str):
            errors.append(f"addition for {k} is missing added_value")
            continue
        added.append({"product_id": k[0], "field": k[1], "added_value": value,
                      "held_status": held_index[k].get("status"), "source": "merchant_supplied"})
    if additions:
        any_submitted = True
    if not any_submitted:
        errors.append("no group submitted and no additions given")

    if errors:
        write_record(agent, "invalid_decision", fp, diff, scorecard, groups_summary,
                     [], [], [], [], [r for g in groups for r in g["rows"]], excluded, ungrouped,
                     approved_by.strip() if isinstance(approved_by, str) and approved_by.strip() else None,
                     decision_path.name, None, tenant=tenant, session_info=session_info,
                     questions_asked=[], questions_closed=[],
                     questions_open=questions_open_before)
        agent.write_audit_log(filename="approval_run.json", extra={
            "status": "invalid_decision", "gate_checks": checks, "publish_allowed": False,
            "diff_fingerprint": fp, "decision_errors": errors,
        })
        print("Invalid decision. Nothing approved. Nothing may be published.")
        for error in errors:
            print(f"  - {error}")
        print(f"Record: {HERE / 'approval_record.json'}")
        raise SystemExit(1)

    presented_total = len(presented_index)
    approved_total = len(approved_proposed) + len(approved_corrected)
    if presented_total and approved_total == presented_total:
        status = "approved_all_presented"
    elif approved_total == 0 and added:
        status = "approved_partial"
    elif approved_total == 0 and len(rejected) == presented_total and presented_total:
        status = "rejected_all_presented"
    elif approved_total == 0 and (questions_asked_new or questions_closed_new):
        status = "questions_recorded"
    elif approved_total == 0:
        status = "no_rows_approved"
    else:
        status = "approved_partial"
    decided_at = decision.get("decided_at_utc") or now_utc()
    if questions_asked_new or questions_closed_new:
        questions_work["merchant_id"] = tenant["merchant_id"]
        questions_work["store_id"] = tenant["store_id"]
        questions_path().write_text(json.dumps(questions_work, indent=2))
    questions_open_after = open_questions(questions_work)
    write_record(agent, status, fp, diff, scorecard, groups_summary,
                 approved_proposed, approved_corrected, added, rejected, not_approved,
                 excluded, ungrouped, approved_by.strip(), decision_path.name, decided_at,
                 tenant=tenant, session_info=session_info,
                 questions_asked=questions_asked_new, questions_closed=questions_closed_new,
                 questions_open=questions_open_after)
    agent.write_audit_log(filename="approval_run.json", extra={
        "status": status, "gate_checks": checks,
        "publish_allowed": status in ("approved_all_presented", "approved_partial"),
        "diff_fingerprint": fp, "approved_count": approved_total, "added_count": len(added),
        "rejected_count": len(rejected),
    })
    print(f"Decision recorded: {status}. Approved as proposed {len(approved_proposed)}, "
          f"as corrected {len(approved_corrected)}, added {len(added)}, rejected {len(rejected)}, "
          f"questions asked {len(questions_asked_new)}, questions closed {len(questions_closed_new)}, "
          f"questions open {len(questions_open_after)}.")
    print(f"Merchant ID from session: {session_info['merchant_id'] if session_info else None}. "
          f"Store: {tenant['store_id']}. Tenant status: {tenant['tenant_status']}." )
    print(f"Publish allowed: {status in ('approved_all_presented', 'approved_partial')} "
          "(approved rows only, after Augment re-checks the fingerprint).")
    print(f"Record: {HERE / 'approval_record.json'}")
    print("This agent did not publish anything. Augment publishes, if it runs.")


if __name__ == "__main__":
    main()
