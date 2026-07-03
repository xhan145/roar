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
    "one two three new line paragraph "
    "as also because why how where however therefore although though unless "
    "since until upon per via among between during within across toward "
    "towards off out ago ever never always sometimes often really actually "
    "maybe perhaps quite rather anyway anymore".split())

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
