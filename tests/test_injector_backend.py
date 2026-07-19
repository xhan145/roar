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


def test_send_backspaces_dispatches_to_backend(monkeypatch):
    calls = {}
    class Fake:
        def send_backspaces(self, n): calls["n"] = n
    monkeypatch.setattr(injector, "_BACKEND", Fake())
    injector.send_backspaces(5)
    assert calls["n"] == 5


def test_send_backspaces_swallows_backend_errors(monkeypatch, capsys):
    class Fake:
        def send_backspaces(self, n): raise RuntimeError("boom")
    monkeypatch.setattr(injector, "_BACKEND", Fake())
    injector.send_backspaces(3)  # must not raise
    assert "send_backspaces failed" in capsys.readouterr().out
