# ROAR Commercial Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Reconcile ROAR's two divergent license/entitlements modules into one canonical, offline-signed commercial model, add the commercial docs + real Ed25519 verification + diagnostics redaction + dev tooling + tests — **without enabling any runtime gate** — and ship v0.17.0.

**Architecture:** Three pure modules — `commercial_config.py` (constants), `entitlements.py` (edition→feature policy, canonical vocabulary), `license.py` (parse→verify→edition via a `SignatureVerifier` interface) — plus a calm display-only Settings license panel, dev scripts, and docs. Nothing is wired to block a feature.

**Tech Stack:** Python 3, pytest, `cryptography` (Ed25519), existing pywebview-style HTML/JS settings bridge.

## Global Constraints

- Runtime feature gates stay **OFF**; app remains "everything on". Matrix = policy.
- Canonical edition vocabulary: lowercase `core/pro/developer/supporter`.
- Canonical feature vocabulary: existing dotted names in `entitlements.py` (`snippets.packs`, `code.mode`, …).
- License/entitlements code imports **no** transcript/audio/history/vocabulary/clipboard/network.
- Fail closed to Core on any license problem; never raise/crash.
- No private keys in repo or app. Dev-signed licenses rejected under production verifier.
- Unknown feature → allowed **+ warn**; unknowns never block Core/privacy; guard test requires registration.
- Commercial copy: no "subscription/account/cloud" claims except the literal reassurances.
- Version target **0.17.0**. Run `scripts/roar_versions.py --fix` after the bump.
- Branch: `claude/v0.17-commercial-scaffold`.

---

### Task 1: `commercial_config.py` — constants

**Files:** Create `commercial_config.py`; Test `tests/test_commercial_config.py`.

**Produces:** `DEFAULT_EDITION`, `CURRENT_MAJOR_VERSION`, `PRO_PRICE_USD`, `DEVELOPER_PRICE_USD`, `SUPPORTER_PRICE_USD`, `PURCHASE_URL_PRO/DEVELOPER/SUPPORTER`, `SUPPORT_EMAIL`, `LICENSE_PUBLIC_KEY_PEM` (dev public key string), `IS_PRODUCTION` (False in repo).

- [ ] Test asserts prices are 19/29/49 ints, `DEFAULT_EDITION=="core"`, `CURRENT_MAJOR_VERSION==1`, URLs are `https://`, and the module imports nothing from history/audio/transcriber/recorder/clipboard.
- [ ] Implement constants only (placeholders marked `# TODO before launch`).
- [ ] Run `pytest tests/test_commercial_config.py -q` → PASS.
- [ ] Commit: `feat: add commercial_config constants`.

### Task 2: `entitlements.py` — canonical reconciliation

**Files:** Modify `entitlements.py`; Modify `tests/test_entitlements.py`.

**Consumes:** none. **Produces:** `EDITIONS`, `ALWAYS_FREE`, `KNOWN_FEATURES`, `normalize_edition(edition)`, `features_for_edition(edition)->set`, `allowed(feature, edition=None)->bool`, `can_use = allowed`, `requires_upgrade(feature, edition)->bool`, `minimum_edition_for(feature)->str|None`.

- [ ] Add `KNOWN_FEATURES = ALWAYS_FREE | _PRO | _DEVELOPER`.
- [ ] `allowed()`: ALWAYS_FREE→True; known-paid→membership check; unknown→True **and** `logging.getLogger("roar.entitlements").warning("unregistered entitlement feature: %s", feature)`.
- [ ] Add `features_for_edition`, `requires_upgrade`, `minimum_edition_for`.
- [ ] Tests: core has `dictation.push_to_talk`, `privacy.controls`, `history.delete`, `audio.delete`; core lacks `code.mode`; pro has `formatting.smart`, lacks `code.mode`; developer has `code.mode`; supporter==developer; unknown edition→core; **unknown feature→True + warning emitted** (capture with `caplog`); privacy features True for every edition; `minimum_edition_for("code.mode")=="developer"`.
- [ ] Purity test: `entitlements` module source imports none of {history, audio, transcriber, recorder, clipboard, requests, urllib, socket}.
- [ ] Run `pytest tests/test_entitlements.py -q` → PASS.
- [ ] Commit: `feat: reconcile entitlements to canonical vocabulary + guard`.

### Task 3: `SignatureVerifier` + `license.py` reconciliation

**Files:** Modify `license.py`; Modify `tests/test_license.py`; Modify `requirements.txt` (add `cryptography`).

**Consumes:** `entitlements.normalize_edition`, `commercial_config` (public key, current major, IS_PRODUCTION). **Produces:** `LicenseResult(edition, valid, reason)`; `SignatureVerifier` protocol with `.verify(message: bytes, signature: bytes)->bool`; `CryptographySignatureVerifier(public_key_pem)`; `parse_license(raw)->dict|None`; `validate_license(payload, verifier, current_major)->LicenseResult`; `load_license(path, verifier=None)->LicenseResult`; `get_current_edition(path=None, verifier=None)->str`; `canonical_bytes(payload)->bytes`. `FakeSignatureVerifier` lives in the test module only.

- [ ] Add `cryptography` to `requirements.txt`; `pip install` into venv.
- [ ] `canonical_bytes`: `json.dumps({k:v for k,v in payload.items() if k!="signature"}, sort_keys=True, separators=(",",":")).encode()`.
- [ ] `validate_license`: parse edition via `normalize_edition`; core/missing→`LicenseResult(reason="core"/"missing")`; verify base64 signature over `canonical_bytes` with verifier; bad→`reason="bad_signature"`; `valid_for_major != current_major`→`reason="wrong_major"`; dev key under `IS_PRODUCTION`→`reason="dev_rejected"`; success→`LicenseResult(edition, True, "ok")`. Everything fails closed to `edition="core", valid=False`, never raises.
- [ ] Remove the old `BASE/PRO/DEVELOPER_ENTITLEMENTS` dicts + `entitlements_for` from `license.py`; delegate feature questions to `entitlements.py`.
- [ ] Tests (`FakeSignatureVerifier` returns True/False deterministically; plus a real-Ed25519 round-trip with an ephemeral keypair generated in-test): missing · valid pro · valid developer · valid supporter · bad signature · malformed JSON · missing signature · unsupported edition · wrong major · 5 MB input · empty · corrupt file · dev-license under production verifier→`dev_rejected` · verify no `socket`/`urllib` import.
- [ ] Run `pytest tests/test_license.py -q` → PASS.
- [ ] Commit: `feat: real Ed25519 offline license verification (fail-closed)`.

### Task 4: `diagnostics.redact_diagnostics`

**Files:** Modify `diagnostics.py`; Modify `tests/test_diagnostics.py`.

**Consumes:** existing `redact_path`. **Produces:** `redact_diagnostics(data: dict)->dict`.

- [ ] `SAFE_KEYS` allowlist = {version, edition, license_status, model, device, language, format_mode, overlay_enabled, streaming_preview_enabled, history_enabled, last_record_duration_ms, last_transcription_duration_ms, last_injection_duration_ms}. Drop everything else; run `redact_path` on any surviving path-like values.
- [ ] Explicitly strip keys matching transcript/audio/clipboard/window_title/signature/private_key/email.
- [ ] Tests: a dict with `transcript`, `clipboard`, `signature`, `email`, `audio_path`, `window_title` plus safe keys → output has only SAFE_KEYS, no forbidden substrings anywhere in the JSON dump.
- [ ] Run `pytest tests/test_diagnostics.py -q` → PASS.
- [ ] Commit: `feat: full diagnostics redaction allowlist`.

### Task 5: dev scripts

**Files:** Create `scripts/dev_generate_license.py`, `scripts/verify_license_file.py`.

- [ ] `dev_generate_license.py`: reads private key from `ROAR_LICENSE_PRIVATE_KEY_PEM` env; prints `LOCAL TESTING ONLY — not for production`; refuses if `sys.frozen`; writes a signed license JSON. Not importable side-effect-free (guard under `if __name__=="__main__"`).
- [ ] `verify_license_file.py`: verifies a license file against a public key path/arg; prints edition + reason.
- [ ] Test (`tests/test_commercial_privacy.py` later) asserts app modules never import these scripts.
- [ ] Manual run: generate a dev license, verify it validates with the dev verifier and is `dev_rejected` under a production verifier.
- [ ] Commit: `chore: dev-only license generation + verification scripts`.

### Task 6: documentation

**Files:** Create `docs/MONETIZATION.md`, `docs/PRICING.md`, `docs/FAQ.md`, `docs/FOUNDER_COMPANY_READINESS.md`, `docs/SUPPORT.md`, `docs/REFUND_POLICY.md`, `docs/PRIVACY_PROMISE.md`, `docs/COMMERCIAL_READINESS_CHECKLIST.md`, `docs/CHECKOUT_SETUP.md`; Modify `docs/FEATURE_MATRIX.md`, `docs/LICENSING.md`, `README.md`.

- [ ] Write each doc per the spec's "Documentation deliverables". Prices 19/29/49. Founder doc = readiness checklist + "not legal advice" + 50/25/25 placeholder + vesting/IP-assignment required. Refund = 14-day draft. Privacy promise = plain, strong. Checkout = Lemon Squeezy/Stripe/Paddle + manual-first + key safety + test/refund/support.
- [ ] FEATURE_MATRIX: add a price row; keep the four "remains free" statements.
- [ ] README: add the Pricing block + doc links + "Includes v1.x updates…" line.
- [ ] Copy check: `grep -rniE "subscription|account|cloud" docs README.md` → only allowed reassurance contexts (verified in Task 8 test).
- [ ] Commit: `docs: monetization, pricing, faq, founder, checkout, privacy promise`.

### Task 7: Settings license panel + upgrade-prompt copy helper

**Files:** Modify `settings_ui.py`, `settings.html`; Create `upgrade_prompts.py`; check `tests/test_settings_bridge.py`, `tests/test_settings_smoke.py`.

**Consumes:** `license.get_current_edition`, `commercial_config`. **Produces:** a bridge method returning `{edition, license_status, validation:"Local/offline"}`; `upgrade_prompts.copy_for(edition)->dict` (title+body strings, no subscription wording).

- [ ] Add a display-only License section: edition, status, "validated locally/offline", Import/Enter license + Buy links. No launch prompt, no dictation hook, blocks nothing.
- [ ] `upgrade_prompts.py`: pure copy dict per edition ("$19 once. No subscription. No account. No cloud transcription."). Not wired to gate anything.
- [ ] Run `pytest tests/test_settings_bridge.py tests/test_settings_smoke.py -q` → PASS (fix any breakage).
- [ ] Commit: `feat: calm offline license panel + upgrade copy helper (no gating)`.

### Task 8: `test_commercial_privacy.py`

**Files:** Create `tests/test_commercial_privacy.py`.

- [ ] license + entitlements source import none of {history, audio, transcriber, recorder, clipboard}.
- [ ] Core runs with no license file present → `get_current_edition()=="core"`, no exception.
- [ ] `redact_diagnostics` removes transcript-like fields.
- [ ] Commercial copy (`docs/*.md`, README, `upgrade_prompts.py`) contains no "subscription/account/cloud" **except** allowed reassurance phrases ("No subscription", "No account", "No cloud transcription", and explanatory negations).
- [ ] Dev scripts not imported by any app module.
- [ ] Run `pytest tests/test_commercial_privacy.py -q` → PASS.
- [ ] Commit: `test: commercial privacy + copy-hygiene coverage`.

### Task 9: version bump + full suite + red-team + release

**Files:** Modify `paths.py` (`APP_VERSION`), `CHANGELOG.md`; run version tool.

- [ ] Bump `APP_VERSION` 0.16.0→0.17.0; add CHANGELOG entry.
- [ ] Run `python scripts/roar_versions.py --fix`.
- [ ] Run the **full** suite `pytest -q`; all green (or pre-existing failures documented with evidence).
- [ ] Red-team self-review (spec checklist): no keys committed, no dev license in prod, no network, no account/subscription copy, privacy/delete never gated, no user-data imports in license code, settings loads, version consistent, no un-built claims.
- [ ] Commit: `chore: bump v0.17.0 + changelog`. Tag `v0.17.0` only if fully green.

---

## Self-Review

**Spec coverage:** commercial_config (T1), entitlements reconcile (T2), license+Ed25519+SignatureVerifier (T3), diagnostics redaction (T4), dev scripts (T5), all docs (T6), settings panel + upgrade copy (T7), commercial privacy tests (T8), version+parity+red-team (T9). Non-negotiables mapped to T2/T3/T8. ✅ no gaps.

**Placeholder scan:** URLs/email/dev-key are intentional launch placeholders, marked as such. No "implement later" steps.

**Type consistency:** `LicenseResult`, `SignatureVerifier.verify(bytes,bytes)->bool`, `allowed(feature,edition)`, `get_current_edition`, `redact_diagnostics(dict)`, `canonical_bytes` used consistently across tasks.
