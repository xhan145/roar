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
    assert s["version"] == "0.8.0"


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
