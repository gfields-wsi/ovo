## Start here, judges

Live OvO Harness: https://wsiventures.com/ovoharness/index.html?v=10
Use the version link above. The plain link can serve a stale server-cached copy.

Harness code: repository gfields-wsi/ovo, branch ovo-harness, folder ovo-harness/
Commit: f0e2582911773b61397440076f6b7ef656369adb (2026-11-03)
Main is unchanged by the harness work. Nothing was merged to main.

Demo video (3 minutes): [VIDEO LINK TO BE ADDED BY GREG]

## The demo, in three steps

Locked task for the judged run: City Chelsea Rain Boots, black, size 10,
$1 CAD, product 23, at https://wsiventures.com/solemates

1. Run Before. The agent reads the store only, with no OVO fields.
   It stops, and the screen states the exact reason: the agent will not
   pay unless it can verify material, fit, returns, stock, and the exact
   total from structured fields. A fact in description prose alone does
   not count as a structured field.
2. Run OvO. Audit, Enrichment, Merchant Approval, and Publish, in that
   order. Each stage shows its own output, source, and log.
3. Run After. The agent reads the store plus the OVO fields. It shows
   the same fields now present as structured data, the exact total
   re-checked from live store data, and the test order in the store's
   own order list.

Full judge instructions: see JUDGE.md in this folder.

## Honest limits, up front

- Test mode only. No live customer payment.
- Agent payment is blocked. The payment bridge is not installed.
  A judge-entered browser test order is a fallback record only, not
  an agent payment.
- Publish is live for this demo store only, approval-gated, product 23
  only, additional_property fields only, token held on the host only.
- Do not claim full MCP, ACP, or UCP compliance, consumer Muse personal
  agent discovery unless tested in the actual product, live customer
  payment, production plug-in compatibility, or broad SMB onboarding.
- Payment stays pass-through: the merchant's checkout and processor,
  the merchant as merchant of record.

## How Meta tools are used, in two separate parts

Builder partner: Meta Muse, the personal agent, built and wired the
harness in its own virtual machine, iterated on it with Greg, checked
it in a real browser preview, and verified the push by reading the
branch back. [GREG TO CONFIRM: exact split between Codex files and
Muse fixes, before this paragraph is published.]

Runtime: Muse Spark 1.3, through the Meta Model API, is what the
harness calls when it shops and when it checks audit work. The harness
shows this live, with model, purpose, duration, and outcome, and no
key ever appears on screen. Audit and enrichment are deterministic
first. Spark only checks or shops. No Meta call is simulated.

---

# OvO

VIP Shopping Experience for AI Agents

OvO makes an SMB storefront shoppable by AI agents, on the store's own URL. OvO is the layer that fixes the store. OvO is not the shop.

## Status

Decision 0 DECIDED 2026-10-29 by Greg: Startup track, Build for Your World theme, OVO as the behind-the-scenes enabler, not the buyer. See docs/decision-0-and-mapping.md.

Live demo store: https://wsiventures.com/solemates — WordPress + WooCommerce, 12 products at $1 CAD, live, with a $1 Cash on delivery test order (#119) and a $1 Stripe test-mode order (#122) completed.

Day-one progress 2026-10-29: Muse Spark 1.3 tool calling and streaming verified via the Meta Model API; Store API products and cart verified (via `?rest_route=`); product JSON-LD present; Stripe test mode live in the store checkout. Agent Store API checkout with Stripe is still open: Stripe requires a payment token made through its own payment form, and a direct API token call is blocked.

## Structure

- `sole-mates/` — Sole Mates mock store, WordPress plus WooCommerce, 10+ products (12 in the current storefront, 79 variations).
- `ovo-plugin/` — Small WooCommerce plugin that publishes enrichment in place, with originals kept for revert.
- `ovo-agent/` — Audit, enrich, and shopping-agent tools, powered by Meta models.
- `eval/` — Golden tasks, ground truth, before-and-after runs, and red-team runs.
- `docs/` — Decision 0 and R1 to R10 mapping, day-one tests, and build order.

## Dates

Feature freeze: Nov 2, 2026.
Submissions due: Nov 4, 2026, at 9:00 PM ET. Submit before noon ET Nov 4 as a buffer, from a frozen build.
Judging: Nov 4 to 8, 2026.
Finals: Nov 9, 2026.

## Honest limits

Do not claim full MCP, ACP, or UCP compliance, consumer Muse personal agent discovery unless tested in the actual product, live customer payment, production plugin compatibility, or broad SMB onboarding. Payment stays pass-through: the merchant's checkout and processor, the merchant as merchant of record. Demo payment is Stripe test mode, labelled as such.
