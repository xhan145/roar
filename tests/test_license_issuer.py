"""Tests for the pure license-payload builder (license_issuer.py).

The critical guarantee: a payload built here, signed with a private key, must
VERIFY as valid through the real app-side validator in license.py — and it must
NOT carry the dev marker that a production build rejects.
"""
import pytest

import license as lic
import license_issuer as iss
from entitlements import CORE, PRO, DEVELOPER, SUPPORTER


# --- token_from_bytes -------------------------------------------------------

def test_token_is_uppercase_unambiguous_and_right_length():
    tok = iss.token_from_bytes(bytes(range(20)), length=8)
    assert len(tok) == 8
    assert all(c in iss._TOKEN_ALPHABET for c in tok)
    # unambiguous alphabet excludes 0/O/1/I
    assert not (set("01OI") & set(tok))


def test_token_is_deterministic_for_same_bytes():
    raw = b"\x10\x20\x30\x40\x50\x60\x70\x80"
    assert iss.token_from_bytes(raw) == iss.token_from_bytes(raw)


def test_token_rejects_empty_randomness():
    with pytest.raises(ValueError):
        iss.token_from_bytes(b"", length=8)


# --- new_license_id ---------------------------------------------------------

def test_new_license_id_shape():
    lid = iss.new_license_id("pro", "ABCD2345")
    assert lid == "ROAR-PRO-ABCD2345"


def test_new_license_id_rejects_core():
    with pytest.raises(ValueError):
        iss.new_license_id("core", "ABCD2345")


def test_new_license_id_rejects_bad_token():
    with pytest.raises(ValueError):
        iss.new_license_id("pro", "abc-01")  # lowercase + ambiguous + dash


# --- build_payload ----------------------------------------------------------

def test_build_payload_has_no_env_or_signature():
    p = iss.build_payload("pro", "Ada", "ROAR-PRO-ABCD2345", "2026-07-17")
    assert "signature" not in p
    assert "env" not in p  # production licenses must never be dev-marked


def test_build_payload_normalizes_edition_case():
    p = iss.build_payload("PRO", "Ada", "ROAR-PRO-ABCD2345", "2026-07-17")
    assert p["edition"] == PRO


@pytest.mark.parametrize("edition", [PRO, DEVELOPER, SUPPORTER])
def test_build_payload_accepts_every_sellable_edition(edition):
    lid = f"ROAR-{edition.upper()}-ABCD2345"
    p = iss.build_payload(edition, "Ada", lid, "2026-07-17")
    assert p["edition"] == edition


def test_build_payload_rejects_core():
    with pytest.raises(ValueError):
        iss.build_payload("core", "Ada", "ROAR-CORE-ABCD2345", "2026-07-17")


def test_build_payload_rejects_id_mismatched_to_edition():
    with pytest.raises(ValueError):
        iss.build_payload("pro", "Ada", "ROAR-DEVELOPER-ABCD2345", "2026-07-17")


def test_build_payload_rejects_bad_date():
    with pytest.raises(ValueError):
        iss.build_payload("pro", "Ada", "ROAR-PRO-ABCD2345", "July 17")


def test_build_payload_rejects_major_below_one():
    with pytest.raises(ValueError):
        iss.build_payload("pro", "Ada", "ROAR-PRO-ABCD2345", "2026-07-17",
                          valid_for_major=0)


def test_build_payload_omits_empty_email_hash():
    p = iss.build_payload("pro", "Ada", "ROAR-PRO-ABCD2345", "2026-07-17",
                          email_hash="")
    assert p["email_hash"] is None


# --- the whole point: it verifies through the real app validator ------------

@pytest.fixture
def keypair():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization as ser
    priv = Ed25519PrivateKey.generate()
    pub_pem = priv.public_key().public_bytes(
        ser.Encoding.PEM, ser.PublicFormat.SubjectPublicKeyInfo)
    return priv, lic.CryptographySignatureVerifier(pub_pem)


def _sign(priv, payload):
    import base64
    payload = dict(payload)
    payload["signature"] = base64.b64encode(
        priv.sign(lic.canonical_bytes(payload))).decode()
    return payload


def test_issued_license_validates_as_ok(keypair):
    priv, verifier = keypair
    payload = iss.build_payload("pro", "Ada", "ROAR-PRO-ABCD2345", "2026-07-17")
    signed = _sign(priv, payload)
    result = lic.validate_license(signed, verifier=verifier, current_major=1)
    assert result.valid and result.edition == PRO and result.reason == "ok"


def test_issued_license_is_rejected_in_production_only_if_dev_marked(keypair):
    """A production-built payload has no env:dev, so a production verifier
    accepts it — proving these licenses work when IS_PRODUCTION is True."""
    priv, verifier = keypair
    payload = iss.build_payload("developer", "Ada",
                                "ROAR-DEVELOPER-ABCD2345", "2026-07-17")
    signed = _sign(priv, payload)
    result = lic.validate_license(signed, verifier=verifier,
                                  current_major=1, is_production=True)
    assert result.valid and result.edition == DEVELOPER


def test_wrong_major_is_rejected(keypair):
    priv, verifier = keypair
    payload = iss.build_payload("pro", "Ada", "ROAR-PRO-ABCD2345",
                                "2026-07-17", valid_for_major=1)
    signed = _sign(priv, payload)
    result = lic.validate_license(signed, verifier=verifier, current_major=2)
    assert not result.valid and result.reason == "wrong_major"


def test_tampering_breaks_the_signature(keypair):
    priv, verifier = keypair
    payload = iss.build_payload("pro", "Ada", "ROAR-PRO-ABCD2345", "2026-07-17")
    signed = _sign(priv, payload)
    signed["edition"] = SUPPORTER  # upgrade attempt after signing
    result = lic.validate_license(signed, verifier=verifier, current_major=1)
    assert not result.valid and result.reason == "bad_signature"
