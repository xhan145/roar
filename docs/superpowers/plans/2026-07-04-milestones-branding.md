# Private Word Milestones + ROAR Branding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Local-only word-count milestone badges + the lavender ROAR logo as the settings/about brand asset, shipping as v0.13.0.

**Architecture:** Pure `milestones.py` maps an all-time word total to badge progress; `history.py` gains a `badge_unlocks` table (migration v2→3) and an all-time word sum; `insights` exposes a milestones block; `app.py` detects and tray-notifies crossings after each dictation. Additive only — no existing behavior changes.

**Tech Stack:** Python 3.14 (`venv/Scripts/python.exe`), sqlite3, Pillow (already a build dep for the icon), pytest; PyInstaller/WiX/7zSD release train.

## Global Constraints

- Version bumps to `0.13.0` (`paths.APP_VERSION`).
- 100% local: no cloud, telemetry, account, leaderboards, sharing, or public badges. Milestone data lives only in the local history DB.
- Preserve dictation, streaming preview, history, insights, vocabulary, snippets, cleanup, multilingual, scratch-that. **Tray icon unchanged.**
- Milestone thresholds/names (exact): 1000 First Roar, 5000 Warming Up, 10000 Voice Layer, 25000 Fluent Flow, 50000 Local Legend, 100000 Hundred-K Roar, 250000 Dictation Engine, 500000 Thunder Typist, 1000000 Million Word Roar.
- Progress = live all-time `SUM(word_count)`; unlocked badges are sticky (first-unlock timestamp persists through history deletes).
- Config defaults: `milestones_enabled: true`, `milestone_notifications: true`.
- Notification = tray balloon only (no new tone, no overlay).
- Logo source: `C:/Users/xhan1/OneDrive/Pictures/ROAR LOGO FINAL 2 LAV.png`.
- Kill ROAR + webviews before builds/installs; serialize builds; MSI external cabs; fetch before push.

---

### Task 1: `milestones.py` — pure progress engine (TDD)

**Files:**
- Create: `milestones.py`
- Test: `tests/test_milestones.py`

**Interfaces:**
- Produces: `MILESTONES` (list of `(threshold:int, name:str)`, ascending);
  `progress(total_words, unlocks=None) -> dict`;
  `newly_crossed(old_total, new_total) -> list[int]`;
  `name_for(threshold) -> str | None`.

- [ ] **Step 1: Write the failing tests** — `tests/test_milestones.py`:

```python
import milestones


def test_thresholds_ascending_and_named():
    ts = [t for t, _ in milestones.MILESTONES]
    assert ts == sorted(ts)
    assert ts[0] == 1000 and ts[-1] == 1_000_000
    assert milestones.name_for(50000) == "Local Legend"
    assert milestones.name_for(1234) is None


def test_progress_start():
    p = milestones.progress(0)
    assert p["unlocked"] == []
    assert p["next"] == {"threshold": 1000, "name": "First Roar"}
    assert p["words_remaining"] == 1000
    assert p["percent"] == 0
    assert p["total_words"] == 0


def test_progress_mid_band():
    p = milestones.progress(3000)   # past 1000, toward 5000
    assert [u["threshold"] for u in p["unlocked"]] == [1000]
    assert p["next"]["threshold"] == 5000
    assert p["words_remaining"] == 2000
    # from 1000 -> 5000, at 3000 => (3000-1000)/(5000-1000) = 50%
    assert p["percent"] == 50


def test_progress_exact_threshold_counts_as_unlocked():
    p = milestones.progress(5000)
    assert 5000 in [u["threshold"] for u in p["unlocked"]]
    assert p["next"]["threshold"] == 10000


def test_progress_maxed():
    p = milestones.progress(2_000_000)
    assert len(p["unlocked"]) == len(milestones.MILESTONES)
    assert p["next"] is None
    assert p["words_remaining"] == 0
    assert p["percent"] == 100


def test_progress_carries_unlock_timestamps():
    p = milestones.progress(6000, unlocks={1000: 111.0, 5000: 222.0})
    got = {u["threshold"]: u["unlocked_ts"] for u in p["unlocked"]}
    assert got == {1000: 111.0, 5000: 222.0}


def test_newly_crossed():
    assert milestones.newly_crossed(0, 999) == []
    assert milestones.newly_crossed(0, 1000) == [1000]
    assert milestones.newly_crossed(900, 6000) == [1000, 5000]
    assert milestones.newly_crossed(5000, 5001) == []       # 5000 already had
    assert milestones.newly_crossed(999_999, 3_000_000) == [1_000_000]


def test_progress_tolerates_bad_input():
    assert milestones.progress(-5)["total_words"] == 0
    assert milestones.progress("nope")["next"]["threshold"] == 1000
```

- [ ] **Step 2: Run to verify fail**

Run: `venv/Scripts/python.exe -m pytest tests/test_milestones.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'milestones'`.

- [ ] **Step 3: Implement `milestones.py`**

```python
"""Word-count milestones: map an all-time dictation word total to badge
progress. Pure — no I/O, no persistence (the history DB stores unlock times)."""

MILESTONES = [
    (1000, "First Roar"),
    (5000, "Warming Up"),
    (10000, "Voice Layer"),
    (25000, "Fluent Flow"),
    (50000, "Local Legend"),
    (100000, "Hundred-K Roar"),
    (250000, "Dictation Engine"),
    (500000, "Thunder Typist"),
    (1000000, "Million Word Roar"),
]

_NAMES = dict(MILESTONES)


def name_for(threshold):
    return _NAMES.get(threshold)


def _clamp(total):
    try:
        total = int(total)
    except (TypeError, ValueError):
        return 0
    return max(0, total)


def progress(total_words, unlocks=None):
    total = _clamp(total_words)
    unlocks = unlocks or {}
    unlocked = [{"threshold": t, "name": n, "unlocked_ts": unlocks.get(t)}
                for t, n in MILESTONES if t <= total]
    nxt = next(({"threshold": t, "name": n} for t, n in MILESTONES if t > total),
               None)
    if nxt is None:
        return {"unlocked": unlocked, "next": None, "percent": 100,
                "words_remaining": 0, "total_words": total}
    prev = unlocked[-1]["threshold"] if unlocked else 0
    span = nxt["threshold"] - prev
    percent = int((total - prev) / span * 100) if span else 0
    return {"unlocked": unlocked, "next": nxt, "percent": percent,
            "words_remaining": nxt["threshold"] - total, "total_words": total}


def newly_crossed(old_total, new_total):
    old, new = _clamp(old_total), _clamp(new_total)
    return [t for t, _ in MILESTONES if old < t <= new]
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/Scripts/python.exe -m pytest tests/test_milestones.py -q`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add milestones.py tests/test_milestones.py
git commit -m "feat: pure word-milestone progress engine"
```

---

### Task 2: `history.py` — badge_unlocks table + all-time total (TDD)

**Files:**
- Modify: `history.py` (SCHEMA, `_migrate`, new methods)
- Test: `tests/test_history.py`

**Interfaces:**
- Produces: `History.total_words() -> int`;
  `History.record_unlock(threshold:int, ts:float) -> None`;
  `History.unlocks() -> dict[int, float]`; DB `user_version == 3`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_history.py`
  (read the file first for its `History(...)` construction pattern; use the
  same tmp_path db_path/audio_dir style already used there):

```python
def test_total_words_all_time(tmp_path):
    import history as history_mod
    h = history_mod.History(db_path=str(tmp_path / "h.db"),
                            audio_dir=str(tmp_path / "a"))
    assert h.total_words() == 0
    h.record("one two three", ts=1.0)      # 3 words
    h.record("four five", ts=2.0)          # 2 words
    assert h.total_words() == 5
    h.close()


def test_badge_unlocks_sticky(tmp_path):
    import history as history_mod
    h = history_mod.History(db_path=str(tmp_path / "h.db"),
                            audio_dir=str(tmp_path / "a"))
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
    # hand-build a v2 DB: dictations table + user_version=2, no badge_unlocks
    con = sqlite3.connect(p)
    con.executescript(history_mod.SCHEMA)
    con.execute("PRAGMA user_version=2")
    con.commit(); con.close()
    h = history_mod.History(db_path=p, audio_dir=str(tmp_path / "a"))
    assert h.unlocks() == {}                 # table exists, empty
    h.record_unlock(1000, 5.0)
    assert h.unlocks() == {1000: 5.0}
    h.close()
```

- [ ] **Step 2: Run to verify fail**

Run: `venv/Scripts/python.exe -m pytest tests/test_history.py -q -k "total_words or badge or migration"`
Expected: FAIL — no `total_words` / `record_unlock` / `unlocks`.

- [ ] **Step 3: Implement in `history.py`:**

Extend `SCHEMA` (add the table to the existing triple-quoted string, after the
index line):

```python
CREATE TABLE IF NOT EXISTS badge_unlocks (
    threshold   INTEGER PRIMARY KEY,
    unlocked_ts REAL    NOT NULL
);
```

Extend `_migrate` to bump to 3:

```python
def _migrate(conn):
    """Bring an existing DB forward. v2 adds duration_s; v3 adds badge_unlocks
    (created by SCHEMA's IF NOT EXISTS, so v3 just records the version)."""
    ver = conn.execute("PRAGMA user_version").fetchone()[0]
    if ver < 2:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(dictations)")]
        if "duration_s" not in cols:
            conn.execute("ALTER TABLE dictations ADD COLUMN duration_s REAL")
    conn.execute("PRAGMA user_version=3")
```

(SCHEMA is run via `executescript` before `_migrate` on every open, so
`badge_unlocks` is created for old DBs too — the pragma bump just records it.)

Add methods to `History` (near `stats`):

```python
    def total_words(self):
        with self._lock:
            return self._conn.execute(
                "SELECT COALESCE(SUM(word_count), 0) FROM dictations").fetchone()[0]

    def record_unlock(self, threshold, ts):
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO badge_unlocks (threshold, unlocked_ts)"
                " VALUES (?, ?)", (int(threshold), float(ts)))
            self._conn.commit()

    def unlocks(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT threshold, unlocked_ts FROM badge_unlocks").fetchall()
        return {r["threshold"]: r["unlocked_ts"] for r in rows}
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/Scripts/python.exe -m pytest tests/test_history.py -q`
Expected: all pass (existing history tests still green — SCHEMA/migration change is additive).

- [ ] **Step 5: Commit**

```bash
git add history.py tests/test_history.py
git commit -m "feat: badge_unlocks table + all-time word total (history v3)"
```

---

### Task 3: insights block + bridge wiring + config keys (TDD)

**Files:**
- Modify: `insights.py`, `settings_ui.py` (get_insights, get_state, INSTANT_KEYS, set_value), `config.py`
- Test: `tests/test_insights.py`, `tests/test_config.py`, `tests/test_settings_bridge.py`

**Interfaces:**
- Consumes: `milestones.progress` (Task 1); `History.total_words/unlocks` (Task 2).
- Produces: `compute_insights(rows, now=None, total_words=None, unlocks=None)`
  with a `"milestones"` key; config keys `milestones_enabled`/
  `milestone_notifications` (default True/True); `get_state()["logo_path"]`.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_insights.py`:

```python
def test_milestones_block_from_rows_sum():
    rows = [{"ts_utc": 1.0, "word_count": 1200, "text": "x", "duration_s": None}]
    d = insights.compute_insights(rows, now=1000.0)
    assert d["milestones"]["next"]["threshold"] == 5000
    assert 1000 in [u["threshold"] for u in d["milestones"]["unlocked"]]


def test_milestones_block_uses_all_time_total_when_given():
    rows = [{"ts_utc": 1.0, "word_count": 50, "text": "x", "duration_s": None}]
    d = insights.compute_insights(rows, now=1000.0, total_words=12000,
                                  unlocks={1000: 7.0})
    assert d["milestones"]["total_words"] == 12000
    assert d["milestones"]["next"]["threshold"] == 25000
    got = {u["threshold"]: u["unlocked_ts"] for u in d["milestones"]["unlocked"]}
    assert got[1000] == 7.0
```

Append to `tests/test_config.py`:

```python
def test_milestone_defaults_and_coercion(tmp_path):
    cfg = config.load(str(tmp_path / "c1.json"))
    assert cfg["milestones_enabled"] is True
    assert cfg["milestone_notifications"] is True
    p = tmp_path / "c2.json"
    p.write_text(json.dumps({"milestones_enabled": 0, "milestone_notifications": 1}))
    cfg = config.load(str(p))
    assert cfg["milestones_enabled"] is False
    assert cfg["milestone_notifications"] is True
```

Append to `tests/test_settings_bridge.py`:

```python
def test_milestone_instant_keys(tmp_path):
    p = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=p)
    assert api.set_value("milestones_enabled", False)["ok"] is True
    assert config.load(p)["milestones_enabled"] is False
    assert api.set_value("milestone_notifications", False)["ok"] is True
    assert config.load(p)["milestone_notifications"] is False


def test_get_insights_includes_all_time_milestones(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    monkeypatch.setattr(paths, "audio_dir", lambda: str(tmp_path / "a"))
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    api._history.record("word " * 1200, ts=1.0)  # 1200 words -> First Roar
    d = api.get_insights()
    assert "milestones" in d
    assert 1000 in [u["threshold"] for u in d["milestones"]["unlocked"]]
```

- [ ] **Step 2: Run to verify fail**

Run: `venv/Scripts/python.exe -m pytest tests/test_insights.py tests/test_config.py tests/test_settings_bridge.py -q -k "milestone"`
Expected: FAIL — no milestones key / config keys.

- [ ] **Step 3a: `insights.py`** — add `import milestones` at the top, and
  extend the signature + return:

```python
def compute_insights(rows, now=None, total_words=None, unlocks=None):
```

Just before the final `return {`, compute the block:

```python
    ms_total = words_total if total_words is None else total_words
    milestones_block = milestones.progress(ms_total, unlocks)
```

and add `"milestones": milestones_block,` to the returned dict.

- [ ] **Step 3b: `config.py`** — add to DEFAULTS (after the cleanup keys):

```python
    "milestones_enabled": True,
    "milestone_notifications": True,
```

and a sanitize branch (next to the cleanup one):

```python
        elif key in ("cleanup_enabled", "remove_discourse_fillers",
                     "milestones_enabled", "milestone_notifications"):
            cfg[key] = bool(value)
```

- [ ] **Step 3c: `settings_ui.py`** — `get_insights` feeds the all-time total:

```python
    def get_insights(self):
        from insights import compute_insights
        rows = self._history.list(limit=5000)
        result = compute_insights(rows,
                                  total_words=self._history.total_words(),
                                  unlocks=self._history.unlocks())
        total = self._history.stats()["count"]
        result["truncated_from"] = total if total > len(rows) else None
        return result
```

`get_state` gains a logo path (add the key to the returned dict):

```python
            "logo_path": paths.resource_path("assets/roar-logo-purple-256.png"),
```

`INSTANT_KEYS` += the two keys; extend the `set_value` bool-coercion list to
include `"milestones_enabled", "milestone_notifications"`.

- [ ] **Step 4: Run to verify pass**

Run: `venv/Scripts/python.exe -m pytest tests/test_insights.py tests/test_config.py tests/test_settings_bridge.py -q`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add insights.py settings_ui.py config.py tests/test_insights.py tests/test_config.py tests/test_settings_bridge.py
git commit -m "feat: milestones in insights + config keys + bridge wiring"
```

---

### Task 4: `app.py` — unlock detection + tray notify (TDD)

**Files:**
- Modify: `app.py`
- Test: `tests/test_capture_integration.py`

**Interfaces:**
- Consumes: `milestones.newly_crossed/name_for`, `History.total_words/record_unlock`.
- Produces: after a recorded dictation (history on + `milestones_enabled`),
  newly-crossed thresholds are persisted and (if `milestone_notifications`)
  tray-notified. Failure-isolated.

- [ ] **Step 1: Write the failing test** — append to
  `tests/test_capture_integration.py` (the module already stubs `inject_text`;
  `_make_app` builds a real temp History and sets `_inject_stack`):

```python
def test_milestone_unlock_records_and_notifies(tmp_path, monkeypatch):
    notes = []
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path, {"milestones_enabled": True,
                             "milestone_notifications": True})
    a.notify = lambda msg: notes.append(msg)
    # transcript of 1000 words -> crosses First Roar in one shot
    a.transcriber.transcribe = lambda audio: "word " * 1000
    a._handle_transcription(_loud_audio())
    assert a.history.unlocks().get(1000) is not None
    assert any("First Roar" in n for n in notes)
    a.history.close()


def test_milestone_disabled_no_unlock(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: True)
    a = _make_app(tmp_path, {"milestones_enabled": False})
    a.notify = lambda msg: None
    a.transcriber.transcribe = lambda audio: "word " * 1000
    a._handle_transcription(_loud_audio())
    assert a.history.unlocks() == {}
    a.history.close()
```

(Note `_make_app`'s cfg dict lacks the milestone keys by default — the test
passes them via `cfg_overrides`. Also add safe `.get` defaults in app code so
missing keys don't crash.)

- [ ] **Step 2: Run to verify fail**

Run: `venv/Scripts/python.exe -m pytest tests/test_capture_integration.py -q -k milestone`
Expected: FAIL — no unlock recorded / no notify.

- [ ] **Step 3: Implement in `app.py`:**

Add imports near the others: `import time` (if absent) and `import milestones`.

In `_handle_transcription`, after the existing
`rid = record_history(...)` and the `self._inject_stack.push(...)` line, add:

```python
        self._check_milestones(text, rid)
```

Add the method to `ROARApp` (near `_scratch`):

```python
    def _check_milestones(self, text, rid):
        """Persist + notify any word-count milestones this dictation crossed.
        Failure-isolated: milestones must never affect dictation."""
        if rid is None or not self.cfg.get("milestones_enabled", True):
            return
        try:
            new_total = self.history.total_words()
            old_total = new_total - len(text.split())
            for t in milestones.newly_crossed(old_total, new_total):
                self.history.record_unlock(t, time.time())
                if self.cfg.get("milestone_notifications", True):
                    self.notify(f"Milestone unlocked: {milestones.name_for(t)}"
                                f" — {t:,} words")
        except Exception as e:
            self.log(f"milestone check failed: {e}")
```

- [ ] **Step 4: Run full suite** (kill ROAR + webviews first)

Run: `venv/Scripts/python.exe -m pytest tests/ -q --ignore=tests/test_transcriber_gpu.py`
Expected: PASS ×2.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_capture_integration.py
git commit -m "feat: milestone unlock detection + tray notification"
```

---

### Task 5: logo assets + Insights UI + About logo + version (TDD-ish)

**Files:**
- Create: `scripts/make_logo_assets.py`, `assets/roar-logo-purple*.png`
- Modify: `roar.spec`, `settings.html`, `settings_ui.py` (smoke probe), `paths.py`
- Test: `tests/test_paths.py`, `tests/test_settings_bridge.py` (version), `tests/test_settings_smoke.py`

- [ ] **Step 1: Create `scripts/make_logo_assets.py`:**

```python
"""Copy the lavender ROAR logo into assets/ and derive tight square sizes.
Run once: venv/Scripts/python.exe scripts/make_logo_assets.py"""
import os
import shutil

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = r"C:/Users/xhan1/OneDrive/Pictures/ROAR LOGO FINAL 2 LAV.png"
ASSETS = os.path.join(ROOT, "assets")


def main():
    os.makedirs(ASSETS, exist_ok=True)
    full = os.path.join(ASSETS, "roar-logo-purple.png")
    shutil.copyfile(SRC, full)
    im = Image.open(SRC).convert("RGBA")
    bbox = im.getchannel("A").getbbox()   # trim transparent margins
    mark = im.crop(bbox)
    side = max(mark.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(mark, ((side - mark.width) // 2, (side - mark.height) // 2))
    for px in (256, 64, 32):
        square.resize((px, px), Image.LANCZOS).save(
            os.path.join(ASSETS, f"roar-logo-purple-{px}.png"))
    print("logo assets written to", ASSETS)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Generate the assets**

Run: `venv/Scripts/python.exe scripts/make_logo_assets.py`
Expected: `assets/roar-logo-purple.png` + `-256/-64/-32.png` exist.
Verify: `venv/Scripts/python.exe -c "from PIL import Image; print(Image.open('assets/roar-logo-purple-256.png').size)"` → `(256, 256)`.

- [ ] **Step 3: `roar.spec`** — after the `settings.html` datas line, add:

```python
import os as _os2
if _os2.path.isdir("assets"):
    datas += [("assets", "assets")]
```

- [ ] **Step 4: `paths.py`** — `APP_VERSION = "0.13.0"`. Update version asserts
  in `tests/test_paths.py` and `tests/test_settings_bridge.py::test_get_state_shape`
  from `"0.12.0"` to `"0.13.0"`.

- [ ] **Step 5: `settings.html`** — About logo: at the top of
  `<section id="about">`, before the `<h1>`, add:

```html
      <img id="a-logo" src="assets/roar-logo-purple-256.png" alt="ROAR"
           style="width:96px;height:96px;display:block;margin:0 0 8px;">
```

(Relative `src` resolves next to settings.html in both dev and the frozen
`_internal/` layout.)

Insights milestones block: inside `<div id="ins-body">`, after the totals
`<div style="display:flex;gap:10px;">…</div>` block, insert:

```html
        <div class="row" id="ms-block">
          <div style="display:flex;justify-content:space-between;align-items:baseline;">
            <div class="hint">Milestones</div>
            <div class="hint" id="ms-next"></div>
          </div>
          <div style="background:#1A1D29;border-radius:6px;height:8px;margin:8px 0 4px;overflow:hidden;">
            <div id="ms-bar" style="height:100%;width:0;background:#A78BFA;border-radius:6px;"></div>
          </div>
          <div class="hint" id="ms-remaining"></div>
          <div id="ms-shelf" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;"></div>
          <div class="row flex" style="background:#0a0a0c;margin-top:10px;">
            <div>Track word milestones<div class="hint">Private, on this device only</div></div>
            <button class="toggle" id="t-milestones" aria-pressed="true" aria-label="Track word milestones"></button>
          </div>
          <div class="row flex" style="background:#0a0a0c;margin-top:8px;">
            <div>Notify on unlock</div>
            <button class="toggle" id="t-ms-notify" aria-pressed="true" aria-label="Notify on milestone unlock"></button>
          </div>
        </div>
```

In `init()` (where other toggles are set from `c`), add:

```javascript
  setToggle($("t-milestones"), c.milestones_enabled);
  setToggle($("t-ms-notify"), c.milestone_notifications);
```

In `renderInsights()`, after the totals are set, render milestones:

```javascript
  const ms = d.milestones, on = state.config.milestones_enabled !== false;
  $("ms-block").style.display = on ? "" : "none";
  if (on && ms) {
    $("ms-bar").style.width = (ms.next ? ms.percent : 100) + "%";
    $("ms-next").textContent = ms.next
      ? "Next: " + ms.next.name + " (" + ms.next.threshold.toLocaleString() + ")"
      : "All milestones unlocked";
    $("ms-remaining").textContent = ms.next
      ? ms.words_remaining.toLocaleString() + " words to go" : "";
    const shelf = $("ms-shelf"); shelf.innerHTML = "";
    const unlocked = new Set(ms.unlocked.map(u => u.threshold));
    MILESTONES_FOR_UI.forEach(([t, name]) => {
      const chip = document.createElement("span");
      chip.className = "chipword";
      chip.textContent = name;
      if (!unlocked.has(t)) { chip.style.opacity = "0.4"; }
      else { chip.style.background = "#2A2547"; chip.style.color = "#C9BEF5"; }
      chip.title = t.toLocaleString() + " words";
      shelf.appendChild(chip);
    });
  }
```

Add the milestone table near the top of the `<script>` (after `const $ =`):

```javascript
const MILESTONES_FOR_UI = [[1000,"First Roar"],[5000,"Warming Up"],[10000,"Voice Layer"],[25000,"Fluent Flow"],[50000,"Local Legend"],[100000,"Hundred-K Roar"],[250000,"Dictation Engine"],[500000,"Thunder Typist"],[1000000,"Million Word Roar"]];
```

Add toggle handlers (near the other instant toggles):

```javascript
$("t-milestones").addEventListener("click", async () => {
  const want = !isOn($("t-milestones"));
  const r = await api().set_value("milestones_enabled", want);
  if (r.ok) { setToggle($("t-milestones"), want); state.config.milestones_enabled = want; renderInsights(); }
});
$("t-ms-notify").addEventListener("click", async () => {
  const want = !isOn($("t-ms-notify"));
  const r = await api().set_value("milestone_notifications", want);
  if (r.ok) setToggle($("t-ms-notify"), want);
});
```

- [ ] **Step 6: smoke probe** — in `settings_ui.py` `probe_and_close`, add:

```python
                    has_ms = window.evaluate_js(
                        "document.getElementById('ms-shelf') ? 1 : 0")
                    has_logo = window.evaluate_js(
                        "document.getElementById('a-logo') ? 1 : 0")
```

and extend the probe print with `f"ms={has_ms} logo={has_logo}"`. Append to
`tests/test_settings_smoke.py` asserts: `assert "ms=1" in out and "logo=1" in out`.

- [ ] **Step 7: suite ×2** (kill ROAR + webviews first)

Run: `venv/Scripts/python.exe -m pytest tests/ -q --ignore=tests/test_transcriber_gpu.py`
Expected: PASS twice.

- [ ] **Step 8: Commit**

```bash
git add scripts/make_logo_assets.py assets roar.spec settings.html settings_ui.py paths.py tests/test_paths.py tests/test_settings_bridge.py tests/test_settings_smoke.py
git commit -m "feat: ROAR logo assets + Insights milestones UI; bump v0.13.0"
```

---

### Task 6: docs + release train v0.13.0

- [ ] **Step 1:** README: milestones line `v0.13.0 private offline word
  milestones + lavender ROAR branding`; a short "Milestones" section (private,
  on-device, no sharing; sticky badges; the 9 names). Roadmap note. Commit
  `docs: private milestones`.
- [ ] **Step 2:** Kill ROAR + webviews; exe rebuild; frozen probe
  (`version=0.13.0 … ms=1 logo=1`); confirm the About logo renders (screenshot);
  MSI build SOLO (external cabs); setup exe (`scripts/build_setup.sh`); `7za l`
  payload check.
- [ ] **Step 3:** Adversarial review (Workflow): milestones math (percent
  banding, past-max, multi-cross), sticky-unlock vs history-delete, all-time
  total vs 5000 window, migration from a real v2 DB, notify failure-isolation,
  logo path in frozen layout, no ML import creep. Verify confirmed inline; fix;
  suite ×2; `git status` clean.
- [ ] **Step 4:** Upgrade-install over 0.12.0 (kill first): exit 0, single ROAR
  v0.13.0, installed probe green, config + history intact, badge_unlocks
  migration applied (unlocks() works on the real DB).
- [ ] **Step 5:** `git fetch` → push; release commit `feat: add private word
  milestones and ROAR branding`; tag `v0.13.0`; push --tags; relaunch;
  MEMORY.md + flowlocal-project.md; final report.
