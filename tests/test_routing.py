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


# -- per-app routing profiles ----------------------------------------------

SESSION = {"clipboard": False, "notes": True, "speak": False}


def test_effective_routes_inherits_session_when_no_rules():
    assert routing.effective_routes(SESSION, {}, "slack.exe") == SESSION
    assert routing.effective_routes(SESSION, {}, None) == SESSION


def test_effective_routes_override_on_and_off():
    rules = {"slack.exe": {"notes": False, "clipboard": True}}
    out = routing.effective_routes(SESSION, rules, "slack.exe")
    assert out == {"clipboard": True, "notes": False, "speak": False}


def test_effective_routes_unset_keys_inherit():
    rules = {"winword.exe": {"speak": True}}   # says nothing about notes/clip
    out = routing.effective_routes(SESSION, rules, "WINWORD.EXE")
    assert out == {"clipboard": False, "notes": True, "speak": True}


def test_effective_routes_matching_is_case_insensitive():
    rules = {"Slack.exe": {"notes": False}}
    assert routing.effective_routes(SESSION, rules, "slack.exe")["notes"] is False


def test_effective_routes_unknown_exe_is_session():
    rules = {"slack.exe": {"notes": False}}
    assert routing.effective_routes(SESSION, rules, "code.exe") == SESSION


def test_effective_routes_never_contains_inject_and_never_mutates():
    session = dict(SESSION)
    out = routing.effective_routes(session, {"x.exe": {"inject": False,
                                                       "notes": False}}, "x.exe")
    assert "inject" not in out
    assert out["notes"] is False
    assert session == SESSION            # input untouched


def test_effective_routes_ignores_unknown_route_keys():
    out = routing.effective_routes(SESSION, {"x.exe": {"teleport": True}}, "x.exe")
    assert out == SESSION
