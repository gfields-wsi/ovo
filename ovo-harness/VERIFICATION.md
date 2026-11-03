# OvO Harness verification — A1 to A11, checked 2026-11-03

No partial credit is given here. A builder check is not an
independent judge check. Items marked pending are not passes.

## A1 — Fresh start
Local: PASS. Setup is: run `python3 server.py 8000`, open the page.
No key is in code or logs, checked by search. No WordPress admin
step and no plug-in activation is needed from the judge.
Hosted: NOT YET. Render is not deployed yet, because that needs
a repository push first, and a push needs Greg's approval of the
exact branch and folder.

## A2 — Live Before
API: PASS. A fresh live fetch for product 23 lists Size and Colour
as store structured fields, and Material, Fit, and Returns as
missing structured fields. Description prose values are shown as
prose only, not as structured fields. The run stops with the
stated reason.
Browser UI: PENDING. The browser test could not open
http://localhost:8001/ on its own, and is waiting for a user
takeover and hand-back.

## A3 — Live During
API: PASS, with a blocked publish step. A fresh live audit gives
35 proposals for Material, Fit, and Returns across 12 products
(the framework file gave 36 on 2026-10-31; product 92 now shows
no Returns value in prose). The judged product gives all 3 rows,
each with source field description and group 95 percent or
greater. A recorded approval was made, and a publish log was
made. The publish log is dry-run only and states the live-post
blocker plainly. No new live publish is claimed.

## A4 — Approval gate
PASS. Publish without approval returned 403 and logged a stop.
Publish after a recorded approval for group 95 or greater ran
the dry-run mapping only. Silence and a group that was not
submitted give no approval in code.

## A5 — Live After
FAIL for the live path, so far. A fresh After check shows the
OVO fields as structured data and a cart total re-checked live
at $1.00 CAD. No new test order number has been recorded yet.
The payment bridge for an agent-only payment is blocked, and
no mock payment is shown as live. A test order can only pass
this item after a merchant checkout in test mode, with the
order number from the confirmation page recorded in the harness.

## A6 — No invented data
PASS for the judged product. Material, Fit, and Returns for
product 23 trace to description prose, shown in the log. No
price, stock level, or policy was invented. Weight, dimensions,
and stock quantity are not proposed, because the prose does
not state them.

## A7 — Honest payment label
PASS. The page footer and payment card say test mode only.
The payment bridge is labelled blocked. The publish step is
labelled dry-run only. No mock payment is shown as live.

## A8 — Replay and reset
PASS. A new run was started by the reset path, and the old run
file is still present, with its logs and Meta call intact.
Reset does not delete run files, ground truth, the fix diff,
or past orders.

## A9 — Hosted match
FAIL, so far. The Render file is in the folder, with the same
code and stages, but no Render service is live yet. This needs
a repository push first, then Render access to that repository.
Until then, the hosted version cannot be checked.

## A10 — UCP pattern
Page structure: PASS. The page has a buyer view, a trace,
a timeline tab, a diff card, logs, a funnel with a stopping
stage, and errors labelled by source.
Browser UI: PENDING, for the same takeover reason as A2.

## A11 — Meta visibility
API: PASS. A real Meta call to Muse Spark 1.3 took 4.68 seconds,
with model, purpose, duration, outcome, and token counts from
the service itself, not estimated. No key appears in the run
file. The top bar indicator is set to Calling only while the
call is in flight in code, and to Done after it.
Browser UI: PENDING, for the same takeover reason as A2.

## A12 — Independent check
FAIL, so far. The independent browser check did not finish,
because the browser could not open the local page on its own.
It is waiting for a user takeover and hand-back. A builder
check alone does not count as a pass.
