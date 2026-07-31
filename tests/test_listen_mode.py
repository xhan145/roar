"""Meeting capture: pure chunking, gating, worker drain, and boundaries."""

import numpy as np

import entitlements as ent
import listen_mode
import recorder as recorder_mod

SR = recorder_mod.SAMPLE_RATE


def tone(seconds, amp=0.2):
    t = np.linspace(0, seconds, int(SR * seconds), endpoint=False)
    return (amp * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


# -- chunker ---------------------------------------------------------------

def test_chunker_emits_fixed_chunks():
    c = listen_mode.Chunker(chunk_s=1)
    assert c.add(tone(0.5)) == []
    chunks = c.add(tone(0.6))
    assert len(chunks) == 1 and chunks[0].size == SR


def test_chunker_carries_the_remainder():
    c = listen_mode.Chunker(chunk_s=1)
    c.add(tone(1.4))
    tail = c.flush()
    assert tail is not None and tail.size == int(0.4 * SR)
    assert c.flush() is None


def test_chunker_handles_multi_chunk_bursts():
    c = listen_mode.Chunker(chunk_s=1)
    chunks = c.add(tone(3.2))
    assert len(chunks) == 3
    assert all(ch.size == SR for ch in chunks)


# -- gate ------------------------------------------------------------------

def test_silence_is_not_transcribed():
    silent = np.zeros(SR * 2, dtype=np.float32)
    assert listen_mode.worth_transcribing(silent, threshold=0.005) is False
    assert listen_mode.worth_transcribing(None, threshold=0.005) is False
    assert listen_mode.worth_transcribing(tone(2), threshold=0.005) is True


# -- session worker --------------------------------------------------------

def _session(texts):
    got = []
    s = listen_mode.ListenSession(
        transcribe=lambda chunk: texts.pop(0) if texts else "",
        on_text=got.append, threshold=0.005, log=lambda m: None, chunk_s=1)
    return s, got


def test_worker_drains_enqueued_chunks_and_stops():
    s, got = _session(["hello", "world"])
    s._worker = None
    import threading
    s._worker = threading.Thread(target=s._drain, daemon=True)
    s._worker.start()
    s._enqueue(tone(1))
    s._enqueue(tone(1))
    s._stop.set()
    with s._cv:
        s._cv.notify_all()
    s._worker.join(timeout=10)
    assert got == ["hello", "world"]


def test_transcription_failure_is_logged_not_fatal():
    logs = []
    s = listen_mode.ListenSession(
        transcribe=lambda c: (_ for _ in ()).throw(RuntimeError("boom")),
        on_text=lambda t: None, threshold=0.005, log=logs.append, chunk_s=1)
    import threading
    s._worker = threading.Thread(target=s._drain, daemon=True)
    s._worker.start()
    s._enqueue(tone(1))
    s._stop.set()
    with s._cv:
        s._cv.notify_all()
    s._worker.join(timeout=10)
    assert any("failed" in l for l in logs)


def test_stop_flushes_the_tail():
    """stop() must transcribe leftover audio shorter than a full chunk."""
    got = []
    s = listen_mode.ListenSession(
        transcribe=lambda c: "tail text", on_text=got.append,
        threshold=0.005, log=lambda m: None, chunk_s=10)
    import threading
    s._worker = threading.Thread(target=s._drain, daemon=True)
    s._worker.start()
    s._chunker.add(tone(2))    # under one chunk
    s.stop()
    assert got == ["tail text"]


# -- boundaries ------------------------------------------------------------

def test_capture_feature_is_registered_pro():
    assert "capture.system_audio" in ent.KNOWN_FEATURES
    assert ent.minimum_edition_for("capture.system_audio") == ent.PRO


def test_listen_module_never_touches_injection_or_clipboard():
    import pathlib
    src = pathlib.Path("listen_mode.py").read_text(encoding="utf-8")
    for forbidden in ("injector", "pyperclip", "inject_text", "clipboard_guard"):
        assert forbidden not in src.replace("clipboard —", ""), forbidden


# -- resampling ------------------------------------------------------------

def test_resample_changes_length_proportionally():
    chunk = tone(1)  # 1 s at 16 kHz
    out = listen_mode.resample(chunk, from_rate=SR, to_rate=SR)
    assert out.size == chunk.size                      # no-op path
    up = listen_mode.resample(chunk, from_rate=8000)   # pretend it was 8 kHz
    assert up.size == chunk.size * 2                   # 8k -> 16k doubles
    down = listen_mode.resample(chunk, from_rate=32000)
    assert down.size == chunk.size // 2


def test_resample_preserves_signal_energy_roughly():
    chunk = tone(1)
    out = listen_mode.resample(chunk, from_rate=48000)
    assert out.dtype == np.float32
    assert 0.05 < float(np.abs(out).mean()) < 0.3
