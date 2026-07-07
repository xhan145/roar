"""Home-dashboard remote controls: a tiny one-way channel from the Settings
window to the tray/engine process.

Only fixed command NAMES cross (never user data), and the whole feature is gated
by the `dashboard_controls` config flag (off by default). Writes are atomic and
best-effort; reads never raise. The tray ignores any command whose timestamp is
not newer than the last one it acted on, so a stale file can't re-fire.
"""
import json
import os
import time

import paths

ALLOWED = frozenset({"toggle", "scratch"})


def send_command(cmd, path=None):
    """Write a command for the tray to pick up. Returns True on success, False
    on an unknown command or any failure — never raises."""
    if cmd not in ALLOWED:
        return False
    path = path or paths.command_path()
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"cmd": cmd, "ts": time.time()}, fh)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def take_command(last_ts, path=None):
    """Return (cmd, ts) for a NEW valid command (ts > last_ts), else
    (None, last_ts). Never raises."""
    path = path or paths.command_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        cmd = data.get("cmd")
        ts = float(data.get("ts", 0))
        if cmd in ALLOWED and ts > last_ts:
            return cmd, ts
    except Exception:
        pass
    return None, last_ts
