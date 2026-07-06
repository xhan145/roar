import license as license_mod


def test_missing_or_corrupt_license_is_core():
    assert license_mod.load_license(None).edition == "Core"
    assert license_mod.load_license("not json").edition == "Core"
    assert license_mod.entitlements_for("mystery")["privacy_controls"] is True


def test_privacy_entitlements_are_never_paid_only():
    for edition in ("Core", "Pro", "Developer", "Supporter"):
        ent = license_mod.entitlements_for(edition)
        assert ent["dictation"] is True
        assert ent["privacy_controls"] is True
        assert ent["delete_history_audio"] is True


def test_supporter_includes_developer_features():
    supporter = license_mod.entitlements_for("Supporter")
    developer = license_mod.entitlements_for("Developer")
    for key, enabled in developer.items():
        if enabled:
            assert supporter[key] is True
