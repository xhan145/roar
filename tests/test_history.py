import time
import wave

import numpy as np
import pytest

from history import History


@pytest.fixture
def hist(tmp_path):
    h = History(db_path=str(tmp_path / "history.db"),
                audio_dir=str(tmp_path / "audio"))
    yield h
    h.close()


def _tone(seconds=0.5):
    n = int(16000 * seconds)
    return (0.1 * np.sin(np.linspace(0, 100, n))).astype(np.float32)


def test_record_and_list_reverse_chron(hist):
    hist.record("first", model="small.en", ts=100.0)
    hist.record("second and third words", model="small.en", ts=200.0)
    rows = hist.list()
    assert [r["text"] for r in rows] == ["second and third words", "first"]
    assert rows[0]["word_count"] == 4
    assert rows[1]["char_count"] == 5
    assert rows[0]["has_audio"] is False


def test_word_count_handles_whitespace_and_newlines(hist):
    rid = hist.record("hello   world\n\nnew  paragraph", ts=1.0)
    row = [r for r in hist.list() if r["id"] == rid][0]
    assert row["word_count"] == 4


def test_audio_saved_only_when_retained(hist, tmp_path):
    no_audio = hist.record("no keep", audio=_tone(), retention_days=0)
    kept = hist.record("keep me", audio=_tone(), retention_days=7)
    rows = {r["id"]: r for r in hist.list()}
    assert rows[no_audio]["has_audio"] is False
    assert rows[kept]["has_audio"] is True
    path = hist._audio_path_for(kept)
    with wave.open(path) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1


def test_delete_removes_row_and_audio(hist):
    import os
    rid = hist.record("bye", audio=_tone(), retention_days=7)
    path = hist._audio_path_for(rid)
    assert os.path.exists(path)
    hist.delete(rid)
    assert hist.list() == []
    assert not os.path.exists(path)


def test_clear_returns_count_and_empties(hist):
    hist.record("a", ts=1.0)
    hist.record("b", audio=_tone(), retention_days=7, ts=2.0)
    assert hist.clear() == 2
    assert hist.list() == []
    assert hist.stats() == {"count": 0, "audio_count": 0, "audio_bytes": 0}


def test_purge_expired_cutoff(hist):
    now = time.time()
    old = hist.record("old", audio=_tone(), retention_days=7,
                      ts=now - 8 * 86400)
    fresh = hist.record("fresh", audio=_tone(), retention_days=7,
                        ts=now - 1 * 86400)
    removed = hist.purge_expired(7)
    ids = {r["id"] for r in hist.list()}
    assert old in ids and fresh in ids
    assert removed == 1
    assert hist._row(old)["audio_path"] is None
    assert hist._row(fresh)["audio_path"] is not None


def test_retention_zero_nulls_all_audio_keeps_text(hist):
    rid = hist.record("keeptext", audio=_tone(), retention_days=7)
    assert hist.purge_expired(0) == 1
    assert hist._row(rid)["audio_path"] is None
    assert hist.list()[0]["text"] == "keeptext"


def test_stats_math(hist):
    hist.record("x", audio=_tone(), retention_days=7)
    hist.record("y", ts=2.0)
    s = hist.stats()
    assert s["count"] == 2 and s["audio_count"] == 1 and s["audio_bytes"] > 0


def test_corrupt_db_recovers_and_preserves_bad_file(tmp_path):
    import os
    db = tmp_path / "history.db"
    db.write_bytes(b"this is definitely not a sqlite database" * 100)
    h = History(db_path=str(db), audio_dir=str(tmp_path / "audio"))
    rid = h.record("works after recovery", ts=1.0)
    assert h.list()[0]["id"] == rid
    h.close()
    corpses = [f for f in os.listdir(tmp_path) if ".corrupt-" in f]
    assert len(corpses) == 1  # bad file moved aside, not deleted


def test_failed_wav_write_leaves_no_orphan(hist, monkeypatch):
    import os

    def boom(self, rid, audio):
        # simulate a failure AFTER the file was created (partial write)
        open(self._audio_path_for(rid), "wb").close()
        raise OSError("disk full")

    monkeypatch.setattr(History, "_write_wav", boom)
    rid = hist.record("text survives", audio=_tone(), retention_days=7)
    row = hist._row(rid)
    assert row["text"] == "text survives"
    assert row["audio_path"] is None
    assert not os.path.exists(hist._audio_path_for(rid))  # partial cleaned up
