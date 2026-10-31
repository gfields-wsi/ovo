# OvO Merchant Approval Agent — Remaining Requirements

Reading ease, prose version: 66.5, above the 60 bar.

This list covers only Merchant Approval Agent work. Items for the coordinator and for enrichment are removed. Those items belong to those agents. The record format for pass-back is already built. Reading it back is coordinator work, so it is not listed here.

## R1. Cards reach merchants live

Requirement: Merchants can open the cards without access to the workspace.

- A merchant can open the cards in a browser.
- Each card shows its accuracy group, its rows, and its values.
- No row under 50 percent is shown.
- The cards show the live Sole Mates packet, not test values.

## R2. Cards allow edits and submission on the card

Requirement: The merchant can correct a value, add information, and submit a group review on the card itself.

- Each presented row shows an edit field.
- A held row shows an add field where it applies.
- A correction is recorded exactly as given.
- A corrected row is marked merchant supplied.
- A submitted group review is recorded by group.
- No value is invented by the agent.

## R3. A real merchant approves the live packet

Requirement: A named merchant reviews the live packet and submits a decision. The agent records that decision.

- The record names the merchant.
- The record fingerprint matches the live packet.
- Approved rows, rejected rows, and not approved rows are all shown.
- Publish allowed is true only for approved rows.
- The live store is unchanged by the approval agent itself.

## R4. Only their data

Requirement: The agent shows and records a packet only for the merchant and store named in that packet.

- Each packet, card, and record carries a merchant ID and a store ID.
- A decision with a merchant ID or store ID that does not match the packet is rejected.
- A merchant cannot open a packet for another merchant or store.
- No packet lists rows from more than one store.

## R5. Questions about a row

Requirement: The merchant can ask a question on a row or group, and that row stays held until the merchant decides.

- Each row and group shows a question field on the card.
- A question is recorded with product, field, proposed value, merchant, and time.
- A row with an open question is not approved, and is not rejected.
- The merchant can close a question, then approve, reject, or correct the row.

## R6. Authority to approve

Requirement: The agent records a decision only from a merchant session for that store.

- A decision carries a merchant ID and a store ID from the session, not just a typed name.
- A decision with a missing, expired, or revoked session is rejected.
- A decision made only by an agent, without a merchant submission, is rejected.
- The record shows the merchant ID from the session.
- Revoking access ends approval rights for later decisions.

Notes, not requirements for this agent: answering a question belongs to Enrichment and Coordinator. Issuing a session is platform work. This agent only checks the session and the IDs it is given.
