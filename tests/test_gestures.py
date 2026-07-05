import gestures
from gestures import TapToggleDetector as D, START, FINISH, DEFER, HANDSFREE, STOP, NONE


def test_hold_is_ptt():
    d = D()
    assert d.feed("down", 0.0) == START
    assert d.feed("up", 1.0) == FINISH          # long press -> immediate finish


def test_single_tap_defers_then_finishes():
    d = D(double_tap_s=0.4)
    assert d.feed("down", 0.0) == START
    assert d.feed("up", 0.1) == DEFER           # short press -> wait for a 2nd tap
    assert d.on_defer_timeout(0.5) == FINISH     # none came -> finish


def test_double_tap_enters_handsfree_one_session():
    d = D(double_tap_s=0.4)
    assert d.feed("down", 0.0) == START
    assert d.feed("up", 0.1) == DEFER
    assert d.feed("down", 0.3) == HANDSFREE      # 2nd tap within window
    assert d.feed("up", 0.4) == NONE             # release ignored while locked
    assert d.on_defer_timeout(0.5) == NONE       # racing timer is a no-op now
    assert d.feed("down", 5.0) == STOP           # later single tap stops
    assert d.feed("up", 5.1) == NONE


def test_second_tap_after_window_is_not_double():
    d = D(double_tap_s=0.4)
    d.feed("down", 0.0); d.feed("up", 0.1)
    assert d.feed("down", 0.9) == START          # gap > window -> fresh press
    assert d.feed("up", 1.5) == FINISH


def test_hold_on_second_tap_still_handsfree():
    d = D(double_tap_s=0.4)
    d.feed("down", 0.0); d.feed("up", 0.1)
    assert d.feed("down", 0.3) == HANDSFREE
    assert d.feed("up", 2.0) == NONE             # long 2nd press still ignored
    assert d.feed("down", 3.0) == STOP


def test_triple_tap_on_then_off():
    d = D(double_tap_s=0.4)
    d.feed("down", 0.0); d.feed("up", 0.1)
    assert d.feed("down", 0.2) == HANDSFREE
    d.feed("up", 0.25)
    assert d.feed("down", 0.3) == STOP           # 3rd tap stops it
