#!/usr/bin/env python3
"""HTTP front for the OvO MCP service.

Stdlib only. Two routes:

- POST /mcp: JSON-RPC 2.0 (MCP Streamable HTTP shape). The scoped
  key arrives as the X-OvO-Key header.
- GET /.well-known/ovo: the public manifest file, served as JSON.
- GET /health: a plain health answer, no key needed.

Run it with: python3 server.py --db /path/to/mcp.db --port 8080
On Render, DATABASE_URL is set by the Blueprint, and the
stores use Postgres. Locally, with no DATABASE_URL, the
stores use SQLite files, as before.
The manifest file lives in public/.well-known/ovo next to this
file. Static pages and the manifest deploy to the web server;
this API runs on Render.
"""
import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from service import McpService, SERVICE_NAME, SERVICE_VERSION

HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / "public" / ".well-known" / "ovo"


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # noqa: D102 - keep test output clean
            pass

        def _send(self, status, body, content_type="application/json"):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler name
            if self.path in ("/health", "/health/"):
                self._send(200, json.dumps({
                    "service": SERVICE_NAME,
                    "version": SERVICE_VERSION,
                    "status": "ok",
                }))
            elif self.path in ("/.well-known/ovo", "/.well-known/ovo/"):
                try:
                    self._send(200, MANIFEST_PATH.read_bytes())
                except FileNotFoundError:
                    self._send(404, json.dumps({"error": "manifest not found"}))
            else:
                self._send(404, json.dumps({"error": "not found"}))

        def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler name
            if self.path not in ("/mcp", "/mcp/"):
                self._send(404, json.dumps({"error": "not found"}))
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else {}
            except ValueError:
                self._send(200, json.dumps({
                    "jsonrpc": "2.0", "id": None,
                    "error": {"code": -32700, "message": "Parse error"}}))
                return
            key = self.headers.get("X-OvO-Key")
            result = service.handle(payload, key=key)
            if result is None:
                self.send_response(202)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._send(200, json.dumps(result))

    return Handler


def main():
    parser = argparse.ArgumentParser(description="OvO MCP service")
    parser.add_argument("--db", default=None,
                        help="MCP store file. Default is mcp.db next to server.py.")
    parser.add_argument("--runner-db", default=None,
                        help="Runner store file. Default is ovo-runner/ovo_runs.db.")
    parser.add_argument("--database-url", default=None,
                        help="Postgres address. Defaults to DATABASE_URL. "
                             "When set, the stores use Postgres.")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    service = McpService(args.db or HERE / "mcp.db",
                         runner_db_path=args.runner_db,
                         database_url=args.database_url or os.environ.get("DATABASE_URL"))
    try:
        server = ThreadingHTTPServer((args.host, args.port), make_handler(service))
        print(f"{SERVICE_NAME} {SERVICE_VERSION} on {args.host}:{args.port}")
        server.serve_forever()
    finally:
        service.close()


if __name__ == "__main__":
    main()
