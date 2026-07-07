# Checkout Setup

How to sell ROAR licenses. Start **manual**, automate later. ROAR itself never
talks to a payment processor — it only validates a signed license file offline.

## Options

- **Lemon Squeezy** — merchant of record; handles VAT/sales tax and refunds. Good
  default for a solo/small launch. Offers license-key issuance + webhooks.
- **Stripe** — maximum control; you are responsible for tax/VAT (or add Stripe
  Tax). Use Payment Links first, webhooks later.
- **Paddle** — merchant of record like Lemon Squeezy; strong tax handling.

Any of these can trigger a webhook that generates and emails a signed ROAR
license.

## Why manual fulfillment first

For a first small (beta) cohort, you can fulfill by hand: take payment via a
Payment Link, then run `scripts/dev_generate_license.py` (with the **production**
private key from your secret manager, not the repo) and email the license file.
This proves the whole path before you build automation.

## Later: webhook-based license generation

1. Processor fires a webhook on successful payment.
2. A small server-side function loads the **private** signing key from a secret
   manager (never the repo), builds the payload (`edition`, `valid_for_major`,
   etc.), signs `canonical_bytes(payload)` with Ed25519, and emails the license.
3. The app validates that license **offline** with the bundled public key.

## Signing key safety

- The **private** key never lives in the repo, the app, or client machines.
- Store it in a secret manager / environment variable on the fulfillment side.
- Ship only the **public** key in `commercial_config.LICENSE_PUBLIC_KEY_PEM`.
- Rotating the key invalidates old licenses — plan a migration if you rotate.

## Test purchase checklist

- [ ] Make a real test purchase end-to-end.
- [ ] Confirm the emailed license imports and shows the right edition.
- [ ] Confirm `verify_license_file.py` reports `valid=True`.
- [ ] Confirm a tampered license is rejected (Core).

## Refunds & support

- Refunds: follow [REFUND_POLICY.md](REFUND_POLICY.md); process through the
  processor's dashboard.
- Support: [SUPPORT.md](SUPPORT.md); never request transcripts or audio.
