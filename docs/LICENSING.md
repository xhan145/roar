# ROAR licensing & entitlement architecture (design — not yet enforced)

Nothing in the shipped app is gated today. `entitlements.py` holds the pure
policy so that if paid editions ever ship, the rules below are already pinned
by tests and can't drift.

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

## Offline validation design (when implemented)

A license is a small signed document: `{edition, name, issued, license_id}`
plus a signature. Validation is fully offline: verify the signature against a
public key embedded in the app, then read the edition. Expiry is optional and
would gate updates, not the app.

**Deliberately not implemented yet:** Python's stdlib has no safe public-key
signature verification, and homemade crypto is worse than none. Real signing
requires adding a vetted dependency (`cryptography` Ed25519 or `PyNaCl`) at
which point: private keys live only in the issuer tooling (never the repo or
the installer), sample/dev licenses are rejected by key mismatch, and
`license.py` stays pure (bytes in → edition out).

## What exists in the repo today

- `entitlements.py` — pure feature policy (tested).
- `license.py` — pure edition/document primitives (always Core today; no
  crypto, no keys, no network).
- No gates, no edition UI. The app behaves as
  Supporter-with-everything because nothing checks entitlements yet.
