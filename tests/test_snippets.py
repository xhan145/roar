import snippets

SNIPS = {"sig": "Thanks,\nGreg", "addr": "42 Roar St"}


def test_keyword_form_expands():
    out = snippets.expand("please snippet sig today", SNIPS)
    assert out == "please Thanks,\nGreg today"


def test_keyword_case_insensitive_and_sentence_start():
    assert snippets.expand("Snippet sig", SNIPS) == "Thanks,\nGreg"


def test_literal_slash_form():
    assert snippets.expand("send to /addr now", SNIPS) == "send to 42 Roar St now"


def test_unknown_name_left_alone():
    assert snippets.expand("snippet nope and /nada", SNIPS) == "snippet nope and /nada"


def test_no_recursion_single_pass():
    out = snippets.expand("snippet a", {"a": "see snippet b", "b": "BOOM"})
    assert out == "see snippet b"


def test_word_boundaries():
    assert snippets.expand("crosssnippet sig", SNIPS) == "crosssnippet sig"
    assert snippets.expand("path//sig", SNIPS) == "path//sig"


def test_variables(monkeypatch):
    out = snippets.expand("snippet st", {"st": "at {time} clip={clipboard}"},
                          clipboard_getter=lambda: "CLIP")
    import re
    assert re.search(r"at \d{2}:\d{2} clip=CLIP", out)


def test_clipboard_failure_empty(monkeypatch):
    def boom():
        raise RuntimeError("no clipboard")
    out = snippets.expand("snippet c", {"c": "[{clipboard}]"},
                          clipboard_getter=boom)
    assert out == "[]"


def test_unknown_variable_left_literal():
    assert snippets.expand("snippet u", {"u": "{unknown}"}) == "{unknown}"


def test_validate_rules():
    assert snippets.validate("sig", "x", {}) is None
    assert snippets.validate("bad name", "x", {}) is not None
    assert snippets.validate("", "x", {}) is not None
    assert snippets.validate("a" * 31, "x", {}) is not None
    assert snippets.validate("ok", "", {}) is not None
    assert snippets.validate("ok", "y" * 2001, {}) is not None
    full = {f"s{i}": "x" for i in range(snippets.MAX_SNIPPETS)}
    assert snippets.validate("new", "x", full) is not None
    assert snippets.validate("s1", "x", full) is None  # editing existing ok
