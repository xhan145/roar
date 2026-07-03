"""Settings window process: pywebview + JS bridge. Run via app.py --settings.

Must never import app.py or transcriber.py — those pull the ML stack
(ctranslate2 + CUDA DLLs) into what should be a lightweight UI process.
"""
import ctypes
import os
import threading

import autostart
import config as config_mod
import paths
import recorder as recorder_mod
from hotkeys import parse_chord

APP_NAME = "FlowLocal"
SETTINGS_MUTEX = "Global\\FlowLocalSettings"
MODEL_CHOICES = ["auto", "tiny.en", "base.en", "small.en", "medium.en",
                 "distil-large-v3"]
INSTANT_KEYS = {"tones_enabled", "paste_fallback", "silence_rms_threshold",
                "input_device", "history_enabled", "audio_retention_days"}
RETENTION_CHOICES = {0, 1, 7, 30, 90}
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
        self._hist = None

    @property
    def _history(self):
        if self._hist is None:
            import history as history_mod
            self._hist = history_mod.History()
        return self._hist

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
        if key == "audio_retention_days":
            try:
                value = int(value)
            except (TypeError, ValueError):
                return {"error": "retention must be a number"}
            if value not in RETENTION_CHOICES:
                return {"error": "retention must be one of 0, 1, 7, 30, 90 days"}
        if key == "history_enabled":
            value = bool(value)
        self._write(**{key: value})
        if key == "audio_retention_days":
            try:
                self._history.purge_expired(value)
            except Exception:
                pass
        return {"ok": True}

    # -- history / privacy ----------------------------------------------
    def history_list(self, limit=100):
        return self._history.list(limit=limit)

    def history_delete(self, rid):
        self._history.delete(int(rid))
        return {"ok": True}

    def history_clear(self):
        return {"ok": True, "removed": self._history.clear()}

    def privacy_stats(self):
        s = self._history.stats()
        return {"count": s["count"], "audio_count": s["audio_count"],
                "audio_mb": round(s["audio_bytes"] / (1024 * 1024), 1)}

    # -- Apply-gated -----------------------------------------------------
    def apply_hotkeys(self, ptt, toggle):
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
    html = paths.resource_path("settings.html")
    if not os.path.exists(html):
        print(f"FlowLocal: settings.html missing at {html}; opening config.json",
              flush=True)
        os.startfile(config_mod.PATH)
        return 1
    api = SettingsAPI()
    window = webview.create_window(
        "FlowLocal Settings", url=html,
        js_api=api, width=900, height=640, min_size=(760, 560),
        background_color="#0B0E14")

    def on_shown():
        print("FlowLocal: settings window ready", flush=True)
        if smoke:
            def probe_and_close():
                try:
                    navs = window.evaluate_js(
                        "document.querySelectorAll('.nav').length")
                    ver = window.evaluate_js(
                        "document.getElementById('a-version').textContent")
                    has_priv = window.evaluate_js(
                        "document.getElementById('s-retention') ? 1 : 0")
                    print(f"FlowLocal: settings probe navs={navs} version={ver} priv={has_priv}",
                          flush=True)
                finally:
                    window.destroy()
            threading.Timer(2.5, probe_and_close).start()

    window.events.shown += on_shown
    webview.start()
    print("FlowLocal: settings closed", flush=True)
    return 0
