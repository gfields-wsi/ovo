# OvO merchant site

The merchant side of OvO. A merchant signs in here, reviews the
fixes the Enrichment Agent drafted for their store, approves a
group, and presses Install OvO Plugins once. OvO then handles
the plugin download and activation. The monthly bill lists paid
orders only, at the rate in force when each order was paid.

## What is in this folder

- `store.py` — one SQLite store for merchants, sessions,
  sign-ins, packets, decisions, installs, rate changes, orders,
  read sessions, and carts. Tokens are stored as a hash only.
  WordPress passwords are never stored. Card numbers are never
  stored: only a reference, a brand, and the last four digits.
- `auth.py` — three separate sign-ins. OvO site sign-in with
  scrypt passwords and 24-hour session tokens. WordPress sign-in,
  verified against the store's own WordPress, transient only, and
  it must carry the install_plugins capability. Card
  authorization, recorded as a reference only, as the go-live
  gate for billing. The three are separate: card sign-in is not
  the same as WordPress sign-in.
- `approval.py` — builds the review packet from an enrichment
  diff and renders one review screen, a pop-up box, with the 62
  rows grouped the way the Merchant Approval Agent groups them.
  Records the merchant's decision per group. Silence never
  counts as approval: no group submitted means no record, and
  the Plugin Agent refuses to publish without a record.
- `install.py` — builds the plugin zip from
  `ovo-plugin-agent/ovo-enrichment/` and installs it on the
  store: signs in to the store's WordPress admin, uploads the
  zip, activates it, and proves it by reading the manifest.
  The WordPress password is used for one call only, never
  stored and never logged.
- `billing.py` — the rate on a switch: 1.5 percent by default,
  1 percent launch edition for the first 100 customers. The fee
  is fixed at the rate in force when the order was paid; a later
  rate change never changes an old fee. A refund gives no credit.
  The monthly bill lists paid orders only and is blocked until
  the card go-live gate passes.
- `attribution.py` — the link from agent session to cart to
  paid order. A read session, a cart carrying its session id,
  and a paid order carrying both ids. A human order with no
  link records a zero fee and is never billed. A session for
  one store never links an order on another store.
- `stripe_env.py` — reads the Stripe secret key from the
  environment only. When it is not set, the call fails with a
  clear message. No live Stripe call happens in this phase.
- `app.py` — one small HTTP app, standard library only. It
  serves the pages and the API the pages call. Run it with
  `python3 app.py` and set `OVO_MERCHANT_DB` and
  `OVO_MERCHANT_PORT` as needed. It listens on 127.0.0.1 by
  default. The pages under `static/` are plain files, so the
  same pages can deploy to the web server as static files and
  call this API on Render.
- `static/` — the review page styles and script.
- `tests/` — 71 tests. Run them from this folder with
  `python3 -m unittest discover -s tests`.

## How it deploys

The static pages go to the OvO marketing site on the existing
web server. The API runs on Render as the agent service, with
the same database the runner uses. The plugin zip is served by
download from the OvO site. Nothing here touches the live web
server or a live store.

## What still needs the pilot store

- A real merchant signing in.
- A real install on a real store.
- Real paid orders, agent and human, with the bill checked
  against the real orders.
- Live publish, which stays gated and is carried to Phase 8.

## Rules kept

- Store address required everywhere. No default store.
- No Accuracy Agent and no accuracy scorecard anywhere.
  Accuracy comes from the enrichment diff, per row.
- No key, password, or token in code, files, logs, or commits.
- The Stripe secret key lives in secure storage only.
- A session key for one store is refused on another store.
