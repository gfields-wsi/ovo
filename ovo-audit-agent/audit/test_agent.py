#!/usr/bin/env python3
"""Unit tests for the OvO Audit Agent.

Run: python3 test_agent.py
No live store and no Meta key are needed. The store test uses a
local address nothing listens on, so the Store API call fails
fast and the agent must fail closed.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent  # noqa: E402


class TestPureFunctions(unittest.TestCase):
    def test_clean_html_strips_tags_and_spaces(self):
        self.assertEqual(agent.clean_html("<p>Full-grain <b>leather</b></p>"),
                         "Full-grain leather")

    def test_segment_extracts_labelled_value(self):
        desc = "Material: Full-grain leather. Fit: True to size. Returns: 30 days."
        self.assertEqual(agent.segment(desc, "Material", ["Fit", "Returns"]),
                         "Full-grain leather")
        self.assertEqual(agent.segment(desc, "Fit", ["Returns"]), "True to size")
        self.assertEqual(agent.segment(desc, "Returns", []), "30 days")

    def test_segment_missing_label_is_none(self):
        self.assertIsNone(agent.segment("No labels here.", "Material", ["Fit"]))


class TestCli(unittest.TestCase):
    def test_store_url_is_required(self):
        proc = subprocess.run([sys.executable, str(HERE / "agent.py")],
                              capture_output=True, text=True, cwd=str(HERE))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--store-url", proc.stderr)

    def test_unreachable_store_fails_closed(self):
        """No live store: the deterministic audit cannot read the
        Store API, so the agent must exit non-zero and write no
        gaps file for that store."""
        gaps = HERE / "gaps.json"
        if gaps.exists():
            gaps.unlink()
        proc = subprocess.run(
            [sys.executable, str(HERE / "agent.py"),
             "--store-url", "http://127.0.0.1:9/shop"],
            capture_output=True, text=True, cwd=str(HERE), timeout=240)
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(gaps.exists())


if __name__ == "__main__":
    unittest.main()
