# FlowLocal Settings Window — Design Spec

**Date:** 2026-07-02
**Status:** Approved (interactive brainstorm; layout + style chosen via visual companion)
**Sub-project:** 1 of 6 in the FlowLocal upgrade track (settings/UI foundation). Later sub-projects — 2: history+privacy, 3: word analytics+speech profile, 4: custom vocabulary, 5: streaming dictation, 6: multilingual — get their own specs and plug into this shell.

## Goal

A real settings window for FlowLocal (currently config.json + tray menu only): Windows-11-style sidebar navigation, Deep Focus visual style, hybrid apply, plus a start-with-Windows toggle. Wire the essentials now; ship the navigation shell with placeholder tabs for what's coming.

## Locked decisions

- **Scope v1:** essentials wired (auto-start, tones, paste fallback, sensitivity, mic device, hotkeys, model). Full nav shell including grayed **Privacy** and **History** tabs ("coming soon" panels). The replacements (spoken-command) editor stays in config.json for v1.
- **Layout:** left sidebar rail (user-picked A). Window ~900×640, min 760×560.
- **Style:** **Deep Focus** (user-picked): near-black `#0B0E14` background, sidebar `#070A0F`, cards `#121722` with `#1E2635` borders, text `#E8ECF4`, muted `#9AA4BC`, disabled `#3E4557`, accent `#2563EB` with a soft glow on active elements (`box-shadow: 0 0 10-12px rgba(37,99,235,.25-.6)`). Uppercase section headings, letter-spacing .02em. State colors stay consistent with the tray: blue active, red recording. Segoe UI. Per UUPM: contrast ≥4.5:1 for body text on `#121722`, states differ by more than color, focus rings visible, reduced-motion respected (no glow animation, static shadows only).
- **Tech:** pywebview (Edge WebView2, preinstalled on Win11) rendering a bundled single-file `settings.html` (inline CSS/JS). JS↔Python via `js_api`. No server, no ports.
- **Apply model:** hybrid. Instant-apply: auto-start, tones, paste fallback, silence sensitivity, mic device. Explicit **Apply**: hotkeys, model (disruptive: re-hook / model reload). Apply shows "applying…" then confirms.

## Architecture

Separate process. Tray menu gains **"Settings…"** (primary; "Open config" stays as an escape hatch below it).

```
tray app (app.py)                     settings process (app.py --settings)
  config watcher thread  <--mtime--   writes config.json via bridge
  diff_config(old,new)->actions       pywebview window + settings.html
  apply: rehook / reload / device     autostart.py writes HKCU Run key
```

- `app.py --settings`: skips main mutex, hotkeys, tray, model. Own mutex `Global\FlowLocalSettings` (second settings launch just exits; pywebview brings no focus API worth chasing in v1).
- **Config watcher** (tray app): daemon thread polls `config.json` mtime every 2s. On change: load, `diff_config(active, new) -> [actions]`, apply. Actions: `rehook` (unhook_all + re-register both hotkeys), `reload_model` (enqueue existing `("reload", name)` job), `set_device` (recorder.device), `none` (keys read at use-time: tones, thresholds, paste_fallback, replacements). `diff_config` is a pure function.
- **Bridge API** (`settings_ui.py`, class exposed as `js_api`):
  - `get_state() -> {config, autostart: bool, devices: [[idx, name]], models: [...], version, log_path, config_path}`
  - `set_value(key, value)` — instant keys: validate, write config.json
  - `apply_hotkeys(ptt, toggle) -> {ok} | {error}` — validate via `parse_chord`, write both keys
  - `apply_model(name) -> {ok}` — write model key
  - `set_autostart(enabled) -> {ok} | {error}` — registry via autostart.py
  - `capture_hotkey() -> {hotkey} | {error}` — global capture (below)
- **`autostart.py`** (pure, testable): `get(name, exe_cmd) -> bool`, `set(name, exe_cmd, enabled)` on `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`. Command: frozen → path to FlowLocal.exe; source → `pythonw.exe <abs app.py>`. No admin required.
- **Hotkey capture:** browser JS cannot see the Win key. "Set hotkey" button calls `capture_hotkey()`: Python uses the `keyboard` lib (global hook) to record the held combo — keys collected until first release or 5s timeout — normalized to a hotkey string ("left windows"→"windows" etc.), validated, returned to the UI. Field shows the candidate; **Apply** commits.

## UI structure

Sidebar: **General**, **Hotkeys**, **Voice & Mic**, **Transcription**, ~~Privacy~~ (soon), ~~History~~ (soon), **About**.

- **General:** Start FlowLocal with Windows (toggle, instant, registry); Audio feedback tones (toggle, instant).
- **Hotkeys:** push-to-talk + toggle-mode rows, each: current hotkey chip, "Set hotkey" capture button; shared **Apply** + inline validation errors; note about Win+Ctrl+Space input-method conflict.
- **Voice & Mic:** input device dropdown (from `recorder.list_input_devices()`, instant); silence sensitivity slider mapped to `silence_rms_threshold` (0.001–0.02 log scale, instant) with plain-language caption; Fallback paste mode toggle (instant).
- **Transcription:** model radio group (auto / tiny.en / base.en / small.en / medium.en / distil-large-v3) with size/speed captions; **Apply**; status line showing active model + device from last `get_state()`.
- **Privacy / History:** lock icon panel — one sentence on what's coming (sub-projects 2–3).
- **About:** version, config/log paths (click = open), GitHub link, "100% local" statement.

## Error handling

- WebView2 unavailable → catch pywebview failure, open config.json in Notepad + tray notification (graceful degradation).
- Registry read/write failure → `{error}` to UI, toggle reverts, message inline.
- Invalid/empty hotkey capture → `{error: reason}`, field unchanged.
- Settings process crash → tray app unaffected (separate process).
- Watcher reads corrupt config.json → existing `config.load` fallback keeps defaults; watcher skips apply on parse failure (no thrash).

## Testing

- Unit: `autostart` round-trip using a temp value name (`FlowLocalTest-<pid>`), always deleted in teardown; `diff_config` mapping for each action class; bridge handlers called directly with a tmp config path; sensitivity slider mapping function.
- Integration: `app.py --settings --smoke` opens the window, self-closes ~2s, exits 0, logs markers (mirrors existing smoke pattern).
- Existing 34-test suite stays green.
- Packaging: `settings.html` added as a data file in `flowlocal.spec` + pywebview collected; rebuild exe and verify Settings opens from the frozen tray.

## Out of scope (v1)

Replacements editor UI, live mic level meter, theme switcher (Deep Focus only), settings search, per-app profiles, Privacy/History functionality (sub-projects 2–3), streaming (5), multilingual (6).

## Version

Ships as v0.2.0 (tag) with the existing incremental-commit + push workflow on `main`.
