#!/usr/bin/env python3
"""The OvO merchant site app.

One small HTTP app, standard library only. It serves the
merchant pages and the API the pages call:

  GET  /                              index
  GET  /review/<run_key>              the approval screen
  GET  /static/<file>                 styles and review script
  GET  /downloads/<zip>               the plugin zip, with its hash
  GET  /health                        liveness
  GET  /api/review/<run_key>          the packet as JSON
  GET  /api/billing/<merchant>?y&m    the monthly bill
  POST /api/signin                    OvO site sign-in
  POST /api/wordpress-signin          WordPress sign-in, verified
  POST /api/card-auth                 card authorization reference
  POST /api/packets                   deliver a packet for review
  POST /api/decide                    record a merchant decision
  POST /api/install                   Install OvO Plugins, one press
  POST /api/orders                    record a paid order
  POST /api/refund                    record a refund

The pages are plain files under static/, so the same pages can
deploy to the web server as static files and call this API on
Render. The database path comes from OVO_MERCHANT_DB, or a file
next to this app. Nothing here logs a password, a token, or a
key. The Stripe secret key is read from the environment only
when a live Stripe call is about to happen, and no live Stripe
call happens in this phase.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import approval  # noqa: E402
import auth  # noqa: E402
import billing  # noqa: E402
import install as install_mod  # noqa: E402
import attribution  # noqa: E402
from store import MerchantStore  # noqa: E402

DB_PATH = os.environ.get("OVO_MERCHANT_DB") or str(HERE / "ovo-merchant-site.db")
STORE = MerchantStore(DB_PATH)
PACKAGE_DIR = HERE / "downloads"
PACKAGE_DIR.mkdir(exist_ok=True)

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json",
}


def _json(handler, status, payload):
    body = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _html(handler, status, page):
    body = page.encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler):
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length) if length else b""
    if not raw:
        return {}
    try:
        return json.loads(raw.decode())
    except ValueError:
        return {"_bad_json": True}


def _require_session(data, store_id):
    token = data.get("session_token")
    if not token:
        return None, "session token is missing"
    session, error = auth.verify_session(STORE, token, store_id)
    if error:
        return None, error
    return session, None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        # Log method, path, and status only. Never log a body.
        sys.stderr.write(f"{self.command} {self.path} {args[1]}\n")

    # -- GET ------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            _html(self, 200, INDEX_PAGE)
        elif path == "/health":
            _json(self, 200, {"ok": True})
        elif path.startswith("/static/"):
            name = path[len("/static/"):]
            file_path = HERE / "static" / name
            if ".." in name or not file_path.exists():
                _json(self, 404, {"error": "not found"})
                return
            suffix = file_path.suffix
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type",
                             CONTENT_TYPES.get(suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path.startswith("/downloads/"):
            name = path[len("/downloads/"):]
            file_path = PACKAGE_DIR / name
            if ".." in name or not file_path.exists():
                _json(self, 404, {"error": "not found"})
                return
            import hashlib
            digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("X-SHA256", digest)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path.startswith("/review/"):
            run_key = path[len("/review/"):]
            saved = STORE.get_packet(run_key)
            if not saved:
                _json(self, 404, {"error": "no packet for this run"})
                return
            _html(self, 200, approval.render_review_html(
                saved["packet"], run_key))
        elif path.startswith("/api/review/"):
            run_key = path[len("/api/review/"):]
            saved = STORE.get_packet(run_key)
            if not saved:
                _json(self, 404, {"error": "no packet for this run"})
                return
            _json(self, 200, saved["packet"])
        elif path.startswith("/api/billing/"):
            merchant_id = path[len("/api/billing/"):]
            query = parse_qs(parsed.query)
            try:
                year = int(query.get("year", ["0"])[0])
                month = int(query.get("month", ["0"])[0])
            except ValueError:
                _json(self, 400, {"error": "year and month must be numbers"})
                return
            _json(self, 200, billing.monthly_bill(
                STORE, merchant_id, year, month))
        else:
            _json(self, 404, {"error": "not found"})

    # -- POST -----------------------------------------------------
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        data = _read_body(self)
        if data.get("_bad_json"):
            _json(self, 400, {"error": "body is not JSON"})
            return
        if path == "/api/signin":
            result, error = auth.sign_in_ovo(
                STORE, data.get("merchant_id"), data.get("password"),
                data.get("store_id"))
            if error:
                _json(self, 401, {"error": error})
            else:
                _json(self, 200, result)
        elif path == "/api/wordpress-signin":
            session, error = _require_session(data, data.get("store_url"))
            if error:
                _json(self, 401, {"error": error})
                return
            verification, error = auth.verify_wordpress_signin(
                data.get("store_url"), data.get("wp_username"),
                data.get("app_password"))
            if error:
                _json(self, 403, {"error": error})
                return
            auth.record_wordpress_signin(STORE, session["merchant_id"],
                                         verification)
            _json(self, 200, {"verified": True, **verification})
        elif path == "/api/card-auth":
            session, error = _require_session(data, None)
            if error:
                _json(self, 401, {"error": error})
                return
            result, error = auth.record_card_authorization(
                STORE, session["merchant_id"], data.get("auth_ref"),
                data.get("brand"), data.get("last4"))
            if error:
                _json(self, 400, {"error": error})
            else:
                _json(self, 200, result)
        elif path == "/api/packets":
            session, error = _require_session(data, data.get("store_id"))
            if error:
                _json(self, 401, {"error": error})
                return
            packet = data.get("packet")
            run_key = data.get("run_key")
            if not packet or not run_key:
                _json(self, 400, {"error": "run_key and packet are required"})
                return
            STORE.save_packet(run_key, packet.get("store_id"),
                              session["merchant_id"], packet,
                              billing.now_utc())
            _json(self, 200, {"saved": True, "run_key": run_key})
        elif path == "/api/decide":
            run_key = data.get("run_key")
            saved = STORE.get_packet(run_key) if run_key else None
            if not saved:
                _json(self, 404, {"error": "no packet for this run"})
                return
            session, error = _require_session(
                data, saved["packet"].get("store_id"))
            if error:
                _json(self, 401, {"error": error})
                return
            record, errors = approval.record_decision(
                STORE, session, saved["packet"], data.get("groups", []),
                data.get("approved_by", ""), run_key=run_key)
            if errors:
                _json(self, 400, {"errors": errors})
            else:
                _json(self, 200, {"record": record})
        elif path == "/api/install":
            session, error = _require_session(data, data.get("store_url"))
            if error:
                _json(self, 401, {"error": error})
                return
            wp_signin = STORE.latest_wp_signin(
                session["merchant_id"], data.get("store_url"))
            if not wp_signin:
                _json(self, 403, {"error": "sign in to WordPress first:"
                                           " Install needs a verified"
                                           " WordPress sign-in"})
                return
            zip_path, digest, version = install_mod.build_package(
                PACKAGE_DIR)
            try:
                record = install_mod.install_on_store(
                    data.get("store_url"), data.get("wp_username"),
                    data.get("wp_password"), zip_path)
            except install_mod.InstallError as exc:
                _json(self, 502, {"error": str(exc)})
                return
            STORE.record_install(
                data.get("store_url"), record["plugin"],
                record["version"], record["status"],
                True, billing.now_utc(), record)
            _json(self, 200, {"install": record, "zip_sha256": digest})
        elif path == "/api/orders":
            session, error = _require_session(data, data.get("store_url"))
            if error:
                _json(self, 401, {"error": error})
                return
            try:
                if data.get("cart_id"):
                    order = attribution.record_linked_order(
                        STORE, session["merchant_id"],
                        data.get("order_id"), data.get("subtotal_cents"),
                        data.get("currency"), data.get("store_url"),
                        data.get("cart_id"),
                        actor=data.get("actor", "agent"),
                        paid_at=data.get("paid_at"))
                else:
                    order = attribution.record_human_order(
                        STORE, session["merchant_id"],
                        data.get("order_id"), data.get("subtotal_cents"),
                        data.get("currency"), data.get("store_url"),
                        paid_at=data.get("paid_at"))
            except ValueError as exc:
                _json(self, 400, {"error": str(exc)})
                return
            _json(self, 200, {"order": order})
        elif path == "/api/refund":
            session, error = _require_session(data, None)
            if error:
                _json(self, 401, {"error": error})
                return
            try:
                order = billing.record_refund(
                    STORE, data.get("order_id"), data.get("refunded_at"))
            except ValueError as exc:
                _json(self, 400, {"error": str(exc)})
                return
            _json(self, 200, {"order": order})
        else:
            _json(self, 404, {"error": "not found"})


INDEX_PAGE = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>OvO merchant site</title>
<link rel="stylesheet" href="/static/styles.css"></head>
<body><div class="modal">
<h1>OvO merchant site</h1>
<p>Sign in, review your store fixes, install the OvO plugins,
and see your bill. The review screen is one page per run:
ask the OvO agent for your review link.</p>
<p>Health: <a href="/health">/health</a></p>
</div></body></html>
"""


def main():
    port = int(os.environ.get("OVO_MERCHANT_PORT", "8765"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"OvO merchant site on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
