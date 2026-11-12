#!/usr/bin/env python3
"""Acceptance tests for the independent public-launch Audit items.
Each check prints PASS or FAIL. Exit 0 only if every check passes.
Checks: guidance coverage, merchant separation, Spark modes,
bad stores, pagination/pretty/attribute handling, repeatability,
format versioning. Live Sole Mates is restored at the end.
"""
import json, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
checks = []
def check(name, ok, detail=""):
    checks.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}: {name} {detail}")

def run_audit(args):
    return subprocess.run([sys.executable, str(HERE / "agent.py")] + args,
                          capture_output=True, text=True, timeout=300, cwd=str(HERE))

def load(name):
    return json.loads((HERE / name).read_text())

def product(pid, name, desc, size_name="Size", colour_name="Colour"):
    return {"id": pid, "name": name, "sku": f"SKU-{pid}",
            "description": desc, "short_description": "Short.",
            "attributes": [{"name": size_name, "terms": [{"name": "M"}]},
                           {"name": colour_name, "terms": [{"name": "Red"}]}],
            "variations": [{"attributes": [{"value": "M"}]}],
            "prices": {"price": "2000", "currency_code": "CAD"},
            "images": [{"src": "https://example.com/a.jpg", "alt": "A shoe"}],
            "categories": [{"name": "Shoes"}], "tags": ["t"], "brands": ["B"],
            "is_in_stock": True, "low_stock_remaining": None,
            "weight": "500", "dimensions": {"length": "30", "width": "10", "height": "10"}}

def mock_products(store):
    # 5 products, split across pages by the handler, with Color spelling
    # and Shoe Size name, and one non-shoe product.
    desc = "Material: Leather. Fit: True to size. Returns: 30-day returns."
    ps = [product(1, "Mock Shoe A", desc, "Shoe Size", "Color"),
          product(2, "Mock Shoe B", desc, "Size", "Colour"),
          product(3, "Mock Mug", "Material: Ceramic. Fit: N/A. Returns: 30-day returns."),
          product(4, "Mock Shoe C", desc),
          product(5, "Mock Shoe D", desc)]
    for p in ps:
        p["name"] = f"{store} {p['name']}"
    return ps

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        page = int(qs.get("page", ["1"])[0])
        if parsed.path.startswith("/pretty-only/wp-json/"):
            prods = mock_products("Pretty")
            chunk = prods[(page-1)*2:page*2]
            self._send(chunk, None); return
        if parsed.path.startswith("/empty/"):
            self._send([], None); return
        if parsed.path.startswith("/bad/"):
            self.send_response(404); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(b"<html>not found</html>"); return
        if "/mock-a/" in parsed.path or "/mock-b/" in parsed.path:
            store = "A" if "/mock-a/" in parsed.path else "B"
            prods = mock_products(store)
            # 2 per page, no total pages header, so pagination must
            # follow pages until an empty page.
            chunk = prods[(page-1)*2:page*2]
            self._send(chunk, None); return
        self.send_response(404); self.end_headers()
    def _send(self, data, total):
        body = json.dumps(data).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        if total: self.send_header("X-WP-TotalPages", str(total))
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
port = server.server_address[1]
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{port}"

# 1. Guidance coverage, on live Sole Mates first
r = run_audit(["--skip-spark", "--store-url", "https://wsiventures.com/solemates"])
check("live audit runs", r.returncode == 0)
g, s, mg = load("gaps.json"), load("scorecard.json"), load("merchant_guidance.json")
check("guidance covers every gap", len(mg["guidance"]) == len(g["gaps"]) == 124)
check("guidance covers every gap field", set(x["field"] for x in mg["guidance"]) == set(x["field"] for x in g["gaps"]))
check("guidance entries have plain fields", all(x.get("what_is_missing") and x.get("why_it_matters") and x.get("merchant_action") for x in mg["guidance"]))
check("guidance has no invented store value", all("$" not in x["merchant_action"] for x in mg["guidance"]))

# 2. Merchant separation, two mock stores
run_audit(["--skip-spark", "--store-url", f"{base}/mock-a"])
sa = load("scorecard.json")
check("mock A store key", sa["store_key"] == f"127.0.0.1:{port}/mock-a", sa["store_key"])
check("mock A products only", sa["product_count"] == 5 and all("A " in p["product_name"] for p in sa["per_product"]))
run_audit(["--skip-spark", "--store-url", f"{base}/mock-b"])
sb = load("scorecard.json")
check("mock B store key", sb["store_key"] == f"127.0.0.1:{port}/mock-b")
check("mock B products only, no A mixing", sb["product_count"] == 5 and all("B " in p["product_name"] for p in sb["per_product"]) and not any("A " in p["product_name"] for p in sb["per_product"]))

# 3. Pagination, pretty fallback, attribute synonyms
check("pagination reads all 5 mock products", sb["product_count"] == 5)
run_audit(["--skip-spark", "--store-url", f"{base}/pretty-only"])
sp = load("scorecard.json")
check("pretty link fallback works", sp["product_count"] == 5 and sp["store_key"] == f"127.0.0.1:{port}/pretty-only" and all("Pretty " in p["product_name"] for p in sp["per_product"]), sp["store_key"])
# Color / Shoe Size product should pass colour and size checks, so it
# should not have a colour gap or a size gap in its field gaps.
run_audit(["--skip-spark", "--store-url", f"{base}/mock-a"])
ga = load("gaps.json")
p1_gaps = [x["field"] for x in ga["gaps"] if x.get("product_id") == 1]
check("Color and Shoe Size accepted", "colour" not in p1_gaps and "size_variations" not in p1_gaps, str(p1_gaps))

# 4. Bad stores
before = load("scorecard.json")["store_key"]
r = run_audit(["--skip-spark", "--store-url", f"{base}/bad"])
check("bad store fails cleanly", r.returncode != 0 and "Audit failed" in (r.stdout + r.stderr))
err = load("audit_error.json")
check("bad store error file, no partial score", err["scorecard_written"] is False and "/bad" in err["store_key"])
check("bad store does not overwrite scorecard", load("scorecard.json")["store_key"] == before)
r = run_audit(["--skip-spark", "--store-url", f"{base}/empty"])
check("empty store fails cleanly", r.returncode != 0)

# 5. Repeatability, live Sole Mates, deterministic only
run_audit(["--skip-spark", "--store-url", "https://wsiventures.com/solemates"])
first = load("gaps.json"); first.pop("generated_at_utc", None)
run_audit(["--skip-spark", "--store-url", "https://wsiventures.com/solemates"])
second = load("gaps.json"); second.pop("generated_at_utc", None)
check("repeatability: same gaps twice", first == second)
check("repeatability: native core unchanged", load("scorecard.json")["core_score"] == "120/180 = 66.7%")

# 6. Spark modes, gaps unchanged
def gaps_no_time():
    d = load("gaps.json"); d.pop("generated_at_utc", None); return d
base_gaps = gaps_no_time()
r = run_audit(["--spark-sample", "3", "--store-url", "https://wsiventures.com/solemates"])
a = load("agent_run.json")
check("spark sample checks 3", a.get("spark_checked") == 3 and a.get("spark_agreed") == 3, str(a.get("spark_checked")))
check("spark sample gaps unchanged", gaps_no_time() == base_gaps)
check("timing logged", a.get("timing_seconds", {}).get("deterministic_audit", 0) > 0 and a.get("timing_seconds", {}).get("spark", 0) >= 0)

# 7. Format versioning
check("gaps format frozen 1.0", load("gaps.json")["format"] == "ovo-gap-list" and load("gaps.json")["version"] == "1.0")
check("scorecard format 1.0", load("scorecard.json")["format"] == "ovo-audit-scorecard" and load("scorecard.json")["version"] == "1.0")
check("trace format 1.0", load("trace.json")["format"] == "ovo-audit-trace" and load("trace.json")["version"] == "1.0")
check("versioning doc exists", (HERE / "VERSIONING.md").exists())

# Restore live Sole Mates, full Spark, for the pushed output
run_audit(["--store-url", "https://wsiventures.com/solemates"])
check("final live score restored", load("scorecard.json")["core_score"] == "120/180 = 66.7%")
server.shutdown()
passed = sum(1 for _, ok in checks if ok)
print(f"\n{passed}/{len(checks)} checks passed")
sys.exit(0 if passed == len(checks) else 1)
