import sys

import hotkey_listener

def test_app_imports_without_keyboard_module_at_top():
    """app.py must not `import keyboard` at module top — that call raises
    'must be root' on Linux, which would break `import app` there entirely."""
    sys.modules.pop("app", None)
    import app  # noqa: F401 — import is the assertion
    assert "keyboard" not in vars(app)

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
