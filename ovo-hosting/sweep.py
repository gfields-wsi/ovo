#!/usr/bin/env python3
"""OvO daily sweep for Render.

The sweep is the cron job. It runs once and exits. Render
runs it every 24 hours, at 03:00 UTC, off peak. It does two
things:

1. It watches run health, as the worker does, and records
   the sweep in the run store, so the sweep log lists what
   it looked at.
2. It re-reads each store on the watch list, with a full
   readiness check through the runner. A missed webhook is
   caught here: the check re-reads the whole catalog and
   finds drift, within 24 hours. The check pauses at
   Merchant Approval and publishes nothing.

A store is swept only when it is named in OVO_SWEEP_STORES,
a comma-separated list of store addresses. That list is the
watch agreement: a store is watched because its merchant
agreed to it when the store was onboarded. No store is swept
by default. An empty list means the sweep records that
nothing was swept, and exits with success.

Usage, on Render: python3 ovo-hosting/sweep.py
With a watch list: OVO_SWEEP_STORES=https://example.com/shop
python3 ovo-hosting/sweep.py

The sweep exits with 1 when a watched store's check fails,
so the failed cron run is visible in Render. It exits with 0
when every watched check passes, pauses at approval, or when
the watch list is empty. No key, password, token, or card
number is ever printed.
"""
import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import health  # noqa: E402
import postgres_store  # noqa: E402
import runner_client  # noqa: E402


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def watch_list():
    """Store addresses to sweep, from OVO_SWEEP_STORES. Empty
    by default. A blank entry is dropped, and an address
    without http or https is dropped too."""
    raw = os.environ.get("OVO_SWEEP_STORES", "")
    stores = []
    for item in raw.split(","):
        store = item.strip()
        if store.startswith(("http://", "https://")):
            stores.append(store)
    return stores


def sweep(database_url=None, stores=None, repo_root=None):
    """One sweep. Returns (exit_code, report). The report is
    recorded in the run store before it is returned."""
    started = now_utc()
    stores = list(stores if stores is not None else watch_list())
    store = postgres_store.open_run_store(database_url)
    try:
        summary = health.health_summary(store)
        checks = []
        failed = False
        for store_url in stores:
            digest = hashlib.sha256(store_url.encode("utf-8")).hexdigest()[:12]
            run_key = f"sweep-{started[:10]}-{digest}"
            try:
                result = runner_client.run_check(
                    store_url, run_key,
                    database_url=database_url,
                    repo_root=repo_root or REPO_ROOT)
                checks.append({
                    "store_url": store_url,
                    "run_key": run_key,
                    "status": result.get("status"),
                })
                if result.get("status") == "failed":
                    failed = True
            except Exception as exc:  # noqa: BLE001 - a failed check is recorded, not raised
                checks.append({
                    "store_url": store_url,
                    "run_key": run_key,
                    "status": "failed",
                    "failure": str(exc),
                })
                failed = True
        finished = now_utc()
        report = {
            "started_at_utc": started,
            "finished_at_utc": finished,
            "stores_checked": stores,
            "checks": checks,
            "stuck_runs": summary["counts"]["stuck"],
            "failed_runs": summary["counts"]["failed"],
        }
        store.record_sweep(
            started, finished, stores, 0,
            summary["counts"]["stuck"], summary["counts"]["failed"],
            report)
        return (1 if failed else 0), report
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description="OvO daily sweep")
    parser.add_argument("--stores", default=None,
                        help="Comma-separated store addresses to sweep. "
                             "Defaults to OVO_SWEEP_STORES.")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL") or None
    stores = None
    if args.stores is not None:
        stores = [s.strip() for s in args.stores.split(",") if s.strip()]
    exit_code, report = sweep(database_url, stores=stores)
    print(
        f"sweep at {report['started_at_utc']}: "
        f"{len(report['stores_checked'])} stores swept, "
        f"{report['stuck_runs']} stuck runs, "
        f"{report['failed_runs']} failed runs",
        flush=True)
    for check in report["checks"]:
        print(f"sweep: {check['store_url']} -> {check['status']}",
              flush=True)
    if not report["stores_checked"]:
        print("sweep: no stores in watch list, nothing swept",
              flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
