"""Transcription backend seam.

ROAR's shipping backend is CTranslate2 / faster-whisper — `transcriber.Transcriber`
(aliased `transcriber.FasterWhisperBackend`): CUDA when present, CPU int8 as the
always-on fallback (CPU is folded into that class, not a separate backend). This
package defines the minimal interface an alternate backend must satisfy and hosts
the experimental DirectML spike.

Selection is done by `hardware_accel.choose_best_backend(cfg, accel)`.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class TranscriberBackend(Protocol):
    """The surface `app.py` relies on. Any backend must provide these."""
    device: str
    active_model: str
    backend: str
    compute_type: str

    def load(self) -> None: ...
    def transcribe(self, audio) -> str: ...   # float32 mono 16k ndarray or a path
    def description(self) -> str: ...
