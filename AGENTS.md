# AGENTS.md — working in the ROAR repo (Claude Code & GPT Codex)

ROAR is a **local-first Windows dictation tray app** (Python, faster-whisper /
CTranslate2, pywebview settings UI). This file is the shared contract for any AI
agent working here.

## Non-negotiables (never violate)
- No cloud transcription. No telemetry. No account. No background network calls.
- Transcription and license validation are **offline**.
- Monetization is **one-time payment only** (no subscription).
- **Core dictation is free.** Privacy controls, history deletion, audio deletion,
  offline use, and basic dictation are **never paid-only**. Paid gates unlock
  workflow power only.
- Never commit a private signing key. Never bundle sample/dev licenses in a
  production build.

## Architecture invariants (tests enforce these — don't break them)
- **The Settings window is a separate, lightweight process** and must NEVER import
  the ML stack (`transcriber`/`faster_whisper`/`ctranslate2`/`hardware_accel`) at
  module load. It reads state from `config` + `status.json` only.
  (`tests/test_settings_no_ml.py`, `tests/test_settings_bridge.py`.)
- **`status.json` and diagnostics are allowlist-only** — transcripts/audio/
  clipboard/window-titles can never leak through them (`status.ALLOWED`,
  `diagnostics.SAFE_KEYS`).
- **Licensing code touches no user data** (`license.py`/`entitlements.py` import no
  transcript/audio/history/vocabulary/clipboard/network).
- The transcriber keeps the model **warm** (constructed once, never per dictation).
- Commercial copy has **no** subscription/account/cloud claims except the literal
  reassurances (`tests/test_commercial_privacy.py`).

## Branch strategy
`main` is always release-ready. Never commit runtime changes directly to `main`
without review.

- **Claude Code** → `claude/<version>-<topic>` (e.g. `claude/v1.0-gate-wiring`).
- **GPT Codex** → `codex/<topic>` (e.g. `codex/checkout-webhook`).
- **One agent per file at a time.** The two agents must not edit the same files on
  concurrent branches — that has caused reconcile pain before. Split work by file/
  subsystem, keep PRs small, and merge to `main` promptly to shrink the conflict
  window. If branches diverge, rebase onto `main` and resolve before merging.
- **Docs-only vs runtime:** a "docs" task must not change runtime behavior. Keep
  doc-vs-code deltas (e.g. a pricing change) explicit and tracked in
  [ROADMAP-14DAY.md](ROADMAP-14DAY.md), never silent.

## Versioning
- Single source of truth: `paths.APP_VERSION`. After any bump run
  `python scripts/roar_versions.py --fix` (syncs the README badge + version-
  asserting tests + `VERSIONS.md`). A pre-commit `--check` hook blocks drift.
- Components are versioned independently (desktop ≠ Android port).

## Testing gates (run before every merge to `main` / release)
```
venv/Scripts/python.exe -m pytest -q          # full suite (all green*)
venv/Scripts/python.exe scripts/roar_versions.py --check
```
Plus, for releases: settings/tray smoke, installer smoke (fresh/upgrade/
uninstall/reinstall), Core-runs-without-license, offline license validation,
dev-license-rejected-in-prod, privacy/delete-free, copy hygiene, no-network-in-
transcription-path.

*The one expected failure is `tests/test_smoke.py` when a ROAR instance is already
running (the single-instance guard) — environmental, not a code defect.

## Build (Windows)
`export JAVA_HOME` is NOT needed (that's the Android port). Desktop build:
`venv/Scripts/python.exe -m PyInstaller roar.spec --noconfirm` →
`scripts/build_msi.sh` → `scripts/build_setup.sh`. The 7-Zip SFX step needs
**~5-6 GB free** — delete a superseded `dist/ROAR-Setup-*.exe` first if the disk
is tight (and note `set -e` won't catch a 7za disk-full error).

## Commercial docs map
[ROADMAP-14DAY.md](ROADMAP-14DAY.md) · [docs/MONETIZATION.md](docs/MONETIZATION.md)
· [docs/LICENSE_ARCHITECTURE.md](docs/LICENSE_ARCHITECTURE.md) ·
[docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md) ·
[docs/PRICING.md](docs/PRICING.md) · [docs/PRIVACY_PROMISE.md](docs/PRIVACY_PROMISE.md)
· [docs/CHECKOUT_SETUP.md](docs/CHECKOUT_SETUP.md) ·
[docs/COMMERCIAL_READINESS_CHECKLIST.md](docs/COMMERCIAL_READINESS_CHECKLIST.md).
