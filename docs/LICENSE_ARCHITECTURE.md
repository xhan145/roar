# ROAR License Architecture

Offline, signed, public-key-verified license keys. No account, no server, no
network. This is the canonical architecture doc; [LICENSING.md](LICENSING.md) is
the shorter policy summary.

## Model
- **Buy once, use forever.** One-time payment; no subscription.
- A license is a small **signed document** the user imports. Validation is 100%
  **local and offline** — ROAR never phones home.
- The app **fails closed to Core** on any license problem and never crashes.

## License format
JSON, tiny, e.g.:
```json
{
  "license_id": "ROAR-PRO-XXXX",
  "name": "Customer Name",
  "email_hash": null,
  "edition": "pro",
  "issued_at": "2026-07-07",
  "valid_for_major": 1,
  "env": "prod",
  "signature": "base64_ed25519_signature"
}
```
Editions: `core | pro | developer | supporter`.

## Signature + verification (public-key, local)
- **Ed25519** over `canonical_bytes(payload)` — the payload minus `signature`,
  JSON with sorted keys and compact separators, UTF-8 (`license.canonical_bytes`).
- The app ships **only the PUBLIC key** (`commercial_config.LICENSE_PUBLIC_KEY_PEM`).
  The **PRIVATE key never lives in the repo, the installer, or a client machine** —
  it stays in a secret manager on the fulfillment side.
- Verification is done by a `SignatureVerifier` (`CryptographySignatureVerifier`).
  Fields are **not trusted until the signature verifies**.

## Fail-closed behavior (all → Core, `valid=False`, never raise)
`missing · corrupt · malformed · unsigned · bad_signature · unsupported_edition ·
wrong_major · dev_rejected`. If the crypto backend is unavailable, the app still
runs as Core.

## Major-version upgrade policy
- `valid_for_major` pins the license to a major version.
- A license for major **N** unlocks **all v N.x** updates.
- A future **v2** may be a separate one-time purchase, but **purchased versions
  keep working** — a v1 license keeps unlocking v1.x forever.
- A license whose `valid_for_major` ≠ the running major degrades to Core
  (`reason="wrong_major"`) — the app keeps working, just ungated for the new major.

## Dev-license restrictions (production safety)
- In a production build (`commercial_config.IS_PRODUCTION = True` + the real
  public key), any license with `env == "dev"` is **rejected**
  (`reason="dev_rejected"`), and dev-key-signed licenses fail signature anyway.
- `scripts/dev_generate_license.py` is a **developer tool** — reads the private
  key from the environment, prints a "local testing only" banner, refuses to run
  inside a packaged app, and is never imported by the app.
- `scripts/verify_license_file.py` verifies a license offline for support/debug.

## What licensing must NEVER touch
`license.py` / `entitlements.py` import **no** transcript/audio/history/vocabulary/
clipboard/network module. A paid license never inspects user dictation data.
Privacy controls and history/audio deletion are **free in every edition**.

## Test cases (see `tests/`)
`test_license.py`: valid Pro/Developer/Supporter · bad signature · wrong key ·
malformed · missing signature · unsupported edition · wrong major · huge/empty/
corrupt input · **dev-license rejected under a production verifier** · no-network
imports. `test_entitlements.py`, `test_commercial_privacy.py`: policy invariants +
no user-data imports + copy hygiene.

## Production go-live checklist
1. Generate the production Ed25519 keypair; private key → secret manager.
2. Swap `LICENSE_PUBLIC_KEY_PEM`; set `IS_PRODUCTION=True` in the release build.
3. Confirm dev-signed licenses are rejected; confirm a real license validates
   offline and unlocks the right edition.
4. Never commit a private key; `requirements-directml.txt`-style opt-in files stay
   out of the default install.
