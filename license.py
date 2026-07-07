"""Offline license verification.

ROAR needs no license for local dictation. This module is deliberately pure: it
never reads transcript, audio, history, snippets, vocabulary, clipboard,
diagnostics, or the network. Every failure fails **closed to Core** and never
raises — a license problem must never crash the app.

Signature scheme: Ed25519 over the canonical JSON of the payload (all fields
except `signature`, sorted keys, compact separators). Only a PUBLIC key ships in
the app; the private key never lives in the repo or the binary. In a production
build (`commercial_config.IS_PRODUCTION`), dev-signed licenses are rejected.

Editions and the feature vocabulary live in `entitlements.py`.
"""
from dataclasses import dataclass
import base64
import json

import commercial_config
from entitlements import CORE, PRO, DEVELOPER, SUPPORTER, normalize_edition

_KNOWN_EDITIONS = (CORE, PRO, DEVELOPER, SUPPORTER)
_MAX_LICENSE_BYTES = 64 * 1024  # a license is tiny; anything bigger is bogus


@dataclass(frozen=True)
class LicenseResult:
    edition: str = CORE
    valid: bool = False
    # missing|corrupt|malformed|unsigned|bad_signature|unsupported_edition|
    # wrong_major|dev_rejected|core|ok
    reason: str = "missing"


class SignatureVerifier:
    """Interface: return True iff `signature` is a valid signature over
    `message`. Implementations MUST fail closed (return False, never raise)."""

    def verify(self, message: bytes, signature: bytes) -> bool:  # pragma: no cover
        raise NotImplementedError


class _NullVerifier(SignatureVerifier):
    """Used when no crypto backend is available — rejects everything, so the app
    degrades to Core instead of crashing."""

    def verify(self, message: bytes, signature: bytes) -> bool:
        return False


class CryptographySignatureVerifier(SignatureVerifier):
    """Ed25519 verification via the `cryptography` library."""

    def __init__(self, public_key_pem):
        self._key = None
        try:
            from cryptography.hazmat.primitives.serialization import load_pem_public_key
            pem = public_key_pem.encode() if isinstance(public_key_pem, str) else public_key_pem
            self._key = load_pem_public_key(pem)
        except Exception:
            self._key = None  # fail closed

    def verify(self, message: bytes, signature: bytes) -> bool:
        if self._key is None:
            return False
        try:
            self._key.verify(signature, message)  # raises on mismatch
            return True
        except Exception:
            return False


def _default_verifier():
    return CryptographySignatureVerifier(commercial_config.LICENSE_PUBLIC_KEY_PEM)


def canonical_bytes(payload):
    """Deterministic bytes that get signed/verified: the payload minus its
    `signature`, sorted keys, compact separators, UTF-8."""
    body = {k: v for k, v in payload.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def parse_license(raw):
    """Parse raw license text/bytes/dict into a dict, or None if unusable.
    Never raises."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return dict(raw)
    try:
        if isinstance(raw, bytes):
            if len(raw) > _MAX_LICENSE_BYTES:
                return None
            raw = raw.decode("utf-8")
        if not isinstance(raw, str) or len(raw) > _MAX_LICENSE_BYTES:
            return None
        data = json.loads(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def validate_license(payload, verifier=None, current_major=None, is_production=None):
    """Validate a parsed payload. Returns a LicenseResult; always Core on any
    problem, never raises. Fields are NOT trusted until the signature verifies."""
    if verifier is None:
        verifier = _default_verifier()
    if current_major is None:
        current_major = commercial_config.CURRENT_MAJOR_VERSION
    if is_production is None:
        is_production = commercial_config.IS_PRODUCTION

    if not isinstance(payload, dict):
        return LicenseResult(reason="malformed")

    sig_b64 = payload.get("signature")
    if not sig_b64 or not isinstance(sig_b64, str):
        return LicenseResult(reason="unsigned")
    try:
        signature = base64.b64decode(sig_b64, validate=True)
    except Exception:
        return LicenseResult(reason="bad_signature")
    if not verifier.verify(canonical_bytes(payload), signature):
        return LicenseResult(reason="bad_signature")

    # Signature verified — fields may now be trusted.
    edition = payload.get("edition")
    if edition == CORE:
        return LicenseResult(edition=CORE, valid=False, reason="core")
    if edition not in _KNOWN_EDITIONS:
        return LicenseResult(reason="unsupported_edition")
    try:
        major = int(payload.get("valid_for_major"))
    except (TypeError, ValueError):
        return LicenseResult(reason="wrong_major")
    if major != current_major:
        return LicenseResult(reason="wrong_major")
    if is_production and str(payload.get("env", "")).strip().lower() == "dev":
        return LicenseResult(reason="dev_rejected")
    return LicenseResult(edition=edition, valid=True, reason="ok")


def load_license(path, verifier=None):
    """Read and validate a license file. Missing/unreadable/corrupt → Core."""
    if not path:
        return LicenseResult(reason="missing")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read(_MAX_LICENSE_BYTES + 1)
    except Exception:
        return LicenseResult(reason="corrupt")
    if len(raw) > _MAX_LICENSE_BYTES:
        return LicenseResult(reason="corrupt")
    payload = parse_license(raw)
    if payload is None:
        return LicenseResult(reason="malformed")
    return validate_license(payload, verifier=verifier)


def get_current_edition(path=None, verifier=None):
    """The active edition for display/state. Core unless a valid license loads."""
    if not path:
        return CORE
    result = load_license(path, verifier=verifier)
    return result.edition if result.valid else CORE
