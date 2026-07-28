# Point & Speak — Ctrl+Right-click reads the selection aloud

**Date:** 2026-07-27 · **Target:** Windows desktop (tray process) · **Status:** approved

## Goal

Highlight text in ANY application, **Ctrl + right-click**, and ROAR speaks the
selection immediately — one gesture, no menu, no extra click. The same gesture
while speech is playing stops it.

## Decisions (user-approved)

- **Trigger:** global low-level mouse hook, **Ctrl + right-click** (modifier
  configurable later; stored in config now).
- **No popup menu:** the gesture IS the command ("one pass autonomously").
- **Toggle:** gesture during active speech = stop, not re-capture.
- **Off by default:** opt-in toggle in Settings → Read Aloud.

## Why not a real right-click menu item

Windows shell context menus extend files/folders/desktop — not text selections
inside arbitrary apps. Each app owns its own text menu; there is no supported
system-wide injection point. A modifier'd global mouse hook plus ROAR's own
action is the honest equivalent, and plain right-click is left untouched.

## Reuse (nothing re-implemented)

- **Capture:** `tts.text_sources.read_selected_text` — UIA selection first,
  opt-in Ctrl+C-with-clipboard-restore fallback; refuses password/protected
  fields and non-text clipboards. Unchanged.
- **Speak/stop:** the existing `read_selected` / `stop` command path
  (`ROARApp._dispatch_tts_command`). Unchanged.
- **New work is the trigger only.**

## Components

### mouse_hook.py (new)
- `should_trigger(msg, ctrl_down, enabled, now, last_fire)` — pure decision:
  True only for `WM_RBUTTONUP` with Ctrl held, feature enabled, and ≥0.3s since
  the last fire (debounce). Unit-testable anywhere.
- `PointerGestureHook(on_gesture)` — Win32 `SetWindowsHookExW(WH_MOUSE_LL)` via
  ctypes on a dedicated thread with its own message pump.
  - Handler observes only: checks message + `GetAsyncKeyState(VK_CONTROL)`,
    posts to the app queue, ALWAYS `CallNextHookEx` — the click is never eaten;
    the app under the cursor still shows its own menu.
  - Handler does no I/O; sub-millisecond budget (Windows removes slow hooks).
  - Self-heal: if the hook dies, one restart attempt, then a tray notification.
  - `start()` / `stop()` idempotent; installed only while the setting AND
    `tts_enabled` are both on; config change re-evaluates immediately.

### app.py wiring
- On gesture event: if TTS state is active speech → dispatch `stop`; else →
  dispatch `read_selected` (existing error paths give calm notifications for
  "nothing selected"/refusals; elevated windows fail the same calm way).
- Hook lifecycle tied to `diff_config` (`tts_pointer_gesture_enabled`,
  `tts_enabled`).

### config
- `tts_pointer_gesture_enabled: false` (default), `tts_pointer_gesture_modifier:
  "ctrl"` (stored for future configurability; only "ctrl" honored in v1).

### Settings UI
- Toggle in Read Aloud section: "Speak selection on Ctrl + Right-click"; only
  meaningful when Read Aloud is enabled. Smoke-probe marker.

## Error handling
- Nothing selected / unreadable / elevated window: existing TextSourceError →
  tray notification; gesture never blocks or eats the click.
- Hook install failure: notification once, feature stays off, app unaffected.
- Debounce 300 ms.

## Testing
- Pure: `should_trigger` truth table + debounce.
- Wiring: gesture event → `read_selected` dispatch; speaking → `stop`;
  disabled → no dispatch (fake TTS service).
- Live on this Windows machine: enable, select text in two real apps,
  Ctrl+right-click → speech; gesture again → stop; plain right-click unchanged.

## Out of scope
- Popup/menu UI, non-Ctrl modifiers UI, Linux/X11 pointer gesture, elevated-
  window capture (UIPI), secure surfaces.
