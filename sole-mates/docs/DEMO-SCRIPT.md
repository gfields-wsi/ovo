# Demo script — hero purchase

Use this for Demo 1 (Oct 29) and Demo 2 (Nov 2). It is the purchase the buying agent should be able to complete autonomously once the store is agent-ready.

## The ask

> "Buy me the Velocity Road Runners in size 9.5, in blue, for $1."

## Why this product

- Distinct from the other 11 products: the only electric-blue road runners, the only product with size 9.5 in blue
- Nuance an agent must resolve: size (9.5, not 9 or 10), colour (Electric Blue), type (Runners, not Sneakers), price ($1)
- Shippable, unlike the coffee example discussed at kickoff

## Expected flow

1. Agent finds Sole Mates, finds Velocity Road Runners (SKU `SM-RUN-001`)
2. Confirms: Electric Blue, size 9.5, $1 CAD, in stock (10)
3. Completes test checkout for $1
4. Returns a receipt / order confirmation

## Manual check (before the agent demo)

1. Shop > Runners > Velocity Road Runners
2. Select Size: 9.5, Add to Cart
3. Checkout in test mode, total $1
4. WooCommerce > Orders shows the $1 order

## Other good test asks

- "Find me waterproof boots in size 11" → Trailhead Waterproof Hiking Boots, Chestnut Brown
- "I need warm slippers, size 8" → Fireside Wool Slippers (grey) vs Cloud Plush House Slippers (navy) — agent must disambiguate by material / fit
- "Cheapest sandals in size 7" → both sandals are $1, so the agent must ask a follow-up (leather vs sport) rather than picking on price
