#!/usr/bin/env python3
"""Unit tests for the OvO Enrichment Agent.

Run: python3 test_agent.py
No live store and no Meta key are needed. The Meta helper tests
resolve paths only; no Meta call is made.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent  # noqa: E402


class TestMetaHelper(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.pop("OVO_META_HELPER", None)
        agent._HELPER_CACHE.update(checked=False, path=None)

    def tearDown(self):
        if self._env is None:
            os.environ.pop("OVO_META_HELPER", None)
        else:
            os.environ["OVO_META_HELPER"] = self._env
        agent._HELPER_CACHE.update(checked=False, path=None)

    def test_env_setting_wins(self):
        os.environ["OVO_META_HELPER"] = "/tmp/fake-helper.py"
        self.assertEqual(str(agent.meta_helper_path()), "/tmp/fake-helper.py")

    def test_fallback_is_repo_meta_client(self):
        path = agent.meta_helper_path()
        self.assertTrue(str(path).endswith("ovo-runner/meta_client.py"))
        self.assertTrue(path.exists())

    def test_missing_helper_fails_clearly_without_a_call(self):
        os.environ["OVO_META_HELPER"] = "/tmp/does-not-exist-helper.py"
        result = agent.vision_check("https://example.com/photo.jpg", "test")
        self.assertIn("error", result)
        self.assertIn("No Meta helper found", result["error"])
        self.assertIn("OVO_META_HELPER", result["error"])


class TestPureFunctions(unittest.TestCase):
    def test_normalize_base_url_strips_trailing_slash(self):
        self.assertEqual(agent.normalize_base_url("https://example.com/shop/"),
                         "https://example.com/shop")

    def test_merchant_slug_from_url(self):
        self.assertEqual(agent.merchant_slug_from_url("https://example.com/shop"), "shop")
        self.assertEqual(agent.merchant_slug_from_url("https://example.com/"), "example-com")

    def test_merchant_slug_override_wins(self):
        self.assertEqual(agent.merchant_slug_from_url("https://example.com/shop", "mine"),
                         "mine")


class TestCli(unittest.TestCase):
    def test_store_url_is_required(self):
        proc = subprocess.run([sys.executable, str(HERE / "agent.py")],
                              capture_output=True, text=True, cwd=str(HERE))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--store-url", proc.stderr)

    def test_rollback_needs_batch(self):
        proc = subprocess.run(
            [sys.executable, str(HERE / "agent.py"),
             "--store-url", "https://example.com/shop", "--rollback"],
            capture_output=True, text=True, cwd=str(HERE))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--batch", proc.stderr)


if __name__ == "__main__":
    unittest.main()
