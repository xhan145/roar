"""Standalone transcript window: bridge filtering, export, ML-free imports."""

import pathlib
import sys

import paths


def _api(tmp_path, monkeypatch, history_enabled=True):
    import config as config_mod
    from transcript_ui import TranscriptAPI
    monkeypatch.setattr(paths, "history_db_path",
                        lambda: str(tmp_path / "h.db"))
    cfg_path = str(tmp_path / "config.json")
    cfg = config_mod.load(cfg_path)
    cfg["history_enabled"] = history_enabled
    config_mod.save(cfg, cfg_path)
    api = TranscriptAPI(config_path=cfg_path)
    api._history.record("typed one", ts=1.0)
    api._history.record("captured lecture", ts=2.0, model="listen")
    api._history.record("typed two", ts=3.0)
    return api


def test_list_all_interleaves_and_tags_sources(tmp_path, monkeypatch):
    rows = _api(tmp_path, monkeypatch).transcript_list("all")["rows"]
    assert [r["text"] for r in rows] == ["typed two", "captured lecture",
                                         "typed one"]
    assert [r["capture"] for r in rows] == [False, True, False]


def test_list_filters_by_source(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    assert [r["text"] for r in api.transcript_list("capture")["rows"]] == \
        ["captured lecture"]
    assert [r["text"] for r in api.transcript_list("dictation")["rows"]] == \
        ["typed two", "typed one"]


def test_list_search_applies_before_source_filter(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    rows = api.transcript_list("all", query="lecture")["rows"]
    assert [r["text"] for r in rows] == ["captured lecture"]


def test_state_reports_history_toggle(tmp_path, monkeypatch):
    assert _api(tmp_path, monkeypatch).state()["history_enabled"] is True
    assert _api(tmp_path, monkeypatch,
                history_enabled=False).state()["history_enabled"] is False


def test_export_tags_capture_lines(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path))
    (tmp_path / "Documents").mkdir()
    out = api.transcript_export("all")
    assert out["ok"] is True and out["count"] == 3
    text = pathlib.Path(out["path"]).read_text(encoding="utf-8")
    assert "[capture] captured lecture" in text
    assert "typed one" in text


def test_export_empty_is_an_error(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    assert "error" in api.transcript_export("all", query="zzz-no-match")


def test_transcript_process_never_imports_the_ml_stack():
    """The window must open instantly: importing transcript_ui may not drag in
    torch/faster_whisper/ctranslate2 (same discipline as the settings process)."""
    banned = {"torch", "faster_whisper", "ctranslate2", "kokoro"}
    already = banned & set(sys.modules)
    src = pathlib.Path("transcript_ui.py").read_text(encoding="utf-8")
    for mod in ("transcriber", "recorder", "hardware_accel", "torch",
                "faster_whisper"):
        assert f"import {mod}" not in src, mod
    import transcript_ui  # noqa: F401 — the import IS the test
    assert (banned & set(sys.modules)) == already


def test_listen_tag_stays_in_sync_with_listen_mode():
    import listen_mode
    import transcript_ui
    assert transcript_ui.LISTEN_TAG == listen_mode.MODEL_TAG
