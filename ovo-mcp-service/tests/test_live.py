#!/usr/bin/env python3
"""Live integration test: an outside agent starts a real check
on the local test install, reads status, scorecard, and packet,
and is refused approve, publish, and pay.

Runs only when the local test install answers. The real runner
runs in the service's background thread, so this test polls
status until the run pauses at Merchant Approval. The run takes
a few minutes: audit plus enrichment with live vision calls.
"""
import json
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain import check_domain
from keys import issue_key
from service import McpService
from mcp_store import McpStore

TEST_STORE = "http://localhost:8081"
MERCHANT = "test-merchant"


def site_is_up():
    try:
        with urllib.request.urlopen(
                TEST_STORE + "/wp-json/ovo/v1/manifest", timeout=5) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001 - a down site skips the live test
        return False


@unittest.skipUnless(site_is_up(), "local test install is not running")
class LiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.repo_root = Path(__file__).resolve().parents[2]
        self.service = McpService(
            self.tmp_path / "mcp.db",
            runner_db_path=self.tmp_path / "runner.db",
            repo_root=self.repo_root)

    def tearDown(self):
        self.service.join_threads(timeout=10)
        self.service.close()
        self.tmp.cleanup()

    def _call(self, name, args, key):
        return self.service.handle({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": args},
        }, key=key)

    def test_outside_agent_live_check(self):
        # Prove domain ownership for real, with the check file on
        # the test install. The file lives in the test env only.
        passed, status, detail = check_domain(
            self.service._store, TEST_STORE, MERCHANT,
            checked_at="2026-11-12T00:00:00+00:00")
        self.assertTrue(passed, detail)
        self.assertEqual(status, "verified")
        key = issue_key(self.service._store, MERCHANT, TEST_STORE,
                        "2026-11-12T00:00:00+00:00")

        started = self._call("ovo_start_check",
                             {"store_url": TEST_STORE, "merchant_id": MERCHANT},
                             key)
        self.assertNotIn("error", started, started)
        self.assertFalse(started["result"]["test_only"])
        run_key = started["result"]["run_key"]

        # Poll until the run pauses at Merchant Approval.
        status = None
        for _ in range(60):
            time.sleep(10)
            status = self._call("ovo_run_status", {"run_key": run_key}, key)
            self.assertNotIn("error", status, status)
            if status["result"]["status"] in (
                    "paused_awaiting_merchant_decision", "failed",
                    "plugin_dry_run_only"):
                break
        self.assertEqual(status["result"]["status"],
                         "paused_awaiting_merchant_decision")
        self.assertEqual(status["result"]["waiting_for"], "merchant_decision")

        scorecard = self._call("ovo_scorecard", {"run_key": run_key}, key)
        self.assertNotIn("error", scorecard, scorecard)
        self.assertEqual(scorecard["result"]["gaps"]["product_count"], 12)

        packet = self._call("ovo_approval_packet", {"run_key": run_key}, key)
        self.assertNotIn("error", packet, packet)
        self.assertEqual(packet["result"]["record"]["status"],
                         "awaiting_merchant_decision")

        manifest = self._call("ovo_store_manifest",
                              {"store_url": TEST_STORE}, key)
        self.assertNotIn("error", manifest, manifest)
        self.assertEqual(manifest["result"]["version"], "1.0.0")

        # The same agent is refused approve, publish, and pay.
        for name in ("ovo_approve", "ovo_publish", "ovo_pay"):
            refused = self._call(name, {"run_key": run_key}, key)
            self.assertIn("error", refused, name)
        self.assertEqual(len(self.service.refusals("ovo_approve")), 1)
        self.assertEqual(len(self.service.refusals("ovo_publish")), 1)
        self.assertEqual(len(self.service.refusals("ovo_pay")), 1)


if __name__ == "__main__":
    unittest.main()
