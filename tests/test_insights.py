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
    rows = [_row("one two three four five six", NOW - 100, dur=3.0),       # 120 wpm, recent
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
