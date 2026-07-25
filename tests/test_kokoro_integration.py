import os

import pytest

from tts.kokoro_engine import KokoroEngine
from tts.types import CancellationToken, TTSConfig


@pytest.mark.kokoro_model
def test_verified_local_kokoro_pack_generates_audio_without_download():
    pack = os.environ.get("ROAR_KOKORO_TEST_PACK")
    if not pack:
        pytest.skip("set ROAR_KOKORO_TEST_PACK to an installed offline pack")
    engine = KokoroEngine()
    config = TTSConfig(enabled=True, model_path=pack)
    try:
        engine.load(config)
        chunks = list(engine.synthesize(
            "ROAR speaks locally.",
            voice="af_heart",
            speed=1.0,
            language="en-us",
            cancellation_token=CancellationToken(),
        ))
        assert chunks
        assert all(chunk.sample_rate == 24000 for chunk in chunks)
        assert sum(chunk.samples.size for chunk in chunks) > 2400
        if os.name == "nt":
            assert engine.metrics["peak_memory_bytes"] > 100 * 1024 * 1024
    finally:
        engine.unload()
