"""Packaging invariants for the commercial layer: the public key ships, secrets
and dev fixtures do NOT, purchase URLs exist, and a production build refuses a
dev-signed license."""
import base64
import pathlib

import commercial_config as cc
import license as lic
from entitlements import CORE, PRO

ROOT = pathlib.Path(__file__).resolve().parent.parent
_SKIP_DIRS = {"venv", "dist", "build", ".git", "__pycache__", "models",
              "models-seed", "node_modules"}

_PRIVATE_KEY_MARKERS = ("BEGIN PRIVATE KEY", "BEGIN RSA PRIVATE KEY",
                        "BEGIN EC PRIVATE KEY", "BEGIN OPENSSH PRIVATE KEY")


def _source_files():
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in (".py", ".md", ".json", ".spec", ".txt",
                                ".html", ".pem", ".key", ".cfg", ".toml"):
            yield p


def test_public_verification_key_ships():
    assert "BEGIN PUBLIC KEY" in cc.LICENSE_PUBLIC_KEY_PEM
    # and it must actually load as a usable Ed25519 verifier
    v = lic.CryptographySignatureVerifier(cc.LICENSE_PUBLIC_KEY_PEM)
    assert v.verify(b"nope", b"not-a-signature") is False   # loads + fails closed


def test_no_private_key_anywhere_in_the_source_tree():
    me = pathlib.Path(__file__).resolve()   # this scanner names the markers
    offenders = []
    for p in _source_files():
        if p.resolve() == me:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(m in text for m in _PRIVATE_KEY_MARKERS):
            offenders.append(str(p.relative_to(ROOT)))
    assert not offenders, f"private key material in the repo: {offenders}"


def test_no_installed_license_or_grant_is_committed():
    """A shipped, accepted sample license would be a bypass."""
    for name in ("license.json", "legacy_grant.json"):
        assert not (ROOT / name).exists() or name in _gitignored(), name


def _gitignored():
    gi = ROOT / ".gitignore"
    return gi.read_text(encoding="utf-8") if gi.exists() else ""


def test_purchase_urls_and_prices_are_configured_constants():
    for url in (cc.PURCHASE_URL_PRO, cc.PURCHASE_URL_DEVELOPER,
                cc.PURCHASE_URL_SUPPORTER):
        assert isinstance(url, str) and url.startswith("https://")
    for price in (cc.PRO_PRICE_USD, cc.DEVELOPER_PRICE_USD,
                  cc.SUPPORTER_PRICE_USD):
        assert isinstance(price, int) and price > 0


def test_repo_pricing_is_the_agreed_29_49_99():
    """The commercial brief's $19/$29/$49 table is stale — 29/49/99 was set
    explicitly by the owner and re-confirmed. See docs/commercial/
    REPOSITORY_COMMERCIAL_AUDIT.md divergence #1."""
    assert (cc.PRO_PRICE_USD, cc.DEVELOPER_PRICE_USD,
            cc.SUPPORTER_PRICE_USD) == (29, 49, 99)


def _signed(priv, **extra):
    p = {"schema_version": 1, "license_id": "ROAR-DEV-TEST", "edition": PRO,
         "issued_at": "2026-07-11", "valid_for_major": 1}
    p.update(extra)
    p["signature"] = base64.b64encode(priv.sign(lic.canonical_bytes(p))).decode()
    return p


def test_production_build_rejects_a_dev_signed_license():
    """A dev license must never work in a production build."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization as ser
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(
        ser.Encoding.PEM, ser.PublicFormat.SubjectPublicKeyInfo)
    verifier = lic.CryptographySignatureVerifier(pub)
    payload = _signed(priv, env="dev")

    dev_build = lic.validate_license(payload, verifier=verifier, is_production=False)
    assert dev_build.valid is True and dev_build.edition == PRO

    prod_build = lic.validate_license(payload, verifier=verifier, is_production=True)
    assert prod_build.valid is False
    assert prod_build.edition == CORE
    assert prod_build.reason == "dev_rejected"


def test_a_license_signed_by_the_wrong_key_is_rejected():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization as ser
    attacker = Ed25519PrivateKey.generate()
    other = Ed25519PrivateKey.generate()
    pub = other.public_key().public_bytes(
        ser.Encoding.PEM, ser.PublicFormat.SubjectPublicKeyInfo)
    r = lic.validate_license(_signed(attacker),
                             verifier=lic.CryptographySignatureVerifier(pub))
    assert r.valid is False and r.edition == CORE


def test_pyinstaller_spec_does_not_bundle_dev_tooling_or_keys():
    spec = (ROOT / "roar.spec").read_text(encoding="utf-8")
    for banned in ("dev_generate_license", "verify_license_file",
                   "private", "secret_key", "tests/fixtures"):
        assert banned not in spec, banned
