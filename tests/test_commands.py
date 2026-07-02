import commands

REPL = {"new line": "\n", "new paragraph": "\n\n"}


def test_replacement_absorbs_surrounding_punctuation():
    out = commands.process("Hello there. New line. This is a test.", REPL)
    assert out == "Hello there.\nThis is a test."


def test_new_paragraph():
    out = commands.process("First part, new paragraph, second part.", REPL)
    assert out == "First part\n\nsecond part."


def test_capitalizes_first_letter():
    assert commands.process("hello world.", REPL) == "Hello world."


def test_strips_whitespace():
    assert commands.process("  hello  ", REPL) == "Hello"


def test_empty_returns_empty():
    assert commands.process("", REPL) == ""
    assert commands.process("   ", REPL) == ""


def test_solo_new_line_survives():
    assert commands.process("new line", REPL) == "\n"


def test_no_replacements_dict():
    assert commands.process("plain text", {}) == "Plain text"
