#!/usr/bin/env python3
"""Live install test against the Phase 3 test install only
(WordPress 7.1.4 + WooCommerce 11.3.0 at localhost:8081).
Never touches a live store. Uninstalls the plugin, installs it
again through install_on_store with the real WordPress admin
flow, verifies it, then re-sets the token hash, because an
uninstall wipes it. Skipped when the test install is not up."""
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE.parent
sys.path.insert(0, str(SITE))

import install as install_mod  # noqa: E402

ENV = Path.home() / "workspace" / "ovo-test-env"
WPCLI = ["php", str(ENV / "wp-cli.phar"), "--allow-root"]
SITE_A = "wp71"
STORE_URL = "http://localhost:8081"


def wp(*args):
    return subprocess.run(WPCLI + list(args) + [f"--path={ENV / SITE_A}"],
                          capture_output=True, text=True, timeout=120)


def site_up():
    try:
        with urllib.request.urlopen(
                STORE_URL + "/wp-json/ovo/v1/manifest",
                timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


class LiveInstallTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ENV / "admin-password.txt").exists() or not site_up():
            raise unittest.SkipTest("Phase 3 test install is not up")

    def test_live_install(self):
        password = (ENV / "admin-password.txt").read_text().strip()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        try:
            # 1. Uninstall the plugin first, so the install is real.
            r = wp("plugin", "uninstall", "ovo-enrichment", "--deactivate")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = wp("plugin", "is-installed", "ovo-enrichment")
            self.assertNotEqual(r.returncode, 0)
            # 2. Build the package and install it in one press.
            zip_path, sha256, version = install_mod.build_package(
                Path(tmp.name))
            self.assertEqual(version, "1.0.0")
            record = install_mod.install_on_store(
                STORE_URL, "ovo_admin", password, zip_path)
            self.assertEqual(record["status"], "installed_and_active")
            self.assertEqual(record["steps"], [
                "wordpress_login", "upload_page", "plugin_uploaded",
                "plugin_activated", "manifest_answers"])
            # 3. Prove it from outside the installer.
            r = wp("plugin", "is-active", "ovo-enrichment")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with urllib.request.urlopen(
                    STORE_URL + "/wp-json/ovo/v1/manifest",
                    timeout=10) as resp:
                manifest = json.loads(resp.read().decode())
            self.assertEqual(manifest["version"], "1.0.0")
            webhooks = {w["topic"]: w for w in manifest["webhooks"]}
            self.assertTrue(webhooks["product.created"]["active"])
            self.assertTrue(webhooks["product.updated"]["active"])
            self.assertTrue(webhooks["product.deleted"]["active"])
        finally:
            # 4. Leave the site working: an uninstall wipes the
            # token hash, so re-set it from the test token, and
            # make sure the plugin is installed and active.
            r = wp("plugin", "is-installed", "ovo-enrichment")
            if r.returncode != 0:
                zip_path, _, _ = install_mod.build_package(Path(tmp.name))
                r = wp("plugin", "install", str(zip_path))
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = wp("plugin", "is-active", "ovo-enrichment")
            if r.returncode != 0:
                r = wp("plugin", "activate", "ovo-enrichment")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = wp("eval", "echo hash('sha256', file_get_contents("
                   "getenv('HOME').'/workspace/ovo-test-env/ovo-token.txt'));" )
            token_hash = r.stdout.strip()
            self.assertEqual(len(token_hash), 64)
            r = wp("option", "update", "ovo_enrichment_token_hash",
                   token_hash)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = wp("plugin", "is-active", "ovo-enrichment")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
