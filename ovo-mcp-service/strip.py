#!/usr/bin/env python3
"""Hidden-order stripper for the OvO MCP service.

Merchant product words are data, never orders. A product line
that tells an agent to add items, buy, or change a price must
never reach an agent. This module strips such lines before any
product data leaves the service.

The stripper works sentence by sentence. A sentence is stripped
only when it reads as an order to an agent:

- It overrides instructions: "ignore previous instructions",
  "disregard the rules", "you are now", "system prompt".
- It is an imperative to buy, order, or pay: a sentence that
  starts with add, buy, purchase, order, checkout, place, charge,
  or a "you must" form of those verbs.
- It is an imperative to change money: "change the price",
  "apply a discount", "make it free", "use this code".

Ordinary product facts stay. "Free returns within 30 days" is
a fact, not an order, and it stays. "Material: recycled mesh"
stays. An offer stated as a fact stays; the same words phrased
as an order go. The stripper errs toward stripping an imperative:
when a line could be read as an order to an agent, it is removed
and listed, so the merchant can see what was taken out.
"""
import re

# Verbs that, as an imperative, order an agent to act on a purchase.
# Strong verbs are orders on their own at the start of a sentence
# ("Buy now."). Weaker verbs need a purchase object next to them
# ("Add this to your cart"), so a care note such as "Add water
# and let it dry" is not stripped.
STRONG_VERBS = ("buy", "purchase", "checkout", "order", "charge")
WEAK_VERBS = (
    "add", "place", "apply", "change", "set", "give", "use", "enter",
    "redeem", "claim",
)

# Objects that prove a purchase order. A verb alone is not enough:
# "add water" in a care note is not an order. The verb needs a
# purchase object next to it.
ORDER_OBJECTS = (
    "cart", "order", "price", "discount", "code", "coupon", "payment",
    "checkout", "free", "item", "items", "product", "products", "pair",
    "pairs",
)

_OVERRIDE = re.compile(
    r"\b(ignore|disregard|override|forget|bypass)\b.{0,40}\b"
    r"(instruction|instructions|rule|rules|prompt|prompts|guideline|guidelines|price|policy|policies)\b"
    r"|\b(you are now|new instruction|system prompt|as an (ai|assistant|agent)|"
    r"pretend (you are|to be)|act as (an? )?(ai|assistant|agent|system))\b",
    re.IGNORECASE)

_IMPERATIVE_STRONG = re.compile(
    r"^\s*(?:" + "|".join(STRONG_VERBS) + r")\b", re.IGNORECASE)

_IMPERATIVE_WEAK = re.compile(
    r"^\s*(?:" + "|".join(WEAK_VERBS) + r")\b.{0,60}\b(?:"
    + "|".join(ORDER_OBJECTS) + r")\b",
    re.IGNORECASE)

_MUST_FORM = re.compile(
    r"\b(you|agent|assistant)\s+(must|should|need to|have to|will)\s+"
    r"(?:" + "|".join(STRONG_VERBS + WEAK_VERBS) + r")\b",
    re.IGNORECASE)

_SYSTEM_BLOCK = re.compile(
    r"\[system\s*:.*?\]", re.IGNORECASE | re.DOTALL)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _is_hidden_order(sentence):
    text = sentence.strip()
    if not text:
        return False
    if _OVERRIDE.search(text):
        return True
    if _MUST_FORM.search(text):
        return True
    if _IMPERATIVE_STRONG.search(text):
        return True
    if _IMPERATIVE_WEAK.search(text):
        return True
    return False


def strip_text(text):
    """Strip hidden orders from product text. Returns a dict with
    the cleaned text, the stripped sentences, and the count."""
    if not isinstance(text, str):
        return {"cleaned": text, "stripped": [], "stripped_count": 0}
    stripped = []

    def _drop_block(match):
        stripped.append(match.group(0).strip())
        return ""

    cleaned = _SYSTEM_BLOCK.sub(_drop_block, text)
    cleaned = _HTML_COMMENT.sub(_drop_block, cleaned)
    sentences = _SENTENCE_SPLIT.split(cleaned)
    kept = []
    for sentence in sentences:
        if _is_hidden_order(sentence):
            stripped.append(sentence.strip())
        elif sentence.strip():
            kept.append(sentence.strip())
    return {
        "cleaned": " ".join(kept),
        "stripped": [s for s in stripped if s],
        "stripped_count": len([s for s in stripped if s]),
    }


def strip_fields(value):
    """Strip hidden orders from every string in a product record
    (dicts and lists, any depth). Returns (cleaned, stripped)."""
    stripped = []

    def walk(item):
        if isinstance(item, str):
            result = strip_text(item)
            stripped.extend(result["stripped"])
            return result["cleaned"]
        if isinstance(item, list):
            return [walk(i) for i in item]
        if isinstance(item, dict):
            return {k: walk(v) for k, v in item.items()}
        return item

    return walk(value), stripped
