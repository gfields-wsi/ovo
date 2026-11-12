#!/usr/bin/env python3
"""Small client for the Meta Model API.

This file is the only place that talks to Meta at run time.
It uses one service and one model only:
- Service: POST https://api.meta.ai/v1/chat/completions
- Model: muse-spark-1.3

How it gets a key, in order:
1. Read the key from the environment, from META_API_KEY.
   On a host, the host stores the key. The key never goes in code.
2. If no key is set, and the local helper exists on this
   machine, use that helper. That helper only works inside Muse.
   It does not exist on a host, so a host must use step 1.
3. If neither is present, stop with a clear error. Do not guess.

The key is never written to a log or a file by this client.
The reply from Meta is returned as given. The caller decides
what to do with it. A failed call returns an error, not a
made-up reply.

Use as a module:
    from meta_client import chat
    reply = chat(payload)

Use as a helper on the command line, the same way agents call the
local helper:
    python3 meta_client.py chat
Payload JSON goes in on stdin. Reply JSON comes out on stdout.
"""

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

MODEL = "muse-spark-1.3"
URL = "https://api.meta.ai/v1/chat/completions"
LOCAL_HELPER = Path.home() / "workspace/custom-connectors/custom.meta-model-api/bin/meta_model.py"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse a redirect, so a key never follows a new address."""

    def redirect_request(self, *args):
        raise RuntimeError("Redirect refused. Check the endpoint.")


def chat(payload):
    """Send one chat payload to Meta. Return the parsed reply."""
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a dict.")
    # The caller sets the model. If it did not, set Spark here,
    # so no other model can slip in by accident.
    payload = dict(payload)
    payload.setdefault("model", MODEL)
    if payload["model"] != MODEL:
        raise ValueError(f"Only {MODEL} is allowed in this runner.")

    key = os.environ.get("META_API_KEY") or os.environ.get("META_MODEL_API_KEY")
    if key:
        request = urllib.request.Request(
            URL,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
        )
        opener = urllib.request.build_opener(NoRedirect())
        with opener.open(request, timeout=120) as response:
            return json.loads(response.read().decode(errors="replace"))

    if LOCAL_HELPER.exists():
        proc = subprocess.run(
            [sys.executable, str(LOCAL_HELPER), "chat"],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=120,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Local helper failed: {proc.stderr[:500]}")
        return json.loads(proc.stdout)

    raise RuntimeError(
        "No Meta key found. Set META_API_KEY in the host safe store. "
        "No key is stored in code."
    )


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] != "chat":
        print("Usage: python3 meta_client.py chat", file=sys.stderr)
        print("Payload JSON goes in on stdin. Reply JSON comes out on stdout.",
              file=sys.stderr)
        raise SystemExit(2)
    try:
        payload = json.loads(sys.stdin.read())
    except ValueError as exc:
        print(f"Payload is not valid JSON: {exc}", file=sys.stderr)
        raise SystemExit(2)
    try:
        print(json.dumps(chat(payload)))
    except Exception as exc:  # noqa: BLE001 - CLI error, message only
        print(f"Meta call failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
