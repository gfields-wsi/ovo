#!/usr/bin/env python3
"""OvO API server for Render.

One web service, one port, three parts behind it:

- The agent service: POST /mcp, the five MCP tools from Phase 5.
  It never approves, never publishes, and never takes a payment.
- The merchant site API and pages: /api/*, /review/*, /static/*,
  and /downloads/*, from Phase 4. The pages themselves stay on
  the web server as static files; they call this API on Render.
- Run health: GET /health and GET /health/runs. A stuck run
  shows here within one hour. A run waiting for approval shows
  as normal, whatever its age. This is a pull report only. It
  sends nothing to anyone.

The public manifest is served at GET /.well-known/ovo, from
the file in ovo-mcp-service/public. That file is in the repo.
Serving it here is code only: it does not deploy the manifest
live to the OvO site. That step stays with the web server.

On Render, DATABASE_URL is set by the Blueprint, and all three
stores use Postgres. Locally, with no DATABASE_URL, the stores
use their SQLite files, as before. The port comes from PORT,
which Render sets. The host is 0.0.0.0 when PORT is set, and
127.0.0.1 otherwise.

No key, password, token, or card number is ever logged here.
Requests are logged as method, path, and status only. No
request body and no header is ever logged.
"""
import importlib.util
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT / "ovo-mcp-service"))

import health  # noqa: E402
import postgres_store  # noqa: E402
from service import McpService, SERVICE_NAME, SERVICE_VERSION  # noqa: E402

MANIFEST_PATH = (REPO_ROOT / "ovo-mcp-service" / "public"
                 / ".well-known" / "ovo")
API_VERSION = "1.0.0"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_merchant_app(database_url=None):
    """Load the merchant site app module. When a Postgres
    address is set, its store is replaced with the Postgres
    merchant store, so the review, decision, install, order,
    and billing calls all read and write Postgres. When no
    address is set, its SQLite store is left alone."""
    app = _load_module(
        "ovo_merchant_app", REPO_ROOT / "ovo-merchant-site" / "app.py")
    if database_url:
        app.STORE = postgres_store.open_merchant_store(database_url)
    return app


def make_handler(service, merchant_app, database_url=None):
    merchant_handler = merchant_app.Handler

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # noqa: D102 - method, path, status only
            sys.stderr.write(f"{self.command} {self.path} {args[1]}\n")

        def _send(self, status, body, content_type="application/json"):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _run_store(self):
            return postgres_store.open_run_store(database_url)

        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler name
            if self.path in ("/health", "/health/"):
                self._send(200, json.dumps({
                    "service": "ovo-api",
                    "version": API_VERSION,
                    "agent_service": SERVICE_NAME,
                    "agent_version": SERVICE_VERSION,
                    "status": "ok",
                }))
            elif self.path in ("/health/runs", "/health/runs/"):
                store = self._run_store()
                try:
                    self._send(200, json.dumps(
                        health.health_summary(store)))
                finally:
                    store.close()
            elif self.path.startswith("/health/runs/"):
                run_key = self.path[len("/health/runs/"):].strip("/")
                store = self._run_store()
                try:
                    record = store.export_run(run_key)
                finally:
                    store.close()
                if record is None:
                    self._send(404, json.dumps(
                        {"error": f"no run with key {run_key}"}))
                    return
                stages = record.get("stages") or []
                record["health_state"] = health.classify_run(
                    record, stages)
                self._send(200, json.dumps(record))
            elif self.path in ("/.well-known/ovo", "/.well-known/ovo/"):
                try:
                    self._send(200, MANIFEST_PATH.read_bytes())
                except FileNotFoundError:
                    self._send(404, json.dumps(
                        {"error": "manifest not found"}))
            else:
                merchant_handler.do_GET(self)

        def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler name
            if self.path in ("/mcp", "/mcp/"):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                try:
                    payload = json.loads(raw.decode("utf-8")) if raw else {}
                except ValueError:
                    self._send(200, json.dumps({
                        "jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700,
                                  "message": "Parse error"}}))
                    return
                key = self.headers.get("X-OvO-Key")
                result = service.handle(payload, key=key)
                if result is None:
                    self.send_response(202)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self._send(200, json.dumps(result))
            else:
                merchant_handler.do_POST(self)

    return Handler


def main():
    database_url = os.environ.get("DATABASE_URL") or None
    port = int(os.environ.get("PORT")
               or os.environ.get("OVO_API_PORT", "8080"))
    host = os.environ.get("OVO_HOST") or (
        "0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
    merchant_app = load_merchant_app(database_url)
    service = McpService(
        REPO_ROOT / "ovo-mcp-service" / "mcp.db",
        database_url=database_url)
    try:
        server = ThreadingHTTPServer(
            (host, port), make_handler(service, merchant_app, database_url))
        print(f"OvO API {API_VERSION} on {host}:{port}")
        server.serve_forever()
    finally:
        service.close()


if __name__ == "__main__":
    main()
