"""Regressions for the defects the adversarial review confirmed.

Each test names the failure it prevents. All use fake clocks and injected
stores — nothing waits on real time.
"""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

import access
import app as app_mod
import license_service
import trial
import trial_store

T0 = datetime(2026, 8, 1, 20, 0, 0, tzinfo=timezone.utc)


class FakeMarker:
    def __init__(self):
        self.value = None

    def read(self):
        return self.value

    def write(self, envelope):
        self.value = envelope


def _service(tmp_path, marker=None):
    return trial_store.TrialService(
        path=str(tmp_path / "trial.json"),
        marker=marker if marker is not None else FakeMarker(),
        protection=trial_store.NullProtection())


def _envelope(tmp_path):
    return json.loads((tmp_path / "trial.json").read_text(encoding="utf-8"))


def _write_envelope(tmp_path, envelope):
    (tmp_path / "trial.json").write_text(json.dumps(envelope),
                                         encoding="utf-8")


# -- 1. a licence must take effect without restarting ROAR -------------------

def test_licence_written_by_another_process_is_honoured_immediately(
        tmp_path, monkeypatch):
    """Settings runs in its own process. A licence imported there must unlock
    features in the tray at once — the blocker was 'paid licence fails
    because the trial expired' (stale in-process licence cache)."""
    lic_path = tmp_path / "license.json"
    monkeypatch.setattr(access.paths, "license_path", lambda: str(lic_path))
    state = {"edition": "core"}
    monkeypatch.setattr(license_service, "get_active_edition",
                        lambda path=None: state["edition"])
    seen = []
    monkeypatch.setattr(license_service, "refresh",
                        lambda: seen.append("refresh"))
    monkeypatch.setattr(access, "_license_stamp", None)

    assert access.edition() == "core"
    seen.clear()
    # "the other process writes license.json"
    lic_path.write_text('{"edition": "pro"}', encoding="utf-8")
    state["edition"] = "pro"
    assert access.edition() == "pro"
    assert seen == ["refresh"], "the file change must invalidate the cache"
    # steady state: no churn while the file is unchanged
    seen.clear()
    access.edition()
    access.edition()
    assert seen == []
    # and removal is noticed too
    os.remove(str(lic_path))
    state["edition"] = "core"
    assert access.edition() == "core"
    assert seen == ["refresh"]


# -- 2. the anti-rollback mark is signed --------------------------------------

def test_hand_edited_last_seen_invalidates_the_record(tmp_path):
    """Editing last_seen in a text editor used to survive verification, so a
    rolled-back clock could re-grant the trial forever."""
    marker = FakeMarker()
    svc = _service(tmp_path, marker)
    svc.start(now=T0)
    svc.status(now=T0 + timedelta(days=5))   # mark now sits at day 5
    envelope = _envelope(tmp_path)
    # rewind the mark by hand — the move that used to buy an endless trial
    envelope["record"]["last_seen_at_utc"] = trial.format_utc(T0)
    _write_envelope(tmp_path, envelope)
    marker.value = None                      # only the tampered copy remains
    assert _service(tmp_path, marker).status(
        now=T0 + timedelta(days=3)).state == trial.INVALID


def test_hand_edited_notice_flag_invalidates_the_record(tmp_path):
    marker = FakeMarker()
    svc = _service(tmp_path, marker)
    svc.start(now=T0)
    envelope = _envelope(tmp_path)
    envelope["record"]["expired_notice_seen"] = True
    _write_envelope(tmp_path, envelope)
    marker.value = None
    assert _service(tmp_path, marker).status(
        now=T0 + timedelta(days=1)).state == trial.INVALID


def test_legitimate_updates_still_verify(tmp_path):
    svc = _service(tmp_path)
    svc.start(now=T0)
    svc.status(now=T0 + timedelta(days=2))   # advances the mark, re-signs
    svc.mark_expired_notice_seen()
    assert svc.status(now=T0 + timedelta(days=3)).state == trial.ACTIVE


# -- 3. a wild forward clock reading must not wedge the trial ----------------

def test_far_future_clock_reading_does_not_brick_the_trial(tmp_path):
    """A bogus reading years ahead used to poison last_seen, leaving the
    trial permanently in clock_rollback_detected once the clock was fixed."""
    svc = _service(tmp_path)
    svc.start(now=T0)
    assert svc.status(now=T0 + timedelta(days=3650)).state == trial.EXPIRED
    healed = svc.status(now=T0 + timedelta(days=2))
    assert healed.state == trial.ACTIVE
    assert healed.days_remaining == 12


def test_mark_is_clamped_to_expiry(tmp_path):
    svc = _service(tmp_path)
    svc.start(now=T0)
    svc.status(now=T0 + timedelta(days=13, hours=23))
    mark = trial.parse_utc(_envelope(tmp_path)["record"]["last_seen_at_utc"])
    assert mark <= T0 + timedelta(days=14)


def test_rollback_after_expiry_reads_as_expired_not_rollback(tmp_path):
    svc = _service(tmp_path)
    svc.start(now=T0)
    svc.status(now=T0 + timedelta(days=13))
    assert svc.status(now=T0 + timedelta(days=20)).state == trial.EXPIRED
    # a small backwards nudge past expiry is still simply "over"
    assert svc.status(now=T0 + timedelta(days=15)).state == trial.EXPIRED


def test_real_rollback_inside_the_trial_is_still_detected(tmp_path):
    svc = _service(tmp_path)
    svc.start(now=T0)
    svc.status(now=T0 + timedelta(days=5))
    assert svc.status(now=T0 + timedelta(days=1)).state == \
        trial.CLOCK_ROLLBACK_DETECTED


# -- 4. status reads must not hammer the disk or track dictation -------------

def test_status_reads_do_not_rewrite_the_store_every_time(tmp_path):
    svc = _service(tmp_path)
    svc.start(now=T0)
    before = os.stat(str(tmp_path / "trial.json")).st_mtime_ns
    base = T0 + timedelta(minutes=1)
    for i in range(25):                       # a busy dictation session
        svc.status(now=base + timedelta(seconds=i))
    assert os.stat(str(tmp_path / "trial.json")).st_mtime_ns == before


def test_the_mark_still_advances_over_meaningful_time(tmp_path):
    svc = _service(tmp_path)
    svc.start(now=T0)
    svc.status(now=T0 + timedelta(hours=2))
    mark = trial.parse_utc(_envelope(tmp_path)["record"]["last_seen_at_utc"])
    assert mark == T0 + timedelta(hours=2)


def test_expired_trial_stops_recording_when_you_last_dictated(tmp_path):
    """After expiry the mark protects nothing, so ROAR stops refreshing a
    second-resolution 'last used' timestamp in a file privacy resets never
    clear."""
    svc = _service(tmp_path)
    svc.start(now=T0)
    svc.status(now=T0 + timedelta(days=20))
    before = os.stat(str(tmp_path / "trial.json")).st_mtime_ns
    svc.status(now=T0 + timedelta(days=40))
    svc.status(now=T0 + timedelta(days=90))
    assert os.stat(str(tmp_path / "trial.json")).st_mtime_ns == before


# -- 5. both stores contribute the mutable fields ----------------------------

def test_a_newer_mark_in_the_registry_is_not_discarded(tmp_path):
    """The file used to win ties outright, so a mark or a seen-notice held
    only by the registry copy was silently dropped."""
    marker = FakeMarker()
    svc = _service(tmp_path, marker)
    svc.start(now=T0)
    svc.status(now=T0 + timedelta(days=6))     # both stores advance
    stale = _envelope(tmp_path)                 # keep an older file copy
    stale["record"] = json.loads(json.dumps(stale["record"]))
    svc.status(now=T0 + timedelta(days=6, hours=2))
    _write_envelope(tmp_path, stale)            # file rewound, registry newer
    fresh = _service(tmp_path, marker)
    assert fresh.status(now=T0 + timedelta(days=6)).state == \
        trial.CLOCK_ROLLBACK_DETECTED


def test_a_seen_notice_in_either_store_counts(tmp_path):
    marker = FakeMarker()
    svc = _service(tmp_path, marker)
    svc.start(now=T0)
    svc.status(now=T0 + timedelta(days=20))
    before_notice = _envelope(tmp_path)
    svc.mark_expired_notice_seen()
    _write_envelope(tmp_path, before_notice)    # file forgot; registry knows
    assert _service(tmp_path, marker).status(
        now=T0 + timedelta(days=20)).expired_notice_seen is True


# -- 6. an unverifiable record never grants a second trial -------------------

def test_lost_protection_key_does_not_grant_a_fresh_trial(tmp_path):
    """DPAPI can stop decrypting (OS reinstall). The record is then present
    but unverifiable: no trial, and crucially no NEW trial either."""
    marker = FakeMarker()
    svc = _service(tmp_path, marker)
    svc.start(now=T0)
    envelope = _envelope(tmp_path)
    envelope["key_b64"] = "AAAA"                # key no longer matches
    _write_envelope(tmp_path, envelope)
    marker.value = envelope
    broken = _service(tmp_path, marker)
    assert broken.status(now=T0 + timedelta(days=1)).state == trial.INVALID
    assert broken.start(now=T0 + timedelta(days=1)).state == trial.INVALID
    assert broken.mark_expired_notice_seen() is False


def test_a_licence_still_overrides_an_unusable_trial_record(tmp_path,
                                                            monkeypatch):
    marker = FakeMarker()
    svc = _service(tmp_path, marker)
    svc.start(now=T0)
    envelope = _envelope(tmp_path)
    envelope["key_b64"] = "AAAA"
    _write_envelope(tmp_path, envelope)
    marker.value = envelope
    monkeypatch.setattr(access, "_trial_service", _service(tmp_path, marker))
    monkeypatch.setattr(access, "grants", lambda: frozenset())
    monkeypatch.setattr(license_service, "get_active_edition",
                        lambda path=None: "developer")
    monkeypatch.setattr(access, "_license_stamp", None)
    access._trial_cache = None
    assert access.effective_edition() == "developer"
    access._trial_cache = None
    access._trial_service = None


# -- 7. the ended notice is shown at most once per run, even if writes fail --

def test_notice_latch_survives_a_failed_write(tmp_path, monkeypatch):
    """If the acknowledgement cannot be persisted, the user still sees one
    notice per run — never one after every dictation."""
    import types
    svc = _service(tmp_path)
    svc.start(now=T0 - timedelta(days=20))
    monkeypatch.setattr(access, "_trial_service", svc)
    monkeypatch.setattr(access, "_license_stamp", None)
    monkeypatch.setattr(license_service, "get_active_edition",
                        lambda path=None: "core")
    monkeypatch.setattr(svc, "mark_expired_notice_seen", lambda: False)
    notes = []
    stub = types.SimpleNamespace(cfg={}, notify=notes.append)
    for _ in range(5):
        access._trial_cache = None
        app_mod.ROARApp._maybe_trial_ended_notice(stub)
    assert len(notes) == 1
    access._trial_cache = None
    access._trial_service = None


def test_settings_only_consumes_the_notice_when_the_card_is_visible():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html = open(os.path.join(root, "settings.html"), encoding="utf-8").read()
    call = html.index("trial_notice_seen()")
    guard = html[max(0, call - 220):call]
    assert 'classList.contains("active")' in guard
    # and opening the About page re-renders the card so it can be acknowledged
    show = html.split("function showSection")[1].split("\n}")[0]
    assert 'id === "about"' in show and "renderTrial()" in show
