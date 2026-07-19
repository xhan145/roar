# tests/test_hotkeys_x11.py
import sys, types
import pytest

def _stub_pynput(monkeypatch, listener_holder):
    kb = types.ModuleType("pynput.keyboard")
    class KeyCode:
        def __init__(self, char=None): self.char = char
    class Key:
        ctrl = "ctrl"; space = "space"
    class Listener:
        def __init__(self, on_press=None, on_release=None):
            listener_holder["on_press"] = on_press
            listener_holder["on_release"] = on_release
            self.alive = True
        def start(self): pass
        def stop(self): self.alive = False
        def is_alive(self): return self.alive
    kb.KeyCode = KeyCode; kb.Key = Key; kb.Listener = Listener
    root = types.ModuleType("pynput"); root.keyboard = kb
    monkeypatch.setitem(sys.modules, "pynput", root)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", kb)
    return kb

def test_key_event_forwarded_as_down_up(monkeypatch):
    holder = {}
    kb = _stub_pynput(monkeypatch, holder)
    import importlib, hotkeys_x11; importlib.reload(hotkeys_x11)
    seen = []
    h = hotkeys_x11.X11Hotkeys(lambda e: seen.append((e.event_type, e.name)),
                               lambda: None, "ctrl+space")
    h.start()
    holder["on_press"](kb.KeyCode(char="a"))
    holder["on_release"](kb.KeyCode(char="a"))
    assert ("down", "a") in seen and ("up", "a") in seen

def test_toggle_chord_fires(monkeypatch):
    holder = {}
    kb = _stub_pynput(monkeypatch, holder)
    import importlib, hotkeys_x11; importlib.reload(hotkeys_x11)
    fired = []
    h = hotkeys_x11.X11Hotkeys(lambda e: None, lambda: fired.append(1), "ctrl+space")
    h.start()
    holder["on_press"](kb.Key.ctrl)
    holder["on_press"](kb.Key.space)
    assert fired == [1]
