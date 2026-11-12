#!/usr/bin/env python3
"""Stripe secret key, from the environment only.

The Stripe secret key lives in secure storage, never in code
and never in logs. This module reads it from the environment
at the point of use. When it is not set, the call fails with a
clear message instead of guessing. No live Stripe call is made
in this phase: billing records and bills from OvO's own
records, and the key is read only when a live Stripe call is
about to happen. The value is never returned to a caller that
would log it, and never appears in an error message.
"""
import os


def stripe_secret_key():
    """The Stripe secret key, or an error when it is not set."""
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise RuntimeError(
            "Stripe secret key is not set. Set STRIPE_SECRET_KEY in"
            " the host settings store. The key is never stored in"
            " code or in a file.")
    return key


def stripe_configured():
    """True when a Stripe secret key is present in the
    environment. Says nothing about the key itself."""
    return bool(os.environ.get("STRIPE_SECRET_KEY"))
