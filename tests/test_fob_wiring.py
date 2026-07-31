"""Fob wiring: config keys, diff action, app callbacks."""

import types

import app as app_mod
import config as config_mod


def test_defaults():
    assert config_mod.DEFAULTS["fob_enabled"] is True
    assert config_mod.DEFAULTS["fob_pos"] is None


def test_config_round_trips_pos_and_enabled(tmp_path):
    p = str(tmp_path / "config.json")
    cfg = config_mod.load(p)
    cfg["fob_enabled"] = False
    cfg["fob_pos"] = [120, -40]          # negative y is legal (multi-monitor)
    config_mod.save(cfg, p)
    loaded = config_mod.load(p)
    assert loaded["fob_enabled"] is False
    assert loaded["fob_pos"] == [120, -40]


def test_config_rejects_garbage_pos(tmp_path):
    import json
    p = tmp_path / "config.json"
    cfg = dict(config_mod.DEFAULTS)
    cfg["fob_pos"] = ["a", None, 3]
    p.write_text(json.dumps(cfg), encoding="utf-8")
    assert config_mod.load(str(p))["fob_pos"] is None


def test_diff_config_emits_set_fob():
    old = dict(config_mod.DEFAULTS)
    new = dict(config_mod.DEFAULTS)
    new["fob_enabled"] = False
    assert ("set_fob", None) in app_mod.diff_config(old, new)
    new2 = dict(config_mod.DEFAULTS)
    new2["fob_pos"] = [10, 10]
    assert ("set_fob", None) in app_mod.diff_config(old, new2)


def _bare_app(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(config_mod, "save",
                        lambda cfg, path=None: saved.update(cfg))
    saved = {}
    import threading
    a = app_mod.ROARApp.__new__(app_mod.ROARApp)
    a.cfg = dict(config_mod.DEFAULTS)
    a.cfg_lock = threading.RLock()
    a.notices = []
    a.notify = a.notices.append
    a.log = lambda m: None
    a.overlay = types.SimpleNamespace(calls=[],
                                      set_fob=lambda e, p=None:
                                      a.overlay.calls.append((e, p)))
    a._dispatched = []
    a._dispatch_tts_command = lambda m: a._dispatched.append(m)
    a._scratched = []
    a._scratch = lambda: a._scratched.append(1)
    a._opened = []
    a._open_settings = lambda: a._opened.append(1)
    return a, saved


def test_fob_move_persists_position(tmp_path, monkeypatch):
    a, saved = _bare_app(tmp_path, monkeypatch)
    a._on_fob_moved(300, 400)
    assert a.cfg["fob_pos"] == [300, 400]
    assert saved["fob_pos"] == [300, 400]


def test_fob_menu_actions_route_correctly(tmp_path, monkeypatch):
    a, saved = _bare_app(tmp_path, monkeypatch)
    a._on_fob_menu("scratch")
    assert a._scratched
    a._on_fob_menu("read_selected")
    assert a._dispatched == [{"command": "read_selected"}]
    a._on_fob_menu("settings")
    assert a._opened
    a._on_fob_menu("hide")
    assert a.cfg["fob_enabled"] is False
    assert a.overlay.calls[-1][0] is False
    assert any("Voice" in n for n in a.notices)   # tells the user where it went
