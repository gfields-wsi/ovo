#!/usr/bin/env python3
"""Unit tests for the OvO Merchant Approval Agent.

Run: python3 test_agent.py
No live store and no Meta key are needed. The packet and record
tests run the agent against a synthetic version 5 diff in a
temporary folder, by pointing the agent's folders there, so no
file in this repo is read or written. There is no accuracy
scorecard input: the tests prove the agent works with a diff
alone.
"""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent  # noqa: E402


def row(pid, field, new, band, acc=None):
    r = {"product_id": pid, "field": field, "old_value": None, "new_value": new,
         "source_label": "store_api:product.description", "prd_accuracy_band": band,
         "prd_human_check": "check", "presented_to_merchant": "YES",
         "accuracy_basis": "test", "evidence": "test prose",
         "source_field": "description", "source_url": "https://example.com/shop/p",
         "fetched_at_utc": "2026-11-12T00:00:00Z", "reason_code": "test", "next_action": "none"}
    if acc is not None:
        r["accuracy_percent"] = acc
    return r


def make_diff():
    return {
        "format": "ovo-enrichment-diff", "version": "5.0-live",
        "status": "proposed_only_awaiting_merchant_approval", "published": False,
        "generated_at_utc": "2026-11-12T00:00:00Z", "batch_id": "test-1",
        "merchant": "example", "store_url": "https://example.com/shop",
        "product_count": 2, "proposal_count": 6,
        "proposals": [
            row(1, "_ovo_material", "Leather", "95% or greater", acc=98.0),
            row(1, "_ovo_fit_guidance", "True to size", "95% or greater"),
            row(1, "_ovo_returns_summary", "30-day returns", "80-94%"),
            row(2, "_ovo_material", "Canvas", "80-94%"),
            row(2, "_ovo_fit_guidance", "Runs large", "50-79%"),
            row(2, "_ovo_returns_summary", "No returns stated", "under 50%"),
        ],
    }


class TestFingerprint(unittest.TestCase):
    def test_uses_version_5_keys(self):
        rows = [row(1, "_ovo_material", "Leather", "95% or greater")]
        fp = agent.fingerprint(rows)
        expected_rows = [{"product_id": 1, "field": "_ovo_material",
                          "new_value": "Leather", "old_value": None}]
        expected = hashlib.sha256(
            json.dumps(sorted(expected_rows, key=lambda r: (str(r["product_id"]), r["field"])),
                       sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        self.assertEqual(fp, expected)

    def test_order_does_not_change_fingerprint(self):
        rows = make_diff()["proposals"]
        self.assertEqual(agent.fingerprint(rows), agent.fingerprint(list(reversed(rows))))

    def test_changed_value_changes_fingerprint(self):
        rows = make_diff()["proposals"]
        changed = copy.deepcopy(rows)
        changed[0]["new_value"] = "Tampered"
        self.assertNotEqual(agent.fingerprint(rows), agent.fingerprint(changed))


class TestAccuracyBanding(unittest.TestCase):
    def test_exact_percent_wins_over_band(self):
        self.assertEqual(agent.row_accuracy(row(1, "_ovo_material", "x", "50-79%", acc=97.0)), 97.0)

    def test_band_low_end_counts(self):
        self.assertEqual(agent.row_accuracy(row(1, "_ovo_material", "x", "95% or greater")), 95.0)
        self.assertEqual(agent.row_accuracy(row(1, "_ovo_material", "x", "80-94%")), 80.0)
        self.assertEqual(agent.row_accuracy(row(1, "_ovo_material", "x", "50-79%")), 50.0)
        self.assertEqual(agent.row_accuracy(row(1, "_ovo_material", "x", "under 50%")), 0.0)

    def test_no_accuracy_is_ungrouped(self):
        r = row(1, "_ovo_material", "x", "80-94%")
        del r["prd_accuracy_band"]
        self.assertIsNone(agent.row_accuracy(r))

    def test_band_boundaries(self):
        self.assertEqual(agent.band_for(95.0)["band"], "95_plus")
        self.assertEqual(agent.band_for(94.999)["band"], "80_94")
        self.assertEqual(agent.band_for(80.0)["band"], "80_94")
        self.assertEqual(agent.band_for(50.0)["band"], "50_79")
        self.assertIsNone(agent.band_for(49.9))
        self.assertIsNone(agent.band_for(None))

    def test_field_allowed_version_5_only(self):
        self.assertTrue(agent.field_allowed("_ovo_material"))
        self.assertTrue(agent.field_allowed("_ovo_variant_black"))
        self.assertFalse(agent.field_allowed("material_structured"))
        self.assertFalse(agent.field_allowed("price"))


class TestGate(unittest.TestCase):
    def test_valid_diff_passes(self):
        checks, ok = agent.check_gate(make_diff())
        self.assertTrue(ok, checks)

    def test_old_version_fails(self):
        diff = make_diff()
        diff["version"] = "1.0-proposed"
        _, ok = agent.check_gate(diff)
        self.assertFalse(ok)

    def test_row_without_accuracy_fails(self):
        diff = make_diff()
        del diff["proposals"][0]["prd_accuracy_band"]
        del diff["proposals"][0]["accuracy_percent"]
        _, ok = agent.check_gate(diff)
        self.assertFalse(ok)

    def test_disallowed_field_fails(self):
        diff = make_diff()
        diff["proposals"][0]["field"] = "price"
        _, ok = agent.check_gate(diff)
        self.assertFalse(ok)

    def test_count_mismatch_fails(self):
        diff = make_diff()
        diff["proposal_count"] = 99
        _, ok = agent.check_gate(diff)
        self.assertFalse(ok)


class TestPacketAndRecord(unittest.TestCase):
    """Full packet mode and record mode, in temporary folders."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.enrich_dir = base / "enrich"
        self.approval_dir = base / "approval"
        self.audit_dir = base / "audit"
        self.coord_dir = base / "coord"
        for d in (self.enrich_dir, self.approval_dir, self.audit_dir, self.coord_dir):
            d.mkdir()
        (self.enrich_dir / "enrichment_diff_live.json").write_text(json.dumps(make_diff()))
        (self.audit_dir / "gaps.json").write_text(json.dumps({
            "format": "ovo-gap-list", "version": "1.0",
            "store_url": "https://example.com/shop",
            "product_count": 2, "gap_count_total": 6}))
        self._patch = mock.patch.multiple(
            agent, HERE=self.approval_dir, ENRICH_DIR=self.enrich_dir,
            AUDIT_DIR=self.audit_dir, COORD_DIR=self.coord_dir)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self.tmp.cleanup()

    def run_main(self, argv):
        with mock.patch.object(sys, "argv", ["agent.py"] + argv):
            agent.main()

    def test_packet_mode_needs_no_scorecard(self):
        self.run_main([])
        packet = json.loads((self.approval_dir / "approval_packet.json").read_text())
        self.assertEqual(packet["presented_count"], 5)
        self.assertEqual(packet["excluded_under_50_count"], 1)
        self.assertEqual(packet["accuracy_bands_as_given"],
                         {"95_plus": 2, "80_94": 2, "50_79": 1, "under_50": 1})
        self.assertEqual(packet["total_gaps"], 6)
        record = json.loads((self.approval_dir / "approval_record.json").read_text())
        self.assertEqual(record["status"], "awaiting_merchant_decision")
        self.assertFalse(record["publish_allowed"])
        self.assertIn("no separate scorecard", record["accuracy_source"])

    def test_record_mode_approves_and_allows_publish(self):
        self.run_main([])
        record = json.loads((self.approval_dir / "approval_record.json").read_text())
        template = json.loads((self.approval_dir / "decision_template.json").read_text())
        template["diff_fingerprint"] = record["diff_fingerprint"]
        template["approved_by"] = "Test Merchant"
        template["store_id"] = "https://example.com/shop"
        template["session"] = {"session_id": "sess-1", "merchant_id": "merchant-1",
                               "store_id": "https://example.com/shop",
                               "submitted_by": "merchant",
                               "expires_at_utc": "2999-01-01T00:00:00Z", "revoked": False}
        template["decided_at_utc"] = "2026-11-12T01:00:00Z"
        for g in template["groups"]:
            g["submitted"] = True
            if g["band"] == "80_94":
                g["approvals"] = [{"product_id": 1, "field": "_ovo_returns_summary"},
                                  {"product_id": 2, "field": "_ovo_material"}]
            if g["band"] == "50_79":
                g["approvals"] = [{"product_id": 2, "field": "_ovo_fit_guidance"}]
        decision = Path(self.tmp.name) / "decision.json"
        decision.write_text(json.dumps(template))
        self.run_main(["--decision-file", str(decision)])
        record = json.loads((self.approval_dir / "approval_record.json").read_text())
        self.assertEqual(record["status"], "approved_all_presented")
        self.assertTrue(record["publish_allowed"])
        self.assertEqual(record["publishable_count"], 5)

    def test_wrong_fingerprint_is_rejected(self):
        self.run_main([])
        template = json.loads((self.approval_dir / "decision_template.json").read_text())
        template["diff_fingerprint"] = "0" * 64
        template["approved_by"] = "Test Merchant"
        template["store_id"] = "https://example.com/shop"
        template["session"] = {"session_id": "sess-1", "merchant_id": "merchant-1",
                               "store_id": "https://example.com/shop",
                               "submitted_by": "merchant",
                               "expires_at_utc": "2999-01-01T00:00:00Z", "revoked": False}
        for g in template["groups"]:
            g["submitted"] = True
        decision = Path(self.tmp.name) / "decision.json"
        decision.write_text(json.dumps(template))
        with self.assertRaises(SystemExit) as ctx:
            self.run_main(["--decision-file", str(decision)])
        self.assertEqual(ctx.exception.code, 1)
        record = json.loads((self.approval_dir / "approval_record.json").read_text())
        self.assertEqual(record["status"], "invalid_decision")
        self.assertFalse(record["publish_allowed"])

    def test_missing_diff_fails_clearly(self):
        (self.enrich_dir / "enrichment_diff_live.json").unlink()
        with self.assertRaises(SystemExit) as ctx:
            self.run_main([])
        self.assertIn("Missing input", str(ctx.exception.code))

    def test_missing_decision_file_fails_clearly(self):
        self.run_main([])
        with self.assertRaises(SystemExit):
            self.run_main(["--decision-file", str(Path(self.tmp.name) / "nope.json")])


if __name__ == "__main__":
    unittest.main()
