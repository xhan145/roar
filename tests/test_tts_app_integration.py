import queue
import threading

import app as app_mod
import config


class TTSStub:
    def __init__(self):
        self.active = True
        self.stopped = 0
        self.spoken = []

    def stop(self):
        self.stopped += 1

    def speak(self, text, **kwargs):
        self.spoken.append((text, kwargs))
        return True


class RecorderStub:
    def __init__(self):
        self.started_after_stop = False
        self.app = None

    def start(self):
        self.started_after_stop = self.app.tts_service.stopped > 0


def minimal_app(monkeypatch):
    app = app_mod.ROARApp.__new__(app_mod.ROARApp)
    app.cfg = dict(config.DEFAULTS)
    app.cfg["tts_enabled"] = True
    app.cfg["tts_stop_when_dictation_starts"] = True
    app.state = app.IDLE
    app.state_lock = threading.RLock()
    app.session_mode = None
    app._target_hwnd = None
    app.tts_service = TTSStub()
    app.recorder = RecorderStub()
    app.recorder.app = app
    app.overlay = None
    app.jobs = queue.Queue()
    app._session_gen = 0
    app.icon = type("Icon", (), {"update_menu": lambda self: None})()
    monkeypatch.setattr(app_mod.recorder_mod, "play_tone", lambda *args: None)
    monkeypatch.setattr(app_mod.status_mod, "write_status", lambda **kwargs: True)
    monkeypatch.setattr(app_mod.tray_icons, "make_icon", lambda state: None)
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_hwnd", staticmethod(lambda: 5))
    return app


def test_starting_dictation_stops_tts_before_microphone(monkeypatch):
    app = minimal_app(monkeypatch)
    app._start_recording("ptt")
    assert app.tts_service.stopped == 1
    assert app.recorder.started_after_stop
    assert app.state == app.RECORDING


def test_starting_tts_while_recording_is_rejected(monkeypatch):
    app = minimal_app(monkeypatch)
    app.state = app.RECORDING
    result = app._handle_tts_command({"command": "speak", "text": "hello"})
    assert result["ok"] is False
    assert app.tts_service.spoken == []


def test_all_speech_starting_commands_are_rejected_while_recording(monkeypatch):
    app = minimal_app(monkeypatch)
    app.state = app.RECORDING
    for command in (
            "preview", "read_clipboard", "read_selected", "repeat", "preload"):
        message = {"command": command}
        if command == "preview":
            message["text"] = "hello"
        result = app._handle_tts_command(message)
        assert result["ok"] is False, command
    assert app.tts_service.spoken == []


def test_hotkey_and_tray_dispatch_surface_calm_errors(monkeypatch):
    app = minimal_app(monkeypatch)
    app.state = app.RECORDING
    notices = []
    app.notify = notices.append
    result = app._dispatch_tts_command(
        {"command": "speak", "text": "hello"})
    assert result["ok"] is False
    assert notices == ["Stop dictation before starting Read Aloud."]


def test_read_aloud_code_has_no_entitlement_gate():
    from pathlib import Path
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in Path("tts").glob("*.py"))
    assert "access.can" not in combined
    assert "entitlement" not in combined.lower()
