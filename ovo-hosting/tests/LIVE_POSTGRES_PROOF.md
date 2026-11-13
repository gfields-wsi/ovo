# Live Postgres proof

This note records the live proof run, on 13 November 2026,
against a real Postgres server on this machine. It is a
record, not a script: the steps below are the exact steps
that were run, with their exact results.

## The server

- PostgreSQL 16.15, on Ubuntu, installed with apt, cluster
  16 main, port 5432, running locally.
- Test database `ovo_test`, test user `ovo_test`. This is a
  test database only. It is not Render, and it is not a
  real merchant store.
- Driver: psycopg 3.2.0, in a throwaway Python virtual
  environment at /tmp/ovo-pg-venv. It is not installed in
  the system Python.

## What was proved

1. Migration: `migrate.py` created all tables for all three
   stores in Postgres. Running it twice is safe: no row
   was changed, and no table was created twice.
2. Copy: one runner run, one stage, and one sweep were
   copied from a local SQLite file into Postgres, with
   `ON CONFLICT DO NOTHING`. Counts: runs 1, stages 1,
   sweep_runs 1.
3. Round trips: the MCP store and the merchant store both
   read and wrote Postgres. A scoped key, a domain check,
   a merchant, and an approval packet all came back with
   the same values they were saved with.
4. Restart survival: the Postgres server was restarted
   with `pg_ctlcluster 16 main restart`. After the restart,
   a fresh connection read the run back: run `live-1`,
   status running, store https://example.com/shop, stage
   audit complete, one sweep. Row counts after the restart:
   runs 1, stages 1, sweep_runs 1. A host restart loses
   no run.
5. A real bug was found and fixed by this proof: the
   runner's `export_run` loops over a cursor straight
   after execute, and the Postgres cursor wrapper could
   not be looped over. The fix adds `__iter__` to
   `PostgresCursor` in `ovo-hosting/db.py`, so it behaves
   like a SQLite cursor. The live tests pass after the fix.

## The test command

    OVO_TEST_DATABASE_URL='postgresql://ovo_test:ovo_test@127.0.0.1:5432/ovo_test' \
      /tmp/ovo-pg-venv/bin/python -m unittest \
      ovo-hosting.tests.test_hosting.TestLivePostgres -v

Result: 5 tests, all passed.

## What this does not prove

- The live restart test on Render is still untested. The
  proof above is on a local Postgres server, not on the
  Render database. The step that would prove it on Render:
  after Greg creates the four services, run one check
  through the API, restart the web service in the Render
  dashboard, then read `GET /health/runs` and check that
  the run is still there, with the same run key and the
  same stages.
- The full flow on Render on the pilot store is still
  untested. There is no pilot store yet. That carries to
  Phase 8.
