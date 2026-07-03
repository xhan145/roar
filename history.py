"""Local dictation history: SQLite rows + optional retained audio WAVs."""
import os
import threading
import time
import wave

import numpy as np

import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS dictations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc      REAL    NOT NULL,
    text        TEXT    NOT NULL,
    char_count  INTEGER NOT NULL,
    word_count  INTEGER NOT NULL,
    model       TEXT,
    audio_path  TEXT
);
CREATE INDEX IF NOT EXISTS idx_dictations_ts ON dictations(ts_utc);
"""


class History:
    def __init__(self, db_path=None, audio_dir=None):
        import sqlite3
        self._sqlite = sqlite3
        self.db_path = db_path or paths.history_db_path()
        self._audio_dir = audio_dir  # None => resolve paths.audio_dir() lazily
        self._lock = threading.Lock()
        self._conn = self._open()

    def _open(self):
        try:
            conn = self._sqlite.connect(self.db_path, check_same_thread=False)
            conn.row_factory = self._sqlite.Row
            conn.executescript(SCHEMA)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA user_version=1")
            conn.commit()
            return conn
        except self._sqlite.DatabaseError:
            # corrupt file: move aside and recreate
            if os.path.exists(self.db_path):
                os.replace(self.db_path,
                           self.db_path + f".corrupt-{int(time.time())}")
            conn = self._sqlite.connect(self.db_path, check_same_thread=False)
            conn.row_factory = self._sqlite.Row
            conn.executescript(SCHEMA)
            conn.commit()
            return conn

    def _dir(self):
        if self._audio_dir is not None:
            os.makedirs(self._audio_dir, exist_ok=True)
            return self._audio_dir
        return paths.audio_dir()

    def _audio_path_for(self, rid):
        return os.path.join(self._dir(), f"{rid}.wav")

    def _write_wav(self, rid, audio):
        path = self._audio_path_for(rid)
        pcm = np.clip(audio, -1.0, 1.0)
        pcm = (pcm * 32767).astype("<i2")
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm.tobytes())
        return path

    def record(self, text, model=None, audio=None, retention_days=0, ts=None):
        ts = time.time() if ts is None else ts
        words = len(text.split())
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO dictations (ts_utc, text, char_count, word_count, model, audio_path)"
                " VALUES (?, ?, ?, ?, ?, NULL)",
                (ts, text, len(text), words, model))
            rid = cur.lastrowid
            self._conn.commit()
        if audio is not None and retention_days > 0:
            try:
                path = self._write_wav(rid, audio)
                with self._lock:
                    self._conn.execute(
                        "UPDATE dictations SET audio_path=? WHERE id=?",
                        (path, rid))
                    self._conn.commit()
            except OSError as e:
                print(f"FlowLocal: could not save audio for {rid}: {e}",
                      flush=True)
        return rid

    def _row(self, rid):
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM dictations WHERE id=?", (rid,)).fetchone()
        return dict(r) if r else None

    def list(self, limit=100, offset=0):
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, ts_utc, text, char_count, word_count, model, audio_path"
                " FROM dictations ORDER BY ts_utc DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["has_audio"] = bool(d.pop("audio_path"))
            out.append(d)
        return out

    def _delete_audio(self, path):
        if path:
            try:
                os.remove(path)
            except OSError:
                pass

    def delete(self, rid):
        with self._lock:
            r = self._conn.execute(
                "SELECT audio_path FROM dictations WHERE id=?", (rid,)).fetchone()
            if r is None:
                return
            self._conn.execute("DELETE FROM dictations WHERE id=?", (rid,))
            self._conn.commit()
        self._delete_audio(r["audio_path"])

    def clear(self):
        with self._lock:
            audio_paths = [row["audio_path"] for row in self._conn.execute(
                "SELECT audio_path FROM dictations").fetchall()]
            n = self._conn.execute(
                "SELECT COUNT(*) FROM dictations").fetchone()[0]
            self._conn.execute("DELETE FROM dictations")
            self._conn.commit()
        for p in audio_paths:
            self._delete_audio(p)
        return n

    def stats(self):
        with self._lock:
            count = self._conn.execute(
                "SELECT COUNT(*) FROM dictations").fetchone()[0]
            audio_paths = [row["audio_path"] for row in self._conn.execute(
                "SELECT audio_path FROM dictations WHERE audio_path IS NOT NULL").fetchall()]
        total = 0
        live = 0
        for p in audio_paths:
            try:
                total += os.path.getsize(p)
                live += 1
            except OSError:
                pass
        return {"count": count, "audio_count": live, "audio_bytes": total}

    def purge_expired(self, retention_days):
        """Drop audio older than the window (retention 0 => drop ALL audio).
        Transcript rows are always kept."""
        with self._lock:
            if retention_days <= 0:
                rows = self._conn.execute(
                    "SELECT id, audio_path FROM dictations WHERE audio_path IS NOT NULL").fetchall()
            else:
                cutoff = time.time() - retention_days * 86400
                rows = self._conn.execute(
                    "SELECT id, audio_path FROM dictations"
                    " WHERE audio_path IS NOT NULL AND ts_utc < ?",
                    (cutoff,)).fetchall()
            ids = [r["id"] for r in rows]
            if ids:
                self._conn.executemany(
                    "UPDATE dictations SET audio_path=NULL WHERE id=?",
                    [(i,) for i in ids])
                self._conn.commit()
        for r in rows:
            self._delete_audio(r["audio_path"])
        return len(rows)

    def close(self):
        with self._lock:
            self._conn.close()
