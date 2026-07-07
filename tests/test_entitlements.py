import logging

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


def test_can_use_is_alias_of_allowed():
    assert ent.can_use is ent.allowed


def test_unknown_features_default_allowed_and_warn(caplog):
    with caplog.at_level(logging.WARNING, logger="roar.entitlements"):
        assert ent.allowed("future.shiny", "core") is True
    assert any("unregistered entitlement feature" in r.getMessage()
               for r in caplog.records)


def test_features_for_edition():
    core = ent.features_for_edition("core")
    assert "dictation.push_to_talk" in core
    assert "code.mode" not in core
    dev = ent.features_for_edition("developer")
    assert "code.mode" in dev and "snippets.packs" in dev
    # supporter has everything developer has
    assert ent.features_for_edition("supporter") == dev


def test_requires_upgrade():
    assert ent.requires_upgrade("code.mode", "core") is True
    assert ent.requires_upgrade("code.mode", "developer") is False
    assert ent.requires_upgrade("privacy.controls", "core") is False   # always free
    assert ent.requires_upgrade("future.shiny", "core") is False       # unknown


def test_minimum_edition_for():
    assert ent.minimum_edition_for("privacy.controls") == "core"
    assert ent.minimum_edition_for("snippets.packs") == "pro"
    assert ent.minimum_edition_for("code.mode") == "developer"
    assert ent.minimum_edition_for("future.shiny") is None


def test_known_features_registry():
    assert ent.ALWAYS_FREE <= ent.KNOWN_FEATURES
    assert ent._PAID <= ent.KNOWN_FEATURES
    assert "code.mode" in ent.KNOWN_FEATURES
    # privacy/delete controls can never be paid-only
    for f in ("privacy.controls", "history.delete", "audio.delete"):
        assert f in ent.ALWAYS_FREE
