"""The gesture click must be CONSUMED, and only ours.

Letting Ctrl+Right-click through opens the app's context menu; an open menu
holds keyboard focus, so the capture's Ctrl+C lands in the menu instead of the
page — the exact reason Point & Speak failed in browsers.
"""
import mouse_hook as mh


DOWN, UP, MOVE = mh.WM_RBUTTONDOWN, mh.WM_RBUTTONUP, 0x0200
LEFT_DOWN = 0x0201


def test_both_gesture_events_are_consumed():
    # DOWN too, or the app sees an orphaned button-down
    assert mh.should_suppress(DOWN, ctrl_down=True, enabled=True) is True
    assert mh.should_suppress(UP, ctrl_down=True, enabled=True) is True


def test_plain_right_click_is_never_consumed():
    assert mh.should_suppress(DOWN, ctrl_down=False, enabled=True) is False
    assert mh.should_suppress(UP, ctrl_down=False, enabled=True) is False


def test_nothing_is_consumed_while_disabled():
    assert mh.should_suppress(DOWN, ctrl_down=True, enabled=False) is False
    assert mh.should_suppress(UP, ctrl_down=True, enabled=False) is False


def test_other_buttons_and_moves_pass_through():
    for msg in (MOVE, LEFT_DOWN):
        assert mh.should_suppress(msg, ctrl_down=True, enabled=True) is False


def test_suppression_is_independent_of_debounce():
    """A debounced repeat still gets consumed — otherwise the second click of a
    rapid double would leak a context menu into the app."""
    assert mh.should_suppress(UP, ctrl_down=True, enabled=True) is True
    assert mh.should_trigger(UP, ctrl_down=True, enabled=True,
                             now=10.0, last_fire=9.95) is False


def test_accessibility_nudge_is_safe_off_windows(monkeypatch):
    import tts.text_sources as sources
    monkeypatch.setattr(sources.platform_id, "is_windows", lambda: False)
    assert sources.enable_accessibility_for_foreground() is False


def test_uia_failure_retries_after_nudge(monkeypatch):
    """A browser exposes nothing until nudged; the retry is what makes UIA
    work there instead of always falling back to the clipboard."""
    import tts.text_sources as sources
    calls = {"reads": 0, "nudges": 0}

    def fake_read():
        calls["reads"] += 1
        if calls["reads"] == 1:
            raise sources.TextSourceError("no selection exposed yet")
        return "browser selection"

    def fake_nudge(wait_s=0.0):
        calls["nudges"] += 1
        return True

    monkeypatch.setattr(sources.window_focus, "active_process", lambda: "msedge.exe")
    monkeypatch.setattr(sources, "_read_uia_selection", fake_read)
    monkeypatch.setattr(sources, "enable_accessibility_for_foreground", fake_nudge)
    assert sources.read_selected_text() == "browser selection"
    assert calls["nudges"] == 1 and calls["reads"] == 2


def test_clipboard_fallback_still_used_when_nudge_does_not_help(monkeypatch):
    import tts.text_sources as sources
    monkeypatch.setattr(sources.window_focus, "active_process", lambda: "msedge.exe")
    monkeypatch.setattr(sources, "_read_uia_selection",
                        lambda: (_ for _ in ()).throw(
                            sources.TextSourceError("still nothing")))
    monkeypatch.setattr(sources, "enable_accessibility_for_foreground",
                        lambda wait_s=0.0: True)
    monkeypatch.setattr(sources, "_copy_selection_with_restore",
                        lambda *, timeout: "copied text")
    assert sources.read_selected_text(clipboard_fallback=True) == "copied text"
