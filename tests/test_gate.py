import numpy as np

import recorder


def test_zeros_buffer_rejected():
    audio = np.zeros(recorder.SAMPLE_RATE, dtype=np.float32)  # 1s of silence
    assert recorder.passes_gate(audio, threshold=0.005, min_duration_s=0.3) is False


def test_too_short_rejected():
    audio = 0.5 * np.ones(int(0.1 * recorder.SAMPLE_RATE), dtype=np.float32)
    assert recorder.passes_gate(audio, threshold=0.005, min_duration_s=0.3) is False


def test_loud_long_signal_passes():
    t = np.linspace(0, 1, recorder.SAMPLE_RATE, endpoint=False)
    audio = (0.1 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    assert recorder.passes_gate(audio, threshold=0.005, min_duration_s=0.3) is True


def test_empty_buffer_rejected():
    assert recorder.passes_gate(np.zeros(0, dtype=np.float32), 0.005, 0.3) is False


def test_make_tone_shape_and_range():
    tone = recorder.make_tone(880, 80)
    assert tone.dtype == np.float32
    assert len(tone) == int(recorder.SAMPLE_RATE * 0.08)
    assert np.max(np.abs(tone)) <= 0.11
