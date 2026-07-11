"""Red-team invariant: ROAR never touches the network on its own.

The ONLY permitted network call site is settings_ui.check_updates (click-only).
A static source scan is deliberate — it fails loudly the moment anyone adds a
new urlopen/requests/socket call anywhere else.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FIRST_PARTY = [f for f in os.listdir(ROOT)
               if f.endswith(".py") and not f.startswith("conftest")]

NET_CALL = re.compile(r"urlopen\(|requests\.(get|post)|socket\.socket|http\.client")


def _src(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def test_only_check_updates_touches_the_network():
    # Sanctioned network sites, each inbound-only and never in the dictation
    # path (no user data ever leaves the machine):
    #   settings_ui.py     — check_updates, click-only
    #   whispercpp_assets.py — one-time, OPT-IN download of the Vulkan GPU
    #                          binary/model (like faster-whisper's model fetch),
    #                          only after the user enables the GPU backend
    allowed = {"settings_ui.py", "whispercpp_assets.py"}
    offenders = {}
    for name in FIRST_PARTY:
        hits = NET_CALL.findall(_src(name))
        if hits:
            offenders[name] = hits
    assert set(offenders) <= allowed, offenders
    # within settings_ui, urlopen appears exactly once (check_updates)
    assert _src("settings_ui.py").count("urlopen(") == 1
    # whispercpp_assets only downloads (urlopen); it never opens raw sockets
    assert "socket.socket" not in _src("whispercpp_assets.py")


def test_startup_path_never_calls_update_check():
    # app.py must not invoke check_updates (it lives in the settings process,
    # behind a button); tray startup stays fully offline
    assert "check_updates" not in _src("app.py")


def test_no_analytics_or_telemetry_imports():
    banned = re.compile(r"^\s*import (requests|analytics|sentry_sdk|posthog)",
                        re.MULTILINE)
    for name in FIRST_PARTY:
        assert not banned.search(_src(name)), name
