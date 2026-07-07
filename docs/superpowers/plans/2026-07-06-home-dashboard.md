# ROAR Home Dashboard — Implementation Plan

> REQUIRED SUB-SKILL: superpowers:executing-plans. Checkbox steps.

**Goal:** Add a real, safe Home dashboard to the Settings window (default view) reflecting live local ROAR state via a one-way `status.json`, without touching the dictation engine beyond an additive status write. Phased.

**Global constraints:** no network/CDN/external assets/new deps; no paywall UI; existing sections stay reachable; `status.json` carries NO transcript/clipboard/audio-path/window-title/secret; `prefers-reduced-motion` freezes animation; every read fails safe; app launches with missing db/config/mic/offline.

---

### Task 1 — `status.py` + `paths.status_path` (tray→settings channel)
**Files:** Create `status.py`; Modify `paths.py`; Test `tests/test_status.py`.
- [ ] `paths.status_path()` = `os.path.join(_data_dir(), "status.json")`.
- [ ] `status.ALLOWED = {"state","session_started_at","session_word_count","last_latency_seconds","last_injection_status","last_profile","updated_at"}`.
- [ ] `write_status(path=None, **fields)`: keep only ALLOWED keys, add `updated_at` (epoch), atomic write (`path+".tmp"` then `os.replace`), swallow all exceptions (return False), never raise.
- [ ] `read_status(path=None)`: return dict or `{}` on any error.
- [ ] Tests: only allowlisted keys persist; a `transcript`/`clipboard`/`window_title` field is dropped; corrupt file → `{}`; write is atomic (no partial on simulated failure).
- [ ] Commit: `feat: status.json helper (atomic, allowlisted, tray→settings)`.

### Task 2 — tray writes status on state change
**Files:** Modify `app.py`.
- [ ] At launch: `status.write_status(state="idle", session_started_at=<epoch>, session_word_count=0)`.
- [ ] In `set_state(state)`: `status.write_status(state=state)` (best-effort, after the lock).
- [ ] In the finish/record path: accumulate `self._session_words += words`; write `session_word_count`, `last_latency_seconds`, `last_injection_status`, `last_profile` (profile NAME from the existing profile resolution — never a window title).
- [ ] Guard every call so a status failure cannot affect dictation.
- [ ] Verify: run `python -m pytest tests/test_smoke.py -q` is unaffected (or pre-existing env fail only); manual: dictate once, confirm `status.json` appears with no transcript text.
- [ ] Commit: `feat: tray writes live dictation status (no transcript)`.

### Task 3 — `SettingsAPI.get_home_state()`
**Files:** Modify `settings_ui.py`; Test `tests/test_home_state.py`.
- [ ] Implement `get_home_state()` returning the full shape from the spec; each field try/except → safe default / `"Not available"`; never raises.
- [ ] `dictation_state`/session/last_* from `status.read_status()`; `is_running` = status `updated_at` within 15 s; model/device/injection/paste_fallback/autostart/hotkeys/language from `config`; last-transcription card from `history.list(limit=1)` (preview only — same as History); `words_today`/`words_this_week` from history rows filtered by ts; `milestone` from `milestones.progress(history.total_words(), history.unlocks())`; `active_profile`(+description) from `status.last_profile` / `context._profile`; `diagnostics_safe_summary` = `diagnostics.collect(...)`.
- [ ] Tests: with no status/db → safe defaults, no exception; returned dict has NONE of `transcript`(full)/`clipboard`/`audio`/`window_title`/`signature` keys; last_transcription_preview is bounded (≤160 chars).
- [ ] Commit: `feat: get_home_state safe composite bridge`.

### Task 4 — Home section HTML + `--roar-*` tokens + CSS
**Files:** Modify `settings.html`.
- [ ] Add `--roar-bg/-panel/-card/-border/-text/-muted/-blue/-orange/-green` to `:root` (+ light overrides), values harmonized with existing theme.
- [ ] Add `<section id="home">` with headline/subtitle, mic control (blue ring + orange glow), inline SVG waveform, state label, hotkey helper, Start/Stop button (hotkey-guidance), 3 cards, right panel (profile, quick actions, settings summary, view-all), bottom status bar.
- [ ] Mic pulse + waveform animations wrapped in `@media (prefers-reduced-motion: no-preference)`; static otherwise.
- [ ] No `http`/`https`/CDN refs; inline SVG only; reuse local logo asset.
- [ ] Commit: `feat: Home dashboard section + roar theme tokens`.

### Task 5 — sidebar add-Home + JS wiring + live polling
**Files:** Modify `settings.html`; Modify `tests/test_settings_smoke.py`.
- [ ] Add "Home" nav button as first item; make `#home` the default active section (move `aria-current` to Home).
- [ ] `renderHome(state)` fills fields from `get_home_state()`; state→label/waveform mapping; quick-action buttons call existing section-nav (Open/View settings) or show hotkey.
- [ ] Poll `get_home_state()` every 750 ms only while `#home` visible; clear interval on nav-away; guard against bridge errors.
- [ ] Update smoke: `navs` count +1, add a `home=1` marker + `home-default` check; keep all existing markers.
- [ ] Run `pytest tests/test_settings_smoke.py -q` → PASS.
- [ ] Commit: `feat: wire Home dashboard (default view, live status polling)`.

### Task 6 — P2 sidebar re-map + Settings overview
**Files:** Modify `settings.html`; Modify `tests/test_settings_smoke.py`.
- [ ] Re-label/reorder sidebar to Home / Profiles / Insights / History / Dictionary / Hotkeys / Settings / About. Profiles→app-profiles section, Dictionary→vocabulary section, History→history/privacy, Settings→new overview.
- [ ] Add a Settings overview section with cards linking to existing General/Voice/Transcription/Privacy/Snippets/Cleanup sections (existing sections + `data-s` targets kept intact).
- [ ] Update smoke nav asserts to the new structure; confirm every old section still reachable.
- [ ] Run full `pytest -q`; only the pre-existing env smoke fail allowed.
- [ ] Commit: `feat: re-map sidebar to 8-item IA + Settings overview`.

### Task 7 — verify + docs + version
**Files:** Modify `paths.py` (version at merge), `CHANGELOG.md`, README dashboard note.
- [ ] Live-verify the Settings window renders Home (preview tooling) with safe fallbacks.
- [ ] Full suite green (minus pre-existing env smoke). Red-team grep: no `http(s)://` asset/CDN added; no new network import in status.py/settings_ui.py home path; status.json has no transcript.
- [ ] Version bump coordinated with the commercial branch; `roar_versions.py --fix`.
- [ ] Commit: `chore: dashboard changelog + version`.

## Self-review
Spec coverage: status channel (T1-2), bridge (T3), UI+theme (T4), wiring+polling+add-Home (T5), re-map (T6), verify/version (T7). Types consistent: `write_status`/`read_status`, `status_path`, `get_home_state` shape, `--roar-*` tokens. No placeholders.
