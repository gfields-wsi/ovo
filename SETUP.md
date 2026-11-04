# Setup — OvO

## For judges: fastest path, no install

Open the live harness:
https://wsiventures.com/ovoharness/index.html?v=10

Follow JUDGE.md. You need no WordPress admin access, no plug-in step,
and no key. This is the judged run.

Demo video (3 minutes): [VIDEO LINK TO BE ADDED BY GREG]

## For judges: read the code

Repository: gfields-wsi/ovo, public.
- Main branch: project story, docs, eval runs, Sole Mates store source.
- Harness branch ovo-harness, folder ovo-harness/: index.html, meta.php,
  publish.php, README.md, assets. That code is the live harness code.
- Agent branches: see BRANCH-MAP.md. They are separate, not merged
  to main.

No key is in this repository. Do not add one. Keys live on the host
only, in host settings or in a private file outside public_html.

## For a builder: run the harness code locally

This section is for builders, not for the judged run. The judged run
is the hosted harness above.

Harness files are plain web files plus two PHP proxies:
- index.html: the harness page, three panes, Buyer, Trace, Timeline,
  Diff, Logs.
- meta.php: Meta-only proxy, Muse Spark 1.3. It reads a key only
  from host settings (META_API_KEY or META_MODEL_API_KEY) or from a
  private file outside public_html. If no key is set, Meta calls fail
  plainly with 503, and deterministic stages are kept. No call is
  simulated.
- publish.php: live publish proxy, demo store only. It reads a token
  only from host settings (OVO_TOKEN) or from a private file outside
  public_html. If no token is set, Publish fails plainly. No write
  is confirmed without a token and a recorded approval.

To host it yourself, upload the ovo-harness/ files to a web host
that runs PHP, set the host keys above, and open index.html with
a version query, for example index.html?v=10, to avoid a stale
server-cached copy. Purge server cache if the plain link stays stale.

## What does not run from this repository alone

- The live Sole Mates store is hosted separately, at
  https://wsiventures.com/solemates, WordPress + WooCommerce.
  The sole-mates/ folder in this repository is the store source,
  not a running store. See sole-mates/docs/SETUP-LOCALWP.md for a
  local store copy, if you want one for exploration.
- Live agent payment is not available from this repository alone.
  Agent payment is blocked. The payment bridge is not installed.
- Live publish needs a host token and a recorded approval, as above.
  Without them, Publish fails plainly. That is expected, not a bug.

## Limits, repeated here on purpose

Test mode only. No live customer payment. No full MCP, ACP, or UCP
compliance claim. No production plug-in compatibility claim. No
broad SMB onboarding claim. Payment stays pass-through: the
merchant's checkout and processor, the merchant as merchant of
record.
