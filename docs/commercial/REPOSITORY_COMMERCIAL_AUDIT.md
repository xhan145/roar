# ROAR — Repository Commercial Audit

**Date:** 2026-07-11 · **Audited version:** v0.21.0 · **Target:** v0.22.0

Written **before** any gating work, per the commercial brief's Step 1. The
headline: **most of the requested commercial architecture already exists** and
ships on `main`. This audit separates what exists from what is genuinely missing,
and records every place the brief diverges from the repository.

## 1. Architecture discovered

| Aspect | Finding |
|---|---|
| Language / stack | **Python** (cp314), Windows tray app |
| Entry point | `app.py` (`main()` at ~L763, `__main__` at ~L821) |
| Version | `paths.APP_VERSION` = **0.21.0** (synced to README badge + tests by `scripts/roar_versions.py`, enforced by a pre-commit `--check` hook) |
| Settings UI | **pywebview** window in a **separate process**; `settings.html` (HTML/CSS/JS) + `settings_ui.py` bridge. The settings process **must never import the ML stack** (guarded by `test_settings_no_ml` + a subprocess test) |
| Config | `config.py` → `config.json` via `paths.config_path()` = `%APPDATA%\ROAR\config.json` (frozen) / repo root (source). Validated key-by-key; unknown keys pass through; a broken file falls back to defaults without crashing |
| Data paths | `paths.py`: `%APPDATA%\ROAR` = config; `%LOCALAPPDATA%\ROAR` = models, `history.db`, audio, `roar.log`, `status.json`. Getters are **pure** (never create dirs) |
| Packaging | PyInstaller **one-dir** (`roar.spec`) → WiX MSI + external CABs → 7-Zip SFX (`scripts/build_msi.sh`, `scripts/build_setup.sh`). **Note:** `build_msi.sh` does NOT run PyInstaller — the full release is PyInstaller → build_msi → build_setup |
| Update check | `settings_ui.check_updates` — **click-only**, the sole sanctioned outbound call besides `whispercpp_assets` (opt-in GPU download). Enforced by `tests/test_network_hygiene.py` |
| Tests | **374** passing (1 environmental smoke skip), incl. **37 commercial** |

### Feature modules (top-level)
`app.py` (tray/orchestration), `recorder.py`, `transcriber.py`, `injector.py`,
`hotkeys.py`, `gestures.py`, `overlay.py`, `cleanup.py`, `commands.py`,
`context.py` (per-app profiles), `snippets.py`, `vocabulary.py`, `history.py`,
`insights.py`, `milestones.py`, `editing.py` (scratch-that), `diagnostics.py`,
`languages.py`, `hardware_accel.py`, `status.py`, `ipc_commands.py`,
`autostart.py`, `whispercpp_assets.py`, `backends/`.

## 2. Commercial code that ALREADY EXISTS

| Brief step | Status |
|---|---|
| **Step 3** — edition model | ✅ `entitlements.py`: `normalize_edition` (unknown/missing → `core`), `EDITIONS`, hierarchy via `_BY_EDITION` (Developer ⊇ Pro; Supporter ⊇ Developer) |
| **Step 4** — entitlements | ✅ same module: `allowed`/`can_use`, `features_for_edition`, `requires_upgrade`, `minimum_edition_for`. **Pure** — no I/O, no UI, deterministic |
| **Step 5** — offline signed licenses | ✅ `license.py`: Ed25519 via `cryptography`, `SignatureVerifier` interface + `_NullVerifier` (fails closed when no backend), `canonical_bytes` (sorted-keys/compact JSON minus `signature`), `parse_license`, `validate_license` (**verify-before-trust**), `load_license`, `get_current_edition`. 64 KB cap. `LicenseResult(edition, valid, reason)` |
| **Step 6** — dev tooling | ✅ `scripts/dev_generate_license.py`, `scripts/verify_license_file.py`. Public key only in `commercial_config`; private key never committed; `IS_PRODUCTION` rejects `env=dev` licenses |
| **Step 2** — docs | ✅ `docs/`: MONETIZATION, FEATURE_MATRIX, LICENSE_ARCHITECTURE, PRICING, REFUND_POLICY, LICENSING, FAQ, PRIVACY_PROMISE, CHECKOUT_SETUP, COMMERCIAL_READINESS_CHECKLIST |
| **Step 13** — tests | ✅ 37: `test_entitlements` (9), `test_license` (16), `test_commercial_config` (5), `test_commercial_privacy` (7) |
| **Step 14** — privacy audit | ⚠️ Partial: `test_commercial_privacy` already asserts licensing touches no user content; `diagnostics.redact_diagnostics` exists. No consolidated security doc |

**Existing validation states** (`LicenseResult.reason`): `missing`, `corrupt`,
`malformed`, `unsigned`, `bad_signature`, `unsupported_edition`, `wrong_major`,
`dev_rejected`, `core`, `ok`.

## 3. What is genuinely MISSING

1. **No `paths.license_path()`.** `settings_ui` calls `get_current_edition()`
   **with no path**, and the function returns `core` when `path` is falsy — so
   **the edition is always Core today and no license is ever loaded from disk.**
   This is the single biggest gap.
2. **No license service**: no `import_license` / paste / `remove_license` /
   `refresh` / atomic write. `license.py` is read-and-validate only.
3. **No activation UI**: the Settings license card is **display-only**
   (`settings_ui.license_info`) — no Paste / Import / Remove / Buy controls.
4. **No wired upgrade component**: `upgrade_prompts.all_copy()` is copy-only.
5. **Gates are OFF**: verified — `entitlements` is imported by **no runtime
   module** (only `license.py` and `commercial_config.py` reference it).
6. **No** `docs/commercial/`, audit doc, security review, or release checklist.
7. **No** `license_notifications` / `purchase_urls` config defaults.

## 4. Existing features → edition mapping

**Critical finding: every paid-target feature already ships FREE in v0.21.0.**

| Feature (shipped, free today) | Module | Brief's target tier |
|---|---|---|
| Push-to-talk / toggle dictation | `hotkeys`, `gestures` | Core ✔ |
| Local transcription, offline | `transcriber` | Core ✔ |
| Streaming preview | `overlay` | Core ✔ |
| Multilingual | `languages` | Core ✔ |
| Basic cleanup | `cleanup` | Core ✔ |
| History + deletion + retention | `history` | Core ✔ (**never gate**) |
| Audio deletion | `history`/`paths.audio_dir` | Core ✔ (**never gate**) |
| Privacy controls | `config`, `history` | Core ✔ (**never gate**) |
| Basic vocabulary | `vocabulary` | Core ✔ |
| Basic spoken commands | `commands` | Core ✔ |
| Scratch-that | `editing` | Core ✔ |
| Safe diagnostics | `diagnostics` | Core ✔ |
| **Snippets + variables** | `snippets` (v0.10) | **Pro** ⚠ shipped free |
| **Smart / context-aware formatting** | `context`, `commands` (v0.15/16) | **Pro** ⚠ shipped free |
| **Advanced cleanup** (discourse fillers) | `cleanup` (v0.11) | **Pro** ⚠ shipped free |
| **Vocabulary suggestions** (`auto_vocabulary`) | `vocabulary` (v0.5) | **Pro** ⚠ shipped free |
| **Milestones** | `milestones` (v0.13) | **Pro** ⚠ shipped free |
| **Insights** | `insights` (v0.4) | **Pro** ⚠ shipped free |
| **History search/filters** | `history` (v0.4) | **Pro** ⚠ shipped free |
| **Settings/snippet export-import** | `settings_ui` (v0.10) | **Pro** ⚠ shipped free |
| **Per-app profiles / per-app language** | `context` (v0.16) | **Developer** ⚠ shipped free |
| **Code mode + programming symbols** | `commands.CODE_SYMBOLS`, `format_mode="code"` | **Developer** ⚠ shipped free |

### Features in the brief that do NOT exist (mark **planned**, never gate-then-claim)
`vocabulary.project` (project vocabulary), `snippets.developer_packs`,
`files.tagging` / developer tagging, history **tags** (only search/filter exists),
per-app **injection** settings, "productivity formatting profiles" as a distinct
feature.

## 5. Where gating could damage current behavior

1. **Taking shipped features from live users.** ROAR is public and free; all
   paid-target features ship today. Gating without grandfathering violates brief
   rule 17 and would be a trust breach. → **Mitigation: one-time legacy grant.**
2. **Config destruction.** Gating must not delete paid-feature settings. A user
   dropping to Core must keep `format_mode: "code"` / snippets / `app_profiles`
   in config, with only the *behavior* withheld → restoring a license reactivates
   them with no reconfiguration.
3. **Pipeline coupling.** `commands.process` / `context` resolve formatting per
   utterance. A gate there must **never** be able to break plain dictation —
   gate by *resolving down* (`code`→`clean`), never by raising.
4. **Settings-process purity.** Gate checks in `settings_ui` must not import the
   ML stack (`test_settings_no_ml`). `entitlements` is pure → safe.
5. **Fail-closed risk.** If unknown features failed closed, a typo could lock a
   **Core** feature = release blocker. See divergence #2.
6. **Never gate**: dictation, offline, privacy, history/audio deletion, retention
   toggles — in any edition, for any reason.

## 6. Installer & upgrade risks

1. **License must survive upgrades.** Store at `%APPDATA%\ROAR\license.json`
   beside `config.json`. The MSI upgrade replaces program files only; per-user
   APPDATA is untouched. **Never** put the license in `%LOCALAPPDATA%\ROAR`
   alongside `history.db`/audio, which privacy/history clears operate on.
2. **History clear / privacy reset / audio delete must not touch the license.**
   Separate path + explicit "Remove License" only.
3. **Packaging must exclude** private keys and dev license fixtures, and include
   the public key. `roar.spec` bundles top-level modules via the import graph;
   new modules (`license_service`, `legacy_grant`) are imported from `app.py`/
   `settings_ui.py` so they collect — pin as `hiddenimports` if lazily imported
   (precedent: the Vulkan backend needed this).
4. **The stale-bundle trap**: `build_msi.sh` does **not** run PyInstaller. Always
   PyInstaller → build_msi → build_setup, or the installer ships old code under a
   new version stamp.

## 7. Recommended implementation locations

| Concern | Location |
|---|---|
| Edition + entitlements (pure) | `entitlements.py` (extend with `legacy_grants` param) |
| License validation (pure-ish) | `license.py` (**no change needed**) |
| License paths | `paths.py` → `license_path()`, `legacy_grant_path()` (APPDATA) |
| License service (I/O) | **new** `license_service.py` |
| Legacy grant | **new** `legacy_grant.py` (pure decision + thin I/O) |
| Upgrade copy/component | `upgrade_prompts.py` (extend) + `settings.html` |
| Activation UI | `settings.html` License section + `settings_ui.py` bridge |
| Gates | Backend entry points: `settings_ui` bridge methods + `commands`/`context` resolution in `app.py`'s pipeline |
| Commercial constants | `commercial_config.py` (**prices unchanged**) |

## 8. Test coverage — current and missing

**Current (37):** entitlements hierarchy/normalization/always-free; license
valid/invalid-signature/malformed/oversized/wrong-major/dev-rejected/unsupported;
commercial config constants + prices; licensing-touches-no-user-content.

**Missing (to add):** legacy grant (granted / not-granted / idempotent / never
grants an edition / never grants an unshipped feature); license **service**
(missing→Core, corrupt→Core, import refreshes, remove→Core, **failed import
preserves an existing valid license**, oversized paste rejected, atomicity,
survives config migration); **applied gates** (each gated feature blocked in Core,
allowed via license or grant, paid config preserved when unlicensed); UI smoke
(License section renders per edition, invalid paste doesn't crash, buttons use
configured URLs, **no upgrade prompt at startup**); packaging (public key in,
private key + fixtures out); prohibited-language scan.

## 9. Divergences from the brief (deliberate, with rationale)

1. **Pricing — brief says $19/$29/$49; repo keeps $29/$49/$99.**
   The brief's table is **stale**: the owner explicitly set 29/49/99 on
   2026-07-07 ("bump commercial_config prices to 29/49/99 and update the test"),
   and `tests/test_commercial_config.py` asserts it. Confirmed with the owner on
   2026-07-11: **repo pricing wins**; no price change.
2. **Unknown features fail OPEN, not closed.**
   The brief requires fail-closed. `entitlements.allowed` deliberately allows +
   warns for unregistered features, guarded by `KNOWN_FEATURES` + a registration
   test. Kept because fail-closed's failure mode is *accidentally locking a Core
   feature* (release blockers #1/#2, breaks the product promise), whereas
   fail-open's worst case is a paid feature leaking free (a revenue bug). The
   guard test prevents drift.
3. **Feature IDs stay dotted** (`formatting.smart`), not the brief's flat IDs
   (`smart_formatting`). Renaming would churn the module, 37 tests, and the docs
   for zero behavioural gain.
4. **Existing commercial docs stay in `docs/`**, not `docs/commercial/`. They are
   referenced by `tests/test_commercial_privacy.py`, `README.md`, `AGENTS.md`,
   `ROADMAP-14DAY.md`, the `entitlements.py` docstring, and prior specs. The brief
   permits "adapting paths to repository conventions"; flat `docs/` is this repo's
   convention. `docs/commercial/` holds the **new** docs only.
5. **Grandfathering is a feature grant, never an edition.** Required to satisfy
   "no unsigned value unlocks an edition" (release blocker #7) while still not
   taking shipped features from existing users.

## 10. Honest limits

- The legacy grant is **local unsigned state**. All local-only licensing is
  honor-based — ROAR has **no server by design**. The grant is bounded: it can
  never confer an edition and never confer a feature that never shipped free.
- Because every paid-target feature ships free today, **grandfathering means the
  paid tiers monetize new users only** until new Pro/Developer capabilities are
  built. This is a business consequence the owner accepted explicitly.
