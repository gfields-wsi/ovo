Coordinating Agent requirements, production scope only.
Work limited to the Coordinating Agent only. Spawned agent work is not in this list.
Flow: Audit, Enrichment, Merchant Approval, Publish to Plugin. Each stage runs through a relevant agent, not through the Coordinating Agent.
Prior status reporting requirement is removed. As an automated agent system, the Coordinating Agent does not report status updates to a person.
Live test results, 30 October 2026, are listed under each requirement.

Requirement 1. I start without a hand start when a store list changes.
Acceptance criteria are as follows. I start with a continuous start that runs always. I start when a store list changes. I start again after each run. I do not skip merchant approval. I do not publish on my own.
Result: PASS for code and test, with a correction. Continuous trigger tested with a changed hash, runs 1, exit 0, published false, trigger kept watching. Scheduled check for test store is removed. test store is a demo store, not a production store. Production check must use a real merchant store address, given by the merchant. Production interval must be given by the production requirement, not chosen by the Coordinating Agent. No interval is set now.

Requirement 2. I spawn the Audit agent, and I pass the store address to the Audit agent.
Acceptance criteria are as follows. I spawn the Audit agent first. I pass the store address to the Audit agent. I wait for the Audit agent to finish. I do not do audit work myself. The Audit agent does audit work.
Result: PASS, live test. Audit agent ran, 12 products, 120 of 180 core, 124 gaps, store address matched input.

Requirement 3. I spawn the Enrichment agent, and I pass Audit output to the Enrichment agent.
Acceptance criteria are as follows. I spawn the Enrichment agent after Audit. I pass Audit output to the Enrichment agent. I wait for the Enrichment agent to finish. I do not do enrichment work myself. The Enrichment agent does enrichment work.
Result: PASS, live test. Enrichment agent ran, 36 proposals, published false, proposal count matched actual proposed rows.

Requirement 4. I spawn the Merchant Approval agent, and I pause until the Merchant Approval agent records a merchant decision.
Acceptance criteria are as follows. I spawn the Merchant Approval agent after Enrichment. I pass Enrichment output to the Merchant Approval agent. I pause until the Merchant Approval agent records a merchant decision. I do not make approval decisions myself. The Merchant Approval agent records approval decisions.
Result: PASS, live test, paused correctly. Merchant Approval agent ran, packet ready, 36 rows presented, status awaiting_merchant_decision, publish allowed false, coordinator status paused_awaiting_merchant_decision, Plugin agent not spawned, nothing published.

Requirement 5. I spawn the Plugin agent, and I pass the approved list to the Plugin agent, only after approval.
Acceptance criteria are as follows. I spawn the Plugin agent after approval. I pass the approved list to the Plugin agent. I wait for the Plugin agent to finish. I do not do publish work myself. The Plugin agent does publish work.
Result: PASS for coordinator pass logic, in test only. With a test decision file only, not a merchant decision, Plugin agent mapped 36 approved rows, status dry_run_ready_not_posted, posted false, published false, errors none, fingerprint matched. Live publish does NOT pass yet. Live publish is blocked by Plugin stream work, not by coordinator work. Plugin runner refuses live post, plugin token auth is untested on WordPress, plugin is not installed on test store. Live publish also needs a real merchant decision, which is not given yet. Live approval record is restored to awaiting_merchant_decision, publish allowed false.

Requirement 6. I check each agent output, and I stop if any check fails.
Acceptance criteria are as follows. I check that each agent output exists. I check that each agent output form matches the agreed form. I check that each agent output count matches the prior stage count. I stop if any check fails. I do not run the next agent after a failed check.
Result: PASS, live test and test decision test. Gap form checked, enrichment count checked, approval fingerprint checked, publishable count checked. Plugin agent not spawned after a failed or missing approval, in live test.

Requirement 7. I log each coordination action, with source fields.
Acceptance criteria are as follows. The log lists each spawn. The log lists each pass to the next agent. The log lists each check. The log lists each pause. The log lists source fields for each coordination action.
Result: PASS, live test. coordinator_run.json lists spawn, check, and pause steps, with source files, flow Audit, Enrichment, Merchant Approval, Plugin, status paused_awaiting_merchant_decision, published false.
