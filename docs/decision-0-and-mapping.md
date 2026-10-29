# OVO Hackathon — Decision 0 and R1–R10 mapping

Status, 2026-10-29: DRAFT, not verified against a fresh PRD read.
Google Docs is not connected in this chat, so the PRD could not be
re-read here. The R1–R10 list below is the Oct 28 PRD read plus the
mini plan carried into this chat. Re-verify it in full once Docs is
reconnected, before claiming coverage.

PRD document (from the requesting chat):
https://docs.google.com/document/d/13lYCQq4D45HTolj9ZexVBKopOHUKN2O_00nWEEMfefI/edit

Repo: https://github.com/gfields-wsi/ovo
Confirmed public 2026-10-29. Main branch, 2 commits, only README.md
at that time. Push access still needs to be verified before pushing.

## Decision 0 — proposed, not decided

- Track (proposed): Startup
- Theme (proposed): Build for Your World
- Reason given: OVO is a founder-led venture product for a firsthand
  SMB problem.
- OVO role (PRD version, to confirm): OVO works behind the scenes.
  It does not interact directly with the purchasing agent, and it is
  not involved in purchase rules or limits. Gates live in the store
  and in the agent tools, not in OVO as the buyer.
- Conflict to settle: the earlier architecture made OVO a concierge
  that interacts, enforces budgets, and places the order. That version
  is superseded if the PRD version is confirmed.
- Needed: Greg's yes/no on track, theme, and the PRD role before
  building on them.

## Numbering reconciliation

- PRD: R1–R10.
- Earlier architecture: PR-01 to PR-22.
- Those do not map. Do not cite a PR number as PRD coverage.
- Every build item below is mapped to R1–R10 only. Any PR-01–PR-22
  item with no R1–R10 home is listed as unmapped, not silently kept.

## R1–R10 coverage map (draft)

- R1 — Sole Mates mock store, WordPress + WooCommerce, 30–60 products.
  Build: sole-mates/. Messy-store ground-truth sheet first.
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
