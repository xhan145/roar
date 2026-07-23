"""Sentence- and paragraph-aware pure text chunking."""
from __future__ import annotations

import re
import unicodedata

from .types import MAX_TEXT_CHARS

DEFAULT_TARGET_CHARS = 320
DEFAULT_MAX_CHARS = 480
_ABBREVIATIONS = {
    "a.m.", "p.m.", "e.g.", "i.e.", "etc.", "vs.", "mr.", "mrs.", "ms.",
    "dr.", "prof.", "sr.", "jr.", "st.", "no.", "fig.", "inc.", "ltd.",
    "u.s.", "u.k.",
}
_SENTENCE_END = re.compile(r"(?<=[.!?…])(?:[\"'”’)\]]*)\s+")
_LIST_ITEM = re.compile(r"(?m)^(?:\s*[-*•]\s+|\s*\d+[.)]\s+)")


def normalize_text(text: str, *, max_chars: int = MAX_TEXT_CHARS) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    text = unicodedata.normalize("NFC", text).replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text
                   if ch in "\n\t" or unicodedata.category(ch) != "Cc")
    text = text.strip()
    if not text:
        raise ValueError("text is empty")
    if len(text) > max_chars:
        raise ValueError(f"text exceeds {max_chars:,} characters")
    return text


def chunk_text(
    text: str,
    *,
    target_chars: int = DEFAULT_TARGET_CHARS,
    max_chars: int = DEFAULT_MAX_CHARS,
    input_limit: int = MAX_TEXT_CHARS,
) -> list[str]:
    """Split text without recklessly breaking abbreviations or tiny fragments."""
    text = normalize_text(text, max_chars=input_limit)
    target_chars = max(80, min(int(target_chars), int(max_chars)))
    max_chars = max(target_chars, min(int(max_chars), 1000))

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    units: list[str] = []
    for paragraph in paragraphs:
        lines = [line.strip() for line in paragraph.split("\n") if line.strip()]
        for line in lines:
            if _LIST_ITEM.match(line):
                units.append(line)
            else:
                units.extend(_sentences(line))

    chunks: list[str] = []
    current = ""
    for unit in units:
        for part in _split_oversized(unit, max_chars):
            candidate = f"{current} {part}".strip() if current else part
            if current and len(candidate) > target_chars:
                chunks.append(current)
                current = part
            else:
                current = candidate
            if len(current) >= max_chars:
                chunks.append(current)
                current = ""
    if current:
        chunks.append(current)

    # Avoid a tiny tail when it safely fits in the previous chunk.
    if (len(chunks) >= 2 and len(chunks[-1]) < 40
            and len(chunks[-2]) + 1 + len(chunks[-1]) <= max_chars):
        chunks[-2] += " " + chunks.pop()
    return chunks


def _sentences(text: str) -> list[str]:
    starts = [0]
    for match in _SENTENCE_END.finditer(text):
        left = text[starts[-1]:match.start()].strip().lower()
        last = left.rsplit(" ", 1)[-1] if left else ""
        if last in _ABBREVIATIONS or _looks_like_initial(last):
            continue
        starts.append(match.end())
    starts.append(len(text) + 1)
    return [text[starts[i]:starts[i + 1] - 1].strip()
            for i in range(len(starts) - 1)
            if text[starts[i]:starts[i + 1] - 1].strip()]


def _looks_like_initial(token: str) -> bool:
    return bool(re.fullmatch(r"(?:[a-z]\.){1,3}", token))


def _split_oversized(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts = []
    remaining = text
    while len(remaining) > max_chars:
        cut = max(
            remaining.rfind(sep, 0, max_chars + 1)
            for sep in ("; ", ": ", ", ", " ")
        )
        if cut < max_chars // 2:
            cut = max_chars
        else:
            cut += 1
        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        parts.append(remaining)
    return parts
