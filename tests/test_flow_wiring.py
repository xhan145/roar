"""Flow wiring in the tray app: route toggles, delivery, entitlement gating."""

import types

import app as app_mod
import routing


def _bare_app(entitled=True, routes=None):
    a = app_mod.ROARApp.__new__(app_mod.ROARApp)
    a.cfg = {"flow_notes_path": ""}
    a._foreground_exe = lambda: "test.exe"
    a._routes = routes or {"clipboard": False, "notes": False, "speak": False}
    a.notices = []
    a.notify = a.notices.append
    a.logs = []
    a.log = a.logs.append
    a.injected = []
    a._inject_final = lambda t, audio, tr_ms, target: a.injected.append(t)
    a.tts_service = types.SimpleNamespace(
        speak=lambda text, source, remember: a.logs.append(f"spoke:{text}"))
    return a


def _entitle(monkeypatch, allowed):
    import access
    monkeypatch.setattr(access, "can", lambda f: allowed)


# -- route commands ---------------------------------------------------------

def test_route_toggle_updates_session_state_and_notifies(monkeypatch):
    a = _bare_app()
    _entitle(monkeypatch, True)
    a._apply_route_command(("notes", True))
    assert a._routes["notes"] is True
    assert any("notes route on" in n for n in a.notices)
    assert any("ROAR Notes.md" in n for n in a.notices)  # names the file


def test_all_off_clears_every_route(monkeypatch):
    a = _bare_app(routes={"clipboard": True, "notes": True, "speak": True})
    _entitle(monkeypatch, True)
    a._apply_route_command("all_off")
    assert a._routes == {"clipboard": False, "notes": False, "speak": False}


def test_route_toggle_gated_to_pro(monkeypatch):
    a = _bare_app()
    _entitle(monkeypatch, False)
    a._apply_route_command(("notes", True))
    assert a._routes["notes"] is False
    assert any("ROAR Pro" in n for n in a.notices)


# -- delivery ---------------------------------------------------------------

def test_inject_only_fast_path(monkeypatch):
    a = _bare_app()
    _entitle(monkeypatch, True)
    a._deliver("hello", None, 0, None)
    assert a.injected == ["hello"]


def test_multi_route_delivers_to_all(monkeypatch, tmp_path):
    a = _bare_app(routes={"clipboard": False, "notes": True, "speak": True})
    a.cfg["flow_notes_path"] = str(tmp_path / "notes.md")
    _entitle(monkeypatch, True)
    a._deliver("hello world", None, 0, None)
    assert a.injected == ["hello world"]
    assert "hello world" in (tmp_path / "notes.md").read_text(encoding="utf-8")
    assert "spoke:hello world" in a.logs


def test_unwritable_notes_disables_the_route_and_tells_the_user(monkeypatch):
    a = _bare_app(routes={"clipboard": False, "notes": True, "speak": False})
    _entitle(monkeypatch, True)
    monkeypatch.setattr(routing, "append_notes",
                        lambda p, line: (_ for _ in ()).throw(OSError("locked")))
    a._deliver("hello", None, 0, None)
    assert a.injected == ["hello"]            # injection survived
    assert a._routes["notes"] is False        # route auto-disabled
    assert any("notes route" in n.lower() for n in a.notices)


def test_unentitled_delivery_is_inject_only_even_with_routes_on(monkeypatch):
    a = _bare_app(routes={"clipboard": True, "notes": True, "speak": True})
    _entitle(monkeypatch, False)
    a._deliver("hello", None, 0, None)
    assert a.injected == ["hello"]
    assert not any(l.startswith("spoke:") for l in a.logs)


def test_default_notes_path_lands_in_documents():
    a = _bare_app()
    assert a._notes_path().endswith("ROAR Notes.md")
    assert "Documents" in a._notes_path()


def test_per_app_rule_overrides_session_at_delivery(monkeypatch, tmp_path):
    """Focused-app rules win: notes globally ON but OFF for test.exe."""
    a = _bare_app(routes={"clipboard": False, "notes": True, "speak": False})
    a.cfg["flow_notes_path"] = str(tmp_path / "notes.md")
    a.cfg["route_profiles"] = {"test.exe": {"notes": False}}
    _entitle(monkeypatch, True)
    a._deliver("hello", None, 0, None)
    assert a.injected == ["hello"]
    assert not (tmp_path / "notes.md").exists()   # notes suppressed for this app


def test_per_app_rule_adds_a_route_for_one_app(monkeypatch, tmp_path):
    a = _bare_app()                                # all session routes off
    a.cfg["flow_notes_path"] = str(tmp_path / "notes.md")
    a.cfg["route_profiles"] = {"test.exe": {"notes": True}}
    _entitle(monkeypatch, True)
    a._deliver("captured", None, 0, None)
    assert a.injected == ["captured"]
    assert "captured" in (tmp_path / "notes.md").read_text(encoding="utf-8")


# -- review findings: notes-failure pause vs per-app pins --------------------

def test_pinned_notes_rule_cannot_refire_the_failure_toast(monkeypatch):
    """A per-app rule pinning notes ON must not defeat the failure pause:
    one toast, then notes stays paused across deliveries."""
    a = _bare_app()
    a._notes_broken = False
    a.cfg["route_profiles"] = {"test.exe": {"notes": True}}
    a._target_exe = "test.exe"
    _entitle(monkeypatch, True)
    monkeypatch.setattr(routing, "append_notes",
                        lambda p, line: (_ for _ in ()).throw(OSError("locked")))
    for _ in range(3):
        a._deliver("hello", None, 0, None)
    assert a.injected == ["hello"] * 3          # dictation never breaks
    assert len(a.notices) == 1                  # ONE honest toast, not three
    assert "paused" in a.notices[0]


def test_notes_pause_clears_on_deliberate_retoggle(monkeypatch):
    a = _bare_app()
    a._notes_broken = True
    _entitle(monkeypatch, True)
    a._apply_route_command(("notes", True))
    assert a._notes_broken is False


def test_notes_path_change_schedules_unpause():
    import config as config_mod
    old = dict(config_mod.DEFAULTS)
    new = dict(config_mod.DEFAULTS)
    new["flow_notes_path"] = "D:/new/notes.md"
    assert ("notes_path_changed", None) in app_mod.diff_config(old, new)


def test_rule_lookup_uses_recording_time_exe(monkeypatch, tmp_path):
    """Focus moved to another app during transcription: the rule for the app
    the dictation was AIMED at must win, not the newly-focused app's."""
    a = _bare_app()                                  # session routes all off
    a.cfg["flow_notes_path"] = str(tmp_path / "notes.md")
    a.cfg["route_profiles"] = {"winword.exe": {"notes": True}}
    a._target_exe = "winword.exe"                    # captured at record start
    a._foreground_exe = lambda: "chrome.exe"         # focus moved since
    _entitle(monkeypatch, True)
    a._deliver("dictated into word", None, 0, None)
    assert "dictated into word" in (tmp_path / "notes.md").read_text(
        encoding="utf-8")
