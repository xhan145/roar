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


def test_defaults_have_streaming_keys():
    from config import DEFAULTS
    assert DEFAULTS["overlay_enabled"] is True
    assert DEFAULTS["streaming_preview"] is True


class _StubOverlay:
    def __init__(self):
        self.partials = []
        self.hidden = 0

    def set_partial(self, t):
        self.partials.append(t)

    def hide(self):
        self.hidden += 1


def _partial_app(tmp_path):
    from tests.test_capture_integration import _make_app
    a = _make_app(tmp_path)
    a._session_gen = 3
    a.overlay = _StubOverlay()
    a.cfg["streaming_preview"] = True
    a.state = a.RECORDING
    calls = []
    a.transcriber.transcribe = lambda audio: calls.append(len(audio)) or "partial words"
    a.recorder = recorder.Recorder()
    with a.recorder._lock:
        a.recorder._chunks = [np.ones(recorder.SAMPLE_RATE, dtype=np.float32)]
    return a, calls


def test_partial_stale_generation_skipped(tmp_path):
    a, calls = _partial_app(tmp_path)
    a._handle_partial(2)   # stale gen
    assert calls == [] and a.overlay.partials == []
    a.history.close()


def test_partial_live_generation_previews(tmp_path):
    a, calls = _partial_app(tmp_path)
    a._handle_partial(3)
    assert calls == [recorder.SAMPLE_RATE]        # tail-windowed snapshot
    assert a.overlay.partials == ["partial words"]
    a.history.close()


def test_partial_respects_preview_toggle(tmp_path):
    a, calls = _partial_app(tmp_path)
    a.cfg["streaming_preview"] = False
    a._handle_partial(3)
    assert calls == []
    a.history.close()
