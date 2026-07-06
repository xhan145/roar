"""Safe diagnostics helpers.

Diagnostics must describe local operational state without exposing transcript,
clipboard, vocabulary, snippet, license secret, audio, or private path data.
"""
import os
import re

PRIVATE_KEYS = {
    "transcript", "text", "clipboard", "audio", "snippet", "snippets",
    "vocabulary", "custom_vocabulary", "license_key", "license_secret",
    "private_key", "window_title",
}

_WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\Users\\[^\\\r\n]+\\[^\r\n ]*")
_SECRET_LINE_RE = re.compile(
    r"(?im)^(.*(?:clipboard|transcript|license[_ -]?(?:key|secret)|"
    r"private[_ -]?key|window[_ -]?title).*)$"
)


def redact(value):
    if value is None:
        return None
    text = str(value)
    text = _WINDOWS_PATH_RE.sub(lambda m: _redact_path(m.group(0)), text)
    text = _SECRET_LINE_RE.sub("<redacted private field>", text)
    return text


def _redact_path(path):
    drive, tail = os.path.splitdrive(path)
    name = os.path.basename(path.rstrip("\\/"))
    return f"{drive}\\Users\\<redacted>\\...\\{name}"


def safe_value(key, value):
    if value is None:
        return None
    if key in PRIVATE_KEYS:
        return "<redacted private field>"
    if isinstance(value, (int, float, bool)):
        return value
    return redact(value)


def filter_safe(data):
    out = {}
    for key, value in data.items():
        if str(key) in PRIVATE_KEYS:
            continue
        safe = safe_value(str(key), value)
        if safe is not None:
            out[str(key)] = safe
    return out


def format_safe_diagnostics(data):
    safe = filter_safe(data)
    return "\n".join(f"{key}: {safe[key]}" for key in sorted(safe))
