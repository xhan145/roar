# Double-Tap Hands-Free Toggle Implementation Plan

> REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use `- [ ]`.

**Goal:** Double-tap the PTT hotkey to lock dictation hands-free; single tap stops it. Ship as v0.14.0.

**Architecture:** Pure `gestures.py` `TapToggleDetector` recognizes hold/tap/double-tap from timed chord transitions and emits intents; `app.py` wires it to the keyboard hook, recorder, tones, overlay via a cancelable defer Timer.

**Tech Stack:** Python 3.14 (`venv/Scripts/python.exe`), `keyboard`, threading.Timer, pytest; PyInstaller/WiX/7zSD release train.

## Global Constraints

- Version bumps to `0.14.0`.
- Intents: `START, FINISH, DEFER, HANDSFREE, STOP, NONE` (module constants).
- `double_tap_ms` default 400, clamped `[200,1000]`.
- Detector timing in `time.monotonic()` seconds; `tap_max_s=0.35`.
- PTT (hold) behavior and the separate `hotkey_toggle` must stay working.
- Kill ROAR + webviews before builds/installs; MSI external cabs; fetch before push.

---

### Task 1: `gestures.py` — pure detector (TDD)

**Files:** Create `gestures.py`; Test `tests/test_gestures.py`

**Interfaces:** Produces `START/FINISH/DEFER/HANDSFREE/STOP/NONE` (str consts);
`TapToggleDetector(double_tap_s=0.4, tap_max_s=0.35)` with
`feed(kind, now) -> str` (kind in `"down"`/`"up"`) and `on_defer_timeout(now) -> str`.

- [ ] **Step 1: failing tests** — `tests/test_gestures.py`:

```python
import gestures
from gestures import TapToggleDetector as D, START, FINISH, DEFER, HANDSFREE, STOP, NONE


def test_hold_is_ptt():
    d = D()
    assert d.feed("down", 0.0) == START
    assert d.feed("up", 1.0) == FINISH          # long press -> immediate finish


def test_single_tap_defers_then_finishes():
    d = D(double_tap_s=0.4)
    assert d.feed("down", 0.0) == START
    assert d.feed("up", 0.1) == DEFER           # short press -> wait for a 2nd tap
    assert d.on_defer_timeout(0.5) == FINISH     # none came -> finish


def test_double_tap_enters_handsfree_one_session():
    d = D(double_tap_s=0.4)
    assert d.feed("down", 0.0) == START
    assert d.feed("up", 0.1) == DEFER
    assert d.feed("down", 0.3) == HANDSFREE      # 2nd tap within window
    assert d.feed("up", 0.4) == NONE             # release ignored while locked
    assert d.on_defer_timeout(0.5) == NONE       # racing timer is a no-op now
    assert d.feed("down", 5.0) == STOP           # later single tap stops
    assert d.feed("up", 5.1) == NONE


def test_second_tap_after_window_is_not_double():
    d = D(double_tap_s=0.4)
    d.feed("down", 0.0); d.feed("up", 0.1)
    assert d.feed("down", 0.9) == START          # gap > window -> fresh press
    assert d.feed("up", 1.5) == FINISH


def test_hold_on_second_tap_still_handsfree():
    d = D(double_tap_s=0.4)
    d.feed("down", 0.0); d.feed("up", 0.1)
    assert d.feed("down", 0.3) == HANDSFREE
    assert d.feed("up", 2.0) == NONE             # long 2nd press still ignored
    assert d.feed("down", 3.0) == STOP


def test_triple_tap_on_then_off():
    d = D(double_tap_s=0.4)
    d.feed("down", 0.0); d.feed("up", 0.1)
    assert d.feed("down", 0.2) == HANDSFREE
    d.feed("up", 0.25)
    assert d.feed("down", 0.3) == STOP           # 3rd tap stops it
```

- [ ] **Step 2:** FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: implement `gestures.py`:**

```python
"""Pure hotkey-gesture recognition for hands-free dictation. No I/O — app.py
feeds timed chord transitions and acts on the returned intent."""

START = "START"
FINISH = "FINISH"
DEFER = "DEFER"
HANDSFREE = "HANDSFREE"
STOP = "STOP"
NONE = "NONE"


class TapToggleDetector:
    def __init__(self, double_tap_s=0.4, tap_max_s=0.35):
        self.double_tap_s = double_tap_s
        self.tap_max_s = tap_max_s
        self._handsfree = False
        self._press_start = None
        self._last_tap_up = None

    def feed(self, kind, now):
        if kind == "down":
            if self._handsfree:
                self._reset()
                return STOP
            if (self._last_tap_up is not None
                    and now - self._last_tap_up <= self.double_tap_s):
                self._handsfree = True
                self._last_tap_up = None
                self._press_start = None
                return HANDSFREE
            self._press_start = now
            return START
        # kind == "up"
        if self._handsfree:
            return NONE
        if self._press_start is not None:
            dur = now - self._press_start
            self._press_start = None
            if dur <= self.tap_max_s:
                self._last_tap_up = now
                return DEFER
            self._last_tap_up = None
            return FINISH
        return NONE

    def on_defer_timeout(self, now):
        if self._last_tap_up is not None and not self._handsfree:
            self._last_tap_up = None
            return FINISH
        return NONE

    def _reset(self):
        self._handsfree = False
        self._press_start = None
        self._last_tap_up = None
```

- [ ] **Step 4:** `venv/Scripts/python.exe -m pytest tests/test_gestures.py -q` → 6 passed.

- [ ] **Step 5:** commit `feat: pure tap/hold/double-tap gesture detector`.

---

### Task 2: config key (TDD)

**Files:** Modify `config.py`; Test `tests/test_config.py`

- [ ] **Step 1: failing test** (append `tests/test_config.py`):

```python
def test_double_tap_ms_default_and_clamp(tmp_path):
    assert config.load(str(tmp_path / "d.json"))["double_tap_ms"] == 400
    p = tmp_path / "d2.json"
    p.write_text(json.dumps({"double_tap_ms": 50}))
    assert config.load(str(p))["double_tap_ms"] == 200      # clamped up
    p.write_text(json.dumps({"double_tap_ms": 9999}))
    assert config.load(str(p))["double_tap_ms"] == 1000     # clamped down
    p.write_text(json.dumps({"double_tap_ms": "x"}))
    assert config.load(str(p))["double_tap_ms"] == 400      # non-numeric -> default
```

- [ ] **Step 2:** FAIL.

- [ ] **Step 3:** `config.py` DEFAULTS += `"double_tap_ms": 400`; add a load branch:

```python
        elif key == "double_tap_ms":
            try:
                cfg[key] = min(1000, max(200, int(value)))
            except (TypeError, ValueError):
                pass  # keep default 400
```

- [ ] **Step 4:** `pytest tests/test_config.py -q` → pass.

- [ ] **Step 5:** commit `feat: double_tap_ms config key`.

---

### Task 3: app.py wiring (TDD)

**Files:** Modify `app.py`; Test `tests/test_capture_integration.py`

**Interfaces:** Consumes `gestures` (Task 1), `cfg["double_tap_ms"]` (Task 2).
Produces `App._detector`, `App._gesture(kind)`, `App._deferred_finish()`;
`_on_key_event` edge-triggered on chord transitions.

- [ ] **Step 1: failing tests** (append `tests/test_capture_integration.py`):

```python
def test_double_tap_enters_handsfree(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path)
    a.notify = lambda msg: None
    a.recorder = _StubRecorder()
    clock = {"t": 0.0}
    monkeypatch.setattr(app_mod.time, "monotonic", lambda: clock["t"])
    a._gesture("down"); clock["t"] = 0.1
    a._gesture("up");   clock["t"] = 0.3          # tap
    a._gesture("down")                             # 2nd tap within 400ms
    assert a.session_mode == "toggle"
    assert a.state == a.RECORDING
    clock["t"] = 0.4; a._gesture("up")             # release ignored
    assert a.state == a.RECORDING
    clock["t"] = 5.0; a._gesture("down")           # single tap stops
    assert a.state in (a.TRANSCRIBING, a.IDLE)
    a.history.close()


def test_hold_is_still_ptt(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path)
    a.recorder = _StubRecorder()
    clock = {"t": 0.0}
    monkeypatch.setattr(app_mod.time, "monotonic", lambda: clock["t"])
    a._gesture("down"); assert a.state == a.RECORDING
    clock["t"] = 1.0; a._gesture("up")             # long hold -> finish now
    assert a.state in (a.TRANSCRIBING, a.IDLE)
    a.history.close()
```

Add a tiny stub recorder near the top of the test file (after imports):

```python
class _StubRecorder:
    def start(self): pass
    def stop(self): import numpy as _np; return _np.zeros(100, dtype=_np.float32)
```

(`_make_app` builds a bare app; it lacks `_detector`/`recorder` for gestures —
set `a.recorder` in the test and ensure `_make_app` gives `a._detector` and
`a._gesture_lock`; add those to the app code and to `_make_app`.)

- [ ] **Step 2:** FAIL — no `_gesture`.

- [ ] **Step 3: implement in `app.py`:**

Add `import gestures` and ensure `import time`, `import threading` present.

In `__init__` (after `self._inject_stack = ...`):

```python
        self._detector = gestures.TapToggleDetector(
            double_tap_s=cfg.get("double_tap_ms", 400) / 1000)
        self._gesture_lock = threading.Lock()
        self._defer_timer = None
```

Replace `_on_key_event` with edge-triggered transitions:

```python
    def _on_key_event(self, event):
        name = (event.name or "").lower()
        before = self._chord_down()
        if event.event_type == "down":
            self.pressed.add(name)
        else:
            self.pressed.discard(name)
        after = self._chord_down()
        if after and not before:
            self._gesture("down")
        elif before and not after:
            self._gesture("up")
```

Add the gesture dispatcher + deferred finish:

```python
    def _gesture(self, kind):
        with self._gesture_lock:
            action = self._detector.feed(kind, time.monotonic())
            self._apply_gesture(action)

    def _apply_gesture(self, action):
        if action == gestures.START:
            self._start_recording("ptt")
        elif action in (gestures.FINISH, gestures.STOP):
            self._cancel_defer()
            self._finish_recording()
        elif action == gestures.DEFER:
            self._cancel_defer()
            self._defer_timer = threading.Timer(
                self._detector.double_tap_s, self._deferred_finish)
            self._defer_timer.daemon = True
            self._defer_timer.start()
        elif action == gestures.HANDSFREE:
            self._cancel_defer()
            with self.state_lock:
                if self.state == self.RECORDING:
                    self.session_mode = "toggle"
            self.notify("Hands-free dictation on — tap to stop")

    def _cancel_defer(self):
        if self._defer_timer is not None:
            self._defer_timer.cancel()
            self._defer_timer = None

    def _deferred_finish(self):
        with self._gesture_lock:
            if self._detector.on_defer_timeout(time.monotonic()) == gestures.FINISH:
                self._finish_recording()
```

In `diff_config`/config-reload path where `ptt_chord` is rebuilt, also rebuild
the detector when `double_tap_ms` changes:

```python
        self._detector = gestures.TapToggleDetector(
            double_tap_s=self.cfg.get("double_tap_ms", 400) / 1000)
```

(Add to the same block that re-parses `ptt_chord` after a config change —
around app.py:458.)

`_make_app` in the test file: add `a._detector = gestures.TapToggleDetector()`,
`a._gesture_lock = __import__("threading").Lock()`, `a._defer_timer = None`
(and `import gestures` at the test top).

- [ ] **Step 4:** full suite ×2 (kill ROAR first) — PASS.

- [ ] **Step 5:** commit `feat: double-tap hands-free wiring in the hotkey hook`.

---

### Task 4: docs + release train v0.14.0

- [ ] **Step 1:** `paths.APP_VERSION = "0.14.0"`; bump `test_paths.py` +
  `test_settings_bridge.py::test_get_state_shape` asserts to 0.14.0. README:
  milestones line + a short "Hands-free dictation" usage note (double-tap to
  lock, single tap to stop). Commit `docs: hands-free dictation; bump v0.14.0`.
- [ ] **Step 2:** Kill ROAR + webviews; exe rebuild; frozen probe
  (`version=0.14.0`, all flags green); MSI SOLO (external cabs); setup exe.
- [ ] **Step 3:** Adversarial review (Workflow): detector state-machine edges,
  defer-timer/second-tap races, chord edge-trigger correctness (multi-key
  chords, key repeat), session_mode interplay with `_on_toggle`, no regression
  to PTT/streaming. Verify confirmed inline; fix; suite ×2; `git status` clean.
- [ ] **Step 4:** Upgrade-install over 0.13.0 (kill first): exit 0, single ROAR
  v0.14.0, installed probe green, config + history intact.
- [ ] **Step 5:** `git fetch` → push; release commit `roar v0.14.0 — double-tap
  hands-free dictation`; tag `v0.14.0`; push --tags; relaunch; MEMORY.md +
  flowlocal-project.md; final report.
