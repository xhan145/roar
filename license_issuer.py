"""Pure license-payload construction for ROAR's signing tools.

This module is the mirror of `license.py`: `license.py` VERIFIES a signed
payload inside the app (public key only); this builds the payload that the
offline signing CLIs in `scripts/` then sign with the PRIVATE key.

It is deliberately pure — no keys, no network, no file I/O, no randomness and
no clock. The caller supplies the random token and the issue date, so every
function here is deterministic and unit-testable. The scripts inject
`secrets`/`datetime` at their edges.

A production payload never carries `env: "dev"` (that marker exists only so a
production verifier can reject test licenses — see `license.validate_license`).
Fields here become exactly the signed bytes, so they must match what
`license.canonical_bytes` re-serialises on the verifying side.
"""
import re

from entitlements import PRO, DEVELOPER, SUPPORTER, normalize_edition

# Editions a customer can actually buy. Core is free (no license) and Supporter
# is a patron tier with Developer's capabilities — all three are sellable.
SELLABLE_EDITIONS = (PRO, DEVELOPER, SUPPORTER)

# License-id token: uppercase base32-ish, unambiguous alphabet (no 0/O/1/I).
_TOKEN_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_TOKEN_RE = re.compile(r"^[" + _TOKEN_ALPHABET + r"]+$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def token_from_bytes(raw, length=8):
    """Map arbitrary random bytes to a `length`-char token over the
    unambiguous alphabet. Deterministic given `raw`; the caller owns the
    randomness (e.g. `secrets.token_bytes`)."""
    if length <= 0:
        raise ValueError("length must be positive")
    if not raw:
        raise ValueError("need at least one byte of randomness")
    n = len(_TOKEN_ALPHABET)
    return "".join(_TOKEN_ALPHABET[b % n] for b in bytes(raw)[:length]).ljust(
        length, _TOKEN_ALPHABET[0])


def new_license_id(edition, token):
    """`ROAR-PRO-XXXXXXXX` style id. `token` must be a non-empty string over the
    unambiguous alphabet (use `token_from_bytes`)."""
    ed = normalize_edition(edition)
    if ed not in SELLABLE_EDITIONS:
        raise ValueError(f"not a sellable edition: {edition!r}")
    if not token or not _TOKEN_RE.match(token):
        raise ValueError(f"token must be non-empty over {_TOKEN_ALPHABET!r}")
    return f"ROAR-{ed.upper()}-{token}"


def build_payload(edition, name, license_id, issued_at,
                  valid_for_major=1, email_hash=None):
    """Build the unsigned production payload dict.

    Raises ValueError on anything a signer should refuse to stamp (bad edition,
    malformed id/date, non-int major). The returned dict has NO `signature` and
    NO `env` — a script adds the signature; production licenses never carry
    `env: "dev"`.
    """
    ed = normalize_edition(edition)
    if ed not in SELLABLE_EDITIONS:
        raise ValueError(
            f"edition must be one of {SELLABLE_EDITIONS}, got {edition!r}")
    if not license_id or not str(license_id).startswith(f"ROAR-{ed.upper()}-"):
        raise ValueError(
            f"license_id {license_id!r} must start with ROAR-{ed.upper()}-")
    if not _ISO_DATE_RE.match(str(issued_at)):
        raise ValueError(f"issued_at must be YYYY-MM-DD, got {issued_at!r}")
    try:
        major = int(valid_for_major)
    except (TypeError, ValueError):
        raise ValueError(f"valid_for_major must be an int, got {valid_for_major!r}")
    if major < 1:
        raise ValueError("valid_for_major must be >= 1")

    return {
        "license_id": str(license_id),
        "name": str(name or ""),
        "email_hash": email_hash if email_hash else None,
        "edition": ed,
        "issued_at": str(issued_at),
        "valid_for_major": major,
    }
