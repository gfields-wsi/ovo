=== OvO Enrichment ===
Contributors: ovo
Tags: woocommerce, agentic commerce, enrichment
Requires at least: 6.5
Tested up to: 7.1.4
Requires PHP: 7.4
WC requires at least: 10.0
WC tested up to: 11.3.0
Stable tag: 1.0.0
License: GPLv2 or later

Publishes merchant-approved enrichment in place on the merchant's own WooCommerce store, with originals kept for revert.

== Description ==

OvO Enrichment does not become the shop. It publishes enrichment on the store's own product pages, in server-rendered form, so an agent can read it without JavaScript.

This plugin is free. No feature is locked behind payment, and no license check sits in this plugin code. The paid OvO service behind it is described below, under "The OvO service and the data sent".

What it does:

* Server-rendered JSON-LD block, id "ovo-enrichment", on single product pages only. Nothing is output on cart, checkout, or account pages. WooCommerce's own Product JSON-LD is left untouched, so its offers block stays canonical.
* A plain link on product pages to the OvO REST read surface for that product.
* REST read routes: /ovo/v1/manifest, /ovo/v1/products, /ovo/v1/products/{id}. These return approved enrichment fields only. Price and stock are deliberately absent from this surface. Agents must read price and stock from the store's own product data. The list route is paginated (page and per_page, 100 at most) and answers X-WP-Total and X-WP-TotalPages headers, so a store with more than 100 enriched products is not silently capped.
* REST write route /ovo/v1/diff, admin-only or scoped-token, for approved field-level diffs. Each change is checked against the live store value first. A stale diff is rejected, not applied over a merchant edit.
* Originals kept in _ovo_originals post meta, first-write wins. Every change is reversible with /ovo/v1/revert. Uninstall restores the kept originals first, then deletes OvO data.
* Product webhooks: on activation the plugin creates one webhook per product event (created, updated, deleted) so OvO is told when the catalog changes. A daily check repairs a missing or disabled webhook. See "Webhooks" below.
* Cache purge after publish and revert: WooCommerce product transients are cleared, plus the full-page cache of any cache plugin found on the store (W3 Total Cache, WP Super Cache, WP Rocket, LiteSpeed Cache), plus a generic action hosts can hook. What was purged is recorded in the audit log.
* Audit log: every write records old value, new value, source, approver, approval fingerprint, batch id, and what caches were purged. The log is kept (up to 5,000 entries) and the last 50 show in WooCommerce > OvO Enrichment.

What it never does:

* It never writes price, regular price, sale price, sale dates, stock quantity, stock status, SKU, GTIN, tax class, shipping class, weight, or dimensions from modelled data. Those fields are blocked in code, not just in guidance.
* It never writes material, safety, compatibility, returns, shipping, or tax policy claims from modelled data.
* It never changes checkout totals. WooCommerce recalculates totals server-side.
* It never writes a variation attribute. Changing a Size term would break variations, so size-label notes publish as JSON-LD additional_property only.
* Modelled wording may only publish as additional_property, never as a native store field. Modelled short descriptions and descriptions are rejected by the plugin.
* It never reads or writes order data. It declares HPOS compatibility and touches products only, through WooCommerce CRUD objects and WordPress post functions.

== The OvO service and the data sent ==

OvO is a service that makes a WooCommerce store readable by shopping agents. The plugin on its own publishes enrichment that the merchant has already approved. The service does the audit and the enrichment drafting, and the merchant approves the result on the OvO site before anything publishes.

Data the plugin sends to OvO:

* Product change messages (webhooks): when a product is created, updated, or deleted, WooCommerce sends a signed message to the OvO endpoint with that product's public data (product id, name, description, price, stock status). The message is signed, so OvO can trust it came from this store. No customer data, no order data, and no payment data is sent in these messages.
* Nothing else leaves the store from this plugin. The read routes are public and are read by agents; the plugin does not send data when they are read. The diff route receives approved batches from the OvO runner; it does not send store data out.

The OvO service terms of use and privacy policy are on the OvO site at https://wsiventures.com/ovo. By activating this plugin and connecting the OvO service, the merchant agrees to those terms. The merchant can stop the data flow at any time by deactivating the plugin, which pauses the webhooks.

== Installation ==

Install from the WordPress plugin directory (version 1 channel), or upload the zip in WP admin, Plugins, Add New, Upload Plugin, then activate. Direct download from the OvO site is the pilot path. No catalog change happens on activation. Enrichment only arrives through an approved diff.

Single-site only. Network activation is not supported, and the plugin does not share tokens or audit logs between sites.

== Webhooks ==

On activation the plugin creates three webhooks: product.created, product.updated, product.deleted. The delivery address is the OvO endpoint, https://wsiventures.com/ovo/webhooks, unless the store sets the ovo_enrichment_webhook_url option to another address. Each webhook carries its own secret, and deliveries are signed with it. A daily check (WP-Cron, plus a "Check webhooks now" button in WooCommerce > OvO Enrichment) recreates or repairs any webhook that is missing, disabled, or pointing at the wrong address, and logs what it fixed.

== Frequently Asked Questions ==

= Where is enrichment verified? =
With curl, on the raw server response, not in a browser DOM. See verify-live.sh. Check the product page HTML for the ovo-enrichment script, check /ovo/v1/products/{id}, and check that checkout HTML contains no ovo-enrichment block.

= What happens if a diff sends a price change? =
It is rejected. The diff response lists it under rejected, with the reason. Nothing is written for that change.

= What happens on uninstall? =
Uninstall restores the kept originals first, so the catalog goes back to how it was before OvO wrote anything, then deletes OvO meta, webhooks, and options. Export the audit log first if the record is needed.

== Changelog ==

= 1.0.0 =
Production release. Version 1.0.0. Publish writes only approved fields, keeps originals, and undo restores them. Blocked fields (price, stock, SKU, tax, shipping, policy claims) are refused in code. Server cache is purged after publish and revert. Product webhooks are created on activation and checked daily. The manifest answers at /ovo/v1/manifest with version, cache policy, and webhook status. The products list is paginated past 100. The audit log records old and new values, approver, fingerprint, and batch id. HPOS compatibility declared after testing with HPOS on and off. Tested on WordPress 7.1.4 with WooCommerce 11.3.0, and on WordPress 7.0.8 with WooCommerce 10.9.4.

= 0.2.0-demo =
Scoped OvO token auth, stored as a hash only, generated once in admin. A token call must carry approved_by and approval_fingerprint. Confidence below 50 percent is rejected. Augment runner in the parent folder verifies the approval fingerprint, maps approved framework rows to JSON-LD additional_property only, and fails closed when approval is awaiting. Live WordPress test is still pending, and the plugin is still not installed on a live store.

= 0.1.0-demo =
First demo build. JSON-LD, REST read, REST diff with old-value check, originals and revert, demo reset, admin status page.
