import base64
import json

import pytest

import license as lic
from entitlements import CORE, PRO, DEVELOPER, SUPPORTER


class FakeVerifier(lic.SignatureVerifier):
    """Tests-only deterministic verifier (never used by the app)."""
    def __init__(self, ok=True):
        self.ok = ok

    def verify(self, message, signature):
        return self.ok


@pytest.fixture
def keypair():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization as ser
    priv = Ed25519PrivateKey.generate()
    pub_pem = priv.public_key().public_bytes(
        ser.Encoding.PEM, ser.PublicFormat.SubjectPublicKeyInfo)
    return priv, lic.CryptographySignatureVerifier(pub_pem)


def _payload(edition=PRO, major=1, **extra):
    p = {"license_id": "ROAR-TEST", "name": "Tester", "edition": edition,
         "issued_at": "2026-07-06", "valid_for_major": major}
    p.update(extra)
    return p


def _sign(payload, priv):
    payload = dict(payload)
    payload["signature"] = base64.b64encode(priv.sign(lic.canonical_bytes(payload))).decode()
    return payload


def test_missing_license_is_core():
    r = lic.load_license(None)
    assert r.edition == CORE and not r.valid and r.reason == "missing"


def test_get_current_edition_core_without_license():
    assert lic.get_current_edition(None) == CORE


def test_valid_pro(keypair):
    priv, verifier = keypair
    r = lic.validate_license(_sign(_payload(PRO), priv), verifier=verifier, current_major=1)
    assert r.edition == PRO and r.valid and r.reason == "ok"


def test_valid_developer(keypair):
    priv, verifier = keypair
    r = lic.validate_license(_sign(_payload(DEVELOPER), priv), verifier=verifier, current_major=1)
    assert r.edition == DEVELOPER and r.valid


def test_valid_supporter(keypair):
    priv, verifier = keypair
    r = lic.validate_license(_sign(_payload(SUPPORTER), priv), verifier=verifier, current_major=1)
    assert r.edition == SUPPORTER and r.valid


def test_bad_signature_is_core(keypair):
    priv, verifier = keypair
    signed = _sign(_payload(PRO), priv)
    signed["name"] = "Tampered After Signing"   # canonical bytes no longer match
    r = lic.validate_license(signed, verifier=verifier, current_major=1)
    assert r.edition == CORE and not r.valid and r.reason == "bad_signature"


def test_wrong_key_is_core(keypair):
    _, verifier = keypair
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    other = Ed25519PrivateKey.generate()
    r = lic.validate_license(_sign(_payload(PRO), other), verifier=verifier, current_major=1)
    assert r.reason == "bad_signature" and r.edition == CORE


def test_missing_signature_is_unsigned():
    r = lic.validate_license(_payload(PRO), verifier=FakeVerifier(), current_major=1)
    assert r.reason == "unsigned" and r.edition == CORE


def test_malformed_payload_is_core():
    assert lic.validate_license("not a dict", verifier=FakeVerifier()).reason == "malformed"
    assert lic.parse_license("{bad json") is None
    assert lic.parse_license("[1,2,3]") is None   # valid JSON but not an object


def test_unsupported_edition(keypair):
    priv, verifier = keypair
    r = lic.validate_license(_sign(_payload("ultimate"), priv), verifier=verifier, current_major=1)
    assert r.reason == "unsupported_edition" and r.edition == CORE


def test_wrong_major(keypair):
    priv, verifier = keypair
    r = lic.validate_license(_sign(_payload(PRO, major=2), priv), verifier=verifier, current_major=1)
    assert r.reason == "wrong_major" and r.edition == CORE


def test_dev_license_rejected_only_in_production(keypair):
    priv, verifier = keypair
    signed = _sign(_payload(PRO, env="dev"), priv)
    dev = lic.validate_license(signed, verifier=verifier, current_major=1, is_production=False)
    assert dev.edition == PRO and dev.valid
    prod = lic.validate_license(signed, verifier=verifier, current_major=1, is_production=True)
    assert prod.reason == "dev_rejected" and prod.edition == CORE


def test_huge_and_empty_input():
    assert lic.parse_license("x" * (64 * 1024 + 5)) is None
    assert lic.parse_license("") is None
    assert lic.parse_license(None) is None


def test_corrupt_file(tmp_path):
    p = tmp_path / "lic.json"
    p.write_bytes(b"\x00\x01 not json \xff")
    r = lic.load_license(str(p))
    assert r.edition == CORE and not r.valid


def test_load_valid_from_file(tmp_path, keypair):
    priv, verifier = keypair
    p = tmp_path / "lic.json"
    p.write_text(json.dumps(_sign(_payload(PRO), priv)), encoding="utf-8")
    assert lic.load_license(str(p), verifier=verifier).edition == PRO
    assert lic.get_current_edition(str(p), verifier=verifier) == PRO


def test_license_module_imports_no_user_data_or_network():
    import ast
    import pathlib
    tree = ast.parse(pathlib.Path("license.py").read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    for banned in {"socket", "urllib", "requests", "http",
                   "history", "audio", "transcriber", "recorder", "clipboard"}:
        assert banned not in mods, banned
