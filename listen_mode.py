"""Meeting capture — transcribe SYSTEM audio (what the PC is playing) locally.

A ListenSession opens a WASAPI-loopback input stream on the default output
device, accumulates audio in fixed chunks, transcribes each chunk with the
app's existing (already-loaded) transcriber, and hands the text to a callback.

Boundaries, on purpose:
  * Loopback text is NEVER injected into the focused app and never touches the
    clipboard — it goes to local history (the Live view shows it) and, if the
    user turned that route on, the notes file.
  * Everything stays local, exactly like dictation. No audio is retained.
  * Capturing other people's voices can require their consent where you live.
    The UI says so; this module just captures what the OS is already playing.

The chunker is pure and tested; the stream wrapper is a thin adapter around
sounddevice so tests can drive the chunker with fakes.
"""

import threading

import numpy as np

import recorder as recorder_mod

CHUNK_S = 8           # transcribe every ~8 s of system audio
MODEL_TAG = "listen"  # history rows carry this so the source is visible


class Chunker:
    """Accumulate float32 mono frames; emit fixed-length chunks."""

    def __init__(self, chunk_s=CHUNK_S, sample_rate=recorder_mod.SAMPLE_RATE):
        self._need = int(chunk_s * sample_rate)
        self._buf = []
        self._count = 0

    def add(self, frames):
        """Add frames; return a list of completed chunks (usually 0 or 1)."""
        frames = np.asarray(frames, dtype=np.float32).reshape(-1)
        if frames.size == 0:
            return []
        self._buf.append(frames)
        self._count += frames.size
        out = []
        while self._count >= self._need:
            flat = np.concatenate(self._buf)
            out.append(flat[:self._need])
            rest = flat[self._need:]
            self._buf = [rest] if rest.size else []
            self._count = rest.size
        return out

    def flush(self):
        """Whatever is left (used when the session stops)."""
        if not self._count:
            return None
        flat = np.concatenate(self._buf)
        self._buf, self._count = [], 0
        return flat


def worth_transcribing(chunk, threshold, min_duration_s=1.0) -> bool:
    """Silence gate for loopback chunks — same physics as dictation's gate.
    Expects audio already at recorder_mod.SAMPLE_RATE."""
    if chunk is None:
        return False
    return recorder_mod.passes_gate(np.asarray(chunk, dtype=np.float32),
                                    threshold, min_duration_s)


def resample(chunk, from_rate, to_rate=recorder_mod.SAMPLE_RATE):
    """Linear-interp resample to the transcriber's rate. Loopback devices run
    at their mix rate (usually 44.1/48 kHz); Whisper wants 16 kHz mono. Linear
    interpolation is plenty for speech recognition."""
    chunk = np.asarray(chunk, dtype=np.float32).reshape(-1)
    if from_rate == to_rate or chunk.size == 0:
        return chunk
    n_out = max(1, int(round(chunk.size * to_rate / from_rate)))
    x_old = np.linspace(0.0, 1.0, chunk.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, n_out, endpoint=False)
    return np.interp(x_new, x_old, chunk).astype(np.float32)


class ListenSession:
    """Owns the loopback stream + a transcription worker thread."""

    def __init__(self, transcribe, on_text, threshold, log,
                 chunk_s=CHUNK_S):
        self._transcribe = transcribe    # np.ndarray (16 kHz mono) -> str
        self._on_text = on_text          # str -> None
        self._threshold = threshold
        self._log = log
        self._chunk_s = chunk_s
        self._chunker = Chunker(chunk_s=chunk_s)   # rebuilt at device rate
        self._in_rate = recorder_mod.SAMPLE_RATE
        self._channels = 1
        self._pending = []               # chunks awaiting transcription
        self._cv = threading.Condition()
        self._stop = threading.Event()
        self._stream = None
        self._pa = None
        self._worker = None

    # -- lifecycle ---------------------------------------------------------

    def start(self):
        self._stream = self._open_stream()
        self._worker = threading.Thread(target=self._drain, daemon=True)
        self._worker.start()
        self._stream.start_stream()

    def stop(self):
        self._stop.set()
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
        tail = self._chunker.flush()
        tail = resample(tail, self._in_rate) if tail is not None else None
        if worth_transcribing(tail, self._threshold):
            self._enqueue(tail)
        with self._cv:
            self._cv.notify_all()
        if self._worker is not None:
            self._worker.join(timeout=30)

    # -- stream side (audio callback thread: cheap work only) --------------

    def _open_stream(self):
        """WASAPI loopback of the default output device via PyAudioWPatch —
        upstream PortAudio has no loopback, the patched build does."""
        import pyaudiowpatch as pyaudio
        self._pa = pyaudio.PyAudio()
        dev = self._pa.get_default_wasapi_loopback()
        self._in_rate = int(dev["defaultSampleRate"])
        self._channels = max(1, int(dev["maxInputChannels"]))
        self._chunker = Chunker(chunk_s=self._chunk_s,
                                sample_rate=self._in_rate)
        return self._pa.open(
            format=pyaudio.paFloat32, channels=self._channels,
            rate=self._in_rate, input=True,
            input_device_index=int(dev["index"]),
            frames_per_buffer=2048,
            stream_callback=self._on_frames)

    def _on_frames(self, in_data, frame_count, time_info, status):
        import pyaudiowpatch as pyaudio
        frames = np.frombuffer(in_data, dtype=np.float32)
        if self._channels > 1:
            frames = frames.reshape(-1, self._channels).mean(axis=1)
        for chunk in self._chunker.add(frames):
            rs = resample(chunk, self._in_rate)
            if worth_transcribing(rs, self._threshold):
                self._enqueue(rs)
        return (None, pyaudio.paContinue)

    def _enqueue(self, chunk):
        with self._cv:
            self._pending.append(chunk)
            self._cv.notify()

    # -- worker side -------------------------------------------------------

    def _drain(self):
        while True:
            with self._cv:
                while not self._pending and not self._stop.is_set():
                    self._cv.wait(timeout=1.0)
                if not self._pending and self._stop.is_set():
                    return
                chunk = self._pending.pop(0)
            try:
                text = (self._transcribe(chunk) or "").strip()
                if text:
                    self._on_text(text)
            except Exception as exc:  # capture must never kill the tray
                self._log(f"listen: transcription failed: {exc}")
