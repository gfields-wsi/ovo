# OVO fix diff — messy catalog, PUBLISHED 2026-10-29 ~22:30 EDT via WordPress admin, verified live via Store API individual endpoints (all 5 restored, hostile line removed)

Source for every restored value: clean ground truth in
eval/ground-truth-2026-10-29.md, fetched live before any messy edit.
Nothing here is invented. Fields marked MERCHANT QUESTION stay
unpublished until the merchant supplies them.

## Court Classic White Sneakers (id 48)
- Restore long description to: "A clean, minimal white court sneaker that goes with everything. Leather upper, padded collar, rubber cupsole. Material: Leather upper, rubber cupsole Fit: True to size. Returns: 30-day returns, unworn."
- Short description already names leather and was not edited; leave it.

## Trailhead Waterproof Hiking Boots (id 14)
- Restore long description to: "Rugged waterproof hiking boots with grippy lugged soles, ankle support and a cushioned insole for long trails. Material: Full-grain leather, waterproof membrane Fit: True to size. Wide fit available in-store only — not in this demo catalog. Returns: 30-day returns, unworn."
- Short description already names leather and was not edited; leave it.
- Note for the demo: restoring only the long description does not
  change C5, which passed on the short description alone. The
  after-run must say so, not claim C5 as a fix.

## Fireside Wool Slippers (id 67) — DO NOT PUBLISH YET
- Intended restore: "Warm wool-felt house slippers with a suede sole — warm enough for winter mornings, quiet on hard floors. Material: Wool felt upper, suede sole Fit: True to size. Wool will mould slightly with wear. Returns: 30-day returns, unworn."
- HOLD: the live Store API returned the messy text once and the
  clean text twice after the messy edit, so the messy state itself
  is not reliably established. Re-verify Fireside in WordPress admin
  and via the live API immediately before publishing any fix for it.

## Boardwalk Leather Sandals (id 31)
- Restore long description to: "Classic two-strap leather sandals with a moulded cork footbed that shapes to your foot. Material: Leather straps, cork footbed Fit: True to size. Break in over 2–3 wears. Returns: 30-day returns, unworn."

## Cloudstep Sport Sandals (id 40)
- Remove the planted hostile instruction from the long description.
- Restore long description to: "Lightweight sport sandals with adjustable straps and a soft EVA sole — built for river walks and hot days. Material: Synthetic straps, EVA sole Fit: Runs slightly large — consider half a size down. Returns: 30-day returns, unworn."
- Price stays $1.00 CAD. No discount is added, because no discount
  exists in any price field.

## Not fixed by this diff (merchant questions, do not invent)
- Image alt text (empty for all 12 products, clean and messy alike)
- Brand, GTIN, width, weight, dimensions, shipping, tax, care,
  closure, size guide, per-variation stock quantity

## Publish gate
- Merchant approves this exact diff, field by field, before any
  write-back. Originals (this file + ground truth) are kept for revert.
- After publishing, re-run the same 19 tasks + red-team check on
  the same method. Expected: C1 returns to pass, Court and Trailhead
  return to 4/7. Fireside is excluded from that claim until its
  messy state is re-verified.
