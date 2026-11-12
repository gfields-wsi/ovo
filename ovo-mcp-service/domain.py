#!/usr/bin/env python3
"""Domain ownership check for the OvO MCP service.

A store is checked before it goes live in any listing. The
merchant proves they own the web address in one of two ways:

1. Check file. The merchant places a file at
   <store>/.well-known/ovo-ownership.txt whose first line is
   exactly "ovo-ownership <merchant_id>".
2. WordPress admin proof. The merchant signs in with a WordPress
   admin account (username plus an application password). The
   service reads /wp-json/wp/v2/users/me and requires the
   install_plugins capability, which only an admin has.

A store with no passed check stays "unchecked" and lives in a
test area. It never appears in a listing. A passed check records
"verified" with the method used. A failed check records the
reason, so the merchant can see what to fix.
"""
import base64
import json
import urllib.error
import urllib.request

CHECK_FILENAME = ".well-known/ovo-ownership.txt"


def check_file(store_url, merchant_id, http_get=None):
    """Fetch the ownership file from the store and compare its
    first line. Returns (passed, detail)."""
    url = store_url.rstrip("/") + "/" + CHECK_FILENAME
    get = http_get or _default_http_get
    try:
        status, body = get(url)
    except Exception as exc:  # noqa: BLE001 - a failed fetch is a failed check
        return False, f"could not read {url}: {exc}"
    if status != 200:
        return False, f"{url} answered HTTP {status}"
    first = (body or "").strip().splitlines()[0].strip() if (body or "").strip() else ""
    expected = f"ovo-ownership {merchant_id}"
    if first == expected:
        return True, f"check file matches merchant {merchant_id}"
    return False, f"check file first line is not '{expected}'"


def check_wordpress_admin(store_url, wp_username, app_password, http_get=None):
    """Prove WordPress admin rights on the store. Returns
    (passed, detail)."""
    url = store_url.rstrip("/") + "/wp-json/wp/v2/users/me"
    token = base64.b64encode(f"{wp_username}:{app_password}".encode()).decode()
    get = http_get or _default_http_get
    try:
        status, body = get(url, headers={"Authorization": f"Basic {token}"})
    except Exception as exc:  # noqa: BLE001 - a failed fetch is a failed check
        return False, f"could not read {url}: {exc}"
    if status == 401:
        return False, "WordPress sign-in refused (401)"
    if status != 200:
        return False, f"{url} answered HTTP {status}"
    try:
        me = json.loads(body)
    except ValueError:
        return False, "WordPress answer is not valid JSON"
    capabilities = me.get("capabilities") or {}
    if capabilities.get("install_plugins"):
        return True, f"WordPress admin proof for {me.get('slug') or wp_username}"
    return False, "WordPress account has no install_plugins right"


def check_domain(store, store_url, merchant_id, method="check_file",
                 wp_username=None, app_password=None, http_get=None,
                 checked_at=None):
    """Run one ownership check and record it. Returns
    (passed, status, detail). Status is "verified" or "unchecked"."""
    if method == "wordpress_admin":
        passed, detail = check_wordpress_admin(
            store_url, wp_username, app_password, http_get=http_get)
    else:
        passed, detail = check_file(store_url, merchant_id, http_get=http_get)
    status = "verified" if passed else "unchecked"
    store.record_domain(store_url, merchant_id, status,
                        "wordpress_admin" if method == "wordpress_admin" else "check_file",
                        checked_at or "", detail)
    return passed, status, detail


def _default_http_get(url, headers=None):
    """Plain GET with a short timeout. Returns (status, body text).
    Redirects are off: the proof must come from the store itself."""
    request = urllib.request.Request(url, method="GET", headers=headers or {})
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects. A proof that bounces to another host
    proves nothing about this store."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
