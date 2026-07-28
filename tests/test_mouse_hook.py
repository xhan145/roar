"""Point & Speak trigger logic: Ctrl+right-click fires, everything else passes.

Pure decision function only — the Win32 hook shell is exercised live on
Windows (see docs/superpowers/specs/2026-07-27-point-and-speak-design.md).
"""
import mouse_hook


UP = mouse_hook.WM_RBUTTONUP
DOWN = mouse_hook.WM_RBUTTONDOWN


def test_fires_on_ctrl_right_up():
    assert mouse_hook.should_trigger(UP, ctrl_down=True, enabled=True,
                                     now=10.0, last_fire=0.0) is True


def test_never_fires_without_ctrl():
    assert mouse_hook.should_trigger(UP, ctrl_down=False, enabled=True,
                                     now=10.0, last_fire=0.0) is False


def test_never_fires_when_disabled():
    assert mouse_hook.should_trigger(UP, ctrl_down=True, enabled=False,
                                     now=10.0, last_fire=0.0) is False


def test_only_button_up_counts():
    # firing on DOWN would race the app's own selection handling
    assert mouse_hook.should_trigger(DOWN, ctrl_down=True, enabled=True,
                                     now=10.0, last_fire=0.0) is False
    assert mouse_hook.should_trigger(0x0200, ctrl_down=True, enabled=True,
                                     now=10.0, last_fire=0.0) is False  # move


def test_debounce_blocks_rapid_repeat():
    assert mouse_hook.should_trigger(UP, ctrl_down=True, enabled=True,
                                     now=10.0, last_fire=9.9) is False
    assert mouse_hook.should_trigger(UP, ctrl_down=True, enabled=True,
                                     now=10.0, last_fire=9.8) is False


def test_debounce_expires():
    assert mouse_hook.should_trigger(UP, ctrl_down=True, enabled=True,
                                     now=10.0, last_fire=9.6,
                                     debounce_s=0.3) is True


def test_hook_lifecycle_is_idempotent():
    """start/stop twice must not raise; stop before start is a no-op.
    Uses a stubbed installer so no real Win32 hook is created."""
    calls = []
    h = mouse_hook.PointerGestureHook(lambda: calls.append(1))
    h._install = lambda: True         # stub the Win32 layer
    h._uninstall = lambda: None
    h.stop()                          # before start: no-op
    h.start(); h.start()              # double start: one install
    h.stop(); h.stop()                # double stop: safe
    assert h._running is False
