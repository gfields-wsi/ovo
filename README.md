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
