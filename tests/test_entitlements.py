import entitlements as ent


def test_privacy_and_core_always_free_for_every_edition():
    for edition in (None, "", "core", "pro", "developer", "supporter",
                    "corrupt-garbage", 42):
        for feature in ent.ALWAYS_FREE:
            assert ent.allowed(feature, edition) is True, (feature, edition)


def test_unknown_edition_degrades_to_core():
    assert ent.normalize_edition(None) == "core"
    assert ent.normalize_edition("Ultimate") == "core"
    assert ent.normalize_edition(" PRO ") == "pro"
    assert ent.allowed("snippets.packs", "not-a-real-edition") is False


def test_paid_tiers():
    assert ent.allowed("snippets.packs", "core") is False
    assert ent.allowed("snippets.packs", "pro") is True
    assert ent.allowed("profiles.apps", "pro") is False       # developer-tier
    assert ent.allowed("profiles.apps", "developer") is True
    assert ent.allowed("profiles.apps", "supporter") is True  # gets everything
    assert ent.allowed("snippets.packs", "supporter") is True


def test_unknown_features_default_allowed():
    assert ent.allowed("future.shiny", "core") is True
