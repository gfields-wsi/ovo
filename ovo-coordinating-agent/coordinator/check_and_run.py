#!/usr/bin/env python3
"""Scheduled check for the OvO Coordinating Agent.

Run by a scheduled job, every 15 minutes. Read the live Store
API, compare the catalog hash with the last seen hash, and run
the Coordinating Agent only if the hash changed. If the hash
did not change, do nothing. If no state file exists, record the
hash and do nothing, so a first run does not start on first
sight. Never publish, never buy, never bypass merchant approval.
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from trigger import catalog_hash

STATE_FILE = HERE / "trigger_state.json"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--store-url", required=True, help="Public store address, given by the merchant. No default store.")
    store_url = parser.parse_args().store_url
    try:
        current_hash, count = catalog_hash(store_url)
    except Exception as e:
        print(f"Store API read failed, no run: {e}")
        return 1
    if not STATE_FILE.exists() or json.loads(STATE_FILE.read_text()).get("store_url") != store_url:
        STATE_FILE.write_text(json.dumps({"catalog_hash": current_hash, "product_count": count, "store_url": store_url}, indent=2))
        print("First sight for this store address, hash recorded, no run.")
        return 0
    saved = json.loads(STATE_FILE.read_text())
    if saved.get("catalog_hash") == current_hash:
        print("No catalog change, no run.")
        return 0
    print(f"Catalog changed, running Coordinating Agent for {store_url}")
    proc = subprocess.run([sys.executable, str(HERE / "coordinator.py"),
                           "--store-url", store_url, "--skip-spark"],
                          cwd=HERE, capture_output=True, text=True, timeout=900)
    print(proc.stdout, end="")
    STATE_FILE.write_text(json.dumps({"catalog_hash": current_hash, "product_count": count, "store_url": store_url}, indent=2))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
