# Create the four Render services, in order

These are the steps for Greg, when he is ready. Nothing is
created yet, and nothing here asks for a Render login. The
services wait until he says go.

## Before you start

- You need a Render account, and the OvO repo connected to
  it. The repo is `gfields-wsi/ovo`. Use the production
  branch.
- You need the Meta key for the runner, and the Stripe
  secret key for test mode. Keep them in hand. You will
  type them into the Render settings store. They are never
  pasted into code, and never pasted into this file.
- You do not need a pilot store to create the services.
  The services can start with no store. The full flow on
  Render on the pilot store is a later step, Phase 8.

## Step 1. Create the database first

1. In Render, open the dashboard.
2. Choose New, then Blueprint.
3. Pick the `gfields-wsi/ovo` repo, and the production
   branch.
4. Render reads `render.yaml` at the repo root, and lists
   four resources: one database, one web service, one
   worker, and one cron job.
5. Look at the database first. It is named `ovo-db`.
   Leave the plan as Render shows it. You can change the
   plan later, in the dashboard.
6. Do not change the database name, or the service names.
   The other services find the database by the name
   `ovo-db`.

## Step 2. Type the keys into the settings store

Render will ask for two keys, for each service that needs
one:

- `META_API_KEY` — the Meta key for the runner. Type it
  in for the web service, the worker, and the sweep.
- `STRIPE_SECRET_KEY` — the Stripe secret key, test mode.
  Type it in for the web service only. The worker and the
  sweep do not take a payment, so they do not need it.

These keys stay in the Render settings store. They are
never written to code, and never shown in logs.

## Step 3. Create the four resources

1. Choose Apply, or Create, in the Blueprint page.
2. Render creates the resources in order: the database
   first, then the web service, then the worker, then the
   cron job.
3. Wait for each deploy to finish. The first deploy of the
   web service and the worker runs the migration, which
   creates the tables in the database. The sweep runs the
   migration first, each time it runs.
4. Check the web service health: open
   `https://<your web service address>/health`.
   It should answer `status: ok`.

## Step 4. Check the health watch

1. Open `https://<your web service address>/health/runs`.
   With no runs yet, it should answer an empty list.
2. Open the worker logs in the dashboard. It should print
   one line per pass: how many runs, how many stuck, how
   many failed, how many resumed. With no runs yet, all
   counts are zero.
3. Open the cron job in the dashboard. It should show its
   next run at 03:00 UTC. Its first run should print that
   no stores are in the watch list, and that nothing was
   swept. That is correct: the watch list starts empty.

## Step 5. Add a store to the watch list, only when its merchant agrees

1. When a merchant agrees to watching, open the cron job
   in the dashboard.
2. Set `OVO_SWEEP_STORES` to the store address, for
   example `https://example.com/shop`. For more than one
   store, separate the addresses with commas.
3. Save. The next sweep at 03:00 UTC will check that store.
4. Never add a store that has not agreed to watching.

## What is not done yet

- The full flow on Render on the pilot store is not done.
  There is no pilot store yet. That is Phase 8.
- The public manifest at `/.well-known/ovo` is served by
  the web service as code, but it is not deployed live to
  the OvO site. That step stays with the web server.
- No real card is charged. No real Link approval is made.
  No publish happens on a real store. The sweep and the
  worker never approve and never publish.
