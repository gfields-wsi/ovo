#!/usr/bin/env python3
"""Postgres stores for OvO on Render.

The three SQLite stores in this repo keep their method names,
their record shapes, and their callers. These three classes
are the same stores, backed by Postgres instead of a file.
Each one inherits every method from its SQLite parent and
only changes how it connects: a Postgres connection from
DATABASE_URL, with the same tables created in Postgres form.

When DATABASE_URL is not set, the factory functions below
return the SQLite stores instead, so local work and local
tests run with no live database and no extra install. On
Render, DATABASE_URL is set by the Blueprint from the
Postgres service, so the hosted services use Postgres.

No key, password, token, or card number is ever logged here.
The Postgres address itself is never printed. Only its
scrubbed form, with the password replaced by three stars,
may appear in a message.
"""
import importlib.util
import threading
from pathlib import Path

from db import PostgresConnection, parse_database_url

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_runner_store_mod = _load_module(
    "ovo_runner_store_pg", REPO_ROOT / "ovo-runner" / "store.py")
_mcp_store_mod = _load_module(
    "ovo_mcp_store_pg", REPO_ROOT / "ovo-mcp-service" / "mcp_store.py")
_merchant_store_mod = _load_module(
    "ovo_merchant_store_pg", REPO_ROOT / "ovo-merchant-site" / "store.py")

RunStore = _runner_store_mod.RunStore
McpStore = _mcp_store_mod.McpStore
MerchantStore = _merchant_store_mod.MerchantStore


class RunnerStorePg(RunStore):
    """The runner store, backed by Postgres. Same methods, same
    records. A host restart loses no run, because the rows live
    in managed Postgres, not in a file on one machine."""

    def __init__(self, database_url):
        self.db_path = None
        self.database_url = database_url
        self.conn = PostgresConnection(database_url)
        self.conn.executescript(_runner_store_mod.SCHEMA)


class McpStorePg(McpStore):
    """The MCP service store, backed by Postgres. Same methods,
    same records. Scoped key hashes, domain checks, runs, and
    refusals live in managed Postgres."""

    def __init__(self, database_url):
        self.db_path = None
        self.database_url = database_url
        self.conn = PostgresConnection(database_url)
        self.conn.executescript(_mcp_store_mod.SCHEMA)


class MerchantStorePg(MerchantStore):
    """The merchant site store, backed by Postgres. Same methods,
    same records. Each thread gets its own Postgres connection,
    as the SQLite version gives each thread its own file
    connection."""

    def __init__(self, database_url):
        self.db_path = None
        self.database_url = database_url
        self._local = threading.local()
        _ = self.conn

    @property
    def conn(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = PostgresConnection(self.database_url)
            conn.executescript(_merchant_store_mod.SCHEMA)
            self._local.conn = conn
        return conn


def _database_url(database_url=None):
    """The Postgres address to use, or None. A set but broken
    address is an error, never a silent fall back to SQLite:
    falling back would lose runs on a host restart without
    anyone noticing."""
    import os
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        return None
    parse_database_url(url)
    return url


def open_run_store(database_url=None, sqlite_path=None):
    """The runner store: Postgres when DATABASE_URL is set,
    SQLite otherwise. sqlite_path is the file to use when no
    Postgres address is set."""
    url = _database_url(database_url)
    if url is not None:
        return RunnerStorePg(url)
    return RunStore(sqlite_path or REPO_ROOT / "ovo-runner" / "ovo_runs.db")


def open_mcp_store(database_url=None, sqlite_path=None):
    """The MCP service store: Postgres when DATABASE_URL is set,
    SQLite otherwise."""
    url = _database_url(database_url)
    if url is not None:
        return McpStorePg(url)
    return McpStore(sqlite_path or REPO_ROOT / "ovo-mcp-service" / "mcp.db")


def open_merchant_store(database_url=None, sqlite_path=None):
    """The merchant site store: Postgres when DATABASE_URL is
    set, SQLite otherwise."""
    url = _database_url(database_url)
    if url is not None:
        return MerchantStorePg(url)
    return MerchantStore(
        sqlite_path or REPO_ROOT / "ovo-merchant-site" / "ovo-merchant-site.db")
