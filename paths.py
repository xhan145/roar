"""Runtime paths: project-local when run from source, per-user when frozen.

A PyInstaller exe may live in a read-only location and has no console, so
frozen runs keep config in %APPDATA%\\FlowLocal and models plus the log in
%LOCALAPPDATA%\\FlowLocal.
"""
import os
import sys

APP_NAME = "FlowLocal"
APP_VERSION = "0.4.0"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _source_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _ensure(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def config_path() -> str:
    if is_frozen():
        base = _ensure(os.path.join(os.environ["APPDATA"], APP_NAME))
        return os.path.join(base, "config.json")
    return os.path.join(_source_root(), "config.json")


def models_dir() -> str:
    if is_frozen():
        return _ensure(os.path.join(os.environ["LOCALAPPDATA"], APP_NAME, "models"))
    return os.path.join(_source_root(), "models")


def _data_dir() -> str:
    """Per-user writable data root (history, audio, log). Frozen: LOCALAPPDATA;
    source: project root."""
    if is_frozen():
        return _ensure(os.path.join(os.environ["LOCALAPPDATA"], APP_NAME))
    return _source_root()


def history_db_path() -> str:
    return os.path.join(_data_dir(), "history.db")


def audio_dir() -> str:
    return _ensure(os.path.join(_data_dir(), "audio"))


def resource_path(name: str) -> str:
    """Bundled read-only asset (e.g. settings.html)."""
    if is_frozen():
        return os.path.join(os.path.dirname(sys.executable), "_internal", name)
    return os.path.join(_source_root(), name)


def log_path() -> str:
    base = _ensure(os.path.join(os.environ["LOCALAPPDATA"], APP_NAME))
    return os.path.join(base, "flowlocal.log")


def redirect_output_when_frozen():
    """Windowed exes have no stdout/stderr; print() would die. Log to a file."""
    if not is_frozen():
        return
    log = open(log_path(), "a", encoding="utf-8", buffering=1)
    sys.stdout = log
    sys.stderr = log
