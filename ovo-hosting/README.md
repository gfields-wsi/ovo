# OvO hosting — Render

This folder is Phase 7. It holds the deployment code for
Render, the move from local SQLite files to Postgres, and
the run-health watch. It holds no keys, no passwords, and
no card numbers.

## What runs where

- The web server keeps the OvO site, the approval pages,
  the plugin downloads, the public manifest, and static
  scorecards. Vercel is not used.
- Render runs four services, in creation order:
  1. Postgres — `ovo-db`, the database.
  2. Web Service — `ovo-api`, the agent service and API.
  3. Background Worker — `ovo-worker`, the runner worker.
  4. Cron Job — `ovo-sweep`, the daily sweep, 03:00 UTC.
- `render.yaml` at the repo root creates all four, from
  one Blueprint. See `RENDER_STEPS.md` for the exact steps.

## Files

- `db.py` — Postgres adapter. It turns the SQLite-style
  calls the three stores already use into Postgres calls,
  and scrubs a database address before it is ever printed.
- `postgres_store.py` — the three stores, on Postgres:
  the runner store, the MCP store, and the merchant store.
  Each keeps every method its SQLite parent has. When
  DATABASE_URL is set, the store uses Postgres. When it is
  not set, the store uses its SQLite file, as before. A
  set but broken address is an error, never a silent fall
  back to a local file.
- `migrate.py` — creates the tables in Postgres, and can
  copy rows from a local SQLite file. Run it with
  `--print-sql` to see the table plan without connecting.
  The web service and the worker run it before each deploy.
  The sweep runs it first, because a cron job has no
  pre-deploy step.
- `health.py` — run health. A run is `stuck` when it still
  says running, started more than one hour ago, and had no
  stage finish in the last hour. A run is `failed` when it
  or any stage failed. A run waiting for merchant approval
  is `waiting`, which is normal at any age. Nothing here
  sends a message to anyone.
- `api_server.py` — the web service. One port, three parts:
  POST /mcp for the five MCP tools, the merchant site API
  and pages, and GET /health, GET /health/runs, and GET
  /health/runs/<run key>. It also serves the public manifest
  at GET /.well-known/ovo, from the file in the repo. That
  is code only: it does not deploy the manifest live to the
  OvO site. That step stays with the web server.
- `worker.py` — the background worker. It watches run
  health, and recovers runs that a host restart cut short,
  by resuming them with the same run key. It never starts
  a new check on its own, never approves, and never
  publishes.
- `sweep.py` — the daily sweep. It re-reads each store on
  the watch list, with a full readiness check, and records
  the sweep. A store is swept only when it is named in
  OVO_SWEEP_STORES. The list starts empty.
- `runner_client.py` — one shared way for the worker and
  the sweep to start a check through the runner.
- `requirements.txt` — psycopg only. Everything else is
  Python standard library.
- `tests/` — hosting tests. They run with no live database
  and no keys.

## Keys

Keys live in the Render settings store. They never live in
code, in logs, or in browser code. The Meta key stays on
the server. The OvO site and the runner each get their own
keys. A key for one merchant store is never shared with
another store. When Render needs the Meta key, Greg places
it in the Render settings store. Nothing here asks for it,
copies it, or types it.

## Run health, in short

- A stuck run shows in the health watch within one hour.
- A failed stage shows as a failed run.
- A run waiting for approval is normal, even for days.
- A run that fails silently is not allowed: the worker
  prints stuck and failed runs, and the sweep exits with
  1 when a watched store's check fails, so the failed cron
  run is visible in Render.

## Tests

Run all tests from the repo root:

    python3 -m unittest discover -s ovo-hosting/tests -v

The hosting tests use a fake database connection, a fixed
clock, and a temporary SQLite file. They need no live
database and no keys. The live Postgres proof is in
`tests/LIVE_POSTGRES_PROOF.md`.
