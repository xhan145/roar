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
import context
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
                "context_aware", "appearance", "format_mode",
                "acceleration_mode", "performance_preset", "compute_type",
                "backend"}
_TTS_SETTINGS = {
    "tts_enabled", "tts_voice", "tts_language", "tts_speed", "tts_volume",
    "tts_output_device", "tts_readback_mode", "tts_spoken_status_enabled",
    "tts_stop_when_dictation_starts", "tts_clipboard_fallback_enabled",
    "tts_preload_model", "tts_unload_after_idle_minutes",
}
_TTS_HOTKEYS = (
    "tts_hotkey_read_selected", "tts_hotkey_read_clipboard",
    "tts_hotkey_pause_resume", "tts_hotkey_stop", "tts_hotkey_repeat",
)
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


def _license_edition():
    """Display label for the current edition. Licensing is NOT enforced — the
    edition is shown, never used to gate a feature (see docs/LICENSING.md)."""
    import license as license_mod
    return license_mod.get_current_edition().title()


def _epoch(ts):
    """Best-effort convert a history ts_utc (epoch number or ISO string) to
    epoch seconds; None if unparseable."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(ts)).timestamp()
    except Exception:
        return None


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
        cfg = config_mod.load(self.config_path)
        return {
            "config": cfg,
            "autostart": autostart.get(APP_NAME) is not None,
            "devices": recorder_mod.list_input_devices(),
            "models": MODEL_CHOICES,
            "version": paths.APP_VERSION,
            "config_path": self.config_path,
            "log_path": paths.log_path(),
            "tts_enabled": cfg.get("tts_enabled", False),
            "tts_engine": cfg.get("tts_engine", "kokoro"),
            "tts_voice": cfg.get("tts_voice", "af_heart"),
            "tts_language": cfg.get("tts_language", "en-us"),
            "tts_output_device": cfg.get("tts_output_device", "default"),
            "tts_readback_mode": cfg.get("tts_readback_mode", "off"),
            "tts_stop_when_dictation_starts": cfg.get(
                "tts_stop_when_dictation_starts", True),
            "tts_preload_model": cfg.get("tts_preload_model", False),
            "tts_unload_after_idle_minutes": cfg.get(
                "tts_unload_after_idle_minutes", 10),
            "languages": _language_options(),
            "logo_path": paths.resource_path("assets/roar-logo-purple-256.png"),
            "edition": _license_edition(),
            "tts": self.tts_state(cfg),
        }

    def tts_state(self, cfg=None):
        """Read-only operational state; never imports Kokoro/PyTorch."""
        import status as status_mod
        import time as _time
        from tts import model_manager
        from tts.playback import list_output_devices
        from tts.voices import catalog
        cfg = cfg or config_mod.load(self.config_path)
        pack_dir = model_manager.configured_pack_dir(cfg)
        pack = model_manager.inspect_pack(pack_dir, verify_hashes=True)
        st = status_mod.read_status()
        live = bool(st.get("updated_at")
                    and _time.time() - st["updated_at"] < 15)
        return {
            "pack": {key: value for key, value in pack.items()
                     if key != "path"},
            "voices": catalog(pack_dir),
            "output_devices": list_output_devices(),
            "state": (st.get("tts_state") if live else None) or (
                "unloaded" if pack["valid"] else "unavailable"),
            "error_category": st.get("tts_error_category", ""),
            "engine_version": st.get("tts_engine_version", ""),
            "model_version": st.get(
                "tts_model_version", pack.get("model_version")),
        }

    def tts_apply(self, changes):
        if not isinstance(changes, dict) or not changes:
            return {"error": "No Read Aloud settings were provided."}
        if any(key not in _TTS_SETTINGS for key in changes):
            return {"error": "A Read Aloud setting is not supported."}
        with self._cfg_lock:
            cfg = config_mod.load(self.config_path)
            candidate = dict(cfg)
            candidate.update(changes)
            if candidate.get("tts_language") != "en-us":
                return {"error": "The verified voice pack currently supports American English."}
            from tts.voices import VOICES
            if candidate.get("tts_voice") not in {v.voice_id for v in VOICES}:
                return {"error": "Unknown local voice."}
            try:
                speed = float(candidate.get("tts_speed"))
                volume = float(candidate.get("tts_volume"))
                idle = int(candidate.get("tts_unload_after_idle_minutes"))
            except (TypeError, ValueError):
                return {"error": "Speed, volume, and idle timeout must be numbers."}
            if not 0.6 <= speed <= 1.6:
                return {"error": "Speech speed must be between 0.6 and 1.6."}
            if not 0.0 <= volume <= 1.0:
                return {"error": "Volume must be between 0 and 1."}
            if not 0 <= idle <= 1440:
                return {"error": "Idle timeout must be between 0 and 1440 minutes."}
            if candidate.get("tts_readback_mode") not in (
                    "off", "before", "after", "on_command"):
                return {"error": "Unknown dictation read-back mode."}
            from tts.playback import list_output_devices
            valid_devices = {str(item[0]) for item in list_output_devices()}
            if str(candidate.get("tts_output_device")) not in valid_devices:
                return {"error": "The selected output device is unavailable."}
            for key in (
                    "tts_enabled", "tts_spoken_status_enabled",
                    "tts_stop_when_dictation_starts",
                    "tts_clipboard_fallback_enabled", "tts_preload_model"):
                if key in candidate:
                    candidate[key] = bool(candidate[key])
            candidate["tts_speed"] = speed
            candidate["tts_volume"] = volume
            candidate["tts_unload_after_idle_minutes"] = idle
            self._write(**{key: candidate[key] for key in changes})
        return {"ok": True}

    def tts_apply_hotkeys(self, values):
        if not isinstance(values, dict):
            return {"error": "Hotkey values are invalid."}
        cfg = config_mod.load(self.config_path)
        normalized = {}
        occupied = {
            normalize_combo(parse_chord(cfg.get("hotkey_ptt", ""))):
                "Push-to-talk",
            normalize_combo(parse_chord(cfg.get("hotkey_toggle", ""))):
                "Toggle dictation",
        }
        occupied.pop("", None)
        for key in _TTS_HOTKEYS:
            value = str(values.get(key, "") or "").strip().lower()
            if value:
                parts = parse_chord(value)
                if not 1 <= len(parts) <= 4:
                    return {"error": "Each Read Aloud hotkey must contain 1 to 4 keys."}
                value = normalize_combo(parts)
                if value in occupied:
                    return {"error": f"{value} conflicts with {occupied[value]}."}
                occupied[value] = key
            normalized[key] = value
        self._write(**normalized)
        return {"ok": True}

    def tts_command(self, command, text=None, voice=None, speed=None):
        from tts.ipc import send
        payload = {"command": command}
        if command in ("speak", "preview"):
            payload.update(text=text, voice=voice, speed=speed)
        return send(payload)

    def tts_import_pack(self):
        import webview
        from tts import model_manager
        if _WINDOW is None:
            return {"error": "No Settings window is available."}
        selected = _WINDOW.create_file_dialog(webview.FOLDER_DIALOG)
        if not selected:
            return {"cancelled": True}
        source = selected if isinstance(selected, str) else selected[0]
        try:
            # Release worker file handles before atomic replacement.
            self.tts_command("unload")
            result = model_manager.install_pack(source)
            self._write(tts_model_path=None)
            result.pop("path", None)
            return {"ok": True, "pack": result}
        except Exception as exc:
            return {"error": f"Voice pack was not installed: {exc}"}

    def tts_remove_pack(self):
        from tts import model_manager
        try:
            self.tts_command("unload")
            removed = model_manager.remove_pack()
            self._write(tts_model_path=None, tts_enabled=False)
            return {"ok": True, "removed": removed}
        except Exception as exc:
            return {"error": f"Voice pack could not be removed: {exc}"}

    def get_home_state(self):
        """Safe composite of real local state for the Home dashboard. Every
        field is individually guarded; missing/corrupt sources degrade to safe
        defaults. Never raises. Never exposes transcript beyond the History
        preview, clipboard, audio paths, window titles, or secrets."""
        import time as _time
        import status as status_mod
        NA = "Not available"
        out = {
            "app_version": paths.APP_VERSION, "is_running": False,
            "dictation_state": "idle", "active_profile": NA,
            "active_profile_description": "", "current_model": NA,
            "current_device": NA, "injection_method": NA,
            "paste_fallback_enabled": False, "autostart_enabled": False,
            "session_duration_seconds": 0, "session_word_count": 0,
            "last_latency_seconds": None, "last_transcription_preview": "",
            "last_transcription_word_count": 0, "last_transcription_timestamp": None,
            "last_injection_status": NA, "hotkeys": {},
            "diagnostics_safe_summary": {}, "words_today": 0,
            "words_this_week": 0, "milestone": {}, "controls_enabled": False,
        }
        try:
            cfg = config_mod.load(self.config_path)
        except Exception:
            cfg = {}
        try:
            out["controls_enabled"] = bool(cfg.get("dashboard_controls", False))
        except Exception:
            pass
        try:
            out["current_model"] = cfg.get("model") or NA
        except Exception:
            pass
        try:
            pf = bool(cfg.get("paste_fallback", False))
            out["paste_fallback_enabled"] = pf
            out["injection_method"] = "Clipboard paste" if pf else "Direct (SendInput)"
        except Exception:
            pass
        try:
            out["autostart_enabled"] = autostart.get(APP_NAME) is not None
        except Exception:
            pass
        try:
            out["hotkeys"] = {"push_to_talk": cfg.get("hotkey_ptt"),
                              "toggle": cfg.get("hotkey_toggle")}
        except Exception:
            pass
        # Active-profile POLICY (the live foreground profile is resolved in the
        # tray; here we report the configured policy — never a window title).
        try:
            if cfg.get("context_aware", True):
                out["active_profile"] = "Auto (context-aware)"
                out["active_profile_description"] = (
                    "Adapts per app: verbatim in code editors, casual in chat, "
                    "formal in docs.")
            else:
                out["active_profile"] = str(cfg.get("format_mode", "clean")).capitalize()
                out["active_profile_description"] = "Same formatting in every app."
        except Exception:
            pass
        # Live status file (tray -> here). Compute device comes from here too —
        # the settings process must NOT import the ML/CUDA stack to probe it.
        started = 0
        try:
            st = status_mod.read_status()
            if st:
                out["dictation_state"] = st.get("state", "idle")
                if st.get("device"):
                    out["current_device"] = st["device"]
                if st.get("last_injection_status"):
                    out["last_injection_status"] = st["last_injection_status"]
                started = st.get("session_started_at") or 0
                if started:
                    out["session_duration_seconds"] = max(0, int(_time.time() - started))
                upd = st.get("updated_at")
                out["is_running"] = bool(upd and (_time.time() - upd) < 15)
        except Exception:
            pass
        # History-derived: last transcription + word tallies.
        try:
            rows = self._history.list(limit=5000)
        except Exception:
            rows = []
        try:
            if rows:
                r0 = rows[0]
                prev = (r0.get("text") or "")[:160]
                out["last_transcription_preview"] = prev
                out["last_transcription_word_count"] = r0.get("word_count") or len(prev.split())
                out["last_transcription_timestamp"] = r0.get("ts_utc")
                if out["last_injection_status"] == NA:
                    out["last_injection_status"] = "Injected"
                if r0.get("duration_s") is not None:
                    out["last_latency_seconds"] = round(float(r0["duration_s"]), 2)
        except Exception:
            pass
        try:
            now = _time.time()
            start_today = now - (now % 86400)
            start_week = now - 7 * 86400
            wt = ww = ws = 0
            for r in rows:
                ts = _epoch(r.get("ts_utc"))
                if ts is None:
                    continue
                wc = r.get("word_count") or 0
                if ts >= start_today:
                    wt += wc
                if ts >= start_week:
                    ww += wc
                if started and ts >= started:
                    ws += wc
            out["words_today"], out["words_this_week"] = wt, ww
            out["session_word_count"] = ws
        except Exception:
            pass
        try:
            import milestones
            out["milestone"] = milestones.progress(
                self._history.total_words(), self._history.unlocks())
        except Exception:
            pass
        try:
            import diagnostics
            out["diagnostics_safe_summary"] = diagnostics.collect({
                "version": paths.APP_VERSION, "model": cfg.get("model"),
                "language": cfg.get("language"),
                "history_enabled": cfg.get("history_enabled"),
            })
        except Exception:
            pass
        return out

    def send_command(self, cmd):
        """Home-dashboard remote control (Start/Stop, Scratch that). No-op
        unless the `dashboard_controls` flag is on. Only fixed command names
        cross to the tray — never user data."""
        try:
            cfg = config_mod.load(self.config_path)
            if not cfg.get("dashboard_controls", False):
                return {"ok": False, "reason": "disabled"}
            import ipc_commands
            return {"ok": bool(ipc_commands.send_command(cmd))}
        except Exception:
            return {"ok": False}

    def license_info(self):
        """License status for display + activation. Reads ONLY the license file
        (via license_service) — never transcript/audio/history/clipboard, never
        the network. Nothing here blocks a feature; gates live at the feature's
        own entry point."""
        import license_service
        import commercial_config as cc
        import upgrade_prompts
        s = license_service.get_status()
        return {
            "edition": s["edition"].title(),
            "edition_id": s["edition"],
            "valid": s["valid"],
            "status": "Activated locally" if s["valid"] else "Not activated",
            "reason": s["reason"],
            "message": s["message"],
            "detail": s["detail"],
            "license_id": s["license_id"],          # already redacted
            "customer_name": s["customer_name"],
            "valid_for_major": s["valid_for_major"],
            "validation": "Local/offline",
            "prices": {"pro": cc.PRO_PRICE_USD,
                       "developer": cc.DEVELOPER_PRICE_USD,
                       "supporter": cc.SUPPORTER_PRICE_USD},
            "purchase_urls": {"pro": cc.PURCHASE_URL_PRO,
                              "developer": cc.PURCHASE_URL_DEVELOPER,
                              "supporter": cc.PURCHASE_URL_SUPPORTER},
            "upgrades": upgrade_prompts.all_copy(),
        }

    def feature_access(self):
        """Which gated features this install may use, plus the upgrade copy for
        the ones it may not. The UI uses this to EXPLAIN a locked control rather
        than silently disabling it — and never to enforce: the real gates live at
        each feature's backend entry point."""
        import access
        import upgrade_prompts
        import entitlements
        out = {"edition": access.edition(), "features": {}}
        for feature in sorted(entitlements.KNOWN_FEATURES - entitlements.ALWAYS_FREE):
            allowed = access.can(feature)
            entry = {"allowed": allowed}
            if not allowed:
                entry["upgrade"] = upgrade_prompts.prompt_for(feature)
            out["features"][feature] = entry
        return out

    def license_import(self, source):
        """Install a pasted license. Oversized input is rejected before parsing;
        validation happens BEFORE anything is written, so a bad paste can never
        disturb an existing valid license."""
        import license_service
        if not isinstance(source, str):
            return {"ok": False, "message": license_service.reason_copy("malformed")}
        if len(source) > license_service.MAX_IMPORT_BYTES:
            return {"ok": False, "message": license_service.reason_copy("too_large")}
        r = license_service.import_license(source)
        return {"ok": r["ok"], "message": r["message"],
                "edition": r["edition"].title()}

    def license_import_file(self):
        """Pick a license file and install it. Same validate-before-write rules."""
        import webview
        import license_service
        if _WINDOW is None:
            return {"error": "no window"}
        path = _WINDOW.create_file_dialog(webview.OPEN_DIALOG)
        if not path:
            return {"cancelled": True}
        path = path if isinstance(path, str) else path[0]
        r = license_service.import_license(path)
        return {"ok": r["ok"], "message": r["message"],
                "edition": r["edition"].title()}

    def license_remove(self):
        """Return to Core. Deletes ONLY the license file — never history, audio,
        snippets, vocabulary, or settings."""
        import license_service
        r = license_service.remove_license()
        return {"ok": r["ok"], "message": r["message"],
                "edition": r["edition"].title()}

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
        if key == "appearance":
            if value not in ("dark", "light", "system"):
                return {"error": "appearance must be dark, light, or system"}
        if key == "format_mode":
            if value not in ("raw", "clean", "code"):
                return {"error": "format mode must be raw, clean, or code"}
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

    # -- app profiles -------------------------------------------------------
    def app_profiles_get(self):
        cfg = config_mod.load(self.config_path)
        return {"profiles": list(context.PROFILE_NAMES),
                "map": cfg.get("app_profiles", {})}

    def app_profile_set(self, app, profile):
        app = str(app or "").strip().lower()
        profile = str(profile or "").strip().lower()
        if not app:
            return {"error": "app is required"}
        if profile not in context.PROFILE_NAMES:
            return {"error": f"unknown profile {profile}"}
        with self._cfg_lock:
            cfg = config_mod.load(self.config_path)
            app_profiles = dict(cfg.get("app_profiles", {}))
            app_profiles[app] = profile
            self._write(app_profiles=app_profiles)
        return {"ok": True}

    def app_profile_clear(self, app):
        target = str(app or "").strip().lower()
        with self._cfg_lock:
            cfg = config_mod.load(self.config_path)
            app_profiles = {k: v for k, v in cfg.get("app_profiles", {}).items()
                            if str(k).lower() != target}
            self._write(app_profiles=app_profiles)
        return {"ok": True}

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
        added = renamed = clipboard_count = 0
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
                    if "{clipboard}" in text:
                        clipboard_count += 1
            self._write(snippets=sn)
        return {"ok": True, "added": added, "renamed": renamed,
                "clipboard_count": clipboard_count}

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

    def reset_milestones(self):
        return {"ok": True, "removed": self._history.reset_milestones()}

    def clear_log(self):
        try:
            open(paths.log_path(), "w", encoding="utf-8").close()
            return {"ok": True}
        except OSError as e:
            return {"error": f"couldn't clear the log: {e}"}

    # -- diagnostics / safe mode -------------------------------------------
    def diagnostics_get(self):
        import diagnostics
        cfg = config_mod.load(self.config_path)
        import license as license_mod
        info = {
            "version": paths.APP_VERSION,
            "edition": license_mod.CORE,
            "model": cfg.get("model"),
            "language": cfg.get("language"),
            "context_aware": cfg.get("context_aware"),
            "appearance": cfg.get("appearance", "dark"),
            "overlay_enabled": cfg.get("overlay_enabled"),
            "streaming_preview": cfg.get("streaming_preview"),
            "paste_fallback": cfg.get("paste_fallback"),
            "cleanup_enabled": cfg.get("cleanup_enabled"),
            "history_enabled": cfg.get("history_enabled"),
            "audio_retention_days": cfg.get("audio_retention_days"),
            "milestones_enabled": cfg.get("milestones_enabled"),
            "double_tap_ms": cfg.get("double_tap_ms"),
            "format_mode": cfg.get("format_mode", "clean"),
            "history_count": self._history.stats()["count"],
            "config_path": self.config_path,
            "log_path": paths.log_path(),
        }
        # Acceleration facts: config for what's REQUESTED, status.json (written by
        # the tray) for what's ACTUALLY running. Read-only — the settings process
        # never imports the ML/CUDA stack.
        try:
            import status as status_mod
            st = status_mod.read_status()
        except Exception:
            st = {}
        info["acceleration_mode"] = cfg.get("acceleration_mode", "auto")
        info["performance_preset"] = cfg.get("performance_preset", "balanced")
        info["backend"] = st.get("backend")
        info["device"] = st.get("device")            # GPU/CPU label from the engine
        info["compute_type"] = st.get("compute_type") or cfg.get("compute_type", "auto")
        info["cpu_threads"] = st.get("cpu_threads")
        info["last_transcription_duration_ms"] = st.get("last_transcription_duration_ms")
        info["fallback_reason"] = st.get("fallback_reason")
        for key in (
                "tts_state", "tts_engine_version", "tts_model_status",
                "tts_model_version", "tts_device", "tts_sample_rate",
                "tts_error_category", "tts_last_elapsed_ms",
                "tts_last_audio_duration_ms", "tts_last_first_audio_ms",
                "tts_last_real_time_factor"):
            info[key] = st.get(key)
        return {"report": diagnostics.format_report(info)}

    def safe_mode(self):
        """Conservative settings for troubleshooting. Reversible: returns the
        previous values so the UI can tell the user exactly what changed."""
        with self._cfg_lock:
            cfg = config_mod.load(self.config_path)
            before = {k: cfg.get(k) for k in
                      ("overlay_enabled", "streaming_preview", "paste_fallback")}
            self._write(overlay_enabled=False, streaming_preview=False,
                        paste_fallback=True)
        return {"ok": True, "previous": before}

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
                    # Home is the default view and must be reachable/active.
                    home_nav = window.evaluate_js(
                        "(function(){var b=document.querySelector('.nav[data-s=\"home\"]');"
                        "if(!b||b.disabled)return 0; b.click();"
                        "return document.getElementById('home').classList.contains('active')?1:0;})()")
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
                    # Privacy now lives under the Settings overview (still fully
                    # reachable, never gated) — reach it via Settings.
                    priv_nav = window.evaluate_js(
                        "(function(){var s=document.querySelector('.nav[data-s=\"settings\"]');"
                        "if(!s)return 0; s.click();"
                        "var b=document.querySelector('#settings [data-section=\"privacy\"]');"
                        "if(!b)return 0; b.click();"
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
                        "(function(){var s=document.querySelector('.nav[data-s=\"settings\"]');"
                        "if(!s)return 0; s.click();"
                        "var b=document.querySelector('#settings [data-section=\"snippets\"]');"
                        "if(!b)return 0; b.click();"
                        "return document.getElementById('snippets').classList.contains('active')?1:0;})()")
                    prof_nav = window.evaluate_js(
                        "(function(){var b=document.querySelector('.nav[data-s=\"profiles\"]');"
                        "if(!b||b.disabled)return 0; b.click();"
                        "return document.getElementById('profiles').classList.contains('active')?1:0;})()")
                    dict_nav = window.evaluate_js(
                        "(function(){var b=document.querySelector('.nav[data-s=\"dictionary\"]');"
                        "if(!b||b.disabled)return 0; b.click();"
                        "return document.getElementById('dictionary').classList.contains('active')?1:0;})()")
                    set_nav = window.evaluate_js(
                        "(function(){var b=document.querySelector('.nav[data-s=\"settings\"]');"
                        "if(!b||b.disabled)return 0; b.click();"
                        "return document.getElementById('settings').classList.contains('active')?1:0;})()")
                    has_cleanup = window.evaluate_js(
                        "document.getElementById('t-cleanup') ? 1 : 0")
                    has_discourse = window.evaluate_js(
                        "document.getElementById('t-discourse') ? 1 : 0")
                    has_profiles = window.evaluate_js(
                        "document.getElementById('app-profile-list') ? 1 : 0")
                    has_updates = window.evaluate_js(
                        "document.getElementById('b-check-updates') ? 1 : 0")
                    has_credits = window.evaluate_js(
                        "document.getElementById('a-credits') ? 1 : 0")
                    has_ms = window.evaluate_js(
                        "document.getElementById('ms-shelf') ? 1 : 0")
                    has_logo = window.evaluate_js(
                        "document.getElementById('a-logo') ? 1 : 0")
                    has_diag = window.evaluate_js(
                        "document.getElementById('b-diag-copy') ? 1 : 0")
                    tts_nav = window.evaluate_js(
                        "(function(){var b=document.querySelector('.nav[data-s=\"readaloud\"]');"
                        "if(!b||b.disabled)return 0; b.click();"
                        "return document.getElementById('readaloud').classList.contains('active')?1:0;})()")
                    has_tts_status = window.evaluate_js(
                        "document.getElementById('tts-status') ? 1 : 0")
                    has_tts_stop = window.evaluate_js(
                        "document.getElementById('tts-stop-all') ? 1 : 0")
                    has_fmt = window.evaluate_js(
                        "document.getElementById('s-format') ? 1 : 0")
                    has_accel = window.evaluate_js(
                        "(document.getElementById('s-preset') && "
                        "document.getElementById('s-accel') && "
                        "document.getElementById('s-compute')) ? 1 : 0")
                    theme_ok = window.evaluate_js(
                        "(function(){"
                        "applyAppearance('light');"
                        "var lt = getComputedStyle(document.body).color;"
                        "applyAppearance('dark');"
                        "var dk = getComputedStyle(document.body).color;"
                        "return (lt === 'rgb(29, 26, 43)' && dk === 'rgb(237, 237, 239)') ? 1 : 0;})()")
                    print(f"ROAR: settings probe navs={navs} home={home_nav} version={ver} "
                          f"prof={prof_nav} dict={dict_nav} setnav={set_nav} "
                          f"priv={has_priv} privnav={priv_nav} insnav={ins_nav} "
                          f"vocab={has_vocab} ovl={has_ovl} lang={has_lang} "
                          f"snip={has_snip} snipnav={snip_nav} "
                          f"cleanup={has_cleanup} discourse={has_discourse} "
                          f"profiles={has_profiles} "
                          f"updates={has_updates} credits={has_credits} "
                          f"ms={has_ms} logo={has_logo} diag={has_diag} "
                          f"ttsnav={tts_nav} ttsstatus={has_tts_status} "
                          f"ttsstop={has_tts_stop} "
                          f"fmt={has_fmt} accel={has_accel} themeok={theme_ok}",
                          flush=True)
                finally:
                    window.destroy()
            threading.Thread(target=probe_and_close, daemon=True).start()

    window.events.loaded += on_loaded
    window.events.shown += on_shown
    webview.start()
    print("ROAR: settings closed", flush=True)
    return 0
