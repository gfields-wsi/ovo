#!/usr/bin/env python3
"""
OvO Coordinating Agent, production flow.

Flow, in order, through relevant agents only:
1. Audit agent
2. Enrichment agent
3. Merchant Approval agent, pause here
4. Plugin agent, only after approval

The Coordinating Agent does no audit work, no enrichment work,
no approval decisions, and no publish work. The Coordinating
Agent spawns each relevant agent, passes output from one agent
to the next agent, waits for each agent to finish, checks each
agent output, stops if any check fails, and logs each
coordination action with source fields.

The Coordinating Agent never publishes on its own, never buys,
and never approves on its own. A pause at Merchant Approval
means the run stops, with published false, until the Merchant
Approval agent records a merchant decision with publish allowed
true. Only then does the Coordinating Agent spawn the Plugin
agent, and only with the approved list.

Usage:
    python3 coordinator.py [--store-url URL] [--skip-spark]
Output: coordinator_run.json in this folder.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FRAMEWORK = ROOT / "framework"
sys.path.insert(0, str(FRAMEWORK))

from ovo_agent import OvoAgent, COORDINATOR_PHASE  # noqa: E402

SYSTEM_PROMPT = """You are the OvO Coordinating Agent. You spawn relevant
agents in order, pass output from one agent to the next, check
each output, pause at Merchant Approval, and stop if any check
fails. You do no audit work, no enrichment work, no approval
decisions, and no publish work."""


class CoordinatorFailed(Exception):
    pass


def run_agent(agent, name, command, cwd):
    agent.log_step(f"spawn_{name}", " ".join(command))
    proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=900)
    print(proc.stdout, end="")
    if proc.returncode != 0:
        agent.log_step(f"agent_failed_{name}", proc.stderr[:1000])
        raise CoordinatorFailed(f"Agent {name} failed with exit {proc.returncode}.")
    agent.log_step(f"agent_done_{name}", f"exit {proc.returncode}")
    return proc


def load_json(path, label):
    if not path.exists():
        raise CoordinatorFailed(f"{label} output missing: {path}")
    return json.loads(path.read_text())


def fingerprint_of(proposed):
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


def main():
    parser = argparse.ArgumentParser(description="OvO Coordinating Agent")
    parser.add_argument("--store-url", required=True, help="Public store address, given by the merchant. No default store.")
    parser.add_argument("--skip-spark", action="store_true")
    parser.add_argument("--decision-file", default=None,
                        help="Merchant decision file, given by the merchant only. "
                             "Without this file, the Merchant Approval agent runs in packet mode and the run pauses.")
    args = parser.parse_args()

    agent = OvoAgent(
        name="OvO Coordinating Agent",
        phase=COORDINATOR_PHASE,
        system_prompt=SYSTEM_PROMPT,
        workdir=HERE,
    )
    try:
        agent.log_step("start", f"Coordinating Agent run started for {args.store_url}",
                       "coordinator:coordinator.py")

        audit_dir = ROOT / "stream1-audit"
        enrich_dir = ROOT / "stream2-enrichment"
        approval_dir = ROOT / "approval"
        plugin_dir = Path("/home/hatch/workspace/ovo-hackathon/ovo-plugin")

        # 1. Audit agent
        audit_cmd = [sys.executable, str(audit_dir / "agent.py"),
                     "--store-url", args.store_url]
        if args.skip_spark:
            audit_cmd.append("--skip-spark")
        run_agent(agent, "Audit", audit_cmd, audit_dir)
        gaps_path = audit_dir / "gaps.json"
        gaps = load_json(gaps_path, "Audit")
        if gaps.get("format") != "ovo-gap-list" or gaps.get("version") != "1.0":
            raise CoordinatorFailed(f"Unexpected gap format: {gaps.get('format')} {gaps.get('version')}")
        if gaps.get("store_url") != args.store_url:
            raise CoordinatorFailed(f"Audit store_url {gaps.get('store_url')} does not match {args.store_url}")
        agent.log_step("audit_checked", f"{gaps['product_count']} products, "
                       f"{gaps['gap_count_total']} gaps",
                       "stream1-audit:gaps.json")

        # 2. Enrichment agent, with Audit output as input
        run_agent(agent, "Enrichment", [sys.executable, str(enrich_dir / "agent.py")], enrich_dir)
        diff_path = enrich_dir / "enrichment_diff.json"
        diff = load_json(diff_path, "Enrichment")
        if diff.get("published"):
            raise CoordinatorFailed("Enrichment published, which this coordinator forbids. Stopped.")
        if diff.get("status") != "proposed_only_awaiting_merchant_approval":
            raise CoordinatorFailed(f"Unexpected enrichment status: {diff.get('status')}")
        actual_proposed = sum(1 for p in diff["proposals"] if p.get("status") == "proposed")
        if diff.get("proposal_count") != actual_proposed:
            raise CoordinatorFailed(
                f"Enrichment proposal_count {diff.get('proposal_count')} does not match "
                f"actual proposed rows {actual_proposed}.")
        agent.log_step("enrichment_checked",
                       f"{diff['proposal_count']} proposals, published {diff['published']}",
                       "stream2-enrichment:enrichment_diff.json")

        # 3. Merchant Approval agent, with Enrichment output as input, pause here
        # Without a merchant decision file, the approval agent runs in
        # packet mode, writes awaiting_merchant_decision, and the
        # coordinator pauses. With a merchant decision file, the
        # approval agent records that merchant decision only.
        approval_cmd = [sys.executable, str(approval_dir / "agent.py")]
        if args.decision_file:
            approval_cmd += ["--decision-file", args.decision_file]
        run_agent(agent, "Merchant_Approval", approval_cmd, approval_dir)
        record_path = approval_dir / "approval_record.json"
        record = load_json(record_path, "Merchant Approval")
        if record.get("format") != "ovo-approval-record" or record.get("version") != "1.0":
            raise CoordinatorFailed(f"Unexpected approval format: {record.get('format')} {record.get('version')}")
        if record.get("published"):
            raise CoordinatorFailed("Approval record is marked published. Stopped.")
        proposed_rows = [p for p in diff["proposals"] if p.get("status") == "proposed"]
        computed_fp = fingerprint_of(proposed_rows)
        if record.get("diff_fingerprint") != computed_fp:
            raise CoordinatorFailed("Approval fingerprint does not match Enrichment diff. Stopped.")
        agent.log_step("approval_checked",
                       f"status {record.get('status')}, publish_allowed {record.get('publish_allowed')}, "
                       f"fingerprint matches Enrichment diff",
                       "approval:approval_record.json")

        if not record.get("publish_allowed"):
            agent.log_step("approval_pause",
                           "Paused at Merchant Approval. Plugin agent not spawned. Nothing published.",
                           "approval:approval_record.json")
            agent.write_audit_log(filename="coordinator_run.json", extra={
                "flow": ["Audit", "Enrichment", "Merchant Approval", "Plugin"],
                "store_url": args.store_url,
                "product_count": gaps.get("product_count"),
                "gap_count_total": gaps.get("gap_count_total"),
                "proposal_count": diff.get("proposal_count"),
                "approval_status": record.get("status"),
                "publish_allowed": False,
                "published": False,
                "status": "paused_awaiting_merchant_decision",
                "plugin_spawned": False,
                "integration_claimed": False,
            })
            print("Coordinating Agent paused at Merchant Approval. Plugin agent not spawned. Nothing published.")
            return

        # 4. Plugin agent, only after approval, only with approved list
        approved = list(record.get("approved_as_proposed") or [])
        approved += list(record.get("approved_as_corrected") or [])
        approved += list(record.get("added_merchant_supplied") or [])
        if record.get("publishable_count") != len(approved):
            raise CoordinatorFailed(
                f"Approval publishable_count {record.get('publishable_count')} does not match "
                f"approved rows {len(approved)}.")
        if not approved:
            raise CoordinatorFailed("Approval allows publish but names no approved rows. Stopped.")
        agent.log_step("approval_passed_to_plugin",
                       f"{len(approved)} approved rows passed to Plugin agent",
                       "approval:approval_record.json")

        plugin_runner = plugin_dir / "augment-runner.py"
        if not plugin_runner.exists():
            raise CoordinatorFailed(f"Plugin agent runner missing: {plugin_runner}")
        accuracy_path = ROOT / "accuracy" / "accuracy_scorecard.json"
        plugin_out = HERE / "plugin_run.json"
        # Pass the approved list in the form the Plugin agent accepts.
        # The approval record lists approved rows under three keys.
        # The Plugin runner reads a single approved_rows list. The
        # coordinator builds that list here, from the approval
        # record only, with no new rows, and keeps the original
        # approval record unchanged.
        plugin_approval_path = HERE / "plugin_approval.json"
        plugin_approval = dict(record)
        plugin_approval["approved_rows"] = approved
        plugin_approval_path.write_text(json.dumps(plugin_approval, indent=2))
        agent.log_step("approved_list_passed_to_plugin",
                       f"{len(approved)} approved rows in plugin_approval.json",
                       "coordinator:plugin_approval.json")
        plugin_cmd = [sys.executable, str(plugin_runner),
                      "--diff", str(diff_path),
                      "--approval", str(plugin_approval_path),
                      "--accuracy", str(accuracy_path),
                      "--out", str(plugin_out)]
        # Plugin agent runs in dry-run mode by default in its own runner.
        # Live post is refused by that runner until its own stream
        # proves token auth on WordPress. The coordinator does not
        # force a live post, and does not bypass that refusal.
        try:
            run_agent(agent, "Plugin", plugin_cmd, plugin_dir)
        except CoordinatorFailed:
            # Plugin agent exit 2 means its own gate blocked the run.
            # Read its output file, log it, and stop fail-closed.
            if plugin_out.exists():
                plugin_result = load_json(plugin_out, "Plugin")
                agent.log_step("plugin_blocked_by_plugin_gate",
                               f"status {plugin_result.get('status')}, errors {plugin_result.get('errors')}",
                               "coordinator:plugin_run.json")
            raise
        plugin_result = load_json(plugin_out, "Plugin")
        if plugin_result.get("published"):
            agent.log_step("plugin_published", "Plugin agent reported published true",
                           "coordinator:plugin_run.json")
        else:
            agent.log_step("plugin_checked",
                           f"status {plugin_result.get('status')}, posted {plugin_result.get('posted')}, "
                           f"published {plugin_result.get('published')}",
                           "coordinator:plugin_run.json")

        agent.write_audit_log(filename="coordinator_run.json", extra={
            "flow": ["Audit", "Enrichment", "Merchant Approval", "Plugin"],
            "store_url": args.store_url,
            "product_count": gaps.get("product_count"),
            "gap_count_total": gaps.get("gap_count_total"),
            "proposal_count": diff.get("proposal_count"),
            "approval_status": record.get("status"),
            "publish_allowed": True,
            "approved_count": len(approved),
            "plugin_status": plugin_result.get("status"),
            "plugin_posted": plugin_result.get("posted"),
            "published": bool(plugin_result.get("published")),
            "status": "plugin_complete" if plugin_result.get("published") else "plugin_dry_run_only",
            "plugin_spawned": True,
            "integration_claimed": False,
        })
        print(f"Coordinating Agent done. Plugin status: {plugin_result.get('status')}. "
              f"Published: {plugin_result.get('published')}.")
    except CoordinatorFailed as exc:
        agent.log_step("coordinator_failed", str(exc))
        agent.write_audit_log(filename="coordinator_run.json", extra={
            "flow": ["Audit", "Enrichment", "Merchant Approval", "Plugin"],
            "store_url": args.store_url,
            "published": False,
            "status": "failed",
            "failure": str(exc),
            "integration_claimed": False,
        })
        print(f"Coordinating Agent failed: {exc} See coordinator_run.json.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
