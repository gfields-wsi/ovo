#!/usr/bin/env python3
"""Run health for OvO on Render.

The host must show a stuck run within one hour. A failed
stage must be visible. A run that waits for merchant approval
for days is normal, not a fault. A run that fails silently is
not allowed.

This module reads runs from a store and sorts them into four
plain states. It sends nothing to anyone. It starts nothing.
It approves nothing. It publishes nothing. It only reports,
so a person or a watch can read it. There is no status
reporting to a person in the production flow: this is a pull
report, read when someone asks for it.

States:
- waiting_for_approval: the run paused at Merchant Approval,
  or finished a plugin dry run and waits. Any age is normal.
- stuck: the run still says running, it started more than
  one hour ago, and no stage finished in the last hour.
- failed: the run failed, or any of its stages failed.
- running: the run still says running, and it is not stuck.
- complete: the run reached a finished state.

A run key, a store address, a status, and times are the only
facts used. No key, password, token, or card number appears
in a health report.
"""
from datetime import datetime, timezone

STUCK_AFTER_MINUTES = 60

WAITING_STATUSES = (
    "paused_awaiting_merchant_decision",
    "plugin_dry_run_only",
)


def _parse_time(text):
    """An ISO time, or None when the text is missing or broken.
    A broken time never makes a run look healthy."""
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def classify_run(run, stages=None, now=None):
    """One run, one state. run is a run row from the store.
    stages is the run's stage rows, when known. now is the
    time to judge by, defaulting to this moment."""
    now = now or datetime.now(timezone.utc)
    status = (run or {}).get("status") or ""
    stages = stages or []
    if any((s or {}).get("status") == "failed" for s in stages):
        return "failed"
    if status == "failed":
        return "failed"
    if status in WAITING_STATUSES:
        return "waiting_for_approval"
    if status == "running":
        started = _parse_time(run.get("started_at_utc"))
        if started is None:
            return "stuck"
        age_minutes = (now - started).total_seconds() / 60.0
        if age_minutes <= STUCK_AFTER_MINUTES:
            return "running"
        finished_times = [
            _parse_time(s.get("finished_at_utc")) for s in stages]
        finished_times = [t for t in finished_times if t is not None]
        if finished_times:
            last_finish = max(finished_times)
            if (now - last_finish).total_seconds() / 60.0 <= STUCK_AFTER_MINUTES:
                return "running"
        return "stuck"
    if status in ("complete", "completed", "done"):
        return "complete"
    return "unknown"


def health_summary(store, now=None):
    """All runs in the store, sorted by state. store is any
    store with list_runs and export_run, which the runner store
    has. Returns a dict with a count per state and one entry
    per run: run key, store address, status, state, started
    time, and finished time. No other run detail is included."""
    now = now or datetime.now(timezone.utc)
    runs = store.list_runs()
    entries = []
    counts = {
        "waiting_for_approval": 0,
        "stuck": 0,
        "failed": 0,
        "running": 0,
        "complete": 0,
        "unknown": 0,
    }
    for run in runs:
        record = store.export_run(run["run_key"])
        stages = (record or {}).get("stages") or []
        state = classify_run(run, stages, now=now)
        counts[state] += 1
        entries.append({
            "run_key": run.get("run_key"),
            "store_url": run.get("store_url"),
            "status": run.get("status"),
            "state": state,
            "started_at_utc": run.get("started_at_utc"),
            "finished_at_utc": run.get("finished_at_utc"),
        })
    return {
        "checked_at_utc": now.isoformat(),
        "run_count": len(entries),
        "counts": counts,
        "runs": entries,
    }


def stuck_runs(store, now=None):
    """Only the stuck runs, for the worker and the sweep to log.
    Each entry names the run key, the store, and how long the
    run has been going."""
    now = now or datetime.now(timezone.utc)
    summary = health_summary(store, now=now)
    return [r for r in summary["runs"] if r["state"] == "stuck"]
