"""Pure trial-state primitives (trial.py) — fake clocks only, no real time.

The 14-day Full-Feature Trial is calculated entirely from timezone-aware UTC
timestamps carried in a small local record. These tests pin the exact
boundary behaviour the product promises: explicit start, exactly 14 days,
whole-day countdown, conservative clock-rollback detection, and a record that
never contains dictation data.
"""

from datetime import datetime, timedelta, timezone

import pytest

import trial

T0 = datetime(2026, 8, 1, 20, 0, 0, tzinfo=timezone.utc)
KEY = b"test-integrity-key"


def _record(now=T0):
    return trial.new_record(now=now)


# -- record creation ---------------------------------------------------------

def test_trial_not_started_when_no_record():
    status = trial.status_of(None, now=T0)
    assert status.state == trial.NOT_STARTED
    assert status.started_at is None
    assert status.expires_at is None
    assert status.seconds_remaining == 0


def test_new_record_lasts_exactly_fourteen_days():
    rec = _record()
    started = trial.parse_utc(rec["started_at_utc"])
    expires = trial.parse_utc(rec["expires_at_utc"])
    assert expires - started == timedelta(days=14)
    assert trial.TRIAL_DURATION == timedelta(days=14)


def test_new_record_shape_and_privacy():
    rec = _record()
    assert rec["schema_version"] == trial.SCHEMA_VERSION == 1
    # exactly these keys — no transcript, audio, history, clipboard,
    # vocabulary, or window-title data can ever hide in the record
    assert set(rec) == {
        "schema_version", "trial_id", "started_at_utc", "expires_at_utc",
        "last_seen_at_utc", "expired_notice_seen",
    }
    assert rec["expired_notice_seen"] is False
    assert len(rec["trial_id"]) >= 32  # uuid4 hex or canonical form


def test_new_record_timestamps_are_utc_aware():
    rec = _record()
    for field in ("started_at_utc", "expires_at_utc", "last_seen_at_utc"):
        parsed = trial.parse_utc(rec[field])
        assert parsed is not None and parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(0)


# -- status boundaries -------------------------------------------------------

def test_active_one_second_before_expiry():
    rec = _record()
    almost = T0 + timedelta(days=14) - timedelta(seconds=1)
    status = trial.status_of(rec, now=almost)
    assert status.state == trial.ACTIVE
    assert status.seconds_remaining == 1
    assert status.days_remaining == 0


def test_expired_at_exact_expiry_timestamp():
    rec = _record()
    status = trial.status_of(rec, now=T0 + timedelta(days=14))
    assert status.state == trial.EXPIRED
    assert status.seconds_remaining == 0


def test_expired_one_second_after_expiry():
    rec = _record()
    status = trial.status_of(rec, now=T0 + timedelta(days=14, seconds=1))
    assert status.state == trial.EXPIRED


def test_whole_days_remaining_counts_down_by_floor():
    rec = _record()
    assert trial.status_of(rec, now=T0).days_remaining == 14
    assert trial.status_of(rec, now=T0 + timedelta(seconds=1)).days_remaining == 13
    assert trial.status_of(rec, now=T0 + timedelta(days=2)).days_remaining == 12
    under_day = trial.status_of(rec, now=T0 + timedelta(days=13, hours=1))
    assert under_day.state == trial.ACTIVE
    assert under_day.days_remaining == 0


def test_remaining_label_copy():
    rec = _record()
    assert trial.remaining_label(trial.status_of(rec, now=T0)) == "14 days remaining"
    assert trial.remaining_label(
        trial.status_of(rec, now=T0 + timedelta(days=2))) == "12 days remaining"
    assert trial.remaining_label(
        trial.status_of(rec, now=T0 + timedelta(days=13, hours=2))
    ) == "Less than one day remaining"
    assert trial.remaining_label(
        trial.status_of(rec, now=T0 + timedelta(days=15))) == ""


# -- clock rollback ----------------------------------------------------------

def test_rollback_inside_tolerance_is_accepted():
    rec = _record()
    rec["last_seen_at_utc"] = trial.format_utc(T0 + timedelta(days=3))
    now = T0 + timedelta(days=3) - timedelta(minutes=4)
    assert trial.status_of(rec, now=now).state == trial.ACTIVE


def test_rollback_outside_tolerance_is_detected():
    rec = _record()
    rec["last_seen_at_utc"] = trial.format_utc(T0 + timedelta(days=3))
    now = T0 + timedelta(days=3) - timedelta(minutes=6)
    status = trial.status_of(rec, now=now)
    assert status.state == trial.CLOCK_ROLLBACK_DETECTED
    # detection never destroys the underlying dates
    assert status.started_at == T0
    assert status.expires_at == T0 + timedelta(days=14)


def test_rollback_does_not_mask_a_paid_license():
    status = trial.TrialStatus(
        state=trial.CLOCK_ROLLBACK_DETECTED, started_at=T0,
        expires_at=T0 + timedelta(days=14), seconds_remaining=0,
        days_remaining=0, expired_notice_seen=False)
    assert trial.resolve_effective_edition(
        license_edition="pro", license_valid=True, trial_status=status) == "pro"


# -- record validation -------------------------------------------------------

@pytest.mark.parametrize("bad", [
    None, 42, "trial", [], {"schema_version": 1},
])
def test_validate_record_rejects_malformed(bad):
    assert trial.validate_record(bad) is None


def test_validate_record_rejects_unsupported_schema():
    rec = _record()
    rec["schema_version"] = 99
    assert trial.validate_record(rec) is None


def test_validate_record_rejects_garbage_timestamps():
    rec = _record()
    rec["expires_at_utc"] = "not-a-date"
    assert trial.validate_record(rec) is None


def test_validate_record_rejects_expiry_before_start():
    rec = _record()
    rec["expires_at_utc"] = trial.format_utc(T0 - timedelta(days=1))
    assert trial.validate_record(rec) is None


def test_validate_record_accepts_a_fresh_record():
    rec = _record()
    assert trial.validate_record(rec) == rec


def test_invalid_record_status_is_invalid_not_a_crash():
    status = trial.status_of({"schema_version": 1}, now=T0)
    assert status.state == trial.INVALID
    assert status.seconds_remaining == 0


# -- integrity signature -----------------------------------------------------

def test_sign_and_verify_round_trip():
    rec = trial.sign_record(_record(), KEY)
    assert trial.verify_record(rec, KEY)


def test_tampered_record_fails_verification():
    rec = trial.sign_record(_record(), KEY)
    rec["expires_at_utc"] = trial.format_utc(T0 + timedelta(days=365))
    assert not trial.verify_record(rec, KEY)


def test_wrong_key_fails_verification():
    rec = trial.sign_record(_record(), KEY)
    assert not trial.verify_record(rec, b"other-key")


def test_mutable_bookkeeping_does_not_break_signature():
    # last_seen and the notice flag change during normal operation and must
    # not require re-signing
    rec = trial.sign_record(_record(), KEY)
    rec["last_seen_at_utc"] = trial.format_utc(T0 + timedelta(days=5))
    rec["expired_notice_seen"] = True
    assert trial.verify_record(rec, KEY)


# -- effective edition resolution --------------------------------------------

def _active():
    return trial.status_of(_record(), now=T0 + timedelta(days=1))


def _expired():
    return trial.status_of(_record(), now=T0 + timedelta(days=15))


def test_active_trial_resolves_to_trial_edition():
    assert trial.resolve_effective_edition(
        license_edition="core", license_valid=False,
        trial_status=_active()) == "trial"


def test_expired_trial_resolves_to_core():
    assert trial.resolve_effective_edition(
        license_edition="core", license_valid=False,
        trial_status=_expired()) == "core"


def test_not_started_resolves_to_core():
    status = trial.status_of(None, now=T0)
    assert trial.resolve_effective_edition(
        license_edition="core", license_valid=False,
        trial_status=status) == "core"


@pytest.mark.parametrize("edition", ["pro", "developer", "supporter"])
def test_valid_paid_license_overrides_active_trial(edition):
    assert trial.resolve_effective_edition(
        license_edition=edition, license_valid=True,
        trial_status=_active()) == edition


def test_invalid_license_does_not_override_trial():
    assert trial.resolve_effective_edition(
        license_edition="pro", license_valid=False,
        trial_status=_active()) == "trial"


def test_core_license_never_wins_over_active_trial():
    # a "valid core" state (no licence file) must not shadow the trial
    assert trial.resolve_effective_edition(
        license_edition="core", license_valid=True,
        trial_status=_active()) == "trial"


def test_licensed_state_helper():
    status = trial.status_of(_record(), now=T0 + timedelta(days=1))
    shown = trial.display_state(status, license_valid=True)
    assert shown == trial.LICENSED
    assert trial.display_state(status, license_valid=False) == trial.ACTIVE


# -- purity ------------------------------------------------------------------

def test_trial_module_is_pure():
    import ast, inspect
    tree = ast.parse(inspect.getsource(trial))
    banned = {"socket", "urllib", "requests", "http", "history", "audio",
              "transcriber", "recorder", "clipboard", "winreg", "ctypes"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] not in banned
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned
