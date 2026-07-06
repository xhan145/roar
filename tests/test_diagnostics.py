import diagnostics


def test_redact_removes_private_tokens_paths_and_clipboard():
    text = (
        "C:\\Users\\aribe\\secret\\history.db\n"
        "clipboard: copied transcript\n"
        "license_key=abc123\n"
        "window_title=Private Document - Editor"
    )
    redacted = diagnostics.redact(text)
    assert "aribe" not in redacted
    assert "copied transcript" not in redacted
    assert "abc123" not in redacted
    assert "Private Document" not in redacted
    assert "<redacted" in redacted


def test_format_safe_diagnostics_excludes_none_and_sorts():
    data = {"version": "0.13.0", "transcript": "private", "model": None}
    text = diagnostics.format_safe_diagnostics(data)
    assert "version: 0.13.0" in text
    assert "transcript" not in text
    assert "model" not in text
