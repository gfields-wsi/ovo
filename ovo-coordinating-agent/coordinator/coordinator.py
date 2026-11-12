#!/usr/bin/env python3
"""
OvO Coordinating Agent, production flow.

The Coordinating Agent runs the shared runner flow in
ovo-runner/runner.py, in order, through relevant agents only:
1. Audit agent
2. Enrichment agent, version 5, 62-row shape
3. Merchant Approval agent, pause here
4. Plugin agent, only after approval, dry run only

There is one flow, kept in the runner. This file is a thin front
for it: it keeps the Coordinating Agent name, its command line,
and its coordinator_run.json log, and it does no agent work of
its own. The Coordinating Agent does no audit work, no enrichment
work, no approval decisions, and no publish work. It stops if any
check fails, and logs each coordination action with source fields.

The Coordinating Agent never publishes on its own, never buys,
and never approves on its own. A pause at Merchant Approval
means the run stops, with published false, until the Merchant
Approval agent records a merchant decision with publish allowed
true. Only then does the flow spawn the Plugin agent, and only
with the approved list.

Usage:
    python3 coordinator.py [--store-url URL] [--skip-spark]
    python3 coordinator.py --store-url URL --decision-file decision.json
Output: coordinator_run.json in this folder.
"""
import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("OVO_REPO_ROOT") or HERE.parent.parent)
FRAMEWORK = REPO_ROOT / "ovo-framework"
RUNNER_DIR = REPO_ROOT / "ovo-runner"
sys.path.insert(0, str(FRAMEWORK))
sys.path.insert(0, str(RUNNER_DIR))

from ovo_agent import OvoAgent, COORDINATOR_PHASE  # noqa: E402
from runner import run_flow, RunnerFailed  # noqa: E402

SYSTEM_PROMPT = """You are the OvO Coordinating Agent. You spawn relevant
agents in order, pass output from one agent to the next, check
each output, pause at Merchant Approval, and stop if any check
fails. You do no audit work, no enrichment work, no approval
decisions, and no publish work."""


def main():
    parser = argparse.ArgumentParser(description="OvO Coordinating Agent")
    parser.add_argument("--store-url", required=True, help="Public store address, given by the merchant. No default store.")
    parser.add_argument("--skip-spark", action="store_true")
    parser.add_argument("--decision-file", default=None,
                        help="Merchant decision file, given by the merchant only. "
                             "Without this file, the Merchant Approval agent runs in packet mode and the run pauses.")
    parser.add_argument("--run-key", default=None,
                        help="Idempotency key for this run. A retry with the same key resumes safely.")
    parser.add_argument("--db", default=None,
                        help="Run store file. Default is ovo_runs.db next to the runner.")
    args = parser.parse_args()

    agent = OvoAgent(
        name="OvO Coordinating Agent",
        phase=COORDINATOR_PHASE,
        system_prompt=SYSTEM_PROMPT,
        workdir=HERE,
    )
    agent.log_step("start", f"Coordinating Agent run started for {args.store_url}",
                   "coordinator:coordinator.py")
    try:
        result = run_flow(
            args.store_url,
            decision_file=args.decision_file,
            skip_spark=args.skip_spark,
            run_key=args.run_key,
            db_path=args.db,
            repo_root=REPO_ROOT,
        )
    except RunnerFailed as exc:
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

    status = result.get("status")
    agent.log_step("flow_finished", f"status {status}, published False",
                   "ovo-runner:runner.py")
    if status == "paused_awaiting_merchant_decision":
        agent.log_step("approval_pause",
                       "Paused at Merchant Approval. Plugin agent not spawned. Nothing published.",
                       "ovo-approval-agent/approval:approval_record.json")
        print("Coordinating Agent paused at Merchant Approval. Plugin agent not spawned. Nothing published.")
    elif status == "plugin_dry_run_only":
        agent.log_step("plugin_checked",
                       f"status {result.get('plugin_status')}, posted False, published False",
                       "ovo-plugin-agent:plugin_run.json")
        print(f"Coordinating Agent done. Plugin status: {result.get('plugin_status')}. Published: False.")
    agent.write_audit_log(filename="coordinator_run.json", extra={
        "flow": ["Audit", "Enrichment", "Merchant Approval", "Plugin"],
        "store_url": args.store_url,
        "run_key": result.get("run_key"),
        "product_count": result.get("product_count"),
        "gap_count_total": result.get("gap_count_total"),
        "proposal_count": result.get("proposal_count"),
        "approval_status": result.get("approval_status"),
        "publish_allowed": result.get("publish_allowed", False),
        "approved_count": result.get("approved_count"),
        "plugin_status": result.get("plugin_status"),
        "plugin_posted": result.get("plugin_posted"),
        "published": False,
        "status": status,
        "plugin_spawned": result.get("plugin_spawned", False),
        "integration_claimed": False,
    })


if __name__ == "__main__":
    main()
