# Scratch That + Update Check + Credits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Spoken undo ("scratch that"), a manual check-for-updates button, and a credits line in About, shipping as v0.12.0.

**Architecture:** New pure `editing.py` (phrase match + injection stack); `app.py` intercepts scratch commands before the pipeline and undoes via focus-guarded backspaces; `settings_ui.py` gains `check_updates`/`open_repo` bridge methods (stdlib urllib, click-only); About tab gains the button + credits.

**Tech Stack:** Python 3.14 (`venv/Scripts/python.exe`), ctypes user32, `keyboard` lib, urllib, pytest; PyInstaller/WiX/7zSD release train.

## Global Constraints

- Version bumps to `0.12.0` (`paths.APP_VERSION`).
- Scratch phrases: exactly `{"scratch that", "scratch it", "undo that"}`; the ENTIRE utterance must match (standalone-only).
- Undo lengths use the PREPARED string (`injector.prepare()` adds a trailing space) — never the pipeline text.
- Focus guard: undo only when the current foreground hwnd equals the recorded one; refusal = error tone + log, never backspace elsewhere.
- Stack depth 10, session-only.
- Update check: manual click only; `https://api.github.com/repos/xhan145/roar/tags?per_page=1`; 5 s timeout; stdlib only; settings process stays ML-free.
- Credits copy verbatim: `Created, Coded, and Developed by Greg M and Ben Y`.
- Kill ROAR + webviews before builds/installs; serialize builds; fetch before push.

---

### Task 1: `editing.py` — phrase match + injection stack (TDD)

**Files:**
- Create: `editing.py`
- Test: `tests/test_editing.py`

**Interfaces:**
- Produces: `SCRATCH_PHRASES` (frozenset); `is_scratch(text) -> bool`;
  `class InjectionStack` with `push(typed: str, hwnd: int, history_id) -> None`
  and `pop_if(hwnd: int) -> Entry | None` where `Entry` is a NamedTuple
  `(typed, hwnd, history_id)`; `MAX_DEPTH = 10`.

- [ ] **Step 1: Write the failing tests** — `tests/test_editing.py`:

```python
import editing


def test_is_scratch_exact_phrases():
    assert editing.is_scratch("scratch that")
    assert editing.is_scratch("Scratch that.")
    assert editing.is_scratch("  SCRATCH IT!  ")
    assert editing.is_scratch("Undo that")


def test_is_scratch_rejects_embedded_and_other():
    assert not editing.is_scratch("please scratch that now")
    assert not editing.is_scratch("scratch that sentence I wrote")
    assert not editing.is_scratch("scratch")
    assert not editing.is_scratch("")
    assert not editing.is_scratch(None)


def test_stack_push_pop_if():
    s = editing.InjectionStack()
    s.push("hello ", 111, 5)
    s.push("world ", 111, 6)
    assert s.pop_if(222) is None            # wrong window -> untouched
    e = s.pop_if(111)
    assert e.typed == "world " and e.history_id == 6
    assert s.pop_if(111).typed == "hello "
    assert s.pop_if(111) is None            # empty


def test_stack_depth_cap():
    s = editing.InjectionStack()
    for i in range(15):
        s.push(f"t{i} ", 1, i)
    seen = []
    while (e := s.pop_if(1)) is not None:
        seen.append(e.history_id)
    assert len(seen) == editing.MAX_DEPTH == 10
    assert seen[0] == 14 and seen[-1] == 5  # oldest 5 dropped
```

- [ ] **Step 2: Run to verify fail**

Run: `venv/Scripts/python.exe -m pytest tests/test_editing.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'editing'`.

- [ ] **Step 3: Implement `editing.py`**

```python
"""Spoken editing commands: standalone-utterance detection + the injection
stack that makes undo possible. Pure logic — win32/keyboard stay in app.py."""
import re
from collections import deque
from typing import NamedTuple

SCRATCH_PHRASES = frozenset({"scratch that", "scratch it", "undo that"})
MAX_DEPTH = 10


def is_scratch(text) -> bool:
    """True only when the ENTIRE utterance is a scratch phrase — a sentence
    that merely contains one must be typed, not executed."""
    if not isinstance(text, str):
        return False
    norm = " ".join(text.lower().split()).strip(" .,!?;:")
    return norm in SCRATCH_PHRASES


class Entry(NamedTuple):
    typed: str        # the PREPARED string actually sent (incl. trailing space)
    hwnd: int         # foreground window at inject time
    history_id: object  # history row id or None


class InjectionStack:
    def __init__(self):
        self._items = deque(maxlen=MAX_DEPTH)

    def push(self, typed, hwnd, history_id):
        self._items.append(Entry(typed, hwnd, history_id))

    def pop_if(self, hwnd):
        """Pop the newest entry only when it was typed into the SAME window;
        otherwise leave the stack untouched and return None."""
        if self._items and self._items[-1].hwnd == hwnd:
            return self._items.pop()
        return None
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/Scripts/python.exe -m pytest tests/test_editing.py -q`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add editing.py tests/test_editing.py
git commit -m "feat: scratch-phrase detection + injection stack (pure)"
```

---

### Task 2: app wiring — intercept, undo, history row (TDD)

**Files:**
- Modify: `app.py` (record_history return, `_handle_transcription`, `_scratch`)
- Test: `tests/test_capture_integration.py`

**Interfaces:**
- Consumes: `editing.is_scratch`, `editing.InjectionStack` (Task 1);
  `history.delete(rid)`; `injector.prepare(text)`.
- Produces: `App._inject_stack` (an `InjectionStack`); `App._scratch()`;
  `record_history(...) -> rid | None`; `App._foreground_hwnd()` (staticmethod
  wrapping `ctypes.windll.user32.GetForegroundWindow()`, monkeypatchable).

- [ ] **Step 1: Write the failing tests** — append to
  `tests/test_capture_integration.py` (mirror the module's existing `_make_app`
  / `_loud_audio` helpers — read the file first; the tests below assume an app
  whose transcriber returns the given text and whose injector is stubbed):

```python
def test_scratch_undoes_last_injection(tmp_path, monkeypatch):
    import app as app_mod
    sent = {"backspaces": 0}
    monkeypatch.setattr(app_mod.App, "_foreground_hwnd",
                        staticmethod(lambda: 42))
    monkeypatch.setattr(app_mod, "send_backspaces",
                        lambda n: sent.__setitem__("backspaces", n))
    a = _make_app(tmp_path)  # transcriber stub returns "hello from the test"
    a._handle_transcription(_loud_audio())
    assert a.history.stats()["count"] == 1
    a.transcriber._text = "scratch that"      # next utterance is the command
    a._handle_transcription(_loud_audio())
    # prepared text = "Hello from the test " (trailing space)
    assert sent["backspaces"] == len("Hello from the test ")
    assert a.history.stats()["count"] == 0    # history row removed


def test_scratch_refuses_on_focus_change(tmp_path, monkeypatch):
    import app as app_mod
    sent = {"backspaces": 0}
    hwnd = {"v": 42}
    monkeypatch.setattr(app_mod.App, "_foreground_hwnd",
                        staticmethod(lambda: hwnd["v"]))
    monkeypatch.setattr(app_mod, "send_backspaces",
                        lambda n: sent.__setitem__("backspaces", n))
    a = _make_app(tmp_path)
    a._handle_transcription(_loud_audio())
    hwnd["v"] = 99                            # user clicked elsewhere
    a.transcriber._text = "scratch that"
    a._handle_transcription(_loud_audio())
    assert sent["backspaces"] == 0            # refused
    assert a.history.stats()["count"] == 1    # row kept
```

Adapt stub-transcriber text control to however `_make_app` builds it (read the
existing helper; if its transcriber text attribute differs, use that name).

- [ ] **Step 2: Run to verify fail**

Run: `venv/Scripts/python.exe -m pytest tests/test_capture_integration.py -q`
Expected: FAIL — no `send_backspaces` / `_foreground_hwnd`.

- [ ] **Step 3: Implement in `app.py`:**

Add near the imports:

```python
import editing
```

Add a module-level function (patchable in tests):

```python
def send_backspaces(n):
    import keyboard
    for _ in range(n):
        keyboard.send("backspace")
```

Make `record_history` return the row id:

```python
def record_history(hist, cfg, text, model=None, audio=None, duration_s=None):
    """Failure-isolated history write — never breaks dictation."""
    if not cfg.get("history_enabled", True):
        return None
    try:
        retention = cfg.get("audio_retention_days", 0)
        return hist.record(text, model=model,
                           audio=(audio if retention > 0 else None),
                           retention_days=retention, duration_s=duration_s)
    except Exception as e:
        print(f"ROAR: history write failed: {e}", flush=True)
        return None
```

In `App.__init__` (with the other state fields): `self._inject_stack = editing.InjectionStack()`.

Add to `App`:

```python
    @staticmethod
    def _foreground_hwnd():
        import ctypes
        return ctypes.windll.user32.GetForegroundWindow()

    def _scratch(self):
        entry = self._inject_stack.pop_if(self._foreground_hwnd())
        if entry is None:
            recorder_mod.play_tone("error", self.cfg["tones_enabled"])
            self.log("scratch refused — nothing typed here to undo")
            return
        send_backspaces(len(entry.typed))
        if entry.history_id is not None:
            try:
                self.history.delete(entry.history_id)
            except Exception:
                pass
        recorder_mod.play_tone("ok", self.cfg["tones_enabled"])
        self.log(f"scratched {len(entry.typed)} chars")
```

In `_handle_transcription`, after `raw = self.transcriber.transcribe(audio)`:

```python
        if editing.is_scratch(raw):
            self._scratch()
            return
```

And replace the inject/record block so the stack records the prepared text,
the hwnd captured immediately before injecting, and the history row id:

```python
        self.last_transcript = text
        hwnd = self._foreground_hwnd()
        injector.inject_text(text, paste_fallback=self.cfg["paste_fallback"])
        self.log(f"injected {len(text)} chars")
        rid = record_history(self.history, self.cfg, text,
                             model=self.transcriber.active_model, audio=audio,
                             duration_s=len(audio) / recorder_mod.SAMPLE_RATE)
        self._inject_stack.push(injector.prepare(text), hwnd, rid)
```

(Check `recorder_mod.play_tone`'s real tone names first — grep `play_tone`
usages; use the existing ok/error names.)

- [ ] **Step 4: Full suite** (kill ROAR + webviews first)

Run: `venv/Scripts/python.exe -m pytest tests/ -q --ignore=tests/test_transcriber_gpu.py`
Expected: PASS ×2.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_capture_integration.py
git commit -m "feat: scratch-that spoken undo with focus guard + history rollback"
```

---

### Task 3: update check + credits + version (TDD)

**Files:**
- Modify: `settings_ui.py` (check_updates, open_repo), `settings.html` (About), `paths.py` (0.12.0)
- Test: `tests/test_settings_bridge.py`, `tests/test_paths.py`, `tests/test_settings_smoke.py`

**Interfaces:**
- Produces: bridge `check_updates() -> {ok, current, latest, newer} | {error}`;
  `open_repo() -> {ok}`; `REPO_URL = "https://github.com/xhan145/roar"`;
  DOM ids `b-check-updates`, `m-updates`, `a-credits`;
  `paths.APP_VERSION == "0.12.0"`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_settings_bridge.py`:

```python
def test_check_updates_newer_and_current(tmp_path, monkeypatch):
    import io
    import json as _json
    import settings_ui as su

    def fake_urlopen(req, timeout=0):
        return io.BytesIO(_json.dumps([{"name": "v9.9.9"}]).encode())
    monkeypatch.setattr(su.urllib.request, "urlopen", fake_urlopen)
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    r = api.check_updates()
    assert r["ok"] is True and r["newer"] is True and r["latest"] == "9.9.9"

    def fake_same(req, timeout=0):
        import paths
        return io.BytesIO(_json.dumps([{"name": "v" + paths.APP_VERSION}]).encode())
    monkeypatch.setattr(su.urllib.request, "urlopen", fake_same)
    r = api.check_updates()
    assert r["ok"] is True and r["newer"] is False


def test_check_updates_offline_degrades(tmp_path, monkeypatch):
    import settings_ui as su

    def boom(req, timeout=0):
        raise OSError("no network")
    monkeypatch.setattr(su.urllib.request, "urlopen", boom)
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    assert "error" in api.check_updates()
```

Update version asserts: `tests/test_paths.py` and
`tests/test_settings_bridge.py::test_get_state_shape` from `"0.11.1"` to
`"0.12.0"`. Append to `tests/test_settings_smoke.py` asserts:

```python
    assert "updates=1" in out and "credits=1" in out
```

- [ ] **Step 2: Run to verify fail**

Run: `venv/Scripts/python.exe -m pytest tests/test_settings_bridge.py tests/test_paths.py -q`
Expected: FAIL — no `check_updates` / version mismatch.

- [ ] **Step 3a: `settings_ui.py`** — add `import urllib.request` and
  `import json` to the top imports, plus:

```python
REPO_URL = "https://github.com/xhan145/roar"
TAGS_URL = "https://api.github.com/repos/xhan145/roar/tags?per_page=1"


def _version_tuple(v):
    return tuple(int(p) for p in v.strip().lstrip("v").split("."))
```

Add to `SettingsAPI`:

```python
    def check_updates(self):
        """Manual, click-only: the ONLY place ROAR ever touches the network."""
        try:
            req = urllib.request.Request(TAGS_URL,
                                         headers={"User-Agent": "ROAR"})
            # no `with`: works for both real responses and BytesIO test stubs
            resp = urllib.request.urlopen(req, timeout=5)
            tags = json.loads(resp.read().decode("utf-8"))
            latest = tags[0]["name"].lstrip("v")
            newer = _version_tuple(latest) > _version_tuple(paths.APP_VERSION)
            return {"ok": True, "current": paths.APP_VERSION,
                    "latest": latest, "newer": newer}
        except Exception as e:
            return {"error": f"couldn't reach GitHub: {e}"}

    def open_repo(self):
        os.startfile(REPO_URL)  # fixed URL only — never caller-supplied
        return {"ok": True}
```

- [ ] **Step 3b: `paths.py`** — `APP_VERSION = "0.12.0"`.

- [ ] **Step 3c: `settings.html` About section** — after the `a-log` line
  (`<div class="kv">Log: ...</div>`), extend the section:

```html
        <div class="kv" style="margin-top:10px;">
          <button class="btn" id="b-check-updates">Check for updates</button>
          <span class="msg" id="m-updates" style="margin-left:8px;"></span>
        </div>
        <div class="kv" id="a-credits" style="margin-top:10px;">Created, Coded, and Developed by Greg M and Ben Y</div>
```

(Keep the existing "100% local" line after these.) JS, near the other About
handlers:

```javascript
$("b-check-updates").addEventListener("click", async () => {
  const el = $("m-updates");
  el.textContent = "Checking…"; el.className = "msg";
  const r = await api().check_updates();
  if (r.error) { el.textContent = r.error; el.className = "msg err"; return; }
  if (r.newer) {
    el.textContent = "v" + r.latest + " is available — ";
    const a = document.createElement("span");
    a.className = "pathlink"; a.setAttribute("role", "button");
    a.textContent = "open GitHub";
    a.onclick = () => api().open_repo();
    el.appendChild(a);
    el.className = "msg";
  } else {
    el.textContent = "You're up to date (v" + r.current + ")";
    el.className = "msg ok";
  }
});
```

- [ ] **Step 3d: smoke probe** — in `settings_ui.py` `probe_and_close`, add:

```python
                    has_updates = window.evaluate_js(
                        "document.getElementById('b-check-updates') ? 1 : 0")
                    has_credits = window.evaluate_js(
                        "document.getElementById('a-credits') ? 1 : 0")
```

and extend the probe print with `f"updates={has_updates} credits={has_credits}"`.

- [ ] **Step 4: Full suite ×2** (kill ROAR + webviews first)

Run: `venv/Scripts/python.exe -m pytest tests/ -q --ignore=tests/test_transcriber_gpu.py`
Expected: PASS twice.

- [ ] **Step 5: Commit**

```bash
git add settings_ui.py settings.html paths.py tests/test_settings_bridge.py tests/test_paths.py tests/test_settings_smoke.py
git commit -m "feat: manual update check + About credits; bump v0.12.0"
```

---

### Task 4: docs + release train v0.12.0

- [ ] **Step 1:** README: milestones line `v0.12.0 scratch that — spoken undo,
  update check, credits`; short "Scratch that" usage note (standalone
  utterance, same-window guard, auto-indent caveat). Commit `docs: scratch that`.
- [ ] **Step 2:** Kill ROAR + webviews; exe rebuild; frozen probe
  (`version=0.12.0 … updates=1 credits=1`); MSI build SOLO; setup exe build
  (`scripts/build_setup.sh`); `7za l` payload check.
- [ ] **Step 3:** Adversarial review (Workflow): scratch focus-guard races,
  backspace-count vs prepare(), is_scratch false accepts/rejects, history-row
  deletion correctness, check_updates parsing/injection, urlopen no-with
  pattern. Verify confirmed findings inline; fix; suite ×2; `git status` clean.
- [ ] **Step 4:** Live scratch verification from source: drive
  `_handle_transcription` with a stubbed transcriber against a real tkinter
  Entry (pattern exists in test_capture_integration) OR rely on the suite's
  integration tests + a manual smoke with the installed build.
- [ ] **Step 5:** Upgrade-install over 0.11.1 (kill first): exit 0, single
  ROAR v0.12.0, installed probe green, config + history intact.
- [ ] **Step 6:** `git fetch` → push; release commit `roar v0.12.0 — scratch
  that, update check, credits`; tag; push --tags; relaunch; MEMORY.md +
  flowlocal-project.md; final report.
