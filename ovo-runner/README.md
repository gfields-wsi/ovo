# OvO runner, production build

This folder runs the OvO agents, in order, for one store at a time.
It does not change the live store. It does not publish anything on
its own.

## Flow, production only

Audit, then Enrichment version 5 (62-row shape), then Merchant
Approval, then Publish to Plugin. Each stage is run by its own
agent. The runner only starts a stage, checks its output, and stops
if a check fails. The runner does no audit work, no enrichment
work, no approval work, and no publish work itself.

There is no Accuracy stage. The Enrichment Agent works out accuracy
as part of its own work and passes the drafts, with accuracy, to the
Merchant Approval Agent. Accuracy travels inside the enrichment diff.

## How to run it

Run this command, with a real store address:

```
python3 runner.py --store-url https://example.com/shop
```

Add `--skip-spark` to run Audit without the Spark check.
That proves the deterministic path still works.

Without a merchant decision file, Approval runs in packet mode and
the runner pauses. The plugin stage is not started. Nothing is
published. That pause is a normal stop, not an error.

With a merchant decision file, add `--decision-file` and the path
to that file. The file must come from the merchant only. The plugin
stage then runs in dry run mode only in this build. Live post stays
blocked, because token auth on WordPress is untested and the plugin
is not installed on a real store.

## Run state and safe retry

Runs, packets, decisions, and publish attempts live in a database
(`ovo_runs.db` next to this file, unless `--db` names another file),
through `store.py`. A host restart loses no run.

Each run has an idempotency key. Pass one with `--run-key`, or the
runner makes one. A retry with the same key skips stages that
already completed with the same input and output, and never
publishes twice: the plugin stage checks the recorded publish
attempt for the key before it spawns anything.

Export a run as JSON with:

```
python3 store.py --db ovo_runs.db export --run-key my-run-1 --out run.json
```

## What is in this folder

- `runner.py` is the runner. It starts stages and checks gates.
- `store.py` is the run store (SQLite now, Postgres in Phase 7).
  Callers use only its methods, so the store can change without
  changing the runner.
- `meta_client.py` is the only Meta call. It uses Spark 1.3
  through the chat service at api.meta.ai. It reads a key from
  the environment on a host, or the local helper on this machine.
  No key is stored in code or in a log. Agents can also call it
  as a helper: `python3 meta_client.py chat`, payload JSON on
  stdin, reply JSON on stdout.
- `tests/` holds the unit tests. They run with no live store and
  no Meta key: `python3 -m unittest discover -s tests -v`.

## Hard rules

- The store address is required. There is no default store.
- No scheduled check is set here.
- The runner never approves. Only a merchant can approve.
- The runner never publishes on its own.
- A failed stage stops the run. No later stage runs.
