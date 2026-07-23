"""Cancellable in-memory 24 kHz mono playback."""
from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd

from .types import AudioChunk, CancellationToken, TTSCancelled


def list_output_devices():
    devices = [("default", "System default")]
    try:
        hostapi_index = sd.default.hostapi
        if hostapi_index < 0:
            hostapi_index = 0
        hostapi = sd.query_hostapis(hostapi_index)
        for idx in hostapi["devices"]:
            info = sd.query_devices(idx)
            if info["max_output_channels"] > 0:
                devices.append((idx, info["name"]))
    except Exception:
        pass
    return devices


class TTSPlaybackController:
    def __init__(self):
        self._paused = threading.Event()
        self._stopped = threading.Event()
        self._lock = threading.RLock()
        self._stream = None

    @property
    def paused(self):
        return self._paused.is_set()

    def play(
        self,
        chunks,
        *,
        cancellation_token: CancellationToken,
        volume: float = 1.0,
        device="default",
        on_started=None,
    ):
        self._stopped.clear()
        self._paused.clear()
        started = False
        selected = None if device == "default" else device
        try:
            for chunk in chunks:
                if cancellation_token.cancelled or self._stopped.is_set():
                    raise TTSCancelled()
                while self._paused.is_set():
                    if (cancellation_token.wait(0.03)
                            or self._stopped.wait(0.03)):
                        raise TTSCancelled()
                if not isinstance(chunk, AudioChunk):
                    raise ValueError("playback received an invalid audio chunk")
                samples = np.multiply(
                    chunk.samples, np.float32(volume), dtype=np.float32)
                samples = np.clip(samples, -1.0, 1.0).reshape(-1, 1)
                with self._lock:
                    if self._stream is None:
                        self._stream = sd.OutputStream(
                            samplerate=chunk.sample_rate,
                            channels=1,
                            dtype="float32",
                            device=selected,
                            latency="low",
                        )
                        self._stream.start()
                    stream = self._stream
                if not started:
                    started = True
                    if on_started:
                        on_started()
                stream.write(samples)
        finally:
            self._close_stream()

    def pause(self):
        self._paused.set()

    def resume(self):
        self._paused.clear()

    def stop(self):
        self._stopped.set()
        self._paused.clear()
        with self._lock:
            stream = self._stream
        if stream is not None:
            try:
                stream.abort()
            except Exception:
                pass
        self._close_stream()

    def _close_stream(self):
        with self._lock:
            stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass


class NullPlaybackController:
    """Deterministic non-audio playback for tests and benchmarks."""

    def __init__(self):
        self.paused = False
        self.stopped = False
        self.chunks = []

    def play(self, chunks, *, cancellation_token, volume=1.0,
             device="default", on_started=None):
        self.stopped = False
        self.paused = False
        called = False
        for chunk in chunks:
            if cancellation_token.cancelled or self.stopped:
                raise TTSCancelled()
            if not called:
                called = True
                if on_started:
                    on_started()
            self.chunks.append(chunk)

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.stopped = True
