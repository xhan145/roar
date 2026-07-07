import json

import status


def test_only_allowlisted_keys_persist(tmp_path):
    p = str(tmp_path / "status.json")
    assert status.write_status(p, state="recording", session_word_count=12,
                               transcript="SECRET", clipboard="PW",
                               window_title="banking") is True
    data = json.loads(open(p, encoding="utf-8").read())
    assert data["state"] == "recording"
    assert data["session_word_count"] == 12
    assert "updated_at" in data
    for leaked in ("transcript", "clipboard", "window_title"):
        assert leaked not in data
    assert "SECRET" not in json.dumps(data)


def test_read_missing_or_corrupt_is_empty(tmp_path):
    assert status.read_status(str(tmp_path / "nope.json")) == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert status.read_status(str(bad)) == {}


def test_write_merges_and_is_atomic(tmp_path):
    p = str(tmp_path / "status.json")
    status.write_status(p, state="idle", session_started_at=100.0)
    status.write_status(p, state="recording")   # merge, keep session_started_at
    data = status.read_status(p)
    assert data["state"] == "recording"
    assert data["session_started_at"] == 100.0
    # no leftover temp file
    assert not (tmp_path / "status.json.tmp").exists()


def test_write_never_raises_on_bad_path():
    # a path whose parent dir does not exist -> False, no exception
    assert status.write_status("/no/such/dir/status.json", state="idle") is False
