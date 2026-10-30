# OvO Audit Agent, segregated push

Audit Agent only, plus the shared framework it depends on. Other
OvO streams are not in this folder.

## Run

Run: python3 audit/agent.py
Fast run: python3 audit/agent.py --skip-spark
Audit any public store, no login: python3 audit/agent.py --store-url https://example.com/shop
Default store, when no URL is given, is Sole Mates at https://wsiventures.com/solemates.

## Output

gaps.json, format ovo-gap-list 1.0, pending organizer lock.
Audit tracks gaps only. It does not fill gaps, and it does not publish.

## Example scores, 30 October 2026, Sole Mates, 12 products

Native core 66.7 percent. Projected core 86.7 percent, if proposed
enrichment is approved. Live store unchanged until Augment publishes.

## Rules

- Never invent a price, stock quantity, weight, dimension, tax,
  shipping, GTIN, or policy value.
- Stock is reported as given by the store. A boolean stock flag is
  never turned into a numeric quantity.
- Untrusted text is flagged only. It is never followed, and never
  removed here.
- OVO does not buy, and does not set purchase rules or limits.
- No MCP, ACP, or UCP compliance is claimed.
