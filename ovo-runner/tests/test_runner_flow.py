#!/usr/bin/env python3
"""Unit tests for the OvO runner flow, with fake agents.

Run: python3 -m unittest discover -s tests -v
from the ovo-runner folder, or python3 tests/test_runner_flow.py.
No live store and no Meta key are needed. The fake agents are
stub scripts in a temporary folder shaped like the repo. They
write canned gaps, a version 5 diff, and an approval record, and
they count their own invocations, so the tests prove pause,
resume, and no-double-publish behaviour for real.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from runner import run_flow, RunnerFailed  # noqa: E402

STORE_URL = "https://example.com/shop"

FINGERPRINT = '''
import hashlib, json
def fingerprint_of(proposed):
    rows = sorted(
        ({"product_id": p.get("product_id"), "field": p.get("field"),
          "new_value": p.get("new_value"), "old_value": p.get("old_value")}
         for p in proposed),
        key=lambda r: (str(r["product_id"]), r["field"]))
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
'''

AUDIT_STUB = '''
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
(HERE / "invocations.txt").open("a").write("audit\\n")
args = sys.argv[1:]
url = args[args.index("--store-url") + 1]
(HERE / "gaps.json").write_text(json.dumps({
    "format": "ovo-gap-list", "version": "1.0", "store_url": url,
    "product_count": 2, "gap_count_total": 3, "scores": {}}))
(HERE / "scorecard.json").write_text(json.dumps({
    "format": "ovo-scorecard", "version": "1.0", "product_count": 2}))
print("Fake Audit done.")
'''

AUDIT_FAIL_STUB = '''
import sys
print("Fake Audit failed.", file=sys.stderr)
raise SystemExit(1)
'''

ENRICH_STUB = '''
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
(HERE / "invocations.txt").open("a").write("enrich\\n")
args = sys.argv[1:]
url = args[args.index("--store-url") + 1]
proposals = [
    {"product_id": 1, "field": "_ovo_material", "old_value": None,
     "new_value": "Leather", "source_label": "store_api:product.description",
     "prd_accuracy_band": "95% or greater"},
    {"product_id": 2, "field": "_ovo_material", "old_value": None,
     "new_value": "Canvas", "source_label": "store_api:product.description",
     "prd_accuracy_band": "95% or greater"},
]
(HERE / "enrichment_diff_live.json").write_text(json.dumps({
    "format": "ovo-enrichment-diff", "version": "5.0-live",
    "status": "proposed_only_awaiting_merchant_approval", "published": False,
    "store_url": url, "product_count": 2, "proposal_count": 2,
    "proposals": proposals}))
print("Fake Enrichment done.")
'''

APPROVAL_STUB = FINGERPRINT + '''
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
(HERE / "invocations.txt").open("a").write("approval\\n")
enrich_dir = HERE.parent.parent / "ovo-enrichment-agent"
diff = json.loads((enrich_dir / "enrichment_diff_live.json").read_text())
fp = fingerprint_of(diff["proposals"])
packet_rows = [{"product_id": p["product_id"], "field": p["field"],
                "current_value": p["old_value"], "proposed_value": p["new_value"],
                "band": "95_plus"} for p in diff["proposals"]]
args = sys.argv[1:]
if "--decision-file" in args:
    record = {"format": "ovo-approval-record", "version": "1.0",
              "status": "approved_all_presented", "published": False,
              "diff_fingerprint": fp, "store_id": diff["store_url"],
              "publish_allowed": True, "publishable_count": 2,
              "approved_as_proposed": packet_rows,
              "approved_as_corrected": [], "added_merchant_supplied": []}
else:
    record = {"format": "ovo-approval-record", "version": "1.0",
              "status": "awaiting_merchant_decision", "published": False,
              "diff_fingerprint": fp, "store_id": diff["store_url"],
              "publish_allowed": False, "publishable_count": 0,
              "approved_as_proposed": [], "approved_as_corrected": [],
              "added_merchant_supplied": []}
(HERE / "approval_record.json").write_text(json.dumps(record))
(HERE / "approval_packet.json").write_text(json.dumps(
    {"format": "ovo-approval-packet", "version": "1.0", "diff_fingerprint": fp}))
print(f"Fake Approval done: {record['status']}.")
'''

PLUGIN_STUB = FINGERPRINT + '''
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
(HERE / "invocations.txt").open("a").write("plugin\\n")
args = sys.argv[1:]
diff = json.loads(Path(args[args.index("--diff") + 1]).read_text())
approval = json.loads(Path(args[args.index("--approval") + 1]).read_text())
out = Path(args[args.index("--out") + 1])
assert "--accuracy" not in args, "plugin must not receive --accuracy"
assert fingerprint_of(diff["proposals"]) == approval["diff_fingerprint"]
assert approval["approved_rows"], "no approved rows"
result = {"agent": "Fake Augment runner", "status": "dry_run_ready_not_posted",
          "published": False, "posted": False,
          "approved_rows": [{"product_id": r["product_id"], "field": r["field"]}
                            for r in approval["approved_rows"]]}
out.write_text(json.dumps(result))
print(json.dumps(result))
'''


def build_fake_tree(base, failing_audit=False):
    """A temporary folder shaped like the repo, with stub agents."""
    root = Path(base)
    (root / "ovo-audit-agent" / "audit").mkdir(parents=True)
    (root / "ovo-enrichment-agent").mkdir(parents=True)
    (root / "ovo-approval-agent" / "approval").mkdir(parents=True)
    (root / "ovo-plugin-agent").mkdir(parents=True)
    (root / "ovo-audit-agent" / "audit" / "agent.py").write_text(
        AUDIT_FAIL_STUB if failing_audit else AUDIT_STUB)
    (root / "ovo-enrichment-agent" / "agent.py").write_text(ENRICH_STUB)
    (root / "ovo-approval-agent" / "approval" / "agent.py").write_text(APPROVAL_STUB)
    (root / "ovo-plugin-agent" / "augment-runner.py").write_text(PLUGIN_STUB)
    return root


def invocations(root, agent_dir, name):
    path = root / agent_dir / "invocations.txt"
    if not path.exists():
        return 0
    return path.read_text().count(name + "\n")


class TestRunnerFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.repo = build_fake_tree(self.base / "repo")
        self.db = str(self.base / "runs.db")
        self.decision = self.base / "decision.json"
        self.decision.write_text(json.dumps({"format": "ovo-merchant-decision"}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_pause_at_merchant_approval(self):
        result = run_flow(STORE_URL, run_key="pause-1", db_path=self.db,
                          repo_root=self.repo)
        self.assertEqual(result["status"], "paused_awaiting_merchant_decision")
        self.assertFalse(result["published"])
        self.assertFalse(result["plugin_spawned"])
        self.assertEqual(result["proposal_count"], 2)
        self.assertEqual(invocations(self.repo, "ovo-plugin-agent", "plugin"), 0)

    def test_replay_same_key_skips_completed_stages(self):
        run_flow(STORE_URL, run_key="replay-1", db_path=self.db, repo_root=self.repo)
        before = {
            name: invocations(self.repo, d, name)
            for name, d in (("audit", "ovo-audit-agent/audit"),
                            ("enrich", "ovo-enrichment-agent"),
                            ("approval", "ovo-approval-agent/approval"))
        }
        self.assertEqual(before, {"audit": 1, "enrich": 1, "approval": 1})
        result = run_flow(STORE_URL, run_key="replay-1", db_path=self.db,
                          repo_root=self.repo)
        self.assertTrue(result.get("resumed_from_store"))
        self.assertEqual(result["status"], "paused_awaiting_merchant_decision")
        after = {
            name: invocations(self.repo, d, name)
            for name, d in (("audit", "ovo-audit-agent/audit"),
                            ("enrich", "ovo-enrichment-agent"),
                            ("approval", "ovo-approval-agent/approval"))
        }
        self.assertEqual(after, before)

    def test_decision_flow_runs_plugin_dry_run_only(self):
        run_flow(STORE_URL, run_key="dec-1", db_path=self.db, repo_root=self.repo)
        result = run_flow(STORE_URL, decision_file=str(self.decision),
                          run_key="dec-1", db_path=self.db, repo_root=self.repo)
        self.assertEqual(result["status"], "plugin_dry_run_only")
        self.assertTrue(result["publish_allowed"])
        self.assertFalse(result["plugin_posted"])
        self.assertFalse(result["published"])
        self.assertEqual(result["approved_count"], 2)
        self.assertEqual(invocations(self.repo, "ovo-plugin-agent", "plugin"), 1)

    def test_retry_after_plugin_reuses_publish_attempt(self):
        run_flow(STORE_URL, run_key="dec-2", db_path=self.db, repo_root=self.repo)
        run_flow(STORE_URL, decision_file=str(self.decision),
                 run_key="dec-2", db_path=self.db, repo_root=self.repo)
        result = run_flow(STORE_URL, decision_file=str(self.decision),
                          run_key="dec-2", db_path=self.db, repo_root=self.repo)
        self.assertEqual(result["status"], "plugin_dry_run_only")
        self.assertEqual(invocations(self.repo, "ovo-plugin-agent", "plugin"), 1)

    def test_failed_stage_stops_the_run(self):
        bad_repo = build_fake_tree(self.base / "bad-repo", failing_audit=True)
        with self.assertRaises(RunnerFailed):
            run_flow(STORE_URL, run_key="fail-1", db_path=self.db, repo_root=bad_repo)
        self.assertEqual(invocations(bad_repo, "ovo-enrichment-agent", "enrich"), 0)
        self.assertEqual(invocations(bad_repo, "ovo-approval-agent/approval", "approval"), 0)

    def test_same_key_other_store_is_rejected(self):
        run_flow(STORE_URL, run_key="bound-1", db_path=self.db, repo_root=self.repo)
        with self.assertRaises(ValueError):
            run_flow("https://other.com/", run_key="bound-1", db_path=self.db,
                     repo_root=self.repo)


class TestRunnerCli(unittest.TestCase):
    def test_store_url_is_required(self):
        import runner
        with mock.patch.object(sys, "argv", ["runner.py"]):
            with self.assertRaises(SystemExit) as ctx:
                runner.main()
            self.assertEqual(ctx.exception.code, 2)

    def test_store_url_must_have_a_scheme(self):
        import runner
        with mock.patch.object(sys, "argv",
                               ["runner.py", "--store-url", "example.com/shop"]):
            with self.assertRaises(SystemExit) as ctx:
                runner.main()
            self.assertIn("http", str(ctx.exception.code))


if __name__ == "__main__":
    unittest.main()
