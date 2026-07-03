# FlowLocal Insights & Speech Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Insights tab (word analytics, activity, WPM pace, signature words, profile sentences) + History search, computed on-read from the SP2 store; v0.4.0 release.

**Architecture:** Pure `insights.py` over `History.list()` rows; one-column schema migration (`duration_s`, user_version 2) captured from audio length; bridge `get_insights` + search-enabled `history_list`; a new Deep Focus Insights section with hand-rolled CSS charts.

**Tech Stack:** stdlib only (re, statistics, sqlite3). Existing pywebview UI, PyInstaller, WiX.

## Global Constraints

- Project `C:\Users\xhan1\flowlocal`, branch `main`, venv `venv/Scripts/python.exe`, pytest from project root, kill FlowLocal.exe before test runs.
- Spec: `docs/superpowers/specs/2026-07-03-insights-profile-design.md`.
- `paths.APP_VERSION = "0.4.0"`; nav count becomes **8**; smoke probe must CLICK the Insights tab (SP2 lesson).
- Word filter: lowercase, `[a-zA-Z']+`, strip surrounding `'`, len>=3, stopwords excluded. Signature words: len>=5, top 10.
- Pace rows: `duration_s > 0.5` only; WPM = word_count/(duration_s/60); ints; None when no rows.
- `git status` before any `git add -A` (review-agent scratch files). Release: exe + MSI, install/uninstall+data-preserved check, adversarial review, push, tag v0.4.0, relaunch.

---

### Task 1: insights.py (pure)

**Files:** Create `insights.py`, `tests/test_insights.py`

**Interfaces:** Produces `compute_insights(rows: list[dict], now: float | None = None) -> dict` with keys `totals{dictations,words,avg_words}`, `activity` (14 zero-filled day dicts `{date,dictations,words}`, oldest first, local time), `pace{median_wpm,recent_wpm}`, `top_words [[w,c]]` (15), `signature_words [w]` (10), `profile_sentences [str]` ([] when <5 dictations). Rows consumed: `text`, `word_count`, `ts_utc`, `duration_s` (may be absent/None).

- [ ] **Step 1: failing tests** `tests/test_insights.py`:

```python
import time

from insights import compute_insights

NOW = 1_800_000_000.0  # fixed for deterministic day bucketing


def _row(text, ts, dur=None):
    return {"text": text, "word_count": len(text.split()), "ts_utc": ts,
            "duration_s": dur}


def test_empty_history():
    r = compute_insights([], now=NOW)
    assert r["totals"] == {"dictations": 0, "words": 0, "avg_words": 0}
    assert len(r["activity"]) == 14
    assert all(d["dictations"] == 0 for d in r["activity"])
    assert r["pace"] == {"median_wpm": None, "recent_wpm": None}
    assert r["top_words"] == [] and r["signature_words"] == []
    assert r["profile_sentences"] == []


def test_totals_and_top_words_filtering():
    rows = [_row("the amazing keyboard keyboard works", NOW - 100),
            _row("keyboard and the cat", NOW - 200)]
    r = compute_insights(rows, now=NOW)
    assert r["totals"]["dictations"] == 2
    assert r["totals"]["words"] == 9
    words = dict(r["top_words"])
    assert words["keyboard"] == 3
    assert "the" not in words and "and" not in words  # stopwords
    assert "cat" in words  # len 3 allowed


def test_apostrophes_and_short_words():
    r = compute_insights([_row("it's a dev's 'quoted' word", NOW)], now=NOW)
    words = dict(r["top_words"])
    assert "quoted" in words  # surrounding quotes stripped
    assert "a" not in words   # too short


def test_signature_words_length_gate():
    rows = [_row("keyboard keyboard cat cat cat", NOW)]
    r = compute_insights(rows, now=NOW)
    assert r["signature_words"] == ["keyboard"]  # cat is len 3


def test_activity_window_and_order():
    day = 86400
    rows = [_row("today words here", NOW - 3600),
            _row("yesterday item", NOW - day - 3600),
            _row("ancient beyond window", NOW - 20 * day)]
    r = compute_insights(rows, now=NOW)
    acts = r["activity"]
    assert len(acts) == 14
    assert acts[-1]["dictations"] == 1 and acts[-1]["words"] == 3   # today last
    assert acts[-2]["dictations"] == 1                              # yesterday
    assert sum(a["dictations"] for a in acts) == 2                  # ancient excluded
    assert acts[0]["date"] < acts[-1]["date"]


def test_pace_median_and_recent():
    day = 86400
    rows = [_row("one two three four five six", NOW - 100, dur=3.0),    # 120 wpm, recent
            _row("one two three four five six", NOW - 10 * day, dur=2.0),  # 180 wpm, old
            _row("no duration row", NOW - 50)]
    r = compute_insights(rows, now=NOW)
    assert r["pace"]["median_wpm"] == 150   # median of 120,180
    assert r["pace"]["recent_wpm"] == 120   # only the recent one
    # tiny durations are excluded
    r2 = compute_insights([_row("hi there", NOW, dur=0.2)], now=NOW)
    assert r2["pace"]["median_wpm"] is None


def test_profile_sentences_thresholds():
    few = [_row("hello world", NOW - i) for i in range(4)]
    assert compute_insights(few, now=NOW)["profile_sentences"] == []
    many = [_row("hello world again my friend", NOW - i, dur=2.0) for i in range(6)]
    sentences = compute_insights(many, now=NOW)["profile_sentences"]
    assert len(sentences) >= 2
    assert any("burst" in s or "thought" in s or "passage" in s for s in sentences)
```

- [ ] **Step 2:** Run `venv/Scripts/python.exe -m pytest tests/test_insights.py -q` → ModuleNotFoundError.
- [ ] **Step 3:** `insights.py`:

```python
"""Pure analytics over dictation-history rows. No I/O."""
import re
import statistics
import time
from collections import Counter

STOPWORDS = frozenset(
    "the a an and or but if then else when while for nor so yet to of in on at by "
    "from up down with without about into over after before under again further "
    "once here there all any both each few more most other some such not only own "
    "same than too very can will just should now this that these those i me my we "
    "our you your he him his she her it its they them their what which who whom is "
    "are was were be been being have has had having do does did doing would could "
    "may might must shall am let us dont cant wont isnt arent wasnt werent im ive "
    "youre theyre weve hes shes its lets thats whats heres theres yes no okay ok "
    "get got make made go going went come came know knew like want said say says "
    "one two three new line paragraph".split())

_WORD_RE = re.compile(r"[a-zA-Z']+")
DAY = 86400


def _words(text):
    out = []
    for raw in _WORD_RE.findall(text.lower()):
        w = raw.strip("'")
        if len(w) >= 3 and w not in STOPWORDS:
            out.append(w)
    return out


def compute_insights(rows, now=None):
    now = time.time() if now is None else now
    dictations = len(rows)
    words_total = sum(r.get("word_count", 0) for r in rows)
    avg_words = round(words_total / dictations, 1) if dictations else 0

    # 14-day activity, zero-filled, oldest first (local dates)
    buckets = {}
    order = []
    for i in range(13, -1, -1):
        d = time.strftime("%Y-%m-%d", time.localtime(now - i * DAY))
        buckets[d] = {"date": d, "dictations": 0, "words": 0}
        order.append(d)
    for r in rows:
        d = time.strftime("%Y-%m-%d", time.localtime(r["ts_utc"]))
        if d in buckets:
            buckets[d]["dictations"] += 1
            buckets[d]["words"] += r.get("word_count", 0)
    activity = [buckets[d] for d in order]

    # pace
    wpms, recent_wpms = [], []
    for r in rows:
        dur = r.get("duration_s")
        if dur and dur > 0.5 and r.get("word_count"):
            wpm = r["word_count"] / (dur / 60.0)
            wpms.append(wpm)
            if r["ts_utc"] >= now - 7 * DAY:
                recent_wpms.append(wpm)
    pace = {
        "median_wpm": round(statistics.median(wpms)) if wpms else None,
        "recent_wpm": round(statistics.median(recent_wpms)) if recent_wpms else None,
    }

    counter = Counter()
    for r in rows:
        counter.update(_words(r.get("text", "")))
    top_words = [[w, c] for w, c in counter.most_common(15)]
    signature_words = [w for w, _c in counter.most_common() if len(w) >= 5][:10]

    sentences = []
    if dictations >= 5:
        if avg_words < 10:
            sentences.append(f"You dictate in short bursts — about {avg_words:g} words at a time.")
        elif avg_words < 25:
            sentences.append(f"You dictate medium-length thoughts — about {avg_words:g} words at a time.")
        else:
            sentences.append(f"You dictate long-form passages — about {avg_words:g} words at a time.")
        if pace["median_wpm"]:
            style = ("measured" if pace["median_wpm"] < 110
                     else "conversational" if pace["median_wpm"] < 150 else "brisk")
            sentences.append(f"Your speaking pace is {style} — around {pace['median_wpm']} words per minute.")
        if top_words:
            sentences.append(f"You reach for “{top_words[0][0]}” more than any other word.")

    return {
        "totals": {"dictations": dictations, "words": words_total, "avg_words": avg_words},
        "activity": activity,
        "pace": pace,
        "top_words": top_words,
        "signature_words": signature_words,
        "profile_sentences": sentences,
    }
```

- [ ] **Step 4:** Run → 7 passed.
- [ ] **Step 5:** `git add insights.py tests/test_insights.py && git commit -m "feat: pure insights engine (word analytics, activity, pace, profile)"`

---

### Task 2: history migration (duration_s, user_version 2) + search

**Files:** Modify `history.py`; append to `tests/test_history.py`

**Interfaces:** SCHEMA gains `duration_s REAL` (fresh DBs stamped v2). `record(..., duration_s=None)`. `list(limit=100, offset=0, query=None)` — LIKE search, `%`/`_`/`\` escaped, rows include `duration_s`.

- [ ] **Step 1: failing tests** (append to `tests/test_history.py`):

```python
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
```

- [ ] **Step 2:** Run → FAIL (no duration_s / query).
- [ ] **Step 3:** In `history.py`: SCHEMA `audio_path TEXT` line gains `,\n    duration_s  REAL`; in `_open` after `executescript` add:

```python
            ver = conn.execute("PRAGMA user_version").fetchone()[0]
            if ver < 2:
                cols = [r[1] for r in conn.execute("PRAGMA table_info(dictations)")]
                if "duration_s" not in cols:
                    conn.execute("ALTER TABLE dictations ADD COLUMN duration_s REAL")
            conn.execute("PRAGMA user_version=2")
```
(both in the normal path and after corrupt-recovery recreate, replacing the old `user_version=1` stamp). `record` signature gains `duration_s=None`; INSERT lists it. `list` gains `query=None`:

```python
    def list(self, limit=100, offset=0, query=None):
        sql = ("SELECT id, ts_utc, text, char_count, word_count, model, audio_path, duration_s"
               " FROM dictations")
        args = []
        if query:
            esc = (query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_"))
            sql += " WHERE text LIKE ? ESCAPE '\\'"
            args.append(f"%{esc}%")
        sql += " ORDER BY ts_utc DESC, id DESC LIMIT ? OFFSET ?"
        args += [limit, offset]
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        ...  # unchanged dict conversion (has_audio)
```

- [ ] **Step 4:** `tests/test_history.py` all pass.
- [ ] **Step 5:** `git add history.py tests/test_history.py && git commit -m "feat: duration column (v2 migration) + history search"`

---

### Task 3: capture duration + bridge get_insights/search

**Files:** Modify `app.py` (record_history + _handle_transcription), `settings_ui.py`; append tests to `tests/test_capture_integration.py`, `tests/test_settings_bridge.py`

**Interfaces:** `record_history(hist, cfg, text, model=None, audio=None, duration_s=None)`. Bridge: `get_insights() -> dict` (5000-row cap), `history_list(limit=100, query=None)`.

- [ ] **Step 1: failing tests.** Append to `tests/test_capture_integration.py`:

```python
def test_duration_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(injector, "inject_text",
                        lambda text, paste_fallback=False: None)
    a = _make_app(tmp_path)
    a._handle_transcription(_loud_audio(seconds=2.0))
    row = a.history.list()[0]
    assert row["duration_s"] is not None and abs(row["duration_s"] - 2.0) < 0.01
    a.history.close()
```

Append to `tests/test_settings_bridge.py`:

```python
def test_get_insights_and_search(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "history_db_path", lambda: str(tmp_path / "h.db"))
    monkeypatch.setattr(paths, "audio_dir", lambda: str(tmp_path / "a"))
    from settings_ui import SettingsAPI
    api = SettingsAPI(config_path=str(tmp_path / "config.json"))
    ins = api.get_insights()
    assert ins["totals"]["dictations"] == 0 and len(ins["activity"]) == 14
    api._history.record("searchable keyboard text", ts=1.0, duration_s=2.0)
    api._history.record("other entry", ts=2.0)
    ins = api.get_insights()
    assert ins["totals"]["dictations"] == 2
    assert [r["text"] for r in api.history_list(query="keyboard")] == ["searchable keyboard text"]
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** `app.py`: `record_history(..., duration_s=None)` passes `duration_s=duration_s` to `hist.record`; `_handle_transcription` computes `duration_s=len(audio) / recorder_mod.SAMPLE_RATE` and passes it. `settings_ui.py`:

```python
    def get_insights(self):
        from insights import compute_insights
        return compute_insights(self._history.list(limit=5000))

    def history_list(self, limit=100, query=None):
        return self._history.list(limit=limit, query=query or None)
```

- [ ] **Step 4:** Both test files pass; full suite green.
- [ ] **Step 5:** `git add app.py settings_ui.py tests/ && git commit -m "feat: capture duration; bridge insights + search"`

---

### Task 4: settings.html — Insights section + History search + probe

**Files:** Modify `settings.html`, `settings_ui.py` (probe), `tests/test_settings_smoke.py`

- [ ] **Step 1:** Nav: insert `<button class="nav" data-s="insights">Insights</button>` after the Transcription button (8 navs). New section after `#transcription`:

```html
    <section id="insights">
      <h1>Insights</h1>
      <div id="ins-empty" class="row locked" style="display:none;">Dictate a few times to build your profile.</div>
      <div id="ins-body">
        <div style="display:flex;gap:10px;">
          <div class="row" style="flex:1;text-align:center;"><div class="hint">Dictations</div><div class="stat" id="st-dictations">0</div></div>
          <div class="row" style="flex:1;text-align:center;"><div class="hint">Words</div><div class="stat" id="st-words">0</div></div>
          <div class="row" style="flex:1;text-align:center;"><div class="hint">Avg length</div><div class="stat" id="st-avg">0</div></div>
        </div>
        <div class="row">
          <div class="hint" style="margin-bottom:8px;">Last 14 days</div>
          <div id="ins-activity" style="display:flex;align-items:flex-end;gap:4px;height:80px;"></div>
        </div>
        <div class="row" id="ins-pace-row">
          <div class="hint">Speaking pace</div>
          <div id="ins-pace" class="stat">—</div>
        </div>
        <div class="row">
          <div class="hint" style="margin-bottom:8px;">Top words</div>
          <div id="ins-topwords"></div>
        </div>
        <div class="row">
          <div class="hint" style="margin-bottom:6px;">Signature words</div>
          <div id="ins-signature" style="display:flex;flex-wrap:wrap;gap:6px;"></div>
          <div class="hint" style="margin-top:8px;">These will boost transcription accuracy in a future update.</div>
        </div>
        <div class="row" id="ins-profile"></div>
      </div>
    </section>
```

CSS additions: `.stat { font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; }`, `.chipword { background:#0E1320; border:1px solid var(--border); border-radius:14px; padding:3px 12px; font-size:12.5px; }`, `.wbar { height:8px; background:var(--accent); border-radius:4px; opacity:.85; }`.

History search box above `#history-list`:

```html
      <input class="mock" id="history-search" type="search" placeholder="Search dictations…"
             style="width:100%;background:#0E1320;border:1px solid var(--border);border-radius:8px;padding:8px 12px;margin-bottom:10px;" aria-label="Search dictations">
```

JS: `renderHistory(query)` passes `api().history_list(100, query || null)`; debounced input listener (300 ms) calls `renderHistory(value)`; `renderInsights()`:

```javascript
async function renderInsights() {
  const d = await api().get_insights();
  const empty = d.totals.dictations === 0;
  document.getElementById("ins-empty").style.display = empty ? "" : "none";
  document.getElementById("ins-body").style.display = empty ? "none" : "";
  if (empty) return;
  $("st-dictations").textContent = d.totals.dictations;
  $("st-words").textContent = d.totals.words.toLocaleString();
  $("st-avg").textContent = d.totals.avg_words + " words";
  const act = $("ins-activity"); act.innerHTML = "";
  const max = Math.max(1, ...d.activity.map(a => a.words));
  d.activity.forEach(a => {
    const col = document.createElement("div");
    col.style.cssText = "flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;height:100%;justify-content:flex-end;";
    col.title = a.date + ": " + a.words + " words (" + a.dictations + " dictations)";
    const bar = document.createElement("div");
    bar.style.cssText = "width:100%;border-radius:3px;background:var(--accent);opacity:.85;height:" +
      (a.words ? Math.max(6, Math.round(a.words / max * 64)) : 2) + "px;" + (a.words ? "" : "background:#242C3D;");
    const lbl = document.createElement("div");
    lbl.className = "hint"; lbl.style.fontSize = "10px";
    lbl.textContent = a.date.slice(8);
    col.appendChild(bar); col.appendChild(lbl); act.appendChild(col);
  });
  $("ins-pace").textContent = d.pace.median_wpm
    ? d.pace.median_wpm + " WPM" + (d.pace.recent_wpm ? " (" + d.pace.recent_wpm + " this week)" : "")
    : "—  (dictate with the new version to measure pace)";
  const tw = $("ins-topwords"); tw.innerHTML = "";
  const wmax = d.top_words.length ? d.top_words[0][1] : 1;
  d.top_words.forEach(([w, c]) => {
    const row = document.createElement("div");
    row.style.cssText = "display:flex;align-items:center;gap:8px;margin:4px 0;";
    const label = document.createElement("div");
    label.style.cssText = "width:110px;overflow:hidden;text-overflow:ellipsis;"; label.textContent = w;
    const bar = document.createElement("div"); bar.className = "wbar";
    bar.style.width = Math.max(4, Math.round(c / wmax * 60)) + "%";
    const count = document.createElement("div"); count.className = "hint"; count.textContent = c;
    row.appendChild(label); row.appendChild(bar); row.appendChild(count); tw.appendChild(row);
  });
  const sig = $("ins-signature"); sig.innerHTML = "";
  d.signature_words.forEach(w => {
    const chip = document.createElement("span"); chip.className = "chipword"; chip.textContent = w;
    sig.appendChild(chip);
  });
  const prof = $("ins-profile"); prof.innerHTML = "";
  d.profile_sentences.forEach(s => {
    const p = document.createElement("div"); p.textContent = s; p.style.margin = "4px 0";
    prof.appendChild(p);
  });
  $("ins-profile").style.display = d.profile_sentences.length ? "" : "none";
}
```

Call `renderInsights()` from `init()` and refresh when the Insights nav is clicked (add to the nav click handler: `if (b.dataset.s === "insights") renderInsights();`). History deletes/clears also call `renderInsights()`.

- [ ] **Step 2:** Probe: in `settings_ui.py` add `insnav` (click Insights, assert section active) mirroring `privnav`; smoke asserts `navs=8`, `insnav=1`.
- [ ] **Step 3:** Manual `app.py --settings` check; suite green.
- [ ] **Step 4:** `git add settings.html settings_ui.py tests/test_settings_smoke.py && git commit -m "feat: Insights tab + history search UI"`

---

### Task 5: v0.4.0 + release train

- [ ] **Step 1:** `paths.APP_VERSION = "0.4.0"`; bridge test version assert → `0.4.0`. Full suite ×2 green (exit codes).
- [ ] **Step 2:** Kill FlowLocal.exe; PyInstaller rebuild; frozen `--settings --smoke` asserts probe navs=8 insnav=1 version=0.4.0 in the log.
- [ ] **Step 3:** `bash scripts/build_msi.sh` (background; ~5-10 min) → `dist/FlowLocal-0.4.0.msi`; install → installed `--settings --smoke` probe → seed history row → uninstall → program dir gone, data preserved.
- [ ] **Step 4:** README: Insights section + search mention; test count updated to actual.
- [ ] **Step 5:** Adversarial review workflow (dimensions: insights math/stopwords edge cases, migration correctness on real v1 DBs + corrupt path, search escaping/injection, UI rendering safety + nav/probe coverage, capture duration math). Fix confirmed findings; `git status` before adds; suite green ×2.
- [ ] **Step 6:** Push main; release commit `flowlocal v0.4.0 — insights, speech profile, history search`; tag `v0.4.0`; push --tags; relaunch `dist/FlowLocal/FlowLocal.exe`; update memory; report.
