"""core < pro < developer <= supporter, and Core stays free where it matters.

These are product promises, not implementation details: if one of these fails,
someone has made a privacy or accessibility feature paid-only.
"""

import commercial_config as cc
import entitlements as ent

# Features that MUST be free forever — privacy and local-data control.
CORE_FREE = [
    "dictation.push_to_talk",
    "dictation.hands_free",
    "dictation.streaming",
    "dictation.multilingual",
    "dictation.scratch_that",
    "commands.basic",
    "history.basic",
    "history.delete",
    "audio.delete",
    "privacy.controls",
    "vocabulary.basic",
    "diagnostics.safe",
]


def test_supporter_inherits_developer():
    assert ent.features_for_edition(ent.DEVELOPER) <= ent.features_for_edition(
        ent.SUPPORTER)


def test_developer_inherits_pro():
    assert ent.features_for_edition(ent.PRO) <= ent.features_for_edition(
        ent.DEVELOPER)


def test_pro_inherits_core():
    assert ent.features_for_edition(ent.CORE) <= ent.features_for_edition(ent.PRO)


def test_supporter_has_no_exclusive_features():
    """Supporter is a price tier, not a feature tier — we never invent a
    feature that only supporters get."""
    assert ent.features_for_edition(ent.SUPPORTER) == ent.features_for_edition(
        ent.DEVELOPER)


def test_core_keeps_privacy_and_deletion_free():
    for feature in CORE_FREE:
        assert feature in ent.ALWAYS_FREE, feature
        assert ent.allowed(feature, edition=ent.CORE) is True, feature
        assert ent.requires_upgrade(feature, edition=ent.CORE) is False, feature


def test_unknown_edition_resolves_to_core_not_more():
    assert ent.features_for_edition("bogus-edition") == ent.features_for_edition(
        ent.CORE)
    assert ent.features_for_edition(None) == ent.features_for_edition(ent.CORE)


def test_pricing_and_entitlements_share_the_same_edition_ids():
    """Two modules, one vocabulary — a rename in either must break this."""
    assert tuple(cc.PRICING) == ent.EDITIONS
    assert cc.PAID_EDITIONS == tuple(e for e in ent.EDITIONS if e != ent.CORE)


def test_free_edition_is_exactly_the_free_price():
    for edition, entry in cc.PRICING.items():
        is_free = entry["price_usd"] == 0
        assert is_free == (edition == ent.CORE), edition
