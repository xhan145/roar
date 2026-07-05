"""Runtime paths: project-local when run from source, per-user when frozen.

A PyInstaller exe may live in a read-only location and has no console, so
frozen runs keep config in %APPDATA%\\ROAR and models plus the log in
%LOCALAPPDATA%\\ROAR.
"""
import os
import sys

APP_NAME = "ROAR"
APP_VERSION = "0.14.0"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _source_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _ensure(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


# PATH GETTERS ARE PURE — they never create directories. Creation happens
# only at write time (config.save, redirect_output_when_frozen, History,
# audio writes). A getter that creates its directory as a side effect races
# migrate_legacy_data(): config.py evaluates config_path() at IMPORT time,
# which used to conjure an empty %APPDATA%\ROAR before migration could
# rename the legacy FlowLocal dir onto it.

def config_path() -> str:
    if is_frozen():
        return os.path.join(os.environ["APPDATA"], APP_NAME, "config.json")
    return os.path.join(_source_root(), "config.json")


def models_dir() -> str:
    if is_frozen():
        return os.path.join(os.environ["LOCALAPPDATA"], APP_NAME, "models")
    return os.path.join(_source_root(), "models")


def _data_dir() -> str:
    """Per-user writable data root (history, audio, log). Frozen: LOCALAPPDATA;
    source: project root."""
    if is_frozen():
        return os.path.join(os.environ["LOCALAPPDATA"], APP_NAME)
    return _source_root()


def history_db_path() -> str:
    return os.path.join(_data_dir(), "history.db")


def audio_dir() -> str:
    # _ensure is safe here: only called when writing a WAV, long after startup
    return _ensure(os.path.join(_data_dir(), "audio"))


def resource_path(name: str) -> str:
    """Bundled read-only asset (e.g. settings.html)."""
    if is_frozen():
        return os.path.join(os.path.dirname(sys.executable), "_internal", name)
    return os.path.join(_source_root(), name)


def log_path() -> str:
    return os.path.join(os.environ["LOCALAPPDATA"], APP_NAME, "roar.log")


def migrate_legacy_data(old_name="FlowLocal"):
    """One-time rename of legacy data dirs + autostart entry. Frozen-only.
    Never deletes: rename-in-place or leave everything where it is."""
    if not is_frozen():
        return []
    moved = []
    import time
    for env in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        old = os.path.join(base, old_name)
        new = os.path.join(base, APP_NAME)
        if os.path.isdir(old) and not os.path.exists(new):
            for attempt in (1, 2):
                try:
                    os.rename(old, new)
                    moved.append(f"migrated {old} -> {new}")
                    break
                except OSError:
                    if attempt == 1:
                        time.sleep(2)  # webview stragglers may hold locks
                    else:
                        moved.append(f"could not migrate {old}; data left in place")
        elif os.path.isdir(old) and os.path.isdir(new):
            moved.append(f"both {old} and {new} exist; using {new}, leaving {old}")
    try:
        import autostart
        if autostart.get(old_name) is not None:
            autostart.set_enabled(old_name, "", False)
            autostart.set_enabled(APP_NAME, autostart.default_command(), True)
            moved.append("autostart entry renamed")
    except OSError:
        pass
    return moved


def redirect_output_when_frozen():
    """Windowed exes have no stdout/stderr; print() would die. Log to a file."""
    if not is_frozen():
        return
    target = log_path()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    log = open(target, "a", encoding="utf-8", buffering=1)
    sys.stdout = log
    sys.stderr = log
