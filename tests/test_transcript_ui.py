"""Standalone transcript window: bridge filtering, export, ML-free imports."""

import pathlib
import sys

import paths


def _api(tmp_path, monkeypatch, history_enabled=True):
    import config as config_mod
    import history as history_mod
    from transcript_ui import TranscriptAPI
    monkeypatch.setattr(paths, "history_db_path",
                        lambda: str(tmp_path / "h.db"))
    cfg_path = str(tmp_path / "config.json")
    cfg = config_mod.load(cfg_path)
    cfg["history_enabled"] = history_enabled
    config_mod.save(cfg, cfg_path)
    # Seed through the real WRITER (the tray's class); the API under test is
    # read-only by design and owns no write path at all.
    writer = history_mod.History()
    writer.record("typed one", ts=1.0)
    writer.record("captured lecture", ts=2.0, model="listen")
    writer.record("typed two", ts=3.0)
    return TranscriptAPI(config_path=cfg_path)


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


# -- review findings: the window must be PHYSICALLY read-only ----------------

def test_transcript_api_never_writes_or_backs_up(tmp_path, monkeypatch):
    """Polling must not create backups, journals, or any new file — the old
    implementation ran History()'s rolling backup every 1.5 s."""
    import os

    api = _api(tmp_path, monkeypatch)
    db = tmp_path / "h.db"
    before_bytes = db.read_bytes()
    before_files = set(os.listdir(tmp_path)) | {
        f for d in os.listdir(tmp_path)
        if (tmp_path / d).is_dir()
        for f in os.listdir(tmp_path / d)}
    for _ in range(10):
        api.transcript_list("all")
        api.transcript_list("capture", query="lecture")
    after_files = set(os.listdir(tmp_path)) | {
        f for d in os.listdir(tmp_path)
        if (tmp_path / d).is_dir()
        for f in os.listdir(tmp_path / d)}
    assert after_files == before_files          # no backups/, no new journals
    assert db.read_bytes() == before_bytes      # not a single byte written


def test_transcript_source_is_readonly_by_construction():
    src = pathlib.Path("transcript_ui.py").read_text(encoding="utf-8")
    assert "mode=ro" in src                     # SQLite read-only URI
    assert "import history" not in src          # never the writing class
    for verb in ("INSERT ", "UPDATE ", "DELETE FROM", "CREATE TABLE",
                 ".backup("):
        assert verb not in src, verb


def test_missing_db_yields_empty_not_created(tmp_path, monkeypatch):
    import config as config_mod
    from transcript_ui import TranscriptAPI
    monkeypatch.setattr(paths, "history_db_path",
                        lambda: str(tmp_path / "absent.db"))
    cfg_path = str(tmp_path / "config.json")
    config_mod.load(cfg_path)
    api = TranscriptAPI(config_path=cfg_path)
    assert api.transcript_list("all")["rows"] == []
    assert not (tmp_path / "absent.db").exists()   # read-only: nothing created
