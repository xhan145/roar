"""Start-with-Windows via HKCU Run key. No admin required."""
import os
import sys
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def get(name: str):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _type = winreg.QueryValueEx(key, name)
            return value
    except OSError:
        return None


def set_enabled(name: str, command: str, enabled: bool):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, name)
            except OSError:
                pass  # already absent


def default_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    app = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    return f'"{pythonw}" "{app}"'
