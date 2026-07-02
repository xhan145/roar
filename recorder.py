"""Microphone capture (16 kHz mono float32), RMS energy gate, feedback tones."""
import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


def rms(audio: np.ndarray) -> float:
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))


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


def _build_tones():
    gap = np.zeros(int(SAMPLE_RATE * 0.04), dtype=np.float32)
    blip = make_tone(220, 70)
    return {
        "start": make_tone(880, 80),
        "stop": make_tone(440, 80),
        "error": np.concatenate([blip, gap, blip]),
    }


TONES = _build_tones()


def play_tone(kind: str, enabled: bool = True):
    if not enabled:
        return
    try:
        sd.play(TONES[kind], SAMPLE_RATE)  # non-blocking, default output device
    except Exception:
        pass  # audio feedback is never worth crashing over


class Recorder:
    """Buffers microphone audio between start() and stop()."""

    def __init__(self, device=None):
        self.device = device  # None = system default input
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
