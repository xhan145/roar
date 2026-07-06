# Red-Team Hardening + UI Polish (SP14) — Design

**Date:** 2026-07-05 · **Status:** approved (user work order; pre-authorized autonomous)
**Branch:** `codex/redteam-hardening-ui-ux` → merge to main when green.
**Version:** stays `0.16.0` (Codex's app-profiles bump; still unreleased/untagged —
binaries built at next release train, noted in docs).

## Constraints (verbatim from order)
Local-first; no cloud/telemetry/accounts/subscription/auto network; update check
click-only; privacy + data controls never paid; licensing never touches user
data; no local LLM/sync/analytics. Small, fast, calm, deterministic.

## Phase map (order → what actually needs doing here)

| Ph | Work | Notes |
|---|---|---|
| 1 | Docs align: README status quadrants (shipped/experimental/planned/not-included), CHANGELOG.md from tag history, add v0.15.1+v0.16.0 lines, gitignore `backups/` `.obsidian/` | backups/ appears at repo root when running from source (paths._data_dir) |
| 2 | Core safety: mostly EXISTS (corrupt config/db recovery, CPU fallback, calm mic error, click-only updates). ADD: static test asserting startup modules never import urllib/network; keep all-editions privacy (no gating exists) | verify-and-test phase |
| 3 | Focus safety: capture target hwnd at `_start_recording` (`self._target_hwnd`); before inject compare to current; mismatch → NO injection, error tone + notify "Focus changed. ROAR did not type." Clipboard: `injector.MAX_PASTE=100_000` (reject over, notify) + restore stays; scratch guard EXISTS; logs carry char counts only (никогда transcript) — verified | real behavior change |
| 4 | `diagnostics.py` pure: `collect(info)->dict` safe fields only + `redact_path` (home→`~`, keep tail); bridge `diagnostics_get`/`safe_mode`; About gains Diagnostics block: Copy Safe Diagnostics + Safe Mode (sets overlay off / streaming off / paste_fallback on; message lists prior values — reversible, nothing erased) | no transcript/clipboard/audio/titles/vocab/snippets in output |
| 5 | Appearance: config `appearance` in {system,light,dark}, default **dark** (design assumes dark); settings.html palette → CSS custom properties with `[data-theme=light]` overrides + `prefers-color-scheme` for system; toggle in General; lavender/navy/white identity kept; pill overlay already light — untouched; a11y labels + destructive twoStep confirms kept/extended | biggest UI diff |
| 6 | Snippets: validation/limits/collision/one-pass EXIST. ADD `MAX_CLIP_CHARS=10_000` truncation in `resolve_variables`; UI chip "uses {clipboard}" on cards; import result warns when pack contains {clipboard}; no-network = already pure | |
| 7 | Formatting/profiles: no Raw/Clean/Code "modes" exist — profiles supply this (code profile disables cleanup ✓, symbol dictation NOT implemented → documented intentionally-not-included). Lookup failure → "" → {} ✓; titles ephemeral (never logged/stored) — add test + doc | mostly verify |
| 8 | History: clear-all copy states badges persist; ADD bridge `reset_milestones` (+ two-step button in Insights), `clear_log` (About); factory reset SKIPPED (would clobber tuned hotkey/device — unsafe vs order's "only if safe"); migrations safe ✓; no tags/filters exist | |
| 9 | Licensing readiness (nothing exists): ADD PURE `entitlements.py` — editions CORE<PRO<DEV<SUPPORTER, `allowed(feature, edition)`, PRIVACY/CORE features return True for every edition incl. unknown/None; feature lists per the order's gate policy; NOT wired into any runtime gate. `docs/LICENSING.md`: architecture, offline activation design, explicit note that real signature verification needs a vetted crypto dep (stdlib has none) — no homemade crypto, no keys bundled | docs+primitives only |
| 10 | `docs/RELEASE_TEST_PLAN.md`, `docs/KNOWN_ISSUES.md` (mutex smoke flake, /qb Files-in-Use, auto-indent + emoji undo caveats, MSI 2GB→cabs), `PRIVACY.md` (root), `docs/FEATURE_MATRIX.md` | |
| 11 | Full suite ×2 green (kill ROAR first — running tray = known smoke flake) | |
| 12 | Merge branch → main, push both | binaries deliberately not rebuilt; next release train covers it |

## Test additions
startup-no-network static scan; focus-mismatch skip + notify; MAX_PASTE bound;
clipboard truncation; diagnostics redaction (paths, no forbidden keys); safe-mode
writes + message; appearance config sanitize; entitlements privacy-always-free
matrix incl. unknown edition; reset_milestones bridge; profile-title-ephemeral.
