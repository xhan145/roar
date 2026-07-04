"""Deterministic speech cleanup: strip fillers and light disfluencies from a
transcript so it reads like writing. Pure, total, no dependencies, English
filler lists (repeat/false-start collapse is language-agnostic)."""
import re

INTERJECTIONS = frozenset({
    "um", "umm", "ummm", "uh", "uhh", "uhm", "er", "err", "erm",
    "hmm", "hmmm", "hm", "mm", "mmm",
})

# Immediate duplicates of these collapse (classic stutters). Grammatical
# doubles ("had had", "that that", "very very") are deliberately excluded.
COLLAPSE_WORDS = frozenset({
    "i", "a", "an", "the", "to", "and", "we", "you", "it", "is",
    "so", "but", "my", "of", "in", "on", "at", "for", "he", "she", "they",
})

# Removed only when comma-bounded (how Whisper punctuates true fillers).
DISCOURSE_FILLERS = (
    "you know", "i mean", "i guess", "sort of", "kind of",
    "basically", "actually", "literally", "you see", "like", "right",
)

_INTERJ_RE = re.compile(
    r"\b(?:" + "|".join(sorted(INTERJECTIONS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE)
_FALSE_START_RE = re.compile(r"\b\w{1,4}[‒-―\-]\s+", re.UNICODE)
_COLLAPSE_RE = re.compile(
    r"\b(" + "|".join(sorted(COLLAPSE_WORDS, key=len, reverse=True))
    + r")(\s+\1\b)+", re.IGNORECASE)


def _collapse_repeats(text):
    # \1 backref: same allowlisted word repeated (2+ times) -> keep one
    return _COLLAPSE_RE.sub(lambda m: m.group(1), text)


def _remove_discourse(text):
    for phrase in DISCOURSE_FILLERS:
        # comma-bounded on both sides -> collapse to a single space
        text = re.sub(r",\s*" + re.escape(phrase) + r"\s*,", " ", text,
                      flags=re.IGNORECASE)
        # sentence-initial "phrase, ..." or trailing "..., phrase"
        text = re.sub(r"^\s*" + re.escape(phrase) + r"\s*,\s*", "", text,
                      flags=re.IGNORECASE)
        text = re.sub(r",\s*" + re.escape(phrase) + r"\s*$", "", text,
                      flags=re.IGNORECASE)
    return text


def _normalize(text):
    text = re.sub(r"[ \t]*—[ \t]*", " ", text)  # leftover em-dashes -> space
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)      # no space before punct
    text = re.sub(r"^[\s,]+", "", text)                # no leading comma/space
    text = re.sub(r"[ \t]{2,}", " ", text)             # collapse runs of spaces
    return text.strip()


def clean(text, *, discourse=False):
    if not isinstance(text, str) or not text.strip():
        return ""
    text = _FALSE_START_RE.sub("", text)
    text = _INTERJ_RE.sub("", text)
    text = _collapse_repeats(text)
    if discourse:
        text = _remove_discourse(text)
    return _normalize(text)
