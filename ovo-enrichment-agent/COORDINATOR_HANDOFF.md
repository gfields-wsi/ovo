# Coordinator handoff — live Enrichment Agent (Stream 2)

For Greg to direct the Coordinating Agent. This file is not sent
to the organizer by this stream. Integration is for the organizer
to confirm. Nothing here claims a publish, an approval, or
integration as done.

## What was built, 2026-10-30 — v4, any WooCommerce store

v4, added 2026-10-30: the 14 any-store requirements are built
into the live agent. Run it with a store URL:
`python3 agent.py --store-url https://example.com/shop`.
The merchant is derived from that URL, the Store API is found
with both endpoint forms, the full catalog is fetched with
paging, fields are discovered from that store itself, photo
checks are product-type agnostic, bands use that store's
sources only, refresh and tenant records are per merchant,
and failures are fail-closed with no previous diff overwritten.
Test file: `test_any_store.py` in the same folder. It runs the
agent against local mock stores and must report 100 percent
pass before any push. Latest result: 37 of 37 checks passed.

Widened task definition, v3: the 8 remaining work items are built
into the live agent — per-row evidence, variant choices for any
product, unproposed reasons with codes and next actions, an
untrusted-text guard, refresh comparison, a merchant batch file,
typed list values, and a visual-only path with recorded confidence.
Test file: `test_live_agent.py` in the same folder. It checks every
Pass criterion in the 8-item list and must report 100 percent pass
before any push.

Widened task definition:
`~/workspace/ovo-hackathon/ovo-enrichment/live-agent/AGENT.md`

Live agent code:
`~/workspace/ovo-hackathon/ovo-enrichment/live-agent/agent.py`

Run: `python3 agent.py` in that folder. It reads the live store
only, and it writes only in that folder. It never changes the
live store and never publishes.

## Live run result, verified 2026-10-30

- 12 products, 62 enrichment rows, 12 preservation rows,
  17 unproposed fields, 91 CSV rows in total.
- Bands: 50 enrichment rows at 95 percent or greater, 12 rows
  at 80-94 percent, 0 rows at 50-79 percent.
- Vision: all 12 photos checked live with Muse Spark 1.3.
  Each vision result, with its confidence percent, is recorded
  in `enrichment_run_live.json`. No vision confidence was guessed.
- Visual-only rows: none. Every schema field already has a
  text source in this store, so vision corroborates photo text
  and is logged only. Text material always stands over visual
  appearance.
- Store check after the run: 12 products, descriptions and
  prices unchanged against the earlier snapshot. All prices
  $1.00 CAD.

## Difference from the master file, stated plainly

91 rows, same keys, same bands as the master file. Only 7 rows
differ in value, all fit guidance, all at the same band. The
live agent uses the full Fit segment verbatim. The master file
used only the first sentence for those 7 products. No word in
the live values is invented. The live fit values contain the
master fit values as a prefix.

Products: 31, 58, 67, 83, 92, 100, 110.

## What the Coordinator needs to change to task it live

- Widen the Enrichment worker scope to this task definition:
  photos, PRD bands, and the broader field list — material,
  fit, returns, sizes, image alt, and the two notes — not
  material, fit, and returns only.
- Point the worker at this agent code, or merge this code into
  the coordinator's Enrichment worker, as the organizer directs.
- Keep the output status as proposed only, published false.
  Approval and publishing stay in their own workstreams.
