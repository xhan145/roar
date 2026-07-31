# ROAR desktop fob — movable, controllable pill — Design

**Date:** 2026-07-31 · **Status:** approved (user waived review gate; autonomous
build) · **Repo:** `xhan145/roar`

## Goal

Bring the ROAR Android fob experience to Windows: the dictation pill becomes an
always-visible, draggable, clickable control — tap to toggle hands-free
dictation, drag to move (position persists), right-click for quick actions.

## Decisions (user-approved)

1. **One control.** The existing overlay pill is upgraded in place — no second
   floating window. Idle it collapses to a small round mic dot; while dictating
   it expands into the existing waveform pill at the fob's location.
2. **Interactions v1:** tap = toggle hands-free dictation (the double-tap-hotkey
   code path); drag = move + persist; right-click = mini menu (Scratch that,
   Read selected text, Open Settings, Hide fob). No hold-to-talk on the fob.
3. **On by default.** `fob_enabled` defaults True; "Hide fob" persists it off;
   re-enable from Settings → Voice & Mic or the tray.
4. **Architecture:** extend the existing Tk overlay window/thread (option A).
   No new window system.

## The invariant: never steal focus

Clicking the fob must not change the foreground window — otherwise the "focused
app at tap time" is the fob itself and dictation has no target. The Tk toplevel
gets `WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW` via ctypes
(`GetParent(root.winfo_id())`, `Get/SetWindowLongPtrW(GWL_EXSTYLE)`).
If applying the style fails, the fob degrades to display-only: tap and menu are
disabled (logged once), drag still works, dictation via hotkeys is unaffected.
Non-Windows platforms skip the style and keep tap enabled (different focus
semantics; the Linux port is experimental).

## Components

### `fob.py` — pure helpers (no Tk, fully unit-tested)

- `DRAG_THRESHOLD_PX = 6`
- `class GestureClassifier` — feed it `press(x, y)`, `move(x, y)`,
  `release()`; it returns `"tap"` or `"drag"` on release, and during a drag
  `move()` returns the `(dx, dy)` offset from the press point (None until the
  threshold is crossed). A press that never crosses the threshold is a tap.
- `clamp_pos(x, y, w, h, bounds, margin=4)` — keep a `w×h` window fully inside
  `bounds=(left, top, right, bottom)`; bounds may have negative origins
  (multi-monitor virtual screen).
- `default_pos(bounds, w, h)` — bottom-center of the primary work area.
- `validate_pos(pos, w, h, bounds)` — a persisted position is honoured only if
  at least half the window is inside the current virtual screen; otherwise
  None (caller falls back to `default_pos`). Guards against unplugged
  monitors.
- `expand_anchor(dot_x, dot_y, dot_size, pill_w, pill_h, bounds)` — top-left
  for the pill so it is centred on the dot where possible and clamped inside
  bounds.

### `overlay.py` — upgraded window

- New mode `"dot"` beside recording/transcribing/hidden. Dot: 34×34 window,
  white circle with lavender ring + mic glyph drawn on the canvas (same
  transparent-color trick for round corners).
- `set_fob(enabled, pos)` (thread-safe, posted): enabled + idle → show dot at
  `pos` (validated, else default); disabled + idle → withdraw. Mode
  transitions: `show_recording()` expands to the pill at
  `expand_anchor(...)`; `hide()` now returns to the dot when the fob is
  enabled instead of withdrawing.
- Mouse bindings on the canvas (all modes): Button-1 press/motion/release feed
  a `GestureClassifier`; drag moves the window live (`geometry(+x+y)`); a drag
  release clamps, then calls `on_move(x, y)`; a tap calls `on_tap()`.
  Button-3 posts a `tk.Menu` (tearoff=0) with the four actions calling
  `on_menu(action_id)`.
- Callbacks (`on_tap`, `on_menu`, `on_move`) are injected by the app,
  exception-wrapped — the overlay stays cosmetic-safe: any callback failure is
  swallowed and logged, the window never dies.
- Virtual-screen bounds from `GetSystemMetrics(SM_*VIRTUALSCREEN)` via ctypes,
  falling back to Tk's screen size.
- Everything stays on the existing Tk thread + command queue; the 4 Hz hidden
  idle tick becomes the dot's cadence too (the dot is static; 30 fps only
  while the pill is visible).

### `app.py` wiring

- Config: `fob_enabled` (bool, default True), `fob_pos` ([x, y] or null).
- Overlay constructed with callbacks: tap → the same toggle entry the
  double-tap hotkey uses; menu scratch → `_scratch()`; read_selected →
  `_dispatch_tts_command({"command": "read_selected"})`; settings →
  `_open_settings()`; hide → persist `fob_enabled=False`, collapse, notify
  ("Fob hidden — re-enable in Settings → Voice & Mic").
- on_move persists `fob_pos` (under `cfg_lock`).
- `diff_config`: `fob_enabled` change → apply live; startup applies config
  state after `overlay.start()`.
- Tray menu: "Show mic fob" checkbox.

### Settings UI

Voice & Mic section: "Show floating mic fob" toggle (`t-fob`, instant key
`fob_enabled`) with a hint naming tap/drag/right-click. Smoke probe gains
`fob=1`.

## Error handling

- Fob is cosmetic-plus: every mouse handler and callback is try/excepted; a
  failure disables the failing interaction, never dictation.
- NOACTIVATE failure → display-only fob (see invariant).
- Persisted off-screen position → reset to default at startup.
- Menu actions run via the injected callbacks on the Tk thread; each is
  exception-wrapped and the heavy work (toggle, TTS) already hops threads in
  the app.

## Testing

- `tests/test_fob.py` — classifier state machine (tap under threshold, drag
  over, offsets, re-press after release), clamp/validate/default/expand math
  including negative-origin bounds and the unplugged-monitor reset.
- Config round-trip for `fob_enabled` / `fob_pos`; `diff_config` action.
- Existing overlay pure-helper tests keep passing.
- Settings smoke: `fob=1`.
- Live verification on this machine: NOACTIVATE (foreground window unchanged
  after a fob tap), drag persistence across an app restart.

## Out of scope

Hold-to-talk on the fob, snap-to-edge animation, opacity/auto-fade, per-monitor
DPI polish beyond clamping, Linux focus-style parity.
