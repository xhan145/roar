"""Start on login. Windows: HKCU Run key. Linux: XDG autostart .desktop."""
import os
import re
import sys

import platform_id

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _xdg_home() -> str:
    # Read HOME directly rather than os.path.expanduser("~"): on Windows,
    # ntpath.expanduser prefers USERPROFILE over HOME, which would silently
    # ignore a HOME override when this Linux code path is exercised (e.g. in
    # tests) on a Windows dev box. On real Linux, HOME is what expanduser
    # would have used anyway. Mirrors paths._xdg_home().
    return os.environ.get("HOME") or os.path.expanduser("~")


def _autostart_dir() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        _xdg_home(), ".config")
    return os.path.join(base, "autostart")


def _desktop_path(name: str) -> str:
    return os.path.join(_autostart_dir(), f"{name}.desktop")


def _linux_get(name: str):
    try:
        with open(_desktop_path(name), encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("Exec="):
                    return line[len("Exec="):].strip()
    except OSError:
        return None
    return None


def _linux_set(name: str, command: str, enabled: bool):
    path = _desktop_path(name)
    if not enabled:
        try:
            os.remove(path)
        except OSError:
            pass
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name}\n"
        f"Exec={command}\n"
        "X-GNOME-Autostart-enabled=true\n"
        "Terminal=false\n"
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)


def get(name: str):
    if platform_id.is_linux():
        return _linux_get(name)
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _type = winreg.QueryValueEx(key, name)
            return value
    except OSError:
        return None


def set_enabled(name: str, command: str, enabled: bool):
    if platform_id.is_linux():
        return _linux_set(name, command, enabled)
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, name)
            except OSError:
                pass  # already absent


def default_command() -> str:
    if platform_id.is_linux():
        # the launcher script written by linux/setup.sh
        return os.path.join(os.path.expanduser("~"), ".local", "bin", "roar")
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    app = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    return f'"{pythonw}" "{app}"'
