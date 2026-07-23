import diagnostics
import status
from pathlib import Path


def test_tts_status_allowlist_never_persists_content(tmp_path):
    path = tmp_path / "status.json"
    status.write_status(
        str(path),
        tts_state="playing",
        tts_voice="af_heart",
        tts_last_elapsed_ms=42,
        text="private selected words",
        phonemes="secret phonemes",
        clipboard="private clipboard",
        generated_audio=b"audio",
    )
    saved = status.read_status(str(path))
    assert saved["tts_state"] == "playing"
    assert saved["tts_voice"] == "af_heart"
    assert "text" not in saved
    assert "phonemes" not in saved
    assert "clipboard" not in saved
    assert "generated_audio" not in saved


def test_tts_diagnostics_are_allowlist_only_and_paths_are_redacted():
    safe = diagnostics.collect({
        "tts_engine": "kokoro",
        "tts_model_version": "1.0",
        "tts_voice": "af_heart",
        "tts_language": "en-us",
        "tts_last_first_audio_ms": 125,
        "spoken_text": "do not expose",
        "selected_text": "do not expose",
        "phoneme_text": "do not expose",
        "clipboard": "do not expose",
        "tts_model_path": r"C:\Users\private\model",
    })
    assert safe["tts_engine"] == "kokoro"
    assert safe["tts_voice"] == "af_heart"
    assert all("expose" not in str(value) for value in safe.values())
    assert "tts_model_path" not in safe


def test_tts_structured_events_do_not_receive_text():
    from tts.fake_engine import FakeTTSEngine
    from tts.playback import NullPlaybackController
    from tts.service import TTSService
    from tts.types import TTSConfig, TTSState
    import time

    events = []
    service = TTSService(
        FakeTTSEngine(), TTSConfig(enabled=True),
        playback=NullPlaybackController(),
        logger=lambda name, fields: events.append((name, fields)))
    try:
        secret = "highly private phrase"
        service.speak(secret)
        deadline = time.monotonic() + 2
        while service.state != TTSState.READY and time.monotonic() < deadline:
            time.sleep(0.01)
        serialized = repr(events)
        assert secret not in serialized
        assert all("text" not in fields for _, fields in events)
    finally:
        service.shutdown()


def test_tts_runtime_has_no_network_call_sites():
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("tts").glob("*.py"))
    assert "urlopen(" not in combined
    assert "requests.get(" not in combined
    assert "requests.post(" not in combined
    assert "socket.socket(" not in combined
    assert "http.client" not in combined
