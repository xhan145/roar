import config
from settings_ui import SettingsAPI, normalize_combo


def test_normalize_combo_orders_and_merges_sides():
    assert normalize_combo({"left ctrl", "left windows"}) == "ctrl+windows"
    assert normalize_combo({"right shift", "z", "left alt"}) == "alt+shift+z"
    assert normalize_combo(set()) == ""


def test_set_value_whitelist(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.set_value("tones_enabled", False)["ok"] is True
    assert config.load(p)["tones_enabled"] is False
    assert "error" in api.set_value("model", "tiny.en")  # model is Apply-only


def test_sensitivity_clamped(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.set_value("silence_rms_threshold", 999)["ok"] is True
    assert config.load(p)["silence_rms_threshold"] == 0.02
    assert "error" in api.set_value("silence_rms_threshold", "abc")


def test_apply_hotkeys_validates(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.apply_hotkeys("ctrl+alt", "ctrl+alt+space")["ok"] is True
    assert config.load(p)["hotkey_ptt"] == "ctrl+alt"
    assert "error" in api.apply_hotkeys("", "ctrl+space")
    assert "error" in api.apply_hotkeys("ctrl+x", "ctrl+x")


def test_apply_model(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.apply_model("small.en")["ok"] is True
    assert config.load(p)["model"] == "small.en"
    assert "error" in api.apply_model("bogus-model")


def test_get_state_shape(tmp_path):
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    s = api.get_state()
    assert s["config"]["hotkey_ptt"] == "ctrl+windows"
    assert isinstance(s["devices"], list) and isinstance(s["autostart"], bool)
    assert s["version"] == "0.20.0"
    assert s["edition"] == "Core"


def test_retention_validation_and_immediate_purge(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    monkeypatch.setattr(paths, "audio_dir", lambda: str(tmp_path / "a"))
    from settings_ui import SettingsAPI
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    assert api.set_value("audio_retention_days", 7)["ok"] is True
    assert "error" in api.set_value("audio_retention_days", 3)  # not in allowed set
    assert api.set_value("history_enabled", False)["ok"] is True


def test_history_list_delete_clear(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    monkeypatch.setattr(paths, "audio_dir", lambda: str(tmp_path / "a"))
    from settings_ui import SettingsAPI
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    api._history.record("alpha", ts=1.0)
    api._history.record("beta", ts=2.0)
    rows = api.history_list()
    assert [r["text"] for r in rows] == ["beta", "alpha"]
    assert api.history_delete(rows[0]["id"])["ok"] is True
    assert api.privacy_stats()["count"] == 1
    assert api.history_clear()["removed"] == 1
    assert api.privacy_stats()["count"] == 0


def test_get_insights_and_search(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    monkeypatch.setattr(paths, "audio_dir", lambda: str(tmp_path / "a"))
    from settings_ui import SettingsAPI
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    ins = api.get_insights()
    assert ins["totals"]["dictations"] == 0 and len(ins["activity"]) == 14
    api._history.record("searchable keyboard text", ts=1.0, duration_s=2.0)
    api._history.record("other entry", ts=2.0)
    ins = api.get_insights()
    assert ins["totals"]["dictations"] == 2
    assert [r["text"] for r in api.history_list(query="keyboard")] == ["searchable keyboard text"]


def test_insights_truncation_flag(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    monkeypatch.setattr(paths, "audio_dir", lambda: str(tmp_path / "a"))
    from settings_ui import SettingsAPI
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    api._history.record("small history", ts=1.0)
    assert api.get_insights()["truncated_from"] is None
    # bulk-load past the cap directly (record() x5001 would be slow-ish)
    with api._history._lock:
        api._history._conn.executemany(
            "INSERT INTO dictations (ts_utc,text,char_count,word_count,model,audio_path,duration_s)"
            " VALUES (?,?,?,?,?,NULL,NULL)",
            [(float(i), f"row {i}", 5, 2, None) for i in range(5100)])
        api._history._conn.commit()
    ins = api.get_insights()
    assert ins["truncated_from"] == 5101
    assert ins["totals"]["dictations"] == 5000


def test_vocab_round_trip(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    monkeypatch.setattr(paths, "audio_dir", lambda: str(tmp_path / "a"))
    from settings_ui import SettingsAPI
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    assert api.vocab_get()["custom"] == [] and api.vocab_get()["auto_enabled"] is True
    assert api.vocab_add("ScratchEdge")["ok"] is True
    assert "error" in api.vocab_add("scratchedge")       # dup
    assert "error" in api.vocab_add("x")                 # too short
    assert api.vocab_get()["custom"] == ["ScratchEdge"]
    assert api.set_value("auto_vocabulary", False)["ok"] is True
    assert api.vocab_get()["auto_enabled"] is False
    assert api.vocab_remove("SCRATCHEDGE")["ok"] is True
    assert api.vocab_get()["custom"] == []


def test_vocab_add_stores_normalized_phrase(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    monkeypatch.setattr(paths, "audio_dir", lambda: str(tmp_path / "a"))
    from settings_ui import SettingsAPI
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    assert api.vocab_add("New   York")["ok"] is True
    assert api.vocab_get()["custom"] == ["New York"]


def test_apply_model_with_language(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.apply_model("auto", "es")["ok"] is True
    cfg = config.load(p)
    assert cfg["model"] == "auto" and cfg["language"] == "es"
    assert "error" in api.apply_model("auto", "klingon")
    assert api.apply_model("small.en")["ok"] is True   # language untouched
    assert config.load(p)["language"] == "es"


def test_get_state_languages(tmp_path):
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    langs = api.get_state()["languages"]
    assert langs[0] == ["auto", "Auto-detect"]
    assert ["es", "Español"] in langs
    assert len(langs) > 50


def test_apply_language_only_leaves_model_untouched(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    api.apply_model("small.en")
    assert api.apply_model(None, "fr")["ok"] is True
    cfg = config.load(p)
    assert cfg["model"] == "small.en" and cfg["language"] == "fr"
    assert "error" in api.apply_model(None, None)  # nothing to apply


def test_settings_process_never_imports_ml_stack():
    # design invariant: the settings process stays lightweight — building the
    # language list must not pull faster_whisper/ctranslate2
    import subprocess
    import sys
    code = (
        "import sys, settings_ui, config; "
        "settings_ui._language_options(); "
        "config.valid_language('es'); "
        "assert 'faster_whisper' not in sys.modules, 'ML stack leaked'; "
        "assert 'ctranslate2' not in sys.modules; "
        "print('lightweight OK')"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, timeout=120,
                         cwd=__import__('os').path.dirname(
                             __import__('os').path.dirname(
                                 __import__('os').path.abspath(__file__))))
    assert "lightweight OK" in out.stdout, out.stderr


def test_snippet_crud(tmp_path):
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    assert api.snippets_get()["snippets"] == {}
    assert api.snippet_save("sig", "Thanks,\nGreg")["ok"] is True
    assert "error" in api.snippet_save("bad name", "x")
    assert api.snippet_save("SIG", "replaced")["ok"] is True   # case-insensitive replace
    assert api.snippets_get()["snippets"] == {"SIG": "replaced"}
    assert api.snippet_delete("sig")["ok"] is True
    assert api.snippets_get()["snippets"] == {}


def test_app_profiles_crud(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    state = api.app_profiles_get()
    assert state["map"] == {}
    assert state["profiles"] == ["code", "casual", "formal", "chat"]

    assert api.app_profile_set(" Notepad.EXE ", "casual")["ok"] is True
    assert config.load(p)["app_profiles"] == {"notepad.exe": "casual"}
    assert api.app_profile_set("title:Gmail", "formal")["ok"] is True
    assert api.app_profiles_get()["map"] == {
        "notepad.exe": "casual",
        "title:gmail": "formal",
    }
    assert "error" in api.app_profile_set("x.exe", "bogus")
    assert api.app_profile_clear("NOTEPAD.exe")["ok"] is True
    assert api.app_profiles_get()["map"] == {"title:gmail": "formal"}


def test_snippet_pack_round_trip(tmp_path, monkeypatch):
    import settings_ui as su
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    api.snippet_save("sig", "Greg")
    pack = tmp_path / "pack.json"

    class StubWin:
        def create_file_dialog(self, kind, **kw):
            return str(pack)
    monkeypatch.setattr(su, "_WINDOW", StubWin())
    assert api.snippets_export()["ok"] is True
    api.snippet_delete("sig")
    api.snippet_save("sig", "different")          # collision on import
    r = api.snippets_import()
    assert r["ok"] is True and r["added"] == 1 and r["renamed"] == 1
    snaps = api.snippets_get()["snippets"]
    assert snaps["sig"] == "different" and snaps["sig-2"] == "Greg"


def test_cleanup_instant_keys(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.set_value("cleanup_enabled", False)["ok"] is True
    assert config.load(p)["cleanup_enabled"] is False
    assert api.set_value("remove_discourse_fillers", True)["ok"] is True
    assert config.load(p)["remove_discourse_fillers"] is True


def test_check_updates_newer_and_current(tmp_path, monkeypatch):
    import io
    import json as _json
    import settings_ui as su

    def fake_urlopen(req, timeout=0):
        return io.BytesIO(_json.dumps([{"name": "v9.9.9"}]).encode())
    monkeypatch.setattr(su.urllib.request, "urlopen", fake_urlopen)
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    r = api.check_updates()
    assert r["ok"] is True and r["newer"] is True and r["latest"] == "9.9.9"

    def fake_same(req, timeout=0):
        import paths
        return io.BytesIO(_json.dumps([{"name": "v" + paths.APP_VERSION}]).encode())
    monkeypatch.setattr(su.urllib.request, "urlopen", fake_same)
    r = api.check_updates()
    assert r["ok"] is True and r["newer"] is False


def test_check_updates_offline_degrades(tmp_path, monkeypatch):
    import settings_ui as su

    def boom(req, timeout=0):
        raise OSError("no network")
    monkeypatch.setattr(su.urllib.request, "urlopen", boom)
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    assert "error" in api.check_updates()


def test_milestone_instant_keys(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.set_value("milestones_enabled", False)["ok"] is True
    assert config.load(p)["milestones_enabled"] is False
    assert api.set_value("milestone_notifications", False)["ok"] is True
    assert config.load(p)["milestone_notifications"] is False




def test_get_insights_includes_all_time_milestones(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    monkeypatch.setattr(paths, "audio_dir", lambda: str(tmp_path / "a"))
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    api._history.record("word " * 1200, ts=1.0)  # 1200 words -> First Roar
    d = api.get_insights()
    assert "milestones" in d
    assert 1000 in [u["threshold"] for u in d["milestones"]["unlocked"]]


def test_diagnostics_report_is_safe(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    monkeypatch.setattr(paths, "audio_dir", lambda: str(tmp_path / "a"))
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    api._history.record("very private words", ts=1.0)
    api.snippet_save("sig", "private signature")
    rep = api.diagnostics_get()["report"]
    assert "version:" in rep and "history_count: 1" in rep
    assert "private" not in rep            # no transcripts, no snippets
    import os
    assert os.path.expanduser("~").lower() not in rep.lower()  # paths redacted


def test_safe_mode_is_reversible(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    r = api.safe_mode()
    assert r["ok"] is True
    assert r["previous"] == {"overlay_enabled": True,
                             "streaming_preview": True,
                             "paste_fallback": False}
    cfg = config.load(p)
    assert cfg["overlay_enabled"] is False
    assert cfg["streaming_preview"] is False
    assert cfg["paste_fallback"] is True


def test_appearance_instant_key_validated(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.set_value("appearance", "system")["ok"] is True
    assert config.load(p)["appearance"] == "system"
    assert "error" in api.set_value("appearance", "rainbow")


def test_snippet_import_reports_clipboard_usage(tmp_path, monkeypatch):
    import json as _json
    import settings_ui as su
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    pack = tmp_path / "pack.json"
    pack.write_text(_json.dumps({"clip": "paste: {clipboard}", "plain": "hi"}))

    class StubWin:
        def create_file_dialog(self, kind, **kw):
            return str(pack)
    monkeypatch.setattr(su, "_WINDOW", StubWin())
    r = api.snippets_import()
    assert r["ok"] is True and r["added"] == 2
    assert r["clipboard_count"] == 1


def test_reset_milestones_bridge(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    monkeypatch.setattr(paths, "audio_dir", lambda: str(tmp_path / "a"))
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    api._history.record_unlock(1000, 1.0)
    api._history.record_unlock(5000, 2.0)
    r = api.reset_milestones()
    assert r["ok"] is True and r["removed"] == 2
    assert api._history.unlocks() == {}


def test_history_clear_keeps_badges(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    monkeypatch.setattr(paths, "audio_dir", lambda: str(tmp_path / "a"))
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    api._history.record("word " * 1000, ts=1.0)
    api._history.record_unlock(1000, 1.0)
    api.history_clear()
    assert api._history.total_words() == 0
    assert api._history.unlocks() == {1000: 1.0}   # sticky by design
