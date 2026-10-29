# Day-one tests — run before building anything else

Blocked 2026-10-29 on: Sole Mates URL and admin access,
Meta Model API access, and Stripe test-mode setup. Repo access was
confirmed public 2026-10-29. Do not report these as passed or failed
until they are actually run.

1. Muse Spark tool calling and streaming through the Meta Model API.
   If this fails, that is the real emergency.
2. Store API checkout with Stripe test mode, including the
   expected-total type, on this WooCommerce version.
3. Stripe gateway available in block checkout on Sole Mates.
4. JSON-LD hook names on this WooCommerce version.

If test 2 or 3 fails, drop down the checkout ladder at once.
Do not silently substitute an OVO-hosted catalog.

## Build order

- Oct 29: day-one tests.
- Oct 29–30: one-product spine end to end, then messy Sole Mates
  with a ground-truth sheet: strip materials and widths, bury
  returns, blank alt text, plant one hostile instruction.
- Oct 31: approve and publish in place, settle the checkout rung.
- Nov 1: eval harness, before-and-after run, red-team run,
  merchant screen.
- Nov 2: freeze, reset button, timed 90-second run, backup recording.
- Nov 3–4: submission materials and video on the frozen build.

## Cut order

Cut first: animated celebration, then image checks, then golden
tasks from 25 down to 15. Never cut the before-and-after run, the
approval gate, the live re-check, or a real order. Never cut honesty
about which checkout rung was used.
