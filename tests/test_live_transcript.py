"""Live transcript view: export bridge + UI presence."""

import pathlib

import paths


def test_history_export_writes_timestamped_file(tmp_path, monkeypatch):
    from settings_ui import SettingsAPI
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path))
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    (tmp_path / "Documents").mkdir()
    api._history.record("alpha one", ts=1.0)
    api._history.record("beta two", ts=2.0)
    out = api.history_export()
    assert out["ok"] is True and out["count"] == 2
    text = pathlib.Path(out["path"]).read_text(encoding="utf-8")
    assert "alpha one" in text and "beta two" in text
    assert text.index("beta two") < text.index("alpha one")  # newest first
    assert text.startswith("[")                              # timestamped


def test_history_export_respects_the_search_filter(tmp_path, monkeypatch):
    from settings_ui import SettingsAPI
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path))
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    (tmp_path / "Documents").mkdir()
    api._history.record("alpha one", ts=1.0)
    api._history.record("beta two", ts=2.0)
    out = api.history_export(query="beta")
    assert out["count"] == 1
    assert "alpha" not in pathlib.Path(out["path"]).read_text(encoding="utf-8")


def test_history_export_empty_is_an_error_not_a_file(tmp_path, monkeypatch):
    from settings_ui import SettingsAPI
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    assert "error" in api.history_export()


def test_live_view_ui_present():
    html = pathlib.Path("settings.html").read_text(encoding="utf-8")
    assert 'id="b-history-live"' in html
    assert 'id="b-history-export"' in html
    assert "history_export" in html
