#!/usr/bin/env python3
"""Install OvO Plugins.

The merchant, while signed in, presses Install OvO Plugins
once. OvO then handles the plugin download and activation. No
manual file upload happens in the live flow. The plugin zip is
built from the repo and served by download from the OvO site.

The install runs against the store's own WordPress admin, with
the merchant's WordPress sign-in, in the merchant's own
browser session. The steps are the same ones a merchant would
take by hand: log in, open the plugin upload page, upload the
zip, activate it. OvO does them in one press instead. The
WordPress password is used for this one call only. It is never
stored, never written to a file, and never written to a log.

The plugin zip holds the same five files the production test
install proved: the plugin, the readme, the uninstaller, the
example diff, and the live check script.
"""
import hashlib
import http.cookiejar
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
PLUGIN_DIR = REPO_ROOT / "ovo-plugin-agent" / "ovo-enrichment"
PLUGIN_SLUG = "ovo-enrichment"
PLUGIN_FILES = ["ovo-enrichment.php", "readme.txt", "uninstall.php",
                "EXAMPLE-DIFF.json", "verify-live.sh"]


class InstallError(Exception):
    pass


def plugin_version():
    """Version from the plugin header. The zip name carries it."""
    header = (PLUGIN_DIR / "ovo-enrichment.php").read_text()
    match = re.search(r"^\s*\*\s*Version:\s*(\S+)\s*$", header, re.M)
    if not match:
        raise InstallError("plugin header has no Version line")
    return match.group(1)


def build_package(out_dir):
    """Zip the plugin. Returns (zip_path, sha256, version). The
    zip holds one top folder, named for the plugin slug, so
    WordPress installs it under that name."""
    version = plugin_version()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"ovo-enrichment-{version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(PLUGIN_FILES):
            path = PLUGIN_DIR / name
            if not path.exists():
                raise InstallError(f"plugin file missing: {name}")
            zf.write(path, f"{PLUGIN_SLUG}/{name}")
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    return zip_path, digest, version


def _multipart(fields, files):
    """Build a multipart/form-data body. fields is a list of
    (name, value); files is a list of (name, filename, bytes)."""
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in fields:
        body += f"--{boundary}\r\n".encode()
        body += (f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                 f"{value}\r\n").encode()
    for name, filename, data in files:
        body += f"--{boundary}\r\n".encode()
        body += (f'Content-Disposition: form-data; name="{name}";'
                 f' filename="{filename}"\r\n'
                 f"Content-Type: application/zip\r\n\r\n").encode()
        body += data
        body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), boundary


class _Browser:
    """A small cookie browser over urllib. Used for the WordPress
    admin steps. Nothing it carries is logged."""

    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))

    def get(self, url, headers=None):
        req = urllib.request.Request(url, headers=headers or {})
        with self.opener.open(req, timeout=60) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")

    def post(self, url, data, headers=None):
        req = urllib.request.Request(url, data=data,
                                     headers=headers or {}, method="POST")
        with self.opener.open(req, timeout=120) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")

    def has_logged_in_cookie(self):
        return any("wordpress_logged_in_" in c.name for c in self.jar)


def _find_nonce(page, action):
    """Find the _wpnonce value for a WordPress admin form."""
    match = re.search(
        r'name="_wpnonce"\s+value="([0-9a-f]+)"', page)
    if not match:
        raise InstallError(f"WordPress nonce not found for {action}")
    return match.group(1)


def install_on_store(store_url, wp_username, wp_password, zip_path,
                     browser=None):
    """Install and activate the plugin on the store, in one press.
    Returns an install record. The WordPress password is used
    only inside this call. Raises InstallError on any failure,
    with the step named."""
    store_url = store_url.rstrip("/")
    if not wp_username or not wp_password:
        raise InstallError("WordPress username and password are required")
    zip_path = Path(zip_path)
    if not zip_path.exists():
        raise InstallError(f"plugin zip not found: {zip_path}")
    browser = browser or _Browser()
    steps = []
    try:
        # 1. Log in to WordPress.
        browser.get(f"{store_url}/wp-login.php")
        status, _ = browser.post(
            f"{store_url}/wp-login.php",
            urllib.parse.urlencode({
                "log": wp_username, "pwd": wp_password,
                "rememberme": "forever", "testcookie": "1",
                "redirect_to": f"{store_url}/wp-admin/",
            }).encode())
        if status != 200 or not browser.has_logged_in_cookie():
            raise InstallError("WordPress login failed: check the"
                               " username and password")
        steps.append("wordpress_login")
        # 2. Open the plugin upload page and take its nonce.
        status, page = browser.get(
            f"{store_url}/wp-admin/plugin-install.php?tab=upload")
        if status != 200:
            raise InstallError("WordPress plugin upload page did not load")
        nonce = _find_nonce(page, "plugin upload")
        steps.append("upload_page")
        # 3. Upload the zip.
        body, boundary = _multipart(
            [("_wpnonce", nonce),
             ("_wp_http_referer", "/wp-admin/plugin-install.php?tab=upload")],
            [("pluginzip", zip_path.name, zip_path.read_bytes())])
        status, page = browser.post(
            f"{store_url}/wp-admin/update.php?action=upload-plugin",
            body,
            {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        if status != 200:
            raise InstallError("plugin upload failed: HTTP"
                               f" {status}")
        if "Plugin installed successfully" not in page:
            detail = re.sub(r"<[^>]+>", " ", page)
            detail = " ".join(detail.split())[:200]
            raise InstallError("plugin upload failed: "
                               f"{detail or 'no success message'}")
        steps.append("plugin_uploaded")
        # 4. Activate it from the link WordPress returns.
        match = re.search(
            r'href="([^"]*action=activate[^"]*plugin='
            r'ovo-enrichment[^"]*)"', page)
        if not match:
            raise InstallError("plugin uploaded but no activate link"
                               " was returned")
        activate_url = match.group(1).replace("&amp;", "&")
        # WordPress returns the link relative to the admin area,
        # often without a leading slash. Resolve it against the
        # upload page, not by string guesswork.
        activate_url = urllib.parse.urljoin(
            f"{store_url}/wp-admin/update.php?action=upload-plugin",
            activate_url)
        status, page = browser.get(activate_url)
        if status != 200:
            raise InstallError("plugin activation failed: HTTP"
                               f" {status}")
        if "Plugin activated" not in page and "activated" not in page.lower():
            raise InstallError("plugin activation failed: no"
                               " confirmation returned")
        steps.append("plugin_activated")
        # 5. Prove it: the manifest answers.
        status, body_text = browser.get(f"{store_url}/wp-json/ovo/v1/manifest")
        if status != 200:
            raise InstallError("plugin installed but the manifest"
                               f" does not answer: HTTP {status}")
        import json
        manifest = json.loads(body_text)
        if manifest.get("version") != plugin_version():
            raise InstallError("plugin installed but the manifest"
                               " version does not match the zip")
        steps.append("manifest_answers")
    except urllib.error.HTTPError as exc:
        raise InstallError(f"WordPress call failed at step"
                           f" {steps[-1] if steps else 'start'}:"
                           f" HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise InstallError(f"store not reached: {exc}")
    return {"status": "installed_and_active",
            "plugin": PLUGIN_SLUG,
            "version": plugin_version(),
            "store_url": store_url,
            "steps": steps,
            "manifest_version": manifest.get("version")}
