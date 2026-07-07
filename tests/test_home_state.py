import settings_ui
import status


EXPECTED_KEYS = {
    "app_version", "is_running", "dictation_state", "active_profile",
    "active_profile_description", "current_model", "current_device",
    "injection_method", "paste_fallback_enabled", "autostart_enabled",
    "session_duration_seconds", "session_word_count", "last_latency_seconds",
    "last_transcription_preview", "last_transcription_word_count",
    "last_transcription_timestamp", "last_injection_status", "hotkeys",
    "diagnostics_safe_summary", "words_today", "words_this_week", "milestone",
    "controls_enabled",
}
# last_transcription_preview is allowed (same preview as History); raw private
# fields must never appear as keys.
FORBIDDEN_KEYS = {"transcript", "clipboard", "raw_clipboard", "audio_path",
                  "window_title", "signature", "email"}


class _EmptyHist:
    def list(self, **k):
        return []

    def total_words(self):
        return 0

    def unlocks(self):
        return {}


def _api(tmp_path):
    return settings_ui.SettingsAPI(config_path=str(tmp_path / "config.json"))


def test_shape_and_no_private_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_ui.SettingsAPI, "_history",
                        property(lambda self: _EmptyHist()))
    out = _api(tmp_path).get_home_state()
    assert set(out) == EXPECTED_KEYS
    assert not (set(out) & FORBIDDEN_KEYS)
    assert isinstance(out["last_transcription_preview"], str)
    assert len(out["last_transcription_preview"]) <= 160
    assert out["app_version"]


def test_safe_defaults_when_everything_missing(tmp_path, monkeypatch):
    class Boom:
        def list(self, **k):
            raise RuntimeError("db corrupt")

        def total_words(self):
            raise RuntimeError("db corrupt")

        def unlocks(self):
            raise RuntimeError("db corrupt")

    monkeypatch.setattr(settings_ui.SettingsAPI, "_history",
                        property(lambda self: Boom()))
    monkeypatch.setattr(status, "read_status", lambda path=None: {})
    out = _api(tmp_path).get_home_state()
    assert out["words_today"] == 0
    assert out["session_word_count"] == 0
    assert out["dictation_state"] == "idle"
    assert out["last_transcription_preview"] == ""


def test_bounds_and_does_not_leak_transcript_tail(tmp_path, monkeypatch):
    long_text = "word " * 100 + "SENSITIVE_TAIL"

    class Hist:
        def list(self, **k):
            return [{"text": long_text, "word_count": 101,
                     "ts_utc": 1_700_000_000.0, "duration_s": 3.2}]

        def total_words(self):
            return 101

        def unlocks(self):
            return {}

    monkeypatch.setattr(settings_ui.SettingsAPI, "_history",
                        property(lambda self: Hist()))
    out = _api(tmp_path).get_home_state()
    assert len(out["last_transcription_preview"]) == 160
    assert "SENSITIVE_TAIL" not in out["last_transcription_preview"]
    assert out["last_latency_seconds"] == 3.2
