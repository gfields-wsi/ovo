# OvO Plugin Agent — draft branch

Status: draft, not live, not integrated. Do not treat this
branch as a production plugin, and do not merge it to main
until the OvO Hackathon organizer confirms integration.

## What this is

The OvO Enrichment plugin publishes merchant-approved
enrichment in place on the merchant's own WordPress and
WooCommerce store. It is not a shop, not a buyer, and not a
payment process. Payment stays pass-through on the merchant's
own checkout, through the merchant's own payment processor,
under Decision 0 and the PRD.

Current code: version 0.2.0-demo, in ovo-enrichment/.
Lint passes, 13 stub tests pass, and the Augment runner
passes in dry-run only. Nothing in this branch is
live-tested on Sole Mates yet.

## Files in this folder

- ovo-enrichment/ovo-enrichment.php — the plugin
- ovo-enrichment/readme.txt — plugin readme, version 0.2
- ovo-enrichment/uninstall.php — deletes OvO meta and
  options only, including the token hash
- ovo-enrichment/EXAMPLE-DIFF.json — diff format example only
- ovo-enrichment/verify-live.sh — curl-only live verification
- ovo-enrichment/tests-stub.php — stub tests, no WordPress
- augment-runner.py — Publish to Plugin runner, dry-run only,
  post mode refused until token auth is tested on WordPress
  and the plugin is installed
- enrichment-agent-definition.md and .json — contract the
  Plugin Agent defines for the Enrichment Agent, provisional
- plugin-sequence.json and ovo-plugin-sequence.png —
  provisional sequence spec and diagram, version 3
- PRODUCTION-PRD-REQUIREMENTS.md — revision 2, 19 items,
  Plugin lane only, after the WordPress and WooCommerce
  limits audit
- WP-WOO-LIMITS-AUDIT.md — that audit, with verified and
  unverified findings marked
- PLUGIN-TIER-FINGERPRINT-DESIGN.md — design note only for
  full tier and fingerprint verification, not yet coded

## What is NOT done

Live install on Sole Mates, WordPress integration tests,
live coordinator wiring, a real approved diff, live publish
verification, live revert and demo reset, full tier and
fingerprint verification in the plugin, and a named
distribution channel. See PRODUCTION-PRD-REQUIREMENTS.md
for the full list, with acceptance criteria for each item.

## Payment Bridge

The Payment Bridge research plan is NOT in this branch.
It lives in the local workspace as plan.md, research only,
and is superseded by Decision 0 for this stream. Research
showed no other way to enable an agent-only full transaction
on a WordPress and WooCommerce store, but that route is not
a production requirement here until Decision 0 changes.
