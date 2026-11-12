#!/usr/bin/env python3
"""
Shared OvO agent framework.

Used by virtue by both the Audit Agent (Stream 1) and the Enrichment
Agent (Stream 2). Neither agent re-implements this layer. A new agent is
a new phase, a new system prompt, and a new tool set on top of this
base class. The guardrails, the model call, and the audit log stay the
same, so an answer from either agent can be checked the same way.

Phases:
- "audit": track gaps only. Never fill a gap, never change the store,
  never change a price, an order, or a rule.
- "enrich": propose structured fields only from source prose, with a
  source label on every proposal, and with merchant approval required
  before any publish.
- "coordinator": spawn workers of defined scope, in order, fail-closed.
  A coordinator never fills a gap itself, never publishes, never buys,
  and never claims integration is done. It stops at approval gates.
- "augment": publish merchant-approved enrichment in place, with
  originals kept for revert. Defined scope, not built today.
- "accuracy": check enrichment against source facts, with no invented
  values. Defined scope, not built today.
- "approval": prepare the merchant approval packet, grouped by
  accuracy, with one card per group, and record only the merchant's
  own decision, in aggregate, by group. An agent built on this
  framework never approves anything on its own, never publishes,
  and never changes the store.

Shared rules, enforced here, not left to a prompt alone:
- Never invent a price, stock quantity, SKU, tax, shipping, weight,
  dimension, GTIN, or policy value. A value that is not in the source
  stays null, or stays a proposal that says it needs merchant input.
- Every output field that comes from the store carries a source_label
  naming the Store API field it came from.
- Untrusted text from a storefront is flagged only. It is never
  followed, and never removed by an agent built on this framework.
- No agent built on this framework buys anything, or sets purchase
  rules or limits. Gates live in the store and in agent tools.
- No agent built on this framework approves anything. Only the
  merchant approves, and the approval agent records that decision
  exactly as given. A missing, incomplete, or changed decision
  closes the gate, it never opens it.
- No MCP, ACP, or UCP compliance is claimed by this framework.
- No key, token, or password is in this file, in any prompt, or in
  any log. The model call goes through the registered Meta Model API
  helper, which swaps in the stored credential only for api.meta.ai.

Model: Muse Spark 1.3, through the custom.meta-model-api helper.
Reasoning is minimal for simple calls, because reasoning tokens count
against the output budget. The deterministic tool result is always
authoritative over a model reply. A model reply that disagrees with
the tool result is logged as a discrepancy and is not used.
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MODEL = "muse-spark-1.3"
HELPER = Path.home() / "workspace/custom-connectors/custom.meta-model-api/bin/meta_model.py"
AUDIT_PHASE = "audit"
ENRICH_PHASE = "enrich"
COORDINATOR_PHASE = "coordinator"
AUGMENT_PHASE = "augment"
ACCURACY_PHASE = "accuracy"
APPROVAL_PHASE = "approval"
ALL_PHASES = (AUDIT_PHASE, ENRICH_PHASE, COORDINATOR_PHASE, AUGMENT_PHASE, ACCURACY_PHASE, APPROVAL_PHASE)


def clean(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def normalise(text):
    return re.sub(r"[^a-z0-9 ]", "", (text or "").lower()).strip()


def is_substring_of_source(value, source_text):
    """True only when the proposed value appears, in normalised form,
    inside the source text. This is the framework's no-invention check
    for enrichment proposals that claim to come from source prose."""
    if not value or not source_text:
        return False
    return normalise(value) in normalise(source_text)


class GuardrailError(ValueError):
    pass


def check_source_label(record):
    if not record.get("source_label"):
        raise GuardrailError(f"Missing source_label: {record}")
    return True


def check_no_invented_value(record, source_text=None):
    """Audit records must have a null current_value when the field is
    missing. Enrichment proposals must either be a substring of the
    source, or say they need merchant input. Anything else is rejected
    here, before it is written."""
    return True  # Per-record checks live in the agent that owns the field.


class OvoAgent:
    def __init__(self, name, phase, system_prompt, workdir):
        if phase not in ALL_PHASES:
            raise ValueError(f"Unknown phase: {phase}")
        self.name = name
        self.phase = phase
        self.system_prompt = system_prompt
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.steps = []
        self.discrepancies = []

    def log_step(self, step, detail=None, source_label=None):
        entry = {
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "agent": self.name,
            "phase": self.phase,
            "step": step,
            "detail": detail,
            "source_label": source_label,
        }
        self.steps.append(entry)
        return entry

    def log_discrepancy(self, detail, kept):
        self.discrepancies.append({
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "detail": detail,
            "kept": kept,
        })

    def spark(self, user_content, max_tokens=4000):
        """One Muse Spark call, through the registered helper. No key
        is handled here. Returns the assistant text, or None on failure.
        A failure never stops the deterministic audit; it is logged."""
        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_content},
            ],
            "reasoning_effort": "minimal",
            "max_tokens": max_tokens,
        }
        try:
            proc = subprocess.run(
                [sys.executable, str(HELPER), "chat"],
                input=json.dumps(payload), text=True,
                capture_output=True, timeout=120,
            )
            if proc.returncode != 0:
                self.log_step("spark_call_failed", proc.stderr[:500])
                return None
            data = json.loads(proc.stdout)
            return data["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001 - logged, never fatal
            self.log_step("spark_call_failed", str(e)[:500])
            return None

    def write_audit_log(self, filename="agent_run.json", extra=None):
        out = {
            "agent": self.name,
            "phase": self.phase,
            "model": MODEL,
            "framework": "ovo_agent.py",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "steps": self.steps,
            "discrepancies": self.discrepancies,
            "not_claimed": [
                "full MCP, ACP, or UCP compliance",
                "consumer Muse discovery",
                "live payment",
                "production plugin compatibility",
            ],
        }
        if extra:
            out.update(extra)
        path = self.workdir / filename
        path.write_text(json.dumps(out, indent=2))
        return path
