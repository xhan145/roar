"""Supervised JSON-pipe client for the optional Python 3.12 Kokoro worker."""
from __future__ import annotations

import base64
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid

import numpy as np

import paths
from . import model_manager
from .types import (
    CancellationToken,
    TTSConfig,
    TTSCancelled,
    validate_audio,
)
from .voices import get_voice

STARTUP_TIMEOUT_SECONDS = 90
MESSAGE_TIMEOUT_SECONDS = 120
MAX_PROTOCOL_LINE = 16 * 1024 * 1024


class KokoroEngine:
    def __init__(self, *, python_command=None, startup_timeout=None):
        self._python_command = python_command
        self.startup_timeout = startup_timeout or STARTUP_TIMEOUT_SECONDS
        self._config = None
        self._process = None
        self._reader = None
        self._write_lock = threading.Lock()
        self._queues = {}
        self._queues_lock = threading.Lock()
        self._ready_queue = queue.Queue(maxsize=2)
        self._current_id = None
        self.metrics = {}
        self._ready_received = False

    def is_available(self):
        if self._config is not None:
            pack = self._config.model_path or model_manager.default_pack_dir()
        else:
            pack = model_manager.default_pack_dir()
        return (model_manager.inspect_pack(pack, verify_hashes=False)["valid"]
                and self._candidate_python_command() is not None)

    def load(self, config: TTSConfig):
        if self._process is not None and self._process.poll() is None:
            self._config = config
            return
        pack_dir = config.model_path or model_manager.default_pack_dir()
        model_manager.verify_pack(pack_dir, verify_hashes=True)
        python_cmd = self._find_python_command()
        if not python_cmd:
            raise RuntimeError(
                "Kokoro Python 3.12 runtime is not installed")
        worker = paths.resource_path(os.path.join("tts", "worker.py"))
        env = os.environ.copy()
        env.update({
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "NO_PROXY": "*",
            "PYTHONUNBUFFERED": "1",
        })
        bootstrap = (
            "import runpy,sys;"
            "p=sys.argv.pop(1);sys.argv[0]=p;"
            "runpy.run_path(p,run_name='__main__')")
        command = list(python_cmd) + [
            "-c", bootstrap, worker, "--pack", os.path.abspath(pack_dir),
            "--language", config.language,
        ]
        self._ready_queue = queue.Queue(maxsize=2)
        self._ready_received = False
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=env,
            creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)
                           if os.name == "nt" else 0),
        )
        self._reader = threading.Thread(
            target=self._read_loop, name="ROAR-Kokoro-reader", daemon=True)
        self._reader.start()
        try:
            message = self._ready_queue.get(timeout=self.startup_timeout)
        except queue.Empty:
            self._terminate()
            raise RuntimeError("Kokoro worker startup timed out")
        if message.get("type") != "ready":
            self._terminate()
            raise RuntimeError(message.get("category", "worker_start_failed"))
        self.metrics = {key: value for key, value in message.items()
                        if key not in ("type", "detail")}
        self._config = config

    def synthesize(self, text, *, voice, speed, language,
                   cancellation_token: CancellationToken):
        if self._process is None or self._process.poll() is not None:
            raise RuntimeError("Kokoro worker is not loaded")
        selected = get_voice(voice, language)
        request_id = uuid.uuid4().hex
        messages = queue.Queue(maxsize=8)
        with self._queues_lock:
            self._queues[request_id] = messages
        self._current_id = request_id
        self._send({
            "command": "synthesize",
            "id": request_id,
            "text": text,
            "voice_path": selected.relative_path,
            "speed": float(speed),
        })
        sequence = 0
        try:
            while True:
                if cancellation_token.cancelled:
                    self._send({"command": "cancel", "id": request_id})
                    raise TTSCancelled()
                try:
                    message = messages.get(timeout=0.05)
                except queue.Empty:
                    if self._process.poll() is not None:
                        raise RuntimeError("Kokoro worker exited unexpectedly")
                    continue
                kind = message.get("type")
                if kind == "audio":
                    raw = base64.b64decode(message["data"], validate=True)
                    samples = np.frombuffer(raw, dtype="<f4").copy()
                    yield validate_audio(samples, sequence=sequence)
                    sequence += 1
                elif kind == "complete":
                    self.metrics.update({
                        key: value for key, value in message.items()
                        if key not in ("type", "id", "detail")})
                    return
                elif kind == "cancelled":
                    raise TTSCancelled()
                elif kind == "error":
                    raise RuntimeError(
                        message.get("category", "synthesis_failed"))
        finally:
            with self._queues_lock:
                self._queues.pop(request_id, None)
            if self._current_id == request_id:
                self._current_id = None

    def cancel(self):
        request_id = self._current_id
        if request_id and self._process is not None:
            try:
                self._send({"command": "cancel", "id": request_id})
            except Exception:
                pass

    def unload(self):
        if self._process is not None and self._process.poll() is None:
            try:
                self._send({"command": "shutdown"})
                self._process.wait(timeout=2)
            except Exception:
                self._terminate()
        self._process = None
        self._config = None

    def _find_python_command(self):
        candidates = self._python_candidates()
        for candidate in candidates:
            try:
                probe = subprocess.run(
                    candidate + [
                        "-c",
                        "import importlib.util,sys;"
                        "names=('kokoro','torch','misaki');"
                        "sys.exit(0 if all(importlib.util.find_spec(n) "
                        "for n in names) else 1)",
                    ],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=10, check=False,
                    creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                   if os.name == "nt" else 0),
                )
                if probe.returncode == 0:
                    return candidate
            except (OSError, subprocess.SubprocessError):
                continue
        return None

    def _candidate_python_command(self):
        candidates = self._python_candidates()
        return candidates[0] if candidates else None

    def _python_candidates(self):
        if self._python_command:
            return [list(self._python_command)]
        env_path = os.environ.get("ROAR_TTS_PYTHON")
        candidates = []
        if env_path:
            candidates.append([env_path])
        candidates.append([paths.tts_runtime_python()])
        if sys.version_info < (3, 13):
            candidates.append([sys.executable])
        if os.name == "nt" and shutil.which("py"):
            candidates.append(["py", "-3.12"])
        usable = []
        for candidate in candidates:
            executable = candidate[0]
            if os.path.isabs(executable) and not os.path.isfile(executable):
                continue
            usable.append(candidate)
        return usable

    def _send(self, payload):
        process = self._process
        if process is None or process.poll() is not None or process.stdin is None:
            raise RuntimeError("Kokoro worker is unavailable")
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._write_lock:
            process.stdin.write(data + "\n")
            process.stdin.flush()

    def _read_loop(self):
        process = self._process
        try:
            while process and process.stdout:
                line = process.stdout.readline(MAX_PROTOCOL_LINE + 1)
                if not line:
                    break
                if len(line) > MAX_PROTOCOL_LINE:
                    break
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                request_id = message.get("id")
                if request_id:
                    with self._queues_lock:
                        target = self._queues.get(request_id)
                    if target:
                        target.put(message)
                elif message.get("type") in ("ready", "error"):
                    if message.get("type") == "ready":
                        self._ready_received = True
                    try:
                        self._ready_queue.put_nowait(message)
                    except queue.Full:
                        pass
        finally:
            failure = {"type": "error", "category": "worker_exited"}
            if not self._ready_received:
                try:
                    self._ready_queue.put_nowait(failure)
                except queue.Full:
                    pass
            with self._queues_lock:
                targets = list(self._queues.values())
            for target in targets:
                try:
                    target.put_nowait(failure)
                except queue.Full:
                    pass

    def _terminate(self):
        process = self._process
        if process is not None and process.poll() is None:
            if os.name == "nt":
                try:
                    # A venv python.exe may be a launcher whose real Python
                    # interpreter is its child. Kill the tree so a timed-out
                    # model worker cannot survive ROAR.
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=5,
                        check=False,
                        creationflags=getattr(
                            subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    return
                except (OSError, subprocess.SubprocessError):
                    pass
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
