# ROAR licensing & entitlement architecture (offline verification built; gates OFF)

Offline license verification is implemented (real Ed25519), but **nothing in the
shipped app is gated** — the edition is displayed, not enforced. `entitlements.py`
holds the pure policy so that if paid editions ever ship, the rules below are
already pinned by tests and can't drift.

## Non-negotiable policy

- Core (free) forever includes: push-to-talk + hands-free dictation, streaming
  preview, multilingual dictation, scratch-that undo, basic spoken commands,
  basic history, ALL privacy controls, delete history/audio, basic vocabulary,
  safe diagnostics, and the manual update check.
- Privacy and local-data controls are allowed in every edition, unconditionally.
- Licensing code never reads transcripts, audio, history, snippets, vocabulary,
  clipboard, or diagnostics, and never touches the network.
- Missing, corrupt, or unknown license/edition degrades to Core — never a crash,
  never a nag loop.
- Paid tiers unlock workflow power only: Pro (advanced milestones, smart
  formatting, snippet packs/extended variables, vocabulary suggestions, history
  filters, advanced cleanup, settings import/export) and Developer (code mode,
  symbol dictation, app profiles, per-app language/mode, project vocabulary,
  file tagging, developer snippet packs). Supporter includes everything.

## Offline validation (implemented)

**License format.** A license is a small JSON document:

```json
{
  "license_id": "ROAR-PRO-XXXX",
  "name": "Customer Name",
  "email_hash": null,
  "edition": "pro",
  "issued_at": "2026-07-06",
  "valid_for_major": 1,
  "signature": "base64_ed25519_signature"
}
```

**Signature.** Ed25519 over `canonical_bytes(payload)` — the payload minus its
`signature`, JSON with sorted keys and compact separators, UTF-8. Verification
is done by a `SignatureVerifier` (`CryptographySignatureVerifier`, backed by the
`cryptography` library).

**Keys.** Only the **public** key ships, in
`commercial_config.LICENSE_PUBLIC_KEY_PEM`. The **private** key never lives in
the repo or the installer — it is read from the environment by
`scripts/dev_generate_license.py` (dev) or a secret manager (production).

**Fully offline.** Validation makes no network calls. `license.py` imports no
transcript/audio/history/vocabulary/clipboard/network module.

**Fail closed to Core.** Missing, corrupt, malformed, unsigned, bad-signature,
unsupported-edition, wrong-major, and dev-rejected all return Core, `valid=False`
— never a crash, never a nag loop. Fields are **not trusted until the signature
verifies**.

**Production safety.** In a production build (`commercial_config.IS_PRODUCTION =
True` with the real public key swapped in), dev-signed licenses (`env == "dev"`)
are rejected (`reason="dev_rejected"`), and the dev key mismatch rejects them by
signature anyway.

**Test cases.** See `tests/test_license.py` (valid Pro/Developer/Supporter, bad
signature, wrong key, malformed, missing signature, unsupported edition, wrong
major, huge/empty/corrupt input, dev-rejected-in-production, no-network imports)
and `tests/test_commercial_privacy.py`.

## What exists in the repo today

- `entitlements.py` — pure feature policy + canonical vocabulary (tested).
- `license.py` — real offline Ed25519 verification behind a `SignatureVerifier`
  interface; fail-closed to Core; no keys, no network, no user data.
- `commercial_config.py` — pricing/URLs/support + bundled public key.
- **No runtime gates and no edition UI enforcement.** The app still behaves as
  "everything on"; the edition is displayed only. Turning on any gate is a
  separate, later decision (existing users grandfathered).
