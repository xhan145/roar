"""whisper.cpp Vulkan GPU backend (AMD / Intel / NVIDIA).

Runs Whisper on any Vulkan-1.3 GPU via a warm local `whisper-server` subprocess
bound to loopback only — the model loads onto the GPU once and stays resident,
each dictation POSTs a 16 kHz WAV to `/inference` and gets text back. 100%
offline (no network in the transcription path; the one-time binary/model fetch
is handled by `whispercpp_assets`). Satisfies `backends.TranscriberBackend`.

If the server can't start (no Vulkan GPU, download failed, port issues), `load()`
raises and the caller falls back to the CTranslate2 CPU path.
"""
import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.request
import wave

import numpy as np

import paths
import whispercpp_assets as assets

_CREATE_NO_WINDOW = 0x08000000  # Windows: no console window for the subprocess


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def write_wav_16k(audio, path) -> None:
    """Write mono 16 kHz 16-bit PCM WAV. `audio` is a float32 ndarray in
    [-1, 1] (or already int16)."""
    a = np.asarray(audio)
    if a.dtype != np.int16:
        a = np.clip(a, -1.0, 1.0)
        a = (a * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(a.tobytes())


def parse_response(data: dict) -> str:
    """Pull the transcript out of a whisper-server /inference JSON reply."""
    return (data.get("text") or "").strip()


def _lang_flag(model_name: str, language: str) -> str:
    if model_name.endswith(".en"):
        return "en"
    return "auto" if (language or "en") in ("auto", "") else language


class WhisperCppVulkanBackend:
    backend = "whispercpp_vulkan"

    def __init__(self, model_name="auto", models_dir="models", language="en",
                 log=print, accel=None, progress=None):
        self.requested = model_name
        self.models_dir = models_dir
        self.language = language
        self.log = log
        self.progress = progress
        self.accel_cfg = accel or {}
        self.device = None
        self.active_model = None
        self.compute_type = "ggml"
        self.beam_size = 1
        self.cpu_threads = 0
        self.cuda_detected = False
        self.last_infer_ms = 0.0
        self.hotwords = None  # whisper-server has no hotword arg; accepted, unused
        self._proc = None
        self._port = None

    def _model_name(self) -> str:
        req = self.requested
        if req and req != "auto" and req in assets.MODELS:
            return req
        return assets.model_for(self.language)

    def load(self, model_name=None) -> None:
        bin_dir = paths.vulkan_dir()
        server = assets.ensure_binary(bin_dir, self.log, self.progress)
        name = self._model_name()
        model = assets.ensure_model(self.models_dir, name, self.log, self.progress)
        port = _free_port()
        flags = _CREATE_NO_WINDOW if os.name == "nt" else 0
        self.log(f"starting Vulkan whisper-server ({name}) on 127.0.0.1:{port}...")
        # Discard the server's stdout/stderr: reading a pipe risks a
        # buffering deadlock, and an UNdrained pipe can block the server once its
        # buffer fills. Readiness is detected by the port accepting connections
        # (whisper-server listens only after the model is fully loaded).
        self._proc = subprocess.Popen(
            [server, "-m", model, "--host", "127.0.0.1", "--port", str(port),
             "-l", _lang_flag(name, self.language)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags, cwd=bin_dir)
        self._port = port
        if not self._wait_ready(timeout=90):
            self.close()
            raise RuntimeError("Vulkan whisper-server did not become ready")
        self.device = "Vulkan (GPU)"
        self.active_model = name

    def _wait_ready(self, timeout=90) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            if self._proc.poll() is not None:
                return False  # process died during load
            try:
                with socket.create_connection(("127.0.0.1", self._port), 0.5):
                    return True  # listening -> model loaded and serving
            except OSError:
                time.sleep(0.15)
        return False

    def transcribe(self, audio) -> str:
        if isinstance(audio, (str, os.PathLike)):
            wav_path, temp = str(audio), False
        else:
            fd, wav_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            write_wav_16k(audio, wav_path)
            temp = True
        try:
            t0 = time.perf_counter()
            text = self._post(wav_path)
            self.last_infer_ms = (time.perf_counter() - t0) * 1000.0
            return text
        finally:
            if temp and os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except OSError:
                    pass

    def _post(self, wav_path) -> str:
        boundary = "----roar" + str(int(time.perf_counter() * 1e6))
        with open(wav_path, "rb") as f:
            wav = f.read()
        pre = []
        for name, value in (("temperature", "0"), ("response_format", "json")):
            pre.append(
                f"--{boundary}\r\nContent-Disposition: form-data; "
                f'name="{name}"\r\n\r\n{value}\r\n'.encode())
        pre.append(
            f"--{boundary}\r\nContent-Disposition: form-data; "
            f'name="file"; filename="a.wav"\r\n'
            f"Content-Type: audio/wav\r\n\r\n".encode())
        body = b"".join(pre) + wav + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self._port}/inference", data=body, method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        return parse_response(data)

    def description(self) -> str:
        if self.active_model is None:
            return "no model"
        return f"{self.active_model} (Vulkan GPU)"

    def close(self) -> None:
        p, self._proc = self._proc, None
        if p and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=3)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
