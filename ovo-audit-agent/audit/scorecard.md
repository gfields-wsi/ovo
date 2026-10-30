# Sole Mates audit scorecard — Stream 1

Store: https://wsiventures.com/solemates
Date: 30 October 2026
Source: the live Store API, using the rest_route form.
Products checked: 12.

## Scores, kept separate

Native store core score: 66.7 percent (120 of 180 checks).
Post-OVO core score, projected: 86.7 percent (156 of 180 checks).
The post-OVO score is a projection only. It is not the store's own score.
It counts only enrichment that comes from the store's own prose.

Native store full field coverage: 50.0 percent (120 of 240 checks).
Post-OVO full field coverage, projected: 65.0 percent (156 of 240 checks).

## What passes today

Every product has a name, a SKU, a price in Canadian dollars, and a stock flag.
Every product has size options, a colour, a category, and a short description.
Every product has a long description and one image.
Every product is in stock by the boolean flag only.

## What fails today

Material, fit, and returns are in description prose for all 12 products.
They are not structured fields, so an agent cannot read them as fields.
That is 36 gaps, and all 36 can be fixed from the store's own prose.

Weight and dimensions are missing for all 12 products.
Image alt text is empty for all 12 products.
Tags and brand are empty for all 12 products.
No numeric stock quantity is given for any product. The API gives a boolean only.
No GTIN is given for any product.

One extra gap is on Trailhead only. Its description mentions wide fit in store only.
No wide fit variation can be selected online, so an agent must not offer it online.

Shipping and tax are store level gaps. They are not in the product record.
They are checkout level values, so this audit does not invent them.

## Untrusted text

No untrusted text was flagged in this live snapshot.
The scan checked for instruction text, discounts, coupons, and payment overrides.
If a flag appears later, this stream flags it only. It does not follow it, and it does not remove it.

## Audit rule

This audit tracks gaps. It does not fill gaps.
It records what is needed or helpful, and what is not there.
Filling is Stream 2 work, and it needs merchant approval before any publish.

## What this audit does not claim

This audit does not claim full MCP, ACP, or UCP compliance.
It does not claim consumer Muse discovery, live payment, or production plugin compatibility.
It does not claim product JSON-LD is present or absent. That check is left unverified.
It does not invent any price, stock quantity, weight, dimension, tax, or shipping value.

## Gap file for Stream 2

File: gaps.json, in the same folder as this scorecard.
Format: ovo-gap-list, version 1.0.
Total gaps: 124. That is 120 per product field gaps, 1 Trailhead option gap, and 3 store level gaps.
Each gap has a product id, a field, a current value or missing value, a gap type, evidence from the store, and a source label.
Store level gaps use a null product id, so Stream 2 can filter them out.
