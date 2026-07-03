# FlowLocal History + Privacy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Local dictation history (SQLite) with opt-in audio retention, exposed through functional Privacy + History tabs in the settings window.

**Architecture:** New `history.py` owns a SQLite DB + WAV files under `%LOCALAPPDATA%\FlowLocal`. The tray app records after each injection and purges on a throttled sweep; the settings process reads/deletes via new bridge methods and renders the two tabs. Ships as v0.3.0 with exe + MSI rebuild and an adversarial review before push.

**Tech Stack:** Python stdlib `sqlite3` + `wave` (zero new deps), existing pywebview settings UI, PyInstaller, WiX.

## Global Constraints

- Project `C:\Users\xhan1\flowlocal`, branch `main`, venv `venv/Scripts/python.exe`. Run pytest from the project root. Kill FlowLocal.exe before test runs (mutex + hooks).
- Spec: `docs/superpowers/specs/2026-07-02-history-privacy-design.md`.
- New config keys (config.py DEFAULTS): `"history_enabled": true`, `"audio_retention_days": 0`. Retention allowed set: `{0, 1, 7, 30, 90}`.
- Retention 0 = delete audio immediately after transcription AND sweep existing clips; transcripts are always kept regardless of retention.
- Version bump: `paths.APP_VERSION = "0.3.0"`; MSI + tag follow.
- History/audio live in `%LOCALAPPDATA%\FlowLocal` — user data, NOT removed by MSI uninstall.
- Recording must be failure-isolated: a DB/disk error can never break dictation.
- Commit per task. Push + tag at the end; fix any push errors.

---

### Task 1: history.py — SQLite store + audio files

**Files:** Create `history.py`, `tests/test_history.py`; Modify `paths.py` (`history_db_path()`, `audio_dir()`)

**Interfaces:**
- `paths.history_db_path() -> str`, `paths.audio_dir() -> str` (frozen-aware, under the FlowLocal data dir; audio_dir created on demand).
- `class History(db_path=None)`:
  - `record(text, model=None, audio=None, retention_days=0, ts=None) -> int`
  - `list(limit=100, offset=0) -> list[dict]` (keys: id, ts_utc, text, char_count, word_count, model, has_audio)
  - `delete(id) -> None`
  - `clear() -> int`
  - `stats() -> dict` (keys: count, audio_count, audio_bytes)
  - `purge_expired(retention_days) -> int`
  - `close()`
- `audio` is a float32 mono 16 kHz numpy array (or None).

- [ ] **Step 1: Write the failing test** `tests/test_history.py`:

```python
import time
import wave

import numpy as np
import pytest

from history import History


@pytest.fixture
def hist(tmp_path):
    h = History(db_path=str(tmp_path / "history.db"))
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
    # the kept WAV is real 16 kHz mono
    path = hist._audio_path_for(kept)
    with wave.open(path) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1


def test_delete_removes_row_and_audio(hist):
    rid = hist.record("bye", audio=_tone(), retention_days=7)
    path = hist._audio_path_for(rid)
    import os
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
    # transcripts are always kept; purge only drops expired AUDIO
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
```

- [ ] **Step 2: Run → fail** `venv/Scripts/python.exe -m pytest tests/test_history.py -q` → ModuleNotFoundError.

- [ ] **Step 3: Implement.** Add to `paths.py`:

```python
def history_db_path() -> str:
    return os.path.join(_data_dir(), "history.db")


def audio_dir() -> str:
    return _ensure(os.path.join(_data_dir(), "audio"))
```

and a `_data_dir()` helper (frozen → `%LOCALAPPDATA%\FlowLocal`; source → project root), reusing the existing frozen/source split already used by `log_path`/`models_dir`:

```python
def _data_dir() -> str:
    if is_frozen():
        return _ensure(os.path.join(os.environ["LOCALAPPDATA"], APP_NAME))
    return _source_root()
```

Create `history.py`:

```python
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
    def __init__(self, db_path=None):
        import sqlite3
        self._sqlite = sqlite3
        self.db_path = db_path or paths.history_db_path()
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
                os.replace(self.db_path, self.db_path + f".corrupt-{int(time.time())}")
            conn = self._sqlite.connect(self.db_path, check_same_thread=False)
            conn.row_factory = self._sqlite.Row
            conn.executescript(SCHEMA)
            conn.commit()
            return conn

    def _audio_path_for(self, rid):
        return os.path.join(paths.audio_dir(), f"{rid}.wav")

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
                        "UPDATE dictations SET audio_path=? WHERE id=?", (path, rid))
                    self._conn.commit()
            except OSError as e:
                print(f"FlowLocal: could not save audio for {rid}: {e}", flush=True)
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
            paths_ = [row["audio_path"] for row in self._conn.execute(
                "SELECT audio_path FROM dictations").fetchall()]
            n = self._conn.execute("SELECT COUNT(*) FROM dictations").fetchone()[0]
            self._conn.execute("DELETE FROM dictations")
            self._conn.commit()
        for p in paths_:
            self._delete_audio(p)
        return n

    def stats(self):
        with self._lock:
            count = self._conn.execute("SELECT COUNT(*) FROM dictations").fetchone()[0]
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
                    " WHERE audio_path IS NOT NULL AND ts_utc < ?", (cutoff,)).fetchall()
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
```

- [ ] **Step 4: Run → pass** (8 tests).
- [ ] **Step 5: Commit** `git add history.py tests/test_history.py paths.py && git commit -m "feat: SQLite dictation history store with audio retention"`

---

### Task 2: config keys + capture wiring + purge sweep

**Files:** Modify `config.py` (DEFAULTS), `app.py`; Test: `tests/test_history_capture.py`

**Interfaces:**
- Consumes `History` from Task 1.
- `FlowLocalApp` gains `self.history` (created in `__init__`, closed in `_quit`); `_handle_transcription` records after inject; `_watch_config` calls `purge_expired` on first tick + hourly.

- [ ] **Step 1: Write the failing test** `tests/test_history_capture.py`:

```python
import config
from history import History


def test_defaults_have_history_keys():
    assert config.DEFAULTS["history_enabled"] is True
    assert config.DEFAULTS["audio_retention_days"] == 0


def test_capture_helper_records_when_enabled(tmp_path):
    # _record_history is a thin, testable wrapper extracted from the app
    from app import record_history
    h = History(db_path=str(tmp_path / "h.db"))
    record_history(h, {"history_enabled": True, "audio_retention_days": 0},
                   "hello world", model="small.en", audio=None)
    rows = h.list()
    assert len(rows) == 1 and rows[0]["text"] == "hello world"
    h.close()


def test_capture_helper_skips_when_disabled(tmp_path):
    from app import record_history
    h = History(db_path=str(tmp_path / "h.db"))
    record_history(h, {"history_enabled": False, "audio_retention_days": 0},
                   "nope", model="small.en", audio=None)
    assert h.list() == []
    h.close()


def test_capture_never_raises(tmp_path):
    from app import record_history
    h = History(db_path=str(tmp_path / "h.db"))
    h.close()  # force subsequent use to error
    # must swallow, not raise
    record_history(h, {"history_enabled": True, "audio_retention_days": 0},
                   "x", model=None, audio=None)
```

- [ ] **Step 2: Run → fail** (no `record_history`, keys missing).

- [ ] **Step 3: Implement.** In `config.py` DEFAULTS add:

```python
    "history_enabled": True,
    "audio_retention_days": 0,
```

In `app.py`, add `import history as history_mod` and a module-level helper:

```python
def record_history(hist, cfg, text, model=None, audio=None):
    """Failure-isolated history write — never breaks dictation."""
    if not cfg.get("history_enabled", True):
        return
    try:
        retention = cfg.get("audio_retention_days", 0)
        hist.record(text, model=model,
                    audio=(audio if retention > 0 else None),
                    retention_days=retention)
    except Exception as e:
        print(f"FlowLocal: history write failed: {e}", flush=True)
```

In `FlowLocalApp.__init__`, after `self.recorder = ...`:

```python
        self.history = history_mod.History()
```

In `_handle_transcription`, after `injector.inject_text(...)` and the log line, pass the audio through (the method already has `audio` as its parameter):

```python
        record_history(self.history, self.cfg, text,
                       model=self.transcriber.active_model, audio=audio)
```

In `_watch_config`, add a purge throttle. In `__init__` add `self._purge_ticks = 0`, and in `_watch_config`'s loop body (before `self._stop_watch.wait(2.0)`):

```python
            self._purge_ticks += 1
            if self._purge_ticks == 1 or self._purge_ticks % 1800 == 0:  # first + ~hourly
                try:
                    self.history.purge_expired(self.cfg.get("audio_retention_days", 0))
                except Exception as e:
                    self.log(f"purge failed: {e}")
```

In `_quit`, before `self.icon.stop()`:

```python
        try:
            self.history.close()
        except Exception:
            pass
```

- [ ] **Step 4: Run → pass** (4). Then full suite green.
- [ ] **Step 5: Commit** `git add config.py app.py tests/test_history_capture.py && git commit -m "feat: record dictations to history + hourly audio purge"`

---

### Task 3: settings bridge — history/privacy methods

**Files:** Modify `settings_ui.py`; Test: `tests/test_settings_bridge.py` (additions)

**Interfaces:**
- `SettingsAPI` gains `self._history` (lazy `History` on the settings connection) and: `history_list(limit=100)`, `history_delete(id)`, `history_clear()`, `privacy_stats()`.
- `INSTANT_KEYS` += `history_enabled`, `audio_retention_days`; `set_value` validates retention ∈ {0,1,7,30,90} and, when set, calls `purge_expired` immediately.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_settings_bridge.py`):

```python
def test_retention_validation_and_immediate_purge(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    monkeypatch.setattr(paths, "audio_dir", lambda: str(tmp_path))
    from settings_ui import SettingsAPI
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    assert api.set_value("audio_retention_days", 7)["ok"] is True
    assert "error" in api.set_value("audio_retention_days", 3)  # not in allowed set
    assert api.set_value("history_enabled", False)["ok"] is True


def test_history_list_delete_clear(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    monkeypatch.setattr(paths, "audio_dir", lambda: str(tmp_path))
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
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement.** In `settings_ui.py`:

```python
RETENTION_CHOICES = {0, 1, 7, 30, 90}
```

Extend `INSTANT_KEYS`:

```python
INSTANT_KEYS = {"tones_enabled", "paste_fallback", "silence_rms_threshold",
                "input_device", "history_enabled", "audio_retention_days"}
```

Add a lazy history accessor + methods to `SettingsAPI`:

```python
    @property
    def _history(self):
        if getattr(self, "_hist", None) is None:
            import history as history_mod
            self._hist = history_mod.History()
        return self._hist

    def history_list(self, limit=100):
        return self._history.list(limit=limit)

    def history_delete(self, rid):
        self._history.delete(int(rid))
        return {"ok": True}

    def history_clear(self):
        return {"ok": True, "removed": self._history.clear()}

    def privacy_stats(self):
        s = self._history.stats()
        return {"count": s["count"], "audio_count": s["audio_count"],
                "audio_mb": round(s["audio_bytes"] / (1024 * 1024), 1)}
```

In `set_value`, after the existing sensitivity branch, add retention validation + immediate purge:

```python
        if key == "audio_retention_days":
            try:
                value = int(value)
            except (TypeError, ValueError):
                return {"error": "retention must be a number"}
            if value not in RETENTION_CHOICES:
                return {"error": "retention must be one of 0, 1, 7, 30, 90 days"}
        if key == "history_enabled":
            value = bool(value)
```

and after the `self._write(**{key: value})` line, if the key is retention, purge now:

```python
        if key == "audio_retention_days":
            try:
                self._history.purge_expired(value)
            except Exception:
                pass
```

- [ ] **Step 4: Run → pass**; full bridge suite green.
- [ ] **Step 5: Commit** `git add settings_ui.py tests/test_settings_bridge.py && git commit -m "feat: history/privacy bridge methods + retention validation"`

---

### Task 4: settings.html — History + Privacy tabs

**Files:** Modify `settings.html`; Modify `tests/test_settings_smoke.py` (probe the new controls)

**Interfaces:** Consumes bridge methods from Task 3. Replaces the two `.locked` placeholder panels.

- [ ] **Step 1:** Replace the Privacy and History `<section>` bodies. History section:

```html
    <section id="history">
      <h1>History</h1>
      <div id="history-list"></div>
      <div class="msg" id="m-history"></div>
      <button class="btn" id="b-clear-all" style="margin-top:6px;">Clear all history</button>
    </section>
```

Privacy section:

```html
    <section id="privacy">
      <h1>Privacy</h1>
      <div class="row flex">
        <div>Save dictation history<div class="hint">Store transcripts locally so you can review and reuse them</div></div>
        <button class="toggle" id="t-history" aria-pressed="true" aria-label="Save dictation history"></button>
      </div>
      <div class="row">
        <div style="margin-bottom:8px;">Keep audio recordings</div>
        <select id="s-retention" aria-label="Audio retention">
          <option value="0">Off — delete right after transcription</option>
          <option value="1">1 day</option>
          <option value="7">7 days</option>
          <option value="30">30 days</option>
          <option value="90">90 days</option>
        </select>
        <div class="hint" style="margin-top:6px;">Off deletes audio the moment it's transcribed. Transcripts are always kept unless you turn off history.</div>
      </div>
      <div class="row"><div class="kv" id="privacy-stats">…</div></div>
      <button class="btn" id="b-delete-all" style="border-color:#F87171;color:#FCA5A5;">Delete all history &amp; audio</button>
      <div class="msg" id="m-privacy"></div>
    </section>
```

Add to the init flow (`init()` after existing wiring): set `t-history` from `state.config.history_enabled`, `s-retention` from `state.config.audio_retention_days`, and call `renderHistory()` + `refreshStats()`. Add JS (uses `textContent` only — injection-safe; two-step confirm pattern reused from SP1):

```html
<script>
function relTime(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + "m ago";
  if (s < 86400) return Math.floor(s / 3600) + "h ago";
  return Math.floor(s / 86400) + "d ago";
}
async function renderHistory() {
  const rows = await api().history_list(100);
  const box = document.getElementById("history-list");
  box.innerHTML = "";
  if (!rows.length) {
    const e = document.createElement("div");
    e.className = "row locked";
    e.textContent = "No dictations yet — hold your hotkey and speak.";
    box.appendChild(e); return;
  }
  rows.forEach(r => {
    const card = document.createElement("div"); card.className = "row";
    const meta = document.createElement("div"); meta.className = "hint";
    meta.textContent = relTime(r.ts_utc) + " · " + r.word_count + " words" + (r.has_audio ? " · 🔊" : "");
    const txt = document.createElement("div");
    txt.style.cssText = "display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin:4px 0;";
    txt.textContent = r.text;
    const actions = document.createElement("div"); actions.style.cssText = "display:flex;gap:8px;";
    const copy = document.createElement("button"); copy.className = "btn"; copy.textContent = "Copy";
    copy.onclick = () => navigator.clipboard.writeText(r.text);
    const del = document.createElement("button"); del.className = "btn"; del.textContent = "Delete";
    del.onclick = async () => { await api().history_delete(r.id); renderHistory(); refreshStats(); };
    actions.appendChild(copy); actions.appendChild(del);
    card.appendChild(meta); card.appendChild(txt); card.appendChild(actions);
    box.appendChild(card);
  });
}
async function refreshStats() {
  const s = await api().privacy_stats();
  document.getElementById("privacy-stats").textContent =
    s.count + " dictations · " + s.audio_count + " audio clips · " + s.audio_mb + " MB";
}
function twoStep(btn, action) {
  if (btn.dataset.armed === "1") { btn.dataset.armed = "0"; btn.textContent = btn.dataset.label; action(); return; }
  btn.dataset.label = btn.textContent; btn.dataset.armed = "1"; btn.textContent = "Click again to confirm";
  setTimeout(() => { if (btn.dataset.armed === "1") { btn.dataset.armed = "0"; btn.textContent = btn.dataset.label; } }, 4000);
}
window.addEventListener("pywebviewready", () => {
  document.getElementById("t-history").addEventListener("click", async e => {
    const want = e.target.getAttribute("aria-pressed") !== "true";
    const r = await api().set_value("history_enabled", want);
    if (r.ok) e.target.setAttribute("aria-pressed", want ? "true" : "false");
    else document.getElementById("m-privacy").textContent = r.error;
  });
  document.getElementById("s-retention").addEventListener("change", async e => {
    const r = await api().set_value("audio_retention_days", parseInt(e.target.value, 10));
    const m = document.getElementById("m-privacy");
    m.className = "msg " + (r.ok ? "ok" : "err");
    m.textContent = r.ok ? "Saved" : r.error;
    refreshStats();
  });
  document.getElementById("b-clear-all").addEventListener("click", e =>
    twoStep(e.target, async () => { await api().history_clear(); renderHistory(); refreshStats(); }));
  document.getElementById("b-delete-all").addEventListener("click", e =>
    twoStep(e.target, async () => { await api().history_clear(); renderHistory(); refreshStats();
      document.getElementById("m-privacy").className = "msg ok";
      document.getElementById("m-privacy").textContent = "All history and audio deleted"; }));
});
</script>
```

Wire the two `init()` reads (`t-history`, `s-retention`) inside the existing `init()` after the device list block:

```javascript
  setToggle($("t-history"), c.history_enabled);
  $("s-retention").value = String(c.audio_retention_days);
  renderHistory();
  refreshStats();
```

- [ ] **Step 2:** Update the settings smoke probe. In `settings_ui.py` `probe_and_close`, also read the retention control presence:

```python
                    has_priv = window.evaluate_js(
                        "document.getElementById('s-retention') ? 1 : 0")
                    print(f"FlowLocal: settings probe navs={navs} version={ver} priv={has_priv}",
                          flush=True)
```
In `tests/test_settings_smoke.py`, assert on the parts that are true NOW (APP_VERSION is still 0.2.0 this task — Task 5 bumps it and updates this line):

```python
    assert "navs=7" in out and "priv=1" in out
    assert "FlowLocal: settings window ready" in out
```
(Replace the prior exact `navs=7 version=0.2.0` assertion with these two substring checks so the test is version-agnostic; Task 5 re-tightens to the exact 0.3.0 line.)

- [ ] **Step 3:** Manual check: `venv/Scripts/python.exe app.py --settings` → History empty state + Privacy controls render, toggling retention persists to config.json.
- [ ] **Step 4:** Full suite green.
- [ ] **Step 5:** Commit `git add settings.html settings_ui.py tests/test_settings_smoke.py && git commit -m "feat: functional History + Privacy tabs"`

---

### Task 5: version bump + exe rebuild

**Files:** Modify `paths.py` (`APP_VERSION = "0.3.0"`), `installer/flowlocal.wxs` is version-templated already.

- [ ] **Step 1:** Set `APP_VERSION = "0.3.0"` in `paths.py`. Update any `version=="0.2.0"` assertion in `tests/test_settings_bridge.py`/`test_settings_smoke.py` to `0.3.0`.
- [ ] **Step 2:** Full suite green (all version assertions now 0.3.0).
- [ ] **Step 3:** Kill FlowLocal.exe; `venv/Scripts/python.exe -m PyInstaller flowlocal.spec --noconfirm`. (No spec change: history/paths are pure stdlib, already collected via the app import graph.)
- [ ] **Step 4:** Frozen settings smoke: `dist/FlowLocal/FlowLocal.exe --settings --smoke` then assert the probe line (navs=7 version=0.3.0 priv=1) in `%LOCALAPPDATA%\FlowLocal\flowlocal.log`.
- [ ] **Step 5:** Commit `git add paths.py tests/ && git commit -m "build: bump to v0.3.0, rebuild exe with history UI"`

---

### Task 6: MSI rebuild + live verification

**Files:** none (build only).

- [ ] **Step 1:** `bash scripts/build_msi.sh` → `built dist/FlowLocal-0.3.0.msi` (version now flows from APP_VERSION).
- [ ] **Step 2:** Install: `msiexec //i "dist\\FlowLocal-0.3.0.msi" //qn`; confirm `%LOCALAPPDATA%\Programs\FlowLocal\FlowLocal.exe` exists.
- [ ] **Step 3:** Live capture test against the installed app: start it, drive a synthetic PTT with SAPI speech into Notepad (reuse the SP1 e2e harness), confirm the log shows an injection, then open `--settings --smoke` and confirm the History tab now has ≥1 row (query via a short script opening `History(db_path=<installed data dir>/history.db).list()`).
- [ ] **Step 4:** Uninstall: `msiexec //x "dist\\FlowLocal-0.3.0.msi" //qn`; confirm the install dir is gone AND `%LOCALAPPDATA%\FlowLocal\history.db` REMAINS (user data preserved).
- [ ] **Step 5:** Commit (empty if nothing changed) `git commit --allow-empty -m "build: FlowLocal-0.3.0.msi verified (install/capture/uninstall)"`

---

### Task 7: docs, adversarial review, push, tag, relaunch

- [ ] **Step 1:** README: History/Privacy under Settings; note that history.db + audio live in `%LOCALAPPDATA%\FlowLocal` and survive uninstall; bump test count.
- [ ] **Step 2:** Adversarial review workflow over the new diff (history.py thread-safety across processes, purge cutoff correctness, retention-0 semantics, WAV int16 conversion, bridge validation, HTML injection-safety, uninstall-preserves-data). Fix confirmed findings; re-verify. **Before `git add -A`, run `git status` and exclude any review-agent scratch files** (this bit us on v0.1.1 and v0.2.0).
- [ ] **Step 3:** Full suite green ×2 (exit codes checked).
- [ ] **Step 4:** Commit; `git push origin main` (diagnose+fix on failure); `git commit --allow-empty -m "flowlocal v0.3.0 — dictation history + privacy controls, verified"`; tag `v0.3.0`; `git push origin main --tags`.
- [ ] **Step 5:** Relaunch `dist/FlowLocal/FlowLocal.exe` for the user.
