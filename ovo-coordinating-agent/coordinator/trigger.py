#!/usr/bin/env python3
"""
Continuous start for the OvO Coordinating Agent, production flow.

The Coordinating Agent starts without a hand start, when a store
list changes, and keeps running. The trigger polls the live Store
API, records a catalog hash, and runs the Coordinating Agent
each time the hash changes. After each run, the trigger keeps
watching, it does not exit after one run.

The trigger never publishes, never buys, and never bypasses a
merchant approval gate. A trigger is not an approval.

Usage:
    python3 trigger.py --continuous [--store-url URL] [--interval SECONDS] [--skip-spark]
    python3 trigger.py --once [--store-url URL] [--skip-spark]   # test only, one run
Output: trigger_run.json, in this folder.
State: trigger_state.json, in this folder, holds the last catalog hash seen.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "trigger_state.json"
RUN_FILE = HERE / "trigger_run.json"


def catalog_hash(store_url):
    api = store_url.rstrip("/") + "/?rest_route=/wc/store/v1/products&per_page=100"
    products = None
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(api, headers={"User-Agent": "OvO-Trigger/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                products = json.load(resp)
            break
        except Exception as e:
            last = e
    if products is None:
        raise ValueError(f"Store API read failed: {last}")
    if not isinstance(products, list):
        raise ValueError("Store API did not return a product list")
    parts = []
    for p in sorted(products, key=lambda x: x["id"]):
        prices = p.get("prices") or {}
        parts.append(f"{p['id']}|{p.get('name')}|{prices.get('price')}|{prices.get('currency_code')}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest(), len(products)


def run_coordinator(store_url, skip_spark):
    cmd = [sys.executable, str(HERE / "coordinator.py"), "--store-url", store_url]
    if skip_spark:
        cmd.append("--skip-spark")
    proc = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=900)
    print(proc.stdout, end="")
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
    return proc.returncode


def main():
    parser = argparse.ArgumentParser(description="Continuous start for the OvO Coordinating Agent")
    parser.add_argument("--continuous", action="store_true", help="Keep watching, run on each catalog change")
    parser.add_argument("--once", action="store_true", help="Test only, run once now")
    parser.add_argument("--store-url", required=True, help="Public store address, given by the merchant. No default store.")
    parser.add_argument("--interval", type=int, required=True, help="Seconds between polls, given by the production requirement. No default interval.")
    parser.add_argument("--skip-spark", action="store_true")
    args = parser.parse_args()
    if not args.continuous and not args.once:
        parser.error("Use --continuous for production, or --once for a test")

    if args.once:
        code = run_coordinator(args.store_url, args.skip_spark)
        result = {"trigger": "once_test_only", "store_url": args.store_url,
                  "coordinator_ran": True, "coordinator_exit": code, "published": False}
        RUN_FILE.write_text(json.dumps(result, indent=2))
        print(f"Trigger test result: ran=True, exit={code}")
        return code

    # Continuous: use the last seen hash as the baseline, if a state
    # file exists. A change that happened while the trigger was down
    # must still start a run. Only on first sight, with no state
    # file, record the hash and watch, with no run on first sight.
    try:
        current_hash, count = catalog_hash(args.store_url)
    except Exception as e:
        print(f"Store API read failed, no run: {e}")
        return 1
    if STATE_FILE.exists():
        try:
            saved = json.loads(STATE_FILE.read_text())
            if saved.get("store_url") == args.store_url:
                current_hash = saved.get("catalog_hash", current_hash)
                count = saved.get("product_count", count)
            else:
                STATE_FILE.write_text(json.dumps({"catalog_hash": current_hash, "product_count": count, "store_url": args.store_url}, indent=2))
        except Exception:
            STATE_FILE.write_text(json.dumps({"catalog_hash": current_hash, "product_count": count, "store_url": args.store_url}, indent=2))
    else:
        STATE_FILE.write_text(json.dumps({"catalog_hash": current_hash, "product_count": count, "store_url": args.store_url}, indent=2))
    print(f"Continuous trigger started for {args.store_url}, interval {args.interval}s, "
          f"products {count}, baseline hash {current_hash[:12]}")
    runs = 0
    while True:
        time.sleep(args.interval)
        try:
            new_hash, new_count = catalog_hash(args.store_url)
        except Exception as e:
            print(f"Store API read failed during watch, no run: {e}")
            continue
        if new_hash == current_hash:
            continue
        print(f"Catalog changed, hash {current_hash[:12]} to {new_hash[:12]}, running Coordinating Agent")
        code = run_coordinator(args.store_url, args.skip_spark)
        runs += 1
        current_hash, count = new_hash, new_count
        STATE_FILE.write_text(json.dumps({"catalog_hash": current_hash, "product_count": count, "store_url": args.store_url}, indent=2))
        RUN_FILE.write_text(json.dumps({"trigger": "continuous", "store_url": args.store_url,
                                        "coordinator_ran": True, "runs": runs,
                                        "last_coordinator_exit": code, "published": False}, indent=2))
        print(f"Continuous trigger: run {runs} done, exit {code}, watching again")


if __name__ == "__main__":
    raise SystemExit(main())
