#!/usr/bin/env python3
"""Unit tests for the OvO runner store (SQLite now, Postgres later).

Run: python3 test_store.py
No live store and no Meta key are needed.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from store import RunStore  # noqa: E402


class TestRunStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "runs.db")
        self.store = RunStore(self.db)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_create_and_resume_same_key(self):
        first = self.store.create_or_resume_run(
            "k1", "https://example.com/shop", "example-com-shop", "2026-11-12T00:00:00Z")
        self.assertEqual(first["status"], "running")
        second = self.store.create_or_resume_run(
            "k1", "https://example.com/shop", "example-com-shop", "2026-11-12T00:01:00Z")
        self.assertEqual(second["run_key"], "k1")
        self.assertEqual(second["started_at_utc"], "2026-11-12T00:00:00Z")

    def test_same_key_other_store_is_an_error(self):
        self.store.create_or_resume_run(
            "k1", "https://example.com/shop", "example-com-shop", "2026-11-12T00:00:00Z")
        with self.assertRaises(ValueError):
            self.store.create_or_resume_run(
                "k1", "https://other.com/", "other-com", "2026-11-12T00:00:00Z")

    def test_stage_record_and_read(self):
        self.store.create_or_resume_run(
            "k1", "https://example.com/shop", "example-com-shop", "2026-11-12T00:00:00Z")
        self.store.record_stage("k1", "Audit", "completed", "abc",
                                {"gaps": {"product_count": 2}},
                                "2026-11-12T00:01:00Z", input_hash="in1")
        stage = self.store.get_stage("k1", "Audit")
        self.assertEqual(stage["status"], "completed")
        self.assertEqual(stage["input_hash"], "in1")
        self.assertEqual(stage["output"]["gaps"]["product_count"], 2)
        self.assertIsNone(self.store.get_stage("k1", "Nope"))

    def test_publish_attempt_first_write_wins(self):
        attempt = self.store.record_publish_attempt(
            "publish:k1", "k1", "started", None, "2026-11-12T00:02:00Z")
        self.assertEqual(attempt["status"], "started")
        again = self.store.record_publish_attempt(
            "publish:k1", "k1", "dry_run_complete", {"posted": False},
            "2026-11-12T00:03:00Z")
        self.assertEqual(again["status"], "started")
        self.store.update_publish_attempt(
            "publish:k1", "dry_run_complete", {"posted": False}, "2026-11-12T00:03:00Z")
        self.assertEqual(self.store.get_publish_attempt("publish:k1")["status"],
                         "dry_run_complete")

    def test_export_run(self):
        self.store.create_or_resume_run(
            "k1", "https://example.com/shop", "example-com-shop", "2026-11-12T00:00:00Z")
        self.store.record_stage("k1", "Audit", "completed", "abc", {"gaps": {}},
                                "2026-11-12T00:01:00Z", input_hash="in1")
        self.store.record_publish_attempt(
            "publish:k1", "k1", "dry_run_complete", {"posted": False},
            "2026-11-12T00:02:00Z")
        exported = self.store.export_run("k1")
        self.assertEqual(exported["run_key"], "k1")
        self.assertEqual(len(exported["stages"]), 1)
        self.assertEqual(len(exported["publish_attempts"]), 1)
        self.assertIsNone(self.store.export_run("missing"))


if __name__ == "__main__":
    unittest.main()
