"""Integration: a running app's transcription path records to history.

Exercises ROARApp._handle_transcription end-to-end (gate -> transcribe
-> inject -> record) with the heavy pieces (model, tray, keyboard, injection)
stubbed, against a REAL temp History DB. This is the deterministic stand-in
for the mic-loopback manual test, which depends on system audio routing.
"""
import queue
import threading
import types

import numpy as np
import pytest

import access
import app as app_mod
import editing
import gestures
import history as history_mod
import injector
import legacy_grant
import recorder as recorder_mod


@pytest.fixture
def grandfathered(monkeypatch):
    """Simulate an EXISTING install. Every paid-target feature shipped free
    through v0.21.0, so a pre-gating user carries the one-time legacy grant and
    keeps them — that is the whole grandfathering promise. Tests that exercise
    those features use this fixture; a fresh Core install is covered separately
    below."""
    monkeypatch.setattr(access, "edition", lambda: "core")
    monkeypatch.setattr(access, "grants", lambda: legacy_grant.GRANTED_FEATURES)
    return legacy_grant.GRANTED_FEATURES


class _StubRecorder:
    def start(self):
        pass

    def stop(self):
        return np.zeros(100, dtype=np.float32)


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
        # determinism: never let the REAL foreground window during a test run
        # pick a profile — profile tests opt in and stub the lookups
        "context_aware": False,
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
    a.state = a.IDLE
    a.state_lock = threading.RLock()
    a.session_mode = None
    a.jobs = queue.Queue()
    a._detector = gestures.TapToggleDetector()
    a._gesture_lock = threading.Lock()
    a._defer_timer = None
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
                        lambda text, paste_fallback=False:
                        injected.update(text=text) or True)
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
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path)
    a._handle_transcription(np.zeros(recorder_mod.SAMPLE_RATE, dtype=np.float32))
    assert a.history.list() == []
    a.history.close()


def test_history_disabled_records_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path, {"history_enabled": False})
    a._handle_transcription(_loud_audio())
    assert a.history.list() == []
    a.history.close()


def test_retained_audio_saved_on_capture(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path, {"audio_retention_days": 7})
    a._handle_transcription(_loud_audio())
    rows = a.history.list()
    assert len(rows) == 1 and rows[0]["has_audio"] is True
    a.history.close()


def test_duration_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path)
    a._handle_transcription(_loud_audio(seconds=2.0))
    row = a.history.list()[0]
    assert row["duration_s"] is not None and abs(row["duration_s"] - 2.0) < 0.01
    a.history.close()


def test_rebuild_hotwords_merges_custom_and_signature(tmp_path, monkeypatch, grandfathered):
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


def test_scratch_keeps_history_when_backspaces_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_hwnd",
                        staticmethod(lambda: 42))
    monkeypatch.setattr(app_mod, "send_backspaces", lambda n: False)
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path)
    a._handle_transcription(_loud_audio())
    assert a.history.stats()["count"] == 1
    a.transcriber.transcribe = lambda audio: "scratch that"
    a._handle_transcription(_loud_audio())
    assert a.history.stats()["count"] == 1    # history row kept — backspaces failed
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


def test_transcription_refuses_to_inject_when_focus_changed(tmp_path, monkeypatch):
    calls = []
    hwnd = {"v": 99}
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_hwnd",
                        staticmethod(lambda: hwnd["v"]))
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: calls.append(text) or True)
    a = _make_app(tmp_path)
    a._target_hwnd = 42
    a._handle_transcription(_loud_audio())
    assert calls == []
    assert a.history.stats()["count"] == 0
    a.history.close()


def test_transcription_records_target_window_from_recording_start(tmp_path, monkeypatch):
    hwnd = {"v": 42}
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_hwnd",
                        staticmethod(lambda: hwnd["v"]))
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path)
    a._target_hwnd = 42
    a._handle_transcription(_loud_audio())
    hwnd["v"] = 99
    a.transcriber.transcribe = lambda audio: "scratch that"
    sent = {"backspaces": 0}
    monkeypatch.setattr(app_mod, "send_backspaces",
                        lambda n: sent.__setitem__("backspaces", n))
    a._handle_transcription(_loud_audio())
    assert sent["backspaces"] == 0
    assert a.history.stats()["count"] == 1
    a.history.close()


def test_milestone_unlock_records_and_notifies(tmp_path, monkeypatch):
    notes = []
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path, {"milestones_enabled": True,
                             "milestone_notifications": True})
    a.notify = lambda msg: notes.append(msg)
    a.transcriber.transcribe = lambda audio: "word " * 1000
    a._handle_transcription(_loud_audio())
    assert a.history.unlocks().get(1000) is not None
    assert any("First Roar" in n for n in notes)
    a.history.close()


def test_milestone_disabled_no_unlock(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path, {"milestones_enabled": False})
    a.notify = lambda msg: None
    a.transcriber.transcribe = lambda audio: "word " * 1000
    a._handle_transcription(_loud_audio())
    assert a.history.unlocks() == {}
    a.history.close()


def test_milestone_no_renotify_after_history_clear(tmp_path, monkeypatch):
    notes = []
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path, {"milestones_enabled": True,
                             "milestone_notifications": True})
    a.notify = lambda msg: notes.append(msg)
    a.transcriber.transcribe = lambda audio: "word " * 1000
    a._handle_transcription(_loud_audio())          # crosses First Roar -> 1 note
    assert len([n for n in notes if "First Roar" in n]) == 1
    a.history.clear()                                # badges sticky, total -> 0
    a._handle_transcription(_loud_audio())           # re-crosses 1000
    # badge already earned -> must NOT notify again
    assert len([n for n in notes if "First Roar" in n]) == 1
    a.history.close()


def test_double_tap_enters_handsfree(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path)
    a.notify = lambda msg: None
    a.recorder = _StubRecorder()
    clock = {"t": 0.0}
    monkeypatch.setattr(app_mod.time, "monotonic", lambda: clock["t"])
    a._gesture("down"); clock["t"] = 0.1
    a._gesture("up");   clock["t"] = 0.3          # tap
    a._gesture("down")                             # 2nd tap within 400ms
    assert a.session_mode == "toggle"
    assert a.state == a.RECORDING
    clock["t"] = 0.4; a._gesture("up")             # release ignored
    assert a.state == a.RECORDING
    clock["t"] = 5.0; a._gesture("down")           # single tap stops
    assert a.state in (a.TRANSCRIBING, a.IDLE)
    a.history.close()


def test_hold_is_still_ptt(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path)
    a.notify = lambda msg: None
    a.recorder = _StubRecorder()
    clock = {"t": 0.0}
    monkeypatch.setattr(app_mod.time, "monotonic", lambda: clock["t"])
    a._gesture("down"); assert a.state == a.RECORDING
    clock["t"] = 1.0; a._gesture("up")             # long hold -> finish now
    assert a.state in (a.TRANSCRIBING, a.IDLE)
    a.history.close()


def test_context_aware_casual_app_keeps_texting_style(tmp_path, monkeypatch, grandfathered):
    injected = {}
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: injected.update(text=text))
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_exe",
                        staticmethod(lambda: "discord.exe"))
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_title",
                        staticmethod(lambda: "Discord"))
    a = _make_app(tmp_path, {"context_aware": True})
    a.transcriber.transcribe = lambda audio: "like, um hello from the test"
    a._handle_transcription(_loud_audio())
    assert injected["text"] == "like, hello from the test"  # lowercase, keeps "like"
    a.history.close()


def test_context_aware_formal_app_polishes(tmp_path, monkeypatch, grandfathered):
    injected = {}
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: injected.update(text=text))
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_exe",
                        staticmethod(lambda: "outlook.exe"))
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_title",
                        staticmethod(lambda: "Inbox - Outlook"))
    a = _make_app(tmp_path, {"context_aware": True})
    a.transcriber.transcribe = lambda audio: "you know, um hello from the test"
    a._handle_transcription(_loud_audio())
    assert injected["text"] == "Hello from the test"
    a.history.close()


def test_context_aware_code_editor_is_verbatim(tmp_path, monkeypatch, grandfathered):
    injected = {}
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: injected.update(text=text))
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_exe",
                        staticmethod(lambda: "code.exe"))
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_title",
                        staticmethod(lambda: "Visual Studio Code"))
    a = _make_app(tmp_path, {"context_aware": True})
    a.transcriber.transcribe = lambda audio: "um hello from the test"
    a._handle_transcription(_loud_audio())
    assert injected["text"] == "um hello from the test"
    a.history.close()


def test_fresh_core_install_is_gated_but_dictation_still_works(tmp_path, monkeypatch):
    """A NEW user (no license, no grant) does NOT get Developer per-app profiles
    — but plain dictation still works and is cleanly formatted. A gate must never
    be able to break dictation itself."""
    injected = {}
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: injected.update(text=text))
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_exe",
                        staticmethod(lambda: "code.exe"))
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_title",
                        staticmethod(lambda: "Visual Studio Code"))
    monkeypatch.setattr(access, "edition", lambda: "core")
    monkeypatch.setattr(access, "grants", lambda: frozenset())   # fresh install
    a = _make_app(tmp_path, {"context_aware": True})
    a.transcriber.transcribe = lambda audio: "um hello from the test"
    a._handle_transcription(_loud_audio())
    # the code-editor profile (verbatim) is Developer-only, so it does NOT apply;
    # the user still gets working, cleanly-formatted dictation
    assert injected["text"] == "Hello from the test"
    a.history.close()


def test_unentitled_code_mode_steps_down_without_touching_config(tmp_path, monkeypatch):
    """Dropping to Core must not rewrite the user's settings: format_mode stays
    'code' on disk while the BEHAVIOR resolves down, so restoring a license
    reactivates it with no reconfiguration."""
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    monkeypatch.setattr(access, "edition", lambda: "core")
    monkeypatch.setattr(access, "grants", lambda: frozenset())
    a = _make_app(tmp_path, {"format_mode": "code", "snippets": {"sig": "Greg"}})
    eff = a._effective_formatting()
    assert eff["mode"] == "clean"              # behaviour steps down
    assert eff["snippets"] == {}               # Pro snippets withheld
    assert a.cfg["format_mode"] == "code"      # ...but config is PRESERVED
    assert a.cfg["snippets"] == {"sig": "Greg"}
    a.history.close()


def test_restoring_entitlement_reactivates_saved_paid_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    monkeypatch.setattr(access, "edition", lambda: "developer")
    monkeypatch.setattr(access, "grants", lambda: frozenset())
    a = _make_app(tmp_path, {"format_mode": "code", "snippets": {"sig": "Greg"}})
    eff = a._effective_formatting()
    assert eff["mode"] == "code"                       # active again
    assert eff["snippets"] == {"sig": "Greg"}
    a.history.close()


def test_context_aware_off_reverts_to_normal_user_settings(tmp_path, monkeypatch):
    injected = {}
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: injected.update(text=text))
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_exe",
                        staticmethod(lambda: "code.exe"))
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_title",
                        staticmethod(lambda: "Visual Studio Code"))
    a = _make_app(tmp_path, {"context_aware": False, "cleanup_enabled": False})
    a.transcriber.transcribe = lambda audio: "um hello from the test"
    a._handle_transcription(_loud_audio())
    assert injected["text"] == "Um hello from the test"   # no profile applied
    a.history.close()


def test_focus_change_blocks_injection(tmp_path, monkeypatch):
    injected = {}
    notes = []
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: injected.update(text=text))
    hwnd = {"v": 42}
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_hwnd",
                        staticmethod(lambda: hwnd["v"]))
    a = _make_app(tmp_path)
    a.notify = lambda msg: notes.append(msg)
    a._target_hwnd = 42            # captured at recording start
    hwnd["v"] = 99                 # user clicked elsewhere before transcribe done
    a._handle_transcription(_loud_audio())
    assert injected == {}                          # nothing typed
    assert a.history.list() == []                  # nothing recorded
    assert any("did not type" in n for n in notes)
    a.history.close()


def test_focus_same_still_injects(tmp_path, monkeypatch):
    injected = {}
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: injected.update(text=text))
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_hwnd",
                        staticmethod(lambda: 42))
    a = _make_app(tmp_path)
    a._target_hwnd = 42
    a._handle_transcription(_loud_audio())
    assert injected["text"] == "Hello from the test"
    a.history.close()


def test_profile_lookup_failure_is_safe(tmp_path, monkeypatch):
    injected = {}
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: injected.update(text=text))
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_exe",
                        staticmethod(lambda: ""))       # lookup failed
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_title",
                        staticmethod(lambda: ""))
    a = _make_app(tmp_path, {"context_aware": True})
    a._handle_transcription(_loud_audio())
    assert injected["text"] == "Hello from the test"     # user defaults apply
    a.history.close()


def test_profiles_do_not_mutate_global_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_exe",
                        staticmethod(lambda: "code.exe"))
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_title",
                        staticmethod(lambda: ""))
    a = _make_app(tmp_path, {"context_aware": True, "cleanup_enabled": True})
    before = dict(a.cfg)
    a._handle_transcription(_loud_audio())               # code profile applied
    assert a.cfg == before                                # per-dictation only
    a.history.close()


def test_window_title_never_logged(tmp_path, monkeypatch):
    logs = []
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_exe",
                        staticmethod(lambda: "chrome.exe"))
    monkeypatch.setattr(app_mod.ROARApp, "_foreground_title",
                        staticmethod(lambda: "SECRET BANKING TAB - WhatsApp"))
    a = _make_app(tmp_path, {"context_aware": True})
    a.log = lambda m: logs.append(m)
    a._handle_transcription(_loud_audio())
    assert all("SECRET" not in m and "BANKING" not in m for m in logs)
    a.history.close()
