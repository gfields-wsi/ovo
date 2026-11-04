# Branch map — repository gfields-wsi/ovo

Main is the default branch. Main is unchanged by the harness work.
Nothing was merged to main. Read main first for the project story,
Decision 0, R1 to R10 mapping, eval runs, and ground truth.

## For judges: start here

- main, commit 2ec172a0fd7790245c968608f5f9812b3d92b75a
  Project README, docs, eval runs, and the Sole Mates store source.
  Note: ovo-plugin/ on main is only a placeholder file. The real
  plug-in code is on the plugin-agent branch, below.
- ovo-harness, commit f0e2582911773b61397440076f6b7ef656369adb
  Folder ovo-harness/. Live harness code: index.html, meta.php,
  publish.php, README.md, and assets. Start here for the demo code
  behind https://wsiventures.com/ovoharness/index.html?v=10

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
- payment-bridge, commit 9e2d834e
  Folder ovo-payment-bridge/. Quote, approval token, live price
  and stock re-check, test-mode payment, mock tests. Live agent
  payment acceptance is not yet proven. Mock tests are not a live
  payment claim.

## How to read this map

Judges: main README, then JUDGE.md, then the live harness, then
ovo-harness/ code if you want to check the demo implementation.
Agent branches are supporting evidence. They are separate branches
on purpose, and they are not merged to main.
