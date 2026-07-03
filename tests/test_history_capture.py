import config
from history import History


def test_defaults_have_history_keys():
    assert config.DEFAULTS["history_enabled"] is True
    assert config.DEFAULTS["audio_retention_days"] == 0


def test_capture_helper_records_when_enabled(tmp_path):
    from app import record_history
    h = History(db_path=str(tmp_path / "h.db"), audio_dir=str(tmp_path / "a"))
    record_history(h, {"history_enabled": True, "audio_retention_days": 0},
                   "hello world", model="small.en", audio=None)
    rows = h.list()
    assert len(rows) == 1 and rows[0]["text"] == "hello world"
    h.close()


def test_capture_helper_skips_when_disabled(tmp_path):
    from app import record_history
    h = History(db_path=str(tmp_path / "h.db"), audio_dir=str(tmp_path / "a"))
    record_history(h, {"history_enabled": False, "audio_retention_days": 0},
                   "nope", model="small.en", audio=None)
    assert h.list() == []
    h.close()


def test_capture_never_raises(tmp_path):
    from app import record_history
    h = History(db_path=str(tmp_path / "h.db"), audio_dir=str(tmp_path / "a"))
    h.close()  # force subsequent use to error
    record_history(h, {"history_enabled": True, "audio_retention_days": 0},
                   "x", model=None, audio=None)
