#!/usr/bin/env python3
"""Unit tests for the Plugin-side augment runner.

Run: python3 test_augment_runner.py
No live store, no WordPress, and no Meta key are needed. The
tests run the runner against synthetic version 5 diffs and
approval records in a temporary folder. There is no --accuracy
input: accuracy travels inside the diff.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "augment_runner", HERE / "augment-runner.py")
augment_runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(augment_runner)


def row(pid, field, new, band, acc=None):
    r = {"product_id": pid, "field": field, "old_value": None, "new_value": new,
         "source_label": "store_api:product.description", "prd_accuracy_band": band}
    if acc is not None:
        r["accuracy_percent"] = acc
    return r


def make_diff():
    return {
        "format": "ovo-enrichment-diff", "version": "5.0-live",
        "status": "proposed_only_awaiting_merchant_approval", "published": False,
        "store_url": "https://example.com/shop",
        "product_count": 2, "proposal_count": 7,
        "proposals": [
            row(1, "_ovo_material", "Leather", "95% or greater", acc=98.0),
            row(1, "_ovo_fit_guidance", "True to size", "95% or greater"),
            row(1, "_ovo_image_alt", "Boots, Brown, Boots", "95% or greater", acc=96.0),
            row(1, "_ovo_returns_summary", "30-day returns", "80-94%"),
            row(2, "_ovo_material", "Canvas", "80-94%"),
            row(2, "_ovo_fit_guidance", "Runs large", "50-79%"),
            row(2, "_ovo_image_alt_2", "Runners, Blue, Shoes", "95% or greater", acc=97.0),
        ],
    }


def make_approval(diff, approved_rows):
    return {
        "format": "ovo-approval-record", "version": "1.0",
        "status": "approved_all_presented", "published": False,
        "diff_fingerprint": augment_runner.fingerprint(diff["proposals"]),
        "store_id": "https://example.com/shop", "approved_by": "Test Merchant",
        "publish_allowed": True, "approved_rows": approved_rows,
    }


class TestLabels(unittest.TestCase):
    def test_image_alt_labels(self):
        self.assertEqual(augment_runner.label_for("_ovo_image_alt"), "Image alt text")
        self.assertEqual(augment_runner.label_for("_ovo_image_alt_2"), "Image alt text 2")
        self.assertEqual(augment_runner.label_for("_ovo_variant_black"), "Variant black")
        self.assertEqual(augment_runner.label_for("_ovo_material"), "Material")
        self.assertIsNone(augment_runner.label_for("price"))
        self.assertIsNone(augment_runner.label_for("_ovo_original_description"))


class TestRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_runner(self, diff, approval, extra=None):
        diff_path = self.base / "diff.json"
        approval_path = self.base / "approval.json"
        out_path = self.base / "run.json"
        diff_path.write_text(json.dumps(diff))
        approval_path.write_text(json.dumps(approval))
        cmd = [sys.executable, str(HERE / "augment-runner.py"),
               "--diff", str(diff_path), "--approval", str(approval_path),
               "--out", str(out_path)] + (extra or [])
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(HERE))
        result = json.loads(out_path.read_text()) if out_path.exists() else None
        return proc.returncode, result

    def approved(self, diff, keys):
        by_key = {(p["product_id"], p["field"]): p for p in diff["proposals"]}
        return [{"product_id": pid, "field": field,
                 "proposed_value": by_key[(pid, field)]["new_value"]}
                for pid, field in keys]

    def test_dry_run_maps_approved_rows_only(self):
        diff = make_diff()
        approved = self.approved(diff, [(1, "_ovo_material"), (1, "_ovo_image_alt"),
                                        (2, "_ovo_image_alt_2")])
        rc, result = self.run_runner(diff, make_approval(diff, approved))
        self.assertEqual(rc, 0)
        self.assertEqual(result["status"], "dry_run_ready_not_posted")
        self.assertFalse(result["posted"])
        self.assertFalse(result["published"])
        values = sorted(c["new_value"] for c in result["approved_rows"])
        self.assertEqual(values, ["Image alt text 2|Runners, Blue, Shoes",
                                  "Image alt text|Boots, Brown, Boots",
                                  "Material|Leather"])

    def test_corrected_row_publishes_as_corrected(self):
        diff = make_diff()
        approved = [{"product_id": 1, "field": "_ovo_material",
                     "proposed_value": "Leather",
                     "corrected_value": "Full-grain leather"}]
        rc, result = self.run_runner(diff, make_approval(diff, approved))
        self.assertEqual(rc, 0)
        self.assertEqual(result["approved_rows"][0]["new_value"],
                         "Material|Full-grain leather")

    def test_band_row_without_exact_percent_is_blocked(self):
        diff = make_diff()
        approved = self.approved(diff, [(1, "_ovo_returns_summary")])
        rc, result = self.run_runner(diff, make_approval(diff, approved))
        self.assertEqual(rc, 2)
        self.assertEqual(result["status"], "blocked_accuracy_gate")
        self.assertTrue(any("80-94%" in e for e in result["errors"]))

    def test_fingerprint_mismatch_is_blocked(self):
        diff = make_diff()
        approval = make_approval(diff, self.approved(diff, [(1, "_ovo_material")]))
        diff["proposals"][0]["new_value"] = "Tampered"
        rc, result = self.run_runner(diff, approval)
        self.assertEqual(rc, 2)
        self.assertFalse(result["fingerprint_match"])

    def test_awaiting_approval_is_blocked(self):
        diff = make_diff()
        approval = make_approval(diff, self.approved(diff, [(1, "_ovo_material")]))
        approval["status"] = "awaiting_merchant_decision"
        rc, result = self.run_runner(diff, approval)
        self.assertEqual(rc, 2)
        self.assertEqual(result["status"], "blocked_awaiting_or_failed_gate")

    def test_post_is_refused(self):
        diff = make_diff()
        approved = self.approved(diff, [(1, "_ovo_material")])
        rc, result = self.run_runner(diff, make_approval(diff, approved), ["--post"])
        self.assertEqual(rc, 2)
        self.assertEqual(result["status"], "blocked_post_not_enabled")
        self.assertFalse(result["posted"])

    def test_accuracy_flag_is_gone(self):
        proc = subprocess.run([sys.executable, str(HERE / "augment-runner.py"),
                               "--help"], capture_output=True, text=True, cwd=str(HERE))
        self.assertNotIn("--accuracy", proc.stdout)


if __name__ == "__main__":
    unittest.main()
