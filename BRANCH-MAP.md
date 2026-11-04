# Branch map — repository gfields-wsi/ovo

Main is the default branch. Harness code was not merged to main. Judge docs were added to main on 2026-11-04. Read main first for the project story,
Decision 0, R1 to R10 mapping, eval runs, and ground truth.

## For judges: start here

- main, commit 8efc75198a5adaf98a3aeeec4e96f14126944184
  Project README, docs, eval runs, and the Sole Mates store source.
  Note: ovo-plugin/ on main is only a placeholder file. The real
  plug-in code is on the plugin-agent branch, below.
- ovo-harness, commit 93b9090d07b82fc02d9dea01c39fc751b1ac3790
  Folder ovo-harness/. Live harness code: index.html, meta.php,
  publish.php, README.md, and assets. Start here for the demo code
  behind https://wsiventures.com/ovoharness/index.html?v=14

## Agent branches: read for depth, not needed for the demo run

- audit-agent, commit 7c62c8af
  Folder ovo-audit-agent/. Audit gaps, scorecard, trace, guidance.
- enrichment-agent, commit 97c0b158
  Folder ovo-enrichment-agent/. Enrichment diff, accuracy tiers,
  per-run metrics, audit log, rollback rules.
- approval-agent, commit 8ef8a4e8
  Folder ovo-approval-agent/. Approval by group, decision rules.
- coordinating-agent, commit 245dd0ae
  Folder ovo-coordinating-agent/. Coordinator only: Audit, then
  Enrichment, then Merchant Approval, then Publish to Plugin.
- plugin-agent, commit 898167a6
  Folder ovo-plugin-agent/. WordPress plug-in 0.2.0-demo, publish
  in place, dry-run publish runner, production requirements.
- payment-bridge, commit 2c7bca4254093ec743e246f298c2264dbc096a11
  Folder ovo-payment-bridge/. Quote, approval token, live price
  and stock re-check, test-mode payment, mock tests. Agent test payment, MVP, proven in test mode only, orders 132, 135, and 136. Real Link is not proven yet. Mock tests are not a live payment claim.

## How to read this map

Judges: main README, then JUDGE.md, then the live harness, then
ovo-harness/ code if you want to check the demo implementation.
Agent branches are supporting evidence. They are separate branches
on purpose, and they are not merged to main.
