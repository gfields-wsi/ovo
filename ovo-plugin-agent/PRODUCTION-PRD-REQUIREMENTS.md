# Remaining requirements for a production OvO product, Plugin lane only

Revision 2, 2026-10-31, after the WordPress and WooCommerce
limits audit. Revision 1 was 2026-10-30.

Correction, 2026-10-30: Greg clarified that the question was about
production PRD compliance, not about the first demo. The earlier
demo-only adjustment was the wrong direction. This list replaces
that adjustment for production work.

Scope: this list covers the Plugin lane only. Audit, Enrichment,
Accuracy, Merchant Approval, and Coordinating Agent gaps belong
to those streams and to the organizer. They are listed here only
where the plugin must interface with them.

The PRD is the truth. R1 to R9 are P1. R10 is P2. Scope is
WordPress plus WooCommerce, Stripe, and Meta Muse as the
reference agent. Decision 0 stands: OvO is a behind-the-scenes
enabler, not the buyer, and purchase rules live in the store
and in agent tools, not in OvO.

Status today: plugin version 0.2.0-demo, in code only. Lint
passes, 13 stub tests pass, and the Augment runner passes in
dry-run only. Nothing below is live-tested on Sole Mates yet,
and nothing below is claimed as done until its acceptance
criteria pass on the live store.

## Audit revision summary

Audit report: WP-WOO-LIMITS-AUDIT.md, in the same folder,
961 lines, with each finding marked verified from an official
source, verified from plugin code, or unverified.

- Changed by the audit: 10 of 15, items 1, 2, 5, 7, 8, 10, 11,
  13, 14, 15.
- Unchanged by the audit: 5 of 15, items 3, 4, 6, 9, 12.
- New items added by the audit: 4, items 16, 17, 18, 19.
- Total now: 19 items.

Unverified claims in the audit are kept marked as unverified
below, and are not presented as official WordPress or
WooCommerce rules. They are test items or scope decisions.

## Open decision that blocks item 1

The distribution channel must be named before item 1 can pass.
WooCommerce Marketplace, WordPress.org, and a private direct
channel have different, incompatible rules. WooCommerce
Marketplace allows paid extensions with a revenue-share
business model. WordPress.org requires the plugin itself to be
free, with paid features only in the external service. Do not
claim a generic "CMS app store" path. Name one channel, and
meet that channel's rules.

## 1. Real merchant install through a named production channel
[Revised by audit]

Requirement: a merchant installs the plugin through a named
production distribution channel, not a demo-only zip upload.
Acceptance: the channel is named in advance: WooCommerce
Marketplace, WordPress.org, or a private direct channel, and
its rules are met, see item 15. If WooCommerce Marketplace, a
vendor account is approved, QIT API, E2E, Activation, Security,
PHPCompatibility, Malware, and Validation tests pass, and the
business, code, and UX reviews pass, with a formal business
decision expected within 30 days once in business review.
Activation changes no catalog data. GET /ovo/v1/manifest
returns 200, not 404. No PHP errors are logged on activation.

## 2. WordPress and WooCommerce integration tests, plus QIT
[Revised by audit]

Requirement: tests run against real WordPress and WooCommerce,
not stub functions only, and, where the channel is WooCommerce
Marketplace, QIT tests also pass.
Acceptance: automated tests pass on real WordPress and
WooCommerce, on the two latest major releases of each at
submission time, for publish, read, checkout guards, revert,
demo reset, blocked fields, stale diffs, variation guards,
pagination beyond 100 enriched products, and cache invalidation
after publish and revert. Where distribution is WooCommerce
Marketplace, QIT API, E2E, Activation, Security,
PHPCompatibility, Malware, and Validation tests also pass.
Stub tests alone do not pass this requirement.

## 3. Full PRD autonomy tier enforcement in the plugin
[Unchanged by audit]

Requirement: the plugin enforces all PRD tiers, not only the
below 50 percent rejection in version 0.2.
Acceptance: 95 percent and above acts alone, with merchant
rejection by exception in a recorded window. 80 to 94 percent
is a tacit suggestion, with merchant approval by exception.
50 to 79 percent requires explicit merchant approval before
publish. Below 50 percent is rejected and iterated. Every
publish records tier, approver, timestamp, and exception window.
No publish happens outside its tier.
Note from audit, not a wording change: if tier features are
tied to a paid OvO account, WordPress.org distribution requires
the paid part to live in the external service, not as locked
plugin code.

## 4. Approval verification inside the plugin
[Unchanged by audit, with a tenant note from Merchant Approval]

Requirement: the plugin verifies approval itself, not only
that approval fields are present.
Acceptance: the plugin recomputes the diff fingerprint from
the exact diff rows, checks it against the approval record,
checks approval status and approved rows, and stops on any
mismatch. A failed check publishes nothing and writes a
failure status. The Augment runner does this check in
dry-run today. The plugin does not yet do it live.
Tenant note: live approval inputs supply a store URL and no
merchant ID, so the live packet is store only, with no merchant
ID. The session check is structural only, with no cryptographic
signature verified, because no platform issuer or key is
supplied yet. Until live inputs supply merchant ID and store ID,
the plugin can verify store identity only by the fact that it
runs on that store and the product exists there. Do not claim
tenant verification from the approval record until that gap
is closed.

## 5. Scoped, revocable, expiring agent token, with a signed batch,
implemented in the plugin, not by borrowing a broader credential
[Revised by audit]

Requirement: agent access is scoped to one store, revocable,
expiring, and batch-signed, through a plugin-owned token.
Acceptance: one token per store tenant, with expiry, revocation,
and rotation. A batch is signed and the signature is verified.
A token alone never publishes. The admin path does not bypass
tier rules. Only a token hash is stored, never the token itself.
WordPress Application Passwords and WooCommerce REST keys are
NOT accepted as the production agent token, because both inherit
the full permissions of their WordPress user, offer only Read,
Write, or Read-Write scope with no per-field scope, and have no
built-in expiry in core. A WooCommerce Read-Write key could
write price and stock, which item 7 forbids. The custom token
endpoint has rate limiting and failed-attempt logging, because
WordPress core provides no rate limiting for custom REST routes.
Rate limit numbers from third-party summaries are unverified
and are not used here.

## 6. Canonical diff format and field mapping, locked by the organizer
[Unchanged by audit]

Requirement: one canonical diff set, with one documented
field mapping, is used for every publish.
Acceptance: the organizer locks the canonical set, resolving
the 36 row framework set against the 62 row stream set. Every
framework field maps to a plugin field, or is rejected. No
unmapped field publishes. The mapping is tested, and a new
diff requires a new approval record.

## 7. Safe-field publish, with originals and revert for every change,
through WooCommerce CRUD objects
[Revised by audit]

Requirement: only approved safe fields publish, with
originals kept and revert for every change, through
WooCommerce CRUD objects with save(), not direct postmeta
writes alone.
Acceptance: price, stock, SKU, GTIN, tax, shipping, weight,
dimensions, and policy claims are never written from modelled
data, and are blocked live. Only approved safe fields publish.
Writes use WooCommerce CRUD objects with save(), and
lookup-table and filter staleness is tested after publish and
revert. Global attributes, pa_* taxonomies, are never shadowed
by a custom attribute of the same name; a proposed attribute
that matches a global attribute is rejected or mapped to that
taxonomy's terms, as locked by the organizer. Variation
attributes are never written. Variable parent, variation child,
grouped, and external product types each have a defined,
tested enrichment target, or are rejected with a reason.
Gallery image handling is defined or explicitly out of scope.
Originals are kept on first write only. Revert of one field
restores its original. Full revert restores all fields.
Uninstall restores originals, instead of today's rule where
the merchant must revert first. Term creation for categories
and tags does not leave orphan terms after revert, or orphan
terms are documented as accepted.
Note: the lookup-table regeneration step and the global versus
custom attribute taxonomy behaviour are unverified as official
rules in the audit, from third-party guidance only. They are
live test items here, not cited as official rules.

## 8. Server-side surfaces verified live, with checkout clean,
on both permalink forms and with cache invalidation
[Revised by audit]

Requirement: publish is verified on server output, not on
browser display only, and checkout is untouched, on both
checkout forms and both permalink forms.
Acceptance: product page raw HTML contains the separate
ovo-enrichment JSON-LD block, with no change to the
WooCommerce offers block. GET /ovo/v1/products/{id} returns
the same fields. Price and stock are absent from the OvO
block. Cart, checkout, and account pages contain no OvO block,
on both shortcode checkout and block checkout, because block
Cart and Checkout are the default experience. Checkout totals
are unchanged and are recalculated by WooCommerce alone.
After publish and after revert, the product page and the OvO
read surface show the new state without a manual cache purge
by the merchant, see item 18. The read surface is tested on
Plain permalinks via ?rest_route= and on pretty permalinks
via /wp-json/, because rest_url() must generate the correct
form for each store. A WooCommerce REST API write-back path,
if ever used, would not work on a Plain-permalink store,
because that API requires a non-Plain permalink setting.

## 9. Coordinator wiring, with Merchant Approval and Publish to Plugin live
[Unchanged by audit]

Requirement: the production flow is Audit, Enrichment,
Merchant Approval, Publish to Plugin, with each stage run
through its relevant agent, not done by the coordinator itself.
The plugin's Publish to Plugin stage calls the plugin only
with an approved batch.
Acceptance: the coordinator pauses at Merchant Approval,
published false, as tested live in the coordinator stream
on 2026-10-30. Publish to Plugin then calls the plugin only
with an approved batch. A failed approval or fingerprint
check stops the run, publishes nothing, and does not proceed
as a success. The published flag is true only after approval
and publish. Publish to Plugin is still blocked in this lane
because the plugin runner refuses live post, token auth is
untested on WordPress, the plugin is not installed on a real
store, and no real merchant decision has been given.
Note from audit: if Publish to Plugin were re-routed through
WooCommerce REST API write-back, the Plain-permalink limit
and the broader Read-Write key limit in item 5 would apply.
Neither changes this acceptance test.

## 10. Cloud tenant staging, separate from the live store,
with distribution-channel disclosure
[Revised by audit]

Requirement: OvO stores merchant-specific enrichment in a
cloud tenant, as draft, then as an approved batch, and the
plugin publishes only the approved batch, with the external
service disclosed.
Acceptance: staging is never the shop. The plugin holds only
the on-store record: applied state, originals, and audit log.
No modelled value publishes as a native store field. Modelled
values publish only as JSON-LD additional_property, if at all.
The readme discloses the OvO external service, what data is
sent, when, and why, with links to OvO terms of use and
privacy policy, and external contact requires explicit
merchant opt-in. If distribution is WordPress.org, no plugin
code is locked behind payment, and the plugin is not presented
as a storefront front-end for external purchases.

## 11. Production audit log, PRD R10, P2
[Revised: tenant fields added from the Merchant Approval note]

Requirement: the audit log reconstructs any publish, revert,
or reset, with its source fields, including tenant fields
when supplied.
Acceptance: every entry records old value, new value, source
label, approver, fingerprint, and timestamp, plus merchant ID
and store ID when supplied by the approval record. The log is
exportable and retained for production use, not only capped
at 500 entries in an option with the last 50 shown in admin.
A reconstruction test passes for a sample publish. Until live
approval inputs supply merchant ID, tenant reconstruction from
the log cannot be claimed for live stores.

## 12. Hostile text handling in the publish path, PRD R9
[Unchanged by audit]

Requirement: untrusted storefront or agent text changes no
plugin rule.
Acceptance: a red-team set of hostile texts is run against
the publish path. No hostile text is followed, no hostile
text is removed by the plugin, no rule changes, and each
case is flagged in the audit log.

## 13. Agent-facing interface, PRD R6, stable and versioned,
with a defined cache policy
[Revised by audit]

Requirement: the agent-facing read surface is stable,
versioned, documented, and has a defined cache policy.
Acceptance: GET /ovo/v1/manifest, /ovo/v1/products, and
/ovo/v1/products/{id} return approved enrichment fields only,
with a price and stock note, and no price or stock values.
The surface is versioned, and a breaking change requires a
new version, v2, alongside v1, not a silent change to v1.
Public GET responses state their cache policy, and cache
invalidation after publish and revert is tested, see item 18.

## 14. Payment pass-through proof, Decision 0, PRD R7 and R8,
with WooCommerce as the sole total calculator
[Revised by audit, direction unchanged]

Requirement: the plugin never touches payment, purchase
rules, or checkout totals.
Acceptance: the plugin has no payment route, no quote route,
and no checkout-total change. A test order completes through
the merchant's own Stripe checkout, and the order appears in
the merchant's existing system with correct data. Plugin
evidence for this requirement is checkout clean and totals
unchanged, not plugin ownership of payment. The checkout-clean
test is run on both shortcode checkout and block checkout,
because block Cart and Checkout are the default experience.
Note: the Payment Bridge plan in plan.md is research only and
is superseded by Decision 0 for this stream. It is not a
production requirement in this list.
Research note, 2026-10-30, confirmed by Greg: for an agent-only
full transaction on a WordPress and WooCommerce store, the
research showed no other way. The Payment Bridge was the only
scenario identified that unlocks an agent-only full transaction
on Sole Mates. Browser checkout and human handoff remain
pass-through routes, but they are not agent-only pay
transactions, and they do not change this note.

## 15. Production distribution, support, and monitoring
[Revised by audit]

Requirement: the plugin ships as a production product, not
as a demo zip, through the named channel in item 1.
Acceptance: versioning and migration are documented and
tested. PHP and WooCommerce compatibility is tested across
the two latest major releases of WordPress and WooCommerce
at submission time, re-checked at submission, not a fixed
pair written now. The plugin header declares Requires Plugins:
woocommerce, WC requires at least, and WC tested up to for
the releases tested. PHP 7.4 is the stated minimum floor, not
the recommended floor; PHP 8.3 or above is strongly
recommended. The plugin declares HPOS compatibility with
FeaturesUtil::declare_compatibility('custom_order_tables',
__FILE__, true) only after HPOS testing passes, and it never
reads or writes order data except through WooCommerce CRUD
APIs if it ever must, see item 16. Errors are logged in
production form. Demo mode and demo reset are off by default
in production, and do not touch orders, carts, or shopper
sessions when used. The product is updated at least every
6 months, or WooCommerce Marketplace flags the product for
removal. If distribution is WordPress.org, the submission zip
is under 10 MB, production-ready, without test folders or
unused files; the current 14 KB zip passes size, and the
stub test exclusion must stay in production packaging.

## 16. HPOS declaration and order-data non-interference
[New, from audit, official source verified]

Requirement: the plugin declares HPOS compatibility only
after testing, and never touches order data except through
WooCommerce CRUD APIs.
Acceptance: the HPOS declaration in item 15 is present in the
main plugin file, HPOS on and HPOS off are both tested, the
plugin appears as HPOS-compatible, not uncertain, in
WooCommerce settings, and no code path reads or writes order
postmeta directly. Demo reset and revert are tested with
HPOS on, and orders, carts, and shopper sessions are untouched.
Note: HPOS moves orders, not products, to custom tables, so
it does not directly break the plugin's product postmeta
writes. The blocker is Marketplace standing and any future
order code, not product data breakage. Custom product tables
in WooCommerce 10.0 or above are unverified in the audit,
from third-party claims only, and are a watch item only:
re-check the official tables doc at each major release, and
prefer CRUD product objects, see item 7.

## 17. Multisite scope decision
[New, from audit, official rule unverified]

Requirement: the production scope for multisite is stated
and tested, or multisite is explicitly out of scope.
Acceptance: either (a) multisite is supported, with per-site
token, audit log, and demo-mode state, network activation
handled per site, and a test on a two-site network; or (b)
the readme and install path state single-site only, and
network activation is refused or documented as unsupported,
with a test that it does not silently share one site's token
or audit log with another site. The current code is per-site
by construction, using get_option() and a per-site admin menu.
Note: the multisite mechanism in the audit is from
third-party summaries only, with no official multisite page
fetched. The scope decision itself is required regardless.

## 18. Cache invalidation after publish and revert
[New, from audit, design and test requirement, not an official rule]

Requirement: after publish and after revert, the product page,
the OvO JSON-LD block, and the OvO read surface show the new
state without merchant manual cache purging.
Acceptance: publish and revert are tested with WooCommerce
product transients cleared, which the code already does, plus
a full-page cache plugin active, plus a CDN or object cache
if the test store uses one. The test records which caches are
purged by the plugin and which, if any, require host action,
and the readme states that record.

## 19. Pagination and batch limits for large catalogs
[New, from audit, code cap verified]

Requirement: the read surface and demo reset work beyond
100 enriched products, and diff batches respect a stated limit.
Acceptance: GET /ovo/v1/products returns all enriched products
on a test store with more than 100 enriched products, via
pagination or a stated page size, not a silent 100 cap. Demo
reset reverts all enriched products on the same test store.
Diff batches state a maximum change count, and a batch above
that count is rejected or split with a stated rule, not
silently truncated. The current code cap is verified in code:
get_posts(posts_per_page=100) in both routes. A WooCommerce
REST batch limit of 100 objects is unverified in the audit,
from third-party summaries only, and is not used as the basis
for this requirement.

## Sources used in the audit

Official, fetched and quoted in the audit report:
- WooCommerce Marketplace submission page
- WooCommerce HPOS recipe book
- WooCommerce product update guidelines
- WordPress.org detailed plugin guidelines, last updated
  March 15, 2024
- WordPress.org plugin developer FAQ
- WordPress REST API routes and endpoints page
- WooCommerce REST API document
- WooCommerce database tables document
- WordPress.org support topic on fees and taxes calculation

Unverified in the audit, do not cite as verified:
custom product tables, global versus custom attribute
taxonomy behaviour, lookup-table regeneration, multisite
behaviour, Store API rate-limit numbers, WooCommerce REST
batch limit, Application Password edge cases, duplicate
Product JSON-LD SEO risk, and current latest version numbers.
