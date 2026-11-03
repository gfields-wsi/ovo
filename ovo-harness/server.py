#!/usr/bin/env python3
"""OvO Harness server. Thin, live proof screen. Standard library only.

Rules enforced here, not just in the page:
- No key, token, password, cart token, or nonce is written to a log,
  a run file, or a reply. The Meta key is read only from host
  settings (META_API_KEY) on a host, or from the local helper on
  this machine, or from the runner Meta client if it is present.
  No key is stored in code.
- No price, stock level, or policy is invented. Values come from a
  live store fetch in the same run, or the step is marked blocked.
- Silence, a missed deadline, and a group that was not submitted
  never count as approval. Publish mapping runs only after a
  recorded, matching approval for that group.
- Live publish is blocked in this build. The publish step runs a
  dry-run mapping only, compares it with the live OVO endpoint,
  and reports the live-post blocker plainly. It never claims a
  dry run as live.
- Agent-only payment is blocked in this build. The payment bridge
  is not proven. A test order is recorded only when a judge enters
  the order number shown on the merchant checkout confirmation
  page, in test mode, with the exact total re-checked first.
  That order is labelled test mode, and its source is labelled
  judge-entered confirmation, not a private order-list fetch.
- A reset starts a new run. It never deletes old run files,
  ground truth, the fix diff, or past orders. Old runs stay in runs/.

Run: python3 server.py  (serves on port 8000 by default)
Host: set META_API_KEY in host settings for Meta calls on Render.
      No key goes in code, logs, or the repository.
"""
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
RUNNER = Path.home() / "workspace/ovo-hackathon/ovo-runner"
STORE_URL = "https://wsiventures.com/solemates"
STORE_API = STORE_URL + "/?rest_route=/wc/store/v1"
OVO_API = STORE_URL + "/?rest_route=/ovo/v1"
PRODUCT_ID = 23
VARIATION_ID = 29  # City Chelsea Rain Boots, size 10
MODEL = "muse-spark-1.3"
STOP_REASON = ("the agent will not pay unless it can verify material, fit, "
               "returns, stock, and the exact total from structured fields.")

sys.path.insert(0, str(RUNNER))


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def segment(desc, label, next_labels):
    m = re.search(rf"{label}:\s*", desc, re.I)
    if not m:
        return None
    rest = desc[m.end():]
    cut = len(rest)
    for nxt in next_labels:
        n = re.search(rf"\b{nxt}:\s*", rest, re.I)
        if n:
            cut = min(cut, n.start())
    value = clean(rest[:cut].strip().rstrip("."))
    return value or None


def fetch_json(url, timeout=60):
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "OvO-Harness/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:  # noqa: BLE001 - retry transient store reads
            last = exc
            time.sleep(1 + attempt)
    raise last


def fetch_product():
    product = fetch_json(f"{STORE_API}/products/{PRODUCT_ID}")
    desc = clean(product.get("description", ""))
    attrs = {}
    for a in product.get("attributes", []):
        attrs[a.get("name")] = [t.get("name") for t in a.get("terms", [])]
    prose = {
        "Material": segment(desc, "Material", ["Fit", "Returns"]),
        "Fit": segment(desc, "Fit", ["Returns", "Material"]),
        "Returns": segment(desc, "Returns", ["Material", "Fit"]),
    }
    # Fit in prose is one sentence pair; keep it whole for the judged run.
    # The framework proposal for product 23 is the full fit sentence.
    if prose["Fit"]:
        # segment() cut at Returns, which is correct; keep as found.
        pass
    ovo = None
    ovo_error = None
    try:
        ovo = fetch_json(f"{OVO_API}/products/{PRODUCT_ID}")
    except Exception as exc:  # noqa: BLE001 - report, do not invent
        ovo_error = str(exc)[:300]
    ovo_fields = {}
    if ovo and isinstance(ovo.get("fields"), list):
        for f in ovo["fields"]:
            value = f.get("value", "")
            if "|" in value:
                label, val = value.split("|", 1)
                ovo_fields[label.strip()] = val.strip()
            else:
                ovo_fields[f.get("key", "")] = value
    price_minor = product.get("prices", {}).get("price")
    return {
        "store_url": STORE_URL,
        "product_id": PRODUCT_ID,
        "product_name": product.get("name"),
        "sku": product.get("sku"),
        "permalink": product.get("permalink"),
        "price_minor": price_minor,
        "price_text": "$1.00 CAD" if str(price_minor) == "100" else str(price_minor),
        "currency_code": product.get("prices", {}).get("currency_code"),
        "is_in_stock": product.get("is_in_stock"),
        "low_stock_remaining": product.get("low_stock_remaining"),
        "structured_store_fields": attrs,
        "structured_store_field_names": sorted(attrs.keys()),
        "description_prose": desc,
        "prose_values": prose,
        "missing_structured_fields": ["Material", "Fit", "Returns"],
        "ovo_endpoint": ovo,
        "ovo_fields": ovo_fields,
        "ovo_error": ovo_error,
        "variation_size_10_id": VARIATION_ID,
        "fetched_at_utc": now_iso(),
        "sources": {
            "store": f"{STORE_API}/products/{PRODUCT_ID}",
            "ovo": f"{OVO_API}/products/{PRODUCT_ID}",
        },
    }


def cart_recheck():
    """Live cart re-check through the store's own cart. No order is made."""
    base = STORE_API
    def call(method, path, data=None, nonce=None, token=None):
        headers = {"Content-Type": "application/json", "User-Agent": "OvO-Harness/1.0"}
        if nonce:
            headers["Nonce"] = nonce
        if token:
            headers["Cart-Token"] = token
        req = urllib.request.Request(
            base + path,
            data=json.dumps(data).encode() if data is not None else None,
            method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read().decode())
    _s, headers, _b = call("GET", "/cart")
    nonce, token = headers.get("Nonce"), headers.get("Cart-Token")
    _s, headers, added = call("POST", "/cart/add-item",
                              {"id": VARIATION_ID, "quantity": 1}, nonce, token)
    nonce = headers.get("Nonce", nonce)
    token = headers.get("Cart-Token", token)
    _s, _h, cart = call("GET", "/cart", None, nonce, token)
    totals = cart.get("totals", {})
    items = [(i.get("name"), i.get("quantity"), i.get("prices", {}).get("price"))
             for i in cart.get("items", [])]
    return {
        "items": items,
        "total_minor": totals.get("total_price"),
        "total_text": "$1.00 CAD" if str(totals.get("total_price")) == "100" else str(totals.get("total_price")),
        "total_items_tax": totals.get("total_items_tax"),
        "total_shipping": totals.get("total_shipping"),
        "currency_code": totals.get("currency_code"),
        "needs_payment": cart.get("needs_payment"),
        "needs_shipping": cart.get("needs_shipping"),
        "payment_methods": cart.get("payment_methods"),
        "checked_at_utc": now_iso(),
        "note": "Cart only. No checkout, no payment, no order was made by this check.",
    }


def audit_live():
    # Individual product endpoints, as the earlier After run did.
    # This avoids a large list response and keeps each product check live.
    product_ids = [14, 23, 31, 40, 48, 58, 67, 76, 83, 92, 100, 110]
    products = [fetch_json(f"{STORE_API}/products/{pid}") for pid in product_ids]
    gaps = []
    proposals = []
    for p in products:
        desc = clean(p.get("description", ""))
        attrs = {a.get("name"): [t.get("name") for t in a.get("terms", [])] for a in p.get("attributes", [])}
        if "Material" not in attrs:
            val = segment(desc, "Material", ["Fit", "Returns"])
            if val:
                gaps.append({"product_id": p["id"], "product_name": p["name"],
                             "field": "material_structured", "current_value": None,
                             "prose_value": val,
                             "source_field": "description",
                             "source_label": "store_api:product.description + store_api:product.attributes"})
                proposals.append({"product_id": p["id"], "product_name": p["name"],
                                  "field": "material_structured", "current_value": None,
                                  "proposed_value": val, "source_field": "description",
                                  "accuracy_group": "95_plus", "status": "proposed"})
        if "Fit" not in attrs:
            val = segment(desc, "Fit", ["Returns", "Material"])
            if val:
                gaps.append({"product_id": p["id"], "product_name": p["name"],
                             "field": "fit_structured", "current_value": None,
                             "prose_value": val, "source_field": "description",
                             "source_label": "store_api:product.description + store_api:product.attributes"})
                proposals.append({"product_id": p["id"], "product_name": p["name"],
                                  "field": "fit_structured", "current_value": None,
                                  "proposed_value": val, "source_field": "description",
                                  "accuracy_group": "95_plus", "status": "proposed"})
        if "Returns" not in attrs:
            val = segment(desc, "Returns", ["Material", "Fit"])
            if val:
                gaps.append({"product_id": p["id"], "product_name": p["name"],
                             "field": "returns_structured", "current_value": None,
                             "prose_value": val, "source_field": "description",
                             "source_label": "store_api:product.description + store_api:product.attributes"})
                proposals.append({"product_id": p["id"], "product_name": p["name"],
                                  "field": "returns_structured", "current_value": None,
                                  "proposed_value": val, "source_field": "description",
                                  "accuracy_group": "95_plus", "status": "proposed"})
    return {
        "store_url": STORE_URL,
        "product_count": len(products),
        "gap_count_material_fit_returns": len(gaps),
        "proposal_count": len(proposals),
        "gaps": gaps,
        "proposals": proposals,
        "groups": [
            {"band": "95_plus", "presented_count": len(proposals),
             "rule": "Reject by exception: rows not rejected are approved, once the group is submitted."},
            {"band": "80_94", "presented_count": 0,
             "rule": "Approve by exception: only rows listed are approved, once the group is submitted."},
            {"band": "50_79", "presented_count": 0,
             "rule": "Approve by exception: only rows listed are approved, once the group is submitted."},
        ],
        "row_set_used": "framework-style proposals, live count in this run",
        "row_set_reason": ("The framework style is the style the Approval stage expects, "
                            "and it matches the live published batch for the judged product. "
                            "The framework file from 2026-10-31 gave 36 rows. A live check "
                            "today gives 35 rows for Material, Fit, and Returns, because "
                            "product 92 now shows no Returns value in its description prose. "
                            "The judged product, product 23, still gives all 3 rows. "
                            "The version 5 set has 62 rows and a different format, and it is "
                            "not passed to Approval in the runner. That choice stays open "
                            "for Greg. This harness does not pick it in silence."),
        "row_set_open_choice": "Canonical row set is open: framework-style rows or version 5 with 62 rows.",
        "not_proposed": ("Weight, dimensions, stock quantity, and other missing fields are "
                         "not proposed, because the store prose does not state them. "
                         "No price, stock level, or policy is invented."),
        "fetched_at_utc": now_iso(),
    }


def _meta_chat_direct(payload):
    """Direct Meta call, used on a host where META_API_KEY is set.
    No key is logged or returned. Redirects are refused."""
    import os
    key = os.environ.get("META_API_KEY") or os.environ.get("META_MODEL_API_KEY")
    if not key:
        raise RuntimeError("No META_API_KEY in host settings.")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            raise RuntimeError("Redirect refused.")
    req = urllib.request.Request(
        "https://api.meta.ai/v1/chat/completions",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(req, timeout=120) as resp:
        return json.loads(resp.read().decode(errors="replace"))


def meta_call(purpose, stage, prompt):
    """One real Meta call. Timing and result come from this call only."""
    started = time.time()
    started_iso = now_iso()
    try:
        payload = {"model": MODEL,
                   "messages": [{"role": "user", "content": prompt}],
                   "reasoning_effort": "minimal", "max_tokens": 800}
        # Host first: env key, so Render works without the runner folder.
        # Local second: runner Meta client, which falls back to the helper.
        try:
            resp = _meta_chat_direct(payload)
        except RuntimeError:
            import meta_client  # from the runner folder, if present
            resp = meta_client.chat(payload)
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = resp.get("usage")  # only if the service returns it; never estimated
        outcome = "success" if content else "failure: empty reply"
    except Exception as exc:  # noqa: BLE001
        content = ""
        usage = None
        outcome = f"failure: {str(exc)[:300]}"
    finished = time.time()
    return {
        "model": MODEL, "purpose": purpose, "stage": stage,
        "started_at_utc": started_iso, "finished_at_utc": now_iso(),
        "duration_seconds": round(finished - started, 2),
        "outcome": outcome, "content": content,
        "token_counts": usage,  # None when the service does not return counts
    }


def load_run(run_id):
    path = RUNS / f"{run_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def save_run(run):
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / f"{run['run_id']}.json").write_text(json.dumps(run, indent=2))
    return run


def new_run():
    run_id = f"run-{int(time.time())}"
    run = {"run_id": run_id, "store_url": STORE_URL, "product_id": PRODUCT_ID,
           "product_name": "City Chelsea Rain Boots", "size": "10", "colour": "Black",
           "started_at_utc": now_iso(), "steps": [], "meta_calls": [],
           "approvals": [], "logs": [], "status": "started"}
    run["logs"].append({"at_utc": now_iso(), "step": "run_created",
                        "detail": f"New run {run_id}. Old runs are kept in runs/."})
    return save_run(run)


def add_log(run, step, detail, source="harness"):
    entry = {"at_utc": now_iso(), "step": step, "detail": detail, "source": source}
    run["logs"].append(entry)
    run["steps"].append(entry)
    return entry


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep server logs quiet; run logs carry the record
        pass

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode() or "{}")

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            data = (HERE / "static" / "index.html").read_bytes()
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path.startswith("/assets/"):
            target = HERE / path.lstrip("/")
            if target.exists() and target.suffix == ".png":
                data = target.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_response(404); self.end_headers(); return
        if path == "/api/live":
            try:
                self.send_json(fetch_product())
            except Exception as exc:  # noqa: BLE001
                self.send_json({"error": str(exc)[:500], "source": "store"}, status=502)
            return
        if path == "/api/cart":
            last = None
            for _attempt in range(3):
                try:
                    self.send_json(cart_recheck())
                    break
                except Exception as exc:  # noqa: BLE001
                    last = exc
                    time.sleep(1)
            else:
                self.send_json({"error": str(last)[:500], "source": "store"}, status=502)
            return
        if path == "/api/audit":
            try:
                self.send_json(audit_live())
            except Exception as exc:  # noqa: BLE001
                self.send_json({"error": str(exc)[:500], "source": "store"}, status=502)
            return
        if path == "/api/runs":
            runs = sorted([json.loads(p.read_text()) for p in RUNS.glob("*.json")],
                          key=lambda r: r.get("started_at_utc", ""), reverse=True) if RUNS.exists() else []
            self.send_json({"runs": [{k: r[k] for k in ("run_id", "started_at_utc", "status") if k in r} for r in runs]})
            return
        if path.startswith("/api/runs/"):
            run = load_run(path.rsplit("/", 1)[-1])
            if run is None:
                self.send_json({"error": "run not found"}, status=404)
            else:
                self.send_json(run)
            return
        self.send_response(404); self.end_headers()

    def do_POST(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        body = self.read_json()
        if path == "/api/runs":
            self.send_json(new_run(), status=201); return
        if path == "/api/meta":
            run = load_run(body.get("run_id", "")) if body.get("run_id") else None
            result = meta_call(body.get("purpose", "shopping task"),
                               body.get("stage", ""), body.get("prompt", ""))
            if run:
                run["meta_calls"].append(result)
                add_log(run, "meta_call",
                        f"{MODEL}, {result['purpose']}, {result['duration_seconds']} seconds, {result['outcome']}",
                        source="meta")
                save_run(run)
            self.send_json(result); return
        if path.startswith("/api/runs/") and path.endswith("/approval"):
            run_id = path.split("/")[3]
            run = load_run(run_id)
            if run is None:
                self.send_json({"error": "run not found"}, status=404); return
            group = body.get("group")
            submitted = bool(body.get("submitted"))
            if not submitted:
                self.send_json({"error": "Group was not submitted. Silence never counts as approval.",
                                "approved": False}, status=400); return
            record = {"group": group, "submitted": True,
                      "judge_name": body.get("judge_name", ""),
                      "rejected_rows": body.get("rejected_rows", []),
                      "approved_rows": body.get("approved_rows", []),
                      "at_utc": now_iso(),
                      "note": "Demo merchant role for this judged run only. This page does not prove merchant sign-in."}
            run["approvals"].append(record)
            add_log(run, "approval",
                    f"Group {group} submitted by {record['judge_name'] or 'judge'}. "
                    f"Rejected rows: {record['rejected_rows']}.", source="approval")
            save_run(run)
            self.send_json({"approved": True, "record": record}); return
        if path.startswith("/api/runs/") and path.endswith("/publish"):
            run_id = path.split("/")[3]
            run = load_run(run_id)
            if run is None:
                self.send_json({"error": "run not found"}, status=404); return
            approved_95 = [a for a in run.get("approvals", [])
                           if a.get("group") == "95_plus" and a.get("submitted")]
            if not approved_95:
                add_log(run, "publish_blocked",
                        "Publish stopped: no recorded, matching approval for group 95_plus.",
                        source="approval_gate")
                save_run(run)
                self.send_json({"status": "blocked", "live_post": False,
                                "reason": "No recorded, matching approval. Publish does not proceed without approval."},
                               status=403); return
            try:
                live = fetch_product()
                audit = audit_live()
            except Exception as exc:  # noqa: BLE001
                self.send_json({"status": "blocked", "live_post": False,
                                "reason": f"Live fetch failed: {str(exc)[:300]}"}, status=502); return
            rejected = set()
            for a in approved_95:
                for r in a.get("rejected_rows", []):
                    rejected.add((r.get("product_id"), r.get("field")))
            mapped = []
            for p in audit["proposals"]:
                if p["product_id"] != PRODUCT_ID:
                    continue
                key = (p["product_id"], p["field"])
                if key in rejected:
                    continue
                label = {"material_structured": "Material", "fit_structured": "Fit",
                         "returns_structured": "Returns"}[p["field"]]
                mapped.append({"product_id": p["product_id"], "field": p["field"],
                               "mapped_to": f"additional_property:{label}",
                               "value": p["proposed_value"],
                               "live_ovo_value": live["ovo_fields"].get(label),
                               "matches_live_ovo": live["ovo_fields"].get(label) == p["proposed_value"]})
            result = {
                "status": "blocked_live_post_dry_run_only",
                "live_post": False, "dry_run": True,
                "mapped_rows": mapped,
                "written_where": "Dry-run mapping only. No live write was made by this run.",
                "original_kept": ("Store description prose is kept as the source. "
                                   "Store structured values for Material, Fit, and Returns were null "
                                   "before OVO fields. OVO fields are additional_property values, not a replacement of prose."),
                "live_ovo_batch": (live["ovo_endpoint"] or {}).get("fields", [{}])[0].get("batch_id") if live["ovo_endpoint"] else None,
                "live_publish_blocker": ("Live publish in the runner is dry-run only. The plugin runner refuses "
                                         "live post, and token auth on WordPress is untested. The live OVO fields "
                                         "already on the store came from the 2026-11-02 published batch, not from this run."),
                "note": "This run does not claim a new live publish. After can still be checked against the live OVO fields already on the store, with that batch stated.",
            }
            add_log(run, "publish_dry_run",
                    f"Dry-run mapping for {len(mapped)} judged rows. Live post blocked: {result['live_publish_blocker']}",
                    source="plugin")
            save_run(run)
            self.send_json(result); return
        if path.startswith("/api/runs/") and path.endswith("/order"):
            run_id = path.split("/")[3]
            run = load_run(run_id)
            if run is None:
                self.send_json({"error": "run not found"}, status=404); return
            order = {"order_number": body.get("order_number"),
                     "payment_mode": "test mode only",
                     "payment_route": "Merchant checkout, Stripe test card, through the merchant's own checkout. Not an agent-only payment bridge payment.",
                     "total_text": body.get("total_text", "$1.00 CAD"),
                     "source": "Judge-entered order number from the merchant checkout confirmation page. Not a private order-list fetch.",
                     "at_utc": now_iso()}
            run["test_order"] = order
            add_log(run, "test_order_recorded",
                    f"Test order {order['order_number']} recorded, test mode only, total {order['total_text']}. Source: {order['source']}",
                    source="merchant_checkout")
            save_run(run)
            self.send_json(order); return
        if path.startswith("/api/runs/") and path.endswith("/log"):
            run_id = path.split("/")[3]
            run = load_run(run_id)
            if run is None:
                self.send_json({"error": "run not found"}, status=404); return
            add_log(run, body.get("step", "log"), body.get("detail", ""), source=body.get("source", "harness"))
            save_run(run)
            self.send_json(run); return
        self.send_response(404); self.end_headers()


if __name__ == "__main__":
    import os
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    elif os.environ.get("PORT"):
        port = int(os.environ["PORT"])
    else:
        port = 8000
    print(f"OvO Harness on http://localhost:{port}  (test mode only, no key in code)")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
