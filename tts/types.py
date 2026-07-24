"""Small shared types for TTS engines, playback, and orchestration."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import threading
import time
from typing import Callable, Iterable, Optional, Protocol
import uuid

import numpy as np

SAMPLE_RATE = 24_000
MIN_SPEED = 0.6
MAX_SPEED = 1.6
MAX_TEXT_CHARS = 20_000


class TTSState(str, Enum):
    UNAVAILABLE = "unavailable"
    UNLOADED = "unloaded"
    LOADING = "loading"
    READY = "ready"
    SYNTHESIZING = "synthesizing"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass(frozen=True)
class TTSConfig:
    enabled: bool = False
    engine: str = "kokoro"
    voice: str = "af_heart"
    language: str = "en-us"
    speed: float = 1.0
    volume: float = 1.0
    output_device: object = "default"
    model_path: Optional[str] = None
    preload_model: bool = True
    unload_after_idle_minutes: int = 30
    persistent_cache_enabled: bool = False

    @classmethod
    def from_mapping(cls, raw: dict) -> "TTSConfig":
        speed = _bounded_float(raw.get("tts_speed"), 1.0, MIN_SPEED, MAX_SPEED)
        volume = _bounded_float(raw.get("tts_volume"), 1.0, 0.0, 1.0)
        idle = _bounded_int(raw.get("tts_unload_after_idle_minutes"), 30, 0, 1440)
        model_path = raw.get("tts_model_path")
        if not isinstance(model_path, str) or not model_path.strip():
            model_path = None
        voice = raw.get("tts_voice")
        if not isinstance(voice, str) or not voice.strip():
            voice = "af_heart"
        language = raw.get("tts_language")
        if language not in ("en-us", "en-gb"):
            language = "en-us"
        engine = raw.get("tts_engine")
        if engine != "kokoro":
            engine = "kokoro"
        output = raw.get("tts_output_device", "default")
        if output != "default":
            try:
                output = int(output)
            except (TypeError, ValueError):
                output = "default"
        return cls(
            enabled=bool(raw.get("tts_enabled", False)),
            engine=engine,
            voice=voice.strip(),
            language=language,
            speed=speed,
            volume=volume,
            output_device=output,
            model_path=model_path,
            preload_model=bool(raw.get("tts_preload_model", True)),
            unload_after_idle_minutes=idle,
            persistent_cache_enabled=bool(
                raw.get("tts_persistent_cache_enabled", False)),
        )


@dataclass(frozen=True)
class AudioChunk:
    samples: np.ndarray
    sample_rate: int = SAMPLE_RATE
    sequence: int = 0


@dataclass(frozen=True)
class TTSRequest:
    text: str
    voice: str
    speed: float
    language: str
    volume: float = 1.0
    output_device: object = "default"
    source: str = "typed"
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.monotonic)


class CancellationToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self):
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout=None) -> bool:
        return self._event.wait(timeout)

    def raise_if_cancelled(self):
        if self.cancelled:
            raise TTSCancelled()


class TTSCancelled(RuntimeError):
    pass


class TTSEngine(Protocol):
    def load(self, config: TTSConfig) -> None: ...

    def synthesize(
        self,
        text: str,
        *,
        voice: str,
        speed: float,
        language: str,
        cancellation_token: CancellationToken,
    ) -> Iterable[AudioChunk]: ...

    def cancel(self) -> None: ...
    def unload(self) -> None: ...
    def is_available(self) -> bool: ...


StateListener = Callable[[TTSState, dict], None]


def validate_audio(samples, *, sample_rate=SAMPLE_RATE, sequence=0) -> AudioChunk:
    """Return safe mono float32 audio or raise without retaining input data."""
    if sample_rate != SAMPLE_RATE:
        raise ValueError("unsupported sample rate")
    array = np.asarray(samples)
    if array.ndim == 2 and 1 in array.shape:
        array = array.reshape(-1)
    if array.ndim != 1 or array.size == 0:
        raise ValueError("audio must be a non-empty mono array")
    if array.size > SAMPLE_RATE * 300:
        raise ValueError("audio chunk exceeds five minutes")
    array = array.astype(np.float32, copy=False)
    if not np.all(np.isfinite(array)):
        raise ValueError("audio contains non-finite samples")
    array = np.clip(array, -1.0, 1.0)
    return AudioChunk(np.ascontiguousarray(array), sample_rate, sequence)


def _bounded_float(value, default, low, high):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(value):
        return default
    return min(high, max(low, value))


def _bounded_int(value, default, low, high):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return min(high, max(low, value))
