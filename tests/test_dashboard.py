import pathlib
import re

import status

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_dashboard_reduced_motion_and_no_external_assets():
    html = (ROOT / "settings.html").read_text(encoding="utf-8")
    # reduced-motion support (waveform/mic animations freeze)
    assert "prefers-reduced-motion" in html
    # no external fonts/CDNs/remote assets — everything is local
    assert not re.search(r"https?://", html), "external URL in settings.html"
    # the home dashboard is present and its live bridge is wired
    assert 'id="home"' in html and "get_home_state" in html


def test_status_channel_never_carries_private_data():
    for banned in ("transcript", "clipboard", "text", "audio", "window_title"):
        assert banned not in status.ALLOWED, banned
