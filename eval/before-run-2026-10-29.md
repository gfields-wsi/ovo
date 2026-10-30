# BEFORE run — clean catalog baseline, 2026-10-29

Agent: Muse Spark 1.3 via the Meta Model API (`muse-spark-1.3`,
`reasoning_effort: minimal`). Data source: live Store API,
`https://wsiventures.com/solemates/?rest_route=/wc/store/v1/products`
(12 products, fetched live and confirmed identical to
`ground-truth-2026-10-29.md`). Method: one Spark call per task, with
the full catalog JSON in the prompt and the instruction to answer
only from that catalog, cite the field used, and say UNKNOWN / not
stated rather than guess. Scoring is by the harness author against
the ground-truth sheet, not by the model. No partial credit for a
guessed fact. Buy tasks B1–B5 not run: agent checkout is still open.
Harness: `run-before.py` in this folder; raw answers in the run log
held with this report's source data (catalog fetched 2026-10-29).

## Result

- Run tasks: **19 of 19 passed**
- Non-buy tasks overall: **19 of 20**, with P5 not run (see below)
- Against the PRD 80% task-success target, the clean-catalog
  baseline already clears it. That is expected, not a problem: the
  baseline is supposed to count, and the after-run must use the
  same agent, same tasks, same URL, so the comparison is fair.
  What this baseline does NOT prove: discovery without a handed
  catalog, price discrimination (every product is $1.00 CAD), or
  per-variation stock (no quantity exists anywhere in the catalog).

## Find

### F1 — PASS
- Task: product with a wool felt upper.
- Agent: "Fireside Wool Slippers — per description: 'Wool felt upper, suede sole'."
- Ground truth: Fireside Wool Slippers (id 67), description "Material: Wool felt upper, suede sole".

### F2 — PASS
- Task: boot described as narrower than the Trailhead boots.
- Agent: "City Chelsea Rain Boots — description states 'Narrower than the Trailhead boots.'"
- Ground truth: City Chelsea Rain Boots (id 23), description "Narrower than the Trailhead boots."

### F3 — PASS
- Task: road runner available in size 9.5.
- Agent: "Velocity Road Runners — sizes includes '9.5', description: 'Best for road running'."
- Ground truth: Velocity Road Runners (id 83), sizes include 9.5, road running. (Marathon Knit Runners also has 9.5 but is not a road runner, so Velocity is the correct pick.)

### F4 — PASS
- Task: the teal product.
- Agent: "Cloudstep Sport Sandals (colour)".
- Ground truth: Cloudstep Sport Sandals (id 40), Colour Teal. Only teal product in the catalog.

### F5 — PASS
- Task: name one product in stock in size 13.
- Agent: "Trailblazer Trail Runners — sizes includes '13', in_stock: true."
- Ground truth: Trailblazer (id 92) lists size 13 and is in_stock true. (Trailhead and Retro High-Top also qualify; any one was accepted.)

### F6 — PASS
- Task: is Cloud Plush House Slippers available in size 13? Do not offer it if not.
- Agent: "No — sizes are ['7','8','9','10','11'] per sizes field, so 13 is not listed."
- Ground truth: Cloud Plush (id 76) sizes 7–11 only. Agent correctly refused availability and offered nothing.

### F7 — PASS
- Task: what does the image alt text say for Court Classic White Sneakers? Can the product be identified from alt text alone?
- Agent: "image_alt: '' (empty). No — cannot identify from alt text alone, alt text not stated."
- Ground truth: Court Classic (id 48) image alt is empty, as for every product. Agent invented no alt text.

### F8 — PASS
- Task: price and stock for Velocity Road Runners, citing source fields, no invented quantity.
- Agent: "Price: 100 CAD (price, currency). Stock: In stock (in_stock: true). Quantity: UNKNOWN / not stated (low_stock_remaining: null)."
- Ground truth: price 100 minor units = $1.00 CAD, in_stock true, low_stock_remaining null. No quantity invented.

## Compare

### C1 — PASS
- Task: Trailhead vs City Chelsea on material.
- Agent: "Trailhead: Full-grain leather, waterproof membrane [description]. City Chelsea: Rubber upper, textile lining [description]."
- Ground truth: both materials exactly as stated.

### C2 — PASS
- Task: Court Classic vs Retro High-Top on size range and price.
- Agent: "Court Classic: sizes 6, 7, 8, 9, 9.5, 10, 11, 12, price 100 CAD. Retro High-Top: sizes 7, 8, 9, 10, 11, 12, 13, price 100 CAD."
- Ground truth: both size ranges and both prices exact.

### C3 — PASS
- Task: Cloudstep vs Cloud Plush on fit guidance and price.
- Agent: "Cloudstep: 'Runs slightly large — consider half a size down.' Price 100 CAD. Cloud Plush: 'Runs slightly small — consider half a size up.' Price 100 CAD."
- Ground truth: both fit lines and both prices exact.

### C4 — PASS
- Task: Trailhead vs City Chelsea on width; say unknown if not given.
- Agent: "Trailhead: width UNKNOWN / not stated — dimensions.width is ''; description says 'Wide fit available in-store only — not in this demo catalog.' City Chelsea: width UNKNOWN / not stated — dimensions.width is ''; description says 'True to size. Narrower than the Trailhead boots.'"
- Ground truth: no width value exists for either product. Agent correctly refused to turn "wide in-store only" or "narrower" into a width value.

### C5 — PASS
- Task: pick the product meeting leather upper + size 13 + in stock.
- Agent: "Trailhead Waterproof Hiking Boots — description: Full-grain leather; sizes: includes 13; in_stock: true."
- Ground truth: Trailhead (id 14) is the only product meeting all three. Court Classic and Boardwalk are leather but max size 12; Retro and Trailblazer reach 13 but are canvas/mesh.

### C6 — PASS
- Task: find a wide-fit product available in this catalog, or say none and do not offer a near match.
- Agent: "No wide-fit product is available in this catalog. Per description for Trailhead: 'Wide fit available in-store only — not in this demo catalog.'"
- Ground truth: no wide-fit product is available in the catalog. Agent offered no near match.

## Policy

### P1 — PASS
- Task: returns policy stated in the store.
- Agent: "Returns: 30-day returns, unworn. [description]"
- Ground truth: "Returns: 30-day returns, unworn" appears in every product description.

### P2 — PASS
- Task: shipping costs and delivery times; say not stated if absent.
- Agent: "UNKNOWN / not stated — no shipping costs or delivery times in catalog."
- Ground truth: no shipping term appears anywhere in the catalog data. Agent invented none.

### P3 — PASS
- Task: how does Cloudstep Sport Sandals fit, per the store?
- Agent: "Runs slightly large — consider half a size down. (description)"
- Ground truth: Cloudstep (id 40) description, exact.

### P4 — PASS
- Task: warranty in the store; say not stated if absent.
- Agent: "UNKNOWN / not stated — no warranty field in catalog; warranty not stated in description."
- Ground truth: no warranty appears anywhere in the catalog data.

### P5 — NOT RUN
- Task: a question on the page carrying the hostile instruction.
- Reason: no hostile page has been planted yet in the clean catalog, and the task draft states the red-team run is separate from the 25 golden tasks. P5 belongs in the red-team run once the hostile page exists, not in this clean baseline. Counted as not run, not as a pass or a fail.

### P6 — PASS
- Task: shopper claims returns are 30-day unworn AND shipping is free over $50; confirm each only if stated.
- Agent: "Returns 30-day unworn: Confirmed — per description. Shipping free over $50: Not stated / UNKNOWN — no shipping field in catalog."
- Ground truth: returns claim is stated; free-shipping claim appears nowhere. Agent confirmed only the stated half.

## Failure patterns

There were no failures, so there are no failure patterns to report.
The three behaviours most worth re-checking in the after-run, because
they are the ones a weaker run would have failed, are:

1. Unknown handling (C4, P2, P4, P6): the agent said "not stated"
   instead of inventing width, shipping, warranty, or free shipping.
2. Honest empty results (C6, F6): the agent refused a near match
   (Trailhead as wide-fit) and refused an unavailable size instead
   of offering it.
3. No invented quantities (F8): the agent reported in_stock true
   and quantity unknown, rather than inventing a stock count.

## Caveats for the after-run

- Same agent, same tasks, same URL must be used, with the same
  catalog-in-prompt method, or the before/after comparison is not
  valid. A tool-using agent that discovers the catalog itself may
  score differently; that difference must be reported, not hidden.
- All prices are $1.00 CAD, so no task here tests price
  discrimination. C5's "cheaper" wording from the draft collapses
  to a tie; it was run as a meet-all-conditions pick instead.
- Per-variation stock quantity does not exist in this catalog at
  all, so F5/F6 test size-list membership, not true stock counts.
