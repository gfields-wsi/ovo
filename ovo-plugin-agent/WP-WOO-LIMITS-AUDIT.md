# WordPress and WooCommerce plugin limits audit
## Revision input for PRODUCTION-PRD-REQUIREMENTS.md — do not edit that list from here

Date: 2026-10-31 (audit run, following the 2026-10-30 production list)
Scope: OvO Enrichment plugin, version 0.2.0-demo, Plugin lane only.
What was read: PRODUCTION-PRD-REQUIREMENTS.md (15 items) and
ovo-enrichment/ovo-enrichment.php (v0.2).
What was NOT done: no live Sole Mates store was touched, no plugin
code was changed, and PRODUCTION-PRD-REQUIREMENTS.md was not edited.
The parent agent revises that list after reviewing this report.

How to read the verdicts in this report:
- VERIFIED (official source): the claim was read on an official
  WordPress or WooCommerce page fetched during this audit, and the
  URL below is that page, copied verbatim from the search or open
  result that returned it.
- VERIFIED (code): the claim was read in the plugin code itself.
- UNVERIFIED: no official source was fetched that states the claim.
  It is a best practice, a third-party claim, or a risk to test, not
  a hard platform rule. Do not build a requirement on it alone.
- NO CHANGE: the platform limit does not change the requirement,
  even if it adds an implementation note.

Summary counts, for the parent summary:
- Requirements changed by this audit: 10 of 15
  (1, 2, 5, 7, 8, 10, 11, 13, 14, 15)
- Requirements unchanged: 5 of 15 (3, 4, 6, 9, 12)
- New requirements proposed: 4 (16, 17, 18, 19, below)

---

## 1. HPOS: orders move, products do not — but declaration is still mandatory for Marketplace

### 1A. What HPOS actually changes
Limitation: High-Performance Order Storage moves order data from
the WordPress post and postmeta tables to dedicated order tables.
It does not, on the official pages fetched, move product data.
Products remain post-type `product` records with postmeta, plus
WooCommerce lookup tables.

Official source, VERIFIED:
https://developer.woocommerce.com/docs/features/orders/high-performance-order-storage/recipe-book/
What it actually says: "instead of using WordPress-provided APIs
to access order data, developers will need to use WooCommerce-
specific APIs" because "the underlying data structure has changed
fundamentally" for orders; direct reads of WordPress tables "may
mean reading an outdated order, and directly writing to these
tables may mean updating an order that will not be read"; for
metadata, use the order object's update/add/delete methods
"followed by a save call", and WooCommerce "will take care of
figuring out which tables are active".

Official source, VERIFIED, for the tables themselves:
https://woocommerce.com/document/tables-de-base-de-donnees-installees/
What it actually says (in the fetched French rendering, table
names are language-independent): order tables are wc_orders,
wc_order_addresses, wc_order_operational_data, wc_orders_meta;
product lookup tables are wc_product_meta_lookup and
wc_product_attributes_lookup. No wp_wc_products table is listed
on that official page.

Effect on the plugin, VERIFIED (code): the plugin never reads
or writes order postmeta. It reads and writes product postmeta
(_ovo_originals, _ovo_enriched, _wp_attachment_image_alt,
_product_attributes) and product post fields (post_excerpt,
post_content) via wp_update_post, and it queries products with
get_posts(post_type=product). HPOS therefore does NOT directly
break the plugin's product writes. The earlier shorthand "HPOS
breaks the plugin" would be wrong. What HPOS does break, if it
is ignored, is the plugin's Marketplace standing (see 1B) and
any future code that touches orders — which this plugin must
not do, per Decision 0 and requirement 14.

### 1B. HPOS declaration is mandatory for new Marketplace submissions
Limitation: all new WooCommerce Marketplace extension submissions
must be HPOS-compatible, and the plugin must declare it, even if
it does not touch orders. Without a declaration WooCommerce flags
the plugin as uncertain/incompatible.

Official source, VERIFIED:
https://developer.woocommerce.com/docs/woo-marketplace/submitting-your-product/
What it actually says: "High-Performance Order Storage (HPOS) is
the default experience for new WooCommerce stores. It moves order
data from the WordPress post and postmeta tables to dedicated
order tables" and "All new extension submissions must be
HPOS-compatible. View our HPOS recipe book".

Official source, VERIFIED, for the declaration mechanism:
https://developer.woocommerce.com/docs/features/orders/high-performance-order-storage/recipe-book/
What it actually says: place in the main plugin file,
on before_woocommerce_init, a FeaturesUtil::declare_compatibility(
'custom_order_tables', __FILE__, true ) call if compatible, or
false if not; "WooCommerce will warn users if they try to enable
HPOS while any of the incompatible plugins are active" and will
"display a warning in the Plugins screen"; WooCommerce "will
only display this information for extensions that declare
`WC tested up to` in the header".

Effect on the plugin, VERIFIED (code): the plugin has NO HPOS
declaration, NO "WC requires at least", NO "WC tested up to",
and NO "Requires Plugins: woocommerce" header. Its header is
only: Requires at least 6.0, Requires PHP 7.4. That is a
Marketplace blocker, not a product-data blocker.

Affects: requirement 15 (CHANGE) and new requirement 16.
Exact revised wording for requirement 15, proposed:
"Requirement 15 (revised): Production distribution, support, and
monitoring. Acceptance: versioning and migration are documented
and tested. PHP and WooCommerce compatibility is tested across a
stated matrix, and the plugin header declares Requires Plugins:
woocommerce, WC requires at least, and WC tested up to for the
two latest major releases tested. The plugin declares HPOS
compatibility with FeaturesUtil::declare_compatibility(
'custom_order_tables', __FILE__, true ) only after HPOS testing
passes, and it never reads or writes order data except through
WooCommerce CRUD APIs if it ever must. Errors are logged in
production form. Demo mode and demo reset are off by default in
production, and do not touch orders, carts, or shopper sessions
when used. Products are updated at least every 6 months, or the
Marketplace flags the product for removal."

### 1C. Custom product tables in WooCommerce 10.0+ — UNVERIFIED
Claim seen in third-party sources only: WooCommerce 10.0+
introduces optional custom product tables (wp_wc_products) that
will eventually replace wp_posts/wp_postmeta for products.
No official WooCommerce page fetched in this audit states that
table or that timeline. The official tables page fetched above
lists product lookup tables, not a wp_wc_products product store.
Do NOT add a "migrate to custom product tables" requirement on
that claim alone. Do add a watch item: re-check the official
tables doc at each major WooCommerce release, and prefer the
WooCommerce CRUD product object over direct postmeta writes so
a future product-store change is less likely to break the plugin
(see finding 5).

Affects: requirement 7 (implementation note only, no wording
change from this sub-finding alone).

---

## 2. Supported versions, QIT, review timing, and update cadence (Marketplace)

### 2A. Two latest major releases
Limitation: Marketplace products must support the two latest
major releases of both WooCommerce and WordPress.

Official source, VERIFIED:
https://developer.woocommerce.com/docs/woo-marketplace/submitting-your-product/
What it actually says, in the pre-submission checklist:
"Products must support the two latest major releases of both
WooCommerce and WordPress" and "Products must support PHP 7.4+
as a minimum (PHP 8.3+ strongly recommended)" and "PHP 7.4
reached End of Life in November 2022. Using it may expose sites
to security vulnerabilities."

Effect: requirement 15's "stated matrix" is too vague for
production. The matrix must be the two latest majors at
submission time, re-checked at submission, not a fixed pair
written now. The plugin's current "Requires PHP: 7.4" meets the
stated minimum but is the EOL floor, not the recommended floor.
Do not state current latest version numbers in the requirement
from this audit: no official page fetched here states a single
"current latest" pair that will still be true at submission.

Affects: requirement 15 (CHANGE, wording in 1B above) and
requirement 2 (CHANGE, wording in 2C below).

### 2B. Review process, QIT tests, and 30-day business decision
Limitation: Marketplace review is not a listing guarantee. It
is vendor-account approval first, then business review, code
review, UX review, and launch preparation, with automated
Quality Insights Toolkit (QIT) tests, and a formal business
decision within 30 days once in business review.

Official source, VERIFIED:
https://developer.woocommerce.com/docs/woo-marketplace/submitting-your-product/
What it actually says: "Before getting started, make sure you
have applied for a Marketplace vendor account and your
application has been approved"; a review consists of business
review ("good fit for the Marketplace, and that there is a
business model to share revenue"), code review ("original,
secure, and aligned with overall WordPress and WooCommerce
quality standards"), UX review, and launch preparations; products
"must be able to pass" QIT tests: API, End-to-end (E2E),
Activation, Security, PHPCompatibility, Malware, Validation;
"Once the submission is in business review, you can expect a
formal decision from a reviewer within 30 days."

Official source, VERIFIED, for the same 30-day figure in the
developer blog version:
https://developer.woocommerce.com/2025/03/20/getting-to-know-the-woo-marketplace-a-developers-look/
What it actually says: "Your product must be compatible with
the latest two versions of WordPress and WooCommerce", "Ensure
your product can pass our battery of Quality Insights Toolkit
(QIT) tests", and "This process typically takes up to 30 days."

Official source, VERIFIED, for update cadence:
https://developer.woocommerce.com/docs/woo-marketplace/product-update-guidelines/
What it actually says (from the search result for that page):
"Update your product at minimum every 6 months" and "Products
that fail to stay current with WooCommerce core and/or those
that are not updated at least once every six months will be
flagged for removal from the WooCommerce Marketplace."

Effect: requirement 1's "CMS app store path, or a documented
production install path" cannot pass as written for Woo
Marketplace distribution, because it does not name the vendor
account, revenue-share business review, QIT pass, or 30-day
window. If distribution is NOT Woo Marketplace, this finding
does not apply — which is why the distribution decision itself
must be made first (see finding 3).

Affects: requirement 1 (CHANGE) and requirement 2 (CHANGE).
Exact revised wording for requirement 1, proposed:
"Requirement 1 (revised): Real merchant install through a named
production distribution channel. Acceptance: the distribution
channel is named in advance — WooCommerce Marketplace, WordPress
.org, or a private direct channel — and its rules are met (see
requirement 15). If WooCommerce Marketplace, a vendor account is
approved, QIT API, E2E, Activation, Security, PHPCompatibility,
Malware, and Validation tests pass, and the business, code, and
UX reviews pass, with a formal business decision expected within
30 days once in business review. Activation changes no catalog
data. GET /ovo/v1/manifest returns 200, not 404. No PHP errors
are logged on activation."

### 2C. Integration tests must include QIT, not only WP/Woo tests
Exact revised wording for requirement 2, proposed:
"Requirement 2 (revised): WordPress and WooCommerce integration
tests, plus Marketplace QIT tests where the channel is Woo
Marketplace. Acceptance: automated tests pass on real WordPress
and WooCommerce, on the two latest major releases of each, for
publish, read, checkout guards, revert, demo reset, blocked
fields, stale diffs, variation guards, pagination beyond 100
enriched products, and cache invalidation after publish and
revert. Where distribution is WooCommerce Marketplace, QIT API,
E2E, Activation, Security, PHPCompatibility, Malware, and
Validation tests also pass. Stub tests alone do not pass this
requirement."

---

## 3. Distribution channel choice: Woo Marketplace vs WordPress.org vs private

### 3A. WordPress.org serviceware rule — the sharpest distribution limit
Limitation: WordPress.org allows serviceware plugins (plugins
that act as an interface to an external service) only if the
service does substantial work and is clearly documented in the
readme, preferably with a link to the service's Terms of Use.
A service that exists only to validate licenses or keys while
the plugin does all the work is NOT permitted. A plugin that
acts only as a front-end for products to be purchased from
external systems — a storefront, not a service — will NOT be
accepted.

Official source, VERIFIED:
https://developer.wordpress.org/plugins/wordpress-org/detailed-plugin-guidelines/
Last updated on the page: March 15, 2024.
What it actually says: "Plugins that act as an interface to
some external third party service (e.g. a video hosting site)
are allowed, even for paid services. The service itself must
provide functionality of substance and be clearly documented
in the readme file submitted with the plugin, preferably with
a link to the service's Terms of Use." Services NOT allowed
include: "A service that exists for the sole purpose of
validating licenses or keys while all functional aspects of
the plugin are included locally" and "Storefronts that are not
services. A plugin that acts only as a front-end for products
to be purchased from external systems will not be accepted."
Also: "plugins may not contact external servers without explicit
and authorized consent" via opt-in, with readme documentation
of data collection and use, preferably with a privacy policy;
"All 'Powered By' or credit displays and links included in the
plugin code must be optional and default to not show"; "Plugins
may not contain functionality that is restricted or locked,
only to be made available by payment or upgrade" and "Paid
functionality in services is permitted (see guideline 6:
serviceware), provided all the code inside a plugin is fully
available"; "Obscuring code" is not permitted; all code must be
GPL-compatible, with "GPLv2 or later" strongly recommended.

Effect on OvO, VERIFIED (code + PRD): the plugin currently
contains NO remote fetch, NO model call, and NO OvO cloud call
(grep in the prior stream: no muse/spark/meta-api/wp_remote/
curl calls, only a no-Muse-discovery note). Enrichment
generation happens outside the plugin, in the OvO cloud tenant
(requirement 10). That is, on its face, a substantial external
service — Audit, Enrichment, Accuracy, Merchant Approval — not
a key-validation stub. So a WordPress.org serviceware argument
is arguable, NOT proven. It would still require: a readme that
discloses the OvO service, what data is sent, when, and why,
with links to OvO terms and privacy policy; explicit opt-in
consent before any external contact; no locked plugin code
behind payment (paid OvO features must live in the external
service, not as locked code in the plugin); and no storefront
framing, because the plugin must not be presented as a front-end
for buying from OvO's systems. Decision 0 helps here: OvO is
not a shop, and the plugin publishes on the merchant's own
store — but that argument must be made in the readme and
submission, it is not automatic.

Effect on requirement 1: "CMS app store" is not a channel.
WooCommerce Marketplace, WordPress.org, and a private direct
channel have different rules, different fees/revenue share,
and different free-vs-paid rules. WooCommerce Marketplace
allows paid extensions with a revenue-share business model;
WordPress.org requires the plugin itself to be free, with paid
features only in the external service. The production list
must not claim "install from the CMS app store" until the
channel is named, because the acceptance test is different
for each channel.

Affects: requirement 1 (CHANGE, wording in 2B) and requirement
10 (CHANGE, wording in 3B below).

### 3B. Cloud tenant disclosure
Exact revised wording for requirement 10, proposed:
"Requirement 10 (revised): Cloud tenant staging, separate from
the live store, with distribution-channel disclosure. Acceptance:
staging is never the shop. The plugin holds only the on-store
record: applied state, originals, and audit log. No modelled
value publishes as a native store field. Modelled values publish
only as JSON-LD additional_property, if at all. The readme
discloses the OvO external service, what data is sent, when,
and why, with links to OvO terms of use and privacy policy,
and external contact requires explicit merchant opt-in. If
distribution is WordPress.org, no plugin code is locked behind
payment, and the plugin is not presented as a storefront
front-end for external purchases."

### 3C. WordPress.org submission mechanics (not a blocker, a checklist)
VERIFIED from the Plugin Developer FAQ search result and the
detailed guidelines page above:
https://developer.wordpress.org/plugins/wordpress-org/plugin-developer-faq/
What it actually says: a submission zip must be under 10 MB,
in common WordPress plugin format, production-ready, complete,
without errors, without unnecessary logs, without development
tools, and without unused files such as test folders. The
current OvO zip is 14 KB, so size passes trivially, but the
zip currently excludes tests-stub.php for that reason — that
exclusion must stay in production packaging, and the readme
must validate.

Affects: requirement 15 (implementation note only, no separate
wording change beyond 1B).

---

## 4. REST authentication: what WordPress and WooCommerce actually offer

### 4A. WordPress core options
Limitation: WordPress core offers, for REST API writes:
(a) cookie authentication with a nonce, for code running inside
WordPress/wp-admin; (b) Application Passwords, since WordPress
5.6, via HTTP Basic Auth over HTTPS; (c) authentication plugins
(OAuth, JWT) via third-party plugins. There is no core scoped,
per-field, per-tenant token, and no core token expiry.

Official source, VERIFIED, via the REST API Handbook search
result (the handbook page itself was returned via a mirror in
search; the substance below is also stated in multiple
independent sources, so it is marked VERIFIED with that caveat):
the handbook's Authentication page states cookie authentication
is the standard method for logged-in users, with a nonce
(X-WP-Nonce, action wp_rest) to avoid CSRF, and that "Application
Passwords" shipped in 5.6, generated from an Edit User page,
"can be passed along to REST API requests served over https://
using Basic Auth". A separate third-party summary of the same
handbook states the same, and adds that Application Passwords
"cannot be used to log into wp-admin" and "carry the same
permissions as the [user]".

Key limits for OvO, all following from the above:
- Cookie + nonce only works inside a logged-in browser session.
  It does not work for a server-to-server Publish to Plugin call.
- An Application Password is tied to one WordPress user, is
  individually revocable, is shown only once, and requires HTTPS.
  It is NOT scoped: it carries that user's full REST permissions.
  A user who can manage_options (required by the plugin's
  permission_callback) is an administrator, so an Application
  Password for that user would grant full admin REST access,
  not OvO-diff-only access. It has no built-in expiry in core
  (no expiry claim was found on any official page fetched;
  rotation is manual revoke-and-regenerate).
- If that user is deleted, or if a security plugin disables
  Application Passwords, or if the site is not on HTTPS, the
  method stops working. These are UNVERIFIED as official-page
  claims in this audit (they come from third-party summaries),
  so they are listed as test items, not as hard rules.

### 4B. WooCommerce REST API keys
Limitation: WooCommerce REST keys are consumer key (ck_) and
consumer secret (cs_) pairs, created at WooCommerce > Settings >
Advanced > REST API, linked to one WordPress user, with
permissions Read, Write, or Read/Write only. The secret is shown
only once. There is no per-field scope, and no built-in expiry
was found on the official page fetched.

Official source, VERIFIED:
https://woocommerce.com/document/woocommerce-rest-api/
What it actually says: "Go to Settings > Permalinks in your
WordPress dashboard and select any option other than Plain";
"The WooCommerce REST API uses a key system to control access.
Each set of keys is linked to a WordPress user"; permissions are
"Read — allows the application to retrieve data", "Write —
allows the application to create and update data", "Read/Write
— allows the application both"; "The Consumer Secret is shown
only once"; "The legacy REST API has been removed from
WooCommerce core" (so write-back must use wc/v3, not legacy
v1/v2).

Effect: a WooCommerce Read/Write key used for Publish to Plugin
would be broader than an OvO diff — it could create or update
any WooCommerce data that user can touch, including price and
stock, which requirement 7 forbids. It also would NOT work on
Sole Mates as-is, because Sole Mates uses Plain permalinks and
the Woo REST API requires a non-Plain permalink setting, while
the plugin's own ovo/v1 routes work via ?rest_route= on Plain
permalinks (see finding 7). The current plugin's custom
X-Ovo-Token header, checked in permission_callback, is therefore
actually MORE scoped than either core alternative — provided
the plugin itself verifies approval, tier, and fingerprint,
which it does not yet do (requirements 3 and 4). The custom
token is not a WordPress core authentication method, so it
needs its own rate limiting, expiry, and audit of failed
attempts, because WordPress core provides no rate limiting for
custom REST routes (see finding 4C).

Affects: requirement 5 (CHANGE).
Exact revised wording for requirement 5, proposed:
"Requirement 5 (revised): Scoped, revocable, expiring agent
token, with a signed batch, implemented in the plugin, not by
borrowing a broader core credential. Acceptance: one token per
store tenant, with expiry, revocation, and rotation. A batch is
signed and the signature is verified. A token alone never
publishes. The admin path does not bypass tier rules. Only a
token hash is stored, never the token itself. WordPress
Application Passwords and WooCommerce REST keys are NOT accepted
as the production agent token, because both inherit the full
permissions of their WordPress user, offer only Read/Write/
Read-Write scope with no per-field scope, and have no built-in
expiry in core. The custom token endpoint has rate limiting and
failed-attempt logging, because WordPress core provides no rate
limiting for custom REST routes."

### 4C. Rate limiting does not cover custom routes
Limitation: WooCommerce Store API rate limiting, where enabled,
covers Store API cart/checkout requests. It does not cover a
plugin's own ovo/v1 routes.

Source: third-party summaries of WooCommerce Store API rate
limiting (25 requests per 10 seconds when enabled, checkout
POSTs at 3 per 60 seconds in some summaries) — UNVERIFIED as an
official-page claim in this audit, because no official
developer.woocommerce.com page on Store API rate limiting was
fetched. The safe, verified statement is narrower: nothing in
the official REST or Marketplace pages fetched states that
custom plugin routes inherit Store API rate limiting. Do not
claim Store API rate limiting protects /ovo/v1/diff.

Affects: requirement 5 (CHANGE, wording in 4B) and requirement
13 (implementation note only).

---

## 5. Product, variation, attribute, and taxonomy limits (safe-field write-back)

### 5A. Global vs custom attributes — the collision the current code misses
Limitation: WooCommerce has two attribute kinds. Global
attributes are defined in Products > Attributes, are reusable
across products, and function as taxonomies (pa_*), allowing
filtering on shop pages. Custom attributes are created per
product, are stored as product meta, and cannot be used for
filtering. The plugin's attribute write creates only a custom
attribute (is_taxonomy 0, is_variation 0, stored in
_product_attributes postmeta).

Source: third-party best-practice summaries only — UNVERIFIED
as an official-page claim in this audit, because no official
developer.woocommerce.com attributes page was fetched. The
distinction itself is consistent with the plugin code and with
WooCommerce's taxonomy design, but the parent should not cite
it as an official rule until an official attributes page is
fetched.

Effect, VERIFIED (code): the plugin's variation guard checks
only get_variation() on the parent product's attributes. It
does NOT check is_taxonomy(). A proposed attribute named, for
example, "Color" could therefore create a custom "Color"
attribute alongside an existing global pa_color taxonomy, with
no terms created, no filtering, and a duplicate display name.
It also does NOT check variation child products
(post_type product_variation): enrichment written to a variable
parent does not propagate to its variations, and variation-
specific values have no defined target. Grouped and external
product types have no defined enrichment target either, and
the plugin does not distinguish them.

Affects: requirement 7 (CHANGE).
Exact revised wording for requirement 7, proposed:
"Requirement 7 (revised): Safe-field publish, with originals
and revert for every change, through WooCommerce CRUD objects.
Acceptance: price, stock, SKU, GTIN, tax, shipping, weight,
dimensions, and policy claims are never written from modelled
data, and are blocked live. Only approved safe fields publish.
Writes use WooCommerce CRUD objects with save(), not direct
postmeta writes alone, and lookup-table/filter staleness is
tested after publish and revert. Global attributes (pa_*
taxonomies) are never shadowed by a custom attribute of the
same name; a proposed attribute that matches a global attribute
is rejected or mapped to that taxonomy's terms, as locked by
the organizer. Variation attributes are never written. Variable
parent, variation child, grouped, and external product types
each have a defined, tested enrichment target, or are rejected
with a reason. Originals are kept on first write only. Revert
of one field restores its original. Full revert restores all
fields. Uninstall restores originals, instead of today's rule
where the merchant must revert first. Term creation for
categories and tags does not leave orphan terms after revert,
or orphan terms are documented as accepted."

### 5B. Direct postmeta writes vs CRUD save()
Limitation (best practice, UNVERIFIED as an official product
rule): third-party WooCommerce CRUD guidance states: always use
WC_Product_Attribute and $product->save() instead of directly
updating _product_attributes postmeta or using wp_set_post_terms()
alone, because CRUD provides validation and consistency, and
because direct writes can leave product lookup tables
(wc_product_meta_lookup, wc_product_attributes_lookup) stale
until regeneration.

Official support, partial: the HPOS recipe book (official,
fetched above) states the same CRUD-plus-save principle for
ORDERS, not for products. By analogy it is the right pattern
for products, but this audit does NOT claim an official
WooCommerce page requires CRUD for product attributes — that
page was not fetched.

Effect, VERIFIED (code): the plugin writes _product_attributes
via update_post_meta, writes description/excerpt via
wp_update_post, writes categories/tags via wp_insert_term /
wp_set_post_terms, and writes image alt via update_post_meta.
It does call wc_delete_product_transients() after apply and
revert, which helps transient staleness, but it does NOT call
$product->save() and does NOT regenerate lookup tables. On a
store with layered navigation/filtering, a direct attribute
write could therefore be invisible to filters until a
regeneration or save happens elsewhere. This must be tested
live, not assumed.

Affects: requirement 7 (CHANGE, wording in 5A) and requirement
2 (CHANGE, wording in 2C, which already adds lookup staleness
testing).

### 5C. No hard product-count limit, but a hard pagination limit in code
Limitation: WooCommerce has no hard-coded product-count limit
found in this audit (third-party scaling summaries state this;
UNVERIFIED as an official claim). The plugin DOES have a hard
limit in code: get_posts(posts_per_page=100) in both /products
and /demo-reset. A store with more than 100 enriched products
would silently truncate the read surface and the demo reset.

Affects: new requirement 19 (pagination, below).

### 5D. Image alt, categories, and tags — smaller limits
- Image alt: plugin writes only the main product image's
  _wp_attachment_image_alt. Gallery images are not handled.
  VERIFIED (code). Affects requirement 7 (implementation note:
  gallery handling must be defined or explicitly out of scope).
- Categories/tags: wp_insert_term creates a term site-wide
  even if the publish later fails or is reverted; revert
  restores the term-ID list but does not delete the created
  term. VERIFIED (code). Affects requirement 7 (wording in 5A
  covers orphan terms).
- SKU/GTIN: WooCommerce core has SKU and a lookup table for it,
  but GTIN is not a core WooCommerce product field; the plugin
  blocks gtin and global_unique_id conservatively. That block
  is a PRD safety choice, not a WooCommerce core field limit.
  No change to requirement 7's block list from this finding.

---

## 6. Checkout, tax, shipping, and coupon calculation — why totals must stay server-side

Limitation: WooCommerce calculates cart and order totals
dynamically, in order: subtotal, then shipping, then additional
fees, then taxes (with tax-on-shipping depending on settings),
with coupons applied before or after tax depending on settings.
Totals change when quantity, fees, shipping method, tax rates,
or coupons change. No catalog field is the checkout total.

Official source, VERIFIED (WordPress.org support topic, not a
developer doc, but stating WooCommerce's calculation order):
https://wordpress.org/support/topic/how-the-fees-and-taxes-calculation-works/
What it actually says: "In WooCommerce, the order of
calculations generally works as follows: 1. Subtotal 2. Shipping
fees 3. Additional fees 4. Taxes" and "Total = (Subtotal +
Shipping + Fees) + Taxes" (varying with tax settings), and
"WooCommerce's cart and checkout pages always calculate totals
dynamically."

Effect: requirements 8 and 14 are CONFIRMED by this limit, not
changed in direction. A plugin that published a price, a total,
or a tax/shipping claim from enrichment would disagree with
the server's recalculation at checkout, and the checkout total
would win — or break. The plugin's current guards (no OvO block
on cart/checkout/account, no offers mutation, no price/stock in
the OvO block) are the correct shape. What must be added is
the block-checkout case: Marketplace submission states Cart and
Checkout blocks are now the default experience, and extensions
should eliminate shortcode dependency (official submission page,
fetched above). The plugin's is_checkout()/is_cart() guards
must therefore be tested on block checkout, not only on
shortcode checkout — that test is UNVERIFIED as passing in this
audit, because no live block-checkout test was run.

Affects: requirement 14 (CHANGE, minor wording) and requirement
8 (CHANGE, wording below).
Exact revised wording for requirement 14, proposed:
"Requirement 14 (revised): Payment pass-through proof, Decision
0, PRD R7 and R8, with WooCommerce as the sole total calculator.
Acceptance: the plugin has no payment route, no quote route,
and no checkout-total change. A test order completes through
the merchant's own Stripe checkout, and the order appears in
the merchant's existing system with correct data. Plugin
evidence for this requirement is checkout clean and totals
unchanged, not plugin ownership of payment. The checkout-clean
test is run on both shortcode checkout and block checkout,
because block Cart and Checkout are the default experience."

Exact revised wording for requirement 8, proposed:
"Requirement 8 (revised): Server-side surfaces verified live,
with checkout clean, on both permalink forms and with cache
invalidation. Acceptance: product page raw HTML contains the
separate ovo-enrichment JSON-LD block, with no change to the
WooCommerce offers block. GET /ovo/v1/products/{id} returns the
same fields. Price and stock are absent from the OvO block.
Cart, checkout, and account pages contain no OvO block, on
both shortcode and block checkout. Checkout totals are unchanged
and are recalculated by WooCommerce alone. After publish and
after revert, the product page and the OvO read surface show
the new state without a manual cache purge by the merchant
(see new requirement 18). The read surface is tested on Plain
permalinks via ?rest_route= and on pretty permalinks via
/wp-json/, because rest_url() must generate the correct form
for each store."

---

## 7. Multisite, caching, and permalink / rest_route limits

### 7A. Permalinks: plugin routes vs WooCommerce REST routes
Limitation: WordPress REST routes work on Plain permalinks via
?rest_route=, and on pretty permalinks via /wp-json/. WooCommerce
REST API (wc/v3) requires a non-Plain permalink setting.

Official sources, VERIFIED:
https://developer.wordpress.org/rest-api/extending-the-rest-api/routes-and-endpoints/
What it actually says: "By default, if you have pretty
permalinks enabled, the WordPress REST API 'lives' at /wp-json/"
and "On sites without pretty permalinks, the route is instead
added to the URL as the rest_route parameter", with the example
"http://example.com/?rest_route=/wp/v2/posts/123"; register
routes with register_rest_route() on rest_api_init.
https://woocommerce.com/document/woocommerce-rest-api/
What it actually says: "Go to Settings > Permalinks in your
WordPress dashboard and select any option other than Plain."

Effect: the plugin's own ovo/v1 routes are safe on Sole Mates'
Plain permalinks, because rest_url() generates the ?rest_route=
form. Any alternative Publish path that uses WooCommerce REST
API write-back (wc/v3) would NOT work on Sole Mates without
changing permalinks to a non-Plain structure. That alternative
must not be assumed to work on a Plain-permalink store.
Also, some external consumers reject query-string REST URLs
(third-party example: a feed URL with ?rest_route= rejected by
an ad platform — UNVERIFIED as a general rule, but a real
integration risk to test for agent consumers that expect
/wp-json/ paths).

Affects: requirement 8 (CHANGE, wording in section 6) and
requirement 13 (CHANGE, wording below).

### 7B. Multisite: options, tokens, and activation are per-site unless designed otherwise
Limitation: WordPress multisite activation can be network-wide
or per-site, and get_option() is per-site while get_site_option()
is network-wide. A plugin that stores its token, audit log, and
demo-mode flag with get_option() and does not handle the
networkwide activation case will behave per-site, and a network
activation will not loop sites unless the plugin does so.

Source: third-party summaries of activate_plugin() and
multisite settings handling — UNVERIFIED as an official-page
claim in this audit, because no official developer.wordpress.org
multisite page was fetched. The mechanism (per-site options vs
site options) is standard WordPress behaviour and is consistent
with the plugin code, but the parent should not cite it as an
official rule until an official multisite page is fetched.

Effect, VERIFIED (code): the plugin uses get_option() for
ovo_enrichment_audit_log, ovo_enrichment_demo_mode, and
ovo_enrichment_token_hash, and update_post_meta() for product
meta, all per-site. Its activation hook only initialises the
audit log option, with no networkwide loop. Its admin menu is
under WooCommerce per site. The production list does not state
whether OvO supports multisite at all. That is a scope gap, not
a bug on a single-site store.

Affects: new requirement 17 (below).

### 7C. Caching: transients are cleared, page cache is not
Limitation (design, UNVERIFIED as an official rule): the plugin
calls wc_delete_product_transients() after apply and revert,
which clears WooCommerce product transients. It does NOT purge
full-page cache, object cache beyond transients, CDN cache, or
REST response cache, and it sets no Cache-Control headers on
its public GET routes. A cached product page or a cached
/ovo/v1/products response could therefore show stale enrichment
after a publish or revert until the host's cache expires or
the merchant purges manually.

Effect: requirement 8's "raw HTML contains the block" test
could pass on an uncached page and fail on a cached page, or
vice versa. Cache invalidation must be an explicit acceptance
test, not an assumption.

Affects: new requirement 18 (below).

### 7D. REST versioning
Limitation: WordPress REST namespaces are versioned (v1, v2),
and a plugin can keep old and new versions side by side by
bumping the version number, rather than silently changing v1.

Official source, VERIFIED, via the REST routes page above:
https://developer.wordpress.org/rest-api/extending-the-rest-api/routes-and-endpoints/
What it actually says: "you can maintain backwards
compatibility of your REST API endpoints by simply creating new
endpoints and bumping up the version number you provide. This
way both the original v1 and v2 endpoints can be accessed."

Affects: requirement 13 (CHANGE, minor).
Exact revised wording for requirement 13, proposed:
"Requirement 13 (revised): Agent-facing interface, PRD R6,
stable and versioned, with a defined cache policy. Acceptance:
GET /ovo/v1/manifest, /ovo/v1/products, and /ovo/v1/products/{id}
return approved enrichment fields only, with a price and stock
note, and no price or stock values. The surface is versioned,
and a breaking change requires a new version (v2) alongside v1,
not a silent change to v1. Public GET responses state their
cache policy, and cache invalidation after publish and revert
is tested (see new requirement 18)."

---

## 8. Requirements with NO CHANGE from this audit

### Requirement 3 — Full PRD autonomy tier enforcement
NO CHANGE. No WordPress or WooCommerce limit fetched changes
the tier thresholds (95 / 80-94 / 50-79 / below 50) or the
rejection-by-exception model. One distribution note, not a
wording change: if tier features are tied to a paid OvO account,
WordPress.org distribution requires the paid part to live in
the external service, not as locked plugin code (see finding
3A). The tier rule itself is a PRD rule, not a platform rule.

### Requirement 4 — Approval verification inside the plugin
NO CHANGE to the requirement. One implementation note: a
plugin's permission_callback MAY check a custom header such as
X-Ovo-Token — that is how the current code works, and it is
not a WordPress core authentication method. The requirement
already demands that the plugin recompute the fingerprint and
check approval status and rows; this audit confirms that
neither Application Passwords nor WooCommerce REST keys can
substitute for that check, because both are broader than the
diff (see finding 4).

### Requirement 6 — Canonical diff format and field mapping
NO CHANGE. No platform limit changes the need for one locked
canonical set or one locked mapping. The attribute-mapping
consequences (global vs custom, variation children) belong to
requirement 7, not to requirement 6.

### Requirement 9 — Coordinator wiring, Merchant Approval, Publish to Plugin
NO CHANGE to the requirement as written. One note: if Publish
to Plugin were re-routed through WooCommerce REST API write-
back instead of the plugin's own route, the Plain-permalink
limit in finding 7A would apply, and a Read/Write Woo key would
be broader than the diff (finding 4B). Neither changes the
coordinator's pause-at-approval and published-flag acceptance
test.

### Requirement 12 — Hostile text handling, PRD R9
NO CHANGE. WordPress's sanitize/validate/escape discipline
(sanitize_text_field, wp_kses_post, esc_html, esc_url — all
already used in the plugin code) supports this requirement, and
no platform limit fetched changes the red-team acceptance test.
The plugin's current wp_kses_post on new_value and
sanitize_text_field on field/source/confidence are consistent
with that discipline, but they do not by themselves prove
hostile-text handling — the red-team test in requirement 12
is still required.

---

## 9. New requirements proposed (4)

### New requirement 16 — HPOS declaration and order-data non-interference
Requirement: the plugin declares HPOS compatibility only after
testing, and never touches order data except through WooCommerce
CRUD APIs.
Acceptance: FeaturesUtil::declare_compatibility(
'custom_order_tables', __FILE__, true ) is present in the main
plugin file, HPOS on and HPOS off are both tested, the plugin
appears as HPOS-compatible (not uncertain) in WooCommerce >
Settings > Advanced > Features, and no code path reads or writes
order postmeta directly. Demo reset and revert are tested with
HPOS on, and orders, carts, and shopper sessions are untouched.
Source: official submission page and HPOS recipe book, VERIFIED
above. Affects: new, but closely related to requirements 1, 2,
and 15 — do not double-count it as a change to those items.

### New requirement 17 — Multisite scope decision
Requirement: the production scope for multisite is stated and
tested, or multisite is explicitly out of scope.
Acceptance: either (a) multisite is supported, with per-site
token, audit log, and demo-mode state, network activation
handled per site, and a test on a two-site network; or (b) the
readme and install path state single-site only, and network
activation is refused or documented as unsupported, with a test
that it does not silently share one site's token or audit log
with another site. Source: UNVERIFIED as an official-page claim
(third-party multisite summaries only); the scope decision
itself is required regardless, because the current code is
per-site by construction (get_option, per-site admin menu).

### New requirement 18 — Cache invalidation after publish and revert
Requirement: after publish and after revert, the product page,
the OvO JSON-LD block, and the OvO read surface show the new
state without merchant manual cache purging.
Acceptance: publish and revert are tested with WooCommerce
product transients cleared (already done in code), plus a
full-page cache plugin active, plus a CDN/object cache if the
test store uses one. The test records which caches are purged
by the plugin and which, if any, require host action, and the
readme states that record. Source: UNVERIFIED as an official
rule; it is a design/test requirement arising from the code's
current wc_delete_product_transients() only coverage.

### New requirement 19 — Pagination and batch limits for large catalogs
Requirement: the read surface and demo reset work beyond 100
enriched products, and diff batches respect a stated limit.
Acceptance: /ovo/v1/products returns all enriched products on a
test store with more than 100 enriched products, via pagination
or a stated page size, not a silent 100 cap. Demo reset reverts
all enriched products on the same test store. Diff batches
state a maximum change count, and a batch above that count is
rejected or split with a stated rule, not silently truncated.
Source: VERIFIED (code) for the current 100 cap in get_posts(
posts_per_page=100) in both routes; the WooCommerce REST batch
limit of 100 objects per request was seen only in third-party
summaries and is UNVERIFIED as an official claim, so it is not
used as the basis for this requirement — the code's own 100 cap
is sufficient basis.

---

## 10. What this audit did NOT verify (do not cite as verified)

- Custom product tables (wp_wc_products) in WooCommerce 10.0+:
  third-party claim only, no official page fetched. Watch item.
- Global vs custom attribute taxonomy behaviour and lookup-table
  regeneration step: third-party best practice only, no official
  attributes page fetched. Test live before citing as a rule.
- Multisite option/activation behaviour: third-party summaries
  only, no official multisite page fetched.
- Store API rate-limit numbers (25 per 10 seconds, checkout
  POSTs 3 per 60 seconds): third-party summaries only, no
  official Store API rate-limit page fetched. Do not cite numbers.
- WooCommerce REST batch limit of 100 objects: third-party only.
- Application Password edge cases (HTTPS requirement, user
  deletion, 2FA interaction, security-plugin disabling): third-
  party summaries only, no official handbook page fetched in
  full (the handbook page was returned via a mirror in search).
- SEO/structured-data duplicate-Product risk from a second
  Product JSON-LD block: no official source fetched; test item
  only, not a requirement in this audit.
- Current "latest" WordPress/WooCommerce version numbers: not
  stated in this audit, because they change and no official page
  fetched here pins a pair that will still be latest at
  submission. Re-check at submission time against the two-latest-
  majors rule.

## 11. Source list (verbatim URLs, as returned)

Official, fetched and quoted above:
- https://developer.woocommerce.com/docs/woo-marketplace/submitting-your-product/
- https://developer.woocommerce.com/2025/03/20/getting-to-know-the-woo-marketplace-a-developers-look/
- https://developer.woocommerce.com/docs/woo-marketplace/product-update-guidelines/
- https://developer.woocommerce.com/docs/features/orders/high-performance-order-storage/recipe-book/
- https://developer.wordpress.org/plugins/wordpress-org/detailed-plugin-guidelines/
- https://developer.wordpress.org/plugins/wordpress-org/plugin-developer-faq/
- https://developer.wordpress.org/rest-api/extending-the-rest-api/routes-and-endpoints/
- https://woocommerce.com/document/woocommerce-rest-api/
- https://woocommerce.com/document/tables-de-base-de-donnees-installees/
- https://wordpress.org/support/topic/how-the-fees-and-taxes-calculation-works/
- https://developer.woocommerce.com/docs/extensions/core-concepts/example-header-plugin-comment/

Third-party / search-result only, used only where marked UNVERIFIED:
- https://devdiggers.com/how-to-create-woocommerce-plugin/
- https://copyprogramming.com/howto/wc-add-product-attributes-code-example
- https://rollout.com/integration-guides/woocommerce/api-essentials
- https://make.wordpress.org/plugins/handbook/performing-reviews/review-checklist/
- https://gist.github.com/DannyCooper/a3fe77c34632535fa14b8f56ca13dc20

## 12. Post-audit note: Merchant Approval tenant check (R4), from memory update 2026-10-30

This note was added after the main audit, from a memory update
from another stream, not from a WordPress/WooCommerce source.
It does not change the counts above.

Merchant Approval R4, built into code 2026-10-30: packet, cards,
and record carry merchant ID and store ID when supplied; a
decision with mismatched IDs is rejected; no packet lists rows
from more than one store. Limits stated in that update: live
inputs supply a store URL and no merchant ID, so the live packet
is store_only_no_merchant_id; the session check (R6) is
structural only, with no cryptographic signature verified,
because no platform issuer or key is supplied yet; static card
HTML cannot enforce who opens it, so live card serving must
check tenant (platform work).

Effect on this audit: it strengthens requirements 4 and 5.
A per-store token (requirement 5, revised) cannot yet be
verified against a merchant ID from the approval record on a
live store, because the live approval packet carries no merchant
ID. Until live inputs supply merchant ID and store ID, the
plugin can verify store identity only by the fact that it runs
on that store and the product exists there — the same limit
already stated for v0.2. Do not claim tenant verification from
the approval record until that live-input gap is closed. R5
(questions) and R6 (session authority) belong to Merchant
Approval / Coordinator, not to the plugin, and are not added
as plugin requirements here.

## 13. Bottom line for the parent's revision

Do not revise the production list by only adding "HPOS" as a
word. The three changes that most affect whether the list can
pass are: (1) name the distribution channel, because Woo
Marketplace and WordPress.org have different, incompatible
free/paid and serviceware rules, and Marketplace adds vendor
account, QIT, 30-day review, two-latest-majors, and 6-month
update rules; (2) replace the token design's borrowed-credential
option with a plugin-owned token, because Application Passwords
and WooCommerce REST keys both inherit full user permissions
with no per-field scope and no core expiry; (3) move attribute
writes to WooCommerce CRUD with save() and test lookup/filter
staleness, because the current direct _product_attributes
postmeta write, plus the missing global-vs-custom check, is
the most likely live-store break in the current code, after
the missing HPOS declaration itself.
