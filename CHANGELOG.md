# Changelog

All notable changes to ROAR. Dates are release-tag dates; entries before a tag
exists are marked unreleased.

## v0.23.0 — 2026-07-17
- **Paid editions now activate.** This build carries the production license key
  and runs in production mode, so a signed Pro/Developer/Supporter license
  imported in Settings → License unlocks its edition — verified offline. Test
  (dev-signed) licenses are rejected.
- **License generator tooling** (owner-side, not shipped in the app):
  `scripts/generate_keypair.py` mints the Ed25519 signing keypair (private key
  kept off the repo); `scripts/issue_license.py` signs a real per-customer
  license (unique id, hashed email, self-verifies against the app key before
  writing). See docs/commercial/LICENSE_FULFILLMENT.md.
- Core is unchanged and still free; existing installs stay grandfathered and
  their settings/history/license survive the upgrade.

## v0.22.0 — 2026-07-11
- Commercial editions are now real and **enforced, with grandfathering**. The
  edition model, entitlements and offline Ed25519 licensing shipped in v0.17.0;
  this release closes the gaps and turns the gates on.
- **Licences actually load now.** There was no `license_path()`, so the edition
  was always Core and no licence was ever read from disk. Licences live at
  `%APPDATA%\ROAR\license.json` — beside config, never in the data dir that
  history/audio clears touch, so clears and upgrades can't remove them.
- **License service + activation UI**: paste or import a licence file, remove it,
  buy links. Import is atomic and validates *before* replacing, so a bad paste
  can never disturb a valid licence. Oversized input is rejected before parsing;
  licence IDs are redacted everywhere.
- **Grandfathering**: every paid-target feature shipped free through v0.21.0, so
  an existing install gets a one-time grant of exactly those features — **nobody
  loses anything they already had**. New installs are gated. A grant is feature
  IDs only and never confers an edition; never-shipped features stay Developer-
  only for everyone.
- **Gates run in the backend**, not the markup: the pipeline resolves settings
  *down* to what you're entitled to (code→clean, snippets/profiles withheld), so
  a gate can never break plain dictation, and your paid settings are preserved —
  drop to Core and back and everything reactivates untouched.
- One reusable upgrade prompt, shown only on intentional paid-feature
  interaction — never at startup, never during dictation, no countdowns, no
  "trial expired", and Core is never called a trial.
- Core is untouchable: dictation, offline use, privacy controls, history/audio
  deletion and retention toggles are free in every edition, forever.
- Docs: commercial audit, security review, release checklist; FEATURE_MATRIX
  records the grandfathering decision and marks unbuilt features **planned**.
- Pricing stays **$29 / $49 / $99** (the brief's $19/$29/$49 table was stale).
  Purchase URLs + the production key remain placeholders — see
  docs/commercial/RELEASE_CHECKLIST.md before charging.

## v0.21.0 — unreleased (source)
- Real AMD / Intel GPU acceleration via a new **whisper.cpp Vulkan** backend
  (Vulkan is vendor-agnostic — any Vulkan-1.3 GPU). Opt-in from Settings
  ("Engine: AMD / Intel GPU (Vulkan)"); selecting it downloads a small,
  checksum-verified GPU binary + model once (inbound-only, never in the
  dictation path), then transcribes on a warm local `whisper-server` subprocess
  bound to loopback — 100% offline. If it can't start, ROAR falls back to the
  CTranslate2 CPU/CUDA path automatically. Validated on GPU hardware
  (~0.3s/11s clip); NVIDIA CUDA and CPU paths are unchanged.
- Replaces the honest-but-dead DirectML scaffold as the AMD GPU story.

## v0.20.1 — unreleased (source)
- CPU / AMD Ryzen perf: set CTranslate2 `cpu_threads` to the physical-core
  estimate (logical//2 on SMT chips, capped 16) instead of ct2's default,
  which oversubscribes SMT. Measured ~20% faster CPU transcription
  (2197ms -> ~1770ms, small.en int8, 16-logical laptop). New `cpu_threads`
  config (0=auto; >0 explicit), shown in Diagnostics; changing it reloads.

## v0.20.0 — unreleased (source)
- GPU/perf hardening: automatic NVIDIA CUDA fast path made config-driven —
  `hardware_accel.py` detection + device/compute selection with a safe fallback
  ladder; Fast/Balanced/Accurate presets (precision + beam only, never the
  model, so no preset ever downloads); Acceleration + Compute-type controls in
  Settings; always keeps the CPU int8 fallback attempt.
- Real release-to-text latency instrumentation (record/transcription/injection
  ms) surfaced in Diagnostics + the Home dashboard (the old "latency" was
  mislabeled audio length). Model stays warm (unchanged; never per-dictation).
- `scripts/benchmark_transcription.py` (offline). Measured RTX 4060: CPU int8
  2079 ms vs CUDA float16 288 ms / int8_float16 259 ms (~8× faster; Fast ~10%
  under Balanced).
- Backend seam (`backends/`) + honest experimental DirectML spike: AMD/DirectML
  is **unavailable** (no false claim) and falls back cleanly to CUDA/CPU with a
  diagnostics reason. `requirements-directml.txt` is opt-in only.
- CPU-only installs unchanged; no network added to the transcription path; no
  transcript ever written to logs/status/diagnostics (allowlists enforce it).

## v0.19.0 — unreleased (source)
- Reconciled the Home dashboard (v0.18.0) and the commercial scaffold (v0.17.0)
  onto one `main`. Both were developed in parallel off v0.16.0; this is their
  union. No behavior change beyond that; runtime feature gates stay OFF.

## v0.18.0 — unreleased (source)
- ROAR Home dashboard (P1): the Settings window opens to a polished Home view
  ("Talk. Type. Locally.") showing real local state — live dictation status,
  session/last-transcription/active-profile cards, settings summary, and a
  status bar — via a one-way `status.json` the tray writes (operational facts
  only, never transcript/clipboard/audio/window titles). Added as the default
  first sidebar item; all existing sections stay reachable. Live status polls
  only while Home is visible; reduced-motion freezes the mic/waveform. No new
  network, deps, or external assets.
- ROAR Home dashboard (P2): sidebar re-mapped to the 8-item IA — Home / Profiles
  / Insights / History / Dictionary / Hotkeys / Settings / About. Profiles and
  Dictionary split out of Transcription; General/Voice/Transcription/Privacy/
  Snippets grouped under a Settings overview (kept intact, reachable, never
  gated).
- ROAR Home dashboard (P3): optional remote Start/Stop + Scratch-that from Home
  via a local `command.json` (fixed command names only), behind the
  `dashboard_controls` config flag (OFF by default). When off, the buttons show
  hotkey guidance.

## v0.17.0 — unreleased (source)
- Commercial scaffold: reconciled licensing into one canonical, offline-signed
  model (`commercial_config.py`, `entitlements.py`, `license.py`) with real
  Ed25519 verification behind a `SignatureVerifier` interface, verify-before-trust,
  fail-closed to Core, and dev-license rejection in production builds.
- Full diagnostics redaction (`redact_diagnostics`), a calm **display-only**
  license card in Settings, dev-only license generate/verify scripts, and a
  pure upgrade-prompt copy helper (not wired to gate anything).
- Commercial docs: monetization, pricing, FAQ, founder readiness, support,
  refund policy, privacy promise, checkout setup, readiness checklist; README
  pricing block; LICENSING updated to the real implementation.
- **Runtime feature gates remain OFF** — the feature matrix is policy only;
  privacy controls and history/audio deletion stay free, and nothing users have
  today is removed.

## v0.16.0 — unreleased (source)
- Expanded app profiles: `code` (verbatim), `casual` (texting style, keeps
  slang), `formal` (polished) with a large built-in app map (VS/JetBrains/
  terminals; WhatsApp/Discord/Ableton/Spotify; Outlook/Word), Ableton prefix
  matching, browser-title routing (browser-scoped), and user overrides
  (`app_profiles` config + Settings UI).
- Red-team hardening pass: focus-change injection guard, clipboard size
  bounds, safe diagnostics + Safe Mode, appearance (light/dark/system),
  snippet `{clipboard}` cap + UI flags, milestone/log reset actions,
  entitlement primitives + licensing/privacy/release docs.

## v0.15.1 — 2026-07-05
- Rolling launch-time backups of the history DB (keep 5) via SQLite online
  backup API.

## v0.15.0 — 2026-07-05
- Context-aware formatting (first cut): verbatim in code editors/terminals,
  terser in chat apps; `context_aware` toggle.
- Double-tap hands-free dictation (double-tap PTT to lock, tap to stop),
  `double_tap_ms` setting. (Built as v0.14.0; first released here.)
- CRITICAL fix: WAL checkpoint after every dictation and on close — a force-
  killed app could previously strand committed history rows in the WAL
  sidecar (data loss).

## v0.13.0 — 2026-07-04
- Private, offline word-count milestones (9 badges, sticky unlocks, tray
  notification) in Insights; lavender ROAR logo in About. Repo made public;
  history DB migrates v2→v3 (`badge_unlocks`).

## v0.12.0 — 2026-07-04
- "Scratch that" spoken undo (standalone utterance, same-window guard,
  UTF-16-exact backspacing, history rollback).
- Manual check-for-updates (GitHub tags, click-only). About credits.

## v0.11.1 — 2026-07-04
- Slim white + lavender capsule overlay (one-row, no status dot, pixel-clamped
  preview text).

## v0.11.0 — 2026-07-04
- Speech cleanup: interjections, stutter collapse, false starts; opt-in
  comma-bounded discourse-filler removal.

## v0.10.0 — 2026-07-03
- ROAR Snippets ("snippet name" / literal `/name`, variables
  {date}/{time}/{clipboard}, packs import/export, Settings tab).
- Multilingual models bundled in the installer (offline language switching).
- Installer moved to external CABs (`.msi` format is capped at 2 GB); later a
  single-file 7-Zip SFX setup exe wraps msi+cabs.

## v0.9.0 — 2026-07-03
- Multilingual dictation: language picker (auto + 100 codes), model policy
  fork (distil-large-v3 is English-only → large-v3-turbo / small).

## v0.8.0 — 2026-07-03
- Cinema Dark settings refresh (indigo accent, SVG iconography, contrast
  fixes).

## v0.7.0 — 2026-07-03
- Streaming preview overlay (waveform pill + live partial text), soft chimes,
  overlay/streaming toggles.

## v0.6.0 — 2026-07-02
- Product renamed FlowLocal → ROAR (exe, installer, data dirs migrated
  in place; GitHub repo renamed).

## v0.5.0 — 2026-07-02
- Custom vocabulary + auto signature-word hotwords.

## v0.4.0 — 2026-07-02
- Insights (totals, activity, pace, top/signature words) + history search.

## v0.3.0 — 2026-07-02
- Local dictation history (SQLite) + privacy controls (retention, delete).

## v0.2.0 — 2026-07-02
- Settings window (pywebview), hotkey capture, autostart, hot-apply config.

## v0.1.0 — 2026-07-02
- Core tray app: push-to-talk local dictation (faster-whisper), SendInput
  injection, packaged exe + MSI.
