#!/usr/bin/env python3
"""Tests for the five independent public-launch items (v5).

Run after the live agent has been run twice for Sole Mates with v5:
    python3 agent.py --store-url https://wsiventures.com/solemates
This test then runs the agent itself against a local mock store.
No live store is ever changed. Exits 0 only if every check passes.
"""
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import agent as ag  # noqa: E402

results = []


def check(item, name, ok, detail=""):
    results.append((item, name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {item}: {name} {detail}")


def mock_product(pid, name, slug, ptype, cats, attrs, desc, images, variations, currency="USD"):
    return {
        "id": pid, "name": name, "slug": slug, "type": ptype, "parent": 0,
        "permalink": "", "sku": f"V5-{pid}", "short_description": "",
        "description": f"<p>{desc}</p>", "on_sale": False,
        "prices": {"price": "100", "currency_code": currency},
        "images": images, "categories": [{"id": 1, "name": c, "slug": c.lower()} for c in cats],
        "tags": [], "brands": [], "attributes": attrs, "variations": variations,
    }


def attr(name, terms, has_var):
    return {"id": 0, "name": name, "taxonomy": None, "has_variations": has_var,
            "terms": [{"id": 0, "name": t, "slug": t} for t in terms]}


def img(iid, filename):
    return {"id": iid, "src": "", "thumbnail": "", "alt": "", "name": filename}


V5_PRODUCTS = [
    mock_product(301, "Trail Cap", "trail-cap", "simple", ["Accessories"],
                 [attr("Color", ["Red"], False)],
                 "A trail cap. Material: Cotton Fit: Adjustable "
                 "Returns: 30-day returns, unused. Size system: US.",
                 [img(3011, "cap1.jpg")], []),
    mock_product(302, "Running Shorts", "running-shorts", "variable", ["Apparel"],
                 [attr("Size (UK)", ["S", "M", "L"], True),
                  attr("Color", ["Blue"], False)],
                 "Running shorts. Material: Polyester "
                 "Returns: 30-day returns, unused.",
                 [img(3021, "shorts1.jpg")],
                 [{"id": 3021, "attributes": [{"name": "Size (UK)", "value": "S"}]},
                  {"id": 3022, "attributes": [{"name": "Size (UK)", "value": "M"}]},
                  {"id": 3023, "attributes": [{"name": "Size (UK)", "value": "L"}]}]),
    mock_product(303, "Photo Album", "photo-album", "simple", ["Home"],
                 [attr("Color", ["Black"], False)],
                 "A photo album. Material: Leather "
                 "Returns: 30-day returns, unused.",
                 [img(3031, "album1.jpg"), img(3032, "album2.jpg"), img(3033, "album3.jpg")], []),
]


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send_json(self, data, total=None, pages=None):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if total is not None:
            self.send_header("X-WP-Total", str(total))
        if pages is not None:
            self.send_header("X-WP-TotalPages", str(pages))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _products_for(self, base):
        host = self.headers.get("Host", "localhost")
        out = []
        for p in V5_PRODUCTS:
            q = json.loads(json.dumps(p))
            q["permalink"] = f"http://{host}/{base}/?product={q['slug']}"
            for im in q["images"]:
                im["src"] = f"http://{host}/{base}/images/{im['name']}"
            out.append(q)
        return out

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        if path.startswith("/v5shop"):
            if "product" in qs:
                slug = qs["product"][0]
                prod = next((p for p in V5_PRODUCTS if p["slug"] == slug), None)
                if prod is None:
                    self.send_response(404); self.end_headers(); return
                body = f"<html><body>{prod['description']}</body></html>".encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if "/images/" in path:
                body = b"\x89PNG\r\n\x1a\n"
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if "rest_route" in self.path or "wp-json" in self.path:
                per_page = int(qs.get("per_page", ["100"])[0])
                page = int(qs.get("page", ["1"])[0])
                allp = self._products_for("v5shop")
                start = (page - 1) * per_page
                self._send_json(allp[start:start + per_page], total=len(allp), pages=1)
                return
        if path.startswith("/bigshop5"):
            if "rest_route" not in self.path and "wp-json" not in self.path:
                self.send_response(404); self.end_headers(); return
            allp = []
            for i in range(500, 605):
                allp.append(mock_product(i, f"Test Product {i}", f"test-{i}", "simple",
                                        ["Test"], [], "Material: Test material "
                                        "Returns: 30-day returns, unused.", [], []))
            per_page = int(qs.get("per_page", ["100"])[0])
            page = int(qs.get("page", ["1"])[0])
            start = (page - 1) * per_page
            chunk = allp[start:start + per_page]
            pages = (len(allp) + per_page - 1) // per_page
            self._send_json(chunk, total=len(allp), pages=pages)
            return
        self.send_response(404); self.end_headers()


def run_agent(store_url, extra=None):
    cmd = [sys.executable, str(HERE / "agent.py"), "--store-url", store_url] + (extra or [])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        # --- Sole Mates v5 metrics ---
        sm_path = HERE / "merchant" / "solemates" / "latest.json"
        check("Scale", "Sole Mates v5 latest diff exists", sm_path.exists())
        sm = json.loads(sm_path.read_text()) if sm_path.exists() else {}
        check("Scale", "Sole Mates counts unchanged at 62", len(sm.get("proposals", [])) == 62,
              f"got {len(sm.get('proposals', []))}")
        metrics = sm.get("metrics", {})
        check("Scale", "Sole Mates second v5 run hits cache, not the model",
              metrics.get("vision_calls") == 0 and metrics.get("vision_cache_hits") == 12,
              str(metrics))
        check("Scale", "Sole Mates metrics record duration and per-product time",
              metrics.get("duration_seconds", 0) > 0 and metrics.get("seconds_per_product", 0) > 0,
              str(metrics))
        check("Currency", "Sole Mates currency recorded as CAD, with no price proposal",
              sm.get("store_currency") == "CAD"
              and not any(p["field"] in ("price", "_ovo_price") for p in sm.get("proposals", [])))
        check("Size system", "Sole Mates size system stays unproposed, as no store states it",
              "size_system" in [u["field"] for u in sm.get("unproposed_fields_audit_only", [])])

        # --- Mock v5 shop, workers 4, then workers 1 for equivalence ---
        r1 = run_agent(f"{base}/v5shop", ["--vision-workers", "4"])
        check("Multi-photo", "v5shop agent exits 0", r1.returncode == 0, r1.stderr[:200])
        mock_path = HERE / "merchant" / "v5shop" / "latest.json"
        mock = json.loads(mock_path.read_text()) if mock_path.exists() else {}
        mprops = mock.get("proposals", [])
        check("Multi-photo", "v5shop proposal count is 15 as designed", len(mprops) == 15, f"got {len(mprops)}")
        by_prod = {}
        for p in mprops:
            by_prod.setdefault(p["product_id"], []).append(p)
        check("Multi-photo", "album with three photos gets three photo rows",
              sum(1 for p in by_prod.get("303", []) if p["field"].startswith("_ovo_image_alt")) == 3)
        check("Multi-photo", "vision attempts equal five unique photos, not one per product",
              mock.get("metrics", {}).get("vision_attempts") == 5,
              str(mock.get("metrics", {})))
        check("Size system", "cap size system is US, verbatim from its description",
              any(p["field"] == "_ovo_size_system" and p["new_value"] == "US" for p in by_prod.get("301", [])))
        check("Size system", "shorts size system is UK, verbatim from its attribute name",
              any(p["field"] == "_ovo_size_system" and p["new_value"] == "UK" for p in by_prod.get("302", [])))
        check("Size system", "album gets no size system row, as none is stated",
              not any(p["field"] == "_ovo_size_system" for p in by_prod.get("303", [])))
        check("Size system", "v5shop size system drops from unproposed list, as the store supplies it",
              "size_system" not in [u["field"] for u in mock.get("unproposed_fields_audit_only", [])])
        check("Currency", "v5shop currency recorded as USD, with no price proposal",
              mock.get("store_currency") == "USD"
              and not any(p["field"] in ("price", "_ovo_price") for p in mprops))
        # Parallel vs sequential equivalence.
        props_4 = {(p["product_id"], p["field"], str(p["new_value"]), p["prd_accuracy_band"]) for p in mprops}
        r_seq = run_agent(f"{base}/v5shop", ["--vision-workers", "1"])
        mock_seq = json.loads(mock_path.read_text())
        props_1 = {(p["product_id"], p["field"], str(p["new_value"]), p["prd_accuracy_band"]) for p in mock_seq.get("proposals", [])}
        check("Scale", "parallel and sequential runs produce identical proposals",
              props_4 == props_1 and r_seq.returncode == 0)

        # --- Audit log ---
        log_path = HERE / "merchant" / "v5shop" / "audit-log.jsonl"
        lines_before = len(log_path.read_text().strip().splitlines()) if log_path.exists() else 0
        run_agent(f"{base}/v5shop", ["--vision-workers", "4"])
        lines_after = len(log_path.read_text().strip().splitlines())
        check("Audit log", "audit log appends one line per run and preserves earlier lines",
              lines_after == lines_before + 1 and lines_before >= 2, f"{lines_before} -> {lines_after}")
        last_line = json.loads(log_path.read_text().strip().splitlines()[-1])
        check("Audit log", "latest audit line matches the latest batch",
              last_line.get("type") == "enrichment_run" and last_line.get("proposal_count") == 15)

        # --- Status ---
        status_path = HERE / "merchant" / "v5shop" / "status.json"
        status = json.loads(status_path.read_text()) if status_path.exists() else {}
        check("Status", "status file exists and matches the latest diff",
              status.get("products_processed") == 3 and status.get("enrichment_rows") == 15
              and status.get("batch_id") == json.loads(mock_path.read_text()).get("batch_id"))
        check("Status", "status lists unproposed fields with next actions",
              bool(status.get("unproposed_fields")) and all("next_action" in u for u in status["unproposed_fields"]))
        check("Status", "status includes metrics and failures",
              bool(status.get("metrics")) and "failures" in status)

        # --- Rollback ---
        batches = sorted((HERE / "merchant" / "v5shop").glob("v5shop-*.json"))
        batch_ids = [b.name[:-5] for b in batches if "status" not in b.name and b.name != "latest.json"]
        check("Rollback", "at least two mock batches exist to roll back between", len(batch_ids) >= 2, str(batch_ids))
        if len(batch_ids) >= 2:
            # Roll back to the first batch created in this test run.
            # Batches from earlier runs carry an earlier localhost
            # port in their store URL, so they correctly fail the
            # tenant check for this run's URL. The last three batches
            # are this run's workers-4, workers-1, and audit-log runs.
            target = batch_ids[-3] if len(batch_ids) >= 3 else batch_ids[0]
            r_rb = run_agent(f"{base}/v5shop", ["--rollback", "--batch", target])
            latest_after = json.loads(mock_path.read_text())
            check("Rollback", "rollback restores the named batch as latest",
                  r_rb.returncode == 0 and latest_after.get("batch_id") == target or latest_after.get("rollback_to_batch") == target,
                  f"rc={r_rb.returncode} latest={latest_after.get('batch_id')} to={latest_after.get('rollback_to_batch')}")
            last_line = json.loads(log_path.read_text().strip().splitlines()[-1])
            check("Rollback", "rollback is recorded in the audit log",
                  last_line.get("type") == "rollback" and last_line.get("to_batch") == target)
            # Tenant check: a Sole Mates batch must not roll back a mock merchant.
            sm_batches = sorted((HERE / "merchant" / "solemates").glob("solemates-*.json"))
            sm_batch = [b.name[:-5] for b in sm_batches if "status" not in b.name][0]
            r_bad = run_agent(f"{base}/v5shop", ["--rollback", "--batch", sm_batch])
            latest_still = json.loads(mock_path.read_text())
            check("Rollback", "rollback of another merchant's batch fails and changes nothing",
                  r_bad.returncode != 0 and (latest_still.get("rollback_to_batch") == target),
                  f"rc={r_bad.returncode}")

        # --- Cache, synthetic ---
        cache = {"https://example.test/photo.jpg": {"product_type": "cap", "dominant_colour": "red",
                                                    "material_appearance": "cotton", "confidence_percent": 92}}
        calls = {"n": 0}
        orig = ag.vision_check

        def counting(url, name=""):
            calls["n"] += 1
            return {"error": "should not be called on a cache hit"}
        ag.vision_check = counting
        try:
            m = {"vision_calls": 0, "vision_cache_hits": 0, "vision_total_tokens": 0}
            vis, hit = ag.get_vision("https://example.test/photo.jpg", cache, m, use_cache=True)
            check("Scale", "vision cache hit returns the cached result with no model call",
                  hit and vis["confidence_percent"] == 92 and calls["n"] == 0 and m["vision_cache_hits"] == 1)
            vis2, hit2 = ag.get_vision("https://example.test/photo.jpg", cache, m, use_cache=False)
            check("Scale", "--no-cache bypasses the cache",
                  not hit2 and calls["n"] == 1)
        finally:
            ag.vision_check = orig

        # --- Scale, 105 products, no photos ---
        r_big = run_agent(f"{base}/bigshop5", ["--vision-workers", "4"])
        big_path = HERE / "merchant" / "bigshop5" / "latest.json"
        big = json.loads(big_path.read_text()) if big_path.exists() else {}
        check("Scale", "105-product store completes with 210 proposals and recorded metrics",
              r_big.returncode == 0 and big.get("product_count") == 105
              and big.get("proposal_count") == 210 and big.get("metrics", {}).get("duration_seconds", 0) > 0,
              f"rc={r_big.returncode} products={big.get('product_count')} proposals={big.get('proposal_count')}")
        check("Scale", "big store seconds per product equals duration divided by products",
              abs(big.get("metrics", {}).get("seconds_per_product", 0)
                  - big.get("metrics", {}).get("duration_seconds", 0) / 105) < 0.01)

        # --- Synthetic size/currency helpers ---
        check("Currency", "most common currency wins, with a tie going to the first seen",
              ag.most_common_currency([{"prices": {"currency_code": "USD"}}, {"prices": {"currency_code": "USD"}},
                                       {"prices": {"currency_code": "CAD"}}]) == "USD"
              and ag.most_common_currency([]) is None)
        check("Size system", "size system detection finds a stated system and not a product name",
              ag.detect_size_system({"attributes": []}, "Size system: EU. Material: Leather.") is not None
              and ag.detect_size_system({"attributes": []}, "Men's Running Shoes. Material: Mesh.") is None)
    finally:
        server.shutdown()

    failed = [r for r in results if not r[2]]
    print(f"\nTOTAL: {len(results) - len(failed)}/{len(results)} checks passed.")
    if failed:
        print("FAILED:")
        for item, name, _, detail in failed:
            print(f"  {item}: {name} {detail}")
        sys.exit(1)
    print("ALL CRITERIA PASS AT 100 PERCENT.")


if __name__ == "__main__":
    main()
