"""Explicit, privacy-preserving selected-text and clipboard acquisition."""
from __future__ import annotations

import ctypes
import os
import threading
import time

import platform_id
import window_focus

MAX_SOURCE_CHARS = 20_000
_DENIED_PROCESSES = {
    "credentialuibroker.exe", "logonui.exe", "lsass.exe",
    "consent.exe", "winlogon.exe",
}


class TextSourceError(RuntimeError):
    pass


def read_clipboard_explicit() -> str:
    """Read text only when a direct command calls this function."""
    import pyperclip
    try:
        text = pyperclip.paste()
    except Exception as exc:
        raise TextSourceError("Clipboard text is unavailable") from exc
    return _validate_source_text(text)


def read_selected_text(*, clipboard_fallback=False, timeout=0.6) -> str:
    process = window_focus.active_process()
    if not process or process.lower() in _DENIED_PROCESSES:
        raise TextSourceError("ROAR cannot safely identify selected text here")
    try:
        return _read_uia_selection()
    except TextSourceError:
        if not clipboard_fallback:
            raise
    return _copy_selection_with_restore(timeout=timeout)


def _read_uia_selection() -> str:
    if not platform_id.is_windows():
        raise TextSourceError("Selected-text reading is available on Windows")
    try:
        import uiautomation as auto
        auto.SetGlobalSearchTimeout(0.4)
        control = auto.GetFocusedControl()
        if control is None:
            raise TextSourceError("No accessible focused field was found")
        # Security is fail-closed: inability to read IsPassword is not treated
        # as evidence that a field is safe.
        try:
            is_password = bool(control.IsPassword)
        except Exception as exc:
            raise TextSourceError(
                "The focused field's security status is unknown") from exc
        if is_password:
            raise TextSourceError("Password fields cannot be read aloud")
        pattern = control.GetPattern(auto.PatternId.TextPattern)
        if pattern is None:
            raise TextSourceError(
                "The focused application does not expose a text selection")
        ranges = pattern.GetSelection()
        text = "\n".join(part.GetText(MAX_SOURCE_CHARS + 1) for part in ranges)
        return _validate_source_text(text)
    except TextSourceError:
        raise
    except Exception as exc:
        raise TextSourceError(
            "The focused application did not expose a safe selection") from exc


def _copy_selection_with_restore(*, timeout, _api=None):
    """Use Ctrl+C only after an explicit command and protect newer clipboard data."""
    if not platform_id.is_windows():
        raise TextSourceError("Clipboard selection fallback is Windows-only")
    if _api is None:
        import keyboard
        import pyperclip
        user32 = ctypes.windll.user32
        _api = {
            "sequence": lambda: int(user32.GetClipboardSequenceNumber()),
            "has_text": lambda: bool(user32.IsClipboardFormatAvailable(13)),
            "format_count": lambda: int(user32.CountClipboardFormats()),
            "get": pyperclip.paste,
            "set": pyperclip.copy,
            "send": lambda: keyboard.send("ctrl+c"),
            "sleep": time.sleep,
        }
    before_sequence = _api["sequence"]()
    had_text = _api["has_text"]()
    try:
        previous = _api["get"]() if had_text else ""
    except Exception as exc:
        raise TextSourceError(
            "ROAR could not preserve the existing clipboard") from exc
    # Refuse to destroy a non-text clipboard payload that pyperclip cannot
    # faithfully restore.
    format_count = _api.get(
        "format_count", lambda: 1 if before_sequence else 0)()
    if not had_text and format_count:
        raise TextSourceError(
            "Clipboard fallback cannot preserve the current non-text clipboard")

    _api["send"]()
    deadline = time.monotonic() + max(0.1, min(float(timeout), 1.5))
    copied_sequence = before_sequence
    while time.monotonic() < deadline:
        copied_sequence = _api["sequence"]()
        if copied_sequence != before_sequence:
            break
        _api["sleep"](0.02)
    if copied_sequence == before_sequence:
        raise TextSourceError("The application did not copy selected text")
    try:
        selected = _api["get"]()
    except Exception as exc:
        raise TextSourceError("Copied text is unavailable") from exc
    finally:
        # Restore only if no user/app clipboard write occurred after Ctrl+C.
        if _api["sequence"]() == copied_sequence:
            try:
                _api["set"](previous)
            except Exception:
                pass
    return _validate_source_text(selected)


def _validate_source_text(text):
    if not isinstance(text, str) or not text.strip():
        raise TextSourceError("No text is available to read")
    if len(text) > MAX_SOURCE_CHARS:
        raise TextSourceError(
            f"Text exceeds the {MAX_SOURCE_CHARS:,}-character safety limit")
    return text.strip()
