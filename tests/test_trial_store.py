"""Trial persistence + rollback bookkeeping (trial_store.py).

Fake clocks, tmp_path files, and dict-backed registry fakes — no real time,
no real registry (one opt-in Windows round-trip test uses a per-process
value name, mirroring tests/test_autostart.py).
"""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

import trial
import trial_store

T0 = datetime(2026, 8, 1, 20, 0, 0, tzinfo=timezone.utc)


class FakeMarker:
    """Dict-backed stand-in for the HKCU trial marker."""

    def __init__(self):
        self.value = None

    def read(self):
        return self.value

    def write(self, envelope):
        self.value = envelope


def service(tmp_path, marker=None, protection=None):
    return trial_store.TrialService(
        path=str(tmp_path / "trial.json"),
        marker=marker if marker is not None else FakeMarker(),
        protection=protection or trial_store.NullProtection(),
    )


# -- explicit start ----------------------------------------------------------

def test_no_trial_until_explicitly_started(tmp_path):
    svc = service(tmp_path)
    assert svc.status(now=T0).state == trial.NOT_STARTED
    # merely asking must not create anything
    assert not os.path.exists(str(tmp_path / "trial.json"))


def test_start_creates_a_fourteen_day_trial(tmp_path):
    svc = service(tmp_path)
    status = svc.start(now=T0)
    assert status.state == trial.ACTIVE
    assert status.days_remaining == 14
    assert status.expires_at - status.started_at == timedelta(days=14)


def test_start_is_not_a_restart(tmp_path):
    svc = service(tmp_path)
    first = svc.start(now=T0)
    again = svc.start(now=T0 + timedelta(days=20))
    assert again.state == trial.EXPIRED
    assert again.started_at == first.started_at


def test_status_after_start_counts_down(tmp_path):
    svc = service(tmp_path)
    svc.start(now=T0)
    assert svc.days_remaining(now=T0 + timedelta(days=1)) == 13
    assert svc.status(now=T0 + timedelta(days=3)).days_remaining == 11
    assert svc.is_active(now=T0 + timedelta(days=13))
    assert not svc.is_active(now=T0 + timedelta(days=15))


# -- persistence across instances (upgrade survival) -------------------------

def test_new_service_instance_sees_the_same_trial(tmp_path):
    marker = FakeMarker()
    service(tmp_path, marker=marker).start(now=T0)
    reopened = service(tmp_path, marker=marker)
    status = reopened.status(now=T0 + timedelta(days=2))
    assert status.state == trial.ACTIVE
    assert status.started_at == T0


def test_deleting_the_file_does_not_grant_a_new_trial(tmp_path):
    marker = FakeMarker()
    svc = service(tmp_path, marker=marker)
    svc.start(now=T0)
    os.remove(str(tmp_path / "trial.json"))
    fresh = service(tmp_path, marker=marker)
    # the registry marker restores the original record
    assert fresh.start(now=T0 + timedelta(days=30)).state == trial.EXPIRED
    # and the file is healed back
    assert os.path.exists(str(tmp_path / "trial.json"))


def test_losing_the_marker_does_not_grant_a_new_trial(tmp_path):
    svc = service(tmp_path, marker=FakeMarker())
    svc.start(now=T0)
    fresh = service(tmp_path, marker=FakeMarker())  # empty marker
    assert fresh.start(now=T0 + timedelta(days=30)).state == trial.EXPIRED


def test_earliest_record_wins_when_sources_disagree(tmp_path):
    marker = FakeMarker()
    a = service(tmp_path, marker=marker)
    a.start(now=T0)
    older = marker.value
    # simulate a later, second record in the file only
    b = service(tmp_path, marker=FakeMarker())
    os.remove(str(tmp_path / "trial.json"))
    b.start(now=T0 + timedelta(days=40))
    marker.value = older
    merged = service(tmp_path, marker=marker)
    assert merged.status(now=T0 + timedelta(days=41)).started_at == T0


# -- corruption and tampering ------------------------------------------------

def test_corrupt_file_with_marker_backup_recovers(tmp_path):
    marker = FakeMarker()
    svc = service(tmp_path, marker=marker)
    svc.start(now=T0)
    (tmp_path / "trial.json").write_text("{not json", encoding="utf-8")
    status = service(tmp_path, marker=marker).status(now=T0 + timedelta(days=1))
    assert status.state == trial.ACTIVE


def test_corrupt_everything_is_invalid_not_a_crash_and_not_a_reset(tmp_path):
    marker = FakeMarker()
    svc = service(tmp_path, marker=marker)
    svc.start(now=T0)
    (tmp_path / "trial.json").write_text("{not json", encoding="utf-8")
    marker.value = "garbage"
    broken = service(tmp_path, marker=marker)
    assert broken.status(now=T0).state == trial.INVALID
    # corruption never silently grants a fresh trial
    assert broken.start(now=T0).state == trial.INVALID


def test_tampered_expiry_is_invalid(tmp_path):
    marker = FakeMarker()
    svc = service(tmp_path, marker=marker)
    svc.start(now=T0)
    envelope = json.loads((tmp_path / "trial.json").read_text(encoding="utf-8"))
    envelope["record"]["expires_at_utc"] = trial.format_utc(
        T0 + timedelta(days=365))
    (tmp_path / "trial.json").write_text(json.dumps(envelope),
                                         encoding="utf-8")
    marker.value = None
    assert service(tmp_path, marker=marker).status(
        now=T0 + timedelta(days=20)).state == trial.INVALID


def test_missing_everything_is_simply_not_started(tmp_path):
    svc = service(tmp_path)
    assert svc.status(now=T0).state == trial.NOT_STARTED


# -- clock rollback ----------------------------------------------------------

def test_rollback_detected_and_recoverable(tmp_path):
    svc = service(tmp_path)
    svc.start(now=T0)
    svc.status(now=T0 + timedelta(days=5))       # advances last_seen
    rolled = svc.status(now=T0 + timedelta(days=2))
    assert rolled.state == trial.CLOCK_ROLLBACK_DETECTED
    # a retry with the clock fixed recovers without losing the record
    healed = svc.status(now=T0 + timedelta(days=5, minutes=1))
    assert healed.state == trial.ACTIVE
    assert healed.started_at == T0


def test_rollback_within_tolerance_is_fine(tmp_path):
    svc = service(tmp_path)
    svc.start(now=T0)
    svc.status(now=T0 + timedelta(days=5))
    ok = svc.status(now=T0 + timedelta(days=5) - timedelta(minutes=4))
    assert ok.state == trial.ACTIVE


def test_last_seen_never_regresses(tmp_path):
    svc = service(tmp_path)
    svc.start(now=T0)
    svc.status(now=T0 + timedelta(days=6))
    svc.status(now=T0 + timedelta(days=2))       # rollback read
    envelope = json.loads((tmp_path / "trial.json").read_text(encoding="utf-8"))
    last_seen = trial.parse_utc(envelope["record"]["last_seen_at_utc"])
    assert last_seen == T0 + timedelta(days=6)


# -- expired notice bookkeeping ----------------------------------------------

def test_expired_notice_seen_persists(tmp_path):
    marker = FakeMarker()
    svc = service(tmp_path, marker=marker)
    svc.start(now=T0)
    late = T0 + timedelta(days=15)
    assert svc.status(now=late).expired_notice_seen is False
    svc.mark_expired_notice_seen()
    assert service(tmp_path, marker=marker).status(
        now=late).expired_notice_seen is True


# -- hygiene ------------------------------------------------------------------

def test_writes_are_atomic_and_leave_no_tmp_files(tmp_path):
    svc = service(tmp_path)
    svc.start(now=T0)
    svc.mark_expired_notice_seen()
    leftovers = [p for p in os.listdir(tmp_path) if p != "trial.json"]
    assert leftovers == []


def test_stored_state_contains_no_personal_data_fields(tmp_path):
    svc = service(tmp_path)
    svc.start(now=T0)
    raw = (tmp_path / "trial.json").read_text(encoding="utf-8").lower()
    for banned in ("transcript", "clipboard", "audio", "history",
                   "vocabulary", "window_title", "hwid", "hardware"):
        assert banned not in raw


def test_store_module_has_no_eager_platform_or_network_imports():
    import ast, inspect
    tree = ast.parse(inspect.getsource(trial_store))
    banned = {"socket", "urllib", "requests", "http", "winreg", "ctypes",
              "history", "audio", "transcriber", "recorder", "clipboard"}
    for node in tree.body:  # top level only — lazy in-function imports are fine
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] not in banned
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned


def test_null_protection_round_trip():
    p = trial_store.NullProtection()
    assert p.unprotect(p.protect(b"abc")) == b"abc"


@pytest.mark.skipif(os.name != "nt", reason="DPAPI is Windows-only")
def test_dpapi_protection_round_trip():
    p = trial_store.DpapiProtection()
    secret = b"trial-key-material"
    blob = p.protect(secret)
    assert blob != secret
    assert p.unprotect(blob) == secret


@pytest.mark.skipif(os.name != "nt", reason="registry is Windows-only")
def test_windows_marker_round_trip_real_registry():
    marker = trial_store.WindowsRegistryMarker(
        value_name=f"ROARTrialTest{os.getpid()}")
    try:
        assert marker.read() is None
        marker.write({"schema_version": 1, "probe": "x"})
        assert marker.read() == {"schema_version": 1, "probe": "x"}
    finally:
        marker.delete()
