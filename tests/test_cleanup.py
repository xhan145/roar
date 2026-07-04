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


def test_interjection_only_with_punctuation_yields_empty():
    # "hmm." must not inject a lone period
    assert cleanup.clean("hmm.") == ""
    assert cleanup.clean("um.") == ""
    assert cleanup.clean("uh?") == ""
    assert cleanup.clean("um. hello") == "hello"


def test_asr_split_hyphenates_preserved():
    # Whisper splits hyphenates on a pause: fragment is NOT a prefix of the
    # next word, so it's a real word, not a stutter
    assert cleanup.clean("e- mail me") == "e- mail me"
    assert cleanup.clean("co- op meeting") == "co- op meeting"
    assert cleanup.clean("x- ray results") == "x- ray results"
    assert cleanup.clean("well- known fact") == "well- known fact"
    # true stutters (fragment IS a prefix of the next word) still trim
    assert cleanup.clean("tha- that works") == "that works"


def test_stacked_discourse_fillers_all_removed():
    assert cleanup.clean("it's, like, you know, cool", discourse=True) == "it's cool"
    assert cleanup.clean("so, you know, like, i mean, anyway",
                         discourse=True) == "so anyway"
    assert cleanup.clean("well, i mean, you know, sure", discourse=True) == "well sure"


def test_homograph_fillers_safe_at_sentence_edges():
    # single-word homographs are removed ONLY when fully comma-bounded;
    # at sentence edges they are real words ("Actually, ..." = contrast,
    # ", right" = tag question that changes meaning if dropped)
    assert cleanup.clean("Actually, I think so", discourse=True) == "Actually, I think so"
    assert cleanup.clean("It works, right", discourse=True) == "It works, right"
    # multi-word phrases at edges are unambiguous fillers -> removed
    assert cleanup.clean("You know, maybe later", discourse=True) == "maybe later"
