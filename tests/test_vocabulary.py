from vocabulary import MAX_CUSTOM, merge_hotwords, validate_entry


def test_merge_dedupes_case_insensitively_custom_first():
    s = merge_hotwords(["ScratchEdge", "Kubernetes"], ["kubernetes", "roar"])
    assert s == "ScratchEdge Kubernetes roar"


def test_merge_trims_and_drops_empties():
    assert merge_hotwords(["  padded  ", "", "  "], []) == "padded"


def test_merge_empty_returns_none():
    assert merge_hotwords([], []) is None
    assert merge_hotwords(["  "], [""]) is None


def test_merge_cap():
    custom = [f"word{i:02d}" for i in range(50)]
    sig = [f"sig{i}" for i in range(20)]
    merged = merge_hotwords(custom, sig, cap=60).split()
    assert len(merged) == 60
    assert merged[0] == "word00" and merged[49] == "word49"  # custom first
    assert merged[50] == "sig0"


def test_validate_entry_rules():
    assert validate_entry("ok", []) is None
    assert validate_entry("x", []) is not None            # too short
    assert validate_entry("y" * 41, []) is not None       # too long
    assert validate_entry("dupe", ["DUPE"]) is not None   # case-insensitive dup
    assert validate_entry("ctl\x07chr", []) is not None   # control char
    assert validate_entry("word", [f"w{i}" for i in range(MAX_CUSTOM)]) is not None
    assert validate_entry("  spaced  ", []) is None       # trimmed before checks


def test_merge_guards_against_non_list_inputs():
    # a mistyped config (bare string) must not become per-character hotwords
    assert merge_hotwords("hello", []) is None
    assert merge_hotwords(None, "world") is None
    assert merge_hotwords({"a": 1}, ["ok"]) == "ok"


def test_phrases_normalized_not_rejected():
    from vocabulary import normalize_entry
    assert validate_entry("New   York", []) is None
    assert normalize_entry("New \t York ") == "New York"
