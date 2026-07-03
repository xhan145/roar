"""Microphone capture (16 kHz mono float32), RMS energy gate, feedback tones."""
import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


def rms(audio: np.ndarray) -> float:
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))


def normalize_level(rms_val: float) -> float:
    """Map block RMS to a 0..1 display level for the overlay bars."""
    return min(1.0, rms_val / 0.08)


def tail_window(audio, seconds=15.0):
    """Last N seconds of a buffer (whole buffer when shorter)."""
    n = int(seconds * SAMPLE_RATE)
    return audio if audio.size <= n else audio[-n:]


def passes_gate(audio: np.ndarray, threshold: float, min_duration_s: float) -> bool:
    """True when the clip is long enough and loud enough to be worth transcribing."""
    if audio.size < int(max(0.0, min_duration_s) * SAMPLE_RATE):
        return False
    return rms(audio) >= threshold


def make_tone(freq_hz: float, ms: int, amplitude: float = 0.1) -> np.ndarray:
    n = int(SAMPLE_RATE * ms / 1000)
    t = np.linspace(0, ms / 1000, n, endpoint=False)
    tone = (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)
    fade = max(1, int(SAMPLE_RATE * 0.005))  # 5 ms fade to avoid clicks
    env = np.ones(n, dtype=np.float32)
    env[:fade] = np.linspace(0.0, 1.0, fade)
    env[-fade:] = np.linspace(1.0, 0.0, fade)
    return tone * env


def make_chime(freqs, note_ms=110, overlap_ms=40, amplitude=0.07):
    """Soft overlapping notes with exponential decay — no assets needed."""
    notes = []
    for f in freqs:
        n = int(SAMPLE_RATE * note_ms / 1000)
        t = np.linspace(0, note_ms / 1000, n, endpoint=False)
        env = np.exp(-t * 22.0).astype(np.float32)
        notes.append((amplitude * np.sin(2 * np.pi * f * t)).astype(np.float32) * env)
    step = max(1, int(SAMPLE_RATE * (note_ms - overlap_ms) / 1000))
    total = step * (len(freqs) - 1) + len(notes[0])
    out = np.zeros(total, dtype=np.float32)
    for i, note in enumerate(notes):
        out[i * step:i * step + len(note)] += note
    return np.clip(out, -1.0, 1.0)


TONES = {
    "start": make_chime([523.25, 659.25]),   # C5 -> E5, gentle rise
    "stop": make_chime([659.25, 523.25]),    # mirror fall
    "error": make_chime([165.0, 165.0], note_ms=90, overlap_ms=0),
}


def play_tone(kind: str, enabled: bool = True):
    if not enabled:
        return
    try:
        sd.play(TONES[kind], SAMPLE_RATE)  # non-blocking, default output device
    except Exception:
        pass  # audio feedback is never worth crashing over


class Recorder:
    """Buffers microphone audio between start() and stop()."""

    def __init__(self, device=None, on_level=None):
        self.device = device  # None = system default input
        self.on_level = on_level  # optional callback(0..1) per audio block
        self._stream = None
        self._chunks = []
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self._stream is not None:
                return
            self._chunks = []
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                device=self.device,
                callback=self._callback,
            )
            self._stream.start()

    def _callback(self, indata, frames, time_info, status):
        self._chunks.append(indata[:, 0].copy())
        if self.on_level is not None:
            try:
                self.on_level(normalize_level(rms(indata[:, 0])))
            except Exception:
                pass  # level feed is cosmetic

    def snapshot(self):
        """Copy of everything recorded so far, without stopping the stream."""
        with self._lock:
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            return np.concatenate(self._chunks).copy()

    def stop(self) -> np.ndarray:
        with self._lock:
            if self._stream is None:
                return np.zeros(0, dtype=np.float32)
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            return np.concatenate(self._chunks)


def list_input_devices():
    """[(index, name)] for input-capable devices on the default host API,
    prefixed with (None, 'System default')."""
    devices = [(None, "System default")]
    try:
        hostapi_index = sd.default.hostapi
        if hostapi_index < 0:
            hostapi_index = 0
        hostapi = sd.query_hostapis(hostapi_index)
        for idx in hostapi["devices"]:
            info = sd.query_devices(idx)
            if info["max_input_channels"] > 0:
                devices.append((idx, info["name"]))
    except Exception:
        pass
    return devices
