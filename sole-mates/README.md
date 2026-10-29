# Sole Mates — Mock Shoe Store

Fictional WordPress + WooCommerce shoe store for the WSI / Meta hackathon (Ovo agent-to-agent storefront enablement). **Storefront only** — this repo does not contain the rest of the Ovo app.

- Store: **Sole Mates**
- Platform: WordPress + WooCommerce, Storefront child theme (`wp-content/themes/sole-mates`)
- Catalog: 12 products, 79 size variations — boots, sandals, sneakers, slippers, runners, in different colours and sizes. See `data/products.json` (source of truth) and `data/products.csv` (WooCommerce import).
- Price: **everything $1 CAD**, test-mode checkout only. No real payments.
- Build: **clean build first**. Intentional shortcomings for the agent audit demo will be introduced later, on a separate branch / step — not in this first version.

## What's in this repo

| Path | What it is |
| --- | --- |
| `wp-content/themes/sole-mates/` | Storefront child theme. Homepage = catalog, 12 products, 3 per row. |
| `wp-content/plugins/sole-mates-demo-data/` | Optional plugin. On activation it creates the 12 variable products from `data/products.json`. |
| `data/products.json` | Source of truth for the catalog. |
| `data/products.csv` | WooCommerce Product Import CSV (variable products + size variations). Use this instead of the plugin if you prefer manual import. |
| `docs/SETUP-LOCALWP.md` | Step-by-step LocalWP setup. |
| `docs/DEMO-SCRIPT.md` | Hero demo purchase: Velocity Road Runners, size 9.5, Electric Blue, $1. |

## Quick start (LocalWP)

Full steps in `docs/SETUP-LOCALWP.md`. Short version:

1. In LocalWP, create a fresh site, e.g. `solemates.local`, PHP 8.1+, WordPress latest.
2. Install + activate WooCommerce, run its setup wizard, set currency to CAD, enable test payments (WooCommerce Payments in test mode, or Cash on Delivery for the very first test).
3. Install the **Storefront** theme from Appearance > Themes, then copy `wp-content/themes/sole-mates/` into your site's `wp-content/themes/` and activate **Sole Mates**.
4. Create products one of two ways — pick one, not both:
   - **Plugin:** copy `wp-content/plugins/sole-mates-demo-data/` into `wp-content/plugins/`, copy `data/` to `wp-content/sole-mates-data/` if the plugin is installed on its own, then activate the plugin.
   - **CSV:** WooCommerce > Products > Import, upload `data/products.csv`.
5. Set the homepage: Settings > Reading > "Your homepage displays: A static page", Homepage = a page using the Sole Mates front page, or simply leave the Shop page as the homepage for the demo. WooCommerce > Settings > Advanced should already have Cart, Checkout and My Account pages.
6. Test checkout with a $1 product in test mode. Do not use a real card.

## Assumptions / open questions

- Currency is CAD (Cameron is in Toronto). Change in WooCommerce > Settings > General if the demo should be USD.
- Sizing is US sizing. Product colours are fixed per product; size is the variable attribute. That keeps 79 variations instead of size × colour exploding.
- Product images: one generated studio image per shoe (12 total) in `assets/images/` and in the plugin at `wp-content/plugins/sole-mates-demo-data/images/`. The plugin attaches each image as the product featured image on activation. The CSV also lists each image as a raw GitHub URL, so the WooCommerce importer can fetch it once the images are in GitHub.
- Theme v0.2.0: monochrome visual polish inspired in general terms by Db Journey — black/white/light-grey, Inter type, generous spacing, square product tiles, pill buttons, hero + featured + shop-by-type + black CTA on the homepage. No sliders, no new features, no copied branding or copy.
- Theme v0.3.0: no sidebar on product pages, no header search, no promo banner, simple Sole Mates logo (sole-tread icon + SOLE MATES wordmark) in the nav and as favicon (`wp-content/themes/sole-mates/assets/sole-mates-logo.png` and `sole-mates-icon.png`), bolder PDP tabs with hover/active states, styled variation dropdowns and quantity inputs. Delete the default WordPress Sample Page in WP Admin (Pages > Sample Page > Trash) — it is not part of the store.
- Theme v0.3.1: sidebar also removed on shop and product category/tag pages, PDP image viewer is square with the image covering the whole area (object-fit: cover).
- Plugin v0.1.3: 3 demo reviews per product (36 total, average 4.6 stars — 23×5, 11×4, 2×3), varied by sizing, fit, look, comfort and durability, added from `data/products.json` on activation, including for products that already exist.
- No real brand names. Product names are fictional / generic.

## Hackathon notes

- This repo must be **new and public** for the hackathon. Do not push pre-existing project history into it.
- Do not commit WordPress core, `wp-content/uploads/`, database dumps, `.env`, or payment keys. See `.gitignore`.
