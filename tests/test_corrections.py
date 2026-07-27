"""Personal corrections: teach ROAR the words it keeps mishearing.

Distinct from commands.apply_replacements, which deliberately ABSORBS
surrounding punctuation/space ("new line" -> "\n"). A word correction must
leave the sentence intact: only the misheard word is swapped.
"""
import pytest

import corrections


# --- applying corrections ---------------------------------------------------

def test_replaces_a_misheard_word():
    assert corrections.apply("I use pie plot daily",
                             {"pie plot": "PyPlot"}) == "I use PyPlot daily"


def test_preserves_surrounding_punctuation_and_spacing():
    # the command-style replacer would eat the period and the spaces here
    assert corrections.apply("I use pie plot.",
                             {"pie plot": "PyPlot"}) == "I use PyPlot."
    assert corrections.apply("pie plot, then rest",
                             {"pie plot": "PyPlot"}) == "PyPlot, then rest"


def test_is_case_insensitive_when_matching():
    assert corrections.apply("Pie Plot rules",
                             {"pie plot": "PyPlot"}) == "PyPlot rules"


def test_keeps_the_intended_casing_of_the_replacement():
    # the user taught "PyPlot" — capitalization of the fix is theirs to choose
    assert corrections.apply("pie plot", {"pie plot": "PyPlot"}) == "PyPlot"


def test_capitalizes_replacement_at_sentence_start_when_taught_lowercase():
    # taught lowercase, but it lands where a sentence begins
    assert corrections.apply("kubernetes is fine. cuber netes too",
                             {"cuber netes": "kubernetes"}) == \
        "kubernetes is fine. Kubernetes too"


def test_only_matches_whole_words():
    assert corrections.apply("scalable", {"cal": "Cal"}) == "scalable"


def test_longest_phrase_wins():
    out = corrections.apply("new york city", {"new york": "NY",
                                              "new york city": "NYC"})
    assert out == "NYC"


def test_empty_inputs_are_safe():
    assert corrections.apply("", {"a": "b"}) == ""
    assert corrections.apply("text", {}) == "text"
    assert corrections.apply("text", None) == "text"


# --- learning a correction from a real mistake ------------------------------

def test_learn_extracts_the_changed_words():
    pair = corrections.learn("I use pie plot daily", "I use PyPlot daily")
    assert pair == ("pie plot", "PyPlot")


def test_learn_handles_a_single_word_fix():
    assert corrections.learn("send it to bob", "send it to Bob") == ("bob", "Bob")


def test_learn_returns_none_when_nothing_changed():
    assert corrections.learn("same text", "same text") is None


def test_learn_returns_none_when_edit_is_too_broad():
    # a wholesale rewrite is not a word correction; refuse to guess
    assert corrections.learn("one two three four",
                             "completely different sentence entirely") is None


def test_learn_ignores_pure_punctuation_edits():
    assert corrections.learn("hello there", "hello there!") is None


# --- validation -------------------------------------------------------------

def test_validate_rejects_empty_and_self_mapping():
    existing = {}
    assert corrections.validate("", "x", existing) is not None
    assert corrections.validate("x", "", existing) is not None
    assert corrections.validate("same", "same", existing) is not None


def test_validate_rejects_duplicate_heard_phrase():
    existing = {"pie plot": "PyPlot"}
    assert corrections.validate("Pie Plot", "Matplotlib", existing) is not None


def test_validate_rejects_overlong_entries():
    assert corrections.validate("a" * 200, "b", {}) is not None


def test_validate_accepts_a_good_pair():
    assert corrections.validate("pie plot", "PyPlot", {}) is None


def test_normalize_lowercases_and_collapses_space():
    assert corrections.normalize_heard("  Pie   Plot ") == "pie plot"
