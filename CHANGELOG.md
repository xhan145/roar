# Changelog

All notable changes to ROAR. Dates are release-tag dates; entries before a tag
exists are marked unreleased.

## v0.16.0 — unreleased (source)
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
