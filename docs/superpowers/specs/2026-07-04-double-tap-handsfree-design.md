# Double-Tap Hands-Free Toggle (SP12) — Design

**Version:** v0.14.0
**Date:** 2026-07-04
**Status:** approved

## Goal

Let the user lock dictation on hands-free by double-tapping the existing
push-to-talk hotkey, and stop it with a single tap — so long dictations don't
require holding the key. Push-to-talk (hold) is unchanged.

## Interaction

- **Hold** the PTT hotkey (`hotkey_ptt`, e.g. `ctrl+shift`): record while held,
  inject on release. Identical to today, no added latency.
- **Double-tap** (two quick taps within `double_tap_ms`, default 400 ms): enter
  **hands-free** — recording locks on and continues after release.
- **Single tap** while hands-free: stop and inject.

Recording begins on the very first tap-down, so no speech is lost. A lone
short tap's stop is deferred by the double-tap window; if a second tap lands,
the two fold into ONE continuous session with a single start tone. A hold is
never deferred (finishes immediately on release). A lone tap that captures only
silence is dropped by the existing RMS/min-duration gate.

## Architecture

New pure module `gestures.py` — a `TapToggleDetector` that recognizes the
gesture from timed chord transitions. All timing/state lives here; `app.py`
only wires it to the keyboard hook, recorder, tones, and overlay.

```python
# intents returned by feed()/on_defer_timeout()
START      # begin capturing (PTT)
FINISH     # stop + transcribe + inject
DEFER      # schedule a finish after the double-tap window (cancelable)
HANDSFREE  # cancel any pending defer; lock recording on (hands-free)
STOP       # stop hands-free + transcribe + inject
NONE       # no-op

class TapToggleDetector:
    def __init__(self, double_tap_s=0.4, tap_max_s=0.35): ...
    def feed(self, kind, now) -> str      # kind in {"down","up"}
    def on_defer_timeout(self, now) -> str
```

State machine (pure; `now` in monotonic seconds):

- `feed("down", now)`:
  - hands-free active → `STOP` (reset).
  - else if a completed tap is still within the double-tap window
    (`now - last_tap_up <= double_tap_s`) → second tap: enter hands-free,
    clear `last_tap_up`/`press_start` → `HANDSFREE`.
  - else → new press: `press_start = now` → `START`.
- `feed("up", now)`:
  - hands-free active → `NONE` (release ignored while locked).
  - else if `press_start` set:
    - `dur = now - press_start`; clear `press_start`.
    - `dur <= tap_max_s` → tap: `last_tap_up = now` → `DEFER`.
    - else → hold: clear `last_tap_up` → `FINISH`.
  - else → `NONE`.
- `on_defer_timeout(now)`: if `last_tap_up` set and not hands-free →
  clear it → `FINISH`; else `NONE` (a second tap already cancelled it).

Detector instances are not thread-safe; `app.py` serializes calls with a lock.

## app.py wiring

- `_on_key_event` becomes edge-triggered: track whether the PTT chord was fully
  down before vs after each key event; on the OFF→ON transition call
  `_gesture("down")`, on the ON→OFF transition call `_gesture("up")`. This
  replaces the old "start on chord down / finish on chord-key up (ptt)" logic.
- `_gesture(kind)` (under a `_gesture_lock`): `action = self._detector.feed(kind,
  time.monotonic())`, then map:
  - `START` → `_start_recording("ptt")`
  - `FINISH` / `STOP` → `_finish_recording()`
  - `DEFER` → cancel any prior timer, start
    `threading.Timer(double_tap_s, self._deferred_finish)` (daemon), keep ref.
  - `HANDSFREE` → cancel the pending timer; set `session_mode = "toggle"`;
    `notify("Hands-free dictation on — tap to stop")`. Recording (begun on the
    first tap-down) simply continues.
  - `NONE` → nothing.
- `_deferred_finish()`: `if self._detector.on_defer_timeout(time.monotonic())
  == FINISH: self._finish_recording()`.
- `double_tap_s = cfg["double_tap_ms"] / 1000`, read when (re)creating the
  detector; the detector is (re)built in `__init__` and on config change.

The separate `hotkey_toggle` (`_on_toggle`) is unchanged and still works;
double-tap is an additional path to the same hands-free session.

## Config

`config.DEFAULTS` += `"double_tap_ms": 400`. Sanitized on load: coerce to int,
clamp to `[200, 1000]` (below 200 ms is unhittable, above 1 s feels laggy);
non-numeric falls back to 400.

## Feedback

Reuses existing tones (start on first tap-down, stop on finish) and the overlay
recording state. Entering hands-free adds a one-line tray balloon
("Hands-free dictation on — tap to stop"). No new tone, no overlay change.

## Edge cases (all covered by tests)

- Hold → PTT (immediate finish, never deferred).
- Lone short tap → deferred finish; silence gated, so nothing injected.
- Double-tap → one continuous hands-free session; single tap stops it.
- Hold on the second tap → still hands-free (double-tap commits regardless of
  the second press's duration).
- Triple rapid tap → hands-free on, then immediately stopped by the third tap.
- Defer timer racing a second tap → `on_defer_timeout` returns `NONE` (the
  second tap already cleared `last_tap_up`).

## Testing

- `tests/test_gestures.py`: drive `TapToggleDetector` with synthetic
  timestamps for every case above; assert the exact intent sequence.
- `tests/test_capture_integration.py`: an app-level test feeding chord
  down/up transitions (monkeypatching `time.monotonic`) asserts a double-tap
  ends in `session_mode == "toggle"` and a following tap finishes; a hold still
  finishes immediately.
- `tests/test_config.py`: `double_tap_ms` default + clamp/coerce.
- Existing hotkey/smoke tests stay green (PTT path preserved).

## Release

v0.14.0: version bump, suite ×2, exe, MSI + external cabs, setup exe, frozen +
installed probes, adversarial review, upgrade over 0.13.0 (data intact), fetch
→ push, tag, relaunch, memory.
