"""Offline Kokoro benchmark. Never downloads model or dependency files."""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tts.kokoro_engine import KokoroEngine
from tts.chunker import chunk_text
from tts.types import CancellationToken, TTSConfig

TEXTS = {
    "short": "ROAR reads this sentence aloud entirely on this computer.",
    "medium": " ".join(
        ["Local speech can help people review a draft, hear a completed "
         "dictation, or listen while their attention is elsewhere."] * 5),
    "long": " ".join(
        ["ROAR generates speech locally, keeps the model optional, avoids "
         "retaining generated audio, and allows playback to be stopped."] * 25),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", required=True,
                        help="verified offline ROAR Local Voice Pack directory")
    parser.add_argument("--voice", default="af_heart")
    args = parser.parse_args()
    engine = KokoroEngine()
    config = TTSConfig(enabled=True, model_path=os.path.abspath(args.pack),
                       voice=args.voice)
    report = {
        "hardware": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python": platform.python_version(),
        },
        "voice": args.voice,
        "results": {},
    }
    started = time.perf_counter()
    engine.load(config)
    report["cold_model_load_ms"] = round(
        (time.perf_counter() - started) * 1000)
    report["backend"] = engine.metrics.get("backend", "unknown")
    report["worker_python"] = engine.metrics.get("python_version", "unknown")
    try:
        for name, text in TEXTS.items():
            token = CancellationToken()
            started = time.perf_counter()
            first = None
            samples = 0
            pieces = chunk_text(text)
            for piece in pieces:
                for chunk in engine.synthesize(
                        piece, voice=args.voice, speed=1.0, language="en-us",
                        cancellation_token=token):
                    if first is None:
                        first = time.perf_counter()
                    samples += chunk.samples.size
            elapsed = time.perf_counter() - started
            duration = samples / 24000
            report["results"][name] = {
                "input_character_count": len(text),
                "chunk_count": len(pieces),
                "time_to_first_audio_ms": (
                    round((first - started) * 1000) if first else None),
                "total_synthesis_ms": round(elapsed * 1000),
                "generated_audio_ms": round(duration * 1000),
                "real_time_factor": (
                    round(elapsed / duration, 3) if duration else None),
            }
        report["peak_worker_memory_bytes"] = engine.metrics.get(
            "peak_memory_bytes")
    finally:
        engine.unload()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
