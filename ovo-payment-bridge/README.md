# OvO Payment Bridge — Separate Component, Test Mode Only

Status: Version 1.0.0, Phase 6, 2026-11-12. Test mode only, mocks only, plus live fail-closed tests on the local test install. bridge.py plus the Phase 6 tests pass in mock form. Not deployed to a live store. No live charges. No changes to the enrichment plugin. Level B Link approval and live acceptance criteria are NOT proven, and are blocked on inputs below.

Blocked, not code gaps: real merchant network id, real Link wallet spend request and customer approval, Stripe preview API access and secret key via Secure Vault, merchant bridge approval for a live store, CAD SPT test result, and Greg's separate approval to deploy to a live store and to charge live. Without those, Requirements 22.2, 22.3, and 20.2 cannot pass, and no live claim is made.

## Phase 6: what changed

Phase 6 adds four things, all in test mode first.

1. Merchant payment profile. The seller network id is derived from the merchant Stripe account id and stored per merchant, in the merchant site store, never shared across stores. In test mode the derivation is a labelled test derivation. The real derivation from Stripe is not proven: the real Link adapter fails closed on every call until a verified Link route and Greg's approval for a real Link test are both in place.

2. Link spend request through an adapter. The bridge asks Link for a single-use payment token for the exact merchant total. In test mode a mock adapter answers. The agent sends that token, with no card data, and the merchant creates the payment in its own Stripe account. Money stays with the merchant. The merchant stays the seller. OvO stores no card data.

3. Single-use human approval token. The token binds one human approval to one cart and one total. It is used up on first checkout. A cart change, price change, or stock change voids it. A declined payment uses it up too, so a retry needs a fresh human approval. An extra card check, such as 3D Secure, fails closed with no paid order.

4. Attribution. The bridge records the session to cart to paid order link on every paid order: session id, cart id, order id, agent route, human approval id, and subtotal before tax and shipping. The WordPress plugin writes the same link into the WooCommerce order record, so the merchant can see it in their own store. A signed attribution event goes to the OVO host, where Phase 4 billing records it: a linked agent order bills at the rate in force (1.5 percent for a standard merchant, 1 percent for a launch merchant), a test order bills zero, and a human order with no agent link bills zero. No link means no bill. The fee itself is set by Phase 4 billing, not by the bridge.

New tests: test_link_spend.py (profile and spend request), test_approval_token.py (single-use tokens), test_bridge_attribution.py (signed events and billing), test_bridge_phase6.py (end-to-end happy path and the fail-closed list). The old test_bridge_full.py now presents a fresh approval token on every checkout, as version 1.0.0 requires.

## Phase 6 finish, 13 November 2026

Two fixes closed the Phase 6 validation gaps.

1. Test name clash. Two files were both called attribution.py: the bridge event builder and the Phase 4 billing receiver. A full test run from the repo root imported the wrong one and failed. The bridge module is now bridge_attribution.py. Phase 4 billing is untouched. The full bridge suite runs 59 tests, all passing, from the repo root and from a fresh clone.

2. Order total gap, Requirement 6. The PHP checkout checked that subtotal plus tax plus shipping equals the charged amount, but then created the order with the product only and called calculate_totals() with no shipping line and no tax line set. WooCommerce could then work the total out again from its own rules, and nothing checked it against the charged amount. The PHP checkout now sets a shipping line and a tax line from the approved split before calculate_totals(), then reads the order total right after it: if the total differs from the charged amount, the order is held, not marked paid, the mismatch is logged, and the charge is named in the order note so the merchant can refund it. The checkout also accepts a simple product as its own line item, because the live test install has simple products only and a variation-only rule would refuse every checkout there. The return_url is the store home address, per store, not a demo store address.

Live total test: test_bridge_live_total.py runs the checkout on Site A with tax 500 cents and shipping 1000 cents above zero, and asserts the WooCommerce order total equals the charged amount. It needs the Stripe test secret on the test install host and the agent token set; without the secret it reports BLOCKED, not failed. It was not run end to end here: the machine has no PHP binary after the VM restart, Site A is down, and no Stripe test secret is on this machine. PHP lint is also open for the same reason. Those two checks stay open for Phase 6 validation.

Still open, carried to Phase 8: a real Link spend request, a real Shared Payment Token, a real paid order on a pilot store, and the merchant Stripe profile with the agentic commerce seller terms.

First store, Sole Mates, merchant Stripe account id, provided by Greg 2026-11-02: [Sole Mates merchant Stripe account id, provided separately, not published]. Network id / profile id for this account is still to be derived, via Stripe with a secret key, or via a 402 challenge. Do not use this account id as a network id without verification.

Scope: Agent to merchant, programmatic only, no browser step. WordPress plus WooCommerce only. Stripe only. Meta Muse as reference agent only. Generic for all OvO merchant customers, on all their web stores. Sole Mates is only the first store, for proof. Store address, merchant id, and seller network id are inputs per merchant, never hard coded to Sole Mates. Product and amount are inputs per purchase request, never hard coded. Linked Stripe card authentication happens per purchase request, via Link spend request approval at that time, never as a pre-saved token reused without approval.

Generic core, built 2026-11-02: core_generic.py plus test_core_generic.py, Requirements 1-22, no Sole Mates store, URL, or account id in those files, no live purchase session required for tests. Tests passed. External adapters for Link, Stripe, and WooCommerce are injected interfaces with mock adapters for tests; real adapters, Level B Link approval, and live charge are NOT proven by these tests.

Source of truth: `../ovo-plugin/PAYMENT-BRIDGE-REQUIREMENTS-2026-11-02.md` — 22 requirements, each with distinct acceptance criteria.

## Flow diagram

The diagram below shows the agent-to-agent flow, programmatic only, with no browser step. It is built from `build_diagram.py`, and the image file is in this same folder, so it renders on GitHub.

![OvO Payment Bridge flow](ovo-payment-bridge-flow.png)

Flow, in order:
1. User asks Muse agent to buy a product.
2. Agent creates a cart, from the purchase request.
3. Merchant calculates total, tax, shipping, and locks quote.
4. Agent creates a Link spend request, amount = merchant total.
5. Bridge checks network id, agent authorization, merchant approval.
6. User approves in the Link app, within 30 minutes.
7. Link issues SPT, single use, merchant scoped, amount limited.
8. Agent sends SPT, programmatic only, no card data, no browser.
9. Merchant creates PaymentIntent with SPT, own Stripe account.
10. Stripe charges, through merchant account.
11. Merchant creates paid Woo order, only after Stripe confirms.

Failure fails closed: declined, stock gone, quote void, or reused token creates no paid order. Card data is never collected, stored, or sent by OvO.

Boundaries, locked for this build:
- Merchant stays as merchant of record. Money stays with the merchant.
- OvO does not collect a card, store a card, or charge the buyer.
- Payment credential is a Shared Payment Token, SPT, id starting with `spt_`, issued by a Link spend request, credential type shared payment token, seller network id only.
- No browser checkout, no Link Pay Token, no virtual card form, no UCP Link completion.
- Test mode gate, split into Level A merchant redemption test, then Level B Link end to end test, then live only after both pass.
- Live CAD is gated on a CAD SPT test passing, otherwise live scope is USD only for the first live release.
- Endpoint paths in the requirements are proposed, not existing, and are used here as proposed: `/ovo-bridge/v1/manifest` and POST `/ovo-bridge/v1/checkout/complete`.
- Rate limits are proposed defaults, not merchant confirmed limits.
- No Stripe secret key is stored in this code. Any live Stripe call requires a key supplied via environment, test mode only, and fails closed if missing.
- No deployment to Sole Mates, no install on a live store, and no live charge without Greg's separate approval for that deployment step.

Work order:
1. Manifest, seller network id, agent authorization, merchant approval, cart, quote lock — Requirements 1 to 6.
2. Link SPT spend request, approval, SPT limits, programmatic submission, PaymentIntent charging — Requirements 7 to 12.
3. WooCommerce order, audit log, idempotency, failure closed, amount increase, refunds, rate limiting — Requirements 13 to 19.
4. Currency gate, separation, test mode Level A and Level B gates — Requirements 20 to 22.
5. Acceptance tests against mocks and test helper patterns, with verified-only results reported, no claim of live success until live tests pass.
