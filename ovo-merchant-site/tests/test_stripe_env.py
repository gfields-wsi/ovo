#!/usr/bin/env python3
"""Tests for the Stripe key rule: the key lives in the
environment only, never in code or logs. When it is not set,
the call fails with a clear message. No live Stripe call is
made here."""
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE.parent
sys.path.insert(0, str(SITE))

import stripe_env  # noqa: E402


class StripeEnvTest(unittest.TestCase):
    def setUp(self):
        self.saved = os.environ.pop("STRIPE_SECRET_KEY", None)

    def tearDown(self):
        if self.saved is not None:
            os.environ["STRIPE_SECRET_KEY"] = self.saved
        else:
            os.environ.pop("STRIPE_SECRET_KEY", None)

    def test_unset_key_fails_with_clear_message(self):
        self.assertFalse(stripe_env.stripe_configured())
        with self.assertRaises(RuntimeError) as ctx:
            stripe_env.stripe_secret_key()
        self.assertIn("not set", str(ctx.exception))
        self.assertIn("host settings store", str(ctx.exception))

    def test_set_key_is_read_and_never_in_an_error(self):
        os.environ["STRIPE_SECRET_KEY"] = "sk_test_example"
        self.assertTrue(stripe_env.stripe_configured())
        self.assertEqual(stripe_env.stripe_secret_key(), "sk_test_example")


if __name__ == "__main__":
    unittest.main()
