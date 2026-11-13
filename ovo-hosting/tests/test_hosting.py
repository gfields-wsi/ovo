#!/usr/bin/env python3
"""Hosting tests for OvO Phase 7.

These tests need no live database and no keys. The Postgres
adapter and the health rules run against a fake connection
and a fixed clock. The API server, the worker, and the sweep
run against temporary SQLite files. The one live test class
runs only when OVO_TEST_DATABASE_URL is set, and is skipped
otherwise.

Run from the repo root:
    python3 -m unittest discover -s ovo-hosting/tests -v
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOSTING = HERE.parent
REPO_ROOT = HOSTING.parent
sys.path.insert(0, str(HOSTING))
sys.path.insert(0, str(REPO_ROOT / "ovo-mcp-service"))

import db as ovo_db  # noqa: E402
import health  # noqa: E402
import migrate as ovo_migrate  # noqa: E402
import postgres_store  # noqa: E402
import worker as ovo_worker  # noqa: E402
import sweep as ovo_sweep  # noqa: E402

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def _run_row(run_key, store_url, status, started_at, finished_at=None):
    return {
        "run_key": run_key,
        "store_url": store_url,
        "status": status,
        "started_at_utc": started_at,
        "finished_at_utc": finished_at,
    }


def _stage(status, finished_at=None):
    return {"status": status, "finished_at_utc": finished_at}


class TestScrubUrl(unittest.TestCase):
    def test_password_is_replaced(self):
        scrubbed = ovo_db.scrub_url(
            "postgresql://ovo:secret123@db.example.com:5432/ovo")
        self.assertNotIn("secret123", scrubbed)
        self.assertIn("***", scrubbed)
        self.assertIn("db.example.com", scrubbed)
        self.assertIn("ovo", scrubbed)

    def test_address_without_password_is_unchanged(self):
        url = "postgresql://ovo@db.example.com:5432/ovo"
        self.assertEqual(ovo_db.scrub_url(url), url)

    def test_empty_address_is_empty(self):
        self.assertEqual(ovo_db.scrub_url(""), "")
        self.assertEqual(ovo_db.scrub_url(None), "")


class TestParseDatabaseUrl(unittest.TestCase):
    def test_valid_address(self):
        parts = ovo_db.parse_database_url(
            "postgresql://ovo:pw@db.example.com:5432/ovo?sslmode=require")
        self.assertEqual(parts["host"], "db.example.com")
        self.assertEqual(parts["port"], 5432)
        self.assertEqual(parts["user"], "ovo")
        self.assertEqual(parts["database"], "ovo")
        self.assertEqual(parts["sslmode"], "require")
        self.assertNotIn("pw", parts["scrubbed"])

    def test_default_port(self):
        parts = ovo_db.parse_database_url(
            "postgres://ovo@db.example.com/ovo")
        self.assertEqual(parts["port"], 5432)

    def test_missing_address_is_an_error(self):
        with self.assertRaises(ValueError):
            ovo_db.parse_database_url("")

    def test_non_postgres_scheme_is_an_error(self):
        with self.assertRaises(ValueError):
            ovo_db.parse_database_url("mysql://ovo@db.example.com/ovo")

    def test_missing_host_is_an_error(self):
        with self.assertRaises(ValueError):
            ovo_db.parse_database_url("postgresql:///ovo")

    def test_missing_database_is_an_error(self):
        with self.assertRaises(ValueError):
            ovo_db.parse_database_url("postgresql://ovo@db.example.com/")


class TestTranslateSql(unittest.TestCase):
    def test_placeholders_become_percent_s(self):
        sql, serial = ovo_db.translate_sql(
            "SELECT * FROM runs WHERE run_key = ?")
        self.assertEqual(sql, "SELECT * FROM runs WHERE run_key = %s")
        self.assertFalse(serial)

    def test_question_mark_in_a_string_is_left_alone(self):
        sql, _ = ovo_db.translate_sql(
            "SELECT * FROM runs WHERE status = 'what?' AND run_key = ?")
        self.assertIn("'what?'", sql)
        self.assertIn("run_key = %s", sql)

    def test_insert_or_replace_becomes_on_conflict_update(self):
        sql, serial = ovo_db.translate_sql(
            "INSERT OR REPLACE INTO runs (run_key, store_url, status) "
            "VALUES (?, ?, ?)")
        self.assertIn("ON CONFLICT (run_key) DO UPDATE SET", sql)
        self.assertIn("store_url = EXCLUDED.store_url", sql)
        self.assertIn("status = EXCLUDED.status", sql)
        self.assertNotIn("run_key = EXCLUDED.run_key", sql)
        self.assertFalse(serial)

    def test_insert_or_ignore_becomes_on_conflict_do_nothing(self):
        sql, _ = ovo_db.translate_sql(
            "INSERT OR IGNORE INTO stages (run_key, stage) VALUES (?, ?)")
        self.assertIn("ON CONFLICT DO NOTHING", sql)

    def test_plain_insert_into_a_serial_table(self):
        sql, serial = ovo_db.translate_sql(
            "INSERT INTO sweep_runs (started_at_utc) VALUES (?)")
        self.assertTrue(serial)
        self.assertIn("%s", sql)

    def test_plain_insert_into_a_plain_table_is_not_serial(self):
        _sql, serial = ovo_db.translate_sql(
            "INSERT INTO runs (run_key) VALUES (?)")
        self.assertFalse(serial)

    def test_insert_or_replace_without_a_known_key_is_an_error(self):
        with self.assertRaises(ValueError):
            ovo_db.translate_sql(
                "INSERT OR REPLACE INTO mystery (a) VALUES (?)")


class TestConvertSchema(unittest.TestCase):
    def test_autoincrement_becomes_serial(self):
        schema = ("CREATE TABLE sweep_runs (\n"
                  "    id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
                  "    started_at_utc TEXT\n);")
        converted = ovo_db.convert_schema(schema)
        self.assertIn("id SERIAL PRIMARY KEY", converted)
        self.assertNotIn("AUTOINCREMENT", converted)

    def test_other_text_is_unchanged(self):
        schema = "CREATE TABLE runs (run_key TEXT PRIMARY KEY);"
        self.assertEqual(ovo_db.convert_schema(schema), schema)


class FakeCursor:
    """A stand-in for a psycopg cursor, for the adapter tests."""

    def __init__(self):
        self.statements = []
        self.row = None

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        return self

    def fetchone(self):
        return self.row

    def fetchall(self):
        return []

    def close(self):
        pass


class TestPostgresCursor(unittest.TestCase):
    def test_execute_translates_and_returns_the_cursor(self):
        fake = FakeCursor()
        cursor = ovo_db.PostgresCursor(fake)
        returned = cursor.execute(
            "INSERT OR REPLACE INTO runs (run_key, store_url) VALUES (?, ?)",
            ("k1", "https://example.com/shop"))
        self.assertIs(returned, cursor)
        sql, params = fake.statements[0]
        self.assertIn("ON CONFLICT (run_key) DO UPDATE SET", sql)
        self.assertEqual(params, ("k1", "https://example.com/shop"))

    def test_serial_insert_returns_the_new_id(self):
        fake = FakeCursor()
        fake.row = {"id": 7}
        cursor = ovo_db.PostgresCursor(fake)
        cursor.execute(
            "INSERT INTO sweep_runs (started_at_utc) VALUES (?)",
            ("2026-11-13T12:00:00+00:00",))
        sql, _params = fake.statements[0]
        self.assertTrue(sql.endswith(" RETURNING id"))
        self.assertEqual(cursor.lastrowid, 7)

    def test_fetchone_and_fetchall_pass_through(self):
        fake = FakeCursor()
        fake.row = {"run_key": "k1"}
        cursor = ovo_db.PostgresCursor(fake)
        self.assertEqual(cursor.fetchone(), {"run_key": "k1"})
        self.assertEqual(cursor.fetchall(), [])


class TestHealth(unittest.TestCase):
    def test_old_waiting_run_is_normal(self):
        run = _run_row("k1", "https://example.com/shop",
                       "paused_awaiting_merchant_decision",
                       (NOW - timedelta(days=3)).isoformat())
        self.assertEqual(health.classify_run(run, now=NOW),
                         "waiting_for_approval")

    def test_old_dry_run_wait_is_normal(self):
        run = _run_row("k1", "https://example.com/shop",
                       "plugin_dry_run_only",
                       (NOW - timedelta(days=5)).isoformat())
        self.assertEqual(health.classify_run(run, now=NOW),
                         "waiting_for_approval")

    def test_running_run_under_one_hour_is_running(self):
        run = _run_row("k1", "https://example.com/shop", "running",
                       (NOW - timedelta(minutes=30)).isoformat())
        self.assertEqual(health.classify_run(run, now=NOW), "running")

    def test_running_run_over_one_hour_with_no_stage_is_stuck(self):
        run = _run_row("k1", "https://example.com/shop", "running",
                       (NOW - timedelta(hours=2)).isoformat())
        self.assertEqual(health.classify_run(run, now=NOW), "stuck")

    def test_running_run_with_a_recent_stage_is_not_stuck(self):
        run = _run_row("k1", "https://example.com/shop", "running",
                       (NOW - timedelta(hours=2)).isoformat())
        stages = [_stage("complete",
                         (NOW - timedelta(minutes=10)).isoformat())]
        self.assertEqual(health.classify_run(run, stages, now=NOW),
                         "running")

    def test_running_run_with_an_old_stage_is_stuck(self):
        run = _run_row("k1", "https://example.com/shop", "running",
                       (NOW - timedelta(hours=3)).isoformat())
        stages = [_stage("complete",
                         (NOW - timedelta(hours=2)).isoformat())]
        self.assertEqual(health.classify_run(run, stages, now=NOW),
                         "stuck")

    def test_running_run_with_no_start_time_is_stuck(self):
        run = _run_row("k1", "https://example.com/shop", "running", None)
        self.assertEqual(health.classify_run(run, now=NOW), "stuck")

    def test_failed_stage_means_failed(self):
        run = _run_row("k1", "https://example.com/shop", "running",
                       (NOW - timedelta(minutes=5)).isoformat())
        stages = [_stage("failed", NOW.isoformat())]
        self.assertEqual(health.classify_run(run, stages, now=NOW),
                         "failed")

    def test_failed_run_means_failed(self):
        run = _run_row("k1", "https://example.com/shop", "failed",
                       (NOW - timedelta(minutes=5)).isoformat())
        self.assertEqual(health.classify_run(run, now=NOW), "failed")

    def test_complete_run_is_complete(self):
        run = _run_row("k1", "https://example.com/shop", "complete",
                       (NOW - timedelta(minutes=5)).isoformat(),
                       NOW.isoformat())
        self.assertEqual(health.classify_run(run, now=NOW), "complete")

    def test_summary_counts_each_state(self):
        store = _MemoryStore([
            _run_row("k1", "https://a.example.com", "running",
                     (NOW - timedelta(minutes=10)).isoformat()),
            _run_row("k2", "https://b.example.com", "running",
                     (NOW - timedelta(hours=2)).isoformat()),
            _run_row("k3", "https://c.example.com",
                     "paused_awaiting_merchant_decision",
                     (NOW - timedelta(days=2)).isoformat()),
            _run_row("k4", "https://d.example.com", "failed",
                     (NOW - timedelta(minutes=5)).isoformat()),
        ])
        summary = health.health_summary(store, now=NOW)
        self.assertEqual(summary["run_count"], 4)
        self.assertEqual(summary["counts"]["running"], 1)
        self.assertEqual(summary["counts"]["stuck"], 1)
        self.assertEqual(summary["counts"]["waiting_for_approval"], 1)
        self.assertEqual(summary["counts"]["failed"], 1)

    def test_stuck_runs_lists_only_stuck(self):
        store = _MemoryStore([
            _run_row("k1", "https://a.example.com", "running",
                     (NOW - timedelta(hours=2)).isoformat()),
            _run_row("k2", "https://b.example.com", "running",
                     (NOW - timedelta(minutes=10)).isoformat()),
        ])
        stuck = health.stuck_runs(store, now=NOW)
        self.assertEqual([r["run_key"] for r in stuck], ["k1"])


class _MemoryStore:
    """A store with fixed runs, for the health tests."""

    def __init__(self, runs):
        self._runs = runs

    def list_runs(self):
        return self._runs

    def export_run(self, run_key):
        for run in self._runs:
            if run["run_key"] == run_key:
                return dict(run, stages=[])
        return None


class TestMigratePrintSql(unittest.TestCase):
    def test_print_sql_needs_no_database(self):
        result = subprocess.run(
            [sys.executable, str(HOSTING / "migrate.py"), "--print-sql"],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CREATE TABLE IF NOT EXISTS runs", result.stdout)
        self.assertIn("CREATE TABLE IF NOT EXISTS stages", result.stdout)
        self.assertIn("CREATE TABLE IF NOT EXISTS scoped_keys", result.stdout)
        self.assertIn("CREATE TABLE IF NOT EXISTS merchants", result.stdout)
        self.assertIn("CREATE TABLE IF NOT EXISTS sweep_runs", result.stdout)
        self.assertIn("SERIAL PRIMARY KEY", result.stdout)
        self.assertNotIn("AUTOINCREMENT", result.stdout)
        self.assertNotIn("postgresql://", result.stdout)

    def test_print_sql_covers_all_three_stores(self):
        result = subprocess.run(
            [sys.executable, str(HOSTING / "migrate.py"), "--print-sql"],
            capture_output=True, text=True, timeout=60)
        self.assertIn("-- runner store", result.stdout)
        self.assertIn("-- mcp store", result.stdout)
        self.assertIn("-- merchant store", result.stdout)

    def test_no_address_is_a_clean_error(self):
        env = dict(os.environ)
        env.pop("DATABASE_URL", None)
        result = subprocess.run(
            [sys.executable, str(HOSTING / "migrate.py")],
            capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("DATABASE_URL is not set", result.stderr)


class TestRenderYaml(unittest.TestCase):
    def setUp(self):
        import yaml
        with open(REPO_ROOT / "render.yaml", encoding="utf-8") as handle:
            self.blueprint = yaml.safe_load(handle)

    def test_database_comes_first(self):
        databases = self.blueprint["databases"]
        self.assertEqual(len(databases), 1)
        self.assertEqual(databases[0]["name"], "ovo-db")
        self.assertEqual(databases[0]["databaseName"], "ovo")

    def test_services_are_in_creation_order(self):
        services = self.blueprint["services"]
        self.assertEqual(
            [s["name"] for s in services],
            ["ovo-api", "ovo-worker", "ovo-sweep"])
        self.assertEqual(
            [s["type"] for s in services], ["web", "worker", "cron"])

    def test_each_service_reads_the_database_address(self):
        for service in self.blueprint["services"]:
            env_vars = {e["key"]: e for e in service["envVars"]}
            database = env_vars["DATABASE_URL"]
            self.assertEqual(database["fromDatabase"]["name"], "ovo-db")
            self.assertEqual(database["fromDatabase"]["property"],
                             "connectionString")

    def test_no_secret_value_is_written(self):
        text = (REPO_ROOT / "render.yaml").read_text(encoding="utf-8")
        for service in self.blueprint["services"]:
            for entry in service["envVars"]:
                if "value" in entry:
                    # The only value written is the empty watch list.
                    self.assertEqual(entry["key"], "OVO_SWEEP_STORES")
                    self.assertEqual(entry["value"], "")
                if entry["key"] in ("META_API_KEY", "STRIPE_SECRET_KEY"):
                    self.assertEqual(entry.get("sync"), False)
        self.assertNotIn("sk-", text)
        self.assertNotIn("password", text.lower())

    def test_web_service_has_a_health_check_and_migration(self):
        api = self.blueprint["services"][0]
        self.assertEqual(api["healthCheckPath"], "/health")
        self.assertIn("migrate.py", api["preDeployCommand"])
        self.assertIn("api_server.py", api["startCommand"])

    def test_worker_has_a_migration_and_no_payment_key(self):
        worker = self.blueprint["services"][1]
        self.assertIn("migrate.py", worker["preDeployCommand"])
        self.assertIn("worker.py", worker["startCommand"])
        keys = [e["key"] for e in worker["envVars"]]
        self.assertNotIn("STRIPE_SECRET_KEY", keys)

    def test_sweep_runs_daily_and_starts_with_an_empty_watch_list(self):
        sweep = self.blueprint["services"][2]
        self.assertEqual(sweep["schedule"], "0 3 * * *")
        self.assertIn("sweep.py", sweep["startCommand"])
        self.assertIn("migrate.py", sweep["startCommand"])
        env_vars = {e["key"]: e for e in sweep["envVars"]}
        self.assertEqual(env_vars["OVO_SWEEP_STORES"]["value"], "")


class TestApiServer(unittest.TestCase):
    """The combined API server, on a local port, against
    temporary SQLite files. No DATABASE_URL is set here."""

    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="ovo-api-test-"))
        self.old_merchant_db = os.environ.get("OVO_MERCHANT_DB")
        os.environ["OVO_MERCHANT_DB"] = str(self.temp / "merchant.db")
        self.old_database_url = os.environ.pop("DATABASE_URL", None)
        import api_server
        self.api_server = api_server
        self.runner_store = postgres_store.open_run_store(
            None, sqlite_path=self.temp / "runs.db")
        self.merchant_app = api_server.load_merchant_app(None)
        from service import McpService
        self.service = McpService(self.temp / "mcp.db")
        self._open_run_store = postgres_store.open_run_store
        runs_db = self.temp / "runs.db"
        # A fresh store per call, as the production code expects:
        # it closes the store it opens, so a shared store would
        # be closed under the next request.
        postgres_store.open_run_store = (
            lambda *a, **k: postgres_store.RunStore(runs_db))
        handler = api_server.make_handler(
            self.service, self.merchant_app, database_url=None)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=10)
        self.service.close()
        self.runner_store.close()
        postgres_store.open_run_store = self._open_run_store
        if self.old_merchant_db is None:
            os.environ.pop("OVO_MERCHANT_DB", None)
        else:
            os.environ["OVO_MERCHANT_DB"] = self.old_merchant_db
        if self.old_database_url is not None:
            os.environ["DATABASE_URL"] = self.old_database_url
        shutil.rmtree(self.temp, ignore_errors=True)

    def _get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.read().decode("utf-8")

    def _post(self, path, payload):
        url = f"http://127.0.0.1:{self.port}{path}"
        request = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8")

    def test_health_answers_ok(self):
        status, body = self._get("/health")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "ovo-api")

    def test_health_runs_is_empty_at_first(self):
        status, body = self._get("/health/runs")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["run_count"], 0)
        self.assertEqual(data["counts"]["stuck"], 0)

    def test_health_runs_shows_a_seeded_run(self):
        self.runner_store.create_or_resume_run(
            "seed-1", "https://example.com/shop", "example",
            "2026-11-13T12:00:00+00:00")
        status, body = self._get("/health/runs")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["run_count"], 1)
        self.assertEqual(data["runs"][0]["run_key"], "seed-1")

    def test_health_run_detail_for_a_missing_key_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self._get("/health/runs/no-such-run")
        self.assertEqual(caught.exception.code, 404)

    def test_manifest_is_served(self):
        status, body = self._get("/.well-known/ovo")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["name"], "OvO")
        tool_names = [t["name"] for t in data["tools"]]
        self.assertEqual(len(tool_names), 5)
        self.assertIn("ovo_start_check", tool_names)

    def test_mcp_initialize_answers(self):
        status, body = self._post("/mcp", {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05",
                       "capabilities": {}, "clientInfo": {"name": "test",
                                                          "version": "1"}}})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["id"], 1)
        self.assertIn("result", data)

    def test_merchant_site_still_answers(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("OvO merchant site", body)


class TestWorkerAndSweep(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="ovo-worker-test-"))
        self.store = postgres_store.open_run_store(
            None, sqlite_path=self.temp / "runs.db")
        self._open_run_store = postgres_store.open_run_store
        runs_db = self.temp / "runs.db"
        # A fresh store per call, as the production code expects:
        # it closes the store it opens, so a shared store would
        # be closed under the next pass.
        postgres_store.open_run_store = (
            lambda *a, **k: postgres_store.RunStore(runs_db))
        self._run_check = ovo_worker.runner_client.run_check
        self._sweep_run_check = ovo_sweep.runner_client.run_check

    def tearDown(self):
        postgres_store.open_run_store = self._open_run_store
        ovo_worker.runner_client.run_check = self._run_check
        ovo_sweep.runner_client.run_check = self._sweep_run_check
        self.store.close()
        shutil.rmtree(self.temp, ignore_errors=True)

    def _seed(self, run_key, status, started_at):
        self.store.create_or_resume_run(
            run_key, "https://example.com/shop", "example", started_at)
        if status != "running":
            self.store.update_run(run_key, status, started_at, "{}")

    def test_worker_resumes_a_stuck_run_and_leaves_a_waiting_run(self):
        self._seed("stuck-1", "running",
                   (NOW - timedelta(hours=3)).isoformat())
        self._seed("waiting-1", "paused_awaiting_merchant_decision",
                   (NOW - timedelta(days=2)).isoformat())
        calls = []

        def fake_run_check(store_url, run_key, database_url=None,
                           repo_root=None):
            calls.append(run_key)
            return {"status": "paused_awaiting_merchant_decision"}

        ovo_worker.runner_client.run_check = fake_run_check
        report = ovo_worker.one_pass(None)
        self.assertEqual(report["counts"]["stuck"], 1)
        self.assertEqual(report["counts"]["waiting_for_approval"], 1)
        self.assertEqual(calls, ["stuck-1"])
        self.assertEqual(len(report["resumed"]), 1)
        self.assertEqual(report["resumed"][0]["run_key"], "stuck-1")

    def test_worker_leaves_a_failed_run_alone(self):
        self._seed("failed-1", "failed",
                   (NOW - timedelta(minutes=5)).isoformat())
        calls = []
        ovo_worker.runner_client.run_check = (
            lambda *a, **k: calls.append(a) or {"status": "failed"})
        report = ovo_worker.one_pass(None)
        self.assertEqual(calls, [])
        self.assertEqual(report["counts"]["failed"], 1)
        self.assertEqual(report["resumed"], [])

    def test_sweep_with_an_empty_watch_list_sweeps_nothing(self):
        exit_code, report = ovo_sweep.sweep(None, stores=[])
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["stores_checked"], [])
        self.assertEqual(report["checks"], [])
        sweeps = self.store.list_sweeps()
        self.assertEqual(len(sweeps), 1)

    def test_sweep_checks_each_watched_store(self):
        def fake_run_check(store_url, run_key, database_url=None,
                           repo_root=None):
            return {"status": "paused_awaiting_merchant_decision"}

        ovo_sweep.runner_client.run_check = fake_run_check
        exit_code, report = ovo_sweep.sweep(
            None, stores=["https://example.com/shop"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(report["checks"]), 1)
        self.assertEqual(report["checks"][0]["status"],
                         "paused_awaiting_merchant_decision")

    def test_sweep_fails_when_a_watched_check_fails(self):
        def fake_run_check(store_url, run_key, database_url=None,
                           repo_root=None):
            raise RuntimeError("store is down")

        ovo_sweep.runner_client.run_check = fake_run_check
        exit_code, report = ovo_sweep.sweep(
            None, stores=["https://example.com/shop"])
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["checks"][0]["status"], "failed")

    def test_watch_list_drops_blanks_and_non_web_addresses(self):
        old = os.environ.get("OVO_SWEEP_STORES")
        try:
            os.environ["OVO_SWEEP_STORES"] = (
                "https://a.example.com, , ftp://b.example.com, "
                "https://c.example.com")
            self.assertEqual(ovo_sweep.watch_list(), [
                "https://a.example.com", "https://c.example.com"])
            os.environ["OVO_SWEEP_STORES"] = ""
            self.assertEqual(ovo_sweep.watch_list(), [])
        finally:
            if old is None:
                os.environ.pop("OVO_SWEEP_STORES", None)
            else:
                os.environ["OVO_SWEEP_STORES"] = old


@unittest.skipUnless(
    os.environ.get("OVO_TEST_DATABASE_URL"),
    "live Postgres proof needs OVO_TEST_DATABASE_URL")
class TestLivePostgres(unittest.TestCase):
    """Proved against a real local Postgres server. The
    database address comes from OVO_TEST_DATABASE_URL, a test
    database only. Nothing here touches Render or a real
    store."""

    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["OVO_TEST_DATABASE_URL"]
        # A fresh suffix per run, so the shared test database
        # never clashes with rows from an earlier run.
        import uuid
        cls.suffix = uuid.uuid4().hex[:8]
        cls.temp = Path(tempfile.mkdtemp(prefix="ovo-live-pg-"))
        cls.sqlite_path = cls.temp / "runs.db"
        source = postgres_store.open_run_store(
            None, sqlite_path=cls.sqlite_path)
        source.create_or_resume_run(
            "live-1", "https://example.com/shop", "example",
            "2026-11-13T12:00:00+00:00")
        source.record_stage(
            "live-1", "audit", "complete", "abc",
            '{"score": 90}', "2026-11-13T12:05:00+00:00")
        source.record_sweep(
            "2026-11-13T03:00:00+00:00", "2026-11-13T03:01:00+00:00",
            ["https://example.com/shop"], 0, 0, 0, {"stores": 1})
        source.close()
        tables = ovo_migrate.migrate(cls.url)
        for table in ("runs", "stages", "sweep_runs", "scoped_keys",
                      "domains", "merchants", "packets", "orders"):
            assert table in tables, f"missing table {table}"
        cls.counts = ovo_migrate.copy_runner_sqlite(cls.sqlite_path, cls.url)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp, ignore_errors=True)

    def test_copy_moved_the_runner_rows(self):
        self.assertEqual(self.counts["runs"], 1)
        self.assertEqual(self.counts["stages"], 1)
        self.assertEqual(self.counts["sweep_runs"], 1)

    def test_run_survives_a_fresh_connection(self):
        store = postgres_store.open_run_store(self.url)
        try:
            record = store.export_run("live-1")
            self.assertEqual(record["status"], "running")
            self.assertEqual(record["store_url"],
                             "https://example.com/shop")
            self.assertEqual(len(record["stages"]), 1)
            self.assertEqual(record["stages"][0]["stage"], "audit")
            self.assertEqual(record["stages"][0]["status"], "complete")
            sweeps = store.list_sweeps()
            self.assertEqual(len(sweeps), 1)
        finally:
            store.close()

    def test_mcp_store_round_trips_on_postgres(self):
        key_hash = f"hash-{self.suffix}"
        merchant_id = f"merchant-{self.suffix}"
        store_url = "https://example.com/shop"
        store = postgres_store.open_mcp_store(self.url)
        try:
            store.record_key(
                key_hash, merchant_id, store_url,
                "2026-11-13T12:00:00+00:00")
            key = store.get_key(key_hash)
            self.assertEqual(key["merchant_id"], merchant_id)
            store.record_domain(
                store_url, merchant_id, "verified",
                "file", "2026-11-13T12:00:00+00:00")
            self.assertEqual(
                store.get_domain(store_url)["status"], "verified")
        finally:
            store.close()

    def test_merchant_store_round_trips_on_postgres(self):
        merchant_id = f"merchant-{self.suffix}"
        store = postgres_store.open_merchant_store(self.url)
        try:
            store.create_merchant(
                merchant_id, "Test Merchant", "test@example.com",
                "hash", "salt", 1, "2026-11-13T12:00:00+00:00")
            merchant = store.get_merchant(merchant_id)
            self.assertEqual(merchant["name"], "Test Merchant")
            store.save_packet(
                "live-1", "store-1", merchant_id,
                {"run_key": "live-1"}, "2026-11-13T12:00:00+00:00")
            packet = store.get_packet("live-1")
            self.assertEqual(packet["run_key"], "live-1")
        finally:
            store.close()

    def test_migration_is_safe_to_run_twice(self):
        tables = ovo_migrate.migrate(self.url)
        self.assertIn("runs", tables)
        counts = ovo_migrate.copy_runner_sqlite(self.sqlite_path, self.url)
        self.assertEqual(counts["runs"], 1)
        store = postgres_store.open_run_store(self.url)
        try:
            self.assertEqual(len(store.list_runs()), 1)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
