"""Pure rule engine: predictable matching, consume semantics, validation."""

import automations as au


def rule(phrase="open terminal", action="open_app", params=None, enabled=True,
         trusted=False, consume=True):
    if params is None:
        params = {"target": "wt.exe"}
    return {"phrase": phrase, "action": action, "params": params,
            "enabled": enabled, "trusted": trusted, "consume": consume}


# -- normalization ---------------------------------------------------------

def test_normalize_case_punct_whitespace():
    assert au.normalize("  Open   Terminal!  ") == "open terminal"
    assert au.normalize("open, terminal.") == "open terminal"
    assert au.normalize("") == ""


# -- matching --------------------------------------------------------------

def test_whole_utterance_match_consumes_everything():
    m = au.match("Open terminal.", [rule()])
    assert len(m.actions) == 1
    assert m.actions[0]["action"] == "open_app"
    assert m.remaining_text == ""


def test_prefix_match_on_word_boundary_consumes_phrase():
    m = au.match("open terminal and make it big", [rule()])
    assert len(m.actions) == 1
    assert m.remaining_text == "and make it big"


def test_no_mid_sentence_fire():
    m = au.match("please open terminal now", [rule()])
    assert m.actions == []
    assert m.remaining_text == "please open terminal now"


def test_prefix_must_end_on_word_boundary():
    # "open terminals" must NOT fire "open terminal"
    m = au.match("open terminals are drafty", [rule()])
    assert m.actions == []


def test_disabled_rule_never_matches():
    m = au.match("open terminal", [rule(enabled=False)])
    assert m.actions == []
    assert m.remaining_text == "open terminal"


def test_consume_false_leaves_text_untouched():
    m = au.match("open terminal", [rule(consume=False)])
    assert len(m.actions) == 1
    assert m.remaining_text == "open terminal"


def test_no_chaining_only_exact_single_phrase_matches_one_rule():
    rules = [rule("open terminal"), rule("lights on", "open_url",
                                         {"url": "https://example.com"})]
    m = au.match("open terminal lights on", [*rules])
    # prefix match fires the first rule only; the rest is plain text
    assert len(m.actions) == 1
    assert m.remaining_text == "lights on"


def test_longest_phrase_wins_over_shorter_prefix():
    rules = [rule("open"), rule("open terminal")]
    m = au.match("open terminal", rules)
    assert len(m.actions) == 1
    assert m.actions[0]["phrase"] == "open terminal"


def test_matched_action_carries_rule_fields():
    m = au.match("open terminal", [rule(trusted=True)])
    a = m.actions[0]
    assert a["trusted"] is True
    assert a["params"] == {"target": "wt.exe"}
    assert a["utterance"] == "open terminal"


def test_empty_rules_and_empty_text_are_safe():
    assert au.match("", [rule()]).actions == []
    assert au.match("hello", []).remaining_text == "hello"


# -- validation ------------------------------------------------------------

def test_validate_accepts_a_good_rule():
    assert au.validate_rule(rule(), []) is None


def test_validate_rejects_empty_and_long_phrases():
    assert au.validate_rule(rule(phrase=""), []) is not None
    assert au.validate_rule(rule(phrase="x" * 61), []) is not None


def test_validate_rejects_unknown_action():
    assert au.validate_rule(rule(action="format_disk"), []) is not None


def test_validate_rejects_duplicate_phrase():
    existing = [rule()]
    assert au.validate_rule(rule(), existing) is not None
    assert au.validate_rule(rule(phrase="Open Terminal!"), existing) is not None


def test_validate_requires_action_params():
    assert au.validate_rule(rule(action="open_app", params={}), []) is not None
    assert au.validate_rule(
        rule(action="open_url", params={"url": "ftp://x"}), []) is not None
    assert au.validate_rule(
        rule(action="open_url", params={"url": "https://x.com"}), []) is None
    assert au.validate_rule(
        rule(action="webhook", params={"url": "https://x.com"}), []) is None


def test_scripted_actions_set():
    assert au.SCRIPTED_ACTIONS == {"run_script", "webhook"}
    for a in au.SCRIPTED_ACTIONS:
        assert a in au.KNOWN_ACTIONS
