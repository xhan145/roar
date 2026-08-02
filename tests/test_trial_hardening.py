"""Trial hardening: preservation, privacy, offline, packaging, diagnostics.

The release-blocker list in TRIAL_ARCHITECTURE.md is pinned here: expiry
deletes nothing, personal-data controls never couple to trial state, the
trial ships with no network calls, no environment bypass, no bundled
records, and diagnostics stay redacted.
"""

import glob
import json
import os
import re
from datetime import datetime, timedelta, timezone

import pytest

import access
import diagnostics
import entitlements as ent
import license_service
import settings_ui
import trial
import trial_store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.now(timezone.utc)
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


# -- expiry preserves everything the user made -------------------------------

def test_expiry_touches_no_user_files(tmp_path):
    import config as config_mod
    cfg_path = tmp_path / "config.json"
    cfg = config_mod.load(str(cfg_path))
    cfg["automation_rules"] = [{"phrase": "sign off", "expansion": "Best,"}]
    cfg["route_profiles"] = {"code.exe": {"notes": True}}
    cfg["custom_vocabulary"] = ["Fable"]
    cfg["corrections"] = {"flow local": "FlowLocal"}
    config_mod.save(cfg, str(cfg_path))
    before = cfg_path.read_bytes()
    history = tmp_path / "history.db"
    history.write_bytes(b"user history bytes")

    svc = _service(tmp_path)
    svc.start(now=T0)
    assert svc.status(now=T0 + timedelta(days=20)).state == trial.EXPIRED
    svc.mark_expired_notice_seen()

    assert cfg_path.read_bytes() == before
    assert history.read_bytes() == b"user history bytes"


def test_clearing_personal_data_cannot_touch_the_trial(tmp_path):
    svc = _service(tmp_path)
    svc.start(now=T0)
    # simulate every personal-data clear: none of them know the trial path
    for artifact in ("history.db", "audio", "vocabulary.json",
                     "snippets.json", "diagnostics.log"):
        p = tmp_path / artifact
        p.write_text("x", encoding="utf-8")
        p.unlink()
    status = svc.status(now=T0 + timedelta(days=1))
    assert status.state == trial.ACTIVE
    assert status.started_at == T0


def test_settings_reset_does_not_restart_the_trial(tmp_path):
    import config as config_mod
    cfg_path = tmp_path / "config.json"
    config_mod.save(config_mod.load(str(cfg_path)), str(cfg_path))
    svc = _service(tmp_path)
    svc.start(now=T0)
    os.remove(str(cfg_path))                      # "reset settings"
    late = T0 + timedelta(days=30)
    assert svc.status(now=late).state == trial.EXPIRED
    assert svc.start(now=late).state == trial.EXPIRED


def test_trial_lives_beside_the_license_not_the_personal_data(monkeypatch,
                                                              tmp_path):
    import paths
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    trial_dir = os.path.dirname(paths.trial_state_path())
    assert trial_dir == os.path.dirname(paths.license_path())
    assert trial_dir != os.path.dirname(paths.history_db_path())


# -- core stays free, paid stays configured ----------------------------------

def test_every_core_promise_survives_expiry(tmp_path, monkeypatch):
    svc = _service(tmp_path)
    svc.start(now=T0)
    monkeypatch.setattr(access, "_trial_service", svc)
    monkeypatch.setattr(access, "grants", lambda: frozenset())
    monkeypatch.setattr(access.license_service, "get_active_edition",
                        lambda path=None: "core")
    real = svc.status
    monkeypatch.setattr(svc, "status",
                        lambda now=None: real(now=T0 + timedelta(days=30)))
    access._trial_cache = None
    assert access.effective_edition() == "core"
    for feature in sorted(ent.ALWAYS_FREE):
        access._trial_cache = None
        assert access.can(feature), feature
    for feature in ("privacy.controls", "history.delete", "audio.delete"):
        assert feature in ent.ALWAYS_FREE
    access._trial_cache = None
    access._trial_service = None


# -- offline + no bypass -----------------------------------------------------

def test_trial_feature_makes_no_network_calls_and_reads_no_environ():
    for name in ("trial.py", "trial_store.py"):
        src = open(os.path.join(ROOT, name), encoding="utf-8").read()
        for banned in ("urlopen", "requests.", "socket.socket", "http.client",
                       "os.environ", "os.getenv", "getenv("):
            assert banned not in src, f"{name}: {banned}"


def test_no_trial_env_bypass_anywhere_first_party():
    for py in glob.glob(os.path.join(ROOT, "*.py")):
        src = open(py, encoding="utf-8", errors="ignore").read()
        assert "ROAR_TRIAL" not in src, py


def test_bridge_trial_methods_have_no_network_calls():
    src = open(os.path.join(ROOT, "settings_ui.py"), encoding="utf-8").read()
    section = src.split("def trial_info")[1].split("def _write")[0]
    for banned in ("urlopen", "requests.", "socket"):
        assert banned not in section


# -- packaging ----------------------------------------------------------------

def test_no_trial_records_are_bundled():
    for spec in glob.glob(os.path.join(ROOT, "*.spec")):
        src = open(spec, encoding="utf-8", errors="ignore").read()
        assert "trial.json" not in src, spec


def test_source_run_trial_file_is_gitignored():
    gitignore = open(os.path.join(ROOT, ".gitignore"),
                     encoding="utf-8").read().splitlines()
    assert "trial.json" in gitignore


# -- diagnostics redaction ----------------------------------------------------

@pytest.fixture
def api(tmp_path, monkeypatch):
    bridge = settings_ui.SettingsAPI(config_path=str(tmp_path / "config.json"))
    bridge._trial_svc = _service(tmp_path)
    monkeypatch.setattr(license_service, "get_status", lambda path=None: {
        "edition": "core", "valid": False, "reason": "missing",
        "license_id": "", "customer_name": "", "valid_for_major": None,
        "verified_offline": True, "message": "", "detail": "",
    })
    return bridge


def test_diagnostics_show_trial_facts_only(api):
    api._trial_svc.start(now=NOW - timedelta(hours=1))
    report = api.diagnostics_get()["report"]
    assert "effective_edition: Trial" in report
    assert "trial_status: Active" in report
    assert "trial_started: " in report
    assert "trial_expires: " in report
    assert "trial_days_remaining: 13" in report


def test_diagnostics_after_expiry_read_core(api):
    api._trial_svc.start(now=NOW - timedelta(days=30))
    report = api.diagnostics_get()["report"]
    assert "effective_edition: Core" in report
    assert "trial_status: Expired" in report
    assert "trial_days_remaining" not in report


def test_diagnostics_never_leak_protection_material(api, tmp_path):
    api._trial_svc.start(now=NOW - timedelta(hours=1))
    report = api.diagnostics_get()["report"].lower()
    envelope = json.loads((tmp_path / "trial.json").read_text(encoding="utf-8"))
    for banned in ("signature", "key_b64", "dpapi", "hmac",
                   envelope["record"]["trial_id"].lower()):
        assert banned not in report


def test_redactor_drops_raw_trial_material():
    filtered = diagnostics.redact_diagnostics({
        "trial_status": "Active", "signature": "abc", "key_b64": "xyz",
        "trial_record": {"trial_id": "deadbeef"},
    })
    assert filtered == {"trial_status": "Active"}


def test_status_channel_still_bans_private_fields():
    import status
    for banned in ("transcript", "clipboard", "audio", "window_title"):
        assert banned not in status.ALLOWED


# -- upgrades, contextual prompts, browser failures --------------------------

def test_normal_application_upgrade_preserves_the_trial(tmp_path):
    """An MSI upgrade replaces program files, not %APPDATA% — a new process
    reading the same store must see the same trial, mid-flight."""
    marker = FakeMarker()
    _service(tmp_path, marker).start(now=T0)
    # "new version starts": fresh service objects, same stores
    after_upgrade = _service(tmp_path, marker)
    status = after_upgrade.status(now=T0 + timedelta(days=7))
    assert status.state == trial.ACTIVE
    assert status.started_at == T0
    assert status.days_remaining == 7
    # and it still cannot be restarted
    assert after_upgrade.start(now=T0 + timedelta(days=7)).started_at == T0


def test_upgrading_an_existing_install_never_auto_starts_a_trial(tmp_path):
    """v0.13/v0.14 users land on not_started — the button is the only door."""
    import config as config_mod
    cfg_path = tmp_path / "config.json"
    cfg = config_mod.load(str(cfg_path))
    cfg["commercial_schema"] = 1          # an already-migrated older install
    config_mod.save(cfg, str(cfg_path))
    svc = _service(tmp_path)
    assert svc.status(now=T0).state == trial.NOT_STARTED
    assert not os.path.exists(str(tmp_path / "trial.json"))


def test_upgrade_prompts_are_pull_only_never_pushed():
    """Contextual upgrade copy exists as a lookup; nothing in the app shows it
    on launch. prompt_for() answers a question the user asked by clicking."""
    import upgrade_prompts
    assert upgrade_prompts.prompt_for("dictation.push_to_talk") is None
    prompt = upgrade_prompts.prompt_for("code.mode")
    assert prompt and "Not Now" in prompt["buttons"]
    html = open(os.path.join(ROOT, "settings.html"), encoding="utf-8").read()
    # every browser launch sits behind a click handler (no startup nag)
    for match in re.finditer(r"window\.open\(", html):
        assert "=>" in html[max(0, match.start() - 40):match.start()]
    app_src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
    assert "upgrade_prompts" not in app_src   # the tray never nags


def test_purchase_launch_failure_is_handled_gracefully():
    html = open(os.path.join(ROOT, "settings.html"), encoding="utf-8").read()
    body = html.split("function openPurchase")[1].split("\n}")[0]
    assert "try {" in body and "catch" in body
    assert "could not open your browser" in body
    assert "No purchase link is configured" in body
    # the purchase buttons go through the guarded helper, not raw window.open
    for button in ("b-buy-pro", "b-buy-dev", "b-buy-supporter"):
        line = [l for l in html.splitlines()
                if f'$("{button}").onclick' in l][0]
        assert "openPurchase(" in line
