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

# Lookarounds exclude hyphens as well as word chars, so a hyphen-joined
# affirmation ("uh-huh", "mm-hmm" — which mean "yes") is left whole instead of
# being split into a stray dash.
_INTERJ_RE = re.compile(
    r"(?<![-\w])(?:" + "|".join(sorted(INTERJECTIONS, key=len, reverse=True))
    + r")(?![-\w])", re.IGNORECASE)
# Fragment + dash + space, with the next word captured by lookahead. Only a
# fragment that is a PREFIX of the next word is a stutter ("wh- what"); ASR
# often splits real hyphenates with a space ("e- mail", "x- ray") and those
# must survive.
_FALSE_START_RE = re.compile(r"\b(\w{1,4})[‒-―\-]\s+(?=(\w+))", re.UNICODE)
_COLLAPSE_RE = re.compile(
    r"\b(" + "|".join(sorted(COLLAPSE_WORDS, key=len, reverse=True))
    + r")(\s+\1\b)+", re.IGNORECASE)

# A "run" of adjacent fillers ("like, you know, i mean") matches as ONE unit —
# per-phrase substitution would consume the shared comma and orphan neighbors.
_PHRASE = "(?:" + "|".join(re.escape(p) for p in DISCOURSE_FILLERS) + ")"
_MULTIWORD = "(?:" + "|".join(re.escape(p) for p in DISCOURSE_FILLERS
                              if " " in p) + ")"
_RUN = _PHRASE + r"(?:\s*,\s*" + _PHRASE + r")*"
# Sentence-edge removal only when the edge-most phrase is multi-word: a
# single-word homograph there is a real word ("Actually, ..." = contrast,
# trailing ", right" = tag question).
_EDGE_START_RE = re.compile(
    r"^\s*" + _MULTIWORD + r"(?:\s*,\s*" + _PHRASE + r")*\s*,\s*",
    re.IGNORECASE)
_EDGE_END_RE = re.compile(
    r",\s*(?:" + _PHRASE + r"\s*,\s*)*" + _MULTIWORD + r"\s*$",
    re.IGNORECASE)
_BOUNDED_RE = re.compile(r",\s*" + _RUN + r"\s*,", re.IGNORECASE)


def _trim_false_starts(text):
    def repl(m):
        frag, nxt = m.group(1), m.group(2)
        return "" if nxt.lower().startswith(frag.lower()) else m.group(0)
    return _FALSE_START_RE.sub(repl, text)


def _collapse_repeats(text):
    # \1 backref: same allowlisted word repeated (2+ times) -> keep one
    return _COLLAPSE_RE.sub(lambda m: m.group(1), text)


def _remove_discourse(text):
    text = _BOUNDED_RE.sub(" ", text)
    text = _EDGE_START_RE.sub("", text)
    text = _EDGE_END_RE.sub("", text)
    return text


def _normalize(text):
    text = re.sub(r"[ \t]*—[ \t]*", " ", text)  # leftover em-dashes -> space
    text = re.sub(r",(\s*,)+", ",", text)              # ",," (removed filler) -> ","
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)      # no space before punct
    text = re.sub(r"^[\s,.;:!?]+", "", text)   # orphaned leading punctuation
    text = re.sub(r"[ \t]{2,}", " ", text)             # collapse runs of spaces
    text = text.strip()
    if not re.search(r"\w", text):
        return ""  # nothing but punctuation left ("hmm." -> ".") — inject nothing
    return text


def clean(text, *, discourse=False):
    if not isinstance(text, str) or not text.strip():
        return ""
    text = _trim_false_starts(text)
    text = _INTERJ_RE.sub("", text)
    text = _collapse_repeats(text)
    if discourse:
        text = _remove_discourse(text)
    return _normalize(text)
