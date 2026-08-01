# Automated licence fulfilment on Vercel (PayPal → licence email) — Design

**Date:** 2026-08-01 · **Status:** approved (user: "yes", dual-key confirmed;
autonomous build) · **Repo:** `xhan145/roar`

## Goal

When a buyer completes a PayPal payment for Pro/Developer/Supporter, a Vercel
function verifies the payment, signs a licence, and emails it — no human in the
loop for the happy path. Manual issuance stays as the fallback and for refunds.

## The key decision (user-approved): dual-key

- The **founder key** stays offline-only in `~/.roar-signing/
  roar_license_private_key.pem`. Nothing about it changes.
- A new **fulfilment keypair** was generated
  (`~/.roar-signing/roar_fulfillment_private_key.pem`); its PRIVATE half goes
  ONLY into Vercel env vars; its PUBLIC half ships in the app.
- The app accepts licences signed by EITHER key
  (`commercial_config.LICENSE_PUBLIC_KEYS`, founder first). If the Vercel key
  is ever compromised: remove its public key in an app update, reissue the
  affected licences from the founder key. Founder-signed licences are never at
  risk.
- Fulfilment public key:
  `MCowBQYDK2VwAyEA5V8lZZEUi5X19S9OpbrrVZju5hNcrqyAFaf+zQbjxcM=`

## Part A — app change (dual-key verification)

`license.py` gains `MultiKeyVerifier` (list of `CryptographySignatureVerifier`;
valid iff ANY key verifies; fail-closed). `_default_verifier()` builds it from
`commercial_config.LICENSE_PUBLIC_KEYS = (FOUNDER_PEM, FULFILLMENT_PEM)`;
`LICENSE_PUBLIC_KEY_PEM` stays as the founder alias. Everything else
(env:"dev" rejection in production, schema/major checks) is unchanged and must
keep passing. Ships in the next app release — buyers always download the
latest installer, so new fulfilment-signed licences will validate.

## Part B — fulfilment service (`fulfillment-service/` in this repo)

Node 18+ Vercel functions; **zero npm dependencies** (node:crypto does Ed25519,
fetch does HTTP). Public code, secrets only in env.

- `api/paypal-webhook.js` — POST handler:
  1. Verify the webhook via PayPal `POST /v1/notifications/
     verify-webhook-signature` (env: `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET`,
     `PAYPAL_WEBHOOK_ID`, `PAYPAL_API_BASE` for sandbox/live). Reject anything
     unverified with 400. NEVER trust the event body alone.
  2. Accept only `PAYMENT.CAPTURE.COMPLETED`, status COMPLETED, currency USD,
     and an amount that maps EXACTLY to an edition: 19.00→pro, 29.00→developer,
     49.00→supporter. Anything else: log row with status "ignored", 200.
  3. Idempotency: insert the PayPal capture id into Supabase
     (`roar_licenses`, capture_id UNIQUE) BEFORE signing; a conflict means
     already fulfilled → 200, no second licence.
  4. Sign the licence: same payload shape as `scripts/issue_license.py`
     (schema_version, license_id `ROAR-W-<12 hex>`, edition, customer name +
     sha256(email) hash, issued_at, valid_for_major=1, signature) using
     `FULFILLMENT_PRIVATE_KEY_PEM` from env via node:crypto Ed25519.
  5. Email the buyer via Resend (env: `RESEND_API_KEY`, `FULFILLMENT_FROM`)
     with the licence attached as `roar-license-<edition>.json` + activation
     steps; BCC the owner (`OWNER_EMAIL`). Store the licence JSON + txn id in
     the Supabase row (status "issued").
  6. Any failure after idempotency insert → row status "failed" + owner alert
     email; respond 500 so PayPal retries; the insert-first design plus
     UPSERT-on-retry keeps retries safe (a retry may complete a "failed" row,
     never duplicate an "issued" one).
- `lib/canonical.js` — byte-exact port of `license.canonical_bytes`
  (sorted keys, compact separators, UTF-8, signature key excluded). Proven by
  a fixture generated from Python (see testing).
- `lib/sign.js`, `lib/paypal.js`, `lib/supabase.js`, `lib/email.js` — thin,
  fetch-based.
- `vercel.json` — functions config; Vercel project Root Directory =
  `fulfillment-service`.

Storage: the existing Supabase project (same one ScratchEdge/Collective use is
NOT reused — a table in ANY of the user's Supabase projects works; docs default
to creating table `roar_licenses` wherever the user prefers; service key in
Vercel env only).

## Env vars (Vercel only, never committed)

`PAYPAL_CLIENT_ID`, `PAYPAL_SECRET`, `PAYPAL_WEBHOOK_ID`, `PAYPAL_API_BASE`,
`FULFILLMENT_PRIVATE_KEY_PEM`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`,
`RESEND_API_KEY`, `FULFILLMENT_FROM`, `OWNER_EMAIL`.

## Privacy

The service handles: buyer name (PayPal-provided), buyer email, amount, capture
id. It stores name, email-hash + email (needed for resend/support), edition,
licence JSON, timestamps. It never sees or touches app data. The app remains
fully offline; nothing app-side phones this service.

## Testing

- Python: multi-key verifier matrix (founder-signed ok, fulfilment-signed ok,
  unknown-key rejected, dev-in-production still rejected, empty list closed);
  packaging test keeps both PUBLIC keys in and every private key out;
  fixture generator writes `fulfillment-service/test/fixtures/canonical.json`
  (payload → canonical string → signature with a TEST keypair + its public
  key DER) so JS can prove byte-parity.
- Node (`node --test`): canonicalization equals the Python fixture byte-for-
  byte; sign→verify round trip; webhook handler unit tests with injected fakes
  (bad signature → 400 + no side effects; wrong amount → ignored; duplicate
  capture → single licence; Resend failure → 500 + failed row); amount→edition
  map exhaustive.
- End-to-end dry run happens in PayPal sandbox after the user provisions env
  (documented, not automatable from here).

## Rollout order

1. Ship the dual-key app release (buyers' installers must trust the new key
   before it ever signs anything real).
2. User provisions: Vercel project (root `fulfillment-service`), env vars
   (private key PEM from `~/.roar-signing/roar_fulfillment_private_key.pem`),
   Supabase table, PayPal webhook (sandbox first), Resend domain.
3. Sandbox dry run per docs; then flip `PAYPAL_API_BASE` to live.

## Out of scope

Automated refunds/revocation, Stripe webhooks (contract already documented),
customer portal, license re-download page.
