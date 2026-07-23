"""Private local command pipe between lightweight Settings and the tray."""
from __future__ import annotations

import getpass
import multiprocessing.connection
import os
import re
import threading

import paths

AUTHKEY = b"ROAR-Read-Aloud-v1"
MAX_TEXT_CHARS = 20_000
COMMANDS = frozenset({
    "speak", "preview", "read_clipboard", "read_selected", "pause_resume",
    "stop", "repeat", "preload",
    "unload",
})


def pipe_address():
    user = re.sub(r"[^A-Za-z0-9_.-]", "_", getpass.getuser())[:80]
    if os.name == "nt":
        return rf"\\.\pipe\ROAR-Read-Aloud-{user}"
    return os.path.join(paths.tts_dir(), "read-aloud.sock")


def family():
    return "AF_PIPE" if os.name == "nt" else "AF_UNIX"


def validate_message(message):
    if not isinstance(message, dict) or message.get("command") not in COMMANDS:
        raise ValueError("unknown Read Aloud command")
    clean = {"command": message["command"]}
    if clean["command"] in ("speak", "preview"):
        text = message.get("text")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= MAX_TEXT_CHARS:
            raise ValueError("invalid Read Aloud text")
        clean["text"] = text
        voice = message.get("voice")
        if isinstance(voice, str) and 1 <= len(voice) <= 40:
            clean["voice"] = voice
        try:
            speed = float(message.get("speed", 1.0))
            if 0.6 <= speed <= 1.6:
                clean["speed"] = speed
        except (TypeError, ValueError):
            pass
    return clean


def send(message, timeout=1.5):
    message = validate_message(message)
    result = {}
    done = threading.Event()

    def connect():
        try:
            conn = multiprocessing.connection.Client(
                pipe_address(), family=family(), authkey=AUTHKEY)
            try:
                conn.send(message)
                result["response"] = conn.recv()
            finally:
                conn.close()
        except Exception:
            result["response"] = {
                "ok": False,
                "error": "ROAR is not running. Start the tray app and try again.",
            }
        finally:
            done.set()

    thread = threading.Thread(target=connect, daemon=True)
    thread.start()
    if not done.wait(timeout):
        return {"ok": False, "error": "ROAR did not respond in time."}
    return result["response"]


class TTSCommandServer:
    def __init__(self, handler):
        self.handler = handler
        self._listener = None
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        address = pipe_address()
        if family() == "AF_UNIX":
            os.makedirs(os.path.dirname(address), exist_ok=True)
            try:
                os.unlink(address)
            except FileNotFoundError:
                pass
        self._listener = multiprocessing.connection.Listener(
            address, family=family(), authkey=AUTHKEY)
        self._thread = threading.Thread(
            target=self._run, name="ROAR-TTS-command-pipe", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        try:
            # Wake a blocking accept. The handler may see this stop command,
            # which is harmless during application shutdown.
            send({"command": "stop"}, timeout=0.3)
        except Exception:
            pass
        if self._listener:
            try:
                self._listener.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=1)
        if family() == "AF_UNIX":
            try:
                os.unlink(pipe_address())
            except OSError:
                pass

    def _run(self):
        while not self._stop.is_set():
            try:
                conn = self._listener.accept()
            except (OSError, EOFError):
                break
            try:
                message = validate_message(conn.recv())
                response = self.handler(message)
                conn.send(response if isinstance(response, dict)
                          else {"ok": bool(response)})
            except Exception as exc:
                conn.send({"ok": False, "error": str(exc)})
            finally:
                conn.close()
