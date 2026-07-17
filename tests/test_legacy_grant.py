"""Grandfathering: an install that predates gating keeps exactly the features it
already had — and nothing more. These tests pin the invariants that make the
grant safe."""
import json

import entitlements as ent
import legacy_grant as lg
from entitlements import CORE, PRO, DEVELOPER, SUPPORTER


def _legacy_cfg():
    return {"model": "auto", "language": "en"}          # no schema marker


def _gated_cfg():
    return {"model": "auto", lg.SCHEMA_KEY: lg.SCHEMA_VERSION}


# -- pure decision --------------------------------------------------------

def test_pre_gating_config_is_legacy():
    assert lg.is_legacy_install(_legacy_cfg()) is True


def test_stamped_config_is_not_legacy():
    assert lg.is_legacy_install(_gated_cfg()) is False


def test_fresh_install_is_not_legacy():
    # a brand-new install has no config yet -> nothing to grandfather
    assert lg.is_legacy_install({}) is False
    assert lg.is_legacy_install(None) is False


def test_grant_for_legacy_is_the_shipped_free_set():
    assert lg.grant_for(_legacy_cfg()) == lg.GRANTED_FEATURES


def test_grant_for_fresh_is_empty():
    assert lg.grant_for({}) == frozenset()
    assert lg.grant_for(_gated_cfg()) == frozenset()


# -- the safety invariants ------------------------------------------------

def test_grant_never_includes_a_never_shipped_feature():
    """Planned Developer features were never free, so they are never granted."""
    for planned in ("vocabulary.project", "snippets.developer_packs",
                    "files.tagging"):
        assert planned not in lg.GRANTED_FEATURES


def test_grant_only_contains_registered_paid_features():
    assert lg.GRANTED_FEATURES <= ent.KNOWN_FEATURES
    # granting an always-free feature would be meaningless
    assert not (lg.GRANTED_FEATURES & ent.ALWAYS_FREE)


def test_grant_never_names_an_edition():
    """A grant is feature IDs only — it can never smuggle in an edition."""
    assert not (lg.GRANTED_FEATURES & set(ent.EDITIONS))
    for f in lg.GRANTED_FEATURES:
        assert f not in ent.EDITIONS


# -- persistence ----------------------------------------------------------

def test_ensure_grant_writes_once_for_legacy_install(tmp_path):
    p = tmp_path / "legacy_grant.json"
    granted = lg.ensure_grant(_legacy_cfg(), str(p), log=lambda *a: None)
    assert granted == lg.GRANTED_FEATURES
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert sorted(data["features"]) == sorted(lg.GRANTED_FEATURES)


def test_ensure_grant_is_idempotent(tmp_path):
    p = tmp_path / "legacy_grant.json"
    first = lg.ensure_grant(_legacy_cfg(), str(p), log=lambda *a: None)
    mtime = p.stat().st_mtime_ns
    # a stamped config on the second run must not re-grant or rewrite
    second = lg.ensure_grant(_gated_cfg(), str(p), log=lambda *a: None)
    assert second == first
    assert p.stat().st_mtime_ns == mtime


def test_fresh_install_gets_no_grant_file(tmp_path):
    p = tmp_path / "legacy_grant.json"
    assert lg.ensure_grant({}, str(p), log=lambda *a: None) == frozenset()
    assert not p.exists()


def test_load_grants_missing_is_empty(tmp_path):
    assert lg.load_grants(str(tmp_path / "nope.json")) == frozenset()


def test_load_grants_corrupt_is_empty(tmp_path):
    p = tmp_path / "legacy_grant.json"
    p.write_text("{not json", encoding="utf-8")
    assert lg.load_grants(str(p)) == frozenset()


def test_hand_edited_grant_cannot_widen_beyond_shipped_free_set(tmp_path):
    """Someone adding a never-shipped feature (or junk) to the file gains
    nothing — only the known grandfathered set is honoured."""
    p = tmp_path / "legacy_grant.json"
    p.write_text(json.dumps({"features": [
        "snippets.packs",            # legitimately granted
        "vocabulary.project",        # never shipped free -> ignored
        "files.tagging",             # never shipped free -> ignored
        "totally.made.up",           # junk -> ignored
    ]}), encoding="utf-8")
    assert lg.load_grants(str(p)) == frozenset({"snippets.packs"})


# -- entitlements honour grants without becoming an edition ---------------

def test_grant_unlocks_only_the_granted_feature():
    grants = frozenset({"snippets.packs"})
    assert ent.allowed("snippets.packs", CORE, grants) is True
    assert ent.allowed("code.mode", CORE, grants) is False     # not granted


def test_grant_does_not_make_the_user_pro():
    grants = lg.GRANTED_FEATURES
    # they keep what they had...
    assert ent.allowed("formatting.smart", CORE, grants) is True
    # ...but a never-shipped Developer feature stays locked
    assert ent.allowed("vocabulary.project", CORE, grants) is False
    assert ent.allowed("files.tagging", CORE, grants) is False


def test_requires_upgrade_false_for_granted_feature():
    grants = frozenset({"formatting.smart"})
    assert ent.requires_upgrade("formatting.smart", CORE, grants) is False
    assert ent.requires_upgrade("formatting.smart", CORE) is True   # ungranted


def test_features_for_edition_includes_grants():
    grants = frozenset({"snippets.packs"})
    feats = ent.features_for_edition(CORE, grants)
    assert "snippets.packs" in feats
    assert "vocabulary.project" not in feats


def test_grants_never_widen_a_paid_edition_beyond_its_tier():
    # junk grants can't add unknown features to any edition's set
    feats = ent.features_for_edition(PRO, frozenset({"totally.made.up"}))
    assert "totally.made.up" not in feats


# -- core promises still hold with grants in play -------------------------

def test_core_features_free_in_every_edition_regardless_of_grants():
    for edition in (None, CORE, PRO, DEVELOPER, SUPPORTER, "bogus"):
        for feature in ("dictation.push_to_talk", "privacy.controls",
                        "history.delete", "audio.delete", "history.basic",
                        "dictation.multilingual", "dictation.scratch_that"):
            assert ent.allowed(feature, edition) is True
            assert ent.allowed(feature, edition, frozenset()) is True
