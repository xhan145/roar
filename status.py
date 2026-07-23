"""Live dictation status: a tiny one-way channel from the tray/engine process to
the Settings window's Home dashboard.

Operational facts ONLY — never transcript text, clipboard, audio, or window
titles. Writes are atomic and best-effort: a status failure must never affect
dictation, so every function swallows its own errors.
"""
import json
import os
import time

import paths

# The ONLY keys allowed to persist. Anything else is dropped, so a future caller
# can't leak a new field (e.g. a transcript) through the status file.
ALLOWED = frozenset({
    "state", "session_started_at", "session_word_count",
    "last_latency_seconds", "last_injection_status", "last_profile",
    "device", "updated_at",
    # performance / acceleration (operational facts only — never transcripts)
    "last_record_duration_ms", "last_transcription_duration_ms",
    "last_injection_duration_ms", "backend", "compute_type", "fallback_reason",
    "cpu_threads",
    # Read Aloud operational facts. Never text, phonemes, clipboard, or audio.
    "tts_state", "tts_engine", "tts_engine_version", "tts_model_status",
    "tts_model_version",
    "tts_voice", "tts_language", "tts_device", "tts_sample_rate",
    "tts_error_category", "tts_last_elapsed_ms", "tts_last_audio_duration_ms",
    "tts_last_first_audio_ms", "tts_last_real_time_factor",
})


def write_status(path=None, **fields):
    """Merge `fields` (allowlisted) into the status file, atomically. Returns
    True on success, False on any failure — never raises."""
    path = path or paths.status_path()
    try:
        current = read_status(path)
        for key, value in fields.items():
            if key in ALLOWED:
                current[key] = value
        current["updated_at"] = time.time()
        clean = {k: v for k, v in current.items() if k in ALLOWED}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(clean, fh)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def read_status(path=None):
    """Return the status dict, or {} if missing/corrupt. Never raises."""
    path = path or paths.status_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {k: v for k, v in data.items() if k in ALLOWED} if isinstance(data, dict) else {}
    except Exception:
        return {}
