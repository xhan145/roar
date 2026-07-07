# ROAR Commercial Scaffold — Design Spec

**Date:** 2026-07-06
**Component:** ROAR Desktop (Windows), repo `flowlocal` (github `xhan145/roar`)
**Current version:** 0.16.0 → target **v0.17.0**
**Mode:** `Complete scaffold` — **runtime feature gates stay OFF**. Build the
commercial foundation (docs, one canonical offline-signed licensing model, real
Ed25519 verification, diagnostics redaction, dev tooling, tests, a calm license
display). Remove nothing from current users. The feature matrix stays *policy*.

**Goal:** Move ROAR toward a sellable, trustable, offline product without
touching the privacy promise or breaking Core behavior.

---

## Context: a partial scaffold already exists (this is a reconciliation)

A prior pass (SP14, commit `68b8d6c`) already landed part of this on `main`:

- `license.py` — pure, editions `Core/Pro/Developer/Supporter`, entitlement
  dicts, `load_license`/`entitlements_for`. **No real signature check** (all
  non-Core payloads fail closed to Core).
- `entitlements.py` — pure, lowercase editions, **dotted** feature names
  (`snippets.packs`, `code.mode`), `allowed()`, `ALWAYS_FREE`. Unknown feature
  → allowed.
- `docs/FEATURE_MATRIX.md`, `docs/LICENSING.md`, `docs/RELEASE_TEST_PLAN.md`.
- `diagnostics.py` with `redact_path()` (partial).
- `settings_ui.py` already imports license/entitlements (partial wiring).
- Tests: `test_license.py`, `test_entitlements.py`, `test_gate.py`,
  `test_network_hygiene.py`, `test_diagnostics.py`.
- No crypto library pinned in `requirements*.txt`.

**Three divergences this spec resolves:**
1. `license.py` and `entitlements.py` use different edition casing and feature
   vocabularies. The incoming prompt introduced a *third* naming. → **Converge
   on ONE canonical vocabulary** (the `entitlements.py` lowercase-dotted one).
2. Unknown-feature default differs. → **Allow-unknown, but warn**, plus a guard
   test (see below). Unknowns never block Core/privacy.
3. Matrix would move currently-free features (snippets, milestones) behind Pro.
   → **Not enforced this pass.** Matrix is policy only; gates stay OFF.

---

## Global constraints (non-negotiables — verbatim)

1. No cloud transcription. 2. No account. 3. No subscriptions. 4. No internet
required for normal use. 5. No internet required for license validation after
import. 6. Don't gate basic dictation. 7. Don't gate offline use. 8. Don't gate
privacy controls. 9. Don't gate delete-history/delete-audio. 10. Licensing code
never touches transcript/audio/history/vocabulary/clipboard. 11. No telemetry.
12. No dark-pattern popups. 13. No upgrade prompts on launch. 14. No monetization
UI during dictation. 15. No private signing keys in the app. 16. No sample/dev
licenses accepted in production builds. 17. Don't break current Core behavior.

---

## Architecture

Three pure modules + docs + a calm settings panel + dev scripts. Data flow:

```
license file (JSON) ──parse──> payload ──SignatureVerifier(Ed25519)──> edition
                                                    │ fail-closed
                                                    ▼
                                          entitlements.allowed(feature, edition)
                                                    │ (NOT wired to any gate)
                                                    ▼
                                          settings license panel (display only)
```

### Unit 1 — `commercial_config.py` (new, constants only)

```python
DEFAULT_EDITION = "core"
CURRENT_MAJOR_VERSION = 1
PRO_PRICE_USD = 19
DEVELOPER_PRICE_USD = 29
SUPPORTER_PRICE_USD = 49
PURCHASE_URL_PRO = "https://example.com/roar/pro"          # placeholder
PURCHASE_URL_DEVELOPER = "https://example.com/roar/developer"
PURCHASE_URL_SUPPORTER = "https://example.com/roar/supporter"
SUPPORT_EMAIL = "support@example.com"                       # placeholder
LICENSE_PUBLIC_KEY_PATH = <resource path to bundled Ed25519 public key>
```
No logic, no imports of user data, no network. Placeholders are clearly marked
TODO-before-launch.

### Unit 2 — `entitlements.py` (canonical, reconciled)

- Canonical vocabulary = existing lowercase dotted names. Keep `EDITIONS`,
  `ALWAYS_FREE`, `_PRO`, `_DEVELOPER`, `_BY_EDITION`.
- Functions: `normalize_edition(edition)`, `features_for_edition(edition) -> set`,
  `allowed(feature, edition=None) -> bool` (alias `can_use`),
  `requires_upgrade(feature, edition) -> bool`,
  `minimum_edition_for(feature) -> str | None`.
- **Rule:** `ALWAYS_FREE` → always True (every edition). Known paid feature →
  True only if the edition grants it. **Unknown feature → True (allowed), and a
  warning is logged** ("unregistered entitlement feature: <name>").
- **Guard:** `KNOWN_FEATURES = ALWAYS_FREE | _PRO | _DEVELOPER`. A test
  (`test_entitlements.py`) asserts every feature string referenced elsewhere in
  the app is in `KNOWN_FEATURES` — forcing explicit registration before any real
  gate could ever ship. Unknowns must NEVER block Core/privacy.
- Purity: no file I/O, no UI imports, no config import, no network, no user-data
  imports.

### Unit 3 — `license.py` (reconciled)

- **Removes** its duplicate entitlement dicts; delegates feature questions to
  `entitlements.py`. Keeps a frozen result type:
  ```python
  @dataclass(frozen=True)
  class LicenseResult:
      edition: str = "core"
      valid: bool = False
      reason: str = "missing"     # missing|corrupt|malformed|unsigned|
                                  # bad_signature|unsupported_edition|
                                  # wrong_major|dev_rejected|ok
  ```
- Functions:
  - `parse_license(raw: str|bytes|dict) -> dict|None` — safe JSON, size-capped,
    never raises.
  - `validate_license(payload: dict, verifier: SignatureVerifier, current_major: int) -> LicenseResult`
  - `load_license(path: str|Path, verifier=None) -> LicenseResult` — reads file,
    defaults to the production verifier, fail-closed to Core on any error.
  - `get_current_edition(...) -> str` — resolves the active edition (Core when no
    valid license), for the settings panel.
- **Fail-closed table** (all return Core, `valid=False`, never raise/crash):
  missing · corrupt · malformed · missing signature · bad signature ·
  unsupported edition · wrong major · dev-license-in-production.
- **Canonicalization:** signed bytes = JSON of all fields except `signature`,
  `sort_keys=True`, `separators=(",",":")`, UTF-8. Verify signature over exactly
  those bytes.
- No `eval`. No trusting fields before verification. No network. No user-data.

### Unit 4 — `SignatureVerifier` interface + implementations

```python
class SignatureVerifier(Protocol):
    def verify(self, message: bytes, signature: bytes) -> bool: ...
```
- `CryptographySignatureVerifier(public_key_pem)` — Ed25519 via the
  `cryptography` library (added to `requirements.txt`). `verify` returns
  False on `InvalidSignature` or any error (**fail-closed, never raises out**).
- If `cryptography` import fails at runtime → licensing degrades to Core, app
  never crashes.
- `FakeSignatureVerifier` — **tests only**, lives under `tests/` or is guarded so
  it can never be selected in a packaged/production build.
- **Key handling:** app ships only a **public** key. Repo commits a *dev* public
  key; a production build swaps in the real key and **rejects dev-signed
  licenses** (`reason="dev_rejected"`). Private keys never in repo or app.

### Unit 5 — `diagnostics.redact_diagnostics(data: dict) -> dict`

Builds on existing `redact_path()`. Removes/redacts: transcript text, audio file
paths (unless explicitly safe), clipboard content, full window titles (unless
opted in), license signature, private keys, email, local paths beyond allowed
config/log summaries. Allowlist of safe keys: `version, edition, license_status,
model, device, language, format_mode, overlay_enabled,
streaming_preview_enabled, history_enabled, last_record_duration_ms,
last_transcription_duration_ms, last_injection_duration_ms`.

### Unit 6 — Settings license panel (calm, display-only)

Complete the stub in `settings_ui.py` / `settings.html`:
- Shows: `Current edition`, `License status` (Not activated / Activated locally
  / Invalid license), `Validation: Local/offline`.
- Buttons: Buy Pro / Buy Developer / Buy Supporter / Enter license / Import
  license file.
- Copy: "ROAR validates your license locally. No account is required. Your
  dictation data stays on this machine." Error copy is calm, never a stack trace.
- **No launch prompts. No dictation interruption. No feature is blocked.**
- An upgrade-prompt **copy helper** module is added (Pro/Developer/Supporter
  copy — "$19 once. No subscription. No account. No cloud transcription.") but is
  **NOT wired to block any feature** this pass.

### Unit 7 — Dev scripts (never imported by the app)

- `scripts/dev_generate_license.py` — generates a signed test license; reads the
  private key from an **env var**; prints "LOCAL TESTING ONLY — not for
  production"; refuses to run inside a packaged app.
- `scripts/verify_license_file.py` — verifies a license file against a public key
  for support/debugging.

---

## Documentation deliverables

Create: `docs/MONETIZATION.md`, `docs/PRICING.md`, `docs/FAQ.md`,
`docs/FOUNDER_COMPANY_READINESS.md`, `docs/SUPPORT.md`, `docs/REFUND_POLICY.md`,
`docs/PRIVACY_PROMISE.md`, `docs/COMMERCIAL_READINESS_CHECKLIST.md`,
`docs/CHECKOUT_SETUP.md`.
Update: `docs/FEATURE_MATRIX.md` (add the 19/29/49 prices; keep the free-forever
statements), ensure `docs/LICENSING.md` covers all LICENSE_ARCHITECTURE points
(format, public-key verify, offline, fail-to-Core, no network, no user-data,
test cases, production safety, dev-license restrictions). README pricing block +
doc links.

**Copy hygiene (enforced by test):** no "subscription", "account required", or
"cloud" claims anywhere in the commercial copy except the literal reassurances
("No subscription", "No account", "No cloud transcription"). Founder doc is a
business-readiness checklist with a "not legal advice / see attorney+CPA before
paid launch" disclaimer; founder split placeholder 50/25/25 with vesting + IP
assignment flagged as required.

---

## Versioning

Bump `paths.APP_VERSION` 0.16.0 → **0.17.0** (the prompt's `v0.14` predates this
repo's history). Run `scripts/roar_versions.py --fix` so README/VERSIONS stay in
parity. Tag `v0.17.0` only if all tests pass and the release checklist items that
apply to a docs+scaffold change are satisfied. No runtime behavior changes ship.

---

## Testing

- `test_license.py`: missing · valid Pro · valid Developer · valid Supporter ·
  invalid signature · malformed JSON · missing signature · unsupported edition ·
  wrong major · huge input · empty input · corrupt file · dev-license rejected
  under a production verifier · no network. Uses `FakeSignatureVerifier` and a
  real-Ed25519 round-trip with an ephemeral test keypair.
- `test_entitlements.py`: Core has dictation/privacy/delete · Core lacks
  code.mode · Pro has smart formatting, lacks code.mode · Developer has code.mode
  · Supporter == Developer · unknown edition → core · **unknown feature → allowed
  + warns** · privacy features can never become paid-only · **every referenced
  feature is registered in KNOWN_FEATURES**.
- `test_commercial_privacy.py`: license/entitlements import no history/audio/
  transcript/clipboard modules · validation needs no user data · diagnostics
  redaction removes transcript-like fields · commercial copy has no forbidden
  subscription/account/cloud wording (except the reassurances) · Core runs with
  no license config present.
- All existing tests stay green; the two divergent tests are updated to the
  canonical vocabulary.

---

## Acceptance criteria

Core dictation works with no license; missing/invalid license → Core, not crash;
privacy + delete controls free; no subscription language except "No
subscription"; no account; no cloud transcription; no telemetry; validation
offline; license code never touches user data; matrix documented; founder +
checkout + pricing + FAQ docs exist; tests cover license + entitlements; existing
tests still pass. **Additionally:** the two modules are reconciled to one
vocabulary; real Ed25519 verification works behind the `SignatureVerifier`
interface and fails closed; runtime gates remain OFF.

## Out of scope (explicit)

Runtime feature gating; wiring upgrade prompts to block features; real product
public key / purchase URLs / support email; any payment server; grandfathering
logic (unneeded while gates are off).

## Red-team self-review (run before finishing implementation)

No private keys committed; no dev license accepted under a production verifier;
no network calls in license/entitlements; no account/subscription copy; privacy
& delete never gated; no transcript/audio/history imports in license code; no
broad UI rewrite; settings page still loads; version consistent; docs don't claim
un-built features exist; no tests skipped without a documented reason.
