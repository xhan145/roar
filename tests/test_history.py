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


def test_fresh_db_is_v2_with_duration(hist):
    rid = hist.record("timed words", ts=1.0, duration_s=2.5)
    row = hist._row(rid)
    assert row["duration_s"] == 2.5
    assert hist.list()[0]["duration_s"] == 2.5


def test_v1_db_migrates_in_place(tmp_path):
    import sqlite3
    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE dictations (id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts_utc REAL NOT NULL, text TEXT NOT NULL, char_count INTEGER NOT NULL,
        word_count INTEGER NOT NULL, model TEXT, audio_path TEXT)""")
    conn.execute("INSERT INTO dictations (ts_utc,text,char_count,word_count,model,audio_path)"
                 " VALUES (1.0,'legacy row',10,2,'small.en',NULL)")
    conn.execute("PRAGMA user_version=1")
    conn.commit(); conn.close()
    h = History(db_path=db, audio_dir=str(tmp_path / "a"))
    rows = h.list()
    assert rows[0]["text"] == "legacy row" and rows[0]["duration_s"] is None
    h.record("new row", ts=2.0, duration_s=1.5)
    assert h.list()[0]["duration_s"] == 1.5
    h.close()


def test_search_matches_and_escapes(hist):
    hist.record("hello wonderful world", ts=1.0)
    hist.record("100% sure_thing", ts=2.0)
    hist.record("unrelated", ts=3.0)
    assert [r["text"] for r in hist.list(query="wonderful")] == ["hello wonderful world"]
    assert [r["text"] for r in hist.list(query="100%")] == ["100% sure_thing"]
    assert [r["text"] for r in hist.list(query="e_thing")] == ["100% sure_thing"]
    assert hist.list(query="zzz") == []
    assert len(hist.list(query=None)) == 3


def test_total_words_all_time(tmp_path):
    from history import History
    h = History(db_path=str(tmp_path / "h.db"), audio_dir=str(tmp_path / "a"))
    assert h.total_words() == 0
    h.record("one two three", ts=1.0)      # 3 words
    h.record("four five", ts=2.0)          # 2 words
    assert h.total_words() == 5
    h.close()


def test_badge_unlocks_sticky(tmp_path):
    from history import History
    h = History(db_path=str(tmp_path / "h.db"), audio_dir=str(tmp_path / "a"))
    assert h.unlocks() == {}
    h.record_unlock(1000, 111.0)
    h.record_unlock(1000, 999.0)           # INSERT OR IGNORE — first wins
    h.record_unlock(5000, 222.0)
    assert h.unlocks() == {1000: 111.0, 5000: 222.0}
    h.close()


def test_migration_v2_db_gains_badge_unlocks(tmp_path):
    import sqlite3
    import history as history_mod
    p = str(tmp_path / "old.db")
    con = sqlite3.connect(p)
    con.execute("""CREATE TABLE dictations (id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts_utc REAL NOT NULL, text TEXT NOT NULL, char_count INTEGER NOT NULL,
        word_count INTEGER NOT NULL, model TEXT, audio_path TEXT, duration_s REAL)""")
    con.execute("PRAGMA user_version=2")
    con.commit(); con.close()
    h = history_mod.History(db_path=p, audio_dir=str(tmp_path / "a"))
    assert h.unlocks() == {}                 # table exists, empty
    h.record_unlock(1000, 5.0)
    assert h.unlocks() == {1000: 5.0}
    h.close()


def test_record_checkpoints_wal_into_main_db(tmp_path):
    # durability: after each record the WAL is folded into the main file, so a
    # force-kill (which can lose the -wal sidecar) never strands a dictation
    from history import History
    p = tmp_path / "h.db"
    h = History(db_path=str(p), audio_dir=str(tmp_path / "a"))
    h.record("durable row", ts=1.0)
    wal = tmp_path / "h.db-wal"
    assert (not wal.exists()) or wal.stat().st_size == 0
    h.close()


def test_close_truncates_wal_and_data_survives(tmp_path):
    from history import History
    p = tmp_path / "h.db"
    h = History(db_path=str(p), audio_dir=str(tmp_path / "a"))
    h.record("row a", ts=1.0)     # 2 words
    h.record("row b two", ts=2.0)  # 3 words
    h.close()
    wal = tmp_path / "h.db-wal"
    assert (not wal.exists()) or wal.stat().st_size == 0
    h2 = History(db_path=str(p), audio_dir=str(tmp_path / "a"))
    assert h2.total_words() == 5
    h2.close()
