# Development History

Moved here from the main README, to keep the main README judging-first. This is history, not the judged run.

## Status, October 29, 2026

Decision 0 DECIDED 2026-10-29 by Greg: Startup track, Build for Your World theme, OVO as the behind-the-scenes enabler, not the buyer. See docs/decision-0-and-mapping.md.

Live demo store: https://wsiventures.com/solemates — WordPress + WooCommerce, 12 products at $1 CAD, live, with a $1 Cash on delivery test order (#119) and a $1 Stripe test-mode order (#122) completed. Bridge test orders, all $1 CAD, test mode only: #132 (test helper token), #135 and #136 (test card only, no Link token).

## Day-one progress, October 29, 2026

Muse Spark 1.3 tool calling and streaming verified via the Meta Model API. Store API products and cart verified. Product JSON-LD present. Stripe test mode live in the store checkout.

Historical note: Agent Store API checkout with Stripe was still open on October 29, because Stripe required a payment token made through its own payment form, and a direct API token call was blocked. Superseded November 4, 2026, by the bridge MVP, test orders 132, 135, and 136.

## Dates

Feature freeze: Nov 2, 2026. Submissions due: Nov 4, 2026, at 9:00 PM ET. Submit before noon ET Nov 4 as a buffer, from a frozen build. Judging: Nov 4 to 8, 2026. Finals: Nov 9, 2026.
