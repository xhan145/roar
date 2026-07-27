"""End-to-end: a taught correction actually changes what gets TYPED.

Drives the real ROARApp._handle_transcription path (the same code a live
dictation runs) with the model/injection stubbed, so this proves the wiring —
not just that corrections.apply() works in isolation.
"""
import queue
import threading
import types

import numpy as np
import pytest

import app as app_mod
import editing
import gestures
import history as history_mod
import injector
import recorder as recorder_mod
import vocabulary


def _make_app(tmp_path, heard_text, corrections=None):
    cfg = {
        "history_enabled": True, "audio_retention_days": 0,
        "silence_rms_threshold": 0.005, "min_duration_s": 0.3,
        "paste_fallback": False, "replacements": {}, "tones_enabled": False,
        "overlay_enabled": False, "streaming_preview": False,
        "context_aware": False, "corrections": corrections or {},
    }
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
    a.state = a.IDLE
    a.state_lock = threading.RLock()
    a.session_mode = None
    a.jobs = queue.Queue()
    a._detector = gestures.TapToggleDetector()
    a._gesture_lock = threading.Lock()
    a._defer_timer = None
    a.transcriber = types.SimpleNamespace(
        active_model="small.en", hotwords=None,
        transcribe=lambda audio: heard_text)
    return a


def _loud_audio(seconds=1.0):
    n = int(recorder_mod.SAMPLE_RATE * seconds)
    return (0.1 * np.sin(np.linspace(0, 200, n))).astype(np.float32)


def test_taught_correction_changes_the_typed_text(tmp_path, monkeypatch):
    typed = {}
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False:
                        typed.update(text=text) or True)
    a = _make_app(tmp_path, "I use pie plot every day",
                  corrections={"pie plot": "PyPlot"})
    a._handle_transcription(_loud_audio())
    assert typed["text"] == "I use PyPlot every day"
    a.history.close()


def test_without_the_correction_the_mistake_survives(tmp_path, monkeypatch):
    """Control: proves the fix above came from the correction, not the pipeline."""
    typed = {}
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False:
                        typed.update(text=text) or True)
    a = _make_app(tmp_path, "I use pie plot every day", corrections={})
    a._handle_transcription(_loud_audio())
    assert typed["text"] == "I use pie plot every day"
    a.history.close()


def test_correction_does_not_eat_sentence_punctuation(tmp_path, monkeypatch):
    typed = {}
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False:
                        typed.update(text=text) or True)
    a = _make_app(tmp_path, "call cuber netes, then stop.",
                  corrections={"cuber netes": "Kubernetes"})
    a._handle_transcription(_loud_audio())
    assert typed["text"] == "Call Kubernetes, then stop."
    a.history.close()


def test_history_stores_the_corrected_text(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path, "ship it to bob",
                  corrections={"bob": "Bob"})
    a._handle_transcription(_loud_audio())
    assert a.history.list()[0]["text"] == "Ship it to Bob"
    a.history.close()


def test_intended_words_reach_the_recognizer_as_hotwords(tmp_path):
    """The 'prevent' half: what you meant is fed to the model as a hotword."""
    import access
    a = _make_app(tmp_path, "unused",
                  corrections={"pie plot": "PyPlot", "cuber netes": "Kubernetes"})
    a.cfg["custom_vocabulary"] = ["ScratchEdge"]
    a.cfg["auto_vocabulary"] = False
    a._rebuild_hotwords()
    words = a.transcriber.hotwords or ""
    assert "PyPlot" in words and "Kubernetes" in words
    assert "ScratchEdge" in words          # existing vocabulary is preserved
    a.history.close()
