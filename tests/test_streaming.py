import numpy as np

import recorder


def test_tail_window_short_passthrough():
    a = np.ones(recorder.SAMPLE_RATE, dtype=np.float32)  # 1s
    out = recorder.tail_window(a, seconds=15.0)
    assert out is a


def test_tail_window_cuts_long_buffer():
    a = np.arange(20 * recorder.SAMPLE_RATE, dtype=np.float32)
    out = recorder.tail_window(a, seconds=15.0)
    assert out.size == 15 * recorder.SAMPLE_RATE
    assert out[-1] == a[-1]


def test_snapshot_copy_and_empty():
    r = recorder.Recorder()
    assert r.snapshot().size == 0
    with r._lock:
        r._chunks = [np.ones(100, dtype=np.float32)]
    snap = r.snapshot()
    assert snap.size == 100
    snap[0] = 5.0
    assert r._chunks[0][0] == 1.0  # copy, not view


def test_on_level_called_per_block():
    seen = []
    r = recorder.Recorder(on_level=seen.append)
    block = 0.08 * np.ones((160, 1), dtype=np.float32)
    r._callback(block, 160, None, None)
    assert len(seen) == 1 and 0.9 <= seen[0] <= 1.0
