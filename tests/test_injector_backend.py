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
