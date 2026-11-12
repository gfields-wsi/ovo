#!/usr/bin/env python3
"""Tests for the public manifest and the registry listing: the
file in the repo answers at its fixed address, and only verified
stores are named in a listing."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service import (TOOLS, build_public_manifest, build_registry_listing)
from mcp_store import McpStore

HERE = Path(__file__).resolve().parents[1]
MANIFEST_PATH = HERE / "public" / ".well-known" / "ovo"
LISTING_PATH = HERE / "registry-listing.json"


class ManifestTest(unittest.TestCase):
    def test_manifest_file_matches_the_builder(self):
        stored = json.loads(MANIFEST_PATH.read_text())
        built = build_public_manifest(
            "https://wsiventures.com/ovo/mcp",
            "https://wsiventures.com/ovo", TOOLS)
        self.assertEqual(stored, built)

    def test_manifest_names_the_service_tools_and_rules(self):
        manifest = json.loads(MANIFEST_PATH.read_text())
        self.assertEqual(manifest["name"], "OvO")
        self.assertEqual(manifest["scope"].split(" only")[0],
                         "WordPress + WooCommerce")
        self.assertEqual(manifest["mcp_endpoint"],
                         "https://wsiventures.com/ovo/mcp")
        self.assertEqual([t["name"] for t in manifest["tools"]],
                         ["ovo_start_check", "ovo_run_status", "ovo_scorecard",
                          "ovo_approval_packet", "ovo_store_manifest"])
        rules = " ".join(manifest["rules"])
        self.assertIn("never approves", rules)
        self.assertIn("never publishes", rules)
        self.assertIn("never takes a payment", rules)
        self.assertIn("merchant stays the seller", rules)
        self.assertIn("One scoped key per store", rules)

    def test_manifest_served_locally_and_read_back(self):
        """Serve the public folder on localhost and read the
        manifest back from its fixed address."""
        root = HERE / "public"
        handler = lambda *a, **k: SimpleHTTPRequestHandler(
            *a, directory=str(root), **k)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/.well-known/ovo",
                    timeout=10) as resp:
                self.assertEqual(resp.status, 200)
                manifest = json.loads(resp.read().decode())
            self.assertEqual(manifest["name"], "OvO")
            self.assertEqual(len(manifest["tools"]), 5)
        finally:
            server.shutdown()
            server.server_close()

    def test_registry_listing_is_prepared_and_names_woocommerce_only(self):
        listing = json.loads(LISTING_PATH.read_text())
        self.assertEqual(listing["name"], "OvO")
        self.assertEqual(listing["platform"], "WooCommerce only")
        self.assertEqual(listing["manifest_url"],
                         "https://wsiventures.com/ovo/.well-known/ovo")
        self.assertEqual(listing["tools"],
                         ["ovo_start_check", "ovo_run_status", "ovo_scorecard",
                          "ovo_approval_packet", "ovo_store_manifest"])
        rules = " ".join(listing["rules"])
        self.assertIn("merchant approves", rules.lower())
        self.assertIn("merchant stays the seller", rules.lower())

    def test_listing_names_verified_stores_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = McpStore(Path(tmp) / "mcp.db")
            store.record_domain("https://verified.example", "m1", "verified",
                                "check_file", "2026-11-12T00:00:00+00:00", "")
            store.record_domain("https://unchecked.example", "m2", "unchecked",
                                "check_file", "2026-11-12T00:00:00+00:00", "")
            verified = store.verified_stores()
            store.close()
        listing = build_registry_listing(
            "https://wsiventures.com/ovo/.well-known/ovo",
            "https://wsiventures.com/ovo", TOOLS, verified)
        self.assertEqual(listing["verified_stores"], ["https://verified.example"])


if __name__ == "__main__":
    unittest.main()
