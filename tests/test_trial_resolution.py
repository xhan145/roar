"""Trial edition + effective-edition resolution (entitlements/access/licence).

The `trial` edition is runtime-only: full Developer feature set while active,
never sellable, always outranked by any valid paid licence, and gone at
expiry (core). These tests pin the whole priority chain through the real
access facade with injected licence and trial state.
"""

import base64
from datetime import datetime, timedelta, timezone

import pytest

import access
import entitlements as ent
import commercial_config as cc
import license as lic
import trial
import trial_store

T0 = datetime(2026, 8, 1, 20, 0, 0, tzinfo=timezone.utc)


# -- entitlement policy for the trial edition --------------------------------

def test_trial_edition_gets_the_full_developer_set():
    assert ent.features_for_edition(ent.TRIAL) == \
        ent.features_for_edition(ent.DEVELOPER)


@pytest.mark.parametrize("feature", [
    "formatting.smart", "snippets.packs", "code.mode", "profiles.apps",
    "vocabulary.project", "snippets.developer_packs", "files.tagging",
    "automations.rules", "routing.per_app", "capture.system_audio",
])
def test_trial_can_use_pro_and_developer_features(feature):
    assert ent.can_use(feature, edition=ent.TRIAL) is True


def test_trial_edition_normalizes_and_is_runtime_only():
    assert ent.normalize_edition(" TRIAL ") == ent.TRIAL
    assert ent.TRIAL in ent.RUNTIME_EDITIONS
    # never sellable: not in the canonical editions/pricing/paid sets
    assert ent.TRIAL not in ent.EDITIONS
    assert ent.TRIAL not in cc.PRICING
    assert ent.TRIAL not in cc.PAID_EDITIONS


def test_always_free_still_free_for_trial_and_after():
    for feature in ent.ALWAYS_FREE:
        assert ent.can_use(feature, edition=ent.TRIAL)
        assert ent.can_use(feature, edition=ent.CORE)


def test_minimum_edition_never_names_the_trial():
    for feature in ent.KNOWN_FEATURES:
        assert ent.minimum_edition_for(feature) != ent.TRIAL


# -- a signed "trial" licence must never validate ----------------------------

def test_trial_licence_payload_is_unsupported():
    payload = {"schema_version": 1, "license_id": "ROAR-TRIAL-XXXX2222",
               "edition": "trial", "issued_at": "2026-08-01",
               "valid_for_major": 1, "signature": base64.b64encode(
                   b"irrelevant").decode()}

    class YesVerifier(lic.SignatureVerifier):
        def verify(self, message, signature):
            return True

    result = lic.validate_license(payload, verifier=YesVerifier(),
                                  current_major=1, is_production=True)
    assert not result.valid
    assert result.reason == "unsupported_edition"
    assert result.edition == ent.CORE


# -- effective edition through the access facade -----------------------------

class FakeMarker:
    def __init__(self):
        self.value = None

    def read(self):
        return self.value

    def write(self, envelope):
        self.value = envelope


@pytest.fixture
def facade(tmp_path, monkeypatch):
    """access.* with an isolated trial service and a controllable licence."""
    svc = trial_store.TrialService(
        path=str(tmp_path / "trial.json"), marker=FakeMarker(),
        protection=trial_store.NullProtection())
    state = {"edition": "core", "now": T0}
    monkeypatch.setattr(access.license_service, "get_active_edition",
                        lambda path=None: state["edition"])
    monkeypatch.setattr(access, "_trial_service", svc)
    monkeypatch.setattr(access, "grants", lambda: frozenset())
    real_status = svc.status
    monkeypatch.setattr(svc, "status",
                        lambda now=None: real_status(now=state["now"]))
    access._trial_cache = None
    yield state, svc
    access._trial_cache = None
    access._trial_service = None


def _fresh(state):
    access._trial_cache = None
    return access.effective_edition()


def test_no_licence_no_trial_is_core(facade):
    state, _svc = facade
    assert _fresh(state) == "core"


def test_active_trial_resolves_to_trial(facade):
    state, svc = facade
    svc.start(now=T0)
    assert _fresh(state) == "trial"
    assert access.can("code.mode") is True
    assert access.can("snippets.packs") is True
    assert access.requires_upgrade("code.mode") is False


def test_expired_trial_resolves_to_core(facade):
    state, svc = facade
    svc.start(now=T0)
    state["now"] = T0 + timedelta(days=15)
    assert _fresh(state) == "core"
    access._trial_cache = None
    assert access.can("code.mode") is False
    access._trial_cache = None
    assert access.requires_upgrade("code.mode") is True


@pytest.mark.parametrize("edition", ["pro", "developer", "supporter"])
def test_valid_licence_overrides_active_trial(facade, edition):
    state, svc = facade
    svc.start(now=T0)
    state["edition"] = edition
    assert _fresh(state) == edition


def test_licence_works_even_after_trial_expired(facade):
    state, svc = facade
    svc.start(now=T0)
    state["now"] = T0 + timedelta(days=40)
    state["edition"] = "pro"
    assert _fresh(state) == "pro"
    access._trial_cache = None
    assert access.can("snippets.packs") is True


def test_rollback_locks_trial_features_but_not_core(facade):
    state, svc = facade
    svc.start(now=T0)
    real = access._trial_service.status
    state["now"] = T0 + timedelta(days=5)
    _fresh(state)                       # advance last_seen to day 5
    state["now"] = T0 + timedelta(days=1)
    assert _fresh(state) == "core"      # rollback: paid features lock
    access._trial_cache = None
    assert access.can("dictation.push_to_talk") is True
    access._trial_cache = None
    assert access.can("code.mode") is False


def test_trial_fault_degrades_to_core_not_a_crash(facade, monkeypatch):
    state, svc = facade

    def boom(now=None):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(svc, "status", boom)
    assert _fresh(state) == "core"
    access._trial_cache = None
    assert access.can("dictation.push_to_talk") is True


def test_refresh_clears_the_trial_cache(facade):
    state, svc = facade
    assert _fresh(state) == "core"
    svc.start(now=T0)
    access.refresh()
    assert access.effective_edition() == "trial"
