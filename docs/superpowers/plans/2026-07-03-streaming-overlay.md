# ROAR Streaming + Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Live dictation pill (realtime waveform + streaming text preview), preview-only streaming via sliding-window re-transcription, soft chime tones; v0.7.0.

**Architecture:** `overlay.py` runs Tk on a dedicated thread (commands via queue, 33 ms tick); recorder feeds RMS levels and exposes lock-safe `snapshot()`; the existing worker gains a `("partial", gen)` job that transcribes the buffer tail and self-reschedules via a daemon `threading.Timer`; a session generation counter makes the final always win. Tones become enveloped chimes.

**Tech Stack:** stdlib tkinter + numpy. No new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-03-streaming-overlay-design.md` (normative). Preview-only: injected text path byte-identical to today.
- Overlay is COSMETIC: any failure logs once and never affects dictation. All public Overlay methods are exception-proof.
- Worker must never sleep for pacing (a queued final would stall): pacing = daemon `threading.Timer` re-enqueue.
- Worker's IDLE reset after jobs must NOT fire for partial jobs (state stays RECORDING).
- `paths.APP_VERSION = "0.7.0"` in the release task; probes add `ovl=1`; kill ROAR.exe + its webview children before tests/builds; builds strictly serialized; `git status` before adds.

---

### Task 1: recorder — levels, snapshot, tail_window, chimes (TDD)

**Files:** Modify `recorder.py`; Test: append to `tests/test_gate.py`, new `tests/test_streaming.py`

**Interfaces:**
- Produces: `normalize_level(rms_val: float) -> float` (min(1, rms/0.08));
  `tail_window(audio: np.ndarray, seconds: float = 15.0) -> np.ndarray` (pure);
  `Recorder(device=None, on_level=None)` — `_callback` calls `on_level(normalize_level(block_rms))` (exception-proof); `snapshot() -> np.ndarray` (lock-guarded concat copy; empty when no chunks);
  `make_chime(freqs: list[float], note_ms=110, overlap_ms=40, amplitude=0.07) -> np.ndarray`; rebuilt `TONES` = start C5→E5 rise, stop E5→C5 fall, error double 165 Hz thud. `make_tone` kept unchanged.

- [ ] **Step 1: failing tests.** Append to `tests/test_gate.py`:

```python
def test_chimes_shape_and_softness():
    for key in ("start", "stop", "error"):
        tone = recorder.TONES[key]
        assert tone.dtype == np.float32
        assert np.max(np.abs(tone)) <= 0.08          # soft
        # decaying tail: last 10% quieter than global peak
        tail = tone[-len(tone) // 10:]
        assert np.max(np.abs(tail)) < np.max(np.abs(tone)) * 0.5


def test_make_chime_two_notes_longer_than_one():
    one = recorder.make_chime([523.25])
    two = recorder.make_chime([523.25, 659.25])
    assert len(two) > len(one)


def test_normalize_level_bounds():
    assert recorder.normalize_level(0.0) == 0.0
    assert recorder.normalize_level(0.04) == 0.5
    assert recorder.normalize_level(9.9) == 1.0
```

New `tests/test_streaming.py`:

```python
import numpy as np

import recorder


def test_tail_window_short_passthrough():
    a = np.ones(recorder.SAMPLE_RATE, dtype=np.float32)  # 1s
    out = recorder.tail_window(a, seconds=15.0)
    assert out is a


def test_tail_window_cuts_long_buffer():
    a = np.arange(20 * recorder.SAMPLE_RATE, dtype=np.float32)
    out = recorder.tail_window(a, seconds=15.0)
    assert out.size == 15 * recorder.SAMPLE_RATE
    assert out[-1] == a[-1]


def test_snapshot_copy_and_empty():
    r = recorder.Recorder()
    assert r.snapshot().size == 0
    with r._lock:
        r._chunks = [np.ones(100, dtype=np.float32)]
    snap = r.snapshot()
    assert snap.size == 100
    snap[0] = 5.0
    assert r._chunks[0][0] == 1.0  # copy, not view


def test_on_level_called_per_block():
    seen = []
    r = recorder.Recorder(on_level=seen.append)
    block = 0.08 * np.ones((160, 1), dtype=np.float32)
    r._callback(block, 160, None, None)
    assert len(seen) == 1 and 0.9 <= seen[0] <= 1.0
```

- [ ] **Step 2:** Run both → FAIL (missing attrs).
- [ ] **Step 3:** Implement in `recorder.py`:

```python
def normalize_level(rms_val: float) -> float:
    return min(1.0, rms_val / 0.08)


def tail_window(audio, seconds=15.0):
    n = int(seconds * SAMPLE_RATE)
    return audio if audio.size <= n else audio[-n:]


def make_chime(freqs, note_ms=110, overlap_ms=40, amplitude=0.07):
    """Soft overlapping notes with exponential decay — no assets needed."""
    notes = []
    for f in freqs:
        n = int(SAMPLE_RATE * note_ms / 1000)
        t = np.linspace(0, note_ms / 1000, n, endpoint=False)
        env = np.exp(-t * 22.0).astype(np.float32)
        notes.append((amplitude * np.sin(2 * np.pi * f * t)).astype(np.float32) * env)
    step = max(1, int(SAMPLE_RATE * (note_ms - overlap_ms) / 1000))
    total = step * (len(freqs) - 1) + len(notes[0])
    out = np.zeros(total, dtype=np.float32)
    for i, note in enumerate(notes):
        out[i * step:i * step + len(note)] += note
    return np.clip(out, -1.0, 1.0)


TONES = {
    "start": make_chime([523.25, 659.25]),          # C5 -> E5, gentle rise
    "stop": make_chime([659.25, 523.25]),           # mirror fall
    "error": make_chime([165.0, 165.0], note_ms=90, overlap_ms=0),
}
```
(replacing `_build_tones()`; keep `make_tone` as-is). `Recorder.__init__(self, device=None, on_level=None)` stores `self.on_level = on_level`; `_callback` appends chunk then:

```python
        if self.on_level is not None:
            try:
                self.on_level(normalize_level(rms(indata[:, 0])))
            except Exception:
                pass  # level feed is cosmetic
```

`snapshot`:

```python
    def snapshot(self):
        """Copy of everything recorded so far, without stopping the stream."""
        with self._lock:
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            return np.concatenate(self._chunks).copy()
```

- [ ] **Step 4:** Both test files pass; full suite green (old tone tests unaffected — `make_tone` kept).
- [ ] **Step 5:** `git add recorder.py tests/test_gate.py tests/test_streaming.py && git commit -m "feat: level feed, snapshot, tail window, chime tones"`

---

### Task 2: overlay.py (TDD pure helpers + lifecycle smoke)

**Files:** Create `overlay.py`; Test: `tests/test_overlay.py`

**Interfaces:**
- Produces: `bar_heights(levels, n=24, h=28) -> list[int]` (right-aligned, floor 2 px); `tail_text(text, max_chars=52) -> str` (head-ellipsis); `class Overlay` — `start()`, `available` (bool), `show_recording()`, `push_level(v: float)`, `set_partial(text: str)`, `show_transcribing()`, `hide()`, `stop()`. All public methods never raise.

- [ ] **Step 1: failing tests** `tests/test_overlay.py`:

```python
import time

import overlay


def test_bar_heights_padding_and_floor():
    assert overlay.bar_heights([], n=4, h=28) == [2, 2, 2, 2]
    out = overlay.bar_heights([0.0, 1.0], n=4, h=28)
    assert out == [2, 2, 2, 28]


def test_bar_heights_takes_most_recent():
    out = overlay.bar_heights([1.0] + [0.0] * 10, n=4, h=20)
    assert out == [2, 2, 2, 2]


def test_tail_text():
    assert overlay.tail_text("short") == "short"
    long = "word " * 30
    out = overlay.tail_text(long, max_chars=20)
    assert len(out) == 20 and out.startswith("…")
    assert overlay.tail_text("  spaced   out  ") == "spaced out"


def test_overlay_lifecycle_smoke():
    ov = overlay.Overlay()
    ov.start()
    deadline = time.time() + 10
    while time.time() < deadline and not ov.available:
        time.sleep(0.1)
    assert ov.available
    ov.show_recording()
    for i in range(30):
        ov.push_level(i / 30)
    ov.set_partial("hello streaming world")
    time.sleep(0.3)          # a few ticks render
    ov.show_transcribing()
    ov.hide()
    ov.stop()
    time.sleep(0.3)          # clean shutdown, no exceptions
```

- [ ] **Step 2:** Run → ModuleNotFoundError.
- [ ] **Step 3:** `overlay.py`:

```python
"""Always-on-top dictation pill: live waveform + streaming text preview.

Tk runs on its own thread; every Tk touch happens there (commands posted via
a queue, drained by a 33 ms tick). The overlay is cosmetic — every public
method is exception-proof and the app never depends on it.
"""
import queue
import threading
from collections import deque

ACCENT = "#2563EB"
BG = "#0B0E14"
BORDER = "#1E2635"
TEXT = "#E8ECF4"
MUTED = "#9AA4BC"
REC = "#DC2626"
DIM = "#3E4557"
TRANS_KEY = "#010203"   # transparentcolor => rounded pill corners
W, H = 400, 76
N_BARS = 24
BAR_AREA_H = 28


def bar_heights(levels, n=N_BARS, h=BAR_AREA_H):
    vals = list(levels)[-n:]
    vals = [0.0] * (n - len(vals)) + vals
    return [max(2, int(v * h)) for v in vals]


def tail_text(text, max_chars=52):
    text = " ".join((text or "").split())
    if len(text) <= max_chars:
        return text
    return "…" + text[-(max_chars - 1):]


class Overlay:
    def __init__(self):
        self.available = False
        self._cmds = queue.Queue()
        self._levels = deque(maxlen=N_BARS)
        self._thread = None
        self._mode = "hidden"
        self._partial = ""
        self._visible = False

    # -- thread-side ------------------------------------------------------
    def _run(self):
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            try:
                root.attributes("-transparentcolor", TRANS_KEY)
            except Exception:
                pass
            x = (root.winfo_screenwidth() - W) // 2
            y = root.winfo_screenheight() - 140
            root.geometry(f"{W}x{H}+{x}+{y}")
            canvas = tk.Canvas(root, width=W, height=H, bg=TRANS_KEY,
                               highlightthickness=0)
            canvas.pack()
            self._root, self._canvas = root, canvas
            self.available = True
            root.after(33, self._tick)
            root.mainloop()
        except Exception as e:
            self.available = False
            print(f"ROAR: overlay unavailable: {e}", flush=True)

    def _tick(self):
        try:
            while True:
                self._cmds.get_nowait()()
        except queue.Empty:
            pass
        except Exception:
            pass
        if self._visible:
            self._draw()
        try:
            self._root.after(33, self._tick)
        except Exception:
            pass

    def _draw(self):
        c = self._canvas
        c.delete("all")
        r = 20
        # rounded pill
        c.create_polygon(
            r, 2, W - r, 2, W - 2, 2, W - 2, r, W - 2, H - r, W - 2, H - 2,
            W - r, H - 2, r, H - 2, 2, H - 2, 2, H - r, 2, r, 2, 2,
            smooth=True, fill=BG, outline=BORDER)
        dot = REC if self._mode == "recording" else MUTED
        c.create_oval(18, 16, 28, 26, fill=dot, outline="")
        color = ACCENT if self._mode == "recording" else DIM
        heights = bar_heights(self._levels)
        mid = 22
        for i, bh in enumerate(heights):
            x0 = 40 + i * 14
            c.create_rectangle(x0, mid - bh // 2, x0 + 8, mid + bh // 2,
                               fill=color, outline="")
        txt = self._partial
        if self._mode == "transcribing":
            txt = (txt + " …") if txt else "…"
        if txt:
            c.create_text(W // 2, 56, text=tail_text(txt), fill=TEXT,
                          font=("Segoe UI", 10))

    # -- public, thread-safe, exception-proof ------------------------------
    def _post(self, fn):
        try:
            self._cmds.put(fn)
        except Exception:
            pass

    def start(self):
        try:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        except Exception as e:
            print(f"ROAR: overlay thread failed: {e}", flush=True)

    def push_level(self, v):
        try:
            self._levels.append(float(v))
        except Exception:
            pass

    def show_recording(self):
        def f():
            self._levels.clear()
            self._mode = "recording"
            self._partial = ""
            self._visible = True
            self._root.deiconify()
        self._post(f)

    def set_partial(self, text):
        def f():
            self._partial = text or ""
        self._post(f)

    def show_transcribing(self):
        def f():
            self._mode = "transcribing"
        self._post(f)

    def hide(self):
        def f():
            self._visible = False
            self._mode = "hidden"
            self._partial = ""
            self._root.withdraw()
        self._post(f)

    def stop(self):
        def f():
            self._root.quit()
        self._post(f)
```

- [ ] **Step 4:** tests pass (lifecycle briefly shows the pill).
- [ ] **Step 5:** `git add overlay.py tests/test_overlay.py && git commit -m "feat: dictation pill overlay (waveform + preview)"`

---

### Task 3: app wiring — config keys, partial jobs, generation, overlay lifecycle

**Files:** Modify `config.py`, `app.py`; Test: append `tests/test_streaming.py`, `tests/test_capture_integration.py` harness

**Interfaces:**
- DEFAULTS += `"overlay_enabled": True`, `"streaming_preview": True`.
- `FlowLocalApp`: `self._session_gen = 0`; `self.overlay` (Overlay, started in `run()` when enabled, stopped in `_quit`); `_on_level(v)`; worker handles `("partial", gen)` via `_handle_partial(gen)`; worker's IDLE reset skipped for partials; `_start_recording` shows overlay + seeds first partial; `_finish_recording` bumps gen + `show_transcribing`; after the final job (incl. gated/empty) `overlay.hide()`.

- [ ] **Step 1: failing tests.** Append to `tests/test_streaming.py`:

```python
def test_defaults_have_streaming_keys():
    from config import DEFAULTS
    assert DEFAULTS["overlay_enabled"] is True
    assert DEFAULTS["streaming_preview"] is True


class _StubOverlay:
    def __init__(self):
        self.partials = []
        self.hidden = 0

    def set_partial(self, t):
        self.partials.append(t)

    def hide(self):
        self.hidden += 1


def _partial_app(tmp_path):
    from tests.test_capture_integration import _make_app
    a = _make_app(tmp_path)
    a._session_gen = 3
    a.overlay = _StubOverlay()
    a.cfg["streaming_preview"] = True
    a.state = a.RECORDING
    calls = []
    a.transcriber.transcribe = lambda audio: calls.append(len(audio)) or "partial words"
    a.recorder = recorder.Recorder()
    with a.recorder._lock:
        a.recorder._chunks = [np.ones(recorder.SAMPLE_RATE, dtype=np.float32)]
    return a, calls


def test_partial_stale_generation_skipped(tmp_path):
    a, calls = _partial_app(tmp_path)
    a._handle_partial(2)   # stale gen
    assert calls == [] and a.overlay.partials == []
    a.history.close()


def test_partial_live_generation_previews(tmp_path):
    a, calls = _partial_app(tmp_path)
    a._handle_partial(3)
    assert calls == [recorder.SAMPLE_RATE]        # tail-windowed snapshot
    assert a.overlay.partials == ["partial words"]
    a.history.close()


def test_partial_respects_preview_toggle(tmp_path):
    a, calls = _partial_app(tmp_path)
    a.cfg["streaming_preview"] = False
    a._handle_partial(3)
    assert calls == []
    a.history.close()
```

Also add to `_make_app` in `tests/test_capture_integration.py`: `a._session_gen = 0`, `a.overlay = None`, and cfg keys `"overlay_enabled": False, "streaming_preview": False` in the base dict.

- [ ] **Step 2:** Run → AttributeError (`_handle_partial`).
- [ ] **Step 3:** Implement. `config.py` DEFAULTS += the two keys. `app.py`:
  - `__init__`: `self._session_gen = 0`; `self.overlay = None`; Recorder gets `on_level=self._on_level`.
  - Methods:

```python
    def _on_level(self, v):
        ov = self.overlay
        if ov is not None and self.state == self.RECORDING:
            ov.push_level(v)

    def _handle_partial(self, gen):
        """Preview-only streaming: transcribe the buffer tail and show it in
        the overlay. Never blocks the worker with pacing sleeps — the next
        partial is scheduled via a daemon Timer."""
        if (gen != self._session_gen or self.state != self.RECORDING
                or not self.cfg.get("streaming_preview", True)):
            return
        import time as _time
        delay = 0.7
        audio = self.recorder.snapshot()
        if audio.size >= int(0.6 * recorder_mod.SAMPLE_RATE):
            t0 = _time.time()
            try:
                text = self.transcriber.transcribe(
                    recorder_mod.tail_window(audio))
            except Exception as e:
                self.log(f"partial preview failed (waveform-only): {e}")
                return
            if gen == self._session_gen and self.overlay is not None:
                self.overlay.set_partial(text)
            delay = max(0.7, _time.time() - t0)
        timer = threading.Timer(
            delay, lambda: self.jobs.put(("partial", gen)))
        timer.daemon = True
        timer.start()
```

  - Worker loop: partial branch + skip IDLE reset for partials:

```python
                elif kind == "partial":
                    self._handle_partial(payload)
            except Exception as e:
                ...
            if kind != "partial":
                self._set_state(self.IDLE)
```

  - `_start_recording` (inside the lock, after `_set_state(self.RECORDING)`):

```python
            if self.overlay is not None and self.cfg.get("overlay_enabled", True):
                self.overlay.show_recording()
                if self.cfg.get("streaming_preview", True):
                    self.jobs.put(("partial", self._session_gen))
```

  - `_finish_recording` (inside the lock, before enqueueing the final):
    `self._session_gen += 1` and `if self.overlay is not None: self.overlay.show_transcribing()`.
  - Worker `transcribe` branch, after `self._handle_transcription(payload)`:
    `if self.overlay is not None: self.overlay.hide()` (covers gated/empty/injected).
  - `run()`: before starting the watcher thread —

```python
        import overlay as overlay_mod
        self.overlay = overlay_mod.Overlay()
        self.overlay.start()
```

  - `_quit`: `try: self.overlay and self.overlay.stop()` pattern (guarded) before `icon.stop()`.

- [ ] **Step 4:** New tests pass; FULL suite green ×2 (exit codes).
- [ ] **Step 5:** `git add config.py app.py tests/ && git commit -m "feat: streaming preview pipeline + overlay lifecycle"`

---

### Task 4: settings toggles + probe + version

**Files:** Modify `settings_ui.py`, `settings.html`, `tests/test_settings_smoke.py`, `paths.py`, version asserts.

- [ ] **Step 1:** `settings_ui.py`: INSTANT_KEYS += `"overlay_enabled", "streaming_preview"`; bool-coerce tuple becomes `("history_enabled", "auto_vocabulary", "overlay_enabled", "streaming_preview")`.
- [ ] **Step 2:** `settings.html` General section, after the tones row:

```html
      <div class="row flex">
        <div>Show the dictation pill<div class="hint">Floating waveform indicator while you record</div></div>
        <button class="toggle" id="t-overlay" aria-pressed="true" aria-label="Show dictation pill"></button>
      </div>
      <div class="row flex">
        <div>Live text preview<div class="hint">Your words appear in the pill while you speak; the final text is typed when you release</div></div>
        <button class="toggle" id="t-streamprev" aria-pressed="true" aria-label="Live text preview"></button>
      </div>
```

JS in init: `setToggle($("t-overlay"), c.overlay_enabled); setToggle($("t-streamprev"), c.streaming_preview);` and two click handlers mirroring `t-tones` (`set_value("overlay_enabled"|"streaming_preview", want)`). Probe adds `ovl = evaluate_js("document.getElementById('t-overlay') ? 1 : 0")`; smoke asserts `ovl=1`.
- [ ] **Step 3:** `paths.APP_VERSION = "0.7.0"`; bridge version assert → `0.7.0`.
- [ ] **Step 4:** Full suite ×2 green.
- [ ] **Step 5:** `git add -u && git commit -m "feat: overlay/preview toggles; bump v0.7.0"` (status-checked first).

---

### Task 5: release train v0.7.0

- [ ] **Step 1:** Kill ROAR.exe + ROAR webview children. PyInstaller `roar.spec` (tkinter is currently in `excludes` in roar.spec — REMOVE `"tkinter"` from excludes, it is now required). Frozen smoke: probe `navs=8 version=0.7.0 ... ovl=1` in `%LOCALAPPDATA%\ROAR\roar.log`.
- [ ] **Step 2:** Live check (dist exe, normal mode): synthetic PTT hold ~4 s with SAPI speech; verify roar.log partial activity and overlay behavior; confirm final injection still lands (Notepad harness) or at minimum history row + log line.
- [ ] **Step 3:** `bash scripts/build_msi.sh` (solo). Upgrade over installed 0.6.0: exit 0, ProductsEx = one ROAR v0.7.0, data + config preserved, installed smoke probe green.
- [ ] **Step 4:** README: pill + live preview section, sounds note, toggles; test count. Adversarial review workflow (overlay thread-safety, partial/final race + generation, worker IDLE-reset regression, Timer leaks, chime math, probe coverage); fix confirmed; suite ×2; `git status` before adds.
- [ ] **Step 5:** Push; release commit `roar v0.7.0 — streaming preview, live waveform pill, softer chimes`; tag `v0.7.0`; push --tags; relaunch installed ROAR; update MEMORY.md (new invariants: worker-never-sleeps pacing, overlay cosmetic-only, tkinter no longer excluded) + memory file; full report.
