# OvO Harness — Judge instructions

## Open the harness

Open this exact link:
https://wsiventures.com/ovoharness/index.html?v=14

Demo video (3 minutes): https://youtube.com/shorts/i1ncawyazM0

Use the version link. The plain link can serve a stale server-cached
copy, even after a correct upload. Browser cache clearing does not
fix server cache.

You need no WordPress admin access. You need no plug-in step.
You need no key. Do not enter a key anywhere on this page.

## Run it, in order

Locked task: City Chelsea Rain Boots, black, size 10, $1 CAD,
product 23, store https://wsiventures.com/solemates

1. Press Run Judge Test, or Run Before.
   Expect: the run stops at Searched. The screen lists the missing
   structured fields by name, and states the stopping reason.
2. Press Run OvO.
   Expect, in order: Audit gaps and score, Enrichment proposals with
   source and accuracy, Approval cards by group, Publish log.
   Approve a group to allow publish for that group only. Silence
   and a group that was not submitted never count as approval.
3. Press Run After.
   Expect: the same fields now present as structured data, the exact
   total re-checked from live store data, and a test order number.

## Verify a result yourself

- Re-read the live store product:
  https://wsiventures.com/solemates/?rest_route=/wc/store/v1/products/23
  This shows the store's own data: price, stock flag, Size, Colour.
- Re-read the OVO endpoint for the same product:
  https://wsiventures.com/solemates/?rest_route=/ovo/v1/products/23
  This shows the OVO structured fields: Material, Fit, Returns.
  Before uses the store data only. After uses the store data plus
  the OVO fields. That contrast is the demo.
- Check the test order in the store's own order list, in test mode.
  A test order number shown only in the harness, with no matching
  store order, does not count as a paid order.

## Replay, export, and reset

- Use the Buyer, Trace, Timeline, Diff, and Logs tabs to view the
  same run from different angles. They are views of one run, not
  separate runs.
- Export run JSON from Logs if you need to read the run on another
  device. In this version, run logs live only in the judge's own
  browser. A shared link on another device will not show that run's
  logs.
- Demo reset restores the clean state for a new run. It never deletes
  judged run logs, ground truth, the fix diff, or past orders.

## What not to expect

- No live customer payment. Test mode only.
- No real Link payment yet. Agent payment, MVP, research preview: test mode only, test card only, bridge version 0.5.0-test, test orders 132, 135, and 136. A judge-entered browser test order is a fallback record only, not an agent payment.
- No full MCP, ACP, or UCP compliance.
- No consumer Muse personal agent discovery, unless tested in the
  actual product.
- No production plug-in compatibility claim, and no broad SMB
  onboarding claim.

## Meta calls, shown live

The top bar shows when a Meta Model API call is in flight, with model,
purpose, duration, and outcome. Audit and enrichment are deterministic
first. Muse Spark 1.3 only checks or shops. No Meta call is simulated.
No key ever appears on screen or in a log.

## If a stage is blocked

A blocked stage shows amber, states the block plainly, and shows any
dry-run or mock result as dry-run or mock, never as live. A blocked
stage is a failed live claim, not a hidden pass.
