# OvO

VIP Shopping Experience for AI Agents

OvO makes an SMB storefront shoppable by AI agents, on the store's own URL. OvO is the layer that fixes the store. OvO is not the shop.

## Status

Skeleton only. No code yet.

Decision 0 is proposed, not decided. See docs/decision-0-and-mapping.md.

## Structure

- `sole-mates/` — Sole Mates mock store, WordPress plus WooCommerce, 30 to 60 products.
- `ovo-plugin/` — Small WooCommerce plugin that publishes enrichment in place, with originals kept for revert.
- `ovo-agent/` — Audit, enrich, and shopping-agent tools, powered by Meta models.
- `eval/` — Golden tasks, ground truth, before-and-after runs, and red-team runs.
- `docs/` — Decision 0 and R1 to R10 mapping, day-one tests, and build order.

## Dates

- Feature freeze: Nov 2, 2026.
- Submissions due: Nov 4, 2026, at 9:00 PM ET. Submit before noon ET Nov 4 as a buffer, from a frozen build.
- Judging: Nov 4 to 8, 2026.
- Finals: Nov 9, 2026.

## Honest limits

Do not claim full MCP, ACP, or UCP compliance, consumer Muse personal agent discovery unless tested in the actual product, live customer payment, production plugin compatibility, or broad SMB onboarding. Payment stays pass-through: the merchant's checkout and processor, the merchant as merchant of record. Demo payment is Stripe test mode, labelled as such.
