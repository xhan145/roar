# Point & Speak Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ctrl+Right-click any highlighted text anywhere on screen → ROAR speaks it immediately; same gesture stops it.

**Architecture:** New `mouse_hook.py` (pure `should_trigger` decision + Win32 WH_MOUSE_LL shell on its own thread, never eats the click). app.py owns lifecycle (`_sync_pointer_gesture`) and routes gestures to the existing `read_selected`/`stop` command path. Two `tts_`-prefixed config keys ride the existing `reload_tts_config` diff action.

**Tech Stack:** ctypes/Win32 (SetWindowsHookExW, GetAsyncKeyState), existing tts command path, pywebview settings toggle.

## Global Constraints
- Off by default (`tts_pointer_gesture_enabled: false`); hook installed only when that AND `tts_enabled` are true.
- Hook callback: observe-only, no I/O, always CallNextHookEx; debounce 300 ms; self-heal one restart.
- Capture/speak/stop paths unchanged (`tts.text_sources`, `_dispatch_tts_command`).
- Full suite stays green; settings smoke gains a `ptr=1` marker.

### Task 1: mouse_hook.py pure logic + tests
- `should_trigger(msg, ctrl_down, enabled, now, last_fire, debounce_s=0.3) -> bool`
- Tests: WM_RBUTTONUP+ctrl+enabled+past debounce → True; wrong msg / no ctrl / disabled / within debounce → False.

### Task 2: PointerGestureHook (Win32 shell)
- Thread with SetWindowsHookExW(WH_MOUSE_LL) + message pump; `start()`/`stop()` idempotent; posts via `on_gesture()` callback; one-shot self-heal; never blocks (CallNextHookEx always). Windows-only import guards. Test: lifecycle with a stubbed backend where feasible; real behavior verified live.

### Task 3: config + app wiring + tests
- config.py DEFAULTS: `tts_pointer_gesture_enabled: False`, `tts_pointer_gesture_modifier: "ctrl"`.
- app.py: `self._pointer_hook` (created lazily), `_sync_pointer_gesture()` called on tray-ready and in the `reload_tts_config` watcher branch; `_on_pointer_gesture()` → if `self.tts_service.active` → dispatch `{"command":"stop"}` else thread-dispatch `{"command":"read_selected"}` (mirrors hotkey path).
- Tests: gesture→read_selected dispatch; speaking→stop; disabled→no hook start (fakes).

### Task 4: settings UI + smoke
- settings_ui: add `tts_pointer_gesture_enabled` to `_TTS_SETTINGS`; probe `ptr=1` (toggle element exists).
- settings.html: toggle row in `#readaloud` ("Speak selection on Ctrl + Right-click"), `setToggle`+`toggleSetting` wiring; smoke test asserts `ptr=1`.

### Task 5: docs + full suite + live verify
- TTS_TROUBLESHOOTING note (elevated windows; gesture passes click through). CHANGELOG unreleased entry.
- Full suite green; live check on this machine: enable → Ctrl+right-click selection in two apps → speech; gesture again → stop; plain right-click unaffected.
