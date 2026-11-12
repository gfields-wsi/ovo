#!/usr/bin/env python3
"""Unit tests for the OvO Coordinating Agent.

Run: python3 test_coordinator.py
No live store and no Meta key are needed. The tests run the
coordinator against stub agents in a temporary folder shaped
like the repo, and prove it pauses at Merchant Approval and
publishes nothing.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import coordinator  # noqa: E402

STORE_URL = "https://example.com/shop"

AUDIT_STUB = '''
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
args = sys.argv[1:]
url = args[args.index("--store-url") + 1]
(HERE / "gaps.json").write_text(json.dumps({
    "format": "ovo-gap-list", "version": "1.0", "store_url": url,
    "product_count": 1, "gap_count_total": 1, "scores": {}}))
print("Fake Audit done.")
'''

ENRICH_STUB = '''
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
args = sys.argv[1:]
url = args[args.index("--store-url") + 1]
proposals = [{"product_id": 1, "field": "_ovo_material", "old_value": None,
              "new_value": "Leather", "source_label": "store_api:product.description",
              "prd_accuracy_band": "95% or greater"}]
(HERE / "enrichment_diff_live.json").write_text(json.dumps({
    "format": "ovo-enrichment-diff", "version": "5.0-live",
    "status": "proposed_only_awaiting_merchant_approval", "published": False,
    "store_url": url, "product_count": 1, "proposal_count": 1,
    "proposals": proposals}))
print("Fake Enrichment done.")
'''

APPROVAL_STUB = '''
import hashlib, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
enrich_dir = HERE.parent.parent / "ovo-enrichment-agent"
diff = json.loads((enrich_dir / "enrichment_diff_live.json").read_text())
rows = sorted(({"product_id": p.get("product_id"), "field": p.get("field"),
                "new_value": p.get("new_value"), "old_value": p.get("old_value")}
               for p in diff["proposals"]),
              key=lambda r: (str(r["product_id"]), r["field"]))
fp = hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
record = {"format": "ovo-approval-record", "version": "1.0",
          "status": "awaiting_merchant_decision", "published": False,
          "diff_fingerprint": fp, "store_id": diff["store_url"],
          "publish_allowed": False, "publishable_count": 0,
          "approved_as_proposed": [], "approved_as_corrected": [],
          "added_merchant_supplied": []}
(HERE / "approval_record.json").write_text(json.dumps(record))
(HERE / "approval_packet.json").write_text(json.dumps(
    {"format": "ovo-approval-packet", "version": "1.0", "diff_fingerprint": fp}))
print("Fake Approval done: awaiting_merchant_decision.")
'''


def build_fake_tree(base):
    root = Path(base)
    (root / "ovo-audit-agent" / "audit").mkdir(parents=True)
    (root / "ovo-enrichment-agent").mkdir(parents=True)
    (root / "ovo-approval-agent" / "approval").mkdir(parents=True)
    (root / "ovo-plugin-agent").mkdir(parents=True)
    (root / "ovo-audit-agent" / "audit" / "agent.py").write_text(AUDIT_STUB)
    (root / "ovo-enrichment-agent" / "agent.py").write_text(ENRICH_STUB)
    (root / "ovo-approval-agent" / "approval" / "agent.py").write_text(APPROVAL_STUB)
    return root


class TestCoordinatorPause(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.repo = build_fake_tree(base / "repo")
        self.db = str(base / "runs.db")
        # Point the coordinator at the fake tree. The real runner
        # code runs; only the agents are fakes.
        self._patch = mock.patch.object(coordinator, "REPO_ROOT", self.repo)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self.tmp.cleanup()

    def test_pause_at_merchant_approval(self):
        argv = ["coordinator.py", "--store-url", STORE_URL,
                "--run-key", "coord-pause-1", "--db", self.db]
        with mock.patch.object(sys, "argv", argv):
            coordinator.main()
        log = json.loads((HERE / "coordinator_run.json").read_text())
        self.assertEqual(log["status"], "paused_awaiting_merchant_decision")
        self.assertFalse(log["published"])
        self.assertFalse(log["plugin_spawned"])
        self.assertFalse(log["publish_allowed"])
        self.assertEqual(log["proposal_count"], 1)
        # The plugin agent was never spawned: no plugin output exists.
        self.assertFalse((self.repo / "ovo-plugin-agent" / "plugin_run.json").exists())

    def test_store_url_is_required(self):
        with mock.patch.object(sys, "argv", ["coordinator.py"]):
            with self.assertRaises(SystemExit) as ctx:
                coordinator.main()
            self.assertEqual(ctx.exception.code, 2)


def tearDownModule():
    # The pause test writes coordinator_run.json next to this file.
    # Remove it so the repo stays clean.
    run_file = HERE / "coordinator_run.json"
    if run_file.exists():
        run_file.unlink()


if __name__ == "__main__":
    unittest.main()
