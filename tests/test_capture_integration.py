"""Integration: a running app's transcription path records to history.

Exercises ROARApp._handle_transcription end-to-end (gate -> transcribe
-> inject -> record) with the heavy pieces (model, tray, keyboard, injection)
stubbed, against a REAL temp History DB. This is the deterministic stand-in
for the mic-loopback manual test, which depends on system audio routing.
"""
import types

import numpy as np

import app as app_mod
import editing
import history as history_mod
import injector
import recorder as recorder_mod


def _make_app(tmp_path, cfg_overrides=None):
    cfg = {
        "history_enabled": True,
        "audio_retention_days": 0,
        "silence_rms_threshold": 0.005,
        "min_duration_s": 0.3,
        "paste_fallback": False,
        "replacements": {},
        "tones_enabled": False,
        "overlay_enabled": False,
        "streaming_preview": False,
    }
    if cfg_overrides:
        cfg.update(cfg_overrides)
    # bare instance — skip __init__ (it builds tray/model/keyboard threads)
    a = app_mod.ROARApp.__new__(app_mod.ROARApp)
    a.cfg = cfg
    a.last_transcript = ""
    a._dictation_count = 0
    a._session_gen = 0
    a.overlay = None
    a.history = history_mod.History(db_path=str(tmp_path / "h.db"),
                                    audio_dir=str(tmp_path / "audio"))
    a.log = lambda msg: None
    a._inject_stack = editing.InjectionStack()
    a.transcriber = types.SimpleNamespace(
        active_model="small.en",
        transcribe=lambda audio: "hello from the test")
    return a


def _loud_audio(seconds=1.0):
    n = int(recorder_mod.SAMPLE_RATE * seconds)
    return (0.1 * np.sin(np.linspace(0, 200, n))).astype(np.float32)


def test_transcription_records_history(tmp_path, monkeypatch):
    injected = {}
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: injected.update(text=text))
    a = _make_app(tmp_path)
    a._handle_transcription(_loud_audio())
    # commands.process capitalizes the sentence start
    assert injected["text"] == "Hello from the test"
    rows = a.history.list()
    assert len(rows) == 1
    assert rows[0]["text"] == "Hello from the test"
    assert rows[0]["model"] == "small.en"
    a.history.close()


def test_gated_audio_records_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: None)
    a = _make_app(tmp_path)
    a._handle_transcription(np.zeros(recorder_mod.SAMPLE_RATE, dtype=np.float32))
    assert a.history.list() == []
    a.history.close()


def test_history_disabled_records_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: None)
    a = _make_app(tmp_path, {"history_enabled": False})
    a._handle_transcription(_loud_audio())
    assert a.history.list() == []
    a.history.close()


def test_retained_audio_saved_on_capture(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: None)
    a = _make_app(tmp_path, {"audio_retention_days": 7})
    a._handle_transcription(_loud_audio())
    rows = a.history.list()
    assert len(rows) == 1 and rows[0]["has_audio"] is True
    a.history.close()


def test_duration_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: None)
    a = _make_app(tmp_path)
    a._handle_transcription(_loud_audio(seconds=2.0))
    row = a.history.list()[0]
    assert row["duration_s"] is not None and abs(row["duration_s"] - 2.0) < 0.01
    a.history.close()


def test_rebuild_hotwords_merges_custom_and_signature(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: None)
    a = _make_app(tmp_path)
    a.cfg["custom_vocabulary"] = ["ScratchEdge"]
    a.cfg["auto_vocabulary"] = True
    for i in range(3):
        a.history.record("kubernetes deployment pipeline kubernetes", ts=float(i))
    a._rebuild_hotwords()
    hw = a.transcriber.hotwords
    assert hw.startswith("ScratchEdge")
    assert "kubernetes" in hw
    a.cfg["auto_vocabulary"] = False
    a._rebuild_hotwords()
    assert a.transcriber.hotwords == "ScratchEdge"
    a.history.close()


def test_scratch_undoes_last_injection(tmp_path, monkeypatch):
    sent = {"backspaces": 0}
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_hwnd",
                        staticmethod(lambda: 42))
    monkeypatch.setattr(app_mod, "send_backspaces",
                        lambda n: sent.__setitem__("backspaces", n))
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path)
    a._handle_transcription(_loud_audio())
    assert a.history.stats()["count"] == 1
    a.transcriber.transcribe = lambda audio: "scratch that"
    a._handle_transcription(_loud_audio())
    # prepared text = pipeline text + trailing space
    assert sent["backspaces"] == len("Hello from the test ")
    assert a.history.stats()["count"] == 0    # history row removed
    a.history.close()


def test_scratch_refuses_on_focus_change(tmp_path, monkeypatch):
    sent = {"backspaces": 0}
    hwnd = {"v": 42}
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_hwnd",
                        staticmethod(lambda: hwnd["v"]))
    monkeypatch.setattr(app_mod, "send_backspaces",
                        lambda n: sent.__setitem__("backspaces", n))
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path)
    a._handle_transcription(_loud_audio())
    hwnd["v"] = 99                            # user clicked elsewhere
    a.transcriber.transcribe = lambda audio: "scratch that"
    a._handle_transcription(_loud_audio())
    assert sent["backspaces"] == 0            # refused
    assert a.history.stats()["count"] == 1    # row kept
    a.history.close()
