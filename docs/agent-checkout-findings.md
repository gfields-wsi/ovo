# Agent checkout findings — WooCommerce Stripe Gateway 11.1.1, 2026-10-29

## What the plugin source actually says

Read from the published plugin zip (woocommerce-gateway-stripe 11.1.1),
not from a summary. The block checkout sends this Store API payment_data:

- `payment_method` = `stripe`
- `wc-stripe-payment-method` = Stripe payment method id, e.g. `pm_...`
  (empty when a confirmation token is used instead)
- `wc-stripe-confirmation-token` = Stripe confirmation token id
- `express_payment_type` = `` (empty for card)
- `wc-stripe-is-deferred-intent` = true

The gateway's `process_payment` reads `$_POST['wc-stripe-payment-method']`
(or the confirmation token). When that value is empty, it throws
exactly the error the earlier Store API test hit:
"Your payment details were not submitted."

## Why the raw API route fails

A plain API call to Stripe with the publishable key to create a
payment method is rejected by Stripe: that integration surface is
unsupported for publishable-key tokenisation. Stripe only allows
tokenisation through Stripe.js / Elements, in a browser context.

## Consequence, labelled honestly

- A pure Store API checkout with an empty payment_data can never
  pass on this gateway version. It is not a missing field; it is a
  missing browser-made token.
- The demo's agent checkout therefore has two honest shapes:
  1. Agent decides via Store API (find, compare, cart, exact total
     re-check, human approval), then a browser tool runs the
     merchant checkout's own Stripe Elements step and places the
     order. Payment stays pass-through, merchant is merchant of
     record, Stripe test mode.
  2. Or drop to checkout ladder rung 2: add-to-cart handoff, human
     finishes on the merchant checkout.
- Local headless browser attempt (2026-10-29): Playwright installs,
  but its Chromium download failed, and Muse's own Chromium binary
  refuses to launch outside its own policy ("Hatch WebGL domain
  policy is required"). So the browser tool in this environment is
  the available Elements surface, not a local headless script.
- Do not claim a pure API agent payment on this gateway. Name the
  route used in the demo, README, and merchant screen.
