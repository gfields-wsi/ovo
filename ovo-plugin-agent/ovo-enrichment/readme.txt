=== OvO Enrichment ===
Contributors: ovo-hackathon
Tags: woocommerce, agentic commerce, enrichment
Requires at least: 6.0
Tested up to: 6.9
Requires PHP: 7.4
Stable tag: 0.2.0-demo
License: GPLv2 or later

Publishes merchant-approved enrichment in place on the merchant's own WooCommerce store, with originals kept for revert.

== Description ==

OvO Enrichment does not become the shop. It publishes enrichment on the store's own product pages, in server-rendered form, so an agent can read it without JavaScript.

What it does:

* Server-rendered JSON-LD block, id "ovo-enrichment", on single product pages only. Nothing is output on cart, checkout, or account pages. WooCommerce's own Product JSON-LD is left untouched, so its offers block stays canonical.
* A plain link on product pages to the OvO REST read surface for that product.
* REST read routes: /ovo/v1/manifest, /ovo/v1/products, /ovo/v1/products/{id}. These return approved enrichment fields only. Price and stock are deliberately absent from this surface. Agents must read price and stock from the store's own product data.
* REST write route /ovo/v1/diff, admin-only, for Stream 2 field-level diffs. Each change is checked against the live store value first. A stale diff is rejected, not applied over a merchant edit.
* Originals kept in _ovo_originals post meta, first-write wins. Every change is reversible with /ovo/v1/revert.
* Demo reset, /ovo/v1/demo-reset, with demo mode on and confirm set to RESET-DEMO. It reverts enrichment, keeps the audit log, and does not delete WooCommerce orders, carts, or shopper sessions.

What it never does:

* It never writes price, regular price, sale price, sale dates, stock quantity, stock status, SKU, GTIN, tax class, shipping class, weight, or dimensions from modelled data. Those fields are blocked in code, not just in guidance.
* It never writes material, safety, compatibility, returns, shipping, or tax policy claims from modelled data.
* It never changes checkout totals. WooCommerce recalculates totals server-side.
* It never writes a variation attribute. Changing a Size term would break variations, so size-label notes publish as JSON-LD additional_property only.
* Modelled wording may only publish as additional_property, never as a native store field. Modelled short descriptions and descriptions are rejected by the plugin.

Honest limits:

* Demo build only, for the Meta AI Hackathon freeze on 2026-11-02. Not a production plugin. Not listed in the WordPress plugin directory. Zip upload is a demo-only install method.
* No claim of MCP, ACP, or UCP compliance, consumer Muse discovery, live payment, or production plugin compatibility.
* No scoped agent token yet. Writes require a logged-in admin who can manage options. That is a stated gap.
* Payment stays pass-through on the merchant's own checkout and processor. This plugin does not touch payment at all. The earlier payment-bridge plan in plan.md is superseded for this stream by Decision 0: OvO is the behind-the-scenes enabler, not the buyer, and gates live in the store and agent tools.
* Revert before uninstall if you want originals restored. Uninstall deletes OvO meta only.

== Installation ==

Demo only: upload the ovo-enrichment zip in WP admin, Plugins, Add New, Upload Plugin, then activate. No catalog change happens on activation. Enrichment only arrives through an approved diff.

== Frequently Asked Questions ==

= Where is enrichment verified? =
With curl, on the raw server response, not in a browser DOM. See verify-live.sh. Check the product page HTML for the ovo-enrichment script, check /ovo/v1/products/{id}, and check that checkout HTML contains no ovo-enrichment block.

= What happens if Stream 2 sends a price change? =
It is rejected. The diff response lists it under rejected, with the reason. Nothing is written for that change.

== Changelog ==

= 0.2.0-demo =
Scoped OvO token auth, stored as a hash only, generated once in admin. A token call must carry approved_by and approval_fingerprint. Confidence below 50 percent is rejected. Augment runner in the parent folder verifies the approval fingerprint, maps approved framework rows to JSON-LD additional_property only, and fails closed when approval is awaiting. Live WordPress test is still pending, and the plugin is still not installed on Sole Mates.

= 0.1.0-demo =
First demo build. JSON-LD, REST read, REST diff with old-value check, originals and revert, demo reset, admin status page.
