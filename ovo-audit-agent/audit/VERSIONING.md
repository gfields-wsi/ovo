# Audit Agent versioning, Audit side

Formats are frozen at version 1.0, unless a new version is
released with a new version number.

- gaps.json: ovo-gap-list 1.0. The gap list schema is frozen.
  New top level fields may be added, but no gap field may be
  removed or renamed in version 1.0.
- scorecard.json: ovo-audit-scorecard 1.0.
- trace.json: ovo-audit-trace 1.0.
- merchant_guidance.json: ovo-merchant-guidance 1.0.
- audit_error.json: ovo-audit-error 1.0, written only on failure.

Rule: a change that removes a field, renames a field, or changes
the meaning of a score needs a new major version, and that change
is not made unilaterally. A change that adds a new top level
field, with all old fields unchanged, stays in version 1.0.

Each run writes its own generated_at_utc, store_url, and store_key,
so a file from a previous run cannot be mistaken for a new run
without checking its timestamp and store key.
