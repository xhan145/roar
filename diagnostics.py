"""Safe diagnostics: operational facts only, never user content.

Pure module. The settings bridge feeds it raw state; collect() returns a dict
that is safe to copy-paste into a bug report — no transcripts, clipboard,
audio, vocabulary, snippets, window titles, or secrets, and private paths are
redacted to their tail.
"""
import os

# keys that may appear in output — anything else is dropped, so a future
# caller can't accidentally leak a new field through diagnostics
SAFE_KEYS = frozenset({
    "version", "edition", "license_status", "model", "device", "language",
    "context_aware", "format_mode",
    "appearance", "overlay_enabled", "streaming_preview",
    "streaming_preview_enabled", "paste_fallback",
    "cleanup_enabled", "history_enabled", "history_count",
    "audio_retention_days", "milestones_enabled", "double_tap_ms",
    "last_injection_method", "config_path", "log_path",
    "last_record_duration_ms", "last_transcription_duration_ms",
    "last_injection_duration_ms",
})

_FORBIDDEN_SUBSTRINGS = ("transcript", "clipboard", "snippet", "vocab",
                         "license_key", "secret", "title", "signature",
                         "private", "email", "audio", "password")


def redact_path(path):
    """Keep the useful tail of a path, hide the user identity in the middle."""
    if not isinstance(path, str) or not path:
        return ""
    home = os.path.expanduser("~")
    if home and path.lower().startswith(home.lower()):
        return "~" + path[len(home):]
    return os.path.join("…", os.path.basename(path))


def collect(info):
    """Filter raw state down to the safe allowlist; redact path values."""
    if not isinstance(info, dict):
        return {}
    out = {}
    for key, value in info.items():
        if key not in SAFE_KEYS:
            continue
        if any(bad in key.lower() for bad in _FORBIDDEN_SUBSTRINGS):
            continue  # belt and braces — SAFE_KEYS should never include these
        if key.endswith("_path"):
            value = redact_path(value)
        out[key] = value
    return out


def redact_diagnostics(data):
    """Public name for the safe-diagnostics filter: allowlist only, paths
    redacted, and never transcript/audio/clipboard/window-title/signature/
    key/email content. Same behavior as `collect`."""
    return collect(data)


def format_report(info):
    """Human-pasteable 'key: value' lines, sorted for diff-friendliness."""
    safe = collect(info)
    return "\n".join(f"{k}: {safe[k]}" for k in sorted(safe))
