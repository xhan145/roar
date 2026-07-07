import os
import sys
import wave

import numpy as np

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS)
import benchmark_transcription as bench  # noqa: E402


def test_candidates_always_include_cpu():
    legs = bench.candidates({"cuda": False, "cuda_compute": set()})
    assert legs and legs[0][1] == "cpu"
    assert all(dev == "cpu" for _, dev, _ in legs)


def test_candidates_add_two_cuda_legs_when_available():
    legs = bench.candidates({"cuda": True,
                             "cuda_compute": {"float16", "int8_float16", "int8"}})
    devs = [d for _, d, _ in legs]
    assert "cpu" in devs and devs.count("cuda") == 2
    computes = [c for _, d, c in legs if d == "cuda"]
    assert "float16" in computes and "int8_float16" in computes


def test_candidates_skip_unsupported_cuda_compute():
    legs = bench.candidates({"cuda": True, "cuda_compute": {"float16"}})  # no int8_float16
    computes = [c for _, d, c in legs if d == "cuda"]
    assert computes == ["float16"]


def test_load_audio_roundtrip(tmp_path):
    p = str(tmp_path / "t.wav")
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(np.zeros(16000, dtype=np.int16).tobytes())
    audio, dur = bench.load_audio(p)
    assert audio.dtype == np.float32
    assert abs(dur - 1.0) < 0.01
