# OvO Merchant Approval Agent

Built on the shared OvO agent framework in ../framework/ovo_agent.py. It uses the approval phase in that framework.

## Job

Group enrichments by accuracy. Present one card for each group. Record only the merchant's own decision, in aggregate, by group. Never approve anything on its own. Never publish. Never change the live store. Never change the audit, enrichment, or accuracy files.

## Run

Packet mode, with no decision yet:

Run: python3 agent.py

Record mode, with a merchant decision file:

Run: python3 agent.py --decision-file decision.json

## Inputs

The agent reads three inputs, and it changes none of them. It reads the enrichment diff from ../stream2-enrichment/enrichment_diff.json. It reads the accuracy scorecard from ../accuracy/accuracy_scorecard.json, only to group rows. When a coordinator run file is present, it checks that file for a published flag only.

## Outputs

The agent writes files in this folder. It writes approval_packet.json, in format ovo-approval-packet 1.0. It writes approval_packet.md, a short packet for the merchant to read. It writes approval_cards.html, with one card for each accuracy group. It writes decision_template.json, with one group entry for each card. It writes approval_record.json, in format ovo-approval-record 1.0. It also writes approval_run.json, the audit log. When a decision asks or closes a question, it writes questions.json, in format ovo-approval-questions 1.0.

## Groups and actions

At 95 percent or better, the action is reject by exception. The merchant lists any rows to reject on the card. In a submitted group review, rows the merchant does not reject are recorded as approved.

At 80 to 94 percent, the action is approve individual. The merchant chooses approve for each row they want. Rows they do not explicitly approve are not approved.

At 50 to 79 percent, the same rule applies. The merchant chooses approve for each row they want.

Under 50 percent, no row is presented. No row under 50 percent is approved.

A group that is not submitted gives no approval for any row in that group. Silence, and a missed deadline, never count as approval.

## Accuracy grouping

A row's accuracy percent is taken from accuracy_percent on the diff proposal, when present. If that field is absent, it is taken from the accuracy scorecard result for that row. In that case, accurate true maps to 100 percent, and accurate false maps to 0 percent. The scorecard today marks each row accurate or not accurate only, so it gives no finer percent. Finer percent groups need the Coordinating Agent to supply a percent for each row in future. A row with no accuracy value is ungrouped. It is not presented.

## Trust and roles

This agent trusts the enrichments it is given. It does not re-check enrichment values against source text. It does not recompute accuracy. If enrichment is wrong, that is Enrichment and Coordinator work to fix, not this agent's work.

The Enrichment Agent is Responsible for the enrichment and its accuracy. The Coordinating Agent is Accountable for the enrichment output. The Merchant Approval Agent is neither Responsible nor Accountable for enrichment accuracy. It is Responsible only for recording merchant decisions accurately, in aggregate, by group.

## Merchant corrections and additions

The merchant can correct a proposed value, or add information where it applies. The agent records the merchant value exactly as given. It marks that value as merchant supplied, separate from the enrichment value. A corrected row counts as approved as corrected, only when the merchant submits it. An added row must refer to a held gap in the diff. It counts as approved as merchant supplied, only when the merchant submits it. The agent does not check a correction or an addition. The agent does not invent a value. Full card edit design comes later. The record supports corrections and additions now.

## Gate checks

These checks are this agent's own checks only. They are not accuracy checks. The diff must be proposed only, not published. The claimed proposal count must match the actual proposed rows. Every proposed row must be for material, fit, or returns only. Every proposed row must require merchant approval, must not be published, and must have a source label. The scorecard format must be correct, and it must not be published. Tenant IDs in the diff and in the scorecard must not conflict. When a coordinator run file is present, it must not say published true. If a check fails, the gate closes. The packet files are removed, and a blocked record is written. Nothing may be published from a blocked record.

## Only their data

A packet, a card, and a record carry a merchant ID and a store ID, when those IDs are supplied. The store ID comes from the diff, then the scorecard, then the audit store URL, then a command line value. The merchant ID comes from the diff, then the scorecard, then a command line value. No ID is invented. Today the live inputs supply a store URL and no merchant ID, so the live packet is marked store only, with no merchant ID. That gap is recorded, not hidden. A decision whose merchant ID or store ID does not match the packet is rejected. No packet lists rows from more than one store. The tenant check is enforced when a decision is recorded. A static card file cannot enforce who opens it, so a live card service must check the tenant before it serves a card. That service check is platform work, not yet built.

## Questions

The merchant can ask a question on a row or a group. The question is recorded in questions.json, with product, field, proposed value, merchant, and time. A row with an open question is held. It is not approved, and it is not rejected. The merchant can close a question, then decide the row in a later decision. A row cannot have a question and a decision in the same file. A row with an open question cannot be decided until that question is closed. Answering a question is Enrichment and Coordinator work, not this agent's work. This agent records the question and the close only. A question alone is a valid submission, with no approval. Its record state is questions recorded.

## Authority

A typed name alone is not authority. A decision must carry a session object from the merchant. The session must name a merchant ID, a store ID, and a session ID. It must be submitted by the merchant, not by an agent. It must not be revoked. It must not be expired. The session IDs must match the packet tenant IDs, when the packet has them. The record shows the merchant ID from the session. A decision with a missing, expired, revoked, or agent-submitted session is invalid. A decision with a session store ID that does not match the packet is invalid. This code checks session fields, expiry, revocation flag, and ID match only. It does not verify a cryptographic signature, because no platform issuer or key is supplied yet. That proof is platform work, not yet built. Older decision files with a name only are now invalid, by design.

## The merchant decision

The merchant decides, not the agent. The decision file must use format ovo-merchant-decision 1.0. It must name the merchant in approved_by. It must carry a session object from the merchant, as set out under Authority above. It must carry the exact diff fingerprint from the packet. Each group entry must set submitted true or false. A submitted group may list rejections, approvals, and corrections for rows in that band. In the 95 percent or better band, an approvals list is not used. Use the rejections list there. A decision for a row outside its band makes the decision invalid. A duplicate decision makes the decision invalid. A correction without a corrected value makes the decision invalid. An addition without an added value, or for a row that is not a held gap, makes the decision invalid. A fingerprint that does not match makes the decision invalid. A question for a row that is not in the packet makes the decision invalid. A decision for a row with an open question, without closing that question, makes the decision invalid. An invalid decision writes a record with publish allowed set to false. It never opens the publish gate.

## Binding

The diff fingerprint is a SHA-256 hash of the exact proposed rows, sorted by product and field. Augment must check that fingerprint against the live diff before it publishes anything. A new diff needs a new approval record. A record for an old diff must not be reused.

## Held rows

Held rows have no proposed value. They are not presented as enrichment. They stay held, unless the merchant adds a value for that held gap. In that case, the added value is recorded as merchant supplied, not as enrichment.

## Record states

Awaiting merchant decision means no decision has been recorded yet, and nothing may be published. Approved all presented means every presented row was approved, as proposed or as corrected. Approved partial means some rows were approved, and others were rejected or not approved. Rejected all presented means every presented row was explicitly rejected. No rows approved means no presented row was approved, and no added row was given. Questions recorded means a question was asked or closed, with no row approved. Invalid decision means the decision file failed a check, and nothing may be published. Blocked gate failed means a gate check failed.

## Scope limits

This agent does not publish. Publishing is Augment work, after approval, with originals kept for revert. This agent does not claim MCP, ACP, or UCP compliance. It does not claim live payment or production plugin compatibility. It does not claim that a test approval is a real merchant approval. Integration with the coordinator is for the OvO Hackathon organizer to confirm. This agent does not claim integration is done.
