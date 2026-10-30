# OVO Hackathon — Decision 0 and R1–R10 mapping

Standing rule, 2026-10-29, from Greg: the PRD is the truth.
Where the PRD, the earlier architecture, the mini plan, or any
summary disagree, the PRD governs. No PR-01–PR-22 citation, demo
shortcut, or summary counts as coverage against the PRD.

Status, 2026-10-29: Decision 0 DECIDED by Greg. R1–R10 VERIFIED
against a fresh PRD read on 2026-10-29, after Google Docs connected.
PRD title: "OvO PRD (Draft)". Full text extract saved at
docs/prd-extract-2026-10-29.txt. The R1–R10 list below matches the
fresh read. Note: R10 is P2 in the PRD, not P1; R1–R9 are P1.
Success measures confirmed: task success 80% or higher, enrichment
accuracy 85% or higher, agent experience 4 or higher out of 5.
Scope confirmed: WordPress + WooCommerce, Stripe, Meta Muse as
reference agent, US English. PRD enrichment autonomy tiers run from
95% or higher (acts alone, merchant rejects by exception) down to
under 50% (reject); the demo uses merchant approval for all
publishes, which is stricter than the PRD tiers and stays inside them.

PRD document (from the requesting chat):
https://docs.google.com/document/d/13lYCQq4D45HTolj9ZexVBKopOHUKN2O_00nWEEMfefI/edit

Repo (verified 2026-10-29 via the WSI corporate GitHub connection):
https://github.com/gfields-wsi/ovo — public, main branch, skeleton
pushed at 5cc929def6eecd9f6b36efedff75f6b8d970e2d8, latest main at
b8a0f39eb5395eef3e51f021b229b34593acb2b8 (README date fix).
Structure: sole-mates, ovo-plugin, ovo-agent, eval, docs.

## Decision 0 — decided 2026-10-29

- Track: Startup
- Theme: Build for Your World
- Reason given: OVO is a founder-led venture product for a firsthand
  SMB problem.
- OVO role (PRD version, confirmed): OVO works behind the scenes.
  It does not interact directly with the purchasing agent, and it is
  not involved in purchase rules or limits. Gates live in the store
  and in the agent tools, not in OVO as the buyer.
- Conflict settled: the earlier architecture made OVO a concierge
  that interacts, enforces budgets, and places the order. That version
  is superseded by the PRD version.

## Numbering reconciliation

- PRD: R1–R10.
- Earlier architecture: PR-01 to PR-22.
- Those do not map. Do not cite a PR number as PRD coverage.
- Every build item below is mapped to R1–R10 only. Any PR-01–PR-22
  item with no R1–R10 home is listed as unmapped, not silently kept.

## R1–R10 coverage map (draft)

- R1 — Sole Mates mock store, WordPress + WooCommerce, 10+ products.
  Updated 2026-10-29 by Greg, superseding the mini plan's 30–60 figure.
  Current Sole Mates storefront has 12 products, 79 variations, so it
  meets the 10+ bar. Build: sole-mates/. Messy-store ground-truth
  sheet first.
- R2 — Audit any public storefront from a URL, no login.
  Build: ovo-agent audit from URL alone.
- R3 — Repeatable readiness score with gaps.
  Build: score reported as raw store score and post-OVO score,
  separately, every time.
- R4 — Enrichment, no invented price, stock, SKU, tax, shipping, or
  policy claims. Per-fact source labels and accuracy tiers.
  Build: ovo-agent enrichment, merchant-approved field diff only.
- R5 — Enrichment stored in a cloud tenant.
  Build: OVO snapshot as staging and fast read cache only, never
  the shop.
- R6 — Agent-facing interface for the reference agent.
  Build: ovo-agent tools. Labelled MCP-shaped unless a real,
  discoverable MCP surface is tested. Never claim full MCP/ACP/UCP.
- R7 — Stripe agent checkout, autonomous and human-approved.
  Build: checkout ladder (see below). Both modes on the rung used.
- R8 — Order handoff to the merchant's existing system.
  Build: order lands in WooCommerce, shown on the merchant screen.
- R9 — Red-team testing for untrusted storefront and agent text. P1.
  Build: eval red-team run. The hostile page must change none of
  OVO's rules.
- R10 — Audit log of every interaction and decision.
  Build: log kept with runs; demo reset must not delete judged logs.

## Checkout ladder, labelled honestly

1. Store API checkout with Stripe test mode and expected total.
   Mismatch forces re-approval.
2. Add-to-cart handoff, human finishes on merchant checkout.
3. Last resort only: REST test order, labelled plainly as a stub,
   never as a payment.
Tell judges which rung was used.

## Proof targets

Same buying agent, same 25 golden tasks, same URL, before and after.
Task success 80% or higher. Enrichment accuracy 85% or higher
against ground truth. Agent experience 4 or higher out of 5.
Hostile page changes no rules.

## Meta use, named per stage

- Muse Spark: audit, enrich, augment.
- Muse Wonder: hard long-running runs.
- Muse Image and SAM 3.1: optional image work only. Neither verifies
  a photo matches the product. Never claim photo verification.
- Muse Code: coding agent.
Name the model behind each stage in the demo, README, and
merchant screen. If time runs short, cut animated celebration first,
never the proof.

## Dates

Feature freeze Nov 2. Submissions due Nov 4 at 9:00 PM ET.
Submit before noon ET Nov 4 as a buffer, from a frozen build.
Judging Nov 4–8. Finals Nov 9.
Rubric (unverified, from third-party summaries): impact 30%,
creative use of Meta AI tools 25%, demo including video 25%,
technical depth and execution 20%. Verify against the official
rules before submission.
