"""Trial activation UI: settings bridge methods + static scans of the card.

Follows the test_license_ui.py conventions: bridge functions are exercised
with injected trial services and licence states; the HTML is scanned as text
for the required ids and calm copy, and for the absence of urgency."""

import os
import re
from datetime import timedelta, timezone, datetime

import pytest

import license_service
import settings_ui
import trial
import trial_store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "settings.html"), encoding="utf-8") as _fh:
    HTML = _fh.read()
BRIDGE_SRC = open(os.path.join(ROOT, "settings_ui.py"), encoding="utf-8").read()

NOW = datetime.now(timezone.utc)


class FakeMarker:
    def __init__(self):
        self.value = None

    def read(self):
        return self.value

    def write(self, envelope):
        self.value = envelope


@pytest.fixture
def api(tmp_path, monkeypatch):
    bridge = settings_ui.SettingsAPI(config_path=str(tmp_path / "config.json"))
    bridge._trial_svc = trial_store.TrialService(
        path=str(tmp_path / "trial.json"), marker=FakeMarker(),
        protection=trial_store.NullProtection())
    monkeypatch.setattr(license_service, "get_status", lambda path=None: {
        "edition": "core", "valid": False, "reason": "missing",
        "license_id": "", "customer_name": "", "valid_for_major": None,
        "verified_offline": True, "message": "", "detail": "",
    })
    return bridge


def _license(monkeypatch, edition):
    monkeypatch.setattr(license_service, "get_status", lambda path=None: {
        "edition": edition, "valid": True, "reason": "ok",
        "license_id": "ROAR-TEST", "customer_name": "", "valid_for_major": 1,
        "verified_offline": True, "message": "", "detail": "",
    })


# -- bridge: trial_info / trial_start / trial_notice_seen --------------------

def test_info_starts_not_started_and_enabled(api):
    info = api.trial_info()
    assert info["state"] == trial.NOT_STARTED
    assert info["enabled"] is True
    assert info["badge"] == ""
    assert info["show_expiry_notice"] is False


def test_start_activates_and_reports_calmly(api):
    r = api.trial_start()
    assert r["ok"] is True
    assert "trial has started" in r["message"]
    assert "Pro and Developer features are now available locally" in r["message"]
    info = api.trial_info()
    assert info["state"] == trial.ACTIVE
    assert info["started"] and info["expires"]
    assert info["effective_edition"] == "Trial"


def test_start_twice_refuses_politely(api):
    api.trial_start()
    r = api.trial_start()
    assert r["ok"] is False
    assert "already been used" in r["message"]


def test_active_badge_counts_whole_days(api):
    api._trial_svc.start(now=NOW - timedelta(hours=1))
    info = api.trial_info()
    assert "Full-Feature Trial" in info["badge"]
    assert "13 days remaining" in info["badge"]
    assert info["days_remaining"] == 13


def test_badge_can_be_disabled_by_config(api, tmp_path):
    import config as config_mod
    cfg = config_mod.load(str(tmp_path / "config.json"))
    cfg["trial_status_badge_enabled"] = False
    config_mod.save(cfg, str(tmp_path / "config.json"))
    api._trial_svc.start(now=NOW - timedelta(hours=1))
    assert api.trial_info()["badge"] == ""


def test_trial_disabled_config_hides_and_refuses(api, tmp_path):
    import config as config_mod
    cfg = config_mod.load(str(tmp_path / "config.json"))
    cfg["trial_enabled"] = False
    config_mod.save(cfg, str(tmp_path / "config.json"))
    assert api.trial_info()["enabled"] is False
    assert api.trial_start()["ok"] is False


def test_expired_shows_notice_once(api):
    api._trial_svc.start(now=NOW - timedelta(days=20))
    info = api.trial_info()
    assert info["state"] == trial.EXPIRED
    assert info["show_expiry_notice"] is True
    api.trial_notice_seen()
    assert api.trial_info()["show_expiry_notice"] is False


def test_licence_wins_and_ends_trial_countdown(api, monkeypatch):
    api._trial_svc.start(now=NOW - timedelta(hours=1))
    _license(monkeypatch, "pro")
    info = api.trial_info()
    assert info["state"] == trial.LICENSED
    assert info["effective_edition"] == "Pro"
    assert info["badge"] == ""
    assert info["show_expiry_notice"] is False


def test_licence_activation_during_expired_trial_shows_no_notice(api,
                                                                 monkeypatch):
    api._trial_svc.start(now=NOW - timedelta(days=30))
    _license(monkeypatch, "developer")
    info = api.trial_info()
    assert info["state"] == trial.LICENSED
    assert info["show_expiry_notice"] is False


def test_info_never_carries_raw_protection_material(api):
    api.trial_start()
    info = api.trial_info()
    flat = str(info).lower()
    for banned in ("signature", "key_b64", "hmac", "dpapi", "trial_id"):
        assert banned not in flat


# -- static scans of the Settings card ---------------------------------------

def test_trial_card_elements_exist():
    for el in ("trial-block", "t-pre", "t-active", "b-trial-start",
               "b-trial-core", "b-trial-license", "b-trial-retry",
               "trial-badge", "t-headline", "t-meta", "t-note", "m-trial"):
        assert f'id="{el}"' in HTML, el


def test_trial_card_copy_is_calm_and_complete():
    for phrase in (
        "Try every ROAR feature for 14 days",
        "No account.", "No payment card.", "No subscription.",
        "Your voice stays on this computer.",
        "Start 14-Day Trial", "Continue with ROAR Core",
        "Your ROAR trial has ended",
        "still yours to use for free",
        "have been preserved",
        "appears to have moved backward",
        "ROAR Core remains available",
    ):
        assert phrase in HTML, phrase


def test_no_urgency_no_timers_no_accusations():
    low = HTML.lower()
    for banned in ("trial expired", "hours remaining", "minutes remaining",
                   "seconds remaining", "limited time", "only today",
                   "hurry", "last chance", "piracy", "% off"):
        assert banned not in low, banned


def test_trial_starts_only_from_the_explicit_button():
    # exactly one call site, and it is inside a click handler
    calls = [m.start() for m in re.finditer(r"trial_start\(\)", HTML)]
    assert len(calls) == 1
    before = HTML[max(0, calls[0] - 120):calls[0]]
    assert 'addEventListener("click"' in before


def test_bridge_exposes_the_three_trial_methods():
    for name in ("def trial_info", "def trial_start",
                 "def trial_notice_seen"):
        assert name in BRIDGE_SRC


# -- expiry + contextual upgrade UX ------------------------------------------

def test_expired_card_offers_the_four_actions():
    for el in ("t-actions", "b-trial-buy-pro", "b-trial-buy-dev",
               "b-trial-enter", "b-trial-continue"):
        assert f'id="{el}"' in HTML, el
    # purchase clicks delegate to the canonical license buttons - no new
    # window.open sites, one source of labels and links
    assert '$("b-buy-pro").click()' in HTML
    assert '$("b-buy-dev").click()' in HTML


def test_settings_marks_the_ended_notice_seen_once():
    assert "trial_notice_seen()" in HTML


def test_app_has_the_idle_moment_notice():
    src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
    assert "_maybe_trial_ended_notice" in src
    method = src.split("def _maybe_trial_ended_notice")[1]
    method = method.split("\n    def ")[0]
    # marked seen BEFORE notifying, so it can never repeat
    assert method.index("mark_trial_notice_seen") < method.index("self.notify")
    assert "trial has ended" in method
    assert "preserved" in method
    # fires from the IDLE transition only
    set_state = src.split("def _set_state")[1].split("\n    def ")[0]
    assert "_maybe_trial_ended_notice" in set_state
    assert "self.IDLE" in set_state


def test_app_notice_fires_once_and_only_when_expired_unlicensed(
        tmp_path, monkeypatch):
    import types
    import access
    import app as app_mod

    svc = trial_store.TrialService(
        path=str(tmp_path / "trial.json"), marker=FakeMarker(),
        protection=trial_store.NullProtection())
    svc.start(now=NOW - timedelta(days=20))
    monkeypatch.setattr(access, "_trial_service", svc)
    monkeypatch.setattr(access, "_trial_cache", None)
    monkeypatch.setattr(access.license_service, "get_active_edition",
                        lambda path=None: "core")
    notes = []
    stub = types.SimpleNamespace(cfg={}, notify=notes.append)
    app_mod.ROARApp._maybe_trial_ended_notice(stub)
    assert len(notes) == 1
    assert "trial has ended" in notes[0]
    assert "preserved" in notes[0]
    # the record remembers: never a second notice
    access._trial_cache = None
    app_mod.ROARApp._maybe_trial_ended_notice(stub)
    assert len(notes) == 1


def test_app_notice_respects_licence_and_config(tmp_path, monkeypatch):
    import types
    import access
    import app as app_mod

    svc = trial_store.TrialService(
        path=str(tmp_path / "trial.json"), marker=FakeMarker(),
        protection=trial_store.NullProtection())
    svc.start(now=NOW - timedelta(days=20))
    monkeypatch.setattr(access, "_trial_service", svc)
    monkeypatch.setattr(access, "_trial_cache", None)
    notes = []
    # a valid licence silences the notice entirely
    monkeypatch.setattr(access.license_service, "get_active_edition",
                        lambda path=None: "pro")
    stub = types.SimpleNamespace(cfg={}, notify=notes.append)
    app_mod.ROARApp._maybe_trial_ended_notice(stub)
    assert notes == []
    # and so does the config switch
    monkeypatch.setattr(access.license_service, "get_active_edition",
                        lambda path=None: "core")
    access._trial_cache = None
    stub_off = types.SimpleNamespace(
        cfg={"trial_expiry_notice_enabled": False}, notify=notes.append)
    app_mod.ROARApp._maybe_trial_ended_notice(stub_off)
    assert notes == []
