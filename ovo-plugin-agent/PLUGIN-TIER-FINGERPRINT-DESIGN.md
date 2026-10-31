# Plugin-side tier and fingerprint verification, design note, not yet coded

Purpose: close production requirements 3, 4, and 5 from
PRODUCTION-PRD-REQUIREMENTS.md, without coding a speculative
version that the organizer has not locked.

## What version 0.2 does today

- Token calls must carry approved_by and approval_fingerprint.
  Presence only. The plugin does not verify either value.
- Confidence below 50 percent is rejected. No other tier
  is enforced. The admin path treats the admin as approver.
- The Augment runner, in dry-run only, verifies the
  fingerprint against the framework diff, checks accuracy
  at 85 percent or above, and stops when approval is awaiting.
  That check lives in the runner, not in the plugin.

## What production needs, in order

1. The plugin recomputes a fingerprint and compares it to
   the approval fingerprint, before any write.
2. The plugin checks approval status and approved rows,
   not only presence.
3. The plugin enforces all tiers: 95 and above, 80 to 94,
   50 to 79, and below 50.
4. The token is scoped per store, with expiry, revocation,
   and a signed batch.

## The mapping problem, to be locked first

The approval fingerprint is computed over framework rows:
product_id, field, proposed_value, current_value, sorted by
product_id then field, JSON with sorted keys, SHA-256.
The plugin diff is different. It uses product_id, field,
old_value, new_value, source, confidence, and for framework
rows it maps material, fit, and returns to a single plugin
field, additional_property, with values such as
"Material|Full-grain leather".

A direct fingerprint match between the plugin diff and the
approval fingerprint will therefore fail for mapped rows,
even when the publish is correct. Coding that direct check
now would break every mapped publish.

## Proposed verification, for organizer lock

Option A, preferred for audit: the Publish to Plugin stage
sends both the original approved rows and the mapped plugin
diff, with the approval fingerprint. The plugin verifies:
(a) the fingerprint matches the original approved rows,
(b) every mapped plugin change corresponds to exactly one
approved original row, by the locked mapping rule,
(c) no mapped change has no approved original row, and
(d) no approved row is dropped without a listed reason.

Option B: the stage sends only the plugin diff, plus a
stage-signed mapping record that lists, per plugin change,
the original product, field, and value it came from. The
plugin verifies the stage signature, then checks (b) to (d)
against the mapping record, and checks the approval
fingerprint only if the stage also supplies the original
rows. Option B is weaker, because the plugin trusts the
stage signature for the mapping.

No option is coded until the organizer locks one, and locks
the mapping rule for material, fit, and returns.

## Tier enforcement, for organizer lock

Proposed rule, using confidence_percent on each change:
- 95 and above: publish with a group approval record, with
  a recorded rejection window. A merchant rejection in that
  window must revert that change.
- 80 to 94: publish with a tacit approval record, with a
  recorded approval-by-exception window.
- 50 to 79: publish only with an explicit individual
  approval record for that change.
- Below 50: reject, as version 0.2 already does.

Open questions, not assumed:
- What field carries the exception window, and in what format?
- Does a group approval record carry one fingerprint for
  the whole batch, or one per tier group?
- Does the admin path keep any bypass in production, or is
  admin approval treated as an explicit approval record
  with the same checks?
- How long is a token valid, and how is batch signing done?

## Test cases, to be stub-tested once locked

- Fingerprint match, all mapped changes accounted for: pass.
- Fingerprint mismatch: publish nothing, failure logged.
- Approved row dropped without reason: publish nothing.
- Unapproved mapped change added: publish nothing.
- Below 50 percent: reject, even with a token.
- 95 and above, rejection in window: revert that change only.
- Expired token, revoked token, unsigned batch: reject, no write.
- Admin call without approval record, in production mode:
  reject, unless the organizer locks an admin-as-approver rule.

## Status

Design note only. No plugin code change in this note.
Item 7 remains blocked on the organizer lock above, plus
live WordPress testing and a real merchant decision.
