#!/usr/bin/env python3
"""Merchant approval screen and decision recording.

The merchant sees the enriched data in one review screen, most
likely a pop-up box, grouped the way the Merchant Approval
Agent groups it: one card per accuracy band. The merchant
approves a group. Approval differs by group, but that stays in
the background and does not change the flow. Silence never
counts as approval: a group that is not submitted gives no
approval for any row in that group.

Only a recorded merchant approval lets the Plugin Agent
publish. The record this module writes is the approval record
format 1.0, with one addition: an approved_rows list, which is
what the Plugin Agent's augment runner reads. The Merchant
Approval Agent's own record did not carry that list, so the
chain from a recorded decision to a publish was broken. This
module writes it, and the approval agent was given the same
field, so both paths produce one shape.

Rows come from the enrichment diff only. Accuracy travels
inside the diff. There is no Accuracy Agent and no accuracy
scorecard anywhere here.
"""
import html as htmlmod
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent


def _load_approval_agent():
    """Load the Merchant Approval Agent module by file path, so
    this site reuses its banding and fingerprint, not a copy."""
    path = REPO_ROOT / "ovo-approval-agent" / "approval" / "agent.py"
    spec = importlib.util.spec_from_file_location("ovo_approval_agent", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_APPROVAL = None


def approval_agent():
    global _APPROVAL
    if _APPROVAL is None:
        _APPROVAL = _load_approval_agent()
    return _APPROVAL


def build_packet(diff):
    """Group the diff proposals into the approval packet, one
    card per accuracy band. Rows under 50 percent and rows with
    no accuracy value are never presented."""
    agent = approval_agent()
    proposed = list(diff.get("proposals", []))
    fingerprint = agent.fingerprint(proposed)
    groups = []
    presented_index = {}
    excluded = []
    ungrouped = []
    for band in agent.BANDS:
        rows = []
        for p in proposed:
            accuracy = agent.row_accuracy(p)
            if accuracy is None:
                continue
            if agent.band_for(accuracy) is band:
                row = agent.packet_row(p, accuracy, band)
                rows.append(row)
                presented_index[agent.key_of(p)] = row
        groups.append({
            "band": band["band"],
            "label": band["label"],
            "action": band["action"],
            "rule": band["rule"],
            "presented_count": len(rows),
            "rows": rows,
        })
    for p in proposed:
        accuracy = agent.row_accuracy(p)
        if accuracy is None:
            ungrouped.append({"product_id": p.get("product_id"),
                              "field": p.get("field")})
        elif accuracy < 50.0:
            excluded.append({"product_id": p.get("product_id"),
                             "field": p.get("field"),
                             "accuracy_percent": accuracy})
    store_id = None
    merchant_id = None
    if isinstance(diff.get("merchant"), dict):
        merchant_id = diff["merchant"].get("merchant_id")
        store_id = diff["merchant"].get("store_id")
    if not store_id:
        store_id = diff.get("store_url") or "store"
    return {
        "format": "ovo-approval-packet",
        "version": "1.0",
        "status": "awaiting_merchant_decision",
        "published": False,
        "merchant_id": merchant_id,
        "store_id": store_id,
        "diff_fingerprint": fingerprint,
        "diff_source": "ovo-enrichment-agent:enrichment_diff_live.json"
                       " ovo-enrichment-diff 5.0-live",
        "accuracy_source": "enrichment diff: accuracy_percent or"
                           " prd_accuracy_band on each row;"
                           " no separate scorecard",
        "product_count": diff.get("product_count"),
        "proposed_count": len(proposed),
        "presented_count": len(presented_index),
        "excluded_under_50_count": len(excluded),
        "ungrouped_count": len(ungrouped),
        "groups": groups,
        "excluded_under_50": excluded,
        "ungrouped_no_accuracy": ungrouped,
    }


def _row_html(row, band):
    product = htmlmod.escape(str(row.get("product_name") or
                                 row.get("product_id") or ""))
    field = htmlmod.escape(str(row.get("field") or ""))
    now = htmlmod.escape(str(row.get("current_value") or ""))
    proposed = htmlmod.escape(str(row.get("proposed_value") or ""))
    accuracy = row.get("accuracy_percent")
    key = f"{row.get('product_id')}:{row.get('field')}"
    if band == "95_plus":
        control = (f'<label><input type="checkbox" name="reject"'
                   f' value="{htmlmod.escape(key)}"> Reject</label>')
    else:
        control = (f'<label><input type="checkbox" name="approve"'
                   f' value="{htmlmod.escape(key)}"> Approve</label>')
    return (f"<tr><td>{product}</td><td>{field}</td><td>{now}</td>"
            f"<td>{proposed}</td><td>{accuracy}</td><td>{control}</td></tr>")


def render_review_html(packet, run_key):
    """One review screen: 62 rows in one screen, grouped by
    band, in a pop-up box. Each group card shows its rule and
    its rows, and submits on its own. Nothing is approved until
    the merchant submits a group."""
    agent = approval_agent()
    total = packet.get("presented_count", 0)
    store = htmlmod.escape(str(packet.get("store_id") or ""))
    cards = []
    for group in packet.get("groups", []):
        band = group["band"]
        label = htmlmod.escape(group["label"])
        rule = htmlmod.escape(group["rule"])
        count = group["presented_count"]
        if count == 0:
            body = "<p>No rows in this group.</p>"
        else:
            rows = "".join(_row_html(r, band) for r in group["rows"])
            body = (
                "<table><thead><tr><th>Product</th><th>Field</th>"
                "<th>Now</th><th>Proposed</th><th>Accuracy</th>"
                "<th>Your call</th></tr></thead><tbody>"
                f"{rows}</tbody></table>")
        cards.append(
            f'<section class="card" data-band="{htmlmod.escape(band)}">'
            f"<h2>{label} &mdash; {count} rows</h2><p>{rule}</p>{body}"
            f'<button type="submit">Submit this group</button>'
            f"</section>")
    _ = agent  # banding is reused by build_packet; kept for parity.
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>OvO review: {store}</title>
<link rel="stylesheet" href="/static/styles.css">
</head>
<body>
<div class="modal" role="dialog" aria-label="Review enrichment">
<h1>Review your store fixes</h1>
<p>Store: {store}. {total} rows to review. Nothing is approved
until you submit a group. A group you do not submit approves
nothing.</p>
<form id="review-form" data-run-key="{htmlmod.escape(run_key)}">
{''.join(cards)}
</form>
<p class="note">Rows under 50 percent are never shown. They are
not approved and not published.</p>
</div>
<script src="/static/review.js"></script>
</body>
</html>
"""


def _parse_iso(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def record_decision(store, session, packet, group_inputs, approved_by,
                    decided_at=None, run_key=""):
    """Record a merchant decision. group_inputs is a list of
    per-group entries: band, submitted, approvals, rejections,
    corrections. Returns (record, None) or (None, errors).
    Silence is not approval: a group that is not submitted
    approves none of its rows."""
    agent = approval_agent()
    errors = []
    decided_at = decided_at or datetime.now(timezone.utc).isoformat() \
        .replace("+00:00", "Z")
    if not approved_by or not isinstance(approved_by, str) \
            or not approved_by.strip():
        errors.append("approved_by is missing or blank")
    if packet.get("diff_fingerprint") is None:
        errors.append("packet has no diff fingerprint")
    # The session is the authority. A typed name alone is not.
    if not isinstance(session, dict):
        errors.append("session is missing: a typed name alone is not"
                      " authority, a merchant session is required")
        session = {}
    if session.get("submitted_by") != "merchant":
        errors.append("session submitted_by must be merchant;"
                      " an agent cannot approve")
    if session.get("revoked") is True:
        errors.append("session is revoked")
    expires = _parse_iso(session.get("expires_at_utc"))
    ref = _parse_iso(decided_at) or datetime.now(timezone.utc)
    if expires is None:
        errors.append("session expires_at_utc is missing or not a date")
    elif expires <= ref:
        errors.append("session is expired")
    if packet.get("merchant_id") and session.get("merchant_id") \
            and session["merchant_id"] != packet["merchant_id"]:
        errors.append("session merchant_id does not match the packet"
                      " merchant_id")
    if packet.get("store_id") and session.get("store_id") \
            and session["store_id"] != packet["store_id"]:
        errors.append("session store_id does not match the packet store_id")
    if not session.get("merchant_id") or not session.get("store_id") \
            or not session.get("session_id"):
        errors.append("session is missing merchant_id, store_id,"
                      " or session_id")

    groups = packet.get("groups", [])
    group_by_band = {}
    if not isinstance(group_inputs, list):
        errors.append("groups list is missing")
        group_inputs = []
    for entry in group_inputs:
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
    for group in groups:
        band = group["band"]
        band_index = {agent.key_of(r): r for r in group["rows"]}
        entry = group_by_band.get(band)
        if entry is None:
            groups_summary.append({
                "band": band, "submitted": False,
                "presented_count": len(group["rows"]),
                "approved_as_proposed": 0, "approved_as_corrected": 0,
                "rejected": 0, "not_approved": len(group["rows"])})
            not_approved.extend(group["rows"])
            continue
        submitted = entry.get("submitted")
        if not isinstance(submitted, bool):
            errors.append(f"submitted for band {band} must be true or false")
            submitted = False
        rejections = entry.get("rejections", [])
        approvals = entry.get("approvals", [])
        corrections = entry.get("corrections", [])
        if not isinstance(rejections, list) \
                or not isinstance(approvals, list) \
                or not isinstance(corrections, list):
            errors.append(f"rejections, approvals, and corrections for"
                          f" band {band} must be lists")
            rejections, approvals, corrections = [], [], []
        if not submitted and (rejections or approvals or corrections):
            errors.append(f"band {band} has decisions but submitted"
                          f" is false")
        if submitted:
            any_submitted = True
        if band == "95_plus" and approvals:
            errors.append("95 percent or better band uses rejections"
                          " only, not an approvals list")
        seen = set()
        band_rejected = []
        band_corrected = []
        band_approved = []

        def check_key(item, kind):
            if not isinstance(item, dict):
                errors.append(f"{kind} entry in band {band} is not"
                              f" an object")
                return None
            key = (item.get("product_id"), item.get("field"))
            if key in seen:
                errors.append(f"duplicate decision for {key} in"
                              f" band {band}")
            seen.add(key)
            if key not in band_index:
                errors.append(f"decision for a row not in band {band}:"
                              f" {key}")
                return None
            return key

        for item in rejections:
            key = check_key(item, "rejection")
            if key:
                band_rejected.append({
                    "product_id": key[0], "field": key[1],
                    "proposed_value": band_index[key]["proposed_value"],
                    "band": band})
        for item in corrections:
            key = check_key(item, "correction")
            if key:
                value = item.get("corrected_value")
                if not value or not isinstance(value, str):
                    errors.append(f"correction for {key} is missing"
                                  f" corrected_value")
                else:
                    band_corrected.append({
                        "product_id": key[0], "field": key[1],
                        "proposed_value":
                            band_index[key]["proposed_value"],
                        "corrected_value": value, "band": band,
                        "source": "merchant_supplied"})
        for item in approvals:
            key = check_key(item, "approval")
            if key:
                if item.get("corrected_value") is not None:
                    errors.append(f"approval for {key} carries"
                                  f" corrected_value; use corrections"
                                  f" instead")
                else:
                    band_approved.append({
                        "product_id": key[0], "field": key[1],
                        "proposed_value":
                            band_index[key]["proposed_value"],
                        "band": band})
        if submitted and band == "95_plus":
            rejected_keys = {agent.key_of(x) for x in band_rejected}
            corrected_keys = {agent.key_of(x) for x in band_corrected}
            band_approved = [{
                "product_id": r["product_id"], "field": r["field"],
                "proposed_value": r["proposed_value"], "band": band}
                for r in group["rows"]
                if agent.key_of(r) not in rejected_keys
                and agent.key_of(r) not in corrected_keys]
        band_not_approved = [
            r for r in group["rows"]
            if agent.key_of(r) not in {agent.key_of(x)
                                       for x in band_approved}
            and agent.key_of(r) not in {agent.key_of(x)
                                        for x in band_corrected}
            and agent.key_of(r) not in {agent.key_of(x)
                                        for x in band_rejected}
        ] if submitted else list(group["rows"])
        if not submitted:
            band_approved, band_corrected, band_rejected = [], [], []
            band_not_approved = list(group["rows"])
        approved_proposed.extend(band_approved)
        approved_corrected.extend(band_corrected)
        rejected.extend(band_rejected)
        not_approved.extend(band_not_approved)
        groups_summary.append({
            "band": band, "submitted": submitted,
            "presented_count": len(group["rows"]),
            "approved_as_proposed": len(band_approved),
            "approved_as_corrected": len(band_corrected),
            "rejected": len(band_rejected),
            "not_approved": len(band_not_approved)})

    additions = []
    for entry in group_inputs:
        for item in entry.get("additions", []) or []:
            errors.append("addition for a row that is not a held gap:"
                          " the version 5 shape carries no held rows")
    if not any_submitted:
        errors.append("no group submitted and no additions given")
    if errors:
        return None, errors

    presented_total = packet.get("presented_count", 0)
    approved_total = len(approved_proposed) + len(approved_corrected)
    if presented_total and approved_total == presented_total:
        status = "approved_all_presented"
    elif approved_total == 0 and len(rejected) == presented_total \
            and presented_total:
        status = "rejected_all_presented"
    elif approved_total == 0:
        status = "no_rows_approved"
    else:
        status = "approved_partial"
    approved_rows = []
    for row in approved_proposed:
        approved_rows.append({"product_id": row["product_id"],
                              "field": row["field"]})
    for row in approved_corrected:
        approved_rows.append({"product_id": row["product_id"],
                              "field": row["field"],
                              "corrected_value": row["corrected_value"]})
    for row in additions:
        approved_rows.append({"product_id": row["product_id"],
                              "field": row["field"],
                              "added_value": row["added_value"]})
    session_info = {
        "session_id": session.get("session_id"),
        "merchant_id": session.get("merchant_id"),
        "store_id": session.get("store_id"),
        "submitted_by": session.get("submitted_by"),
        "expires_at_utc": session.get("expires_at_utc"),
        "revoked": session.get("revoked") is True,
    }
    record = {
        "format": "ovo-approval-record",
        "version": "1.0",
        "status": status,
        "published": False,
        "diff_fingerprint": packet["diff_fingerprint"],
        "diff_source": packet.get("diff_source"),
        "accuracy_source": packet.get("accuracy_source"),
        "accuracy_note": "Accuracy values are taken as given. This"
                         " agent does not re-check enrichment values,"
                         " and it does not recompute accuracy.",
        "approved_by": approved_by.strip(),
        "merchant_id": session.get("merchant_id"),
        "store_id": session.get("store_id"),
        "authority_status": "merchant_session",
        "session": session_info,
        "decided_at_utc": decided_at,
        "groups_summary": groups_summary,
        "approved_as_proposed": approved_proposed,
        "approved_as_corrected": approved_corrected,
        "added_merchant_supplied": additions,
        "rejected_rows": rejected,
        "not_approved_rows": not_approved,
        "excluded_under_50": packet.get("excluded_under_50", []),
        "ungrouped_no_accuracy": packet.get("ungrouped_no_accuracy", []),
        "publishable_count": len(approved_rows),
        "approved_rows": approved_rows,
        "publish_allowed": status in ("approved_all_presented",
                                      "approved_partial"),
        "publish_scope": (
            "Augment may publish only approved_as_proposed as"
            " proposed, approved_as_corrected as the corrected"
            " value, and added_merchant_supplied as the merchant"
            " value, and only after it re-checks that the live"
            " diff fingerprint still matches this record. A new"
            " diff needs a new approval record."
            if status in ("approved_all_presented", "approved_partial")
            else "Nothing may be published from this record."),
    }
    decision = {
        "format": "ovo-merchant-decision",
        "version": "1.0",
        "approved_by": approved_by.strip(),
        "diff_fingerprint": packet["diff_fingerprint"],
        "merchant_id": session.get("merchant_id"),
        "store_id": session.get("store_id"),
        "session": session_info,
        "groups": group_inputs,
        "decided_at_utc": decided_at,
    }
    store.save_decision(run_key, packet["diff_fingerprint"],
                        decision, record, decided_at, approved_by.strip())
    return record, None


def publish_allowed(record):
    """Only a recorded merchant approval lets the Plugin Agent
    publish. Silence never counts: no approved rows means no
    publish, whatever the status says."""
    if not isinstance(record, dict):
        return False
    if record.get("status") not in ("approved_all_presented",
                                    "approved_partial"):
        return False
    return bool(record.get("approved_rows"))
