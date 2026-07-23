"""Backend-neutral local text-to-speech support for ROAR Read Aloud.

This package deliberately does not import Kokoro, Misaki, Transformers, or
PyTorch. Those dependencies live in the optional Python 3.12 worker.
"""

from .service import TTSService
from .types import (
    AudioChunk,
    CancellationToken,
    TTSConfig,
    TTSEngine,
    TTSRequest,
    TTSState,
)

__all__ = [
    "AudioChunk",
    "CancellationToken",
    "TTSConfig",
    "TTSEngine",
    "TTSRequest",
    "TTSService",
    "TTSState",
]
