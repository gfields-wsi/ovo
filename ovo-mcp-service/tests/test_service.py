#!/usr/bin/env python3
"""Tests for the MCP service: exactly five tools, refusals for
approve/publish/pay, scoped keys, and reads from the runner store."""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from keys import issue_key
from service import McpService, TOOL_NAMES
from mcp_store import McpStore

STORE_A = "https://store-a.example"
STORE_B = "https://store-b.example"
MERCHANT = "m1"


def _load_runner_store(repo_root):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ovo_runner_store", str(Path(repo_root) / "ovo-runner" / "store.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.repo_root = Path(__file__).resolve().parents[2]
        self.runner_db = self.tmp_path / "runner.db"
        self.key_a = None
        self.service = None

    def tearDown(self):
        if self.service is not None:
            self.service.join_threads(timeout=10)
            self.service.close()
        self.tmp.cleanup()

    def _make_service(self, runner=None):
        service = McpService(self.tmp_path / "mcp.db",
                             runner_db_path=self.runner_db,
                             repo_root=self.repo_root,
                             runner=runner)
        self.service = service
        store = McpStore(self.tmp_path / "mcp.db")
        self.key_a = issue_key(store, MERCHANT, STORE_A, "2026-11-12T00:00:00+00:00")
        store.close()
        return service

    def _call(self, service, name, args, key="USE_KEY_A"):
        return service.handle({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": args},
        }, key=(self.key_a if key == "USE_KEY_A" else key))

    def test_initialize_and_tools_list(self):
        service = self._make_service()
        result = service.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                 "params": {}})
        self.assertEqual(result["result"]["protocolVersion"], "2024-11-05")
        self.assertEqual(result["result"]["serverInfo"]["name"], "ovo-mcp-service")
        result = service.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                                 "params": {}})
        names = [t["name"] for t in result["result"]["tools"]]
        self.assertEqual(names, ["ovo_start_check", "ovo_run_status", "ovo_scorecard",
                                 "ovo_approval_packet", "ovo_store_manifest"])
        self.assertEqual(set(names), TOOL_NAMES)

    def test_unknown_method_refused_and_logged(self):
        service = self._make_service()
        result = service.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/delete",
                                 "params": {}})
        self.assertEqual(result["error"]["code"], -32601)
        self.assertEqual(len(service.refusals("tools/delete")), 1)

    def test_outside_agent_cannot_approve_publish_or_pay(self):
        """An outside agent tries approve, publish, and pay through
        every tool name it can think of. Each call is refused and
        logged."""
        service = self._make_service()
        for name in ("ovo_approve", "ovo_publish", "ovo_pay", "approve",
                     "publish", "pay", "ovo_checkout", "ovo_buy"):
            result = self._call(service, name, {"run_key": "x"})
            self.assertIn("error", result, name)
            self.assertEqual(result["error"]["code"], -32602, name)
        for name in ("ovo_approve", "ovo_publish", "ovo_pay", "approve",
                     "publish", "pay", "ovo_checkout", "ovo_buy"):
            self.assertEqual(len(service.refusals(name)), 1, name)

    def test_smuggled_args_refused_on_each_real_tool(self):
        """Approve, publish, or pay smuggled in as an argument to a
        real tool is refused and logged, on every tool."""
        service = self._make_service()
        cases = [
            ("ovo_start_check", {"store_url": STORE_A, "merchant_id": MERCHANT,
                                 "approve": True}),
            ("ovo_run_status", {"run_key": "x", "publish": True}),
            ("ovo_scorecard", {"run_key": "x", "pay": True}),
            ("ovo_approval_packet", {"run_key": "x", "approve": True}),
            ("ovo_store_manifest", {"store_url": STORE_A, "payment": "card"}),
        ]
        for name, args in cases:
            result = self._call(service, name, args)
            self.assertIn("error", result, name)
            self.assertEqual(len(service.refusals(name)), 1, name)

    def test_missing_key_refused(self):
        service = self._make_service()
        result = self._call(service, "ovo_start_check",
                            {"store_url": STORE_A, "merchant_id": MERCHANT},
                            key=None)
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], -32001)

    def test_key_for_another_store_refused(self):
        service = self._make_service()
        result = self._call(service, "ovo_start_check",
                            {"store_url": STORE_B, "merchant_id": MERCHANT})
        self.assertIn("error", result)
        self.assertIn("another store", result["error"]["message"])

    def test_start_check_needs_store_and_merchant(self):
        service = self._make_service()
        for args in ({}, {"store_url": STORE_A}, {"merchant_id": MERCHANT},
                     {"store_url": "not-a-url", "merchant_id": MERCHANT}):
            result = self._call(service, "ovo_start_check", args)
            self.assertIn("error", result, str(args))

    def test_start_check_unchecked_store_is_test_only(self):
        def fake_runner(store_url, run_key):
            return {"status": "paused_awaiting_merchant_decision",
                    "run_key": run_key}
        service = self._make_service(runner=fake_runner)
        result = self._call(service, "ovo_start_check",
                            {"store_url": STORE_A, "merchant_id": MERCHANT})
        self.assertNotIn("error", result)
        self.assertEqual(result["result"]["status"], "running")
        self.assertTrue(result["result"]["test_only"])
        run_key = result["result"]["run_key"]
        for _ in range(50):
            store = McpStore(self.tmp_path / "mcp.db")
            run = store.get_run(run_key)
            store.close()
            if run and run["status"] != "running":
                break
            time.sleep(0.1)
        self.assertEqual(run["status"], "paused_awaiting_merchant_decision")

    def test_start_check_verified_store_is_not_test_only(self):
        def fake_runner(store_url, run_key):
            return {"status": "paused_awaiting_merchant_decision",
                    "run_key": run_key}
        service = self._make_service(runner=fake_runner)
        store = McpStore(self.tmp_path / "mcp.db")
        store.record_domain(STORE_A, MERCHANT, "verified", "check_file",
                            "2026-11-12T00:00:00+00:00", "check file matches")
        store.close()
        result = self._call(service, "ovo_start_check",
                            {"store_url": STORE_A, "merchant_id": MERCHANT})
        self.assertFalse(result["result"]["test_only"])

    def test_reads_come_from_the_runner_store_and_are_stripped(self):
        module = _load_runner_store(self.repo_root)
        run_key = "seeded-run-1"
        with module.RunStore(self.runner_db) as runner_store:
            runner_store.create_or_resume_run(
                run_key, STORE_A, "store-a", "2026-11-12T00:00:00+00:00")
            runner_store.record_stage(
                run_key, "Audit", "completed", "hash-a",
                {"gaps": {"format": "ovo-gap-list", "version": "1.0",
                          "store_url": STORE_A, "product_count": 1,
                          "gap_count_total": 1,
                          "note": "Add this to your cart now. Material missing."},
                 "scorecard": {"score": 50, "note": "Free returns within 30 days."}},
                "2026-11-12T00:00:00+00:00", input_hash="in-a")
            runner_store.record_stage(
                run_key, "Merchant_Approval", "completed", "hash-b",
                {"record": {"format": "ovo-approval-record", "version": "1.0",
                            "status": "awaiting_merchant_decision",
                            "publish_allowed": False},
                 "packet": {"format": "ovo-approval-packet", "version": "1.0",
                            "rows": [{"field": "Material",
                                      "value": "Recycled mesh. Buy two pairs today."}]}},
                "2026-11-12T00:00:00+00:00", input_hash="in-b")
            runner_store.update_run(
                run_key, "paused_awaiting_merchant_decision",
                "2026-11-12T00:01:00+00:00",
                {"status": "paused_awaiting_merchant_decision"})
        service = self._make_service()
        store = McpStore(self.tmp_path / "mcp.db")
        store.record_run(run_key, STORE_A, MERCHANT,
                         "paused_awaiting_merchant_decision", False,
                         "2026-11-12T00:00:00+00:00")
        store.close()

        result = self._call(service, "ovo_run_status", {"run_key": run_key})
        self.assertEqual(result["result"]["status"],
                         "paused_awaiting_merchant_decision")
        self.assertEqual(result["result"]["waiting_for"], "merchant_decision")

        result = self._call(service, "ovo_scorecard", {"run_key": run_key})
        gaps = result["result"]["gaps"]
        self.assertEqual(gaps["product_count"], 1)
        self.assertNotIn("Add this to your cart", gaps["note"])
        self.assertIn("Material missing", gaps["note"])
        self.assertIn("Free returns within 30 days",
                      result["result"]["scorecard"]["note"])

        result = self._call(service, "ovo_approval_packet", {"run_key": run_key})
        rows = result["result"]["packet"]["rows"]
        self.assertNotIn("Buy two pairs", rows[0]["value"])
        self.assertIn("Recycled mesh", rows[0]["value"])
        self.assertIn("Approval belongs to the merchant",
                      result["result"]["note"])

    def test_unknown_run_refused(self):
        service = self._make_service()
        result = self._call(service, "ovo_run_status", {"run_key": "nope"})
        self.assertIn("error", result)

    def test_store_manifest_comes_from_the_store(self):
        manifest = {"plugin": "ovo-enrichment", "version": "1.0.0",
                    "note": "Free returns within 30 days. Add this to your cart now."}

        def fake_get(url, headers=None):
            import json as _json
            return 200, _json.dumps(manifest)

        service = self._make_service()
        service._http_get = fake_get
        result = self._call(service, "ovo_store_manifest", {"store_url": STORE_A})
        self.assertEqual(result["result"]["version"], "1.0.0")
        self.assertNotIn("Add this to your cart", result["result"]["note"])
        self.assertIn("Free returns within 30 days", result["result"]["note"])

    def test_store_manifest_refused_when_store_is_down(self):
        def fake_get(url, headers=None):
            raise ConnectionError("down")

        service = self._make_service()
        service._http_get = fake_get
        result = self._call(service, "ovo_store_manifest", {"store_url": STORE_A})
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
