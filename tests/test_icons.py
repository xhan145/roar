import tray_icons

STATES = ["idle", "loading", "recording", "transcribing", "error"]


def test_all_states_render_64px_rgba():
    for state in STATES:
        img = tray_icons.make_icon(state)
        assert img.size == (64, 64)
        assert img.mode == "RGBA"


def test_states_visually_distinct():
    rendered = {s: tray_icons.make_icon(s).tobytes() for s in STATES}
    assert rendered["idle"] != rendered["recording"]
    assert rendered["recording"] != rendered["transcribing"]
    assert rendered["transcribing"] != rendered["error"]
    # shape decoration differs even between same-color states
    assert rendered["idle"] != rendered["loading"]
