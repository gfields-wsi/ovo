# OvO Coordinating Agent

Built on the shared OvO agent framework in ../framework/ovo_agent.py.

## Job, production scope only

Spawn relevant agents of defined scope, in order, fail-closed. Pause at approval gates for the merchant decision. Do not publish on your own. Do not buy. Do not approve on your own. Do not report status updates to a person, as an automated agent system. Do not claim integration is done. The organizer confirms integration.

Flow, in order, through relevant agents only:
1. Audit agent
2. Enrichment agent
3. Merchant Approval agent, pause here
4. Plugin agent, only after approval

The Coordinating Agent does no audit work, no enrichment work, no approval decisions, and no publish work. The Coordinating Agent spawns each relevant agent, passes output from one agent to the next agent, waits for each agent to finish, checks each agent output, stops if any check fails, and logs each coordination action with source fields.

Accountability, set by Greg on 30 October 2026: the Coordinating Agent defers to each spawned agent in its own scope, but it stays accountable for their outcomes. Accountability does not end when the Merchant Approval Agent finalizes merchant approval. After approval, the coordinator spawns the Plugin Agent to publish the approved list to the product catalog, and checks the Plugin agent output. Building those workers stays in their own streams. Coordinating them is the coordinator's job.

## Run

Run: python3 coordinator.py --store-url URL
Optional: --skip-spark, --decision-file DECISION_FILE
The decision file must come from the merchant only. Without a decision file, the Merchant Approval agent runs in packet mode, and the coordinator pauses at Merchant Approval, with published false, and does not spawn the Plugin agent.
Output: coordinator_run.json in this folder.

Trigger: python3 trigger.py --continuous --store-url URL --interval SECONDS
The trigger polls the live Store API, and runs the coordinator each time the catalog hash changes, for that store address only. State is per store address. A trigger is not an approval. The trigger never publishes, never buys, and never bypasses a gate.

Scheduled check: python3 check_and_run.py --store-url URL
The check script reads the live Store API, compares the catalog hash with the last seen hash for that store address, and runs the coordinator only if the hash changed. No store address and no interval are hardcoded in production code. No scheduled check is set by default. A scheduled check needs a production requirement and approval.

## Workers, defined in workers.json

- Audit: built. Audit agent does audit work. Coordinating Agent spawns Audit agent and passes store address.
- Enrichment: built. Enrichment agent does enrichment work. Coordinating Agent spawns Enrichment agent and passes Audit output.
- Merchant Approval: built. Merchant Approval agent records merchant decisions. Coordinating Agent spawns Merchant Approval agent, passes Enrichment output, and pauses until a decision is recorded.
- Plugin: built, dry-run only in its own runner. Plugin agent does publish work. Coordinating Agent spawns Plugin agent only after approval, and only with the approved list. Live post is refused by the Plugin runner until its own stream proves token auth on WordPress, and the plugin is installed on a real store.

## Fail-closed checks

The coordinator verifies each agent output, not just its exit code:

- Audit output must be ovo-gap-list 1.0, and its store address must match the input store address.
- Enrichment output must be proposed only, not published, and its proposal count must match its actual proposed rows.
- Approval output must be ovo-approval-record 1.0, not published, and its fingerprint must match the Enrichment diff fingerprint.
- If approval allows publish, the publishable count must match the approved rows, and the approved list must not be empty.
- If any check fails, the coordinator writes coordinator_run.json with status "failed" and stops. It does not run the next agent, and it does not leave an old success log standing as the latest run.

## Live test result, 30 October 2026, test store only, not production

Audit agent ran, 12 products, 120 of 180 core, 124 gaps. Enrichment agent ran, 36 proposals, published false. Merchant Approval agent ran, packet ready, 36 rows presented, status awaiting merchant decision, publish allowed false. Coordinator paused at Merchant Approval, Plugin agent not spawned, nothing published, live store unchanged.
Plugin pass logic tested in dry-run only, with a test decision file only, not a merchant decision: Plugin agent mapped 36 approved rows, status dry_run_ready_not_posted, posted false, published false, errors none, fingerprint matched. Live publish is not complete, for Plugin stream reasons and for lack of a real merchant decision.
