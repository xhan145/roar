import time

import overlay


def test_bar_heights_padding_and_floor():
    assert overlay.bar_heights([], n=4, h=28) == [2, 2, 2, 2]
    out = overlay.bar_heights([0.0, 1.0], n=4, h=28)
    assert out == [2, 2, 2, 28]


def test_bar_heights_takes_most_recent():
    out = overlay.bar_heights([1.0] + [0.0] * 10, n=4, h=20)
    assert out == [2, 2, 2, 2]


def test_tail_text():
    assert overlay.tail_text("short") == "short"
    long = "word " * 30
    out = overlay.tail_text(long, max_chars=20)
    assert len(out) == 20 and out.startswith("…")
    assert overlay.tail_text("  spaced   out  ") == "spaced out"


def test_overlay_lifecycle_smoke():
    ov = overlay.Overlay()
    ov.start()
    deadline = time.time() + 10
    while time.time() < deadline and not ov.available:
        time.sleep(0.1)
    assert ov.available
    ov.show_recording()
    for i in range(30):
        ov.push_level(i / 30)
    ov.set_partial("hello streaming world")
    time.sleep(0.3)          # a few ticks render
    ov.show_transcribing()
    ov.hide()
    ov.stop()
    time.sleep(0.3)          # clean shutdown, no exceptions
