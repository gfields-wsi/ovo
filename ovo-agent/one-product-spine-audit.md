# One-product spine — audit + enrichment draft only

Spine product: Court Classic White Sneakers
Live store: https://wsiventures.com/solemates
Product page: https://wsiventures.com/solemates/?product=court-classic-white-sneakers
Store API (public, `?rest_route=` form): https://wsiventures.com/solemates/?rest_route=/wc/store/v1/products
Audit model: Muse Spark 1.3 via the Meta Model API (reasoning_effort minimal)
Fetched: 2026-10-29 (page/API crawl timestamp 2026-10-30 00:42 UTC)
Status: DRAFT ONLY. Nothing in this file has been published to the store.
No order was placed in this task. No store setting was changed.

## 1. Product ground truth, exactly as fetched

### Store API record

- id: 48
- name: Court Classic White Sneakers
- slug: court-classic-white-sneakers
- type: variable
- permalink: https://wsiventures.com/solemates/?product=court-classic-white-sneakers
- SKU: SM-SNEA-001
- short_description: "Minimal white leather court sneakers."
- description: "A clean, minimal white court sneaker that goes with everything. Leather upper, padded collar, rubber cupsole. Material: Leather upper, rubber cupsole Fit: True to size. Returns: 30-day returns, unworn."
- on_sale: false
- prices: price "100", regular_price "100", sale_price "100", price_range null, currency_code "CAD", currency_symbol "$", currency_minor_unit 2 — i.e. $1.00 CAD
- price_html: "$1.00"
- average_rating: "4.67"
- review_count: 3
- images: one image — id 49, src https://wsiventures.com/solemates/wp-content/uploads/2026/10/sm-snea-001.webp, file name "sm-snea-001.webp", alt ""
- categories: Sneakers (id 18)
- tags: []
- brands: []
- attributes:
  - Size, has_variations true: 6, 7, 8, 9, 9.5, 10, 11, 12
  - Colour, has_variations false: White
- variations (Size only):
  - 50 = 6, 51 = 7, 52 = 8, 53 = 9, 54 = 9.5, 55 = 10, 56 = 11, 57 = 12
- grouped_products: []
- has_options: true
- is_purchasable: true
- is_in_stock: true
- is_on_backorder: false
- low_stock_remaining: null
- stock_availability: text "", class "in-stock"
- sold_individually: false
- weight: ""
- dimensions: length "", width "", height ""
- formatted_weight: "N/A"
- formatted_dimensions: "N/A"
- extensions: {}

### Product page, as rendered in the text fetch

- Title: Court Classic White Sneakers
- Price shown: $1.00
- Short description shown: "Minimal white leather court sneakers."
- SKU shown: SM-SNEA-001; Category shown: Sneakers
- Description shown: same text as the Store API description above.
- Additional information table: Size 6, 7, 8, 9, 9.5, 10, 11, 12; Colour White — nothing else.
- Product Offer block shown: Product: Court Classic White Sneakers; Price: 1.00 CAD; Availability: InStock; Source: JSON-LD Product.offers.
- Rating wording shown: "Rated 4.67 out of 5 based on 2 customer ratings (3 customer reviews)".
- One product image shown (sm-snea-001-416x277.webp in the page render).
- Related products shown: Retro High-Top Sneakers.

### Rating-count discrepancy — flagged, not resolved

- Store API says review_count 3.
- Product page says "based on 2 customer ratings (3 customer reviews)".
- Do not publish either count as authoritative until the merchant / WooCommerce review data is checked. The rating value 4.67 agrees in both places; the count does not.

### Fields confirmed missing from both the API record and the page

- Width (no width attribute at all)
- Weight (empty) and dimensions (all empty, formatted "N/A")
- Stock quantity per variation (low_stock_remaining null, stock_availability text empty; only a boolean in-stock flag exists)
- Shipping policy (nothing beyond the returns sentence in the description)
- Tax (nothing shown)
- GTIN / barcode (nothing)
- Brand (brands empty)
- Image alt text (alt "")
- Care instructions (nothing)
- Closure type (nothing — do not infer laces from the photo or the word "sneaker")
- Size guide (nothing)
- Gender / audience, occasion beyond "goes with everything" (nothing structured)
- Per-variation price differences (all variations share the single $1.00 price in this record)

## 2. Readiness audit — Muse Spark 1.3

Score: 4 / 7.

Scoring basis, as returned by Spark, checked against the ground truth above:

- Identifier: +1 — id 48, slug court-classic-white-sneakers, SKU SM-SNEA-001 grounded in the Store API.
- Price machine-readable: +1 — price / regular / sale all "100", currency CAD, minor unit 2, so $1.00 CAD; on_sale false; page shows $1.00 and a JSON-LD Product.offers price of 1.00 CAD.
- Availability purchasable: +1 — is_purchasable true, is_in_stock true, is_on_backorder false, class in-stock; JSON-LD Availability InStock.
- Description / category: +1 — short description "Minimal white leather court sneakers."; description includes leather upper, padded collar, rubber cupsole; category Sneakers (id 18).
- Variants structured: 0 — sizes 6–12 with variation ids 50–57 and Colour White are grounded, but there is no stock quantity per variation, low_stock_remaining is null, and stock_availability text is empty.
- Media / trust: 0 — one image (id 49, sm-snea-001.webp) with empty alt text; brands empty; tags empty; rating value 4.67 grounded but the count conflicts (see above).
- Policy / attributes for compare: 0 — returns "30-day returns, unworn" is grounded, but no shipping, tax, width, weight, dimensions, GTIN, care, closure, or size guide is visible.

### Ranked gaps, most blocking first

1. Stock quantity per size missing — blocks buy. is_in_stock is true, but no quantity is given for any variation (ids 50–57), so an agent cannot confirm that size 9, 9.5, or any other size is actually buyable in the quantity asked for.
2. Rating count conflict — blocks compare / trust. API review_count 3 vs page wording "2 customer ratings (3 customer reviews)". Flagged, not resolved.
3. Image alt text empty — blocks find / accessibility. Image 49 alt is "".
4. Brand / GTIN missing — blocks find / compare. Brands empty; no GTIN anywhere.
5. No shipping / tax / size guide / width / weight / dimensions / care / closure — blocks buy / compare. Weight and dimensions are empty, formatted "N/A"; the Additional information table lists Size and Colour only.
6. Tags empty — limits find. Tags [].

## 3. Enrichment diff — every row source-labelled

Rules applied: no price, stock, SKU, tax, shipping, or policy claim unless it appears in the fetched store data. Anything not in the ground truth is a merchant question, never a published fact.

| Proposed field | Proposed value | Source |
|---|---|---|
| Product name | Court Classic White Sneakers | store text |
| SKU | SM-SNEA-001 | store text |
| Price | $1.00 CAD (regular $1.00, sale $1.00, on_sale false) | store text |
| Availability | InStock; is_purchasable true; is_on_backorder false | store text |
| Category | Sneakers | store text |
| Short description | Minimal white leather court sneakers. | store text |
| Description | A clean, minimal white court sneaker that goes with everything. Leather upper, padded collar, rubber cupsole. Material: Leather upper, rubber cupsole. Fit: True to size. Returns: 30-day returns, unworn. | store text |
| Material (upper) | Leather upper | store text |
| Material (sole) | Rubber cupsole | store text |
| Fit | True to size | store text |
| Returns | 30-day returns, unworn | store text |
| Size options | 6, 7, 8, 9, 9.5, 10, 11, 12 | store text |
| Colour | White | store text |
| Image | sm-snea-001.webp (id 49) | store photo |
| Rating value | 4.67 | store text |
| Rating count | MERCHANT QUESTION — do not publish | UNKNOWN (conflict: API 3 vs page "2 ratings / 3 reviews") |
| Image alt text | MERCHANT QUESTION — do not publish | UNKNOWN |
| Brand | MERCHANT QUESTION — do not publish | UNKNOWN |
| GTIN | MERCHANT QUESTION — do not publish | UNKNOWN |
| Stock quantity per variation | MERCHANT QUESTION — do not publish | UNKNOWN |
| Width | MERCHANT QUESTION — do not publish | UNKNOWN |
| Weight | MERCHANT QUESTION — do not publish | UNKNOWN |
| Dimensions | MERCHANT QUESTION — do not publish | UNKNOWN |
| Shipping policy | MERCHANT QUESTION — do not publish | UNKNOWN |
| Tax | MERCHANT QUESTION — do not publish | UNKNOWN |
| Care instructions | MERCHANT QUESTION — do not publish | UNKNOWN |
| Closure type | MERCHANT QUESTION — do not publish | UNKNOWN |
| Size guide | MERCHANT QUESTION — do not publish | UNKNOWN |

Correction to Spark's raw output, made in this file: Spark's diff listed the short description ("Minimal white leather court sneakers.") under "Name/Title". The product name in the ground truth is "Court Classic White Sneakers"; the short description is a separate field, shown above as its own row. No other value in Spark's output was changed; its unknown rows were already merchant questions, with no invented values.

### Fields that could not be grounded at all

Stock quantity per variation, tax, shipping policy, width, weight, dimensions, brand, GTIN, care instructions, closure type, size guide, image alt text, and the authoritative review count. None of these appears in the fetched Store API record or product page, and none is claimed in this file.

Note on photos: Spark did not verify that the photo matches the product, and neither does this file. The image file and its empty alt text are recorded; what the photo shows was not used as a source for any product fact.

## 4. What is NOT yet proven — do not claim these

- Publish step: NOT done. This diff is a draft only. No field has been written back to WooCommerce, no original has been kept for revert yet, and no merchant approval has been sought.
- Agent read step: NOT done. No reference agent has been run against this product after enrichment, and no before/after comparison exists for this product.
- Agent checkout step: NOT done. The Store API agent checkout with Stripe is still open (Stripe requires a payment token made through its own payment form; a direct API token call was blocked). Test order 122 (Court Classic White Sneakers, size 9, $1.00) was a browser block-checkout test of the Stripe gateway, not an agent checkout, and it was placed by the parent task, not by this task.
- Full JSON-LD: NOT fully verified for this product in this run. The page render exposes a JSON-LD Product.offers block (price 1.00 CAD, availability InStock); the full raw JSON-LD type list was not visible in the text fetch, so no broader JSON-LD claim is made here.
- No MCP, ACP, or UCP compliance is claimed. No consumer Muse discovery is claimed. No live customer payment is claimed.
