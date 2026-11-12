#!/usr/bin/env python3
"""OvO runner. It runs the agents, in order. It does no agent work itself.

Production flow only, in this order:
1. Audit
2. Enrichment, version 5, 62-row shape, from the live store
3. Merchant Approval, packet mode by default, then pause
4. Publish to Plugin, only after a merchant decision, dry run only here

There is no Accuracy stage. The Enrichment Agent works out accuracy
as part of its own work and passes the drafts, with accuracy, to the
Merchant Approval Agent. Accuracy travels inside the enrichment diff,
as accuracy_percent on a row, or as prd_accuracy_band.

The 62-row shape flows through unchanged: Enrichment writes it,
Approval reads it, Plugin writes it. Nothing here converts between
the old 36-row shape and the 62-row shape.

Run state lives in a database, through store.py, not in loose files.
A host restart loses no run. Each run has an idempotency key
(--run-key). A retry with the same key skips stages that already
completed with the same input and output, and never publishes twice
or bills twice: the plugin stage checks the recorded publish attempt
for the key before it spawns anything.

Rules that never change in this file:
- The store address is required. There is no default store.
- No scheduled check is set here. A check needs a merchant
  requirement and approval, given outside this file.
- The runner never approves anything. Only a merchant can approve.
- The runner never publishes on its own. A pause means stop.
- A failed check means stop. The next stage never runs.
- One store at a time. No packet holds rows from more than one store.
- No key is stored in code or in a log. Meta calls go through
  meta_client.py, which reads a key from the environment on a
  host, or the local helper on this machine.

Usage:
    python3 runner.py --store-url https://example.com/shop
    python3 runner.py --store-url https://example.com/shop --skip-spark
    python3 runner.py --store-url https://example.com/shop --decision-file decision.json
    python3 runner.py --store-url https://example.com/shop --run-key my-run-1

Without a decision file, Approval runs in packet mode and the
runner pauses. The plugin stage is not started. Nothing is
published. That pause is a normal stop, not an error.

With a decision file, the file must come from the merchant only.
Approval checks the session, the fingerprint, and the store.
If publish is allowed, the plugin stage runs in dry run mode
only in this build. Live post stays blocked, because token auth
on WordPress is untested and the plugin is not installed on a
real store. See the production plan for what is still open.

Run records live in ovo_runs.db next to this file, unless --db
names another file. Export a run as JSON with:
    python3 store.py --db ovo_runs.db export --run-key my-run-1
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("OVO_REPO_ROOT") or HERE.parent)
sys.path.insert(0, str(HERE))

from store import RunStore  # noqa: E402


class RunnerFailed(Exception):
    """A gate failed. Stop. Do not run the next stage."""


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def slug_for_store(store_url):
    """Make a safe folder name from a store address. No invention."""
    parsed = urllib.parse.urlparse(store_url)
    raw = (parsed.netloc + parsed.path).strip("/")
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    if not slug:
        raise RunnerFailed(f"Cannot make a merchant folder from {store_url}")
    return slug


def load_json(path, label):
    if not path.exists():
        raise RunnerFailed(f"{label} output missing: {path}")
    try:
        return json.loads(path.read_text())
    except ValueError as exc:
        raise RunnerFailed(f"{label} output is not valid JSON: {path}: {exc}")


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def hash_file(path):
    return hash_bytes(path.read_bytes())


def fingerprint_of(proposed):
    """Exact fingerprint used by Approval and by the plugin stage.
    Version 5 rows carry new_value and old_value, not proposed_value
    and current_value. Sort by product_id, then field, with the
    values as given. Product IDs sort as text, so a number order
    difference cannot change the fingerprint."""
    rows = sorted(
        (
            {
                "product_id": p.get("product_id"),
                "field": p.get("field"),
                "new_value": p.get("new_value"),
                "old_value": p.get("old_value"),
            }
            for p in proposed
        ),
        key=lambda r: (str(r["product_id"]), r["field"]),
    )
    blob = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def same_store(left, right):
    return (left or "").rstrip("/") == (right or "").rstrip("/")


def run_flow(store_url, decision_file=None, skip_spark=False,
             run_key=None, db_path=None, repo_root=None):
    """Run the production flow once. Returns the run result dict.
    Raises RunnerFailed when a gate fails. All run state is recorded
    in the store, so a retry with the same run key resumes safely."""
    repo_root = Path(repo_root or REPO_ROOT)
    run_key = run_key or uuid.uuid4().hex
    db_path = Path(db_path or HERE / "ovo_runs.db")
    started = datetime.now(timezone.utc)
    merchant_slug = slug_for_store(store_url)
    decision_path = Path(decision_file) if decision_file else None
    if decision_path is not None and not decision_path.exists():
        raise RunnerFailed(f"Decision file not found: {decision_path}")

    audit_dir = repo_root / "ovo-audit-agent" / "audit"
    enrich_dir = repo_root / "ovo-enrichment-agent"
    approval_dir = repo_root / "ovo-approval-agent" / "approval"
    plugin_dir = repo_root / "ovo-plugin-agent"

    steps = []

    def log(step, detail, source=None, passed=True):
        entry = {
            "at_utc": now_utc(),
            "step": step,
            "detail": detail,
            "source": source,
            "passed": passed,
        }
        steps.append(entry)
        print(f"{step}: {detail}")
        return entry

    result = {
        "runner": "OvO runner, production flow only",
        "flow": ["Audit", "Enrichment", "Merchant Approval", "Plugin"],
        "store_url": store_url,
        "merchant_slug": merchant_slug,
        "run_key": run_key,
        "started_at_utc": started.isoformat(),
        "published": False,
        "plugin_spawned": False,
        "publish_allowed": False,
        "status": "failed",
    }

    store = RunStore(db_path)
    try:
        run = store.create_or_resume_run(run_key, store_url, merchant_slug,
                                         started.isoformat())
        if run.get("status") in ("paused_awaiting_merchant_decision",
                                 "plugin_dry_run_only") and run.get("result_json"):
            # A finished run with this key, replayed without a new
            # decision, returns its recorded result. Nothing runs
            # again, nothing publishes again.
            if decision_path is None:
                recorded = json.loads(run["result_json"])
                recorded["resumed_from_store"] = True
                print(f"Run {run_key} already finished with status "
                      f"{recorded.get('status')}. Recorded result returned. "
                      "Nothing ran again. Nothing published again.")
                return recorded

        def run_stage(name, command, cwd, output_path, input_hash):
            """Spawn one stage, unless the store already holds a
            completed run of it with the same input and output."""
            existing = store.get_stage(run_key, name)
            if (existing and existing.get("status") == "completed"
                    and existing.get("input_hash") == input_hash
                    and output_path.exists()
                    and hash_file(output_path) == existing.get("output_hash")):
                log(f"stage_skipped_{name}",
                    "already completed for this run key with the same input and output",
                    passed=True)
                return existing.get("output")
            log(f"spawn_{name}", " ".join(command))
            proc = subprocess.run(command, cwd=cwd, capture_output=True,
                                  text=True, timeout=900)
            if proc.stdout:
                print(proc.stdout, end="")
            if proc.returncode != 0:
                if proc.stderr:
                    print(proc.stderr, file=sys.stderr)
                store.record_stage(run_key, name, "failed", None, None, now_utc(),
                                input_hash=input_hash)
                log(f"agent_failed_{name}", f"exit {proc.returncode}", passed=False)
                raise RunnerFailed(f"Stage {name} failed with exit {proc.returncode}.")
            log(f"agent_done_{name}", f"exit {proc.returncode}")
            return None

        # 1. Audit. This agent does the audit work. The runner does not.
        audit_input = hash_bytes(f"{store_url}|skip_spark={skip_spark}".encode())
        audit_out = audit_dir / "gaps.json"
        skipped = run_stage("Audit", [sys.executable, str(audit_dir / "agent.py"),
                                      "--store-url", store_url] +
                            (["--skip-spark"] if skip_spark else []),
                            audit_dir, audit_out, audit_input)
        if skipped is None:
            gaps = load_json(audit_out, "Audit")
            if gaps.get("format") != "ovo-gap-list" or gaps.get("version") != "1.0":
                raise RunnerFailed(f"Unexpected gap format: {gaps.get('format')} {gaps.get('version')}")
            if not same_store(gaps.get("store_url"), store_url):
                raise RunnerFailed(
                    f"Audit store {gaps.get('store_url')} does not match {store_url}")
            scorecard_path = audit_dir / "scorecard.json"
            scorecard = load_json(scorecard_path, "Audit scorecard") if scorecard_path.exists() else None
            audit_output = {"gaps": gaps, "scorecard": scorecard}
            store.record_stage(run_key, "Audit", "completed", hash_file(audit_out),
                               audit_output, now_utc(), input_hash=audit_input)
        else:
            audit_output = skipped
            gaps = audit_output["gaps"]
        log("audit_checked",
            f"{gaps.get('product_count')} products, {gaps.get('gap_count_total')} gaps",
            "ovo-audit-agent/audit:gaps.json")

        # 2. Enrichment, version 5. It takes the store address and
        # writes the 62-row diff. No Accuracy stage follows it.
        enrich_input = hash_bytes(store_url.encode())
        enrich_out = enrich_dir / "enrichment_diff_live.json"
        skipped = run_stage("Enrichment", [sys.executable, str(enrich_dir / "agent.py"),
                                           "--store-url", store_url],
                            enrich_dir, enrich_out, enrich_input)
        if skipped is None:
            diff = load_json(enrich_out, "Enrichment")
            if diff.get("format") != "ovo-enrichment-diff" or diff.get("version") != "5.0-live":
                raise RunnerFailed(f"Unexpected diff format: {diff.get('format')} {diff.get('version')}")
            if diff.get("published") is not False:
                raise RunnerFailed("Enrichment is marked published. This runner forbids that.")
            if diff.get("status") != "proposed_only_awaiting_merchant_approval":
                raise RunnerFailed(f"Unexpected enrichment status: {diff.get('status')}")
            if diff.get("proposal_count") != len(diff.get("proposals", [])):
                raise RunnerFailed(
                    f"Enrichment count {diff.get('proposal_count')} does not match "
                    f"actual rows {len(diff.get('proposals', []))}"
                )
            if diff.get("product_count") != gaps.get("product_count"):
                raise RunnerFailed(
                    f"Enrichment products {diff.get('product_count')} do not match "
                    f"audit products {gaps.get('product_count')}"
                )
            if not same_store(diff.get("store_url"), store_url):
                raise RunnerFailed(
                    f"Enrichment store {diff.get('store_url')} does not match {store_url}")
            store.record_stage(run_key, "Enrichment", "completed", hash_file(enrich_out),
                               diff, now_utc(), input_hash=enrich_input)
        else:
            diff = skipped
        proposed = diff.get("proposals", [])
        log("enrichment_checked",
            f"{len(proposed)} proposals, version 5.0-live, published False",
            "ovo-enrichment-agent:enrichment_diff_live.json")

        # 3. Merchant Approval. Packet mode by default. Then pause.
        if decision_path is not None:
            approval_input = hash_bytes(decision_path.read_bytes())
        else:
            approval_input = hash_bytes(b"packet")
        approval_out = approval_dir / "approval_record.json"
        skipped = run_stage("Merchant_Approval",
                            [sys.executable, str(approval_dir / "agent.py")] +
                            (["--decision-file", str(decision_path)] if decision_path else []),
                            approval_dir, approval_out, approval_input)
        if skipped is None:
            record = load_json(approval_out, "Merchant Approval")
            if record.get("format") != "ovo-approval-record" or record.get("version") != "1.0":
                raise RunnerFailed(
                    f"Unexpected approval format: {record.get('format')} {record.get('version')}"
                )
            if record.get("published") is not False:
                raise RunnerFailed("Approval record is marked published. Stopped.")
            computed = fingerprint_of(proposed)
            if record.get("diff_fingerprint") != computed:
                raise RunnerFailed("Approval fingerprint does not match the enrichment diff. Stopped.")
            packet_store = record.get("store_id")
            if packet_store and not same_store(packet_store, store_url):
                raise RunnerFailed(f"Approval store {packet_store} does not match {store_url}")
            packet_path = approval_dir / "approval_packet.json"
            packet = load_json(packet_path, "Merchant Approval packet") if packet_path.exists() else None
            approval_output = {"record": record, "packet": packet}
            store.record_stage(run_key, "Merchant_Approval", "completed",
                               hash_file(approval_out), approval_output, now_utc(),
                               input_hash=approval_input)
            if decision_path is not None:
                store.record_decision(run_key, computed,
                                      json.loads(decision_path.read_text()), now_utc())
        else:
            approval_output = skipped
            record = approval_output["record"]
        log("approval_checked",
            f"status {record.get('status')}, publish_allowed {record.get('publish_allowed')}",
            "ovo-approval-agent/approval:approval_record.json")

        if not record.get("publish_allowed"):
            result.update({
                "status": "paused_awaiting_merchant_decision",
                "approval_status": record.get("status"),
                "proposal_count": len(proposed),
                "product_count": gaps.get("product_count"),
                "gap_count_total": gaps.get("gap_count_total"),
                "plugin_spawned": False,
                "published": False,
            })
            log("approval_pause",
                "Paused at Merchant Approval. Plugin not started. Nothing published.",
                "ovo-approval-agent/approval:approval_record.json")
            print("Runner paused at Merchant Approval. Plugin not started. Nothing published.")
        else:
            # 4. Plugin, only after approval, dry run only in this build.
            approved = list(record.get("approved_as_proposed") or [])
            approved += list(record.get("approved_as_corrected") or [])
            approved += list(record.get("added_merchant_supplied") or [])
            if record.get("publishable_count") != len(approved):
                raise RunnerFailed(
                    f"Approval publishable {record.get('publishable_count')} does not match "
                    f"approved rows {len(approved)}"
                )
            if not approved:
                raise RunnerFailed("Approval allows publish but names no approved rows. Stopped.")
            result["plugin_spawned"] = True
            idempotency_key = f"publish:{run_key}"
            attempt = store.get_publish_attempt(idempotency_key)
            if attempt and attempt.get("status") in ("dry_run_complete", "blocked"):
                plugin_result = attempt["result"]
                log("plugin_attempt_reused",
                    f"publish attempt {idempotency_key} already recorded as "
                    f"{attempt.get('status')}. Nothing published again.",
                    "ovo-runner:store.py")
            else:
                if attempt and attempt.get("status") == "started":
                    # A past attempt started but never finished. In this
                    # build the plugin stage can only dry-run, so nothing
                    # could have posted, and a retry is safe. When live
                    # post exists, a started attempt must block and wait
                    # for a human check instead of re-running.
                    log("plugin_attempt_restarted",
                        f"publish attempt {idempotency_key} started before but never "
                        "finished. Dry run only, so nothing could have posted.",
                        "ovo-runner:store.py")
                store.record_publish_attempt(idempotency_key, run_key, "started",
                                             None, now_utc())
                with tempfile.TemporaryDirectory(prefix="ovo-plugin-") as tmp:
                    plugin_approval_path = Path(tmp) / "plugin_approval.json"
                    plugin_out = Path(tmp) / "plugin_run.json"
                    plugin_approval = dict(record)
                    plugin_approval["approved_rows"] = approved
                    plugin_approval_path.write_text(json.dumps(plugin_approval, indent=2))
                    # The plugin runner itself refuses live post in this
                    # build. No --post flag is passed here, ever.
                    run_stage("Plugin", [
                        sys.executable, str(plugin_dir / "augment-runner.py"),
                        "--diff", str(enrich_out),
                        "--approval", str(plugin_approval_path),
                        "--out", str(plugin_out),
                    ], plugin_dir, plugin_out,
                        hash_bytes(f"{idempotency_key}|{computed}".encode()))
                    plugin_result = load_json(plugin_out, "Plugin")
                if plugin_result.get("posted"):
                    store.update_publish_attempt(idempotency_key, "blocked",
                                                 plugin_result, now_utc())
                    raise RunnerFailed("Plugin posted True, but live post is blocked in this build. Stopped.")
                if plugin_result.get("published"):
                    store.update_publish_attempt(idempotency_key, "blocked",
                                                 plugin_result, now_utc())
                    raise RunnerFailed("Plugin reported published True, but live post is blocked here. Stopped.")
                store.update_publish_attempt(idempotency_key, "dry_run_complete",
                                             plugin_result, now_utc())
            if plugin_result.get("posted") is not False and plugin_result.get("posted") is not True:
                raise RunnerFailed("Plugin posted flag is not a clear true or false value.")
            result.update({
                "status": "plugin_dry_run_only",
                "approval_status": record.get("status"),
                "publish_allowed": True,
                "approved_count": len(approved),
                "plugin_status": plugin_result.get("status"),
                "plugin_posted": plugin_result.get("posted"),
                "published": False,
            })
            log("plugin_checked",
                f"status {plugin_result.get('status')}, posted False, published False",
                "ovo-plugin-agent:plugin_run.json")

        result["steps"] = steps
        result["finished_at_utc"] = now_utc()
        store.update_run(run_key, result["status"], result["finished_at_utc"], result)
        print(f"Runner done. Status: {result['status']}. Published: False.")
        return result

    except RunnerFailed as exc:
        result.update({
            "status": "failed",
            "failure": str(exc),
            "steps": steps,
            "finished_at_utc": now_utc(),
        })
        try:
            store.update_run(run_key, "failed", result["finished_at_utc"], result)
        except Exception:  # noqa: BLE001 - the failure itself is the report
            pass
        print(f"Runner failed: {exc}")
        raise
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description="OvO runner, production flow only")
    parser.add_argument("--store-url", required=True,
                        help="Public store address, given by the merchant. No default.")
    parser.add_argument("--decision-file", default=None,
                        help="Merchant decision file, given by the merchant only.")
    parser.add_argument("--skip-spark", action="store_true",
                        help="Pass --skip-spark to Audit. Deterministic path only.")
    parser.add_argument("--run-key", default=None,
                        help="Idempotency key for this run. A retry with the same key "
                             "resumes safely and publishes nothing twice.")
    parser.add_argument("--db", default=None,
                        help="Run store file. Default is ovo_runs.db next to runner.py.")
    args = parser.parse_args()
    store_url = args.store_url.strip()
    if not store_url.startswith("https://") and not store_url.startswith("http://"):
        raise SystemExit("Store address must start with http:// or https://")
    try:
        run_flow(store_url, decision_file=args.decision_file,
                 skip_spark=args.skip_spark, run_key=args.run_key,
                 db_path=args.db)
    except RunnerFailed:
        raise SystemExit(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
