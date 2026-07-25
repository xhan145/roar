"""Runtime paths: project-local when run from source, per-user when frozen.

A PyInstaller exe may live in a read-only location and has no console, so
frozen runs keep config in %APPDATA%\\ROAR and models plus the log in
%LOCALAPPDATA%\\ROAR.
"""
import os
import sys

import platform_id

APP_NAME = "ROAR"
APP_VERSION = "0.23.0"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _xdg_home() -> str:
    # Read HOME directly rather than os.path.expanduser("~"): on Windows,
    # ntpath.expanduser prefers USERPROFILE over HOME, which would silently
    # ignore a HOME override when this Linux code path is exercised (e.g. in
    # tests) on a Windows dev box. On real Linux, HOME is what expanduser
    # consults anyway, so behavior is unchanged there.
    return os.environ.get("HOME") or os.path.expanduser("~")


def _xdg_config_home() -> str:
    return os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        _xdg_home(), ".config")


def _xdg_data_home() -> str:
    return os.environ.get("XDG_DATA_HOME") or os.path.join(
        _xdg_home(), ".local", "share")


def _linux_config_dir() -> str:
    return os.path.join(_xdg_config_home(), APP_NAME)


def _linux_data_dir() -> str:
    return os.path.join(_xdg_data_home(), APP_NAME)


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
    if platform_id.is_linux():
        return os.path.join(_linux_config_dir(), "config.json")
    return os.path.join(_source_root(), "config.json")


def models_dir() -> str:
    if is_frozen():
        return os.path.join(os.environ["LOCALAPPDATA"], APP_NAME, "models")
    if platform_id.is_linux():
        return os.path.join(_linux_data_dir(), "models")
    return os.path.join(_source_root(), "models")


def tts_dir() -> str:
    """Per-user Read Aloud data root. Kept separate from dictation models."""
    if platform_id.is_windows() and os.environ.get("LOCALAPPDATA"):
        return os.path.join(os.environ["LOCALAPPDATA"], APP_NAME, "tts")
    if platform_id.is_linux():
        return os.path.join(_linux_data_dir(), "tts")
    return os.path.join(_source_root(), "tts-data")


def tts_model_dir() -> str:
    """Managed, verified ROAR Local Voice Pack location."""
    return os.path.join(tts_dir(), "kokoro")


def tts_runtime_python() -> str:
    """Optional isolated Python 3.12 runtime installed by the voice component."""
    if platform_id.is_windows():
        return os.path.join(tts_dir(), "runtime", "Scripts", "python.exe")
    return os.path.join(tts_dir(), "runtime", "bin", "python")


def license_path() -> str:
    """The signed license file. Deliberately beside config.json in %APPDATA%\\ROAR
    — NOT in the %LOCALAPPDATA% data dir that holds history/audio, so that a
    history clear, privacy reset, or audio delete can never remove it, and a
    normal MSI upgrade (which replaces program files only) preserves it. Only an
    explicit "Remove License" deletes it."""
    if is_frozen():
        return os.path.join(os.environ["APPDATA"], APP_NAME, "license.json")
    if platform_id.is_linux():
        return os.path.join(_linux_config_dir(), "license.json")
    return os.path.join(_source_root(), "license.json")


def legacy_grant_path() -> str:
    """One-time grandfathering grant: a set of FEATURE IDs (never an edition)
    recorded for installs that predate commercial gating. Stored beside the
    license for the same upgrade-survival reasons."""
    if is_frozen():
        return os.path.join(os.environ["APPDATA"], APP_NAME, "legacy_grant.json")
    if platform_id.is_linux():
        return os.path.join(_linux_config_dir(), "legacy_grant.json")
    return os.path.join(_source_root(), "legacy_grant.json")


def _data_dir() -> str:
    """Per-user writable data root (history, audio, log). Frozen: LOCALAPPDATA;
    source: project root."""
    if is_frozen():
        return os.path.join(os.environ["LOCALAPPDATA"], APP_NAME)
    if platform_id.is_linux():
        return _linux_data_dir()
    return _source_root()


def vulkan_dir() -> str:
    """Where the downloaded whisper.cpp Vulkan binary is unpacked (on first GPU
    use). Under the per-user data root so it survives app updates."""
    return os.path.join(_data_dir(), "vulkan")


def history_db_path() -> str:
    return os.path.join(_data_dir(), "history.db")


def status_path() -> str:
    """Live status file the tray writes and the Settings window reads (Home
    dashboard). Operational facts only — never transcript/audio/clipboard."""
    return os.path.join(_data_dir(), "status.json")


def command_path() -> str:
    """Command file the Settings window writes and the tray reads (Home
    dashboard remote controls). Only fixed command names — never user data.
    Gated by the `dashboard_controls` config flag (off by default)."""
    return os.path.join(_data_dir(), "command.json")


def audio_dir() -> str:
    # _ensure is safe here: only called when writing a WAV, long after startup
    return _ensure(os.path.join(_data_dir(), "audio"))


def resource_path(name: str) -> str:
    """Bundled read-only asset (e.g. settings.html)."""
    if is_frozen():
        return os.path.join(os.path.dirname(sys.executable), "_internal", name)
    return os.path.join(_source_root(), name)


def log_path() -> str:
    if platform_id.is_linux():
        return os.path.join(_linux_data_dir(), "roar.log")
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
