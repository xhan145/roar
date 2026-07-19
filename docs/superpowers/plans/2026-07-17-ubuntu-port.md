# ROAR Ubuntu Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run ROAR on Ubuntu 24.04 (X11) with full feature parity from the same codebase, with NVIDIA CUDA acceleration and a rock-solid global hotkey.

**Architecture:** Introduce a thin platform seam. Each Windows-coupled concern gains a Linux backend selected by `sys.platform` behind an unchanged public API, so no high-level caller changes and Windows behavior is byte-identical. Portable *logic* (path resolution, `.desktop` generation, backend selection) is unit-tested on the Windows build machine by mocking `sys.platform`; genuinely Linux-only behavior (real injection, real hotkey capture, GPU) is verified by the user on Ubuntu against a checklist.

**Tech Stack:** Python 3.12 (Ubuntu system Python), faster-whisper/CTranslate2 (CUDA 12 via `nvidia-cublas-cu12`+`nvidia-cudnn-cu12` wheels), pynput (hotkeys + typing), xdotool (focus + injection fallback), pyperclip/xclip (clipboard), pywebview+webkit2gtk-4.1 (settings), pystray+AppIndicator (tray), tkinter (overlay), sounddevice/PortAudio (audio).

## Global Constraints

- **Windows must not regress.** The full existing suite (485 passed, 1 skipped) stays green after every task. Windows code paths are unchanged; Linux paths are additive.
- **Target platform:** Ubuntu 24.04 LTS, X11/Xorg session, Python 3.12. Wayland is out of scope.
- **Settings process stays ML-free:** the separate settings process must never import the transcription stack (`transcriber`, `ctranslate2`, backends). New platform modules imported by settings must not pull ML libs.
- **Privacy:** no network except the user-initiated update check and first-run model download; platform/licensing code never reads transcript, audio, history, clipboard, vocabulary, or window titles for anything but the per-app-profile feature that already does so.
- **CUDA is first-class on Linux;** Vulkan is Windows-only and must never be offered on Linux.
- **Hotkey reliability is the #1 must-pass** on the Ubuntu checklist.
- **Build-blind:** the author runs Windows. Linux backends carry real code but are verified on Ubuntu. Every platform probe degrades safely (log, never raise).
- Branch for this work: `feature/ubuntu-port`. Commit after every task. Never work on `main`.

## Platform coupling map (what each seam replaces)

| Concern | Windows today | Linux backend | Testable on Windows? |
|---|---|---|---|
| `platform_id` | — | new selector | yes (pure) |
| `paths` config/data | `%APPDATA%`/`%LOCALAPPDATA%` | XDG | yes (mock platform+env) |
| `autostart` | `winreg` Run key | `~/.config/autostart/roar.desktop` | yes (temp HOME) |
| `hardware_accel` device/backend | CUDA+Vulkan | CUDA only, Vulkan filtered | yes (mock probe) |
| `injector` typing | `keyboard.write` | pynput/clipboard/xdotool | selection only |
| `window_focus` | `GetForegroundWindow` + proc/title | xdotool | selection only |
| `hotkey_listener` | `keyboard.hook/add_hotkey` | pynput Listener | selection + lifecycle |
| `single_instance` | `CreateMutexW` | flock pidfile | yes (temp dir) |

---

## Task 1: platform_id selector

**Files:**
- Create: `platform_id.py`
- Test: `tests/test_platform_id.py`

**Interfaces:**
- Produces: `is_windows() -> bool`, `is_linux() -> bool`, `name() -> str` (`"windows"|"linux"|"other"`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_platform_id.py
import platform_id

def test_windows(monkeypatch):
    monkeypatch.setattr(platform_id.sys, "platform", "win32")
    assert platform_id.is_windows() and not platform_id.is_linux()
    assert platform_id.name() == "windows"

def test_linux(monkeypatch):
    monkeypatch.setattr(platform_id.sys, "platform", "linux")
    assert platform_id.is_linux() and not platform_id.is_windows()
    assert platform_id.name() == "linux"

def test_other(monkeypatch):
    monkeypatch.setattr(platform_id.sys, "platform", "darwin")
    assert platform_id.name() == "other"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/Scripts/python.exe -m pytest tests/test_platform_id.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'platform_id'`

- [ ] **Step 3: Write minimal implementation**

```python
# platform_id.py
"""Single source of truth for the running OS. Import this instead of testing
sys.platform ad hoc, so backend selection is consistent and mockable."""
import sys

def is_windows() -> bool:
    return sys.platform.startswith("win")

def is_linux() -> bool:
    return sys.platform.startswith("linux")

def name() -> str:
    if is_windows():
        return "windows"
    if is_linux():
        return "linux"
    return "other"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/Scripts/python.exe -m pytest tests/test_platform_id.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add platform_id.py tests/test_platform_id.py
git commit -m "feat(platform): add platform_id OS selector"
```

---

## Task 2: XDG paths on Linux

**Files:**
- Modify: `paths.py` (config_path, models_dir, license_path, legacy_grant_path, _data_dir, log_path)
- Test: `tests/test_paths_linux.py`

**Interfaces:**
- Consumes: `platform_id.is_linux()`.
- Produces: unchanged public path getters; on Linux they resolve under XDG dirs.

Design: add a private `_xdg_config_home()` and `_xdg_data_home()` and a `_frozen_or_linux` branch. The Windows `is_frozen()` branch is untouched; a **new** Linux branch (frozen OR source — Linux always uses per-user dirs) is added ahead of the source fallback.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paths_linux.py
import os
import importlib
import pytest

@pytest.fixture
def linux_paths(monkeypatch, tmp_path):
    import paths
    monkeypatch.setattr(paths.platform_id, "is_linux", lambda: True)
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return paths, home

def test_config_under_xdg_config(linux_paths):
    paths, home = linux_paths
    assert paths.config_path() == str(home / ".config" / "ROAR" / "config.json")

def test_data_under_xdg_data(linux_paths):
    paths, home = linux_paths
    assert paths.history_db_path() == str(home / ".local" / "share" / "ROAR" / "history.db")
    assert paths.models_dir() == str(home / ".local" / "share" / "ROAR" / "models")

def test_license_beside_config_not_in_data(linux_paths):
    paths, home = linux_paths
    lic = paths.license_path()
    assert lic == str(home / ".config" / "ROAR" / "license.json")
    assert ".local" not in lic  # never in the data dir that clears touch

def test_xdg_env_overrides(linux_paths, monkeypatch, tmp_path):
    paths, _ = linux_paths
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "dat"))
    assert paths.config_path() == str(tmp_path / "cfg" / "ROAR" / "config.json")
    assert paths.log_path() == str(tmp_path / "dat" / "ROAR" / "roar.log")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/Scripts/python.exe -m pytest tests/test_paths_linux.py -v`
Expected: FAIL — `AttributeError: module 'paths' has no attribute 'platform_id'` (not imported yet).

- [ ] **Step 3: Write minimal implementation**

Add near the top of `paths.py` (after `import sys`):

```python
import platform_id


def _xdg_config_home() -> str:
    return os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config")


def _xdg_data_home() -> str:
    return os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share")


def _linux_config_dir() -> str:
    return os.path.join(_xdg_config_home(), APP_NAME)


def _linux_data_dir() -> str:
    return os.path.join(_xdg_data_home(), APP_NAME)
```

Then add a Linux branch to each getter, **above** the existing source-return line. Example for `config_path`:

```python
def config_path() -> str:
    if is_frozen():
        return os.path.join(os.environ["APPDATA"], APP_NAME, "config.json")
    if platform_id.is_linux():
        return os.path.join(_linux_config_dir(), "config.json")
    return os.path.join(_source_root(), "config.json")
```

Apply the same shape to `models_dir` (`_linux_data_dir()/"models"`), `license_path` (`_linux_config_dir()/"license.json"`), `legacy_grant_path` (`_linux_config_dir()/"legacy_grant.json"`), and `_data_dir` (`_linux_data_dir()`). Replace `log_path` entirely so it is not Windows-only:

```python
def log_path() -> str:
    if platform_id.is_linux():
        return os.path.join(_linux_data_dir(), "roar.log")
    return os.path.join(os.environ["LOCALAPPDATA"], APP_NAME, "roar.log")
```

- [ ] **Step 4: Run tests (new + Windows regression on paths)**

Run: `venv/Scripts/python.exe -m pytest tests/test_paths_linux.py tests/test_paths.py -v`
Expected: PASS (new Linux tests pass; existing `tests/test_paths.py` still passes — Windows branch unchanged).

- [ ] **Step 5: Commit**

```bash
git add paths.py tests/test_paths_linux.py
git commit -m "feat(paths): XDG config/data dirs on Linux; license stays beside config"
```

---

## Task 3: Autostart via .desktop on Linux

**Files:**
- Modify: `autostart.py` (add Linux branch; keep winreg branch importable only on Windows)
- Test: `tests/test_autostart_linux.py`

**Interfaces:**
- Consumes: `platform_id`.
- Produces: unchanged `get(name)`, `set_enabled(name, command, enabled)`, `default_command()`. On Linux, `get` returns the `Exec=` line or None; `set_enabled(True)` writes `~/.config/autostart/<name>.desktop`; `set_enabled(False)` removes it.

Critical detail: `autostart.py` currently does `import winreg` at module top, which raises `ModuleNotFoundError` on Linux. Move `winreg` into the Windows-only functions.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_autostart_linux.py
import os, pytest

@pytest.fixture
def linux_autostart(monkeypatch, tmp_path):
    import autostart
    monkeypatch.setattr(autostart.platform_id, "is_linux", lambda: True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return autostart, tmp_path

def test_enable_writes_desktop_file(linux_autostart):
    autostart, home = linux_autostart
    autostart.set_enabled("ROAR", "/opt/roar/roar", True)
    p = home / ".config" / "autostart" / "ROAR.desktop"
    assert p.exists()
    body = p.read_text()
    assert "Type=Application" in body
    assert "Exec=/opt/roar/roar" in body
    assert "Name=ROAR" in body
    assert "X-GNOME-Autostart-enabled=true" in body

def test_get_returns_exec_then_none_after_disable(linux_autostart):
    autostart, _ = linux_autostart
    assert autostart.get("ROAR") is None
    autostart.set_enabled("ROAR", "/opt/roar/roar", True)
    assert autostart.get("ROAR") == "/opt/roar/roar"
    autostart.set_enabled("ROAR", "", False)
    assert autostart.get("ROAR") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/Scripts/python.exe -m pytest tests/test_autostart_linux.py -v`
Expected: FAIL — `AttributeError: module 'autostart' has no attribute 'platform_id'`.

- [ ] **Step 3: Write minimal implementation**

Rewrite `autostart.py` top and add Linux functions; move `winreg` import inside Windows funcs:

```python
"""Start on login. Windows: HKCU Run key. Linux: XDG autostart .desktop."""
import os
import re
import sys

import platform_id

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _autostart_dir() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config")
    return os.path.join(base, "autostart")


def _desktop_path(name: str) -> str:
    return os.path.join(_autostart_dir(), f"{name}.desktop")


def _linux_get(name: str):
    try:
        with open(_desktop_path(name), encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("Exec="):
                    return line[len("Exec="):].strip()
    except OSError:
        return None
    return None


def _linux_set(name: str, command: str, enabled: bool):
    path = _desktop_path(name)
    if not enabled:
        try:
            os.remove(path)
        except OSError:
            pass
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name}\n"
        f"Exec={command}\n"
        "X-GNOME-Autostart-enabled=true\n"
        "Terminal=false\n"
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)


def get(name: str):
    if platform_id.is_linux():
        return _linux_get(name)
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _type = winreg.QueryValueEx(key, name)
            return value
    except OSError:
        return None


def set_enabled(name: str, command: str, enabled: bool):
    if platform_id.is_linux():
        return _linux_set(name, command, enabled)
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, name)
            except OSError:
                pass


def default_command() -> str:
    if platform_id.is_linux():
        # the launcher script written by linux/setup.sh
        return os.path.join(os.path.expanduser("~"), ".local", "bin", "roar")
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    app = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    return f'"{pythonw}" "{app}"'
```

- [ ] **Step 4: Run tests (new + Windows regression)**

Run: `venv/Scripts/python.exe -m pytest tests/test_autostart_linux.py tests/test_autostart.py -v`
Expected: PASS (Linux tests pass; existing `tests/test_autostart.py` still passes — winreg path intact).

- [ ] **Step 5: Commit**

```bash
git add autostart.py tests/test_autostart_linux.py
git commit -m "feat(autostart): XDG .desktop autostart on Linux; lazy winreg import"
```

---

## Task 4: hardware_accel — CUDA first-class, Vulkan excluded on Linux

**Files:**
- Modify: `hardware_accel.py` (add `platform_id` import; guard Vulkan; keep CUDA device selection)
- Test: `tests/test_hardware_accel_linux.py`

**Interfaces:**
- Consumes: `platform_id`, existing `choose_device`, `choose_best_backend`, `vulkan_runtime_present`.
- Produces: `available_backends(cfg)` excludes `whispercpp_vulkan` on Linux; `choose_best_backend` never returns `whispercpp_vulkan` on Linux.

Read `hardware_accel.py` first to find `choose_best_backend`/`available_backends`/`vulkan_runtime_present` (names may differ slightly — adapt). The rule: on Linux, `vulkan_runtime_present()` returns False and any backend list drops the Vulkan entry, so CUDA (via the existing `choose_device` faster-whisper path) or CPU is chosen.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hardware_accel_linux.py
import hardware_accel as hw

def test_vulkan_never_present_on_linux(monkeypatch):
    monkeypatch.setattr(hw.platform_id, "is_linux", lambda: True)
    assert hw.vulkan_runtime_present() is False

def test_best_backend_not_vulkan_on_linux(monkeypatch):
    monkeypatch.setattr(hw.platform_id, "is_linux", lambda: True)
    cfg = {"backend": "whispercpp_vulkan"}  # even if the user asked for it
    assert hw.choose_best_backend(cfg, {}) != "whispercpp_vulkan"

def test_cuda_device_preferred_when_present(monkeypatch):
    monkeypatch.setattr(hw.platform_id, "is_linux", lambda: True)
    accel = {"cuda": True, "cuda_count": 1}
    assert hw.choose_device({}, accel) == "cuda"

def test_cpu_when_no_cuda(monkeypatch):
    monkeypatch.setattr(hw.platform_id, "is_linux", lambda: True)
    assert hw.choose_device({}, {"cuda": False, "cuda_count": 0}) == "cpu"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/Scripts/python.exe -m pytest tests/test_hardware_accel_linux.py -v`
Expected: FAIL — `AttributeError: module 'hardware_accel' has no attribute 'platform_id'`.

- [ ] **Step 3: Write minimal implementation**

Add `import platform_id` at top. In `vulkan_runtime_present()`, add as the first lines:

```python
def vulkan_runtime_present() -> bool:
    if platform_id.is_linux():
        return False  # Vulkan backend ships Windows-only binaries
    # ... existing Windows body unchanged ...
```

In `choose_best_backend(cfg, accel)`, ensure the Vulkan branch is guarded by `vulkan_runtime_present()` (it already is, per app.py line 361 using `choose_best_backend == "whispercpp_vulkan"`). If `available_backends()` exists, filter: `if platform_id.is_linux(): backends = [b for b in backends if b != "whispercpp_vulkan"]`. Do NOT change `choose_device` — its CUDA logic is already cross-platform (CTranslate2 reports `get_cuda_device_count()` on Linux too).

- [ ] **Step 4: Run tests (new + Windows regression)**

Run: `venv/Scripts/python.exe -m pytest tests/test_hardware_accel_linux.py tests/test_hardware_accel.py tests/test_backends.py -v`
Expected: PASS (Vulkan still offered on Windows; excluded on Linux; CUDA device selection intact).

- [ ] **Step 5: Commit**

```bash
git add hardware_accel.py tests/test_hardware_accel_linux.py
git commit -m "feat(accel): exclude Vulkan on Linux; CUDA stays first-class"
```

---

## Task 5: Extract injector backend seam (Windows behavior preserved)

**Files:**
- Create: `inject_windows.py`
- Modify: `injector.py` (dispatch to a backend; keep public API `inject_text`, `prepare`, `MAX_PASTE`)
- Test: `tests/test_injector_backend.py`

**Interfaces:**
- Produces: `injector.inject_text(text, paste_fallback=False) -> bool` (unchanged signature), backed by a backend object exposing `type_text(text) -> None` and `paste_text(text) -> None`. Backend chosen at import via `platform_id` and `ROAR_INJECT_BACKEND` env.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_injector_backend.py
import importlib
import injector

def test_selects_windows_backend(monkeypatch):
    monkeypatch.setattr(injector.platform_id, "is_linux", lambda: False)
    b = injector._select_backend()
    assert b.__class__.__name__ == "WindowsInjector"

def test_inject_text_uses_backend_type(monkeypatch):
    calls = {}
    class Fake:
        def type_text(self, t): calls["typed"] = t
        def paste_text(self, t): calls["pasted"] = t
    monkeypatch.setattr(injector, "_BACKEND", Fake())
    assert injector.inject_text("hello") is True
    assert calls["typed"] == "hello "   # prepare() adds trailing space

def test_inject_text_paste_fallback(monkeypatch):
    calls = {}
    class Fake:
        def type_text(self, t): calls["typed"] = t
        def paste_text(self, t): calls["pasted"] = t
    monkeypatch.setattr(injector, "_BACKEND", Fake())
    assert injector.inject_text("hi", paste_fallback=True) is True
    assert calls["pasted"] == "hi "
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/Scripts/python.exe -m pytest tests/test_injector_backend.py -v`
Expected: FAIL — `AttributeError: module 'injector' has no attribute '_select_backend'`.

- [ ] **Step 3: Write minimal implementation**

Create `inject_windows.py` (extract today's behavior):

```python
"""Windows text injection: keyboard.write (SendInput unicode), clipboard paste."""
import time


class WindowsInjector:
    def type_text(self, text):
        import keyboard
        keyboard.write(text, delay=0)

    def paste_text(self, text):
        import keyboard, pyperclip
        old = None
        try:
            old = pyperclip.paste()
        except Exception:
            pass
        pyperclip.copy(text)
        keyboard.send("ctrl+v")
        time.sleep(0.8)
        if old is not None:
            try:
                pyperclip.copy(old)
            except Exception:
                pass
```

Rewrite `injector.py` to dispatch (keep `prepare`, `MAX_PASTE`):

```python
"""Text injection: platform backend types into the focused app, with a
clipboard-paste fallback. Backend picked by platform_id + ROAR_INJECT_BACKEND."""
import os

import platform_id

MAX_PASTE = 100_000


def prepare(text):
    if not text:
        return None
    if not text.strip():
        return text if "\n" in text else None
    return text if text.endswith("\n") else text + " "


def _select_backend():
    if platform_id.is_linux():
        from inject_x11 import X11Injector          # Task 6
        return X11Injector(os.environ.get("ROAR_INJECT_BACKEND", "pynput"))
    from inject_windows import WindowsInjector
    return WindowsInjector()


_BACKEND = _select_backend()


def inject_text(text, paste_fallback=False) -> bool:
    out = prepare(text)
    if out is None:
        return False
    if len(out) > MAX_PASTE:
        print(f"ROAR: injection refused — {len(out)} chars exceeds the "
              f"{MAX_PASTE} safety bound", flush=True)
        return False
    try:
        if paste_fallback:
            _BACKEND.paste_text(out)
        else:
            _BACKEND.type_text(out)
        return True
    except Exception as e:
        print(f"ROAR: injection failed ({e})", flush=True)
        return False
```

Note: Task 5 imports `inject_x11` lazily only on Linux, so this task is green on Windows before Task 6 exists.

- [ ] **Step 4: Run tests (new + Windows regression)**

Run: `venv/Scripts/python.exe -m pytest tests/test_injector_backend.py tests/test_injector.py -v`
Expected: PASS (existing injector tests still pass; behavior identical on Windows).

- [ ] **Step 5: Commit**

```bash
git add inject_windows.py injector.py tests/test_injector_backend.py
git commit -m "refactor(injector): backend seam; extract Windows injector unchanged"
```

---

## Task 6: X11 injector backend (Linux)

**Files:**
- Create: `inject_x11.py`
- Test: `tests/test_inject_x11.py`

**Interfaces:**
- Consumes: nothing from ROAR.
- Produces: `X11Injector(mode="pynput"|"xdotool")` with `type_text(text)`, `paste_text(text)`. `type_text` uses pynput by default (Unicode `.type()`), or xdotool when `mode=="xdotool"`. `paste_text` copies via pyperclip then presses Ctrl+V via pynput.

Verified on Ubuntu, not Windows — the Windows test only checks construction/mode logic with the OS libs monkeypatched.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_inject_x11.py
import sys, types
import pytest

def _stub_pynput(monkeypatch, recorder):
    kb = types.ModuleType("pynput.keyboard")
    class Key: ctrl = "CTRL"
    class Controller:
        def type(self, t): recorder.append(("type", t))
        def press(self, k): recorder.append(("press", k))
        def release(self, k): recorder.append(("release", k))
    kb.Key = Key; kb.Controller = Controller
    root = types.ModuleType("pynput"); root.keyboard = kb
    monkeypatch.setitem(sys.modules, "pynput", root)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", kb)

def test_pynput_type(monkeypatch):
    rec = []
    _stub_pynput(monkeypatch, rec)
    import importlib, inject_x11; importlib.reload(inject_x11)
    inject_x11.X11Injector("pynput").type_text("héllo")
    assert ("type", "héllo") in rec

def test_xdotool_type(monkeypatch):
    calls = {}
    import inject_x11
    monkeypatch.setattr(inject_x11.subprocess, "run",
                        lambda *a, **k: calls.setdefault("argv", a[0]))
    inject_x11.X11Injector("xdotool").type_text("hi")
    assert calls["argv"][:3] == ["xdotool", "type", "--clearmodifiers"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/Scripts/python.exe -m pytest tests/test_inject_x11.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'inject_x11'`.

- [ ] **Step 3: Write minimal implementation**

```python
# inject_x11.py
"""X11 text injection. pynput Unicode typing by default; xdotool alternative;
clipboard-paste fallback. Verified on Ubuntu 24.04 / Xorg."""
import subprocess
import time


class X11Injector:
    def __init__(self, mode="pynput"):
        self.mode = "xdotool" if mode == "xdotool" else "pynput"
        self._kb = None

    def _controller(self):
        if self._kb is None:
            from pynput import keyboard
            self._kb = keyboard.Controller()
        return self._kb

    def type_text(self, text):
        if self.mode == "xdotool":
            subprocess.run(["xdotool", "type", "--clearmodifiers", "--", text],
                           check=False)
            return
        self._controller().type(text)

    def paste_text(self, text):
        import pyperclip
        old = None
        try:
            old = pyperclip.paste()
        except Exception:
            pass
        pyperclip.copy(text)
        from pynput import keyboard
        kb = self._controller()
        kb.press(keyboard.Key.ctrl)
        kb.press("v"); kb.release("v")
        kb.release(keyboard.Key.ctrl)
        time.sleep(0.8)
        if old is not None:
            try:
                pyperclip.copy(old)
            except Exception:
                pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/Scripts/python.exe -m pytest tests/test_inject_x11.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add inject_x11.py tests/test_inject_x11.py
git commit -m "feat(injector): X11 backend (pynput/xdotool/clipboard)"
```

---

## Task 7: Window-focus seam (extract Windows, add X11)

**Files:**
- Create: `window_focus.py`, `focus_windows.py`, `focus_x11.py`
- Modify: `app.py` (`_foreground_hwnd` and active-window helpers call `window_focus`)
- Test: `tests/test_window_focus.py`

**Interfaces:**
- Produces: `window_focus.current_id() -> int|str` (opaque focused-window handle), `window_focus.active_process() -> str|None`, `window_focus.active_title() -> str|None`. Windows backend wraps the existing ctypes code (extract from app.py lines ~509–560); X11 backend shells to `xdotool getactivewindow` / `getwindowname` / `getwindowpid` + `/proc/<pid>/comm`.

The focus-guard in app.py compares `current_id()` before vs after transcription; the value only needs to be comparable and stable, so an opaque int (Windows HWND) or str (X11 window id) both work.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_window_focus.py
import window_focus

def test_selects_backend_windows(monkeypatch):
    monkeypatch.setattr(window_focus.platform_id, "is_linux", lambda: False)
    assert window_focus._select().__class__.__name__ == "WindowsFocus"

def test_x11_active_process_parses_comm(monkeypatch):
    import focus_x11
    monkeypatch.setattr(focus_x11.subprocess, "check_output",
                        lambda *a, **k: b"1234\n")
    monkeypatch.setattr(focus_x11.os.path, "exists", lambda p: True)
    monkeypatch.setattr(focus_x11, "_read", lambda p: "gedit\n")
    assert focus_x11.X11Focus().active_process() == "gedit"

def test_focus_guard_detects_change(monkeypatch):
    seq = iter([111, 222])
    class Fake:
        def current_id(self): return next(seq)
        def active_process(self): return None
        def active_title(self): return None
    monkeypatch.setattr(window_focus, "_BACKEND", Fake())
    a = window_focus.current_id(); b = window_focus.current_id()
    assert a != b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/Scripts/python.exe -m pytest tests/test_window_focus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'window_focus'`.

- [ ] **Step 3: Write minimal implementation**

`focus_windows.py` — move the ctypes helpers out of `app.py` (`GetForegroundWindow`, `GetWindowThreadProcessId`, `QueryFullProcessImageNameW`, `GetWindowText*`) into:

```python
# focus_windows.py
"""Windows active-window queries (extracted from app.py, behavior unchanged)."""
import ctypes


class WindowsFocus:
    def current_id(self):
        import ctypes.wintypes as wintypes
        u32 = ctypes.windll.user32
        u32.GetForegroundWindow.restype = wintypes.HWND
        return int(u32.GetForegroundWindow() or 0)

    def active_process(self):
        # move the QueryFullProcessImageNameW body here from app.py; return the
        # exe basename lowercased, or None on failure. (Copy verbatim.)
        ...

    def active_title(self):
        # move the GetWindowTextW body here from app.py; return str or None.
        ...
```

(When executing: cut the exact bodies from `app.py` lines ~515–560 into these methods so behavior is byte-identical; app.py then delegates.)

`focus_x11.py`:

```python
# focus_x11.py
"""X11 active-window queries via xdotool. Verified on Ubuntu 24.04 / Xorg."""
import os
import subprocess


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


class X11Focus:
    def current_id(self):
        try:
            return subprocess.check_output(
                ["xdotool", "getactivewindow"]).decode().strip()
        except Exception:
            return ""

    def active_process(self):
        try:
            pid = subprocess.check_output(
                ["xdotool", "getactivewindow", "getwindowpid"]).decode().strip()
        except Exception:
            return None
        comm = f"/proc/{pid}/comm"
        if not os.path.exists(comm):
            return None
        try:
            return _read(comm).strip().lower()
        except Exception:
            return None

    def active_title(self):
        try:
            return subprocess.check_output(
                ["xdotool", "getactivewindow", "getwindowname"]).decode(
                    "utf-8", "replace").strip()
        except Exception:
            return None
```

`window_focus.py`:

```python
# window_focus.py
"""Focused-window queries behind a platform seam. current_id() is an opaque,
comparable handle used for the injection focus-guard; active_process/title feed
per-app profiles (context.py)."""
import platform_id


def _select():
    if platform_id.is_linux():
        from focus_x11 import X11Focus
        return X11Focus()
    from focus_windows import WindowsFocus
    return WindowsFocus()


_BACKEND = _select()

def current_id():      return _BACKEND.current_id()
def active_process():  return _BACKEND.active_process()
def active_title():    return _BACKEND.active_title()
```

In `app.py`: replace `_foreground_hwnd()` body with `return window_focus.current_id()`, and route the active-process/title helpers to `window_focus`. Add `import window_focus`.

- [ ] **Step 4: Run tests (new + Windows regression: context/per-app profiles)**

Run: `venv/Scripts/python.exe -m pytest tests/test_window_focus.py tests/test_context.py -v`
Expected: PASS (per-app profile logic unchanged on Windows).

- [ ] **Step 5: Commit**

```bash
git add window_focus.py focus_windows.py focus_x11.py app.py tests/test_window_focus.py
git commit -m "refactor(focus): window-focus seam; extract Windows, add X11 (xdotool)"
```

---

## Task 8: Hotkey-listener seam — extract Windows (the #1 must-pass)

**Files:**
- Create: `hotkey_listener.py`, `hotkeys_windows.py`
- Modify: `app.py` (`_register_hotkeys`, rehook path, `unhook_all` → seam)
- Test: `tests/test_hotkey_listener.py`

**Interfaces:**
- Produces: `hotkey_listener.HotkeyListener(on_key_event, on_toggle, toggle_chord)` with `.start()`, `.stop()`, `.restart()`. `on_key_event(event)` receives objects with `.event_type` (`"down"`/`"up"`) and `.name` (key name) — matching what `gestures.py` consumes today from the `keyboard` lib. Windows backend wraps `keyboard.hook` + `keyboard.add_hotkey`.

This task only extracts and re-wires Windows; the Linux backend is Task 9. Windows must stay byte-identical (existing hotkey/gesture tests green).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hotkey_listener.py
import hotkey_listener

def test_selects_windows_backend(monkeypatch):
    monkeypatch.setattr(hotkey_listener.platform_id, "is_linux", lambda: False)
    hl = hotkey_listener.HotkeyListener(lambda e: None, lambda: None, "ctrl+space")
    assert hl._backend.__class__.__name__ == "WindowsHotkeys"

def test_start_stop_lifecycle(monkeypatch):
    events = []
    class FakeBackend:
        def start(self): events.append("start")
        def stop(self): events.append("stop")
    hl = hotkey_listener.HotkeyListener(lambda e: None, lambda: None, "ctrl+space")
    hl._backend = FakeBackend()
    hl.start(); hl.stop()
    assert events == ["start", "stop"]

def test_restart_calls_stop_then_start(monkeypatch):
    events = []
    class FakeBackend:
        def start(self): events.append("start")
        def stop(self): events.append("stop")
    hl = hotkey_listener.HotkeyListener(lambda e: None, lambda: None, "ctrl+space")
    hl._backend = FakeBackend()
    hl.restart()
    assert events == ["stop", "start"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/Scripts/python.exe -m pytest tests/test_hotkey_listener.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hotkey_listener'`.

- [ ] **Step 3: Write minimal implementation**

`hotkeys_windows.py`:

```python
"""Windows global hotkeys via the `keyboard` lib (extracted from app.py)."""


class WindowsHotkeys:
    def __init__(self, on_key_event, on_toggle, toggle_chord):
        self._on_key_event = on_key_event
        self._on_toggle = on_toggle
        self._toggle = toggle_chord

    def start(self):
        import keyboard
        keyboard.hook(self._on_key_event)
        keyboard.add_hotkey(self._toggle, self._on_toggle)
        if "windows" in self._toggle:
            keyboard.add_hotkey(self._toggle.replace("windows", "left windows"),
                                self._on_toggle)

    def stop(self):
        import keyboard
        keyboard.unhook_all()
```

`hotkey_listener.py`:

```python
"""Global hotkey capture behind a platform seam. Reliability is the priority:
start/stop/restart are clean, and the Linux backend self-heals a dead listener."""
import platform_id


class HotkeyListener:
    def __init__(self, on_key_event, on_toggle, toggle_chord):
        self._backend = self._select(on_key_event, on_toggle, toggle_chord)

    def _select(self, on_key_event, on_toggle, toggle_chord):
        if platform_id.is_linux():
            from hotkeys_x11 import X11Hotkeys       # Task 9
            return X11Hotkeys(on_key_event, on_toggle, toggle_chord)
        from hotkeys_windows import WindowsHotkeys
        return WindowsHotkeys(on_key_event, on_toggle, toggle_chord)

    def start(self):   self._backend.start()
    def stop(self):    self._backend.stop()
    def restart(self):
        self._backend.stop()
        self._backend.start()
```

In `app.py`: replace `_register_hotkeys` internals with a `HotkeyListener` instance stored on `self`; the rehook branch (line ~719) calls `self._hotkeys.restart()` after re-parsing the chord; teardown (line ~754) calls `self._hotkeys.stop()`. Keep `self.log("hotkeys registered")`. Import `hotkey_listener`. The `keyboard.send("backspace")` at line 64 belongs to editing/undo — move it behind `injector` in Task 10-adjacent cleanup (leave for now; it still works on Windows).

- [ ] **Step 4: Run tests (new + Windows regression: gestures + app smoke)**

Run: `venv/Scripts/python.exe -m pytest tests/test_hotkey_listener.py tests/test_gestures.py -v`
Expected: PASS. Then confirm app still imports: `venv/Scripts/python.exe -c "import app"` (no error).

- [ ] **Step 5: Commit**

```bash
git add hotkey_listener.py hotkeys_windows.py app.py tests/test_hotkey_listener.py
git commit -m "refactor(hotkey): listener seam; extract Windows keyboard backend"
```

---

## Task 9: X11 hotkey backend with self-heal (Linux)

**Files:**
- Create: `hotkeys_x11.py`
- Test: `tests/test_hotkeys_x11.py`

**Interfaces:**
- Consumes: nothing from ROAR.
- Produces: `X11Hotkeys(on_key_event, on_toggle, toggle_chord)` with `.start()`, `.stop()`. Translates pynput key events into the `.event_type`/`.name` shape `gestures.py` expects, detects the toggle chord, runs the listener on its own thread, and restarts once if the listener thread dies.

pynput's `keyboard.Listener(on_press, on_release)` runs its own thread. We adapt each press/release into a small event object and forward to `on_key_event`; we also track modifier state to fire `on_toggle` when the toggle chord is completed.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hotkeys_x11.py
import sys, types
import pytest

def _stub_pynput(monkeypatch, listener_holder):
    kb = types.ModuleType("pynput.keyboard")
    class KeyCode:
        def __init__(self, char=None): self.char = char
    class Key:
        ctrl = "ctrl"; space = "space"
    class Listener:
        def __init__(self, on_press=None, on_release=None):
            listener_holder["on_press"] = on_press
            listener_holder["on_release"] = on_release
            self.alive = True
        def start(self): pass
        def stop(self): self.alive = False
        def is_alive(self): return self.alive
    kb.KeyCode = KeyCode; kb.Key = Key; kb.Listener = Listener
    root = types.ModuleType("pynput"); root.keyboard = kb
    monkeypatch.setitem(sys.modules, "pynput", root)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", kb)
    return kb

def test_key_event_forwarded_as_down_up(monkeypatch):
    holder = {}
    kb = _stub_pynput(monkeypatch, holder)
    import importlib, hotkeys_x11; importlib.reload(hotkeys_x11)
    seen = []
    h = hotkeys_x11.X11Hotkeys(lambda e: seen.append((e.event_type, e.name)),
                               lambda: None, "ctrl+space")
    h.start()
    holder["on_press"](kb.KeyCode(char="a"))
    holder["on_release"](kb.KeyCode(char="a"))
    assert ("down", "a") in seen and ("up", "a") in seen

def test_toggle_chord_fires(monkeypatch):
    holder = {}
    kb = _stub_pynput(monkeypatch, holder)
    import importlib, hotkeys_x11; importlib.reload(hotkeys_x11)
    fired = []
    h = hotkeys_x11.X11Hotkeys(lambda e: None, lambda: fired.append(1), "ctrl+space")
    h.start()
    holder["on_press"](kb.Key.ctrl)
    holder["on_press"](kb.Key.space)
    assert fired == [1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/Scripts/python.exe -m pytest tests/test_hotkeys_x11.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hotkeys_x11'`.

- [ ] **Step 3: Write minimal implementation**

```python
# hotkeys_x11.py
"""X11 global hotkeys via pynput. Reliability first: own thread, clean stop,
one self-heal restart if the listener dies. Verified on Ubuntu 24.04 / Xorg."""
import threading


class _Event:
    __slots__ = ("event_type", "name")
    def __init__(self, event_type, name):
        self.event_type = event_type
        self.name = name


_MOD_NAMES = {"ctrl", "alt", "shift", "cmd", "super"}


def _key_name(key):
    char = getattr(key, "char", None)
    if char:
        return char.lower()
    name = getattr(key, "name", None) or str(key).replace("Key.", "")
    return name.lower()


class X11Hotkeys:
    def __init__(self, on_key_event, on_toggle, toggle_chord):
        self._on_key_event = on_key_event
        self._on_toggle = on_toggle
        self._chord = [k.strip().lower() for k in toggle_chord.split("+") if k.strip()]
        self._down = set()
        self._listener = None
        self._watchdog = None
        self._stopped = False

    def _press(self, key):
        name = _key_name(key)
        self._down.add(name)
        self._on_key_event(_Event("down", name))
        if self._chord and all(
                (c in self._down) or (c == "ctrl" and "ctrl_l" in self._down)
                for c in self._chord):
            try:
                self._on_toggle()
            except Exception:
                pass

    def _release(self, key):
        name = _key_name(key)
        self._down.discard(name)
        self._on_key_event(_Event("up", name))

    def start(self):
        from pynput import keyboard
        self._stopped = False
        self._listener = keyboard.Listener(on_press=self._press,
                                           on_release=self._release)
        self._listener.start()
        self._watchdog = threading.Thread(target=self._watch, daemon=True)
        self._watchdog.start()

    def _watch(self):
        import time
        healed = False
        while not self._stopped:
            time.sleep(2.0)
            lis = self._listener
            if self._stopped or lis is None:
                return
            alive = getattr(lis, "is_alive", lambda: True)()
            if not alive and not healed:
                healed = True
                print("ROAR: hotkey listener died — restarting once", flush=True)
                try:
                    self.start()
                except Exception as e:
                    print(f"ROAR: hotkey restart failed ({e})", flush=True)
                return

    def stop(self):
        self._stopped = True
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
```

Note: the chord-modifier matching is intentionally forgiving (`ctrl` matches `ctrl_l`). Real pynput on X11 reports `Key.ctrl_l`/`ctrl_r`; the Ubuntu checklist confirms the exact toggle behavior and the chord match is tuned there if needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/Scripts/python.exe -m pytest tests/test_hotkeys_x11.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add hotkeys_x11.py tests/test_hotkeys_x11.py
git commit -m "feat(hotkey): X11 pynput backend with self-heal watchdog"
```

---

## Task 10: Single-instance guard seam

**Files:**
- Create: `single_instance.py`
- Modify: `app.py` (replace the `CreateMutexW` block ~lines 38–42)
- Test: `tests/test_single_instance.py`

**Interfaces:**
- Produces: `single_instance.acquire() -> bool` — True if this is the only instance (and holds the lock for process lifetime), False if another instance holds it. Windows: named mutex. Linux: `flock` on `~/.local/share/ROAR/roar.lock` (or `$XDG_RUNTIME_DIR/roar.lock` if set).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_single_instance.py
import single_instance

def test_linux_flock_first_acquires_second_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(single_instance.platform_id, "is_linux", lambda: True)
    monkeypatch.setattr(single_instance, "_lock_path", lambda: str(tmp_path / "roar.lock"))
    assert single_instance.acquire() is True    # first wins
    # second acquire from a fresh handle must fail while the first is held
    assert single_instance._acquire_linux(fresh=True) is False
```

(Skip this test on Windows if `fcntl` is unavailable — guard with `pytest.importorskip("fcntl")`; on the Windows build machine this test is expected to be skipped, and it runs for real on Ubuntu.)

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/Scripts/python.exe -m pytest tests/test_single_instance.py -v`
Expected: FAIL/skip — `ModuleNotFoundError: No module named 'single_instance'`.

- [ ] **Step 3: Write minimal implementation**

```python
# single_instance.py
"""One running ROAR per user. Windows: named mutex. Linux: flock pidfile.
The held handle lives for the process lifetime (module-global)."""
import os

import platform_id

_HANDLE = None  # keep the mutex/file handle alive for the whole process


def _lock_path():
    base = os.environ.get("XDG_RUNTIME_DIR") or os.path.join(
        os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share"), "ROAR")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "roar.lock")


def _acquire_linux(fresh=False):
    import fcntl
    global _HANDLE
    fh = open(_lock_path(), "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return False
    if not fresh:
        _HANDLE = fh
        fh.write(str(os.getpid()))
        fh.flush()
    return True


def _acquire_windows():
    import ctypes
    global _HANDLE
    ERROR_ALREADY_EXISTS = 183
    h = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\ROAR_SINGLETON")
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return False
    _HANDLE = h
    return True


def acquire() -> bool:
    if platform_id.is_linux():
        return _acquire_linux()
    return _acquire_windows()
```

In `app.py`, replace the mutex block with:

```python
import single_instance
if not single_instance.acquire():
    print("ROAR: already running - exiting", flush=True)
    sys.exit(0)
```

(Preserve the exact existing exit message/behavior so `tests/test_smoke.py` still matches.)

- [ ] **Step 4: Run tests (new + Windows smoke)**

Run: `venv/Scripts/python.exe -m pytest tests/test_single_instance.py tests/test_smoke.py -v`
Expected: PASS on Windows (Linux flock test skipped if no `fcntl`; smoke unchanged). Ensure no other ROAR instance is running before the smoke test.

- [ ] **Step 5: Commit**

```bash
git add single_instance.py app.py tests/test_single_instance.py
git commit -m "feat(app): single-instance seam (Windows mutex / Linux flock)"
```

---

## Task 11: Linux requirements + setup.sh

**Files:**
- Create: `requirements-linux.txt`, `linux/setup.sh`
- Test: `tests/test_linux_setup_assets.py` (asserts the files exist and contain the required deps/steps — a guard against drift, runnable on Windows)

**Interfaces:**
- Produces: a venv-building setup script and a pinned-enough Linux requirements file. No Python API.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_linux_setup_assets.py
import pathlib

def test_requirements_linux_has_core_deps():
    txt = pathlib.Path("requirements-linux.txt").read_text()
    for dep in ["faster-whisper", "sounddevice", "pynput", "pyperclip",
                "pywebview", "pystray", "pillow", "numpy",
                "nvidia-cublas-cu12", "nvidia-cudnn-cu12"]:
        assert dep in txt, dep

def test_setup_sh_installs_system_and_python_deps():
    sh = pathlib.Path("linux/setup.sh").read_text()
    for token in ["apt", "python3-gi", "gir1.2-webkit2-4.1",
                  "gir1.2-appindicator3", "libportaudio2", "xclip", "xdotool",
                  "python3-tk", "--system-site-packages", "nvidia-smi"]:
        assert token in sh, token
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/Scripts/python.exe -m pytest tests/test_linux_setup_assets.py -v`
Expected: FAIL — files don't exist.

- [ ] **Step 3: Write the files**

`requirements-linux.txt`:

```text
# ROAR runtime deps for Ubuntu 24.04 (X11). System GTK/webkit come from apt
# (see linux/setup.sh) and are visible via --system-site-packages.
faster-whisper
sounddevice
numpy
pynput
pyperclip
pywebview>=5
pystray
pillow
# CUDA 12 runtime for CTranslate2 GPU (NVIDIA driver must be installed on host)
nvidia-cublas-cu12
nvidia-cudnn-cu12
```

`linux/setup.sh`:

```bash
#!/usr/bin/env bash
# ROAR setup for Ubuntu 24.04 (X11). Installs system deps, creates a venv with
# --system-site-packages (so PyGObject/webkit2gtk are visible), pip-installs the
# rest, and writes the launcher. Re-runnable.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== ROAR setup (Ubuntu 24.04, X11) =="

SYS_PKGS="python3-venv python3-dev python3-tk python3-gi \
gir1.2-webkit2-4.1 gir1.2-appindicator3-0.1 libportaudio2 xclip xdotool \
libnotify-bin"
echo "System packages needed: $SYS_PKGS"
if command -v apt >/dev/null; then
  sudo apt update
  sudo apt install -y $SYS_PKGS
else
  echo "apt not found — install the above manually" >&2
fi

python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-linux.txt

if command -v nvidia-smi >/dev/null; then
  echo "NVIDIA GPU detected — CUDA acceleration will be used."
  nvidia-smi -L || true
else
  echo "No nvidia-smi found — ROAR will run on CPU (still fully functional)."
fi

mkdir -p "$HOME/.local/bin"
install -m 755 linux/roar "$HOME/.local/bin/roar"
echo "Done. Run:  ~/.local/bin/roar   (or 'roar' if ~/.local/bin is on PATH)"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/Scripts/python.exe -m pytest tests/test_linux_setup_assets.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add requirements-linux.txt linux/setup.sh tests/test_linux_setup_assets.py
git commit -m "feat(linux): requirements-linux.txt + setup.sh (venv + CUDA wheels)"
```

---

## Task 12: Launcher, desktop entry, AppImage recipe

**Files:**
- Create: `linux/roar`, `linux/roar.desktop`, `linux/build_appimage.sh`
- Test: `tests/test_linux_launcher_assets.py`

**Interfaces:**
- Produces: a launcher that activates `.venv` and runs `app.py`; a `.desktop` entry; an AppImage build recipe (run on Ubuntu).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_linux_launcher_assets.py
import pathlib

def test_launcher_runs_app_in_venv():
    sh = pathlib.Path("linux/roar").read_text()
    assert ".venv/bin/activate" in sh and "app.py" in sh

def test_desktop_entry_fields():
    d = pathlib.Path("linux/roar.desktop").read_text()
    for token in ["[Desktop Entry]", "Type=Application", "Name=ROAR", "Exec="]:
        assert token in d, token

def test_appimage_recipe_uses_pyinstaller_and_appimagetool():
    sh = pathlib.Path("linux/build_appimage.sh").read_text()
    assert "pyinstaller" in sh.lower() and "appimagetool" in sh.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/Scripts/python.exe -m pytest tests/test_linux_launcher_assets.py -v`
Expected: FAIL — files don't exist.

- [ ] **Step 3: Write the files**

`linux/roar`:

```bash
#!/usr/bin/env bash
# ROAR launcher — activates the venv and runs the app.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# when installed to ~/.local/bin, resolve the repo via a saved marker
if [ ! -f "$ROOT/app.py" ] && [ -f "$HOME/.config/ROAR/repo_path" ]; then
  ROOT="$(cat "$HOME/.config/ROAR/repo_path")"
fi
. "$ROOT/.venv/bin/activate"
exec python "$ROOT/app.py" "$@"
```

`linux/roar.desktop`:

```text
[Desktop Entry]
Type=Application
Name=ROAR
Comment=Local voice-to-text dictation
Exec=roar
Icon=roar
Terminal=false
Categories=Utility;Accessibility;
```

`linux/build_appimage.sh`:

```bash
#!/usr/bin/env bash
# Build a ROAR AppImage on Ubuntu 24.04. Unverified from the Windows dev box —
# run this on the target machine. Requires: the venv from setup.sh, pyinstaller,
# and appimagetool on PATH.
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate
pip install pyinstaller
pyinstaller --noconfirm --name ROAR --windowed app.py
APPDIR=dist/ROAR.AppDir
rm -rf "$APPDIR"; mkdir -p "$APPDIR/usr/bin"
cp -r dist/ROAR/* "$APPDIR/usr/bin/"
cp linux/roar.desktop "$APPDIR/ROAR.desktop"
cp assets/roar-logo-purple.png "$APPDIR/roar.png" 2>/dev/null || true
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/ROAR" "$@"
EOF
chmod +x "$APPDIR/AppRun"
appimagetool "$APPDIR" dist/ROAR-x86_64.AppImage
echo "Built dist/ROAR-x86_64.AppImage"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/Scripts/python.exe -m pytest tests/test_linux_launcher_assets.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add linux/roar linux/roar.desktop linux/build_appimage.sh tests/test_linux_launcher_assets.py
git commit -m "feat(linux): launcher, .desktop entry, AppImage build recipe"
```

---

## Task 13: Tray + settings-process deps on Linux (verify imports)

**Files:**
- Modify: `settings_ui.py` and/or the tray bootstrap only if a Windows-only import breaks on Linux (e.g. an unconditional `win32` import). Otherwise no code change — this task confirms the shared modules import under Linux selection.
- Test: `tests/test_linux_import_safety.py`

**Interfaces:**
- Produces: proof that `paths`, `autostart`, `injector`, `window_focus`, `hotkey_listener`, `single_instance`, `hardware_accel` all import with `platform_id` forced to Linux without touching a Windows-only lib at import time.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_linux_import_safety.py
import importlib, sys
import pytest

MODULES = ["paths", "autostart", "injector", "window_focus",
           "hotkey_listener", "single_instance", "hardware_accel"]

@pytest.mark.parametrize("mod", MODULES)
def test_module_imports_with_linux_selection(mod, monkeypatch):
    import platform_id
    monkeypatch.setattr(platform_id, "is_linux", lambda: True)
    monkeypatch.setattr(platform_id, "is_windows", lambda: False)
    sys.modules.pop(mod, None)
    importlib.import_module(mod)   # must not raise (no eager winreg/win32/ctypes.windll)
```

- [ ] **Step 2: Run test to verify it fails (or reveals eager Windows imports)**

Run: `venv/Scripts/python.exe -m pytest tests/test_linux_import_safety.py -v`
Expected: If any module eagerly imports a Windows lib at module top, it FAILS here. `autostart` (Task 3) and `single_instance` (Task 10) already moved winreg/ctypes to lazy. Fix any newly-revealed eager import by moving it inside the Windows backend method.

- [ ] **Step 3: Fix eager imports if any**

For each failing module, move the offending `import winreg` / `import win32*` / top-level `ctypes.windll` call into the Windows-only code path (a function body or the Windows backend class). Re-run.

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/Scripts/python.exe -m pytest tests/test_linux_import_safety.py -v`
Expected: PASS (all parametrized cases).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test(linux): import-safety guard; make Windows imports lazy"
```

---

## Task 14: Docs, CHANGELOG, and full regression

**Files:**
- Create: `docs/LINUX.md`
- Modify: `CHANGELOG.md`
- Test: full suite

**Interfaces:** none (docs + verification).

- [ ] **Step 1: Write docs/LINUX.md**

Include: prerequisites (Ubuntu 24.04, X11 session — how to pick "Ubuntu on Xorg" at login), `bash linux/setup.sh`, run with `~/.local/bin/roar`, the `ROAR_INJECT_BACKEND=xdotool` escape hatch, GPU note (`nvidia-smi`, `device=cuda` in `~/.local/share/ROAR/roar.log`), and the **smoke-test checklist** verbatim from the spec (9 items, hotkey = #1 must-pass, GPU = #4).

- [ ] **Step 2: Add CHANGELOG entry**

Add under a new top section:

```markdown
## Unreleased — Linux (experimental)
- **ROAR runs on Ubuntu 24.04 (X11)** from the same codebase: XDG paths,
  pynput global hotkey (self-healing), pynput/xdotool text injection, xdotool
  focus tracking, flock single-instance, .desktop autostart, CUDA GPU via the
  nvidia-cu12 wheels (Vulkan is Windows-only). Run-from-source (linux/setup.sh)
  plus an AppImage recipe. Test on 24.04/Xorg per docs/LINUX.md.
```

- [ ] **Step 3: Run the FULL suite (Windows regression + all new Linux-logic tests)**

Run: `venv/Scripts/python.exe -m pytest tests/ -q`
Expected: the prior 485 pass/1 skip PLUS all new tests pass; total green (the single-instance flock test may skip on Windows). If a pre-existing test fails only because a live ROAR instance holds the lock, stop that instance first.

- [ ] **Step 4: Confirm app still imports and version parity**

Run: `venv/Scripts/python.exe -c "import app; print('ok')"` → `ok`
Run: `venv/Scripts/python.exe scripts/roar_versions.py --check` → no drift.

- [ ] **Step 5: Commit**

```bash
git add docs/LINUX.md CHANGELOG.md
git commit -m "docs(linux): LINUX.md setup + smoke checklist; CHANGELOG"
```

---

## Handoff to the user (Ubuntu verification)

After Task 14, the Windows build is unchanged and green, and all portable Linux logic is unit-tested. The remaining verification is the human checklist in `docs/LINUX.md`, run by the user on Ubuntu 24.04 (X11):

1. `bash linux/setup.sh` completes.
2. **(MUST PASS)** hotkey → speak → types into gedit; toggle + double-tap work; still works after several dictations and after opening Settings.
3. Injection into browser field + terminal.
4. **GPU:** `device=cuda` in the log; `nvidia-smi` shows the process; CPU fallback works.
5. Overlay pill shows state.
6. Settings window renders (webkit2gtk-4.1); a change persists to `~/.config/ROAR/config.json`.
7. History records; delete history/audio; retention toggles.
8. Import a signed license → edition activates.
9. Enable autostart → `.desktop` present; re-login starts ROAR.

Report failures with the relevant `~/.local/share/ROAR/roar.log` lines; fixes iterate against this plan.
