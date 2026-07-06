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


def test_snippet_expansion_in_pipeline():
    out = commands.process("snippet sig", {}, {"sig": "Thanks,\nGreg"})
    assert out == "Thanks,\nGreg"


def test_snippets_after_replacements_and_capitalize():
    out = commands.process("hello new line snippet sig", REPL,
                           {"sig": "greg"})
    assert out == "Hello\ngreg"   # capitalize hit transcript, not expansion


def test_process_backcompat_two_args():
    assert commands.process("plain", {}) == "Plain"


def test_cleanup_runs_before_capitalize():
    out = commands.process("um, hello there", {}, cleanup=True)
    assert out == "Hello there"


def test_cleanup_off_by_default_in_signature():
    assert commands.process("um hello", {}) == "Um hello"


def test_cleanup_then_replacement():
    out = commands.process("uh new line done", REPL, cleanup=True)
    assert out == "\nDone"


def test_discourse_gated_by_flag():
    assert commands.process("it's, like, cool", {}, cleanup=True) == "It's, like, cool"
    assert commands.process("it's, like, cool", {}, cleanup=True,
                            discourse_fillers=True) == "It's cool"


def test_raw_mode_preserves_spoken_symbol_words():
    out = commands.process("colon new line", {"new line": "\n"},
                           cleanup=True, mode="raw")
    assert out == "Colon new line"


def test_code_mode_applies_symbols_without_prose_cleanup():
    out = commands.process("foo colon bar new line baz", {},
                           cleanup=True, mode="code")
    assert out == "foo: bar\nbaz"


def test_clean_mode_does_not_turn_symbol_words_into_punctuation():
    out = commands.process("please type colon here", {},
                           cleanup=True, mode="clean")
    assert out == "Please type colon here"
