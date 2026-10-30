# OvO agent framework

One framework, used by virtue by the Audit Agent and the Enrichment Agent.

## What is shared

File: ovo_agent.py, class OvoAgent.

Shared parts:
- Muse Spark 1.3 calls, through the registered Meta Model API helper. No key is in code, prompts, or logs.
- Guardrails: no invented price, stock quantity, SKU, tax, shipping, weight, dimension, GTIN, or policy value. Every output carries a source label. Untrusted text is flagged only, never followed, never removed. No agent buys anything, or sets purchase rules or limits.
- Audit log: steps, discrepancies, model, and time, in agent_run.json form, so any answer can be reconstructed from its source fields.
- The no-invention check: a value that claims to come from source prose must appear in that prose, in normalised form, or it must say it needs merchant input.

## What is not shared

Phase, prompt, and tools. Those belong to each agent.

- Audit Agent (Stream 1, in stream1-audit/agent.py): phase audit. Tools: deterministic Store API audit, then a Spark verification pass. Output: gaps.json, format ovo-gap-list v1.0. It tracks gaps. It does not fill gaps.
- Enrichment Agent (Stream 2, not built here): phase enrich. Input: gaps.json v1.0, from the Audit Agent. Output: the enrichment diff format, as locked by the OvO Hackathon organizer. That diff format is not defined here, and it is not defined by Stream 1. Stream 2 implements enrichment on this same base class, with the same guardrails, the same Spark call, and the same audit log shape, and with merchant approval required before any publish.

## How to build a new agent on this framework

Make a new file, set a phase, write a system prompt, add tools, and call OvoAgent. Do not copy the Spark call, the guardrails, or the log code. Reuse them.

## What this framework does not claim

Full MCP, ACP, or UCP compliance. Consumer Muse discovery. Live payment. Production plugin compatibility. Those are not framework claims.
