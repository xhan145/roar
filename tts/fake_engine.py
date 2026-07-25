"""Deterministic local fake used by normal CI (no model download)."""
from __future__ import annotations

import math

import numpy as np

from .types import (
    AudioChunk,
    CancellationToken,
    SAMPLE_RATE,
    TTSConfig,
    TTSCancelled,
)


class FakeTTSEngine:
    def __init__(self, *, fail_on=None):
        self.loaded = False
        self.load_count = 0
        self.fail_on = fail_on
        self.cancelled = False

    def is_available(self):
        return True

    def load(self, config: TTSConfig):
        self.load_count += 1
        if self.fail_on == "load":
            raise RuntimeError("fake load failure")
        self.loaded = True

    def synthesize(self, text, *, voice, speed, language,
                   cancellation_token: CancellationToken):
        if not self.loaded:
            raise RuntimeError("fake engine is not loaded")
        if self.fail_on == "synthesize":
            raise RuntimeError("fake synthesis failure")
        self.cancelled = False
        duration = max(0.04, min(0.25, len(text) / 1000))
        count = int(SAMPLE_RATE * duration)
        time = np.arange(count, dtype=np.float32) / SAMPLE_RATE
        samples = (0.05 * np.sin(2 * math.pi * 220 * time)).astype(np.float32)
        for index, block in enumerate(np.array_split(samples, 2)):
            if cancellation_token.cancelled or self.cancelled:
                raise TTSCancelled()
            yield AudioChunk(block, SAMPLE_RATE, index)

    def cancel(self):
        self.cancelled = True

    def unload(self):
        self.loaded = False
