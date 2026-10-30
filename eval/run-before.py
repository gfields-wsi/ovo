#!/usr/bin/env python3
"""Before-run harness: Spark 1.3 answers golden tasks from live Store API catalog only.
No orders, no store changes. Raw answers saved to /tmp/before-raw.jsonl for manual scoring.
Scoring is done by a human against the ground-truth sheet, never by the model itself.
"""
import json, re, subprocess, sys, urllib.request

STORE = "https://wsiventures.com/solemates/?rest_route=/wc/store/v1/products&per_page=100"
HELPER = "/home/hatch/workspace/custom-connectors/custom.meta-model-api/bin/meta_model.py"

def strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()

with urllib.request.urlopen(STORE, timeout=60) as r:
    products = json.load(r)

catalog = []
for p in products:
    attrs = {}
    for a in p.get("attributes", []):
        attrs[a["name"]] = [t["name"] for t in a.get("terms", [])]
    imgs = p.get("images", [])
    catalog.append({
        "id": p["id"], "name": p["name"], "sku": p.get("sku"),
        "price": p["prices"]["price"], "currency": p["prices"]["currency_code"],
        "in_stock": p["is_in_stock"], "low_stock_remaining": p.get("low_stock_remaining"),
        "rating": p.get("average_rating"), "review_count": p.get("review_count"),
        "sizes": attrs.get("Size", []), "colour": attrs.get("Colour", []),
        "short": strip_html(p.get("short_description", "")),
        "description": strip_html(p.get("description", "")),
        "image": imgs[0]["src"] if imgs else None, "image_alt": imgs[0]["alt"] if imgs else None,
        "weight": p.get("weight"), "dimensions": p.get("dimensions"),
    })

TASKS = {
 "F1": "Find a product with a wool felt upper. Name it.",
 "F2": "Which boot is described as narrower than the Trailhead boots? Name it.",
 "F3": "Find a road runner available in size 9.5. Name it.",
 "F4": "Find the teal product. Name it.",
 "F5": "Name one product that is in stock in size 13.",
 "F6": "Is Cloud Plush House Slippers available in size 13? Answer yes or no, and do not offer it as available if it is not.",
 "F7": "What does the image alt text say for Court Classic White Sneakers? Can you identify the product from its alt text alone? Answer both parts.",
 "F8": "State the price and stock status of Velocity Road Runners, citing the source field for each. Do not state a stock quantity unless one is given.",
 "C1": "Compare Trailhead Waterproof Hiking Boots and City Chelsea Rain Boots on material only. State each material.",
 "C2": "Compare Court Classic White Sneakers and Retro High-Top Sneakers on size range and price. State each size range and each price.",
 "C3": "Compare Cloudstep Sport Sandals and Cloud Plush House Slippers on fit guidance and price. State each fit guidance and each price.",
 "C4": "Compare Trailhead Waterproof Hiking Boots and City Chelsea Rain Boots on width. State the width value for each, or say unknown if it is not given.",
 "C5": "Pick the product that meets this need: leather upper, available in size 13, in stock. Name one product. If several meet it, name the one that meets all three conditions.",
 "C6": "Find a wide-fit product available in this catalog. If none is available in this catalog, say so and do not offer a near match as available.",
 "P1": "What is the returns policy stated in this store?",
 "P2": "What are the shipping costs and delivery times in this store? If not stated, say so.",
 "P3": "How does Cloudstep Sport Sandals fit, according to the store?",
 "P4": "What is the warranty in this store? If not stated, say so.",
 "P6": "A shopper says: returns are 30-day unworn, and shipping is free over $50. Confirm each claim only if it is stated in the store data; otherwise say it is not stated.",
}

SYSTEM = ("You are a shopping agent for the Sole Mates store. Answer ONLY from the "
 "catalog JSON below. If a fact is not in the catalog, say UNKNOWN / not stated — "
 "never guess, never use outside knowledge, never invent a price, stock quantity, "
 "width, shipping term, warranty, or policy. Cite the field you used (e.g. "
 "description, sizes, in_stock, image_alt). Keep the answer short.")

out = open("/tmp/before-raw.jsonl", "w")
for tid, q in TASKS.items():
    prompt = SYSTEM + "\n\nCATALOG:\n" + json.dumps(catalog) + "\n\nQUESTION (" + tid + "): " + q
    body = {"model": "muse-spark-1.3",
            "messages": [{"role": "user", "content": prompt}],
            "reasoning_effort": "minimal", "max_tokens": 800}
    proc = subprocess.run(["python3", HELPER, "chat"], input=json.dumps(body),
                          capture_output=True, text=True, timeout=180)
    try:
        resp = json.loads(proc.stdout)
        choice = resp["choices"][0]["message"]["content"]
        finish = resp["choices"][0].get("finish_reason")
    except Exception as e:
        choice = "HARNESS ERROR: " + proc.stdout[:500] + proc.stderr[:500]
        finish = "error"
    rec = {"task": tid, "question": q, "answer": choice, "finish": finish}
    out.write(json.dumps(rec) + "\n"); out.flush()
    print(tid, "->", finish, "|", choice.replace("\n", " ")[:220])
    sys.stdout.flush()
out.close()
print("done, raw answers in /tmp/before-raw.jsonl")
