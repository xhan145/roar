"""Personal corrections — teach ROAR the words it keeps mishearing.

Whisper mishears some words *for you specifically* (names, jargon, your accent).
This module records "what it heard" -> "what you meant" and rewrites the misheard
phrase in future transcripts. Paired with a hotword (see vocabulary.py), the
recognizer also becomes more likely to get it right in the first place.

Deliberately NOT `commands.apply_replacements`: that one absorbs surrounding
punctuation and spacing because a spoken command ("new line") should consume its
own punctuation. A word correction must leave the sentence untouched — only the
misheard word changes.

Pure functions: no I/O, no config, no network. Corrections are user text and are
never logged or transmitted.
"""
import re

MAX_PHRASE = 80          # a correction is a word or short phrase, not a sentence
MAX_LEARN_WORDS = 3      # a misheard phrase is 1-3 words; wider edits are
                         # rewrites, not corrections — refuse to guess


def normalize_heard(phrase) -> str:
    """Canonical key for a misheard phrase: lowercased, whitespace collapsed."""
    return " ".join(str(phrase or "").split()).lower()


def apply(text: str, pairs: dict) -> str:
    """Rewrite every misheard phrase in `text`. Case-insensitive matching,
    whole words only, longest phrase first; punctuation and spacing survive.

    The taught replacement's own casing is preserved ("PyPlot" stays "PyPlot"),
    except that a lowercase replacement landing at a sentence start is
    capitalized so the sentence still reads correctly.
    """
    if not text or not pairs:
        return text
    for heard in sorted(pairs, key=len, reverse=True):
        meant = pairs[heard]
        if not heard or meant is None:
            continue
        pattern = re.compile(r"\b" + re.escape(heard) + r"\b", re.IGNORECASE)

        def _sub(match, meant=meant):
            start = match.start()
            prefix = match.string[:start].rstrip()
            at_sentence_start = (not prefix) or prefix[-1] in ".!?\n"
            if at_sentence_start and meant[:1].islower():
                return meant[:1].upper() + meant[1:]
            return meant

        text = pattern.sub(_sub, text)
    return text


def learn(heard_text: str, corrected_text: str):
    """Infer a (heard, meant) pair from a transcript the user fixed by hand.

    Returns None when nothing changed, when the edit is only punctuation, or
    when the rewrite is too broad to be a word correction.
    """
    heard_words = str(heard_text or "").split()
    fixed_words = str(corrected_text or "").split()
    if not heard_words or not fixed_words:
        return None

    # Trim the common head and tail; what remains is the edit.
    head = 0
    while (head < len(heard_words) and head < len(fixed_words)
           and heard_words[head] == fixed_words[head]):
        head += 1
    tail = 0
    while (tail < len(heard_words) - head and tail < len(fixed_words) - head
           and heard_words[len(heard_words) - 1 - tail]
           == fixed_words[len(fixed_words) - 1 - tail]):
        tail += 1

    heard_span = heard_words[head:len(heard_words) - tail]
    meant_span = fixed_words[head:len(fixed_words) - tail]
    if not heard_span or not meant_span:
        return None
    if len(heard_span) > MAX_LEARN_WORDS or len(meant_span) > MAX_LEARN_WORDS:
        return None

    heard = " ".join(heard_span)
    meant = " ".join(meant_span)
    # Ignore edits that only added/removed punctuation around the same words.
    # Case-SENSITIVE on purpose: "bob" -> "Bob" is a real correction people
    # teach, so a capitalization-only fix must survive this check.
    if _strip_punct(heard) == _strip_punct(meant):
        return None
    return (_strip_punct(heard), _strip_punct(meant))


def validate(heard, meant, existing: dict):
    """None when the pair is usable, else a short human-readable reason."""
    key = normalize_heard(heard)
    fix = " ".join(str(meant or "").split())
    if not key:
        return "Enter the word ROAR heard."
    if not fix:
        return "Enter what you actually meant."
    if len(key) > MAX_PHRASE or len(fix) > MAX_PHRASE:
        return f"Keep corrections under {MAX_PHRASE} characters."
    if key == fix.lower():
        return "Those are the same — nothing to correct."
    if existing and key in {normalize_heard(k) for k in existing}:
        return f"“{key}” already has a correction."
    return None


def _strip_punct(text: str) -> str:
    return text.strip(" \t.,!?;:\"'()[]")
