"""Read Aloud responsiveness fixes: preload-by-default, keep-warm, longer
worker startup timeout. Regression guard for the "slow or not at all" report —
the Kokoro cold load is ~20-90s, so paying it once (preload) and not tearing the
worker down under a warm session is what keeps Read Aloud responsive.
"""
import time

from tts.fake_engine import FakeTTSEngine
from tts.playback import NullPlaybackController
from tts.service import TTSService
from tts.types import TTSConfig, TTSState
import tts.kokoro_engine as kokoro_engine


def _wait(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


# --- defaults ---------------------------------------------------------------

def test_default_config_preloads_and_keeps_a_gentle_idle():
    cfg = TTSConfig()
    assert cfg.preload_model is True
    assert cfg.unload_after_idle_minutes == 30


def test_from_mapping_defaults_match_dataclass():
    cfg = TTSConfig.from_mapping({})
    assert cfg.preload_model is True
    assert cfg.unload_after_idle_minutes == 30


def test_from_mapping_still_honors_explicit_off():
    cfg = TTSConfig.from_mapping({
        "tts_preload_model": False,
        "tts_unload_after_idle_minutes": 5,
    })
    assert cfg.preload_model is False
    assert cfg.unload_after_idle_minutes == 5


# --- keep-warm when preloaded ----------------------------------------------

def test_preloaded_service_does_not_idle_unload():
    engine = FakeTTSEngine()
    cfg = TTSConfig(enabled=True, preload_model=True,
                    unload_after_idle_minutes=1)  # tiny idle would normally unload
    service = TTSService(engine, cfg, playback=NullPlaybackController())
    try:
        assert service.speak("Warm it up.", source="typed")
        assert _wait(lambda: service.state == TTSState.READY)
        # Pretend a long idle has elapsed.
        service._last_active = time.monotonic() - 10_000
        # Let the worker loop run _maybe_unload_idle a few times.
        time.sleep(0.4)
        assert service._loaded is True
        assert service.state == TTSState.READY
    finally:
        service.shutdown()


def test_non_preloaded_service_still_idle_unloads():
    engine = FakeTTSEngine()
    cfg = TTSConfig(enabled=True, preload_model=False,
                    unload_after_idle_minutes=1)
    service = TTSService(engine, cfg, playback=NullPlaybackController())
    try:
        assert service.speak("Load once.", source="typed")
        assert _wait(lambda: service.state == TTSState.READY)
        service._last_active = time.monotonic() - 10_000
        assert _wait(lambda: service.state == TTSState.UNLOADED, timeout=2)
        assert service._loaded is False
    finally:
        service.shutdown()


# --- worker startup timeout -------------------------------------------------

def test_startup_timeout_is_generous():
    # Cold load is ~20s idle, up to ~90s under load; a 90s ceiling times out
    # exactly the slow-but-working case that produced "not at all".
    assert kokoro_engine.STARTUP_TIMEOUT_SECONDS >= 180
