#!/usr/bin/env python3
"""Run a readiness check through the OvO runner, for the
hosted services. The worker and the sweep both use this, so
they start a check the same way and with the same store.

A check is the production flow only: Audit, Enrichment,
Merchant Approval, then a pause. It never approves, never
publishes on its own, and never bills. A fresh run store is
opened for each check, so database connections are never
shared across threads.
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import postgres_store  # noqa: E402


def load_runner(repo_root=None):
    """Load ovo-runner/runner.py by path, as the MCP service
    does. The runner folder is put on the path for the import,
    because runner.py imports its store as a top-level module,
    then taken off again."""
    repo_root = Path(repo_root or REPO_ROOT)
    runner_dir = str(repo_root / "ovo-runner")
    sys.path.insert(0, runner_dir)
    try:
        spec = importlib.util.spec_from_file_location(
            "ovo_runner", str(repo_root / "ovo-runner" / "runner.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if sys.path and sys.path[0] == runner_dir:
            sys.path.pop(0)


def run_check(store_url, run_key, database_url=None, repo_root=None):
    """Run one readiness check for one store. Returns the run
    result dict. Raises RunnerFailed when a gate fails, as the
    runner does. The run store is opened fresh here and closed
    by the runner when the check ends."""
    module = load_runner(repo_root)
    store = postgres_store.open_run_store(database_url)
    try:
        return module.run_flow(
            store_url, run_key=run_key, store=store,
            repo_root=repo_root or REPO_ROOT)
    except module.RunnerFailed:
        raise
