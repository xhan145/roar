"""Dual-key licence verification: founder OR fulfilment key, fail-closed."""

import base64

import pytest

import commercial_config as cc
import license as lic


@pytest.fixture(scope="module")
def keys():
    """Two real keypairs standing in for founder + fulfilment."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey)
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PublicFormat)

    def make():
        priv = Ed25519PrivateKey.generate()
        pem = priv.public_key().public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
        return priv, pem

    return {"founder": make(), "fulfillment": make(), "attacker": make()}


def _signed(priv, edition="pro"):
    payload = {"schema_version": 1, "license_id": "ROAR-W-TESTTESTTEST",
               "edition": edition, "issued_at": "2026-08-01",
               "valid_for_major": 1}
    payload["signature"] = base64.b64encode(
        priv.sign(lic.canonical_bytes(payload))).decode()
    return payload


def _verifier(keys, names):
    return lic.MultiKeyVerifier([keys[n][1] for n in names])


def test_founder_signed_licence_verifies(keys):
    v = _verifier(keys, ["founder", "fulfillment"])
    result = lic.validate_license(_signed(keys["founder"][0]), verifier=v,
                                  current_major=1, is_production=True)
    assert result.valid and result.edition == "pro"


def test_fulfillment_signed_licence_verifies(keys):
    v = _verifier(keys, ["founder", "fulfillment"])
    result = lic.validate_license(_signed(keys["fulfillment"][0]), verifier=v,
                                  current_major=1, is_production=True)
    assert result.valid and result.edition == "pro"


def test_unknown_key_is_rejected(keys):
    v = _verifier(keys, ["founder", "fulfillment"])
    result = lic.validate_license(_signed(keys["attacker"][0]), verifier=v,
                                  current_major=1, is_production=True)
    assert not result.valid
    assert result.reason == "bad_signature"


def test_key_order_does_not_matter(keys):
    v = _verifier(keys, ["fulfillment", "founder"])
    assert lic.validate_license(_signed(keys["founder"][0]), verifier=v,
                                current_major=1, is_production=True).valid


def test_empty_key_list_fails_closed():
    v = lic.MultiKeyVerifier([])
    assert v.verify(b"anything", b"sig") is False


def test_garbage_pem_in_list_is_ignored_not_fatal(keys):
    v = lic.MultiKeyVerifier(["not a pem", keys["founder"][1]])
    result = lic.validate_license(_signed(keys["founder"][0]), verifier=v,
                                  current_major=1, is_production=True)
    assert result.valid


def test_dev_env_still_rejected_in_production(keys):
    """Dual-key must not weaken the production dev-licence rejection."""
    payload = {"schema_version": 1, "license_id": "ROAR-DEV-X",
               "edition": "pro", "issued_at": "2026-08-01",
               "valid_for_major": 1, "env": "dev"}
    payload["signature"] = base64.b64encode(
        keys["fulfillment"][0].sign(lic.canonical_bytes(payload))).decode()
    v = _verifier(keys, ["founder", "fulfillment"])
    result = lic.validate_license(payload, verifier=v, current_major=1,
                                  is_production=True)
    assert not result.valid
    assert result.reason == "dev_rejected"


# -- shipped configuration ---------------------------------------------------

def test_config_ships_exactly_the_two_public_keys():
    assert len(cc.LICENSE_PUBLIC_KEYS) == 2
    assert cc.LICENSE_PUBLIC_KEYS[0] == cc.LICENSE_PUBLIC_KEY_PEM  # founder
    assert all(k.strip().startswith("-----BEGIN PUBLIC KEY-----")
               for k in cc.LICENSE_PUBLIC_KEYS)
    assert cc.LICENSE_PUBLIC_KEYS[0] != cc.LICENSE_PUBLIC_KEYS[1]


def test_default_verifier_accepts_both_shipped_keys_shape():
    v = lic._default_verifier()
    assert isinstance(v, lic.MultiKeyVerifier)
    assert len(v._verifiers) == 2
