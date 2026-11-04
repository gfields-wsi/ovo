![OvO Harness](assets/ovo_green.png)

# OvO — Overview

OvO makes a small business web store shoppable by AI agents. It does not sell anything itself. It audits a store. It enriches product data. It gets merchant approval. It publishes the fix in place on the merchant's own store. It supports an agent purchase.

Problem: a store can look fine to a human shopper, but lack structured fields an agent needs. Material, Fit, and Returns may live only in description prose. An agent that needs structured data must stop.

Solution: OvO finds those gaps. It proposes structured fields from store text. A merchant approves them by group. OvO publishes only approved fields, in place. The agent can then verify the same fields, and proceed.

Who it is for: small business merchants, and autonomous shopping agents that shop on their behalf.

Scope now: this is an MVP, a research preview, built in a few days. Test mode only. Test card only. No real Link yet. No real customer payment yet.

## Start Here — Judge Review Path

Goal: verify that OvO helps an AI shopping agent proceed from incomplete merchant product data to a more actionable shopping outcome.

1. **Watch the demo** — [Video](https://youtube.com/shorts/i1ncawyazM0)
   - Understand the merchant problem and the before and after claim.
2. **Understand the flow** — [How OvO Works](#how-ovo-works)
   - Identify Muse, OvO agents, WooCommerce integration, and the payment boundary.
3. **Run the judge test** — [Launch harness](https://wsiventures.com/ovoharness/index.html?v=14)
   - Execute Before, then OvO, then After, using the same shopping task.
   - Locked task: City Chelsea Rain Boots, black, size 10, $1 Canadian, product 23, variation 29, store https://wsiventures.com/solemates
   - Expected Before outcome: agent stops at Searched. Material, Fit, and Returns are missing as structured fields.
   - Expected OvO outcome: Audit gaps, Enrichment proposals, Approval cards by group, then Publish for approved groups only.
   - Expected After outcome: same fields present as structured data. Exact total re-checked live. Test checkout proven in test mode only.
   - Compare input snapshots and outcome. Do not assume checkout or payment completed unless live evidence confirms it.
4. **Inspect Meta AI evidence** — [Meta AI Integration](#meta-ai-integration)
   - Review model ID, purpose, duration, and outcome for each Meta call, in the harness Trace pane.
   - After a run, open Logs and press Export Run JSON. That file carries timestamp, run ID, events, and results.
5. **Inspect the implementation** — [Technical Architecture](#technical-architecture) and [Repository Structure](#repository-structure)
   - Review source, tests, run instructions, and known limitations.

Detailed judging guide: [JUDGE.md](JUDGE.md)

## Capabilities and Implementation Status

| Feature | Description | Status |
|---|---|---|
| OvO Harness | Live judge console to run Before, OvO, and After, with Trace, Timeline, Diff, and Logs | MVP, live at version 14 |
| Audit | Finds missing structured fields in a store, with gaps and a readiness score | MVP, live |
| Enrichment | Proposes Material, Fit, and Returns from store text, with a source for each field | MVP, live, 36 rows for 12 products |
| Merchant Approval | Approval by group, where the judge acts as merchant for the demo, silence never counts as approval | MVP, live |
| Publish in place | Writes only approved fields to the merchant store, through the plugin, with batch IDs recorded | MVP, live |
| OvO Enrichment Plugin | WooCommerce plugin, version 0.2.0-demo, with a live OVO endpoint and a token gated diff endpoint | MVP, live |
| OvO Payment Bridge | Agent to agent checkout endpoint, with live price and stock re-check, and a manifest endpoint | MVP, live, version 0.5.0-test, test mode only |
| Agent checkout, test card | Agent initiated checkout with a test card, no human checkout step, no Link token needed | MVP, live, test orders 132, 135, and 136 |
| Agent checkout, real Link | Link spend request, human Link approval, and token checkout, through the merchant Stripe account | Next step, not done yet |
| Meta Model API traces | Each Meta call shows model, purpose, duration, and outcome, in the top bar and in Trace | MVP, live, Muse Spark 1.3 |
| Export Run JSON | Portable run file with timestamp, run ID, events, and results, from Logs after a run | MVP, live |
| Sole Mates mock store | WordPress plus WooCommerce demo store, 12 products at $1 Canadian, with the locked judged task | MVP, live |
| Flow diagram | High level OvO Agentic Commerce Flow image, with Shopper, Muse, Store, Agents, Plugin, Bridge, and Stripe | MVP, live, in How OvO Works |
| Demo video | 3 minute video of the judged run, Before, OvO, and After | MVP, live |
| Judge guides | README, JUDGE.md, SETUP.md, and BRANCH-MAP.md, with the same version 14 links | MVP, live |
| Render deployment | Hosted deployment of the harness, outside cPanel | Next step, not done yet |

## How OvO Works

![OvO Agentic Commerce Flow](assets/OvO_Agentic_Commerce_Flow_Diagram.png)

Caption: This flow shows the intended roles, not the exact code path. In the live demo, the agent must verify material, fit, returns, stock, and the exact total from structured data before any payment, and must stop with no payment and no order if any of those are missing. The OvO Payment Bridge calls Stripe, through the merchant Stripe account, in test mode only, and creates a WooCommerce order only after Stripe confirms. Real Link payment is not shown as a proven step, because it is not proven yet.

How it works, in short: a shopper asks Muse to buy a product. Muse reads the store. OvO agents audit the store, enrich missing fields, and ask for merchant approval. The WooCommerce plugin publishes approved fields in place. Muse then reads the enriched store, verifies the fields and the exact total, and calls the Payment Bridge. The Bridge calls Stripe in test mode, and creates a WooCommerce order after Stripe confirms.

## Meta AI Integration

Model used in the harness: Muse Spark 1.3, through the Meta Model API, through a server proxy. No key is in browser code. No key is in logs.

What Muse decides: Muse makes the Before and After shopping decisions. It also checks Audit gaps. Each call shows model, purpose, duration, and outcome, live, in the top bar and in Trace. Token counts are shown only if the API returns them. Token counts are never estimated. No Meta call is simulated.

What deterministic code handles: Audit gap finding is deterministic first, then checked by the model. Enrichment proposals come from store text, with a source for each field. Bridge checkout checks, in order, are code: agent token, merchant approval, live price and stock re-check, currency, and idempotency.

What Muse does not do: Muse does not invent price, stock, or policy. Publish does not happen without a recorded, matching approval. Payment does not happen unless material, fit, returns, stock, and the exact total are verified from structured data.

Builder note: Meta Muse built and wired the harness, iterated with Greg, checked it in a real browser preview, and verified the push by reading the branch back. Codex supplied the original harness files. Muse fixed and extended them.

Sanitized trace evidence: use a live run, then open Trace, then open Logs and press Export Run JSON. That exported file is the sanitized trace for that run. A separate published trace file is on the Roadmap, not yet published.

## Technical Architecture

Store: WordPress plus WooCommerce. Harness: a static page plus two server proxies. Plugin: OvO Enrichment, version 0.2.0-demo. Bridge: OvO Payment Bridge, version 0.5.0-test. Test mode only.

Components and boundaries: the harness calls the store API and the OVO endpoint directly. It calls Meta through meta.php, a server proxy. It calls Publish through publish.php, a server proxy. Tokens and keys live in host settings only, never in browser code. Publish is live for this demo store only. Publish is approval gated. Publish is product 23 only. Publish is additional_property fields only.

Data flow: store catalog, then OVO fields, then Audit gaps, then Enrichment proposals, then Approval, then Publish, then enriched store, then Bridge checkout, then WooCommerce order.

Code paths: harness code is branch ovo-harness, folder ovo-harness, commit 93b9090d07b82fc02d9dea01c39fc751b1ac3790, live at version 14. Bridge code is branch payment-bridge, folder ovo-payment-bridge, commit 2c7bca4254093ec743e246f298c2264dbc096a11, version 0.5.0-test. Agent code is in its own branches, listed in Repository Structure below, not merged to main.

## Evaluation Evidence and Results

Controlled baseline: Before reads the store catalog only, not the OVO endpoint. Material, Fit, and Returns are missing as structured fields, 3 missing. The agent stops at Searched. No order is placed.

Enrichment delta: 36 rows published for 12 products on November 2, 2026. For product 23, all 3 fields are present: Material, Fit, and Returns. Live publish batches, from the harness, include 18c5791c, 464619df, and 9f5c928c.

After run outcome: After reads the store catalog plus the OVO endpoint. Same fields present as structured data, 0 missing. Exact total re-checked live, $1 Canadian. Test checkout proven in test mode only, test card only.

What has been verified: live publish, live test checkout with orders 132, 135, and 136, and live Meta calls with traces in the harness. Order 132 used a test helper token. Orders 135 and 136 used a test card, with no Link token.

What has not been verified: real Link payment, real customer payment, Render deployment, production plugin compatibility, broad SMB onboarding, full MCP, ACP, and UCP compliance, and consumer Muse discovery. None of those are claimed.

Caveats: run logs live only in the judge's own browser, unless Export Run JSON is used. A shared link on another device will not show that run's logs. Server cache can serve a stale copy of the plain harness link. Use the version link, version 14. Browser cache can also show an old copy. Use a private window to check a new version.

Logs and artifacts: Trace, Timeline, Diff, and Logs in the harness, plus Export Run JSON after a run. Test orders are in the store's own order list, in test mode.

## Repository Structure

- `sole-mates/` — Sole Mates mock store, WordPress plus WooCommerce, 12 products in the current storefront.
- `ovo-plugin/` on main — Placeholder only. Real plugin code is on branch plugin-agent, folder ovo-plugin-agent/.
- `ovo-agent/` on main — Placeholder and docs only. Real agent code is in its own branches, below, not merged to main.
- Agent branches, not merged to main: audit-agent (ovo-audit-agent/), enrichment-agent (ovo-enrichment-agent/), approval-agent (ovo-approval-agent/), coordinating-agent (ovo-coordinating-agent/), plugin-agent (ovo-plugin-agent/), payment-bridge (ovo-payment-bridge/).
- Harness branch: ovo-harness (ovo-harness/), live at version 14.
- `eval/` — Golden tasks, ground truth, before-and-after runs, and red-team runs.
- `docs/` — Decision 0 and R1 to R10 mapping, day-one tests, build order, and development-history.md.
- `assets/` — OvO logos, favicon, bear image and GIF, and the flow diagram.

## Reproduce and Run Locally

For judges, fastest path, no install: open the live harness at https://wsiventures.com/ovoharness/index.html?v=14, then follow JUDGE.md. You need no WordPress admin access, no plugin step, and no key. Do not enter a key anywhere on this page.

For a builder, to host the harness code locally: upload the ovo-harness/ files to a web host that runs PHP. Set host keys only, META_API_KEY or META_MODEL_API_KEY for Meta, and OVO_TOKEN for Publish. Those names are key names only, not key values. Open index.html with a version query, for example index.html?v=14, to avoid a stale server-cached copy. Purge server cache if the plain link stays stale.

Dependencies: a web host that runs PHP, a WordPress plus WooCommerce store for the live demo, and host keys for Meta and Publish. The live Sole Mates store is hosted separately, at https://wsiventures.com/solemates. The sole-mates/ folder in this repo is store source, not a running store.

Test procedure: press Run Judge Test, then Run OvO, then Run After. Approve a group to allow publish for that group only. Silence never counts as approval.

Expected results: Before stops at Searched. OvO shows Audit, Enrichment, Approval, and Publish. After shows fields present, total re-checked, and test checkout proven in test mode only.

Troubleshooting: if the plain link shows old wording, use the version link, then a private window. If Meta calls fail plainly with 503, no key is set on the host. That is expected, not a bug. If Publish fails plainly, no token is set, or no approval is recorded. That is also expected, not a bug.

## Limitations and Roadmap

MVP scope now: test mode only, no real Link yet, no real customer payment yet, no Render deployment yet, run logs are browser only unless exported, and the plugin revert step is admin only.

Roadmap, in order: real Link payment, with a Stripe profile ID, a Link spend request step, human Link approval, and token checkout. Render deployment, as a later host option. Private core repos after submission, with public branches pointing to interface docs only. License scoping, with MIT only for demo code, and legal review for the plugin GPL question and for license scope. A sanitized Meta trace file, with model, purpose, input, decision, output, duration, and run ID, no key, no private prompt text. A current harness screenshot, with an animated bear as secondary, not primary. Production plugin compatibility, broad SMB onboarding, full MCP, ACP, and UCP compliance, and consumer Muse discovery, all as future work, none claimed now.

Payment stays pass-through in spirit: the merchant's checkout and processor, the merchant as merchant of record, for the production design. For this MVP demo, the Bridge calls Stripe through the merchant Stripe account, in test mode only.

## License, Ownership, and Third-Party Notices

License holder for the hackathon submission: Greg Fields, because Meta approved Greg personally, under his personal account, and Greg used that approved slot to build under WSI.

MIT applies only to intentionally reusable demo code, such as the harness demo and mock store, as scoped in the repo license files. Do not read the root MIT license as a blanket grant for all future proprietary work. Each component needs its own scoped license notice, once IP decisions are made.

WordPress and WooCommerce plugin licensing needs legal review, because a plugin that depends on WordPress and WooCommerce code may need to be GPL compatible if it is distributed. That review has not been done yet. Do not assume all plugin code can be kept proprietary.

No key is in this repository. Do not add one. Keys live on the host only, in host settings or in a private file outside public_html.
