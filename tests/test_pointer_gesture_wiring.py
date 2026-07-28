"""Point & Speak wiring: config drives the hook; the gesture drives TTS."""
import types

import app as app_mod
import config as config_mod


class _FakeHook:
    def __init__(self):
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False


def _bare_app(cfg):
    a = app_mod.ROARApp.__new__(app_mod.ROARApp)
    a.cfg = cfg
    a._pointer_hook = None
    a.log = lambda msg: None
    a.notify = lambda msg: None
    a.tts_service = types.SimpleNamespace(active=False)
    a._dispatched = []
    a._dispatch_tts_command = lambda msg: a._dispatched.append(msg) or {"ok": True}
    return a


def test_defaults_are_off():
    assert config_mod.DEFAULTS["tts_pointer_gesture_enabled"] is False
    assert config_mod.DEFAULTS["tts_pointer_gesture_modifier"] == "ctrl"


def test_sync_installs_only_when_both_flags_on(monkeypatch):
    import mouse_hook
    created = []

    def fake_ctor(cb, on_error=None):
        h = _FakeHook(); created.append(h); return h
    monkeypatch.setattr(mouse_hook, "PointerGestureHook", fake_ctor)

    a = _bare_app({"tts_pointer_gesture_enabled": True, "tts_enabled": False})
    a._sync_pointer_gesture()
    assert a._pointer_hook is None          # TTS off -> no hook

    a.cfg["tts_enabled"] = True
    a._sync_pointer_gesture()
    assert a._pointer_hook is created[0] and created[0].started

    a._sync_pointer_gesture()               # idempotent: no second hook
    assert len(created) == 1

    a.cfg["tts_pointer_gesture_enabled"] = False
    a._sync_pointer_gesture()
    assert a._pointer_hook is None and created[0].started is False


def test_gesture_reads_selection_when_idle(monkeypatch):
    a = _bare_app({})
    a._on_pointer_gesture()
    # dispatch happens on a thread; join it via the recorded call
    import time
    for _ in range(100):
        if a._dispatched:
            break
        time.sleep(0.01)
    assert a._dispatched == [{"command": "read_selected", "force_fallback": True}]


def test_gesture_stops_when_speaking():
    a = _bare_app({})
    a.tts_service = types.SimpleNamespace(active=True)
    a._on_pointer_gesture()
    import time
    for _ in range(100):
        if a._dispatched:
            break
        time.sleep(0.01)
    assert a._dispatched == [{"command": "stop"}]


def test_config_change_triggers_tts_reload_action():
    old = dict(config_mod.DEFAULTS)
    new = dict(config_mod.DEFAULTS)
    new["tts_pointer_gesture_enabled"] = True
    assert ("reload_tts_config", None) in app_mod.diff_config(old, new)
