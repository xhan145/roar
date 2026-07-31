"""Output registry: ordering, failure isolation, notes format, voice parsing."""

import datetime
import pathlib

import pytest

import routing


# -- active set ------------------------------------------------------------

def test_inject_is_always_active_and_first():
    assert routing.active_outputs({}) == ("inject",)


def test_active_outputs_follow_config_in_fixed_order():
    cfg = {"route_speak": True, "route_clipboard": True, "route_notes": True}
    assert routing.active_outputs(cfg) == ("inject", "clipboard", "notes",
                                           "speak")


def test_partial_selection_keeps_order():
    assert routing.active_outputs({"route_notes": True}) == ("inject", "notes")


# -- delivery --------------------------------------------------------------

def test_deliver_calls_each_handler_in_order():
    calls = []
    handlers = {o: (lambda t, o=o: calls.append(o))
                for o in ("inject", "clipboard", "notes")}
    routing.deliver("hi", ("inject", "clipboard", "notes"), handlers,
                    log=lambda m: None)
    assert calls == ["inject", "clipboard", "notes"]


def test_one_failing_output_never_blocks_the_rest():
    calls = []

    def boom(text):
        raise OSError("disk full")

    handlers = {"inject": lambda t: calls.append("inject"),
                "notes": boom,
                "speak": lambda t: calls.append("speak")}
    status = routing.deliver("hi", ("inject", "notes", "speak"), handlers,
                             log=lambda m: None)
    assert calls == ["inject", "speak"]
    assert status["inject"] == "ok" and status["speak"] == "ok"
    assert status["notes"].startswith("error")


def test_missing_handler_is_an_error_not_a_crash():
    status = routing.deliver("hi", ("inject", "notes"),
                             {"inject": lambda t: None}, log=lambda m: None)
    assert status["notes"].startswith("error")


# -- notes file ------------------------------------------------------------

def test_notes_line_format():
    now = datetime.datetime(2026, 7, 31, 14, 5)
    assert routing.notes_line("buy milk", now) == "[2026-07-31 14:05] buy milk\n"


def test_append_notes_creates_parents_and_appends(tmp_path):
    p = tmp_path / "sub" / "notes.md"
    routing.append_notes(p, "[t] one\n")
    routing.append_notes(p, "[t] two\n")
    assert p.read_text(encoding="utf-8") == "[t] one\n[t] two\n"


def test_append_notes_raises_cleanly_on_unwritable(tmp_path):
    with pytest.raises(OSError):
        routing.append_notes(pathlib.Path(tmp_path), "x")  # path IS a dir


# -- voice commands --------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("roar route notes on", ("notes", True)),
    ("Roar route notes off.", ("notes", False)),
    ("roar routes clipboard on", ("clipboard", True)),
    ("roar route speak off", ("speak", False)),
    ("roar routes off", "all_off"),
    ("roar routes off.", "all_off"),
])
def test_parse_route_command(text, expected):
    assert routing.parse_route_command(text) == expected


@pytest.mark.parametrize("text", [
    "roar route inject off",          # injection is not toggleable
    "roar route notes",               # missing on/off
    "please roar route notes on",     # not at utterance start
    "roar route nonsense on",
    "totally unrelated dictation",
    "",
])
def test_parse_route_command_rejects(text):
    assert routing.parse_route_command(text) is None


def test_parse_route_command_tolerates_recognizer_commas():
    assert routing.parse_route_command("Roar, route notes on.") == ("notes", True)
    assert routing.parse_route_command("Roar, routes off!") == "all_off"
