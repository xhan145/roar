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
