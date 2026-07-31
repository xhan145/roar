"""Fob pure helpers — gesture classification and screen geometry. No Tk.

The overlay window feeds raw mouse events into GestureClassifier and positions
itself with the geometry functions; keeping both pure means the whole
interaction model is unit-testable without a display.
"""

DRAG_THRESHOLD_PX = 6
EDGE_MARGIN = 4


class GestureClassifier:
    """Distinguish a tap from a drag. press/move/release mirror the mouse.

    move() returns (dx, dy) from the press point once the pointer has crossed
    DRAG_THRESHOLD_PX (and forever after, for live window dragging); None
    before that. release() returns "tap", "drag", or None when nothing was
    pressed. The instance is reusable after release.
    """

    def __init__(self, threshold=DRAG_THRESHOLD_PX):
        self._threshold = threshold
        self._origin = None
        self._dragging = False

    def press(self, x, y):
        self._origin = (x, y)
        self._dragging = False

    def move(self, x, y):
        if self._origin is None:
            return None
        dx, dy = x - self._origin[0], y - self._origin[1]
        if not self._dragging and (dx * dx + dy * dy) > self._threshold ** 2:
            self._dragging = True
        return (dx, dy) if self._dragging else None

    def release(self):
        if self._origin is None:
            return None
        result = "drag" if self._dragging else "tap"
        self._origin, self._dragging = None, False
        return result


def clamp_pos(x, y, w, h, bounds, margin=EDGE_MARGIN):
    """Keep a w×h window fully inside bounds=(left, top, right, bottom).
    Bounds may have negative origins (multi-monitor virtual screen)."""
    left, top, right, bottom = bounds
    x = max(left + margin, min(int(x), right - w - margin))
    y = max(top + margin, min(int(y), bottom - h - margin))
    return x, y


def default_pos(bounds, w, h):
    """Bottom-center of the given bounds, above the taskbar area."""
    left, top, right, bottom = bounds
    return (left + (right - left - w) // 2, bottom - h - 110)


def validate_pos(pos, w, h, bounds):
    """A persisted position is honoured only if at least half the window is
    inside the current virtual screen — guards against unplugged monitors.
    Returns (x, y) or None."""
    try:
        x, y = int(pos[0]), int(pos[1])
    except (TypeError, ValueError, IndexError):
        return None
    left, top, right, bottom = bounds
    cx, cy = x + w // 2, y + h // 2
    if left <= cx <= right and top <= cy <= bottom:
        return (x, y)
    return None


def expand_anchor(dot_x, dot_y, dot_size, pill_w, pill_h, bounds):
    """Top-left for the pill so it is centred on the dot where possible and
    never expands off-screen."""
    cx, cy = dot_x + dot_size // 2, dot_y + dot_size // 2
    return clamp_pos(cx - pill_w // 2, cy - pill_h // 2, pill_w, pill_h, bounds)
