"""ROAR — local voice-to-text tray app. Entry point."""
import argparse
import ctypes
import os
import queue
import subprocess
import sys
import threading
import time

import keyboard
import pystray
from pystray import Menu, MenuItem as Item

import commands
import config as config_mod
import context
import editing
import gestures
import milestones
import history as history_mod
import injector
import paths
import recorder as recorder_mod
import status as status_mod
import tray_icons
from hotkeys import MODIFIER_ALIASES, parse_chord
from transcriber import Transcriber

__version__ = paths.APP_VERSION

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "Global\\ROARSingleton"

MODEL_CHOICES = ["auto", "tiny.en", "base.en", "small.en", "medium.en", "distil-large-v3"]


def acquire_single_instance():
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return None
    return handle


def record_history(hist, cfg, text, model=None, audio=None, duration_s=None):
    """Failure-isolated history write — never breaks dictation.
    Returns the new row id (or None) so scratch-that can roll it back."""
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


def send_backspaces(n):
    """Undo helper: one backspace per typed char (module-level, test-patchable)."""
    for _ in range(n):
        keyboard.send("backspace")


def diff_config(old: dict, new: dict):
    """Map a config-file change to the actions the running app must take.
    Instant keys (tones, thresholds, paste_fallback, replacements) are read
    at use time and need no action."""
    actions = []
    if (old["hotkey_ptt"] != new["hotkey_ptt"]
            or old["hotkey_toggle"] != new["hotkey_toggle"]):
        actions.append(("rehook", None))
    if (old["model"] != new["model"]
            or old["language"] != new["language"]):  # policy forks by language
        actions.append(("reload_model", new["model"]))
    if old["input_device"] != new["input_device"]:
        actions.append(("set_device", new["input_device"]))
    if (old["custom_vocabulary"] != new["custom_vocabulary"]
            or old["auto_vocabulary"] != new["auto_vocabulary"]):
        actions.append(("rebuild_hotwords", None))
    return actions


class ROARApp:
    IDLE, LOADING, RECORDING, TRANSCRIBING = "idle", "loading", "recording", "transcribing"

    def __init__(self, cfg, smoke=False):
        self.cfg = cfg
        self.smoke = smoke
        self.state = self.LOADING
        self.session_mode = None  # "ptt" | "toggle"
        self.pressed = set()
        # RLock: _start/_finish_recording call _set_state while holding it
        self.state_lock = threading.RLock()
        self.jobs = queue.Queue()
        self.last_transcript = ""
        self.ptt_chord = parse_chord(cfg["hotkey_ptt"])
        self.recorder = recorder_mod.Recorder(device=cfg["input_device"],
                                              on_level=self._on_level)
        self._session_gen = 0
        self.overlay = None
        self.history = history_mod.History()
        self._purge_ticks = 0
        self._dictation_count = 0
        self._inject_stack = editing.InjectionStack()
        self._detector = gestures.TapToggleDetector(
            double_tap_s=cfg.get("double_tap_ms", 400) / 1000)
        self._gesture_lock = threading.Lock()
        self._defer_timer = None
        self._target_hwnd = None  # window the current dictation is aimed at
        self.transcriber = Transcriber(model_name=cfg["model"], language=cfg["language"],
                                       models_dir=paths.models_dir(), log=self.log)
        self.model_ready = threading.Event()
        self._stop_watch = threading.Event()
        # serializes self.cfg mutation+save between menu handlers (tray
        # thread) and the config watcher (its own thread)
        self.cfg_lock = threading.RLock()
        self.icon = pystray.Icon("ROAR", tray_icons.make_icon(self.LOADING),
                                 "ROAR", menu=self._build_menu())
        self.worker = threading.Thread(target=self._worker, daemon=True)

    # -- logging / notifications ------------------------------------------
    def log(self, msg):
        print(f"ROAR: {msg}", flush=True)

    def notify(self, msg):
        self.log(msg)
        try:
            self.icon.notify(msg, "ROAR")
        except Exception:
            pass

    # -- state ------------------------------------------------------------
    def _set_state(self, state):
        with self.state_lock:
            self.state = state
        try:
            self.icon.icon = tray_icons.make_icon(state)
            self.icon.update_menu()
        except Exception:
            pass
        # Best-effort live status for the Home dashboard (separate process).
        # Operational only — no transcript. Never affects dictation.
        status_mod.write_status(state=state)

    # -- hotkeys ----------------------------------------------------------
    def _matches(self, key_name, chord_key):
        return key_name in MODIFIER_ALIASES.get(chord_key, {chord_key})

    def _chord_down(self):
        return all(any(self._matches(p, ck) for p in self.pressed) for ck in self.ptt_chord)

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

    def _gesture(self, kind):
        with self._gesture_lock:
            self._apply_gesture(self._detector.feed(kind, time.monotonic()))

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

    def _on_toggle(self):
        with self.state_lock:
            if self.state == self.RECORDING:
                if self.session_mode == "ptt":
                    self.session_mode = "toggle"  # upgrade held PTT into a toggle session
                    self.notify("Toggle dictation on — press the toggle hotkey to stop")
                else:
                    self._finish_recording()
            else:
                self._start_recording("toggle")

    def _register_hotkeys(self):
        keyboard.hook(self._on_key_event)
        toggle = self.cfg["hotkey_toggle"]
        try:
            keyboard.add_hotkey(toggle, self._on_toggle)
        except ValueError:
            keyboard.add_hotkey(toggle.replace("windows", "left windows"), self._on_toggle)
        self.log("hotkeys registered")

    # -- record / transcribe flow ------------------------------------------
    def _start_recording(self, mode):
        with self.state_lock:
            if self.state != self.IDLE:
                return
            self.session_mode = mode
            # the dictation targets the window focused when speech STARTS —
            # if focus moves before transcription lands, we refuse to type
            self._target_hwnd = self._foreground_hwnd()
            recorder_mod.play_tone("start", self.cfg["tones_enabled"])
            try:
                self.recorder.start()
            except Exception as e:
                recorder_mod.play_tone("error", self.cfg["tones_enabled"])
                self.notify("No microphone found — plug one in or pick a device "
                            f"in the tray menu ({e})")
                self.session_mode = None
                return
            self._set_state(self.RECORDING)
            if self.overlay is not None and self.cfg.get("overlay_enabled", True):
                self.overlay.show_recording()
                if self.cfg.get("streaming_preview", True):
                    self.jobs.put(("partial", self._session_gen))

    def _finish_recording(self):
        with self.state_lock:
            if self.state != self.RECORDING:
                return
            recorder_mod.play_tone("stop", self.cfg["tones_enabled"])
            audio = self.recorder.stop()
            self.session_mode = None
            self._session_gen += 1  # stale partials drain as no-ops
            if self.overlay is not None:
                self.overlay.show_transcribing()
            self._set_state(self.TRANSCRIBING)
            self.jobs.put(("transcribe", audio))

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

    # -- worker thread ------------------------------------------------------
    def _worker(self):
        try:
            self.transcriber.load()
            # Warm-up inference: the first CUDA call pays a one-time kernel
            # autotune cost (~13s measured). Pay it now, not on first dictation.
            import numpy as np
            self.transcriber.transcribe(np.zeros(8000, dtype=np.float32))
            self.log(f"model loaded: {self.transcriber.description()}")
            self._rebuild_hotwords()
        except Exception as e:
            self.notify(f"Model load failed: {e}. Check your internet connection "
                        "for the first-run download, then restart ROAR.")
        self.model_ready.set()
        self._set_state(self.IDLE)
        while True:
            job = self.jobs.get()
            if job is None:
                break
            kind, payload = job
            try:
                if kind == "reload":
                    self._set_state(self.LOADING)
                    self.transcriber.requested = payload  # "auto" re-runs the policy
                    self.transcriber.language = self.cfg["language"]
                    self.transcriber.load()
                    self.notify(f"Model ready: {self.transcriber.description()}")
                elif kind == "transcribe":
                    self._handle_transcription(payload)
                    if self.overlay is not None:
                        self.overlay.hide()
                elif kind == "partial":
                    self._handle_partial(payload)
            except Exception as e:
                recorder_mod.play_tone("error", self.cfg["tones_enabled"])
                self.notify(f"Transcription failed: {e}")
            if kind != "partial":  # partials must not reset RECORDING to IDLE
                self._set_state(self.IDLE)

    def _handle_transcription(self, audio):
        if not recorder_mod.passes_gate(audio, self.cfg["silence_rms_threshold"],
                                        self.cfg["min_duration_s"]):
            self.log("recording gated (silence/too short) — nothing injected")
            return
        raw = self.transcriber.transcribe(audio)
        if editing.is_scratch(raw):
            self._scratch()
            return
        prof = (context.profile_for(
                    self._foreground_exe(),
                    self._foreground_title(),
                    self.cfg.get("app_profiles"))
                if self.cfg.get("context_aware", True) else {})
        text = commands.process(
            raw, self.cfg["replacements"],
            self.cfg.get("snippets"),
            self.cfg.get("snippet_keyword", "snippet"),
            cleanup=prof.get("cleanup", self.cfg.get("cleanup_enabled", True)),
            discourse_fillers=prof.get(
                "discourse_fillers",
                self.cfg.get("remove_discourse_fillers", False)),
            capitalize=prof.get("capitalize", True),
            mode=self.cfg.get("format_mode", "clean"))
        if not text:
            self.log("empty transcript — nothing injected")
            return
        self.last_transcript = text
        hwnd = self._foreground_hwnd()
        target = getattr(self, "_target_hwnd", None)
        if target is not None and hwnd != target:
            # text landing in the wrong app is the one unforgivable failure —
            # refuse rather than type into whatever got focus meanwhile
            recorder_mod.play_tone("error", self.cfg["tones_enabled"])
            self.notify("Focus changed — ROAR did not type.")
            self.log("focus changed between recording and injection — skipped")
            return
        injector.inject_text(text, paste_fallback=self.cfg["paste_fallback"])
        self.log(f"injected {len(text)} chars")
        status_mod.write_status(last_injection_status="injected")
        rid = record_history(self.history, self.cfg, text,
                             model=self.transcriber.active_model, audio=audio,
                             duration_s=len(audio) / recorder_mod.SAMPLE_RATE)
        self._inject_stack.push(injector.prepare(text), hwnd, rid)
        self._check_milestones(text, rid)
        self._dictation_count += 1
        if self._dictation_count % 25 == 0:  # signature words drift slowly
            self._rebuild_hotwords()

    @staticmethod
    def _foreground_hwnd():
        return ctypes.windll.user32.GetForegroundWindow()

    @staticmethod
    def _foreground_exe():
        """Lowercased exe basename of the focused window, or '' on failure."""
        try:
            import os as _os
            import ctypes.wintypes as wintypes
            u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
            # explicit signatures: default ctypes int types truncate 64-bit
            # handles/pointers on Win64
            u32.GetForegroundWindow.restype = wintypes.HWND
            u32.GetWindowThreadProcessId.argtypes = [
                wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            k32.OpenProcess.restype = wintypes.HANDLE
            k32.OpenProcess.argtypes = [
                wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            k32.QueryFullProcessImageNameW.argtypes = [
                wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                ctypes.POINTER(wintypes.DWORD)]
            k32.CloseHandle.argtypes = [wintypes.HANDLE]
            hwnd = u32.GetForegroundWindow()
            pid = wintypes.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            h = k32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFO
            if not h:
                return ""
            try:
                buf = ctypes.create_unicode_buffer(260)
                size = wintypes.DWORD(260)
                k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
                return _os.path.basename(buf.value).lower()
            finally:
                k32.CloseHandle(h)
        except Exception:
            return ""

    @staticmethod
    def _foreground_title():
        """Window title of the focused window, or '' on failure."""
        try:
            import ctypes.wintypes as wintypes
            u32 = ctypes.windll.user32
            u32.GetForegroundWindow.restype = wintypes.HWND
            u32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            u32.GetWindowTextLengthW.restype = ctypes.c_int
            u32.GetWindowTextW.argtypes = [
                wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            u32.GetWindowTextW.restype = ctypes.c_int
            hwnd = u32.GetForegroundWindow()
            if not hwnd:
                return ""
            length = u32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return ""
            buf = ctypes.create_unicode_buffer(length + 1)
            u32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except Exception:
            return ""

    def _check_milestones(self, text, rid):
        """Persist + notify any word-count milestones this dictation crossed.
        Failure-isolated: milestones must never affect dictation."""
        if rid is None or not self.cfg.get("milestones_enabled", True):
            return
        try:
            new_total = self.history.total_words()
            old_total = new_total - len(text.split())
            earned = self.history.unlocks()  # already-unlocked, sticky
            for t in milestones.newly_crossed(old_total, new_total):
                if t in earned:
                    continue  # e.g. re-crossed after a history clear — never re-notify
                self.history.record_unlock(t, time.time())
                if self.cfg.get("milestone_notifications", True):
                    self.notify(f"Milestone unlocked: {milestones.name_for(t)}"
                                f" — {t:,} words")
        except Exception as e:
            self.log(f"milestone check failed: {e}")

    def _scratch(self):
        """Undo the last injection — only into the SAME window it went to."""
        entry = self._inject_stack.pop_if(self._foreground_hwnd())
        if entry is None:
            recorder_mod.play_tone("error", self.cfg["tones_enabled"])
            self.log("scratch refused — nothing typed here to undo")
            return
        n = editing.keystroke_len(entry.typed)
        send_backspaces(n)
        if entry.history_id is not None:
            try:
                self.history.delete(entry.history_id)
            except Exception:
                pass
        recorder_mod.play_tone("stop", self.cfg["tones_enabled"])
        self.log(f"scratched {n} chars")

    # -- tray menu -----------------------------------------------------------
    def _status_text(self):
        return f"{self.state.capitalize()} — {self.transcriber.description()}"

    def _build_menu(self):
        def model_item(name):
            return Item(name, lambda: self._set_model(name),
                        checked=lambda item, n=name: self.cfg["model"] == n, radio=True)

        def device_items():
            def make_action(i):
                return lambda: self._set_device(i)

            def make_checked(i):
                return lambda item: self.cfg["input_device"] == i

            for idx, dev_name in recorder_mod.list_input_devices():
                yield Item(dev_name, make_action(idx), checked=make_checked(idx),
                           radio=True)

        return Menu(
            Item(lambda item: self._status_text(), None, enabled=False),
            Item("Copy last transcript", self._copy_last),
            Item("Model", Menu(*[model_item(m) for m in MODEL_CHOICES])),
            Item("Input device", Menu(device_items)),
            Item("Fallback paste mode", self._toggle_paste,
                 checked=lambda item: self.cfg["paste_fallback"]),
            Item("Settings…", self._open_settings),
            Item("Open config", self._open_config),
            Menu.SEPARATOR,
            Item("Quit", self._quit),
        )

    def _open_settings(self):
        if paths.is_frozen():
            subprocess.Popen([sys.executable, "--settings"])
        else:
            app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "app.py")
            subprocess.Popen([sys.executable, app_path, "--settings"])

    def _copy_last(self):
        import pyperclip
        if self.last_transcript:
            pyperclip.copy(self.last_transcript)
            self.notify("Last transcript copied to clipboard")
        else:
            self.notify("No transcript yet — hold the hotkey and speak first")

    def _set_model(self, name):
        with self.cfg_lock:
            self.cfg["model"] = name
            config_mod.save(self.cfg)
        self.jobs.put(("reload", name))

    def _set_device(self, idx):
        with self.cfg_lock:
            self.cfg["input_device"] = idx
            self.recorder.device = idx
            config_mod.save(self.cfg)

    def _toggle_paste(self):
        with self.cfg_lock:
            self.cfg["paste_fallback"] = not self.cfg["paste_fallback"]
            config_mod.save(self.cfg)

    def _open_config(self):
        subprocess.Popen(["notepad.exe", config_mod.PATH])

    def _rebuild_hotwords(self):
        """Merge custom + auto signature words into the transcriber. Never
        raises; on failure the previous hotwords stay in effect."""
        import vocabulary
        try:
            signature = []
            if (self.cfg.get("auto_vocabulary", True)
                    and self.cfg.get("history_enabled", True)):
                from insights import compute_insights
                signature = compute_insights(
                    self.history.list(limit=5000))["signature_words"]
            self.transcriber.hotwords = vocabulary.merge_hotwords(
                self.cfg.get("custom_vocabulary", []), signature)
        except Exception as e:
            self.log(f"hotwords rebuild failed: {e}")

    def _watch_config(self):
        """Hot-apply external edits to config.json (settings process or hand
        edits). Compares file CONTENT, not mtime — this filesystem's mtime
        granularity (~10ms) can swallow back-to-back writes. cfg_lock
        serializes against menu handlers, whose own writes diff to no-ops."""
        import hashlib
        last = None
        while not self._stop_watch.is_set():
            try:
                with open(config_mod.PATH, "rb") as f:
                    digest = hashlib.sha1(f.read()).hexdigest()
                if last is None:
                    last = digest
                elif digest != last:
                    last = digest
                    with self.cfg_lock:
                        new_cfg = config_mod.load()
                        actions = diff_config(self.cfg, new_cfg)
                        self.cfg.update(new_cfg)
                        # keep the tap window live without a full rehook
                        self._detector.double_tap_s = (
                            self.cfg.get("double_tap_ms", 400) / 1000)
                    for action, arg in actions:
                        if action == "rehook":
                            keyboard.unhook_all()
                            self.pressed.clear()
                            self.ptt_chord = parse_chord(self.cfg["hotkey_ptt"])
                            self._register_hotkeys()
                            self.notify("Hotkeys updated")
                        elif action == "reload_model":
                            self.jobs.put(("reload", arg))
                        elif action == "set_device":
                            self.recorder.device = arg
                        elif action == "rebuild_hotwords":
                            self._rebuild_hotwords()
            except OSError:
                pass  # config briefly missing/locked — retry next tick
            self._purge_ticks += 1
            if self._purge_ticks == 1 or self._purge_ticks % 1800 == 0:  # first + ~hourly
                try:
                    self.history.purge_expired(self.cfg.get("audio_retention_days", 0))
                except Exception as e:
                    self.log(f"purge failed: {e}")
            self._stop_watch.wait(2.0)

    # -- lifecycle -------------------------------------------------------------
    def _quit(self):
        self._stop_watch.set()
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        if self.overlay is not None:
            self.overlay.stop()
        self.jobs.put(None)
        self.worker.join(timeout=5)
        try:
            self.history.close()
        except Exception:
            pass
        self.icon.stop()

    def _on_tray_ready(self, icon):
        icon.visible = True
        self.log("tray ready")
        if self.smoke:
            def stop_after_load():
                self.model_ready.wait(timeout=240)
                self._quit()
            threading.Thread(target=stop_after_load, daemon=True).start()

    def run(self):
        # Seed the Home-dashboard status file for this run (session start).
        status_mod.write_status(state=self.state, session_started_at=time.time(),
                                session_word_count=0)
        import overlay as overlay_mod
        self.overlay = overlay_mod.Overlay()
        self.overlay.start()
        self.worker.start()
        self._register_hotkeys()
        threading.Thread(target=self._watch_config, daemon=True).start()
        self.icon.run(setup=self._on_tray_ready)
        self.log("clean exit")


def main():
    parser = argparse.ArgumentParser(description="ROAR — local voice-to-text")
    parser.add_argument("--smoke", action="store_true",
                        help="start, load model, then exit (self-test)")
    parser.add_argument("--settings", action="store_true",
                        help="open the settings window instead of the tray app")
    args = parser.parse_args()

    # Migration MUST precede redirect_output_when_frozen: opening the log
    # file creates %LOCALAPPDATA%\ROAR, which would make migration see
    # "both dirs exist" and refuse to move the legacy data. Migrate first
    # (silently — windowed exes have no stdout yet), then log what moved.
    migration_lines = paths.migrate_legacy_data()
    paths.redirect_output_when_frozen()
    for line in migration_lines:
        print(f"ROAR: {line}", flush=True)

    if args.settings:
        import settings_ui
        sys.exit(settings_ui.run_settings(smoke=args.smoke))

    mutex = acquire_single_instance()
    if mutex is None:
        print("ROAR: already running — exiting", flush=True)
        sys.exit(1)

    if not paths.is_frozen():
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Self-heal a stale autostart entry (e.g. MSI reinstalled to a new path,
    # or the old entry survived an uninstall — WiX can't remove single
    # per-user Run values). If autostart is on, point it at THIS binary.
    try:
        import autostart
        current = autostart.get(paths.APP_NAME)
        desired = autostart.default_command()
        if current is not None and current != desired:
            autostart.set_enabled(paths.APP_NAME, desired, True)
    except OSError:
        pass

    cfg = config_mod.load()
    if args.smoke:  # deterministic, small, CPU-only for the self-test
        cfg["model"] = "small.en"
    app = ROARApp(cfg, smoke=args.smoke)
    if args.smoke:
        app.transcriber.force_device = "cpu"
    app.run()
    # Native thread pools (ctranslate2 / onnxruntime / PortAudio) intermittently
    # crash with an access violation while the interpreter finalizes (observed
    # 0xC000041D in ~1/3 of runs, native thread, no Python frame). Everything
    # we own is already closed and flushed by _quit — exit without running
    # interpreter finalization at all.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
