# Automated fulfilment on Vercel (PayPal → licence email)

When a buyer completes a PayPal payment, a Vercel function verifies it with
PayPal, signs a licence with the SUBORDINATE fulfilment key, emails it to the
buyer, and records the sale. Manual issuance (`scripts/issue_license.py`)
remains the fallback and the refund path.

## The dual-key model (why this is safe to automate)

- The **founder key** (`~/.roar-signing/roar_license_private_key.pem`) never
  leaves that folder. Ever.
- The **fulfilment key** (`~/.roar-signing/roar_fulfillment_private_key.pem`)
  has its private half ONLY in Vercel env vars. The app (v0.35+) trusts both
  public keys (`commercial_config.LICENSE_PUBLIC_KEYS`).
- Compromise response: remove the fulfilment public key from the app in a
  release, rotate a new fulfilment keypair, reissue the (logged) fulfilment
  licences from the founder key. Founder licences are never affected.

## One-time setup (owner)

### 1. Supabase table (any of your projects)

```sql
create table roar_licenses (
  capture_id text primary key,
  status text not null default 'claimed',   -- claimed | signed | issued | failed
  edition text,
  buyer_email text,
  buyer_name text,
  license jsonb,
  error text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
alter table roar_licenses enable row level security;  -- no policies: service key only
```

### 2. Vercel project

- Import the `xhan145/roar` repo; set **Root Directory** to
  `fulfillment-service`. Framework preset: Other. Deploy.
- Env vars (Production):

| Var | Value |
|---|---|
| `PAYPAL_CLIENT_ID` / `PAYPAL_SECRET` | from developer.paypal.com → your app (SANDBOX first) |
| `PAYPAL_WEBHOOK_ID` | created in step 3 |
| `PAYPAL_API_BASE` | `https://api-m.sandbox.paypal.com` first; `https://api-m.paypal.com` when live |
| `PAYPAL_MERCHANT_ID` | your merchant id (PayPal → Account settings → Business information) — captures paid to anyone else are ignored |
| `FULFILLMENT_PRIVATE_KEY_PEM` | full contents of `~/.roar-signing/roar_fulfillment_private_key.pem` — used ONLY when `PAYPAL_API_BASE` is the live endpoint |
| `FULFILLMENT_SANDBOX_PRIVATE_KEY_PEM` | a THROWAWAY key for sandbox runs (generate: `python scripts/generate_keypair.py --out %TEMP%\sandbox_key.pem` and paste it; its public key is deliberately NOT trusted by the app, so play money can never mint a real licence) |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | the project holding `roar_licenses` |
| `RESEND_API_KEY` / `FULFILLMENT_FROM` | Resend key + verified sender, e.g. `ROAR <license@getroar.tech>` |
| `OWNER_EMAIL` | where sale BCCs and failure alerts go |

### 3. PayPal webhook

developer.paypal.com → your app → Webhooks → Add:
URL `https://<vercel-app>.vercel.app/api/paypal-webhook`, event
**Payment capture completed**. Copy the Webhook ID into
`PAYPAL_WEBHOOK_ID` and redeploy.

### 4. Sandbox dry run (do not skip)

1. With sandbox env vars set, pay a sandbox PayPal link for $19.00.
2. Confirm: Vercel logs show `issued ROAR-PRO-…`; the sandbox buyer email
   received the licence; `roar_licenses` has one `issued` row.
3. The sandbox licence must NOT activate in the app (it is signed by the
   throwaway sandbox key on purpose) — importing it should leave the app on
   Core. That failure IS the passing test: play money cannot mint real
   licences.
4. Fire the same webhook event again from PayPal's dashboard (Resend button):
   logs show `already fulfilled`, and the table still has ONE row.
5. Break `RESEND_API_KEY` on purpose, pay again: row goes `signed` then
   `failed`, the owner alert arrives, PayPal retries; fix the key and the
   retry emails the SAME stored licence and marks it `issued`.
6. Flip `PAYPAL_API_BASE` + client credentials + webhook to LIVE values. The
   first live sale should be your own $19 purchase; that licence (signed by
   the real fulfilment key) is the one to verify in the app.

## Ongoing operation

- Every sale: buyer gets the licence email; you get a BCC. No action needed.
- Failure alert email: check Vercel logs; PayPal retries webhooks for ~3 days.
  If it can't self-heal, verify the payment in the PayPal dashboard and issue
  manually — the `failed` row keeps the capture id for the record.
- Refunds: manual in PayPal; note it on the `roar_licenses` row. Licences
  can't be remotely revoked (validation is offline) — see REFUND_POLICY.md.
- The service stores buyer name/email/edition/licence — nothing from anyone's
  ROAR app, which never contacts this service.

## Guarantees enforced by tests

- JS canonical bytes are byte-identical to `license.canonical_bytes`
  (fixture from `scripts/make_fulfillment_fixture.py`).
- Unverified webhooks do nothing; wrong amounts/currencies mint nothing.
- One capture id → at most one licence, across any number of retries.
- Fulfilment-signed licences never carry `env:"dev"`.
