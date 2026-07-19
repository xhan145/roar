"""One running ROAR per user. Windows: named mutex. Linux: flock pidfile.
The held handle lives for the process lifetime (module-global)."""
import os

import platform_id

_HANDLE = None  # keep the mutex/file handle alive for the whole process


def _lock_path():
    base = os.environ.get("XDG_RUNTIME_DIR") or os.path.join(
        os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share"), "ROAR")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "roar.lock")


def _acquire_linux(fresh=False):
    import fcntl
    global _HANDLE
    fh = open(_lock_path(), "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return False
    if not fresh:
        _HANDLE = fh
        fh.write(str(os.getpid()))
        fh.flush()
    return True


def _acquire_windows():
    import ctypes
    global _HANDLE
    ERROR_ALREADY_EXISTS = 183
    h = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\ROARSingleton")
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return False
    _HANDLE = h
    return True


def acquire() -> bool:
    if platform_id.is_linux():
        return _acquire_linux()
    return _acquire_windows()
