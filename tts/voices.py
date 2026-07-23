"""Validated local voice metadata; UI code consumes this catalog."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import os


@dataclass(frozen=True)
class Voice:
    voice_id: str
    display_name: str
    language: str
    locale: str
    source: str
    quality_note: str
    relative_path: str
    gender: str | None = None


VOICES = (
    Voice("af_heart", "Heart", "en-us", "American English",
          "hexgrad/Kokoro-82M", "Upstream flagship voice",
          "voices/af_heart.pt"),
    Voice("af_bella", "Bella", "en-us", "American English",
          "hexgrad/Kokoro-82M", "Upstream overall grade A−",
          "voices/af_bella.pt"),
    Voice("af_nicole", "Nicole", "en-us", "American English",
          "hexgrad/Kokoro-82M", "Upstream overall grade B−",
          "voices/af_nicole.pt"),
    Voice("am_michael", "Michael", "en-us", "American English",
          "hexgrad/Kokoro-82M", "Upstream overall grade C+",
          "voices/am_michael.pt"),
)
_BY_ID = {voice.voice_id: voice for voice in VOICES}


def get_voice(voice_id: str, language: str = "en-us") -> Voice:
    voice = _BY_ID.get(voice_id)
    if voice and voice.language == language:
        return voice
    fallback = _BY_ID["af_heart"]
    if fallback.language != language:
        raise ValueError("no installed voice is compatible with the language")
    return fallback


def catalog(pack_dir: str | None = None) -> list[dict]:
    out = []
    for voice in VOICES:
        entry = asdict(voice)
        entry["installed"] = bool(
            pack_dir and os.path.isfile(os.path.join(pack_dir, voice.relative_path)))
        out.append(entry)
    return out
