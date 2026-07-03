# ROAR Streaming Dictation + Live Overlay — Design Spec

**Date:** 2026-07-03
**Status:** Approved ("approved and work autonomously")
**Sub-project:** 5 of 6. Ships as v0.7.0.

## Goal

While dictating, the user sees a small always-on-top pill with a live waveform
and their words appearing in real time; the final transcript is injected once
on hotkey release (unchanged accuracy and safety). Feedback tones become soft
chimes.

## Locked decisions

- **Preview-only streaming**: partial transcripts render in the overlay; text
  is injected into the target app ONLY on finish. No injected partials, no
  backspace correction (unsafe in terminals/forms/editors).
- **Overlay**: stdlib tkinter on a dedicated thread inside the tray process
  (no new deps, direct access to levels/partials). Borderless, always-on-top,
  Deep Focus pill (~400×76) at bottom-center (y = screen_h − 140). Contents:
  red recording dot, ~24 live level bars (accent #2563EB on #0B0E14, rounded
  via `-transparentcolor` trick), one line of partial text (tail-truncated,
  #E8ECF4). States: hidden / recording / transcribing ("…", bars dimmed).
  Appears on record start, hides after injection. Cosmetic-only: any overlay
  failure logs and never affects dictation.
- **Streaming engine**: sliding-window re-transcription on the existing single
  worker thread. `Recorder.snapshot()` returns a copy of the buffer without
  stopping; partials transcribe the last `15 s` tail (`tail_window`), display
  the hypothesis. Cadence self-paces: next partial ≥ `max(0.7 s, last partial
  wall time)`. Generation counter: `_finish_recording` bumps the session gen
  and enqueues the final job; stale partial jobs are skipped; the final always
  wins. Partials skip buffers < 0.6 s. Final path is byte-identical to today.
- **Sounds**: `make_chime` — two overlapping sine notes with exponential-decay
  envelopes, amp 0.07: start C5→E5 (rise), stop E5→C5 (fall), error = double
  low thud (165 Hz, fast decay). Same `TONES` keys, `tones_enabled` respected.
- **Config**: `overlay_enabled: true`, `streaming_preview: true` — both
  instant keys (read at use; no diff_config action), toggles in Settings →
  General. `streaming_preview: false` ⇒ waveform-only overlay.
  `overlay_enabled: false` ⇒ no pill at all (today's behavior).

## Components

- **`overlay.py` (new)**: `class Overlay` — `start()` (spawn Tk thread;
  withdrawn root; all Tk calls confined there via a command `queue.Queue`
  drained by `root.after(33, ...)`), `show_recording()`, `push_level(f)`
  (0..1, deque maxlen 24), `set_partial(text)`, `show_transcribing()`,
  `hide()`, `stop()`. Pure helpers exposed for tests:
  `normalize_level(rms) -> float` (min(1, rms/0.08)),
  `bar_heights(levels, n=24, h=28) -> list[int]`,
  `tail_text(text, max_chars=52) -> str` (ellipsis head).
  Tk import failure or thread crash ⇒ `available=False`, all methods no-op.
- **`recorder.py`**: `Recorder(on_level=None)` — callback computes block RMS
  and calls `on_level(normalize_level(rms))`; `snapshot() -> np.ndarray`
  (lock-guarded concat copy; empty array when not recording).
  `tail_window(audio, seconds=15.0) -> np.ndarray` (pure).
  `make_chime(...)` + rebuilt `TONES`.
- **`app.py`**: owns `self.overlay` (created when `overlay_enabled`, started
  in `run()`, stopped in `_quit`). `_start_recording`: overlay.show_recording
  + enqueue `("partial", gen)` when `streaming_preview`. Worker handles
  `("partial", gen)`: skip if gen != current or state != RECORDING; snapshot →
  tail_window → transcribe (existing hotwords apply) → overlay.set_partial →
  re-enqueue next partial for same gen after pacing. `_finish_recording`:
  gen += 1, overlay.show_transcribing, enqueue final. After injection (or
  gate/empty): overlay.hide. Recorder constructed with
  `on_level=self._on_level` → forwards to overlay when visible.
- **`settings_ui.py` / `settings.html`**: INSTANT_KEYS += `overlay_enabled`,
  `streaming_preview` (bool coerce); two toggles in General ("Show the
  dictation pill while recording", "Live text preview in the pill"); probe
  adds `ovl=1` (toggle element present).
- **`config.py`**: the two new DEFAULTS keys.

## Error handling

- Overlay: every public method wrapped; failure marks unavailable + one log
  line; dictation continues.
- Partial transcription exception: logged once per session, overlay falls
  back to waveform-only; NEVER notifies (final path unaffected).
- Pacing guarantees the worker is never saturated: partials are enqueued only
  after the previous one completes; the queue never holds more than one
  partial; finals jump ahead functionally via the gen check (stale partials
  drain fast as no-ops).
- Toggle mode long sessions: tail_window caps compute; partial text shows the
  window's hypothesis (good enough for preview).

## Testing

- `tests/test_overlay.py`: pure helpers (normalize_level bounds, bar_heights
  mapping incl. empty, tail_text truncation); lifecycle smoke — start, show,
  push levels, set_partial, transcribing, hide, stop with no exceptions and
  `available` true (machine has Tk; if Tk init races, retry pattern from
  test_injector applies).
- `tests/test_streaming.py`: `tail_window` (short buffer passthrough, long
  buffer cut, empty); snapshot returns copy + empty-when-idle; generation
  staleness via the capture-test harness (`_make_app`): stale gen partial
  → no overlay update, no crash; live gen partial → transcriber called with
  windowed audio (stub transcriber records call).
- `tests/test_gate.py` additions: chime shape (duration, dtype, |amp| ≤ 0.08,
  decaying tail), TONES keys unchanged.
- Settings probe asserts `ovl=1`; version asserts → 0.7.0.
- Live: GPU partial cadence observed in roar.log (`partial in X.XXs` debug
  lines); full release train (exe + MSI upgrade over 0.6.0, ProductsEx single
  registration, data preserved), adversarial review pre-push, tag v0.7.0,
  relaunch, MEMORY.md updated.

## Out of scope

Injected partials/segment commit, overlay drag/reposition UI, per-app overlay
rules, multilingual (SP6).
