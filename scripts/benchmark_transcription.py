#!/usr/bin/env python3
"""Local transcription benchmark — measures each available backend/compute type.

100% offline (local models only, no download, no network). Prints a table of
backend / device / compute_type / model / audio-seconds / p50 inference ms /
real-time factor (RTF = infer_time / audio_time; < 1.0 means faster than real
time). Output text is only compared across backends for equality; no user data
is involved (the clip is a short synthetic sample or a --wav you pass).

Usage:
    venv/Scripts/python.exe scripts/benchmark_transcription.py            # auto
    venv/Scripts/python.exe scripts/benchmark_transcription.py --wav a.wav --iters 5
"""
import argparse
import os
import statistics
import subprocess
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

import hardware_accel  # noqa: E402
import transcriber as tr  # noqa: E402

SAMPLE = "Hello world. This is a local dictation benchmark for ROAR."


def synth_wav(path):
    """Windows System.Speech synthesizer — same offline trick the tests use."""
    ps = ("Add-Type -AssemblyName System.Speech; "
          "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          f"$s.SetOutputToWaveFile('{path}'); $s.Speak('{SAMPLE}'); $s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, timeout=120)
    return path


def load_audio(path):
    """Return (float32 mono 16k ndarray, duration_seconds)."""
    with wave.open(path, "rb") as w:
        rate = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if rate != 16000:  # cheap linear resample to 16k (benchmark only)
        idx = np.linspace(0, len(data) - 1, int(len(data) * 16000 / rate))
        data = np.interp(idx, np.arange(len(data)), data).astype(np.float32)
    return data, len(data) / 16000.0


def candidates(accel):
    """(label, force_device, compute_type) legs to benchmark, machine-aware."""
    legs = [("CPU int8", "cpu", "int8")]
    if accel.get("cuda"):
        cc = accel.get("cuda_compute") or set()
        if "float16" in cc:
            legs.append(("CUDA float16 (Balanced)", "cuda", "float16"))
        if "int8_float16" in cc:
            legs.append(("CUDA int8_float16 (Fast)", "cuda", "int8_float16"))
    return legs


def bench_leg(force_device, compute, audio, iters, models_dir):
    t = tr.Transcriber(model_name="auto", models_dir=models_dir, force_device=force_device,
                       accel={"compute_type": compute, "performance_preset": "balanced"})
    t.load()  # HF offline is enforced in main(); an uncached model raises -> "skip"
    text = t.transcribe(audio)          # warm-up (pays one-time autotune)
    times = []
    for _ in range(iters):
        t.transcribe(audio)
        times.append(t.last_infer_ms)
    return {"model": t.active_model, "device": t.device, "compute": t.compute_type,
            "p50_ms": statistics.median(times), "text": text}


def main():
    # ENFORCE the offline guarantee: an uncached model must raise ("skip"),
    # never download mid-benchmark. (Respects an explicit override if you set it.)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", help="16-bit PCM WAV; synthesized if omitted")
    ap.add_argument("--iters", type=int, default=5)
    args = ap.parse_args()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    models_dir = os.path.join(root, "models")

    wav = args.wav
    if not wav:
        wav = os.path.join(root, "build", "bench_sample.wav")
        os.makedirs(os.path.dirname(wav), exist_ok=True)
        if not os.path.exists(wav):
            print("synthesizing a sample clip (offline)...")
            synth_wav(wav)
    audio, dur = load_audio(wav)

    accel = hardware_accel.detect_acceleration()
    print(f"\nGPU: {'CUDA present' if accel['cuda'] else 'none (CPU only)'}  "
          f"| audio {dur:.2f}s | {args.iters} iters (p50)\n")
    print(f"{'backend':<28}{'device':<7}{'compute':<15}{'model':<20}"
          f"{'infer ms':>9}{'RTF':>8}  text")
    print("-" * 104)
    ref = None
    for label, dev, compute in candidates(accel):
        try:
            r = bench_leg(dev, compute, audio, args.iters, models_dir)
        except Exception as e:
            print(f"{label:<28}{dev:<7}{compute:<15}{'—':<20}{'skip':>9}"
                  f"{'':>8}  ({type(e).__name__}: {str(e)[:40]})")
            continue
        rtf = (r["p50_ms"] / 1000.0) / dur if dur else 0
        norm = " ".join(r["text"].lower().split())
        if ref is None:
            ref = norm
            match = f'"{r["text"][:34]}"'
        else:
            match = "match" if norm == ref else "DIFF"
        print(f"{label:<28}{r['device']:<7}{r['compute']:<15}{r['model']:<20}"
              f"{r['p50_ms']:>9.0f}{rtf:>8.2f}  {match}")
    print()


if __name__ == "__main__":
    main()
