# ROAR Home Dashboard — Design Spec

**Date:** 2026-07-06 · **Repo:** `flowlocal` (github xhan145/roar) · **Branch:** `claude/v0.18-home-dashboard` (off `main`, independent of the commercial branch)

**Goal:** Add a polished **Home dashboard** as the default view of the existing Settings window, showing **real local ROAR state**, without rewriting the dictation engine or breaking any existing setting/flow. Product promise stays **"Talk. Type. Locally."**

**Architecture:** The tray/engine and the Settings window are **separate processes**; their only channel is `config.json` (tray polls + hot-applies). We add ONE new one-way channel: the tray writes a small **`status.json`**; the Settings window reads it. No commands cross to the engine in Phase 1. All CSS/JS/assets local; no network, no new deps.

## Global constraints (red-team, verbatim intent)

- No cloud transcription, telemetry, accounts, or background network calls. No external fonts/CDNs/icon-libs/remote assets.
- No subscriptions/license/paywall UI in this task.
- Never break existing sections (General, Hotkeys, Voice & Mic, Transcription, Insights, Privacy, History, Snippets, About) — all stay reachable.
- Privacy controls never gated/moved behind anything paid.
- Never log transcript text into diagnostics/logs; **`status.json` contains no transcript text**, no clipboard, no audio paths, no window titles, no secrets.
- Full window titles never stored by default.
- Keyboard accessible; **`prefers-reduced-motion` freezes** waveform/mic animations.
- App must launch with missing/corrupt history DB, no mic, empty config, and offline. Every dashboard read fails safe.
- No heavyweight frontend framework (repo uses plain HTML/CSS/JS in `settings.html` via a pywebview bridge — keep that).

## Data flow

```
tray/engine process                    settings window process
  ROARApp.set_state() ── writes ──►  status.json  ── read by ──► SettingsAPI.get_home_state()
  (atomic, no transcript)            (data dir)                   + config + history + insights
                                                                  + milestones + context
                                                                          │
                                                                   settings.html #home  (polls ~750ms)
```

## Components

### 1. `status.json` writer (tray side — the only engine-process change)
- `paths.status_path()` → `<_data_dir()>/status.json`.
- New `status.py` helper: `write_status(**fields)` — atomic (temp file + `os.replace`), best-effort (any exception swallowed; engine never affected), bounded fields only.
- `ROARApp.set_state(state)` writes `{state}`; `_finish_recording`/`record_history` path also writes `session_word_count` (accumulated this run), `last_latency_seconds`, `last_injection_status`, `last_profile` (the profile NAME used, never the window title). `session_started_at` written once at launch.
- Allowed fields ONLY: `state, session_started_at, session_word_count, last_latency_seconds, last_injection_status, last_profile, updated_at`. A test asserts the writer rejects/omits anything else and that no transcript-like key is ever written.

### 2. `SettingsAPI.get_home_state()` (settings bridge — `settings_ui.py`)
Returns exactly this shape, every field individually guarded (try/except → safe default / `"Not available"`, never raises):
```
{ app_version, is_running, dictation_state, active_profile, active_profile_description,
  current_model, current_device, injection_method, paste_fallback_enabled, autostart_enabled,
  session_duration_seconds, session_word_count, last_latency_seconds,
  last_transcription_preview, last_transcription_word_count, last_transcription_timestamp,
  last_injection_status, hotkeys, diagnostics_safe_summary,
  words_today, words_this_week, milestone }
```
Sources: `paths.APP_VERSION`; `status.json` (dictation_state/session/last_latency/last_injection/last_profile); `config` (model, device, injection method, paste_fallback, autostart, hotkeys, language); `history.list(limit=1)` for the last-transcription card (**same preview already shown in History** — no new exposure); `history.total_words()`/`insights.compute_insights` for words today/this-week; `milestones.progress(total_words, unlocks)` for milestone; `context._profile()` for the active-profile description. `is_running` is best-effort (status.json fresh `updated_at` within N seconds ⇒ running, else "Not available"). `diagnostics_safe_summary` reuses `diagnostics.collect()` (allowlist only).
**Rules:** no transcript beyond the History preview, no clipboard, no audio paths, no window titles, no secrets. Missing status/db/config ⇒ safe defaults, never crash.

### 3. Home UI (`settings.html`)
- New `<section id="home">`, **default-active**. Structure per prompt: headline "Talk. Type. Locally.", subtitle "Press, speak, and watch your ideas appear."; mic control (blue inner ring `--roar-blue` + orange outer glow `--roar-orange`); inline **SVG waveform** behind the mic (idle CSS keyframe drift; amplitude/intensity switched by `dictation_state`; **frozen when `prefers-reduced-motion`**); state label; hotkey helper (from `hotkeys`); Start/Stop button (**Phase 1: shows hotkey guidance**, not a command); cards Session / Last transcription / Active profile; right panel: active profile (display), quick actions (Open settings / View all settings navigate within the window; Toggle & Scratch-that show the hotkey in Phase 1), settings summary (mic/model/injection/paste-fallback/autostart), View-all; bottom status bar (model/device/paste-fallback + small waveform accent).
- **Theme tokens** added: `--roar-bg/-panel/-card/-border/-text/-muted/-blue/-orange/-green`, layered on the existing dark/light theme; scoped so existing sections are visually untouched. `--roar-blue`≈`#5B8DEF`, `--roar-orange`≈`#F5A623`, `--roar-green`≈`#34D399` (final values in the plan).
- **State mapping:** idle→"Ready"; recording/listening→"Listening…"; transcribing→"Transcribing…"; injecting→"Typing…"; injected→"Injected"; error→calm local message.
- **Live polling:** JS calls a light `get_home_state()` every ~750 ms **only while `#home` is visible** (stop when navigated away). Missing status ⇒ "Ready".

### 4. Sidebar (phased)
- **P1 (additive):** add "Home" as the first sidebar item + default section; existing nav items unchanged. `navs=` smoke assert updated (+1).
- **P2 (re-map, after P1 smoke green):** sidebar becomes Home / Profiles / Insights / History / Dictionary / Hotkeys / Settings / About. "Profiles"→existing app-profiles section, "Dictionary"→existing vocabulary section, "Settings"→an overview that links to the existing General/Voice/Transcription/Privacy/Snippets/Cleanup sections (kept intact internally; old `data-s` targets still resolve). Update smoke nav assertions.

### 5. Phase 3 (deferred, behind a feature flag)
Command-file IPC (`command.json`) so Start/Stop/Scratch-that remote-control the engine, added ONLY after status polling is proven stable + tested, and gated by a config/feature flag defaulting OFF. Not implemented in this spec's build.

## Error handling
Every backend read wrapped; `get_home_state` returns safe defaults on any failure. Status writer never raises into the engine. Home renders with all-`"Not available"` if the bridge returns nothing. Reduced-motion respected.

## Testing
- `get_home_state()` returns safe defaults with no status/db/config; redacts private data (no transcript beyond History preview, no clipboard/audio/window-title keys).
- `status.write_status` only emits allowlisted keys; rejects transcript-like fields; atomic.
- Home section exists + is default; sidebar nav works; **all existing sections still present** (extend `test_settings_smoke.py` markers).
- Reduced-motion CSS exists; no external URLs/CDN/`http(s)://` asset refs added to `settings.html`; no new network calls in `settings_ui.py`/`status.py`.
- App-launch resilience covered by existing smoke + a `get_home_state` corrupt-status test.

## Out of scope
Command IPC / remote Start-Stop-Scratch (P3/flag), system vitals (CPU/RAM/battery), Recent Activity feed, any paywall/License UI. Version bump reconciled at merge time vs the parallel commercial branch (which took 0.17.0).

## Phasing / commit plan
P1: `paths.status_path` + `status.py` + tray writer → `get_home_state` → Home section + CSS/JS + polling → add-Home sidebar → tests. P2: sidebar re-map + Settings overview → tests. Version bump last.
