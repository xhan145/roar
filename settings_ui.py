"""Settings window process: pywebview + JS bridge. Run via app.py --settings.

Must never import app.py or transcriber.py — those pull the ML stack
(ctranslate2 + CUDA DLLs) into what should be a lightweight UI process.
"""
import ctypes
import json
import os
import threading
import urllib.request

import autostart
import config as config_mod
import paths
import recorder as recorder_mod
from hotkeys import parse_chord

APP_NAME = paths.APP_NAME
SETTINGS_MUTEX = "Global\\ROARSettings"
MODEL_CHOICES = ["auto", "tiny.en", "base.en", "small.en", "medium.en",
                 "distil-large-v3", "small", "large-v3-turbo"]
LANGUAGE_LABELS = {
    "auto": "Auto-detect", "en": "English", "es": "Español", "fr": "Français",
    "de": "Deutsch", "it": "Italiano", "pt": "Português", "nl": "Nederlands",
    "pl": "Polski", "ru": "Русский", "uk": "Українська", "zh": "中文",
    "ja": "日本語", "ko": "한국어", "ar": "العربية", "hi": "हिन्दी",
    "tr": "Türkçe",
}
_COMMON_ORDER = ["auto", "en", "es", "fr", "de", "it", "pt", "nl", "pl",
                 "ru", "uk", "zh", "ja", "ko", "ar", "hi", "tr"]


def _language_options():
    from languages import CODES  # static — never imports faster_whisper
    codes = sorted(CODES)
    rest = [c for c in codes if c not in _COMMON_ORDER]
    return ([[c, LANGUAGE_LABELS.get(c, c)] for c in _COMMON_ORDER]
            + [[c, c] for c in rest])
INSTANT_KEYS = {"tones_enabled", "paste_fallback", "silence_rms_threshold",
                "input_device", "history_enabled", "audio_retention_days",
                "auto_vocabulary", "overlay_enabled", "streaming_preview",
                "cleanup_enabled", "remove_discourse_fillers",
                "milestones_enabled", "milestone_notifications",
                "context_aware"}
RETENTION_CHOICES = {0, 1, 7, 30, 90}
_SIDE = {"left ctrl": "ctrl", "right ctrl": "ctrl", "left shift": "shift",
         "right shift": "shift", "left alt": "alt", "alt gr": "alt",
         "right alt": "alt", "left windows": "windows",
         "right windows": "windows"}
_ORDER = {"ctrl": 0, "alt": 1, "shift": 2, "windows": 3}

# set by run_settings once the window exists; file dialogs hang off it
_WINDOW = None

REPO_URL = "https://github.com/xhan145/roar"
TAGS_URL = "https://api.github.com/repos/xhan145/roar/tags?per_page=1"


def _version_tuple(v):
    return tuple(int(p) for p in v.strip().lstrip("v").split("."))


def normalize_combo(keys) -> str:
    canon = {_SIDE.get(k, k) for k in keys}
    return "+".join(sorted(canon, key=lambda k: (_ORDER.get(k, 9), k)))


class SettingsAPI:
    def __init__(self, config_path=None):
        self.config_path = config_path or config_mod.PATH
        self._hist = None
        # pywebview runs each JS call on its own thread — guard lazy init
        self._hist_lock = threading.Lock()
        # ...and serialize config read-modify-write cycles (two concurrent
        # JS calls could otherwise lose each other's writes)
        self._cfg_lock = threading.RLock()

    @property
    def _history(self):
        with self._hist_lock:
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
            "languages": _language_options(),
            "logo_path": paths.resource_path("assets/roar-logo-purple-256.png"),
        }

    def _write(self, **changes):
        with self._cfg_lock:
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
        if key in ("history_enabled", "auto_vocabulary",
                   "overlay_enabled", "streaming_preview",
                   "cleanup_enabled", "remove_discourse_fillers",
                   "milestones_enabled", "milestone_notifications",
                   "context_aware"):
            value = bool(value)
        self._write(**{key: value})
        if key == "audio_retention_days":
            try:
                self._history.purge_expired(value)
            except Exception:
                pass
        return {"ok": True}

    # -- history / privacy / insights ------------------------------------
    def get_insights(self):
        from insights import compute_insights
        rows = self._history.list(limit=5000)
        result = compute_insights(rows,
                                  total_words=self._history.total_words(),
                                  unlocks=self._history.unlocks())
        # be honest when the analysis window doesn't cover everything
        total = self._history.stats()["count"]
        result["truncated_from"] = total if total > len(rows) else None
        return result

    def history_list(self, limit=100, query=None):
        return self._history.list(limit=limit, query=query or None)

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

    def apply_model(self, name=None, language=None):
        """Write only what the user actually changed — sending a cached model
        on a language-only change could clobber external edits."""
        changes = {}
        if name is not None:
            if name not in MODEL_CHOICES:
                return {"error": f"unknown model {name}"}
            changes["model"] = name
        if language is not None:
            if not config_mod.valid_language(language):
                return {"error": f"unknown language {language}"}
            changes["language"] = language
        if not changes:
            return {"error": "nothing to apply"}
        self._write(**changes)
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

    # -- vocabulary --------------------------------------------------------
    def vocab_get(self):
        cfg = config_mod.load(self.config_path)
        auto_words = []
        if cfg.get("auto_vocabulary", True):
            try:
                from insights import compute_insights
                auto_words = compute_insights(
                    self._history.list(limit=5000))["signature_words"]
            except Exception:
                pass
        return {"custom": cfg.get("custom_vocabulary", []),
                "auto_enabled": bool(cfg.get("auto_vocabulary", True)),
                "auto_words": auto_words}

    def vocab_add(self, word):
        from vocabulary import normalize_entry, validate_entry
        with self._cfg_lock:
            cfg = config_mod.load(self.config_path)
            custom = [str(w) for w in cfg.get("custom_vocabulary", [])]
            err = validate_entry(word, custom)
            if err:
                return {"error": err}
            custom.append(normalize_entry(word))
            self._write(custom_vocabulary=custom)
        return {"ok": True, "custom": custom}

    def vocab_remove(self, word):
        with self._cfg_lock:
            cfg = config_mod.load(self.config_path)
            target = str(word).strip().lower()
            custom = [w for w in cfg.get("custom_vocabulary", [])
                      if str(w).strip().lower() != target]
            self._write(custom_vocabulary=custom)
        return {"ok": True, "custom": custom}

    # -- snippets ----------------------------------------------------------
    def snippets_get(self):
        cfg = config_mod.load(self.config_path)
        return {"snippets": cfg.get("snippets", {}),
                "keyword": cfg.get("snippet_keyword", "snippet")}

    def snippet_save(self, name, text):
        from snippets import validate
        with self._cfg_lock:
            cfg = config_mod.load(self.config_path)
            sn = dict(cfg.get("snippets", {}))
            err = validate(name, text, sn)
            if err:
                return {"error": err}
            for k in list(sn):
                if k.lower() == name.lower():
                    del sn[k]
            sn[name] = text
            self._write(snippets=sn)
        return {"ok": True}

    def snippet_delete(self, name):
        with self._cfg_lock:
            cfg = config_mod.load(self.config_path)
            sn = {k: v for k, v in cfg.get("snippets", {}).items()
                  if k.lower() != str(name).lower()}
            self._write(snippets=sn)
        return {"ok": True}

    def snippets_export(self):
        import json as _json
        import webview
        if _WINDOW is None:
            return {"error": "no window"}
        path = _WINDOW.create_file_dialog(
            webview.SAVE_DIALOG, save_filename="roar-snippets.json")
        if not path:
            return {"cancelled": True}
        path = path if isinstance(path, str) else path[0]
        cfg = config_mod.load(self.config_path)
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(cfg.get("snippets", {}), f, indent=2, ensure_ascii=False)
        return {"ok": True, "path": str(path)}

    def snippets_import(self):
        import json as _json
        import webview
        from snippets import validate
        if _WINDOW is None:
            return {"error": "no window"}
        path = _WINDOW.create_file_dialog(webview.OPEN_DIALOG)
        if not path:
            return {"cancelled": True}
        path = path if isinstance(path, str) else path[0]
        try:
            with open(path, encoding="utf-8") as f:
                incoming = _json.load(f)
            if not isinstance(incoming, dict):
                raise ValueError("top level must be an object")
        except Exception as e:
            return {"error": f"not a snippet pack: {e}"}
        added = renamed = 0
        with self._cfg_lock:
            cfg = config_mod.load(self.config_path)
            sn = dict(cfg.get("snippets", {}))
            lower = {k.lower() for k in sn}
            for name, text in incoming.items():
                if not isinstance(name, str) or not isinstance(text, str):
                    continue
                target = name
                if name.lower() in lower:
                    target = f"{name}-2"
                    if target.lower() in lower:
                        continue
                    renamed += 1
                if validate(target, text, sn) is None:
                    sn[target] = text
                    lower.add(target.lower())
                    added += 1
            self._write(snippets=sn)
        return {"ok": True, "added": added, "renamed": renamed}

    # -- updates -----------------------------------------------------------
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

    def open_path(self, path):
        allowed = {self.config_path, paths.log_path()}
        if path in allowed and os.path.exists(path):
            os.startfile(path)
            return {"ok": True}
        return {"error": "unknown path"}


def run_settings(smoke=False):
    # (legacy-data migration already ran in app.main before dispatch here)
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, SETTINGS_MUTEX)
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        print("ROAR: settings already open", flush=True)
        return 0
    try:
        import webview
    except Exception as e:
        print(f"ROAR: settings UI unavailable ({e}); opening config.json",
              flush=True)
        os.startfile(config_mod.PATH)
        return 1
    html = paths.resource_path("settings.html")
    if not os.path.exists(html):
        print(f"ROAR: settings.html missing at {html}; opening config.json",
              flush=True)
        os.startfile(config_mod.PATH)
        return 1
    global _WINDOW
    api = SettingsAPI()
    window = webview.create_window(
        "ROAR Settings", url=html,
        js_api=api, width=900, height=640, min_size=(760, 560),
        background_color="#020203")
    _WINDOW = window

    page_loaded = threading.Event()

    def on_loaded():
        page_loaded.set()

    def on_shown():
        print("ROAR: settings window ready", flush=True)
        if smoke:
            def probe_and_close():
                try:
                    # 'shown' means the WINDOW exists; the page may still be
                    # loading (evaluate_js would raise). Wait for 'loaded',
                    # then give init() a beat, and retry on stragglers.
                    page_loaded.wait(timeout=30)
                    import time as _time
                    _time.sleep(1.0)
                    for attempt in range(3):
                        try:
                            navs = window.evaluate_js(
                                "document.querySelectorAll('.nav').length")
                            break
                        except Exception:
                            if attempt == 2:
                                raise
                            _time.sleep(1.5)
                    # version is populated by init() AFTER pywebviewready —
                    # poll until it's actually there instead of racing it
                    ver = ""
                    for _ in range(20):
                        ver = window.evaluate_js(
                            "document.getElementById('a-version').textContent") or ""
                        if any(ch.isdigit() for ch in ver):
                            break
                        _time.sleep(0.5)
                    has_priv = window.evaluate_js(
                        "document.getElementById('s-retention') ? 1 : 0")
                    has_ovl = window.evaluate_js(
                        "document.getElementById('t-overlay') ? 1 : 0")
                    has_lang = window.evaluate_js(
                        "document.getElementById('s-language') ? 1 : 0")
                    # tabs must be REACHABLE, not merely present in the DOM
                    priv_nav = window.evaluate_js(
                        "(function(){var b=document.querySelector('.nav[data-s=\"privacy\"]');"
                        "if(!b||b.disabled)return 0; b.click();"
                        "return document.getElementById('privacy').classList.contains('active')?1:0;})()")
                    ins_nav = window.evaluate_js(
                        "(function(){var b=document.querySelector('.nav[data-s=\"insights\"]');"
                        "if(!b||b.disabled)return 0; b.click();"
                        "return document.getElementById('insights').classList.contains('active')?1:0;})()")
                    has_vocab = window.evaluate_js(
                        "document.getElementById('vocab-input') ? 1 : 0")
                    has_snip = window.evaluate_js(
                        "document.getElementById('snip-name') ? 1 : 0")
                    snip_nav = window.evaluate_js(
                        "(function(){var b=document.querySelector('.nav[data-s=\"snippets\"]');"
                        "if(!b||b.disabled)return 0; b.click();"
                        "return document.getElementById('snippets').classList.contains('active')?1:0;})()")
                    has_cleanup = window.evaluate_js(
                        "document.getElementById('t-cleanup') ? 1 : 0")
                    has_discourse = window.evaluate_js(
                        "document.getElementById('t-discourse') ? 1 : 0")
                    has_updates = window.evaluate_js(
                        "document.getElementById('b-check-updates') ? 1 : 0")
                    has_credits = window.evaluate_js(
                        "document.getElementById('a-credits') ? 1 : 0")
                    has_ms = window.evaluate_js(
                        "document.getElementById('ms-shelf') ? 1 : 0")
                    has_logo = window.evaluate_js(
                        "document.getElementById('a-logo') ? 1 : 0")
                    print(f"ROAR: settings probe navs={navs} version={ver} "
                          f"priv={has_priv} privnav={priv_nav} insnav={ins_nav} "
                          f"vocab={has_vocab} ovl={has_ovl} lang={has_lang} "
                          f"snip={has_snip} snipnav={snip_nav} "
                          f"cleanup={has_cleanup} discourse={has_discourse} "
                          f"updates={has_updates} credits={has_credits} "
                          f"ms={has_ms} logo={has_logo}", flush=True)
                finally:
                    window.destroy()
            threading.Thread(target=probe_and_close, daemon=True).start()

    window.events.loaded += on_loaded
    window.events.shown += on_shown
    webview.start()
    print("ROAR: settings closed", flush=True)
    return 0
