import cleanup


def test_interjections_removed():
    assert cleanup.clean("Um, hello there") == "hello there"
    assert cleanup.clean("so uh I think we uh should go") == "so I think we should go"
    assert cleanup.clean("hmm let me think") == "let me think"


def test_interjection_word_boundary_safe():
    # 'um'/'er' inside real words must survive
    assert cleanup.clean("the umbrella is over there") == "the umbrella is over there"
    assert cleanup.clean("summer water") == "summer water"


def test_stutter_collapse_allowlist():
    assert cleanup.clean("the the cat") == "the cat"
    assert cleanup.clean("I I think") == "I think"
    assert cleanup.clean("we we should go to to the store") == "we should go to the store"


def test_stutter_preserves_grammatical_doubles():
    # not on the allowlist -> left intact
    assert cleanup.clean("I had had enough") == "I had had enough"
    assert cleanup.clean("that that is wrong") == "that that is wrong"
    assert cleanup.clean("it was very very good") == "it was very very good"


def test_false_start_trim():
    assert cleanup.clean("I- I think so") == "I think so"
    assert cleanup.clean("wh- what happened") == "what happened"
    assert cleanup.clean("go— go to the door") == "go to the door"


def test_false_start_preserves_real_hyphenates():
    assert cleanup.clean("a well-known fact") == "a well-known fact"


def test_discourse_off_by_default():
    # comma-bounded 'like' stays when discourse is off
    assert cleanup.clean("it's, like, cool") == "it's, like, cool"


def test_discourse_comma_bounded_only():
    assert cleanup.clean("it's, like, cool", discourse=True) == "it's cool"
    assert cleanup.clean("well, you know, maybe", discourse=True) == "well maybe"
    # bare 'like' as a real verb is NEVER touched
    assert cleanup.clean("I like it", discourse=True) == "I like it"
    assert cleanup.clean("I like it") == "I like it"


def test_empty_and_whitespace():
    assert cleanup.clean("") == ""
    assert cleanup.clean("   ") == ""
    assert cleanup.clean("um") == ""
    assert cleanup.clean(None) == ""


def test_whitespace_and_punctuation_normalized():
    assert cleanup.clean("hello  ,  world") == "hello, world"
    assert cleanup.clean("uh,  hello") == "hello"


def test_hyphenated_affirmations_preserved():
    # 'uh-huh'/'mm-hmm' carry meaning (yes) — must not be split into a stray dash
    assert cleanup.clean("uh-huh") == "uh-huh"
    assert cleanup.clean("mm-hmm") == "mm-hmm"
    assert cleanup.clean("yeah uh-huh") == "yeah uh-huh"


def test_no_double_comma_after_interjection_removal():
    assert cleanup.clean("I think, um, so") == "I think, so"
    assert cleanup.clean("well, uh, maybe") == "well, maybe"
