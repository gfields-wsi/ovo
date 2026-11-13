#!/usr/bin/env python3
"""OvO runner worker for Render.

The worker is the background service. It does not serve web
requests. It does two things, on a loop:

1. It watches run health. A stuck run and a failed run are
   printed, so they are visible in the service logs.
2. It recovers runs that a host restart cut short. A run that
   still says running, started more than one hour ago, and
   had no stage finish in the last hour is resumed with the
   same run key. The runner skips stages that already
   completed, and never publishes twice or bills twice.

It never starts a new check on its own. It never approves.
It never publishes. A run waiting for merchant approval is
normal and is left alone, whatever its age. A failed run is
left alone too, so a person can look at it first: resuming
a failed run without knowing why it failed could repeat the
same failure.

Usage, on Render: python3 ovo-hosting/worker.py
One pass, for a test: python3 ovo-hosting/worker.py --once
The loop waits OVO_WORKER_INTERVAL_SECONDS between passes,
default 900 seconds. A pass prints one line with counts.
No key, password, token, or card number is ever printed.
"""
import argparse
import os
import sys
import time
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


def one_pass(database_url=None, repo_root=None):
    """One watch and recover pass. Returns a dict with the
    counts and the run keys that were stuck, failed, or
    resumed. Nothing is printed here; the caller prints."""
    store = postgres_store.open_run_store(database_url)
    try:
        summary = health.health_summary(store)
        stuck = [r for r in summary["runs"] if r["state"] == "stuck"]
        failed = [r for r in summary["runs"] if r["state"] == "failed"]
        resumed = []
        for run in stuck:
            try:
                result = runner_client.run_check(
                    run["store_url"], run["run_key"],
                    database_url=database_url,
                    repo_root=repo_root or REPO_ROOT)
                resumed.append({
                    "run_key": run["run_key"],
                    "store_url": run["store_url"],
                    "status": result.get("status"),
                })
            except Exception as exc:  # noqa: BLE001 - a failed resume is a failed run
                failed.append({
                    "run_key": run["run_key"],
                    "store_url": run["store_url"],
                    "status": "failed",
                    "failure": str(exc),
                })
        return {
            "checked_at_utc": now_utc(),
            "run_count": summary["run_count"],
            "counts": summary["counts"],
            "stuck": [r["run_key"] for r in stuck],
            "failed": [r["run_key"] for r in failed],
            "resumed": resumed,
        }
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description="OvO runner worker")
    parser.add_argument("--once", action="store_true",
                        help="Run one pass and exit, instead of looping.")
    parser.add_argument("--interval", type=int, default=None,
                        help="Seconds between passes. Defaults to "
                             "OVO_WORKER_INTERVAL_SECONDS, or 900.")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL") or None
    interval = args.interval or int(
        os.environ.get("OVO_WORKER_INTERVAL_SECONDS", "900"))
    while True:
        report = one_pass(database_url)
        print(
            f"worker pass at {report['checked_at_utc']}: "
            f"{report['run_count']} runs, "
            f"{report['counts']['stuck']} stuck, "
            f"{report['counts']['failed']} failed, "
            f"{len(report['resumed'])} resumed",
            flush=True)
        for run_key in report["stuck"]:
            print(f"worker: stuck run {run_key}", flush=True)
        for run_key in report["failed"]:
            print(f"worker: failed run {run_key}", flush=True)
        if args.once:
            return 0
        time.sleep(interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
