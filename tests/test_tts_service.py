import time

from tts.fake_engine import FakeTTSEngine
from tts.playback import NullPlaybackController
from tts.service import TTSService
from tts.types import TTSConfig, TTSState


def wait_for(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def enabled_config():
    return TTSConfig(enabled=True)


def test_service_loads_once_and_returns_to_ready():
    engine = FakeTTSEngine()
    playback = NullPlaybackController()
    states = []
    service = TTSService(
        engine, enabled_config(), playback=playback,
        listener=lambda state, fields: states.append(state))
    try:
        assert service.speak("One sentence.", source="typed")
        assert wait_for(lambda: service.state == TTSState.READY)
        assert engine.load_count == 1
        assert playback.chunks
        assert TTSState.SYNTHESIZING in states
        assert TTSState.PLAYING in states
        service.speak("Another sentence.", source="typed")
        assert wait_for(lambda: service.state == TTSState.READY)
        assert engine.load_count == 1
    finally:
        service.shutdown()


def test_service_stop_cancels_and_discards_stale_requests():
    class SlowPlayback(NullPlaybackController):
        def play(self, chunks, **kwargs):
            self.stopped = False
            for chunk in chunks:
                time.sleep(0.08)
                if kwargs["cancellation_token"].cancelled:
                    from tts.types import TTSCancelled
                    raise TTSCancelled()
                self.chunks.append(chunk)

    service = TTSService(
        FakeTTSEngine(), enabled_config(), playback=SlowPlayback())
    try:
        service.speak("First request " * 40)
        assert wait_for(lambda: service.state in (
            TTSState.SYNTHESIZING, TTSState.PLAYING))
        service.speak("Latest request")
        assert wait_for(lambda: service.state == TTSState.READY)
        assert service._last_text == "Latest request"
        assert service._jobs.empty()
    finally:
        service.shutdown()


def test_pause_resume_and_shutdown_are_deterministic():
    class BlockingPlayback(NullPlaybackController):
        def play(self, chunks, **kwargs):
            self.stopped = False
            if kwargs.get("on_started"):
                kwargs["on_started"]()
            while not kwargs["cancellation_token"].wait(0.01):
                if self.stopped:
                    break

    service = TTSService(
        FakeTTSEngine(), enabled_config(), playback=BlockingPlayback())
    service.speak("Keep speaking for this test")
    assert wait_for(lambda: service.state == TTSState.PLAYING)
    assert service.pause()
    assert service.state == TTSState.PAUSED
    assert service.resume()
    assert service.state == TTSState.PLAYING
    service.shutdown()
    assert not service._worker.is_alive()
    assert service.state == TTSState.UNLOADED


def test_engine_errors_do_not_escape_background_thread():
    events = []
    service = TTSService(
        FakeTTSEngine(fail_on="synthesize"), enabled_config(),
        playback=NullPlaybackController(),
        logger=lambda event, fields: events.append((event, fields)))
    try:
        service.speak("Failure is isolated")
        assert wait_for(lambda: service.state == TTSState.ERROR)
        assert any(event == "tts.playback.failed" for event, _ in events)
    finally:
        service.shutdown()


def test_repeat_only_remembers_explicit_sources():
    service = TTSService(
        FakeTTSEngine(), enabled_config(), playback=NullPlaybackController())
    try:
        service.speak("Explicit text", source="clipboard")
        assert wait_for(lambda: service.state == TTSState.READY)
        service.speak("Status only", source="status", remember=False)
        assert wait_for(lambda: service.state == TTSState.READY)
        assert service._last_text == "Explicit text"
        assert service.repeat_last()
    finally:
        service.shutdown()
