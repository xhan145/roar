"""Applied gates: paid features resolve DOWN when unentitled, Core promises hold
absolutely, paid config is preserved, and the upgrade prompt only ever appears
for genuinely gated features."""
import entitlements as ent
import legacy_grant as lg
import upgrade_prompts as up
from entitlements import CORE, PRO, DEVELOPER, SUPPORTER


# -- the reusable upgrade component --------------------------------------

def test_prompt_is_none_for_free_features():
    """A free feature can never produce an upgrade prompt — that's what stops a
    caller nagging about something that isn't gated."""
    for free in ("dictation.push_to_talk", "privacy.controls", "history.delete",
                 "audio.delete", "vocabulary.basic", "diagnostics.safe"):
        assert up.prompt_for(free) is None


def test_prompt_is_none_for_unknown_feature():
    assert up.prompt_for("totally.made.up") is None


def test_prompt_for_pro_feature():
    p = up.prompt_for("snippets.packs")
    assert p["required_edition"] == PRO
    assert p["feature_name"] == "ROAR Snippets"
    assert "ROAR Pro" in p["headline"]
    assert p["price_usd"] == 29                     # repo pricing
    assert p["purchase_url"]
    assert "Not Now" in p["buttons"]


def test_prompt_for_developer_feature():
    p = up.prompt_for("code.mode")
    assert p["required_edition"] == DEVELOPER
    assert p["feature_name"] == "Code Mode"
    assert p["price_usd"] == 49
    assert "ROAR Developer" in p["headline"]


def test_prompt_terms_are_honest_and_not_coercive():
    for feature in ("snippets.packs", "code.mode"):
        p = up.prompt_for(feature)
        terms = p["terms"].lower()
        assert "no subscription" in terms and "no account" in terms
        blob = (p["headline"] + p["description"] + p["terms"]).lower()
        for banned in ("trial", "expired", "limited time", "hurry", "only today",
                       "lifetime"):
            assert banned not in blob


def test_every_gated_feature_has_human_copy():
    """No gated feature may show a bare feature ID to a user."""
    paid = ent.KNOWN_FEATURES - ent.ALWAYS_FREE
    missing = paid - set(up.FEATURE_COPY)
    assert not missing, f"gated features with no human copy: {missing}"


def test_feature_copy_has_no_stale_ids():
    unknown = set(up.FEATURE_COPY) - ent.KNOWN_FEATURES
    assert not unknown, f"copy for unregistered features: {unknown}"


# -- what Core actually loses (and must not) ------------------------------

def test_core_keeps_every_promise_with_no_license_and_no_grant():
    for feature in ("dictation.push_to_talk", "dictation.hands_free",
                    "dictation.streaming", "dictation.multilingual",
                    "dictation.scratch_that", "commands.basic",
                    "history.basic", "history.delete", "audio.delete",
                    "privacy.controls", "vocabulary.basic", "diagnostics.safe"):
        assert ent.allowed(feature, CORE, frozenset()) is True


def test_ungranted_core_is_gated_on_paid_features():
    """A NEW install (no grant) genuinely doesn't get the paid features."""
    for feature in ("snippets.packs", "formatting.smart", "code.mode",
                    "cleanup.advanced", "profiles.apps"):
        assert ent.allowed(feature, CORE, frozenset()) is False
        assert ent.requires_upgrade(feature, CORE, frozenset()) is True


def test_grandfathered_core_keeps_what_it_had():
    """An EXISTING user loses nothing that shipped free."""
    g = lg.GRANTED_FEATURES
    for feature in ("snippets.packs", "formatting.smart", "code.mode",
                    "cleanup.advanced", "profiles.apps", "history.filters",
                    "settings.import_export", "vocabulary.suggestions",
                    "milestones.advanced"):
        assert ent.allowed(feature, CORE, g) is True
        assert ent.requires_upgrade(feature, CORE, g) is False


def test_grandfathered_core_still_cannot_reach_never_shipped_features():
    g = lg.GRANTED_FEATURES
    for planned in ("vocabulary.project", "snippets.developer_packs",
                    "files.tagging"):
        assert ent.allowed(planned, CORE, g) is False


# -- edition hierarchy through the gate --------------------------------------

def test_pro_gets_pro_not_developer():
    assert ent.allowed("snippets.packs", PRO) is True
    assert ent.allowed("code.mode", PRO) is False


def test_developer_includes_pro():
    assert ent.allowed("snippets.packs", DEVELOPER) is True
    assert ent.allowed("code.mode", DEVELOPER) is True


def test_supporter_includes_developer():
    for feature in ent.KNOWN_FEATURES:
        assert ent.allowed(feature, SUPPORTER) is True


def test_supporter_has_no_exclusive_feature():
    """Supporter is a patron tier — it must never be technically superior."""
    assert (ent.features_for_edition(SUPPORTER)
            == ent.features_for_edition(DEVELOPER))
