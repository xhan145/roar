import base64
import json
import os

import pytest

import commercial_config
import license as lic
import license_service as svc
from entitlements import CORE, PRO, DEVELOPER, SUPPORTER


@pytest.fixture(autouse=True)
def _clear_cache():
    svc.refresh()
    yield
    svc.refresh()


@pytest.fixture
def signing(monkeypatch):
    """Real Ed25519 keypair; the app's bundled public key is pointed at it so the
    default verifier accepts our test licenses (and nothing else)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization as ser
    priv = Ed25519PrivateKey.generate()
    pub_pem = priv.public_key().public_bytes(
        ser.Encoding.PEM, ser.PublicFormat.SubjectPublicKeyInfo).decode()
    monkeypatch.setattr(commercial_config, "LICENSE_PUBLIC_KEY_PEM", pub_pem)
    return priv


def _signed(priv, edition=PRO, major=1, **extra):
    p = {"schema_version": 1, "license_id": "ROAR-PRO-ABCD1234",
         "edition": edition, "issued_at": "2026-07-11",
         "valid_for_major": major, "customer_name": "Tester"}
    p.update(extra)
    p["signature"] = base64.b64encode(priv.sign(lic.canonical_bytes(p))).decode()
    return json.dumps(p)


# -- pure helpers ---------------------------------------------------------

def test_redact_license_id():
    assert svc.redact_license_id("ROAR-PRO-ABCD1234") == "ROAR…1234"
    assert svc.redact_license_id("SHORT") == "…HORT"
    assert svc.redact_license_id("") == ""
    assert svc.redact_license_id(None) == ""


def test_status_copy_core_is_reassuring_not_a_trial():
    text = svc.status_copy(CORE, False).lower()
    assert "free to use" in text and "privacy controls remain available" in text
    for banned in ("trial", "expired", "subscription", "lifetime"):
        assert banned not in text


def test_status_copy_paid_and_supporter():
    pro = svc.status_copy(PRO, True)
    assert "ROAR Pro is activated locally" in pro
    assert "No account is required" in pro
    sup = svc.status_copy(SUPPORTER, True)
    assert "Supporter" in sup and "Developer capabilities" in sup


def test_status_copy_unknown_edition_is_core():
    assert "ROAR Core" in svc.status_copy("bogus", True)


# -- get_status -----------------------------------------------------------

def test_missing_license_is_core(tmp_path):
    s = svc.get_status(str(tmp_path / "nope.json"))
    assert s["edition"] == CORE and s["valid"] is False and s["reason"] == "missing"
    assert s["license_id"] == "" and s["verified_offline"] is True


def test_malformed_license_is_core(tmp_path):
    p = tmp_path / "license.json"
    p.write_text("not json at all", encoding="utf-8")
    s = svc.get_status(str(p))
    assert s["edition"] == CORE and s["reason"] == "malformed"


def test_valid_pro_license_reports_pro_with_redacted_id(tmp_path, signing):
    p = tmp_path / "license.json"
    p.write_text(_signed(signing, PRO), encoding="utf-8")
    s = svc.get_status(str(p))
    assert s["edition"] == PRO and s["valid"] is True
    assert s["license_id"] == "ROAR…1234"          # redacted, never full
    assert s["customer_name"] == "Tester"
    assert s["valid_for_major"] == 1


def test_tampered_payload_is_core(tmp_path, signing):
    raw = json.loads(_signed(signing, PRO))
    raw["edition"] = DEVELOPER          # escalate without re-signing
    p = tmp_path / "license.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    s = svc.get_status(str(p))
    assert s["edition"] == CORE and s["reason"] == "bad_signature"
    assert s["license_id"] == ""        # untrusted fields never surfaced


def test_oversized_license_is_core(tmp_path):
    p = tmp_path / "license.json"
    p.write_text("x" * (svc.MAX_IMPORT_BYTES + 10), encoding="utf-8")
    assert svc.get_status(str(p))["edition"] == CORE


# -- import / remove ------------------------------------------------------

def test_import_valid_paste_installs_and_activates(tmp_path, signing):
    p = tmp_path / "license.json"
    r = svc.import_license(_signed(signing, DEVELOPER), str(p))
    assert r["ok"] is True and r["edition"] == DEVELOPER
    assert p.exists()
    assert svc.get_status(str(p))["edition"] == DEVELOPER


def test_import_from_file_path(tmp_path, signing):
    src = tmp_path / "given.json"
    src.write_text(_signed(signing, SUPPORTER), encoding="utf-8")
    dest = tmp_path / "license.json"
    r = svc.import_license(str(src), str(dest))
    assert r["ok"] is True and r["edition"] == SUPPORTER


def test_failed_import_preserves_existing_valid_license(tmp_path, signing):
    p = tmp_path / "license.json"
    svc.import_license(_signed(signing, PRO), str(p))
    before = p.read_text(encoding="utf-8")

    bad = svc.import_license("{garbage", str(p))
    assert bad["ok"] is False
    assert p.read_text(encoding="utf-8") == before        # untouched
    assert svc.get_status(str(p))["edition"] == PRO       # still Pro


def test_failed_import_of_unsigned_preserves_existing(tmp_path, signing):
    p = tmp_path / "license.json"
    svc.import_license(_signed(signing, PRO), str(p))
    unsigned = json.dumps({"edition": DEVELOPER, "valid_for_major": 1})
    r = svc.import_license(unsigned, str(p))
    assert r["ok"] is False                     # unsigned never unlocks
    assert svc.get_status(str(p))["edition"] == PRO


def test_oversized_paste_rejected_before_parsing(tmp_path):
    p = tmp_path / "license.json"
    r = svc.import_license("x" * (svc.MAX_IMPORT_BYTES + 10), str(p))
    assert r["ok"] is False and r["reason"] == "too_large"
    assert not p.exists()


def test_import_leaves_no_temp_files(tmp_path, signing):
    p = tmp_path / "license.json"
    svc.import_license(_signed(signing, PRO), str(p))
    leftovers = [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]
    assert leftovers == []


def test_remove_returns_core_and_keeps_user_content(tmp_path, signing):
    p = tmp_path / "license.json"
    user_file = tmp_path / "history.db"
    user_file.write_text("precious user data", encoding="utf-8")
    svc.import_license(_signed(signing, PRO), str(p))

    r = svc.remove_license(str(p))
    assert r["ok"] is True and r["edition"] == CORE
    assert not p.exists()
    assert user_file.read_text(encoding="utf-8") == "precious user data"


def test_remove_when_absent_is_safe(tmp_path):
    r = svc.remove_license(str(tmp_path / "nope.json"))
    assert r["ok"] is True and r["edition"] == CORE


# -- caching --------------------------------------------------------------

def test_import_refreshes_cached_edition(tmp_path, signing):
    p = tmp_path / "license.json"
    assert svc.get_active_edition(str(p)) == CORE      # caches Core
    svc.import_license(_signed(signing, PRO), str(p))
    assert svc.get_active_edition(str(p)) == PRO       # cache invalidated


def test_remove_refreshes_cached_edition(tmp_path, signing):
    p = tmp_path / "license.json"
    svc.import_license(_signed(signing, PRO), str(p))
    assert svc.get_active_edition(str(p)) == PRO
    svc.remove_license(str(p))
    assert svc.get_active_edition(str(p)) == CORE
