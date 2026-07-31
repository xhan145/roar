"""Fob pure helpers: tap/drag classifier + screen geometry math."""

import fob

BOUNDS = (0, 0, 1920, 1080)                 # single monitor
MULTI = (-1920, -200, 1920, 1080)           # second monitor left of primary


# -- gesture classifier -----------------------------------------------------

def test_press_release_under_threshold_is_a_tap():
    g = fob.GestureClassifier()
    g.press(100, 100)
    assert g.move(102, 103) is None          # under threshold: no drag yet
    assert g.release() == "tap"


def test_movement_over_threshold_becomes_a_drag():
    g = fob.GestureClassifier()
    g.press(100, 100)
    assert g.move(100 + fob.DRAG_THRESHOLD_PX + 1, 100) == (
        fob.DRAG_THRESHOLD_PX + 1, 0)
    assert g.release() == "drag"


def test_drag_keeps_reporting_offsets_after_threshold():
    g = fob.GestureClassifier()
    g.press(50, 50)
    g.move(80, 50)
    assert g.move(52, 55) == (2, 5)          # once dragging, always offsets
    assert g.release() == "drag"


def test_release_without_press_is_none_and_reusable():
    g = fob.GestureClassifier()
    assert g.release() is None
    g.press(10, 10)
    assert g.release() == "tap"
    g.press(10, 10)                          # reusable after release
    g.move(60, 60)
    assert g.release() == "drag"


def test_move_without_press_is_ignored():
    g = fob.GestureClassifier()
    assert g.move(500, 500) is None
    assert g.release() is None


# -- geometry ---------------------------------------------------------------

def test_clamp_keeps_window_inside_bounds():
    assert fob.clamp_pos(-50, -50, 100, 40, BOUNDS) == (4, 4)
    assert fob.clamp_pos(5000, 5000, 100, 40, BOUNDS) == (1920 - 104, 1080 - 44)
    assert fob.clamp_pos(300, 300, 100, 40, BOUNDS) == (300, 300)


def test_clamp_handles_negative_origin_virtual_screen():
    # y=0 is already inside the [-200, 1080] band, so only x gets clamped
    assert fob.clamp_pos(-3000, 0, 100, 40, MULTI) == (-1916, 0)


def test_default_pos_is_bottom_center():
    x, y = fob.default_pos(BOUNDS, 34, 34)
    assert x == (1920 - 34) // 2
    assert 900 < y < 1080 - 34


def test_validate_pos_accepts_mostly_visible_positions():
    assert fob.validate_pos([300, 300], 34, 34, BOUNDS) == (300, 300)
    assert fob.validate_pos((-1900, 0), 34, 34, MULTI) == (-1900, 0)


def test_validate_pos_rejects_offscreen_and_garbage():
    assert fob.validate_pos([5000, 300], 34, 34, BOUNDS) is None   # unplugged
    assert fob.validate_pos([-1900, 0], 34, 34, BOUNDS) is None    # monitor gone
    assert fob.validate_pos(None, 34, 34, BOUNDS) is None
    assert fob.validate_pos("nope", 34, 34, BOUNDS) is None
    assert fob.validate_pos([1, "x"], 34, 34, BOUNDS) is None


def test_expand_anchor_centers_pill_on_dot():
    x, y = fob.expand_anchor(960, 500, 34, 360, 44, BOUNDS)
    assert x == 960 + 17 - 180                # centred on dot centre
    assert y == 500 + 17 - 22


def test_expand_anchor_clamps_at_screen_edges():
    x, y = fob.expand_anchor(10, 10, 34, 360, 44, BOUNDS)
    assert (x, y) == (4, 5)   # x clamped to margin; y = dot centre - pill/2
    x, y = fob.expand_anchor(1910, 1070, 34, 360, 44, BOUNDS)
    assert x == 1920 - 364 and y == 1080 - 48
