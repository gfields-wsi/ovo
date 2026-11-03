# OvO Harness setup — judge start, no key in the repository

1. Clone the repository and open the harness folder.
2. Run: python3 server.py 8000
3. Open http://localhost:8000
4. Press Run Before, then Run OVO, then Run After, in that order.
5. For approval, type a judge name and submit group 95 or greater.
6. For payment, use the merchant checkout link in test mode only,
   pay with a Stripe test card, and type the order number from
   the confirmation page into the harness.

No step needs WordPress admin access, plug-in activation, or a
pasted key. If a Meta call is needed on a host, set META_API_KEY
in host settings only. If no key is set on a host, Meta calls
fail plainly in the trace, and deterministic results are kept.
