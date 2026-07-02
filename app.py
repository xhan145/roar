"""FlowLocal — local voice-to-text tray app. Entry point."""
import argparse
import ctypes
import os
import queue
import subprocess
import sys
import threading

import keyboard
import pystray
from pystray import Menu, MenuItem as Item

import commands
import config as config_mod
import injector
import recorder as recorder_mod
import tray_icons
from transcriber import Transcriber

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "Global\\FlowLocalSingleton"

MODIFIER_ALIASES = {
    "ctrl": {"ctrl", "left ctrl", "right ctrl"},
    "windows": {"windows", "left windows", "right windows"},
    "alt": {"alt", "left alt", "right alt", "alt gr"},
    "shift": {"shift", "left shift", "right shift"},
}

MODEL_CHOICES = ["auto", "tiny.en", "base.en", "small.en", "medium.en", "distil-large-v3"]


def acquire_single_instance():
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return None
    return handle


def parse_chord(hotkey: str):
    return [k.strip().lower() for k in hotkey.split("+") if k.strip()]


class FlowLocalApp:
    IDLE, LOADING, RECORDING, TRANSCRIBING = "idle", "loading", "recording", "transcribing"

    def __init__(self, cfg, smoke=False):
        self.cfg = cfg
        self.smoke = smoke
        self.state = self.LOADING
        self.session_mode = None  # "ptt" | "toggle"
        self.pressed = set()
        self.state_lock = threading.Lock()
        self.jobs = queue.Queue()
        self.last_transcript = ""
        self.ptt_chord = parse_chord(cfg["hotkey_ptt"])
        self.recorder = recorder_mod.Recorder(device=cfg["input_device"])
        self.transcriber = Transcriber(model_name=cfg["model"], language=cfg["language"],
                                       log=self.log)
        self.model_ready = threading.Event()
        self.icon = pystray.Icon("FlowLocal", tray_icons.make_icon(self.LOADING),
                                 "FlowLocal", menu=self._build_menu())
        self.worker = threading.Thread(target=self._worker, daemon=True)

    # -- logging / notifications ------------------------------------------
    def log(self, msg):
        print(f"FlowLocal: {msg}", flush=True)

    def notify(self, msg):
        self.log(msg)
        try:
            self.icon.notify(msg, "FlowLocal")
        except Exception:
            pass

    # -- state ------------------------------------------------------------
    def _set_state(self, state):
        self.state = state
        try:
            self.icon.icon = tray_icons.make_icon(state)
            self.icon.update_menu()
        except Exception:
            pass

    # -- hotkeys ----------------------------------------------------------
    def _matches(self, key_name, chord_key):
        return key_name in MODIFIER_ALIASES.get(chord_key, {chord_key})

    def _chord_down(self):
        return all(any(self._matches(p, ck) for p in self.pressed) for ck in self.ptt_chord)

    def _on_key_event(self, event):
        name = (event.name or "").lower()
        if event.event_type == "down":
            self.pressed.add(name)
            if self._chord_down():
                self._start_recording("ptt")
        else:
            self.pressed.discard(name)
            if (self.state == self.RECORDING and self.session_mode == "ptt"
                    and any(self._matches(name, ck) for ck in self.ptt_chord)):
                self._finish_recording()

    def _on_toggle(self):
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

    def _finish_recording(self):
        with self.state_lock:
            if self.state != self.RECORDING:
                return
            recorder_mod.play_tone("stop", self.cfg["tones_enabled"])
            audio = self.recorder.stop()
            self.session_mode = None
            self._set_state(self.TRANSCRIBING)
            self.jobs.put(("transcribe", audio))

    # -- worker thread ------------------------------------------------------
    def _worker(self):
        try:
            self.transcriber.load()
            self.log(f"model loaded: {self.transcriber.description()}")
        except Exception as e:
            self.notify(f"Model load failed: {e}. Check your internet connection "
                        "for the first-run download, then restart FlowLocal.")
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
                    self.transcriber.load()
                    self.notify(f"Model ready: {self.transcriber.description()}")
                elif kind == "transcribe":
                    self._handle_transcription(payload)
            except Exception as e:
                recorder_mod.play_tone("error", self.cfg["tones_enabled"])
                self.notify(f"Transcription failed: {e}")
            self._set_state(self.IDLE)

    def _handle_transcription(self, audio):
        if not recorder_mod.passes_gate(audio, self.cfg["silence_rms_threshold"],
                                        self.cfg["min_duration_s"]):
            self.log("recording gated (silence/too short) — nothing injected")
            return
        raw = self.transcriber.transcribe(audio)
        text = commands.process(raw, self.cfg["replacements"])
        if not text:
            self.log("empty transcript — nothing injected")
            return
        self.last_transcript = text
        injector.inject_text(text, paste_fallback=self.cfg["paste_fallback"])
        self.log(f"injected {len(text)} chars")

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
            Item("Open config", self._open_config),
            Menu.SEPARATOR,
            Item("Quit", self._quit),
        )

    def _copy_last(self):
        import pyperclip
        if self.last_transcript:
            pyperclip.copy(self.last_transcript)
            self.notify("Last transcript copied to clipboard")
        else:
            self.notify("No transcript yet — hold the hotkey and speak first")

    def _set_model(self, name):
        self.cfg["model"] = name
        config_mod.save(self.cfg)
        self.jobs.put(("reload", name))

    def _set_device(self, idx):
        self.cfg["input_device"] = idx
        self.recorder.device = idx
        config_mod.save(self.cfg)

    def _toggle_paste(self):
        self.cfg["paste_fallback"] = not self.cfg["paste_fallback"]
        config_mod.save(self.cfg)

    def _open_config(self):
        subprocess.Popen(["notepad.exe", config_mod.PATH])

    # -- lifecycle -------------------------------------------------------------
    def _quit(self):
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        self.jobs.put(None)
        self.worker.join(timeout=5)
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
        self.worker.start()
        self._register_hotkeys()
        self.icon.run(setup=self._on_tray_ready)
        self.log("clean exit")


def main():
    parser = argparse.ArgumentParser(description="FlowLocal — local voice-to-text")
    parser.add_argument("--smoke", action="store_true",
                        help="start, load model, then exit (self-test)")
    args = parser.parse_args()

    mutex = acquire_single_instance()
    if mutex is None:
        print("FlowLocal: already running — exiting", flush=True)
        sys.exit(1)

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    cfg = config_mod.load()
    if args.smoke:  # deterministic, small, CPU-only for the self-test
        cfg["model"] = "small.en"
    app = FlowLocalApp(cfg, smoke=args.smoke)
    if args.smoke:
        app.transcriber.force_device = "cpu"
    app.run()


if __name__ == "__main__":
    main()
