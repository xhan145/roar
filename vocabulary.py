"""Custom-vocabulary merging and validation. Pure functions."""

MAX_CUSTOM = 50


def merge_hotwords(custom, signature, cap=60):
    """Merged hotwords string for faster-whisper, or None when empty.
    Custom words first, case-insensitive dedupe, capped."""
    # defense-in-depth: a mistyped config value (e.g. a bare string) must not
    # be iterated character-by-character
    if not isinstance(custom, (list, tuple)):
        custom = []
    if not isinstance(signature, (list, tuple)):
        signature = []
    out, seen = [], set()
    for word in list(custom) + list(signature):
        w = str(word).strip()
        key = w.lower()
        if w and key not in seen:
            seen.add(key)
            out.append(w)
        if len(out) >= cap:
            break
    return " ".join(out) if out else None


def normalize_entry(word) -> str:
    """Trim and collapse internal whitespace ('New   York' -> 'New York').
    Multi-word phrases are legal: hotwords are injected as prompt text, so
    phrases bias recognition as a unit."""
    return " ".join(str(word or "").split())


def validate_entry(word, existing):
    """None when the entry is acceptable, else a human-readable reason."""
    w = normalize_entry(word)
    if len(w) < 2:
        return "words need at least 2 characters"
    if len(w) > 40:
        return "words are limited to 40 characters"
    if any(ord(ch) < 32 for ch in w):
        return "that contains unprintable characters"
    if len(existing) >= MAX_CUSTOM:
        return f"the custom list is limited to {MAX_CUSTOM} words"
    if w.lower() in {str(e).strip().lower() for e in existing}:
        return "that word is already in the list"
    return None
