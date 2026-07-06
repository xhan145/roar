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


def test_no_recursion_slash_form_in_expansion():
    out = snippets.expand("snippet a", {"a": "see /b", "b": "BOOM"})
    assert out == "see /b"
    out = snippets.expand("/a", {"a": "chain /a", "b": "x"})
    assert out == "chain /a"


def test_clipboard_variable_is_bounded_and_flagged():
    text = snippets.resolve_variables("{clipboard}",
                                      clipboard_getter=lambda: "x" * 50000)
    assert len(text) == snippets.MAX_CLIPBOARD_CHARS
    assert snippets.uses_clipboard("{date} {clipboard}") is True
    assert snippets.uses_clipboard("{clip}") is False


def test_validate_pack_skips_invalid_and_warns_clipboard():
    existing = {"sig": "old"}
    incoming = {
        "sig": "new",
        "bad name": "nope",
        "clip": "paste {clipboard}",
        "too-long": "x" * (snippets.MAX_EXPANSION + 1),
    }
    accepted, summary = snippets.validate_pack(incoming, existing)
    assert accepted == {"sig-2": "new", "clip": "paste {clipboard}"}
    assert summary["added"] == 2
    assert summary["renamed"] == 1
    assert summary["skipped"] == 2
    assert summary["clipboard"] == ["clip"]
