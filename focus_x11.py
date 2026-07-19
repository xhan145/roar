"""X11 active-window queries via xdotool. Verified on Ubuntu 24.04 / Xorg."""
import os
import subprocess


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


class X11Focus:
    def current_id(self):
        try:
            return subprocess.check_output(
                ["xdotool", "getactivewindow"]).decode().strip()
        except Exception:
            return ""

    def active_process(self):
        """Lowercased exe basename (via /proc/<pid>/comm), or '' on failure."""
        try:
            pid = subprocess.check_output(
                ["xdotool", "getactivewindow", "getwindowpid"]).decode().strip()
        except Exception:
            return ""
        comm = f"/proc/{pid}/comm"
        if not os.path.exists(comm):
            return ""
        try:
            return _read(comm).strip().lower()
        except Exception:
            return ""

    def active_title(self):
        """Window title of the focused window, or '' on failure."""
        try:
            return subprocess.check_output(
                ["xdotool", "getactivewindow", "getwindowname"]).decode(
                    "utf-8", "replace").strip()
        except Exception:
            return ""
