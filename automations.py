"""ROAR Flow rule engine — pure matching of spoken trigger phrases to actions.

No I/O, no side effects, no imports from the runtime: this module decides WHAT
fired, never executes anything (that's actions.py). Rules are plain dicts from
config.json:

    {"phrase": "open terminal", "action": "open_app",
     "params": {"target": "wt.exe"},
     "enabled": True, "trusted": False, "consume": True}

Matching is deliberately conservative — a phrase fires only as the WHOLE
utterance or as its PREFIX ending on a word boundary, never mid-sentence, so a
trigger word inside ordinary dictation can't launch anything.
"""

import re
from dataclasses import dataclass, field

# Every action the engine may reference. actions.py implements exactly these;
# validate_rule refuses anything else so stored configs can't drift ahead.
KNOWN_ACTIONS = ("open_app", "open_url", "hotkey", "snippet", "speak", "copy",
                 "run_script", "webhook")

# Actions that execute code or leave the machine — allowed only on rules the
# user explicitly marked trusted AND when the edition allows it (actions.py
# enforces; this set is the single definition).
SCRIPTED_ACTIONS = {"run_script", "webhook"}

MAX_PHRASE = 60

# Which params key each action requires (non-empty string).
_REQUIRED_PARAM = {
    "open_app": "target",
    "open_url": "url",
    "hotkey": "keys",
    "snippet": "name",
    "speak": "text",
    "run_script": "path",
    "webhook": "url",
}
# copy: params optional (empty => copies the utterance itself)


@dataclass
class MatchResult:
    actions: list = field(default_factory=list)
    remaining_text: str = ""


def normalize(text) -> str:
    """Lowercase, punctuation-free, single-spaced — same spirit as
    corrections.normalize_heard so users get one mental model."""
    if not isinstance(text, str):
        return ""
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _prefix_remainder(norm_text, norm_phrase):
    """If norm_phrase is norm_text or its word-boundary prefix, return the
    remainder ('' for a whole match); else None."""
    if norm_text == norm_phrase:
        return ""
    if norm_text.startswith(norm_phrase + " "):
        return norm_text[len(norm_phrase) + 1:]
    return None


def match(text, rules) -> MatchResult:
    """Match the utterance against the rules. Longest phrase wins; exactly one
    rule fires per utterance (no chaining — predictable beats clever). The
    matched action descriptor carries the rule's fields plus the original
    utterance. `consume` controls whether the phrase is removed from the text
    that continues down the pipeline.

    remaining_text is rebuilt from the ORIGINAL text so casing/punctuation of
    genuine dictation survives: for a prefix match we cut the original at the
    point where the normalized remainder begins.
    """
    result = MatchResult(remaining_text=text or "")
    norm_text = normalize(text)
    if not norm_text or not rules:
        return result

    best = None          # (rule, remainder)
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        norm_phrase = normalize(rule.get("phrase", ""))
        if not norm_phrase:
            continue
        rem = _prefix_remainder(norm_text, norm_phrase)
        if rem is None:
            continue
        if best is None or len(norm_phrase) > len(normalize(best[0]["phrase"])):
            best = (rule, rem)

    if best is None:
        return result

    rule, rem = best
    result.actions.append({
        "action": rule.get("action"),
        "params": dict(rule.get("params") or {}),
        "phrase": rule.get("phrase"),
        "trusted": bool(rule.get("trusted", False)),
        "utterance": text,
    })
    if rule.get("consume", True):
        if rem == "":
            result.remaining_text = ""
        else:
            # Cut the original where the remainder's first word starts, so the
            # tail keeps its real casing/punctuation.
            first_word = rem.split(" ", 1)[0]
            m = re.search(r"\b" + re.escape(first_word) + r"\b", text,
                          re.IGNORECASE)
            result.remaining_text = text[m.start():].strip() if m else rem
    return result


def validate_rule(rule, existing) -> "str | None":
    """Return an error message for a bad rule, or None when it's storable."""
    phrase = (rule.get("phrase") or "").strip()
    if not phrase:
        return "A trigger phrase is required."
    if len(phrase) > MAX_PHRASE:
        return f"Trigger phrases are limited to {MAX_PHRASE} characters."
    if not normalize(phrase):
        return "The trigger phrase needs at least one word."
    action = rule.get("action")
    if action not in KNOWN_ACTIONS:
        return f"Unknown action {action!r}."
    params = rule.get("params") or {}
    needed = _REQUIRED_PARAM.get(action)
    if needed:
        value = (params.get(needed) or "").strip() if isinstance(
            params.get(needed), str) else params.get(needed)
        if not value:
            return f"The {action} action needs a {needed!r} value."
        if action in ("open_url", "webhook") and not str(value).startswith(
                ("http://", "https://")):
            return "URLs must start with http:// or https://."
    norm = normalize(phrase)
    for other in existing or []:
        if other is rule:
            continue
        if normalize(other.get("phrase", "")) == norm:
            return "Another rule already uses this trigger phrase."
    return None
