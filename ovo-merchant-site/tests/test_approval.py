#!/usr/bin/env python3
"""Tests for item 2: the approval screen and decision recording.
Proves the chain a merchant approval must travel: no approval
recorded means publish is refused; an approval for one group
publishes only that group. The synthetic diff crosses bands so
each group rule is tested. The real Merchant Approval Agent
runs in record mode on the same decision file, and the two
records must agree. The augment runner is the final judge."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE.parent
REPO = SITE.parent
sys.path.insert(0, str(SITE))
sys.path.insert(0, str(REPO))

import auth  # noqa: E402
import approval  # noqa: E402
from store import MerchantStore  # noqa: E402

PHASE3_DIFF = Path.home() / "workspace" / "ovo-test-env" / "phase3-diff.json"
AUGMENT = REPO / "ovo-plugin-agent" / "augment-runner.py"
APPROVAL_AGENT = REPO / "ovo-approval-agent" / "approval" / "agent.py"
ENRICH_DIR = REPO / "ovo-enrichment-agent"
APPROVAL_DIR = REPO / "ovo-approval-agent" / "approval"


def make_row(product_id, field, value, accuracy, band):
    return {"product_id": product_id, "field": field,
            "new_value": value, "old_value": "",
            "accuracy_percent": accuracy,
            "prd_accuracy_band": band,
            "source_label": "store_api:product.description",
            "product_name": f"Trail Runner {product_id}"}


def synthetic_diff():
    """Rows across bands: 2 at 95, 2 at 88-90, 2 at 65, 1 at 45.
    All fields are allowed version 5 fields. Every row carries
    a source, a value, and an accuracy value, so the approval
    gate passes."""
    proposals = [
        make_row(1, "_ovo_material", "recycled mesh", 95, "95% or greater"),
        make_row(1, "_ovo_fit_guidance", "true to size", 96, "95% or greater"),
        make_row(2, "_ovo_material", "leather", 88, "80-94%"),
        make_row(2, "_ovo_returns_summary", "free returns 30 days", 90, "80-94%"),
        make_row(3, "_ovo_material", "canvas", 65, "50-79%"),
        make_row(3, "_ovo_fit_guidance", "snug at first", 70, "50-79%"),
        make_row(4, "_ovo_material", "suede", 45, "under 50%"),
    ]
    return {"format": "ovo-enrichment-diff", "version": "5.0-live",
            "status": "proposed_only_awaiting_merchant_approval",
            "published": False, "proposal_count": len(proposals),
            "product_count": 4, "proposals": proposals,
            "store_url": "https://store.example.com"}


class ApprovalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MerchantStore(Path(self.tmp.name) / "test.db")
        auth.create_merchant(self.store, "m1", "Test Merchant",
                             "m1@example.com", "correct-horse")
        result, _ = auth.sign_in_ovo(self.store, "m1", "correct-horse",
                                     "https://store.example.com")
        self.token = result["token"]
        self.session, _ = auth.verify_session(
            self.store, self.token, "https://store.example.com")
        self.staged = []

    def tearDown(self):
        for path in self.staged:
            # Only remove files the test run created. Never remove
            # a file that is tracked in the repo.
            tracked = subprocess.run(
                ["git", "-C", str(REPO), "ls-files", "--error-unmatch",
                 path], capture_output=True)
            if tracked.returncode != 0:
                try:
                    Path(path).unlink()
                except FileNotFoundError:
                    pass
        self.store.close()
        self.tmp.cleanup()

    def _track(self, path):
        self.staged.append(str(path))

    def _stage(self, path, content):
        Path(path).write_text(content)
        self.staged.append(str(path))

    def test_packet_from_real_diff_has_62_rows(self):
        diff = json.loads(PHASE3_DIFF.read_text())
        packet = approval.build_packet(diff)
        self.assertEqual(packet["presented_count"], 62)
        self.assertEqual(packet["proposed_count"], 62)
        groups = {g["band"]: g for g in packet["groups"]}
        self.assertEqual(groups["95_plus"]["presented_count"], 62)
        self.assertEqual(groups["80_94"]["presented_count"], 0)
        self.assertEqual(groups["50_79"]["presented_count"], 0)
        self.assertEqual(len(packet["diff_fingerprint"]), 64)

    def test_packet_groups_rows_by_band(self):
        packet = approval.build_packet(synthetic_diff())
        groups = {g["band"]: g for g in packet["groups"]}
        self.assertEqual(groups["95_plus"]["presented_count"], 2)
        self.assertEqual(groups["80_94"]["presented_count"], 2)
        self.assertEqual(groups["50_79"]["presented_count"], 2)
        self.assertEqual(packet["presented_count"], 6)
        self.assertEqual(len(packet["excluded_under_50"]), 1)
        self.assertEqual(len(packet["ungrouped_no_accuracy"]), 0)

    def test_packet_leaves_no_accuracy_rows_ungrouped(self):
        diff = synthetic_diff()
        diff["proposals"].append(
            {"product_id": 5, "field": "_ovo_material",
             "new_value": "nylon", "old_value": "",
             "source_label": "store_api:product.description",
             "product_name": "Trail Runner 5"})
        diff["proposal_count"] = len(diff["proposals"])
        packet = approval.build_packet(diff)
        self.assertEqual(len(packet["ungrouped_no_accuracy"]), 1)
        self.assertEqual(packet["presented_count"], 6)

    def test_review_html_shows_all_62_rows(self):
        diff = json.loads(PHASE3_DIFF.read_text())
        packet = approval.build_packet(diff)
        page = approval.render_review_html(packet, "run-1")
        self.assertIn("Review your store fixes", page)
        self.assertIn("95 percent or better", page)
        self.assertIn("80 to 94 percent", page)
        self.assertIn("50 to 79 percent", page)
        self.assertEqual(page.count("<tr>"), 62 + 1)  # rows + header
        self.assertIn("recycled mesh upper with rubber sole", page)
        self.assertIn("A group you do not submit approves", page)
        self.assertIn('class="modal"', page)

    def test_silence_is_not_approval(self):
        packet = approval.build_packet(synthetic_diff())
        record, errors = approval.record_decision(
            self.store, self.session, packet, [], "Merchant One",
            run_key="run-silence")
        self.assertIsNone(record)
        self.assertTrue(any("no group submitted" in e for e in errors))
        self.assertFalse(approval.publish_allowed(None))
        self.assertFalse(approval.publish_allowed({}))

    def test_agent_session_cannot_approve(self):
        packet = approval.build_packet(synthetic_diff())
        agent_session = dict(self.session)
        agent_session["submitted_by"] = "agent"
        record, errors = approval.record_decision(
            self.store, agent_session, packet,
            [{"band": "95_plus", "submitted": True, "rejections": []}],
            "Merchant One", run_key="run-agent")
        self.assertIsNone(record)
        self.assertTrue(any("agent cannot approve" in e for e in errors))

    def test_wrong_store_session_cannot_approve(self):
        packet = approval.build_packet(synthetic_diff())
        other = dict(self.session)
        other["store_id"] = "other-store"
        record, errors = approval.record_decision(
            self.store, other, packet,
            [{"band": "95_plus", "submitted": True, "rejections": []}],
            "Merchant One", run_key="run-store")
        self.assertIsNone(record)
        self.assertTrue(any("does not match" in e for e in errors))

    def test_approve_one_group_only(self):
        packet = approval.build_packet(synthetic_diff())
        groups = [
            {"band": "80_94", "submitted": True, "approvals": [
                {"product_id": 2, "field": "_ovo_material"},
                {"product_id": 2, "field": "_ovo_returns_summary"}]},
        ]
        record, errors = approval.record_decision(
            self.store, self.session, packet, groups, "Merchant One",
            run_key="run-one-group")
        self.assertIsNone(errors, errors)
        self.assertEqual(record["status"], "approved_partial")
        self.assertTrue(approval.publish_allowed(record))
        keys = {(r["product_id"], r["field"]) for r in record["approved_rows"]}
        self.assertEqual(keys, {(2, "_ovo_material"),
                                (2, "_ovo_returns_summary")})
        self.assertEqual(record["publishable_count"], 2)

    def test_95_band_reject_by_exception(self):
        packet = approval.build_packet(synthetic_diff())
        groups = [
            {"band": "95_plus", "submitted": True, "rejections": [
                {"product_id": 1, "field": "_ovo_material"}]},
        ]
        record, errors = approval.record_decision(
            self.store, self.session, packet, groups, "Merchant One",
            run_key="run-95")
        self.assertIsNone(errors, errors)
        keys = {(r["product_id"], r["field"]) for r in record["approved_rows"]}
        self.assertEqual(keys, {(1, "_ovo_fit_guidance")})
        self.assertEqual(record["status"], "approved_partial")

    def test_95_band_rejects_approvals_list(self):
        packet = approval.build_packet(synthetic_diff())
        groups = [
            {"band": "95_plus", "submitted": True, "approvals": [
                {"product_id": 1, "field": "_ovo_material"}]},
        ]
        record, errors = approval.record_decision(
            self.store, self.session, packet, groups, "Merchant One",
            run_key="run-95-bad")
        self.assertIsNone(record)
        self.assertTrue(any("rejections only" in e for e in errors))

    def _run_augment(self, diff, record):
        out_dir = Path(self.tmp.name)
        diff_path = out_dir / "diff.json"
        approval_path = out_dir / "approval.json"
        out_path = out_dir / "augment.json"
        diff_path.write_text(json.dumps(diff))
        approval_path.write_text(json.dumps(record))
        proc = subprocess.run(
            [sys.executable, str(AUGMENT), "--diff", str(diff_path),
             "--approval", str(approval_path), "--out", str(out_path)],
            capture_output=True, text=True, timeout=60)
        return proc.returncode, json.loads(out_path.read_text())

    def test_augment_refuses_without_approval(self):
        diff = synthetic_diff()
        awaiting = {"status": "awaiting_merchant_decision",
                    "diff_fingerprint": approval.build_packet(diff)["diff_fingerprint"],
                    "approved_rows": []}
        code, result = self._run_augment(diff, awaiting)
        self.assertEqual(code, 2)
        self.assertFalse(result["approved_rows"])
        self.assertIn("no approved rows", " ".join(result["errors"]))

    def test_augment_publishes_only_approved_group(self):
        diff = synthetic_diff()
        packet = approval.build_packet(diff)
        groups = [
            {"band": "80_94", "submitted": True, "approvals": [
                {"product_id": 2, "field": "_ovo_material"},
                {"product_id": 2, "field": "_ovo_returns_summary"}]},
        ]
        record, errors = approval.record_decision(
            self.store, self.session, packet, groups, "Merchant One",
            run_key="run-augment")
        self.assertIsNone(errors, errors)
        code, result = self._run_augment(diff, record)
        self.assertEqual(code, 0, result["errors"])
        self.assertEqual(result["status"], "dry_run_ready_not_posted")
        changes = result["plugin_diff"]["changes"]
        self.assertEqual(len(changes), 2)
        self.assertTrue(all(c["product_id"] == 2 for c in changes))
        self.assertTrue(all(c["field"] == "additional_property"
                            for c in changes))
        values = " ".join(c["new_value"] for c in changes)
        self.assertIn("Material|leather", values)
        self.assertIn("Returns|free returns 30 days", values)

    def test_correction_wins_over_proposal(self):
        diff = synthetic_diff()
        packet = approval.build_packet(diff)
        groups = [
            {"band": "80_94", "submitted": True, "corrections": [
                {"product_id": 2, "field": "_ovo_material",
                 "corrected_value": "full-grain leather"}]},
        ]
        record, errors = approval.record_decision(
            self.store, self.session, packet, groups, "Merchant One",
            run_key="run-correct")
        self.assertIsNone(errors, errors)
        code, result = self._run_augment(diff, record)
        self.assertEqual(code, 0, result["errors"])
        change = result["plugin_diff"]["changes"][0]
        self.assertIn("full-grain leather", change["new_value"])

    def test_low_accuracy_approval_is_blocked_by_augment(self):
        diff = synthetic_diff()
        packet = approval.build_packet(diff)
        groups = [
            {"band": "50_79", "submitted": True, "approvals": [
                {"product_id": 3, "field": "_ovo_material"}]},
        ]
        record, errors = approval.record_decision(
            self.store, self.session, packet, groups, "Merchant One",
            run_key="run-low")
        self.assertIsNone(errors, errors)
        code, result = self._run_augment(diff, record)
        self.assertEqual(code, 2)
        self.assertIn("below the 85 percent target",
                      " ".join(result["errors"]))

    def test_record_matches_real_approval_agent(self):
        """The site record and the Merchant Approval Agent record
        must agree on the same decision file."""
        diff = synthetic_diff()
        self._stage(ENRICH_DIR / "enrichment_diff_live.json",
                    json.dumps(diff))
        for name in ("approval_packet.json", "approval_packet.md",
                     "approval_cards.html", "approval_record.json",
                     "approval_run.json"):
            self._track(APPROVAL_DIR / name)
        # The agent rewrites decision_template.json as a side
        # effect of packet mode. Snapshot it and restore it, so
        # the test never changes a tracked file.
        template_path = APPROVAL_DIR / "decision_template.json"
        template_before = template_path.read_bytes()
        try:
            proc = subprocess.run(
                [sys.executable, str(APPROVAL_AGENT)],
                capture_output=True, text=True, timeout=60,
                cwd=str(APPROVAL_DIR))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            agent_packet = json.loads(
                (APPROVAL_DIR / "approval_packet.json").read_text())
            self._cross_check(agent_packet, diff)
        finally:
            template_path.write_bytes(template_before)

    def _cross_check(self, agent_packet, diff):
        packet = approval.build_packet(diff)
        self.assertEqual(agent_packet["diff_fingerprint"],
                         packet["diff_fingerprint"])
        self.assertEqual(agent_packet["presented_count"],
                         packet["presented_count"])
        groups = [
            {"band": "95_plus", "submitted": True, "rejections": [
                {"product_id": 1, "field": "_ovo_material"}]},
            {"band": "80_94", "submitted": True, "approvals": [
                {"product_id": 2, "field": "_ovo_material"},
                {"product_id": 2, "field": "_ovo_returns_summary"}]},
        ]
        record, errors = approval.record_decision(
            self.store, self.session, packet, groups, "Merchant One",
            run_key="run-cross")
        self.assertIsNone(errors, errors)
        saved = self.store.latest_decision(
            "run-cross", packet["diff_fingerprint"])
        decision = saved["decision"]
        decision_path = Path(self.tmp.name) / "decision.json"
        decision_path.write_text(json.dumps(decision))
        proc = subprocess.run(
            [sys.executable, str(APPROVAL_AGENT), "--decision-file",
             str(decision_path)],
            capture_output=True, text=True, timeout=60,
            cwd=str(APPROVAL_DIR))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        agent_record = json.loads(
            (APPROVAL_DIR / "approval_record.json").read_text())
        self.assertEqual(agent_record["status"], record["status"])
        mine = {(r["product_id"], r["field"])
                for r in record["approved_rows"]}
        theirs = {(r["product_id"], r["field"])
                  for r in agent_record["approved_rows"]}
        self.assertEqual(mine, theirs)
        self.assertEqual(agent_record["publish_allowed"], True)


if __name__ == "__main__":
    unittest.main()
