"""Optional Python 3.12 Kokoro worker.

Protocol output is JSON only and never includes input text or phonemes.
"""
from __future__ import annotations

import argparse
import base64
import importlib.metadata
import json
import os
import queue
import platform
import sys
import threading
import time


def emit(message):
    sys.stdout.write(json.dumps(
        message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--language", default="en-us")
    args = parser.parse_args()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ["NO_PROXY"] = "*"

    try:
        import numpy as np
        import torch
        from kokoro import KModel, KPipeline
        try:
            from loguru import logger
            logger.remove()
        except Exception:
            pass
        config_path = _safe_file(args.pack, "config.json")
        model_path = _safe_file(args.pack, "kokoro-v1_0.pth")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        started = time.perf_counter()
        model = KModel(
            repo_id="hexgrad/Kokoro-82M",
            config=config_path,
            model=model_path,
        ).to(device).eval()
        lang_code = {"en-us": "a", "en-gb": "b"}[args.language]
        pipeline = KPipeline(
            lang_code=lang_code,
            repo_id="hexgrad/Kokoro-82M",
            model=model,
        )
        emit({
            "type": "ready",
            "backend": device,
            "engine_version": importlib.metadata.version("kokoro"),
            "python_version": platform.python_version(),
            "model_version": "1.0",
            "sample_rate": 24000,
            "load_ms": round((time.perf_counter() - started) * 1000),
        })
    except Exception as exc:
        emit({"type": "error", "category": _category(exc)})
        return 2

    jobs = queue.Queue(maxsize=2)
    cancelled = set()
    cancel_lock = threading.Lock()
    shutdown = threading.Event()

    def synth_loop():
        while not shutdown.is_set():
            job = jobs.get()
            if job is None:
                return
            request_id = job["id"]
            started = time.perf_counter()
            first_audio = None
            audio_samples = 0
            try:
                voice = _safe_file(
                    args.pack, job["voice_path"], prefix="voices")
                generator = pipeline(
                    job["text"], voice=voice, speed=job["speed"],
                    split_pattern=None)
                for result in generator:
                    with cancel_lock:
                        if request_id in cancelled:
                            emit({"type": "cancelled", "id": request_id})
                            break
                    audio = result.audio
                    if audio is None:
                        continue
                    array = audio.detach().cpu().numpy().astype(
                        np.float32, copy=False).reshape(-1)
                    if not array.size or not np.all(np.isfinite(array)):
                        raise ValueError("invalid_audio")
                    array = np.clip(array, -1.0, 1.0)
                    if first_audio is None:
                        first_audio = time.perf_counter()
                    audio_samples += int(array.size)
                    emit({
                        "type": "audio",
                        "id": request_id,
                        "sample_rate": 24000,
                        "data": base64.b64encode(
                            array.astype("<f4", copy=False).tobytes()).decode("ascii"),
                    })
                else:
                    elapsed = time.perf_counter() - started
                    emit({
                        "type": "complete",
                        "id": request_id,
                        "elapsed_ms": round(elapsed * 1000),
                        "first_audio_ms": (
                            round((first_audio - started) * 1000)
                            if first_audio else None),
                        "audio_duration_ms": round(audio_samples / 24),
                        "real_time_factor": (
                            round(elapsed / (audio_samples / 24000), 3)
                            if audio_samples else None),
                        "peak_memory_bytes": _peak_memory_bytes(),
                    })
            except Exception as exc:
                emit({"type": "error", "id": request_id,
                      "category": _category(exc)})
            finally:
                with cancel_lock:
                    cancelled.discard(request_id)

    synth_thread = threading.Thread(
        target=synth_loop, name="ROAR-Kokoro-synthesis", daemon=True)
    synth_thread.start()
    for line in sys.stdin:
        try:
            message = json.loads(line)
            command = message.get("command")
            if command == "synthesize":
                _validate_job(message)
                jobs.put(message, timeout=1)
            elif command == "cancel":
                request_id = message.get("id")
                if isinstance(request_id, str):
                    with cancel_lock:
                        cancelled.add(request_id)
            elif command == "shutdown":
                shutdown.set()
                jobs.put(None)
                break
        except Exception as exc:
            emit({"type": "error", "id": (
                message.get("id") if isinstance(message, dict) else None),
                "category": _category(exc)})
    shutdown.set()
    return 0


def _validate_job(job):
    if not isinstance(job.get("id"), str) or len(job["id"]) > 64:
        raise ValueError("invalid_request")
    text = job.get("text")
    if not isinstance(text, str) or not 1 <= len(text) <= 1000:
        raise ValueError("invalid_text")
    speed = float(job.get("speed", 1))
    if not 0.6 <= speed <= 1.6:
        raise ValueError("invalid_speed")
    voice = job.get("voice_path")
    if not isinstance(voice, str) or not voice.startswith("voices/"):
        raise ValueError("invalid_voice")


def _safe_file(root, relative, prefix=None):
    root = os.path.abspath(root)
    normalized = relative.replace("\\", "/")
    if (normalized.startswith("/") or ":" in normalized
            or any(p in ("", ".", "..") for p in normalized.split("/"))):
        raise ValueError("unsafe_path")
    if prefix and normalized.split("/", 1)[0] != prefix:
        raise ValueError("unsafe_path")
    full = os.path.abspath(os.path.join(root, *normalized.split("/")))
    if os.path.commonpath([root, full]) != root or not os.path.isfile(full):
        raise ValueError("missing_model_file")
    return full


def _category(exc):
    text = str(exc).lower()
    if "cuda" in text:
        return "backend_unavailable"
    if "audio" in text:
        return "invalid_audio"
    if "model" in text or "file" in text or isinstance(exc, OSError):
        return "model_unavailable"
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return "invalid_request"
    return "worker_failure"


def _peak_memory_bytes():
    """Best-effort peak resident memory of the actual inference process."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        get_memory = ctypes.windll.kernel32.K32GetProcessMemoryInfo
        get_memory.restype = wintypes.BOOL
        get_memory.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        if get_memory(process, ctypes.byref(counters), counters.cb):
            return int(counters.PeakWorkingSetSize)
    except Exception:
        pass
    return None


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BaseException:
        # Never print tracebacks (they may contain input text from dependencies).
        emit({"type": "error", "category": "worker_failure"})
        raise SystemExit(2)
