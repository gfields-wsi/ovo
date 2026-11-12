#!/usr/bin/env python3
"""Tests for item 3: Install OvO Plugins. The flow is tested
with a fake browser (no live store) for every step and failure,
and live against the Phase 3 test install in test_install_live.
The WordPress password is used for one call only and is never
stored or logged."""
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE.parent
REPO = SITE.parent
sys.path.insert(0, str(SITE))

import install as install_mod  # noqa: E402


class FakeBrowser:
    """Canned WordPress admin. Records what it was asked, so
    the test can prove the password never leaves the call."""

    def __init__(self, fail_login=False, fail_upload=False,
                 no_activate_link=False, manifest_version="1.0.0",
                 relative_link=False):
        self.fail_login = fail_login
        self.fail_upload = fail_upload
        self.no_activate_link = no_activate_link
        self.manifest_version = manifest_version
        self.relative_link = relative_link
        self.logged_in = False
        self.uploads = []
        self.fetched_urls = []

    def get(self, url, headers=None):
        self.fetched_urls.append(url)
        if url.endswith("/wp-login.php"):
            return 200, "<html>login</html>"
        if "plugin-install.php" in url:
            return 200, ('<form><input name="_wpnonce"'
                         ' value="abc123def456"></form>')
        if "action=activate" in url:
            return 200, "<html>Plugin activated.</html>"
        if url.endswith("/wp-json/ovo/v1/manifest"):
            return 200, json.dumps({"plugin": "ovo-enrichment",
                                    "version": self.manifest_version})
        return 404, "not found"

    def post(self, url, data, headers=None):
        if url.endswith("/wp-login.php"):
            if self.fail_login:
                return 200, "<html>login error</html>"
            self.logged_in = True
            return 200, "<html>dashboard</html>"
        if "action=upload-plugin" in url:
            self.uploads.append(data)
            if self.fail_upload:
                return 200, ("<html><div class='error'>Destination"
                             " folder already exists.</div></html>")
            link = ""
            if not self.no_activate_link:
                href = ('plugins.php?action=activate'
                        '&amp;plugin=ovo-enrichment%2Fovo-enrichment.php'
                        '&amp;_wpnonce=abc123def456')
                if not self.relative_link:
                    href = "/wp-admin/" + href
                link = f'<a href="{href}">Activate Plugin</a>'
            return 200, ("<html>Plugin installed successfully."
                         f"{link}</html>")
        return 404, "not found"

    def has_logged_in_cookie(self):
        return self.logged_in


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out_dir = Path(self.tmp.name) / "pkg"
        self.zip_path, self.sha256, self.version = \
            install_mod.build_package(self.out_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_package_has_version_and_hash(self):
        self.assertEqual(self.version, "1.0.0")
        self.assertEqual(len(self.sha256), 64)
        self.assertEqual(
            hashlib.sha256(self.zip_path.read_bytes()).hexdigest(),
            self.sha256)
        self.assertEqual(self.zip_path.name, "ovo-enrichment-1.0.0.zip")

    def test_package_holds_the_plugin_files(self):
        with zipfile.ZipFile(self.zip_path) as zf:
            names = sorted(zf.namelist())
        self.assertEqual(names, [
            "ovo-enrichment/EXAMPLE-DIFF.json",
            "ovo-enrichment/ovo-enrichment.php",
            "ovo-enrichment/readme.txt",
            "ovo-enrichment/uninstall.php",
            "ovo-enrichment/verify-live.sh",
        ])
        with zipfile.ZipFile(self.zip_path) as zf:
            header = zf.read("ovo-enrichment/ovo-enrichment.php").decode()
        self.assertIn("Version:           1.0.0", header)

    def test_package_is_stable(self):
        _, sha2, _ = install_mod.build_package(self.out_dir)
        self.assertEqual(sha2, self.sha256)

    def test_install_flow_end_to_end_fake(self):
        browser = FakeBrowser()
        record = install_mod.install_on_store(
            "https://store.example.com", "admin", "secret-password",
            self.zip_path, browser=browser)
        self.assertEqual(record["status"], "installed_and_active")
        self.assertEqual(record["version"], "1.0.0")
        self.assertEqual(record["steps"], [
            "wordpress_login", "upload_page", "plugin_uploaded",
            "plugin_activated", "manifest_answers"])
        self.assertEqual(len(browser.uploads), 1)
        self.assertIn(b"ovo-enrichment.php", browser.uploads[0])

    def test_install_resolves_bare_relative_activate_link(self):
        # WordPress returns the activate link relative to the
        # admin area, often without a leading slash. The installer
        # must resolve it to a full URL before fetching it.
        browser = FakeBrowser(relative_link=True)
        record = install_mod.install_on_store(
            "https://store.example.com", "admin", "secret-password",
            self.zip_path, browser=browser)
        self.assertEqual(record["status"], "installed_and_active")
        activate_urls = [u for u in browser.fetched_urls
                         if "action=activate" in u]
        self.assertEqual(len(activate_urls), 1)
        self.assertTrue(activate_urls[0].startswith(
            "https://store.example.com/wp-admin/plugins.php?"))

    def test_install_refuses_bad_login(self):
        browser = FakeBrowser(fail_login=True)
        with self.assertRaises(install_mod.InstallError) as ctx:
            install_mod.install_on_store(
                "https://store.example.com", "admin", "wrong-password",
                self.zip_path, browser=browser)
        self.assertIn("login failed", str(ctx.exception))
        self.assertEqual(browser.uploads, [])

    def test_install_refuses_failed_upload(self):
        browser = FakeBrowser(fail_upload=True)
        with self.assertRaises(install_mod.InstallError) as ctx:
            install_mod.install_on_store(
                "https://store.example.com", "admin", "secret-password",
                self.zip_path, browser=browser)
        self.assertIn("upload failed", str(ctx.exception))

    def test_install_refuses_missing_activate_link(self):
        browser = FakeBrowser(no_activate_link=True)
        with self.assertRaises(install_mod.InstallError) as ctx:
            install_mod.install_on_store(
                "https://store.example.com", "admin", "secret-password",
                self.zip_path, browser=browser)
        self.assertIn("no activate link", str(ctx.exception))

    def test_install_refuses_manifest_mismatch(self):
        browser = FakeBrowser(manifest_version="0.2.0-demo")
        with self.assertRaises(install_mod.InstallError) as ctx:
            install_mod.install_on_store(
                "https://store.example.com", "admin", "secret-password",
                self.zip_path, browser=browser)
        self.assertIn("version does not match", str(ctx.exception))

    def test_install_needs_credentials(self):
        browser = FakeBrowser()
        with self.assertRaises(install_mod.InstallError):
            install_mod.install_on_store(
                "https://store.example.com", "", "secret-password",
                self.zip_path, browser=browser)

    def test_password_never_reaches_the_record(self):
        browser = FakeBrowser()
        record = install_mod.install_on_store(
            "https://store.example.com", "admin", "secret-password",
            self.zip_path, browser=browser)
        self.assertNotIn("secret-password", json.dumps(record))


if __name__ == "__main__":
    unittest.main()
