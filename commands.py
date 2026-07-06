"""Spoken-command replacement and text normalization. Pure functions."""
import re

import cleanup as cleanup_mod
import snippets as snippets_mod

CODE_SYMBOLS = {
    "new line": "\n",
    "tab": "\t",
    "colon": ": ",
    "semicolon": "; ",
    "comma": ", ",
    "period": ". ",
    "dot": ".",
    "slash": "/",
    "backslash": "\\",
    "open paren": "(",
    "close paren": ")",
    "open bracket": "[",
    "close bracket": "]",
    "open brace": "{",
    "close brace": "}",
    "equals": "=",
    "plus": "+",
    "minus": "-",
    "underscore": "_",
}


def apply_replacements(text: str, replacements: dict) -> str:
    """Replace spoken phrases (case-insensitive, word-bounded), absorbing
    surrounding punctuation and spaces so 'foo. New line. bar' -> 'foo.\nbar'."""
    for phrase in sorted(replacements, key=len, reverse=True):
        repl = replacements[phrase]
        # Leading side absorbs only whitespace + an optional comma (a sentence-
        # ending period before the command must survive: "there. New line" ->
        # "there.\n"). Trailing side absorbs the command's own punctuation.
        pattern = re.compile(
            r"[ \t]*,?[ \t]*\b" + re.escape(phrase) + r"\b[ \t]*[,.!?;:]?[ \t]*",
            re.IGNORECASE,
        )
        text = pattern.sub(lambda m, r=repl: r, text)
    return text


def process(text: str, replacements: dict, snippets=None,
            snippet_keyword: str = "snippet", cleanup: bool = False,
            discourse_fillers: bool = False, mode: str = "clean") -> str:
    """Full pipeline: strip -> cleanup -> replacements -> capitalize -> snippets.
    Cleanup runs first so capitalization lands on the real first word and
    commands/snippets see already-cleaned text. Snippets run last so expansions
    are injected verbatim. Returns '' when there is nothing worth injecting."""
    text = text.strip()
    if not text:
        return ""
    mode = mode if mode in {"raw", "clean", "code"} else "clean"
    if cleanup and mode == "clean":
        text = cleanup_mod.clean(text, discourse=discourse_fillers)
        if not text:
            return ""
    if mode == "code":
        text = apply_replacements(text, CODE_SYMBOLS)
    elif mode == "clean":
        text = apply_replacements(text, replacements)
    if mode != "code":
        for i, ch in enumerate(text):
            if ch.isalpha():
                if ch.islower():
                    text = text[:i] + ch.upper() + text[i + 1:]
                break
    if snippets:
        text = snippets_mod.expand(text, snippets, keyword=snippet_keyword)
    if not text.strip():
        # whitespace-only result: keep it only if it came from an explicit
        # newline command (e.g. user said just "new line")
        return text if "\n" in text else ""
    return text
