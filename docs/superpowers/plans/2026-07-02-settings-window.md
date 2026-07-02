# FlowLocal Settings Window + Installers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deep Focus settings window (sidebar shell, hybrid apply, auto-start), rebuilt exe including it, and a WiX per-user MSI installer.

**Architecture:** Settings runs as a separate `--settings` process (pywebview window + `js_api` bridge writing config.json); the tray app hot-applies via an mtime-watching thread and a pure `diff_config`. Auto-start = HKCU Run key. MSI wraps the PyInstaller one-dir output via WiX 3.14 portable binaries (heat harvest → candle → light, per-user scope).

**Tech Stack:** pywebview 6.2.1 (WebView2), keyboard (capture), winreg (autostart), PyInstaller 6.21.0, WiX 3.14.1 portable.

## Global Constraints

- Project: `C:\Users\xhan1\flowlocal`, branch `main`, venv interpreter `venv/Scripts/python.exe`.
- Spec: `docs/superpowers/specs/2026-07-02-settings-window-design.md` — Deep Focus tokens verbatim: bg `#0B0E14`, sidebar `#070A0F`, card `#121722`, border `#1E2635`, text `#E8ECF4`, muted `#9AA4BC`, disabled `#3E4557`, accent `#2563EB` (+glow `rgba(37,99,235,.25-.6)`).
- Hybrid apply: instant = auto-start, tones, paste fallback, sensitivity, mic device; Apply = hotkeys, model.
- Version: `__version__ = "0.2.0"` in app.py; MSI ProductVersion 0.2.0; git tag v0.2.0 at the end.
- Stdout markers (settings smoke): `FlowLocal: settings window ready`, `FlowLocal: settings closed`.
- The tray app instance (FlowLocal.exe) must be killed before test runs (mutex + hooks) and the new exe relaunched for the user at the very end.
- All new deps pinned. Commit per task. Push at the end and fix any push failures.

---

### Task 1: autostart.py — HKCU Run key

**Files:** Create `autostart.py`, `tests/test_autostart.py`

**Interfaces:** Produces `get(name: str) -> str | None` (current command or None), `set_enabled(name: str, command: str, enabled: bool) -> None`, `default_command() -> str` (frozen → FlowLocal.exe path; source → `"<pythonw> <abs app.py>"`).

- [ ] **Step 1: failing test** `tests/test_autostart.py`:

```python
import os
import autostart

NAME = f"FlowLocalTest{os.getpid()}"


def test_round_trip_and_cleanup():
    try:
        assert autostart.get(NAME) is None
        autostart.set_enabled(NAME, '"C:\\fake\\FlowLocal.exe"', True)
        assert autostart.get(NAME) == '"C:\\fake\\FlowLocal.exe"'
        autostart.set_enabled(NAME, '"C:\\fake\\FlowLocal.exe"', False)
        assert autostart.get(NAME) is None
        autostart.set_enabled(NAME, "x", False)  # disabling absent key is a no-op
    finally:
        autostart.set_enabled(NAME, "x", False)


def test_default_command_points_at_app():
    cmd = autostart.default_command()
    assert "app.py" in cmd and "pythonw" in cmd.lower()
```

- [ ] **Step 2:** Run `venv/Scripts/python.exe -m pytest tests/test_autostart.py -v` → ModuleNotFoundError.
- [ ] **Step 3:** `autostart.py`:

```python
"""Start-with-Windows via HKCU Run key. No admin required."""
import os
import sys
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def get(name: str):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _type = winreg.QueryValueEx(key, name)
            return value
    except OSError:
        return None


def set_enabled(name: str, command: str, enabled: bool):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, name)
            except OSError:
                pass  # already absent


def default_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    app = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    return f'"{pythonw}" "{app}"'
```

- [ ] **Step 4:** pytest passes (2).
- [ ] **Step 5:** `git commit -m "feat: autostart via HKCU Run key"`

---

### Task 2: diff_config + config watcher (hot apply)

**Files:** Modify `app.py`; Create `tests/test_diff_config.py`

**Interfaces:** Produces module-level `diff_config(old: dict, new: dict) -> list[tuple]` in app.py — actions: `("rehook", None)`, `("reload_model", name)`, `("set_device", idx)`. FlowLocalApp gains `_watch_config()` daemon thread started in `run()`.

- [ ] **Step 1: failing test** `tests/test_diff_config.py`:

```python
import copy

from app import diff_config
from config import DEFAULTS


def _pair(**changes):
    old = copy.deepcopy(DEFAULTS)
    new = copy.deepcopy(DEFAULTS)
    new.update(changes)
    return old, new


def test_no_change_no_actions():
    assert diff_config(*_pair()) == []


def test_hotkey_change_rehooks_once():
    old, new = _pair(hotkey_ptt="ctrl+alt", hotkey_toggle="ctrl+alt+space")
    assert diff_config(old, new) == [("rehook", None)]


def test_model_and_device():
    old, new = _pair(model="tiny.en", input_device=3)
    assert ("reload_model", "tiny.en") in diff_config(old, new)
    assert ("set_device", 3) in diff_config(old, new)


def test_instant_keys_produce_no_actions():
    old, new = _pair(tones_enabled=False, paste_fallback=True,
                     silence_rms_threshold=0.01)
    assert diff_config(old, new) == []
```

- [ ] **Step 2:** Run → ImportError (no diff_config).
- [ ] **Step 3:** In `app.py` add after `parse_chord`:

```python
def diff_config(old: dict, new: dict):
    """Map a config-file change to the actions the running app must take.
    Instant keys (tones, thresholds, paste_fallback, replacements) are read
    at use time and need no action."""
    actions = []
    if (old["hotkey_ptt"] != new["hotkey_ptt"]
            or old["hotkey_toggle"] != new["hotkey_toggle"]):
        actions.append(("rehook", None))
    if old["model"] != new["model"]:
        actions.append(("reload_model", new["model"]))
    if old["input_device"] != new["input_device"]:
        actions.append(("set_device", new["input_device"]))
    return actions
```

and in `FlowLocalApp`:

```python
    def _watch_config(self):
        import time as _time
        last = None
        while not self._stop_watch.is_set():
            try:
                mtime = os.path.getmtime(config_mod.PATH)
                if last is None:
                    last = mtime
                elif mtime != last:
                    last = mtime
                    new_cfg = config_mod.load()
                    for action, arg in diff_config(self.cfg, new_cfg):
                        if action == "rehook":
                            keyboard.unhook_all()
                            self.pressed.clear()
                            self.cfg.update(new_cfg)
                            self.ptt_chord = parse_chord(self.cfg["hotkey_ptt"])
                            self._register_hotkeys()
                            self.notify("Hotkeys updated")
                        elif action == "reload_model":
                            self.jobs.put(("reload", arg))
                        elif action == "set_device":
                            self.recorder.device = arg
                    self.cfg.update(new_cfg)
            except OSError:
                pass  # config briefly missing/locked — retry next tick
            self._stop_watch.wait(2.0)
```

`__init__` gains `self._stop_watch = threading.Event()`; `run()` starts `threading.Thread(target=self._watch_config, daemon=True)` before the tray loop; `_quit()` sets `self._stop_watch.set()` first.

- [ ] **Step 4:** pytest test_diff_config passes (4); full suite green (kill FlowLocal.exe first).
- [ ] **Step 5:** `git commit -m "feat: config watcher hot-applies external config edits"`

---

### Task 3: capture normalization + settings bridge (settings_ui.py)

**Files:** Create `settings_ui.py`, `hotkeys.py`, `tests/test_settings_bridge.py`; Modify `paths.py` (resource_path + `APP_VERSION = "0.2.0"`), `app.py` (import chord helpers from hotkeys, `__version__ = paths.APP_VERSION`)

**Import-weight rule:** the settings process must NOT import `app` or `transcriber` (they load the ML stack). `hotkeys.py` holds `MODIFIER_ALIASES` + `parse_chord` moved verbatim out of app.py; both app.py and settings_ui.py import from it.

**Interfaces:** Produces `normalize_combo(keys: set[str]) -> str`; `class SettingsAPI(config_path=None)` with `get_state()`, `set_value(key, value)`, `apply_hotkeys(ptt, toggle)`, `apply_model(name)`, `set_autostart(enabled)`, `capture_hotkey()`, `open_path(path)`; `run_settings(smoke=False)`. `paths.resource_path(name) -> str` (frozen: `<exe_dir>/_internal/<name>`; source: project root).

- [ ] **Step 1: failing test** `tests/test_settings_bridge.py`:

```python
import json

import config
from settings_ui import SettingsAPI, normalize_combo


def test_normalize_combo_orders_and_merges_sides():
    assert normalize_combo({"left ctrl", "left windows"}) == "ctrl+windows"
    assert normalize_combo({"right shift", "z", "left alt"}) == "alt+shift+z"
    assert normalize_combo(set()) == ""


def test_set_value_whitelist(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.set_value("tones_enabled", False)["ok"] is True
    assert config.load(p)["tones_enabled"] is False
    assert "error" in api.set_value("model", "tiny.en")  # model is Apply-only


def test_apply_hotkeys_validates(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.apply_hotkeys("ctrl+alt", "ctrl+alt+space")["ok"] is True
    assert config.load(p)["hotkey_ptt"] == "ctrl+alt"
    assert "error" in api.apply_hotkeys("", "ctrl+space")


def test_apply_model(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.apply_model("small.en")["ok"] is True
    assert config.load(p)["model"] == "small.en"
    assert "error" in api.apply_model("bogus-model")


def test_get_state_shape(tmp_path):
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    s = api.get_state()
    assert s["config"]["hotkey_ptt"] == "ctrl+windows"
    assert isinstance(s["devices"], list) and isinstance(s["autostart"], bool)
    assert s["version"] == "0.2.0"
```

- [ ] **Step 2:** Run → ModuleNotFoundError.
- [ ] **Step 3:** Add to `paths.py`:

```python
def resource_path(name: str) -> str:
    if is_frozen():
        return os.path.join(os.path.dirname(sys.executable), "_internal", name)
    return os.path.join(_source_root(), name)
```

Add `__version__ = "0.2.0"` near the top of `app.py`. Create `settings_ui.py`:

```python
"""Settings window process: pywebview + JS bridge. Run via app.py --settings."""
import ctypes
import os
import sys
import threading

import autostart
import config as config_mod
import paths
import recorder as recorder_mod

APP_NAME = "FlowLocal"
SETTINGS_MUTEX = "Global\\FlowLocalSettings"
MODEL_CHOICES = ["auto", "tiny.en", "base.en", "small.en", "medium.en",
                 "distil-large-v3"]
INSTANT_KEYS = {"tones_enabled", "paste_fallback", "silence_rms_threshold",
                "input_device"}
_SIDE = {"left ctrl": "ctrl", "right ctrl": "ctrl", "left shift": "shift",
         "right shift": "shift", "left alt": "alt", "alt gr": "alt",
         "right alt": "alt", "left windows": "windows",
         "right windows": "windows"}
_ORDER = {"ctrl": 0, "alt": 1, "shift": 2, "windows": 3}


def normalize_combo(keys) -> str:
    canon = {_SIDE.get(k, k) for k in keys}
    return "+".join(sorted(canon, key=lambda k: (_ORDER.get(k, 9), k)))


class SettingsAPI:
    def __init__(self, config_path=None):
        self.config_path = config_path or config_mod.PATH

    # -- state ---------------------------------------------------------
    def get_state(self):
        return {
            "config": config_mod.load(self.config_path),
            "autostart": autostart.get(APP_NAME) is not None,
            "devices": recorder_mod.list_input_devices(),
            "models": MODEL_CHOICES,
            "version": paths.APP_VERSION,
            "config_path": self.config_path,
            "log_path": paths.log_path(),
        }

    def _write(self, **changes):
        cfg = config_mod.load(self.config_path)
        cfg.update(changes)
        config_mod.save(cfg, self.config_path)

    # -- instant keys ----------------------------------------------------
    def set_value(self, key, value):
        if key not in INSTANT_KEYS:
            return {"error": f"{key} is not an instant-apply setting"}
        if key == "silence_rms_threshold":
            try:
                value = min(0.02, max(0.001, float(value)))
            except (TypeError, ValueError):
                return {"error": "sensitivity must be a number"}
        self._write(**{key: value})
        return {"ok": True}

    # -- Apply-gated -----------------------------------------------------
    def apply_hotkeys(self, ptt, toggle):
        from hotkeys import parse_chord
        for label, hk in (("push-to-talk", ptt), ("toggle", toggle)):
            parts = parse_chord(hk or "")
            if not 1 <= len(parts) <= 4:
                return {"error": f"{label} hotkey is invalid"}
        if ptt == toggle:
            return {"error": "hotkeys must differ"}
        self._write(hotkey_ptt=ptt, hotkey_toggle=toggle)
        return {"ok": True}

    def apply_model(self, name):
        if name not in MODEL_CHOICES:
            return {"error": f"unknown model {name}"}
        self._write(model=name)
        return {"ok": True}

    def set_autostart(self, enabled):
        try:
            autostart.set_enabled(APP_NAME, autostart.default_command(),
                                  bool(enabled))
            return {"ok": True}
        except OSError as e:
            return {"error": f"registry access failed: {e}"}

    # -- hotkey capture ----------------------------------------------------
    def capture_hotkey(self):
        import keyboard
        pressed, snapshot = set(), []
        done = threading.Event()

        def on_event(e):
            name = (e.name or "").lower()
            if e.event_type == "down":
                pressed.add(name)
            elif pressed:
                snapshot.append(frozenset(pressed))
                done.set()

        hook = keyboard.hook(on_event)
        done.wait(timeout=5.0)
        keyboard.unhook(hook)
        if not snapshot:
            return {"error": "no keys pressed — hold the combo you want"}
        combo = normalize_combo(snapshot[0])
        if not combo:
            return {"error": "could not read that combination"}
        return {"hotkey": combo}

    def open_path(self, path):
        allowed = {self.config_path, paths.log_path()}
        if path in allowed and os.path.exists(path):
            os.startfile(path)
            return {"ok": True}
        return {"error": "unknown path"}


def run_settings(smoke=False):
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, SETTINGS_MUTEX)
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        print("FlowLocal: settings already open", flush=True)
        return 0
    try:
        import webview
    except Exception as e:
        print(f"FlowLocal: settings UI unavailable ({e}); opening config.json",
              flush=True)
        os.startfile(config_mod.PATH)
        return 1
    api = SettingsAPI()
    window = webview.create_window(
        "FlowLocal Settings", url=paths.resource_path("settings.html"),
        js_api=api, width=900, height=640, min_size=(760, 560),
        background_color="#0B0E14")

    def on_shown():
        print("FlowLocal: settings window ready", flush=True)
        if smoke:
            threading.Timer(2.5, window.destroy).start()

    window.events.shown += on_shown
    webview.start()
    print("FlowLocal: settings closed", flush=True)
    return 0
```

- [ ] **Step 4:** `pip install pywebview==6.2.1`; add `pywebview==6.2.1` to requirements.txt. pytest test_settings_bridge passes (5).
- [ ] **Step 5:** `git commit -m "feat: settings bridge, hotkey capture, resource paths"`

---

### Task 4: settings.html (Deep Focus UI)

**Files:** Create `settings.html`

**Interfaces:** Consumes the SettingsAPI bridge exactly as defined in Task 3. Sidebar sections: General, Hotkeys, Voice & Mic, Transcription, Privacy (soon), History (soon), About.

- [ ] **Step 1:** Write `settings.html` — single file, inline CSS/JS, Deep Focus tokens, `pywebviewready` bootstrap, instant handlers → `set_value`/`set_autostart`, Apply flows for hotkeys/model with inline errors, capture buttons → `capture_hotkey`, sensitivity slider on a log scale (0–100 ↔ 0.001–0.02), About with clickable paths. (Full markup written at execution; structure and behavior are fixed by this plan + spec. UUPM checks: body contrast ≥4.5:1 on #121722, focus-visible outlines, aria-pressed on toggles, no animations.)
- [ ] **Step 2:** Manual check: `venv/Scripts/python.exe app.py --settings` opens the window, all sections navigate, toggles persist to config.json.
- [ ] **Step 3:** `git commit -m "feat: Deep Focus settings UI"`

---

### Task 5: app.py wiring (--settings, tray item) + settings smoke test

**Files:** Modify `app.py`; Create `tests/test_settings_smoke.py`

**Interfaces:** `app.py --settings [--smoke]` → `settings_ui.run_settings(smoke)`, exits before the main mutex. Tray menu gains `Settings…` above `Open config`, spawning the settings process.

- [ ] **Step 1: failing test** `tests/test_settings_smoke.py`:

```python
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_settings_smoke():
    proc = subprocess.Popen(
        [sys.executable, "app.py", "--settings", "--smoke"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out, _ = proc.communicate(timeout=120)
    assert "FlowLocal: settings window ready" in out
    assert "FlowLocal: settings closed" in out
    assert proc.returncode == 0
```

- [ ] **Step 2:** Run → fails (unknown flag).
- [ ] **Step 3:** In `main()` add `parser.add_argument("--settings", action="store_true")`; before the mutex block:

```python
    if args.settings:
        import settings_ui
        sys.exit(settings_ui.run_settings(smoke=args.smoke))
```

In `_build_menu` add above Open config: `Item("Settings…", self._open_settings),` and:

```python
    def _open_settings(self):
        if getattr(sys, "frozen", False):
            subprocess.Popen([sys.executable, "--settings"])
        else:
            subprocess.Popen([sys.executable,
                              os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "app.py"), "--settings"])
```

- [ ] **Step 4:** settings smoke passes; FULL suite green.
- [ ] **Step 5:** `git commit -m "feat: --settings mode + tray menu entry"`

---

### Task 6: exe rebuild with settings UI

**Files:** Modify `flowlocal.spec` (datas + pywebview collect), rebuild.

- [ ] **Step 1:** In `flowlocal.spec`: append `("settings.html", ".")` to datas — `datas += [("settings.html", ".")]` after the collect loop — and add `"webview"` to the collect_all list (pywebview's package name is `webview`).
- [ ] **Step 2:** Kill FlowLocal.exe; `venv/Scripts/python.exe -m PyInstaller flowlocal.spec --noconfirm`.
- [ ] **Step 3:** Launch `dist/FlowLocal/FlowLocal.exe`; verify log markers incl. cuda; open Settings from the tray — requires manual/scripted check: run `dist/FlowLocal/FlowLocal.exe --settings --smoke` and assert both settings markers + exit 0 (frozen stdout goes to the log file — assert there instead).
- [ ] **Step 4:** `git commit -m "build: bundle settings UI into the exe"`

---

### Task 7: WiX per-user MSI

**Files:** Create `installer/flowlocal.wxs`, `scripts/build_msi.sh`

**Interfaces:** Produces `dist/FlowLocal-0.2.0.msi`. UpgradeCode fixed: `a7a83e4a-83a0-4834-8edc-8dc058eb254f`; shortcut component GUID `ba071046-31e9-4dde-95ba-54fdc712cd9e`.

- [ ] **Step 1:** `installer/flowlocal.wxs`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="*" Name="FlowLocal" Language="1033" Version="0.2.0"
           Manufacturer="xhan145"
           UpgradeCode="a7a83e4a-83a0-4834-8edc-8dc058eb254f">
    <Package InstallerVersion="500" Compressed="yes" InstallScope="perUser"
             Description="FlowLocal — local voice-to-text dictation" />
    <MajorUpgrade DowngradeErrorMessage="A newer version of FlowLocal is already installed." />
    <MediaTemplate EmbedCab="yes" CompressionLevel="high" />
    <Property Id="ALLUSERS" Value="" Secure="yes" />
    <Directory Id="TARGETDIR" Name="SourceDir">
      <Directory Id="LocalAppDataFolder">
        <Directory Id="ProgramsFolder" Name="Programs">
          <Directory Id="INSTALLDIR" Name="FlowLocal" />
        </Directory>
      </Directory>
      <Directory Id="ProgramMenuFolder">
        <Directory Id="AppMenuFolder" Name="FlowLocal" />
      </Directory>
    </Directory>
    <DirectoryRef Id="AppMenuFolder">
      <Component Id="StartMenuShortcut"
                 Guid="ba071046-31e9-4dde-95ba-54fdc712cd9e">
        <Shortcut Id="AppShortcut" Name="FlowLocal"
                  Target="[INSTALLDIR]FlowLocal.exe"
                  WorkingDirectory="INSTALLDIR" />
        <RemoveFolder Id="RemoveAppMenu" On="uninstall" />
        <RegistryValue Root="HKCU" Key="Software\FlowLocal" Name="installed"
                       Type="integer" Value="1" KeyPath="yes" />
      </Component>
    </DirectoryRef>
    <Feature Id="Main" Title="FlowLocal" Level="1">
      <ComponentGroupRef Id="AppFiles" />
      <ComponentRef Id="StartMenuShortcut" />
    </Feature>
  </Product>
</Wix>
```

- [ ] **Step 2:** `scripts/build_msi.sh`:

```bash
#!/usr/bin/env bash
# Build dist/FlowLocal-<version>.msi from the PyInstaller one-dir output.
# Downloads WiX 3.14 portable binaries to build/wix on first run.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="0.2.0"
WIX=build/wix
[ -d dist/FlowLocal ] || { echo "run PyInstaller first"; exit 1; }
if [ ! -f "$WIX/heat.exe" ]; then
  mkdir -p "$WIX"
  curl -L -o "$WIX/wix314.zip" \
    https://github.com/wixtoolset/wix3/releases/download/wix3141rtm/wix314-binaries.zip
  (cd "$WIX" && unzip -oq wix314.zip && rm wix314.zip)
fi
"$WIX/heat.exe" dir dist/FlowLocal -cg AppFiles -dr INSTALLDIR \
  -srd -sreg -scom -ag -sfrag -template fragment -out build/harvest.wxs
"$WIX/candle.exe" -nologo -arch x64 -out build/ \
  build/harvest.wxs installer/flowlocal.wxs
"$WIX/light.exe" -nologo -b dist/FlowLocal -sval \
  -out "dist/FlowLocal-$VERSION.msi" build/harvest.wixobj build/flowlocal.wixobj
echo "built dist/FlowLocal-$VERSION.msi"
```

- [ ] **Step 3:** Run it; expect `built dist/FlowLocal-0.2.0.msi`.
- [ ] **Step 4: install/uninstall verification (per-user, no admin):**

```bash
msiexec //i "dist\\FlowLocal-0.2.0.msi" //qn
# wait for completion, then:
ls "$LOCALAPPDATA/Programs/FlowLocal/FlowLocal.exe"          # exists
"$LOCALAPPDATA/Programs/FlowLocal/FlowLocal.exe" --settings --smoke  # markers in log
msiexec //x "dist\\FlowLocal-0.2.0.msi" //qn
ls "$LOCALAPPDATA/Programs/FlowLocal" 2>/dev/null            # gone
```

(Kill any running FlowLocal.exe first; mind the mutex.)

- [ ] **Step 5:** `git commit -m "build: WiX per-user MSI installer"`

---

### Task 8: docs, adversarial review, push, tag, relaunch

- [ ] **Step 1:** README: Settings section (tray → Settings…, what's instant vs Apply), MSI paragraph under Packaged app (build_msi.sh, per-user install location), bump test count.
- [ ] **Step 2:** Ultracode adversarial review workflow over the new diff (threading of watcher, bridge validation, registry, wxs); fix confirmed findings; suite green.
- [ ] **Step 3:** Full suite green ×2 (exit codes checked, not tail).
- [ ] **Step 4:** Commit; `git push origin main`; on failure diagnose (auth/remote/size) and fix until pushed. Tag `v0.2.0`, push tag.
- [ ] **Step 5:** Relaunch `dist/FlowLocal/FlowLocal.exe` for the user.
