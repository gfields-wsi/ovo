# Continuous start for the Coordinating Agent

Production scope only. No demo scope. No hardcoded store address. No hardcoded interval.

## Why this exists

The Coordinator spawns the Audit agent, but nothing spawns the Coordinator. The Coordinator only runs when a human runs it, unless a start is set up. A continuous start fixes that gap, without bypassing any gate.

## Start

Run: python3 trigger.py --continuous --store-url URL --interval SECONDS
This polls the live Store API for that store address only, and runs the Coordinator each time the catalog hash changes for that store address. After each run, the trigger keeps watching. It does not exit after one run.

Run: python3 trigger.py --once --store-url URL --interval SECONDS
Test only, one run. Production use is --continuous, not --once.

State: trigger_state.json, in this folder, per store address.
Result: trigger_run.json, in this folder.

Scheduled check: python3 check_and_run.py --store-url URL
The check script reads the live Store API, compares the catalog hash with the last seen hash for that store address, and runs the Coordinator only if the hash changed. No scheduled check is set by default. A scheduled check needs a production requirement and approval.

## Safety

A trigger is not an approval. The Coordinator still stops at the merchant approval gate, with published false, until the Merchant Approval agent records a merchant decision with publish allowed true. The trigger never publishes, never buys, and never bypasses a gate.

## Verified, 30 October 2026, test only

- Continuous trigger tested with a changed hash: Coordinator ran, exit 0, published false, trigger kept watching.
- Scheduled check tested with no catalog change: no run.
- Live run paused at Merchant Approval, Plugin agent not spawned, nothing published.
