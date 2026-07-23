import pytest

import platform_id
from tts import text_sources as sources


def test_clipboard_restore_uses_sequence_race_protection(monkeypatch):
    monkeypatch.setattr(platform_id, "is_windows", lambda: True)
    sequence = [10]
    clipboard = ["old"]
    restored = []

    def send():
        clipboard[0] = "selected"
        sequence[0] = 11

    api = {
        "sequence": lambda: sequence[0],
        "has_text": lambda: True,
        "get": lambda: clipboard[0],
        "set": lambda value: restored.append(value),
        "send": send,
        "sleep": lambda value: None,
    }
    assert sources._copy_selection_with_restore(timeout=0.2, _api=api) == "selected"
    assert restored == ["old"]


def test_clipboard_restore_does_not_overwrite_newer_user_change(monkeypatch):
    monkeypatch.setattr(platform_id, "is_windows", lambda: True)
    calls = {"sequence": 0}
    clipboard = ["old"]
    restored = []

    def sequence():
        calls["sequence"] += 1
        if calls["sequence"] == 1:
            return 20
        if calls["sequence"] == 2:
            return 21
        return 22  # another app/user changed the clipboard before restore

    def send():
        clipboard[0] = "selected"

    api = {
        "sequence": sequence,
        "has_text": lambda: True,
        "get": lambda: clipboard[0],
        "set": lambda value: restored.append(value),
        "send": send,
        "sleep": lambda value: None,
    }
    assert sources._copy_selection_with_restore(timeout=0.2, _api=api) == "selected"
    assert restored == []


def test_clipboard_fallback_refuses_non_text_payload(monkeypatch):
    monkeypatch.setattr(platform_id, "is_windows", lambda: True)
    api = {
        "sequence": lambda: 5,
        "has_text": lambda: False,
        "format_count": lambda: 2,
        "get": lambda: "",
        "set": lambda value: None,
        "send": lambda: None,
        "sleep": lambda value: None,
    }
    with pytest.raises(sources.TextSourceError, match="non-text"):
        sources._copy_selection_with_restore(timeout=0.2, _api=api)


def test_clipboard_fallback_allows_an_empty_clipboard(monkeypatch):
    monkeypatch.setattr(platform_id, "is_windows", lambda: True)
    sequence = [5]
    clipboard = [""]

    def send():
        clipboard[0] = "selected"
        sequence[0] += 1

    api = {
        "sequence": lambda: sequence[0],
        "has_text": lambda: False,
        "format_count": lambda: 0,
        "get": lambda: clipboard[0],
        "set": lambda value: None,
        "send": send,
        "sleep": lambda value: None,
    }
    assert sources._copy_selection_with_restore(
        timeout=0.2, _api=api) == "selected"


def test_source_text_limits_are_enforced():
    with pytest.raises(sources.TextSourceError):
        sources._validate_source_text("")
    with pytest.raises(sources.TextSourceError, match="safety limit"):
        sources._validate_source_text("x" * (sources.MAX_SOURCE_CHARS + 1))
