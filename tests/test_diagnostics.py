import os

import diagnostics


def test_collect_allowlist_only():
    raw = {
        "version": "0.16.0", "model": "small.en", "history_count": 5,
        "transcript": "SECRET SPEECH", "clipboard": "PASSWORD",
        "snippets": {"sig": "private"}, "vocabulary": ["name"],
        "window_title": "banking - Chrome", "license_key": "ABC",
    }
    safe = diagnostics.collect(raw)
    assert safe == {"version": "0.16.0", "model": "small.en",
                    "history_count": 5}


def test_paths_are_redacted():
    home = os.path.expanduser("~")
    raw = {"config_path": os.path.join(home, "AppData", "config.json"),
           "log_path": r"D:\weird\place\roar.log"}
    safe = diagnostics.collect(raw)
    assert safe["config_path"].startswith("~")
    assert home not in safe["config_path"]
    assert safe["log_path"].endswith("roar.log")
    assert "weird" not in safe["log_path"]


def test_collect_tolerates_garbage():
    assert diagnostics.collect(None) == {}
    assert diagnostics.collect("nope") == {}


def test_format_report_sorted_lines():
    rep = diagnostics.format_report({"version": "1", "model": "m"})
    assert rep.splitlines() == ["model: m", "version: 1"]


def test_redact_diagnostics_keeps_safe_drops_sensitive():
    raw = {
        "version": "0.17.0", "edition": "core",
        "license_status": "Not activated",
        "last_transcription_duration_ms": 320,
        "transcript": "SECRET SPEECH", "audio_path": r"C:\Users\me\rec.wav",
        "clipboard": "PASSWORD", "signature": "base64sigAAA==",
        "email": "me@example.com", "window_title": "banking - Chrome",
    }
    out = diagnostics.redact_diagnostics(raw)
    assert out["version"] == "0.17.0"
    assert out["edition"] == "core"
    assert out["license_status"] == "Not activated"
    assert out["last_transcription_duration_ms"] == 320
    blob = str(out)
    for leaked in ("SECRET", "PASSWORD", "base64sigAAA", "me@example.com",
                   "banking", "rec.wav"):
        assert leaked not in blob
    for dropped in ("transcript", "audio_path", "clipboard", "signature",
                    "email", "window_title"):
        assert dropped not in out
