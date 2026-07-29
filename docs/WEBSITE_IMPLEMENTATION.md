# Website implementation notes

## Today

`site/` is plain static HTML deployed to GitHub Pages by
`.github/workflows/pages.yml` (`path: site`). There is **no server, no
serverless function, and no build step**. Checkout therefore uses Stripe
Payment Links — see `docs/STRIPE_SETUP.md` — which need no backend.

Files:

- `site/index.html` — the whole marketing page, including the pricing cards and
  a single `ROAR` config block that owns every commercial link.
- `site/purchase/success.html` — the Payment Link redirect target. Static, with
  no script: it must never read a query parameter and treat it as proof of
  payment.

## If the site ever moves to a host with functions

Only then do the server-side pieces become possible. Recording the contract here
so the decision does not have to be re-derived.

### POST /api/checkout

- Accept POST only; reject other verbs with 405.
- Body: `{"edition": "pro" | "developer" | "supporter"}` — the browser sends an
  **edition id and nothing else**. Never accept a price, an amount, or a Stripe
  Price ID from the client.
- Reject unknown editions and `core`.
- Map the edition to a Price ID held in server-side environment variables:
  `STRIPE_PRICE_PRO`, `STRIPE_PRICE_DEVELOPER`, `STRIPE_PRICE_SUPPORTER`.
  Reject the call when the mapping is missing rather than falling back.
- Create the session with `mode: "payment"` (never a recurring mode),
  quantity 1, success and cancel URLs built from `PUBLIC_SITE_URL`, and
  metadata `{product: "roar", edition, license_major: "1"}`.
- Send no transcripts, machine identifiers, history, or application
  configuration to Stripe.
- Return a generic error message to the browser, and log no secrets.

### POST /api/stripe/webhook

- Verify the Stripe signature against `STRIPE_WEBHOOK_SECRET` using the **raw**
  request body; reject anything that fails signature verification.
- Handle `checkout.session.completed`, and optionally `charge.refunded`.
- Be idempotent on the Checkout Session id: store processed event ids so one
  sale can never mint two licences.
- Re-validate the edition from the session metadata — never trust it blindly.
- Only then call the fulfilment boundary (`fulfillment.issue_license`).

### Environment (server-side only)

```env
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_PRO=
STRIPE_PRICE_DEVELOPER=
STRIPE_PRICE_SUPPORTER=
PUBLIC_SITE_URL=https://example.com
```

`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and the licence **signing key**
must never reach the browser, the desktop app, or this repository. Only a
publishable key may ever be exposed to a page, and this design does not need
one.

## Invariants the website must keep

- Core is free and prominent; the download never sits behind a payment.
- No account, no login, no cloud transcription, no telemetry, no subscription.
- Privacy controls, history deletion, and audio deletion are never presented as
  paid features.
- The success page never claims a licence has already been sent.
- Prices shown on the site match `PRICING` in `commercial_config.py`;
  `tests/test_site_pricing.py` and `tests/test_pricing_docs.py` enforce it.
