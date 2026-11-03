# OvO Harness

Thin, live proof screen for OVO. One page. Test mode only.

## What it proves, in order

1. Before: the agent reads the store only. Material, Fit, and Returns
   are missing as structured fields. The run stops with this reason:
   the agent will not pay unless it can verify material, fit,
   returns, stock, and the exact total from structured fields.
   A fact in description prose alone does not count.
2. During: Audit, then Enrichment, then Merchant Approval, then
   Publish to Plug-in. The harness itself does no audit,
   enrichment, approval, or publish work. It calls live store
   fetches, shows the diff, records a judge approval, and runs a
   dry-run publish mapping.
3. After: the agent reads the store plus the OVO fields. The same
   fields are now present as structured data. The exact total is
   re-checked from live cart data: $1.00 CAD for City Chelsea
   Rain Boots, black, size 10, product 23, variation 29.

## Honest limits, shown on screen

- Live publish is blocked. The plugin runner is dry-run only,
  and token auth on WordPress is untested. This run never claims
  a dry run as live. The live OVO fields already on the store
  came from the 2026-11-02 published batch, not from a fresh run.
- Agent-only payment is blocked. The payment bridge is not proven.
  The pass-through route is the merchant checkout in test mode,
  with a Stripe test card. A test order is recorded only from the
  order number on the merchant checkout confirmation page.
- Row set used: framework-style proposals, live count in the run.
  The framework file from 2026-10-31 gave 36 rows; a live check
  today gives 35, because product 92 now shows no Returns value
  in prose. Canonical row set stays open: framework-style rows
  or version 5 with 62 rows. This harness states its choice and
  its reason, and does not pick it in silence.
- Approval on this page is a demo merchant role for the judged
  run only. It does not prove merchant sign-in.

## Run it

```
python3 server.py 8000
```

Open http://localhost:8000

No key is in code, logs, or this folder. On a host, set
META_API_KEY in host settings only.

## Host it on Render

See render.yaml. The service runs `python3 server.py $PORT`.
Set META_API_KEY in the Render dashboard. Do not put it in
render.yaml, code, or logs. Render is the first host choice
from the runner notes, because a long run and lasting run logs
fit a worker better than a short web request host.

## Judge path

No WordPress admin access and no plug-in activation is needed
from the judge. Press Run Before, then Run OVO, then Run After,
in that order. Submit the approval group, then use the merchant
checkout in test mode and record the test order number.

## Files

- server.py: live store fetches, cart re-check, Meta calls,
  approval gate, dry-run publish mapping, run logs.
- static/index.html: one page, top bar, stepper, buyer view,
  stage output, trace, tabs, funnel, limits footer.
- assets/ovo_green.png, ovo_white.png, ovo_black.png: icons
  supplied by Greg, copied unchanged, 1050 by 450, not recoloured,
  stretched, cropped, or given effects. Green is used in the
  header on a light background, at 32 pixels high.
- runs/: one file per run. Reset starts a new run and never
  deletes old runs.
