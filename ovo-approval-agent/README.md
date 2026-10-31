# OvO Merchant Approval Agent

Group enrichments by accuracy. Present one card for each group. Record only the merchant's own decision, in aggregate, by group.

## Run

Packet mode, with no decision yet. Run python3 approval/agent.py.

Record mode, with a merchant decision file. Run python3 approval/agent.py --decision-file decision.json.

Copy approval/decision_template.json to start a decision file.

## Groups and actions

At 95 percent or better, the action is reject by exception. In a submitted group review, rows the merchant does not reject are recorded as approved.

At 80 to 94 percent, and at 50 to 79 percent, the action is approve individual. Rows the merchant does not explicitly approve are not approved.

Under 50 percent, no row is presented. No row under 50 percent is approved.

A group that is not submitted gives no approval. Silence, and a missed deadline, never count as approval.

## Only their data, questions, and authority

A packet, a card, and a record carry a merchant ID and a store ID, when those IDs are supplied. A decision whose IDs do not match the packet is rejected. No packet lists rows from more than one store.

A merchant can ask a question on a row or a group. A row with an open question is held. It is not approved and not rejected, until the merchant closes the question and decides the row.

A typed name alone is not authority. A decision must carry a merchant session for that store. The session must not be revoked. The session must not be expired. The session must be submitted by the merchant. The session check in this code looks at fields only. No signature is checked. No platform key is supplied yet.

## What this agent does not do

It never approves anything on its own. It never publishes. It never changes the live store. It does not re-check enrichment values. It does not recompute accuracy. Enrichment owns enrichment accuracy. The Coordinator owns the output. This agent only records merchant decisions.

Integration with the coordinator is for the OvO Hackathon organizer to confirm. This agent does not claim integration is done.

## Files

The agent code is approval/agent.py. It is built on the shared framework in framework/ovo_agent.py.

The agent guide is approval/AGENT.md.

The remaining requirements are approval/requirements.md.

The blank decision file is approval/decision_template.json. It includes a session template.

The example packet and cards are approval/approval_packet.json, approval_packet.md, and approval_cards.html. They show the live Sole Mates packet. Nothing in them is approved. Nothing in them is published.
