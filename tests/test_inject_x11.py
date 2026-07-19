# tests/test_inject_x11.py
import sys, types
import pytest

def _stub_pynput(monkeypatch, recorder):
    kb = types.ModuleType("pynput.keyboard")
    class Key: ctrl = "CTRL"
    class Controller:
        def type(self, t): recorder.append(("type", t))
        def press(self, k): recorder.append(("press", k))
        def release(self, k): recorder.append(("release", k))
    kb.Key = Key; kb.Controller = Controller
    root = types.ModuleType("pynput"); root.keyboard = kb
    monkeypatch.setitem(sys.modules, "pynput", root)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", kb)

def test_pynput_type(monkeypatch):
    rec = []
    _stub_pynput(monkeypatch, rec)
    import importlib, inject_x11; importlib.reload(inject_x11)
    inject_x11.X11Injector("pynput").type_text("héllo")
    assert ("type", "héllo") in rec

def test_xdotool_type(monkeypatch):
    calls = {}
    import inject_x11
    monkeypatch.setattr(inject_x11.subprocess, "run",
                        lambda *a, **k: calls.setdefault("argv", a[0]))
    inject_x11.X11Injector("xdotool").type_text("hi")
    assert calls["argv"][:3] == ["xdotool", "type", "--clearmodifiers"]
