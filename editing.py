"""Spoken editing commands: standalone-utterance detection + the injection
stack that makes undo possible. Pure logic — win32/keyboard stay in app.py."""
from collections import deque
from typing import NamedTuple

SCRATCH_PHRASES = frozenset({"scratch that", "scratch it", "undo that"})
MAX_DEPTH = 10


# Whisper decorates short utterances: trailing ellipses, wrapping quotes,
# dashes. Strip that ornamentation before matching — words stay untouched.
_ORNAMENT = " .,!?;:…\"'`—–-“”‘’"


def is_scratch(text) -> bool:
    """True only when the ENTIRE utterance is a scratch phrase — a sentence
    that merely contains one must be typed, not executed."""
    if not isinstance(text, str):
        return False
    norm = " ".join(text.lower().split()).strip(_ORNAMENT)
    return norm in SCRATCH_PHRASES


def keystroke_len(typed) -> int:
    """Backspaces needed to undo `typed`. keyboard.write emits one
    KEYEVENTF_UNICODE event per UTF-16 code UNIT, so an astral char (emoji,
    U+10000+) costs 2 keystrokes though it is one Python code point. Equal to
    len() for all BMP text (every ordinary dictation)."""
    return len(str(typed).encode("utf-16-le")) // 2


class Entry(NamedTuple):
    typed: str        # the PREPARED string actually sent (incl. trailing space)
    hwnd: int         # foreground window at inject time
    history_id: object  # history row id or None


class InjectionStack:
    def __init__(self):
        self._items = deque(maxlen=MAX_DEPTH)

    def push(self, typed, hwnd, history_id):
        self._items.append(Entry(typed, hwnd, history_id))

    def pop_if(self, hwnd):
        """Pop the newest entry only when it was typed into the SAME window;
        otherwise leave the stack untouched and return None."""
        if self._items and self._items[-1].hwnd == hwnd:
            return self._items.pop()
        return None
