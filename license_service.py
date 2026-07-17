"""Application-facing license service — the only module that turns a signed
license FILE into an active edition.

It wraps the pure validator in `license.py` with the small amount of I/O the app
needs: locate, validate, import (atomically), remove, refresh. Every failure
degrades to **Core** and never raises — a license problem must never crash the
app or block dictation.

Privacy: this module reads and writes ONLY the license file. It never touches
transcript, audio, history, snippets, vocabulary, clipboard, window titles, or
the network. Untrusted payload fields are NEVER surfaced — display fields are
read only after the signature verifies.
"""
import os
import tempfile

import license as license_mod
import paths
from entitlements import CORE, SUPPORTER, normalize_edition

# Reject oversized input BEFORE parsing (mirrors license._MAX_LICENSE_BYTES).
MAX_IMPORT_BYTES = 64 * 1024

# In-process cache only. Invalidated by import/remove/refresh; never persisted,
# so a cached edition can't outlive the license that justified it.
_cache = None


def redact_license_id(license_id):
    """`ROAR-PRO-ABCD1234` -> `ROAR…1234`. A full license ID must never reach a
    log, diagnostic, or the UI. Pure."""
    if not isinstance(license_id, str) or not license_id.strip():
        return ""
    s = license_id.strip()
    if len(s) <= 8:
        return "…" + s[-4:]
    return f"{s[:4]}…{s[-4:]}"


def status_copy(edition, valid):
    """Calm, accurate status copy. Pure — no I/O. Never accusatory."""
    edition = normalize_edition(edition)
    if not valid or edition == CORE:
        return ("ROAR Core\n"
                "Private local dictation, free to use.\n"
                "Upgrade for advanced formatting, productivity workflows, or "
                "developer tools.\n"
                "Core dictation and privacy controls remain available without a "
                "license.")
    if edition == SUPPORTER:
        return ("ROAR Supporter\n"
                "Includes all ROAR Developer capabilities. Thank you for "
                "supporting independent development.")
    label = "ROAR " + edition.title()
    return (f"{label} is activated locally.\n"
            "No account is required.\n"
            "Your license is verified on this device without sending dictation "
            "data anywhere.")


_REASON_COPY = {
    "missing": "No license installed. ROAR Core is active.",
    "corrupt": "ROAR could not read this license. Core remains available.",
    "malformed": "This license file is not in a supported format.",
    "unsigned": "ROAR could not verify this license. Core remains available.",
    "bad_signature": "ROAR could not verify this license. Core remains available.",
    "unsupported_edition": "This license is for an edition this build doesn't know.",
    "wrong_major": "This license was created for a different major version of ROAR.",
    "dev_rejected": "ROAR could not verify this license. Core remains available.",
    "core": "This license grants ROAR Core.",
    "too_large": "This license file is too large to be valid.",
}


def reason_copy(reason):
    """Calm one-liner for a validation reason. Pure."""
    return _REASON_COPY.get(reason, "ROAR could not verify this license. "
                                    "Core remains available.")


def _core_status(reason):
    return {
        "edition": CORE,
        "valid": False,
        "reason": reason,
        "license_id": "",
        "customer_name": "",
        "valid_for_major": None,
        "verified_offline": True,
        "message": status_copy(CORE, False),
        "detail": reason_copy(reason),
    }


def _read_raw(path):
    """Read a license file, or None if missing/unreadable/oversized."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read(MAX_IMPORT_BYTES + 1)
    except Exception:
        return None
    if len(raw) > MAX_IMPORT_BYTES:
        return None
    return raw


def get_status(path=None):
    """Full display status for the installed license. Never raises; anything
    wrong resolves to Core."""
    path = path or paths.license_path()
    if not os.path.exists(path):
        return _core_status("missing")
    raw = _read_raw(path)
    if raw is None:
        return _core_status("corrupt")
    payload = license_mod.parse_license(raw)
    if payload is None:
        return _core_status("malformed")
    result = license_mod.validate_license(payload)
    if not result.valid:
        return _core_status(result.reason)
    # Signature verified — only NOW may payload fields be surfaced.
    return {
        "edition": result.edition,
        "valid": True,
        "reason": result.reason,
        "license_id": redact_license_id(payload.get("license_id")),
        "customer_name": str(payload.get("customer_name") or ""),
        "valid_for_major": payload.get("valid_for_major"),
        "verified_offline": True,
        "message": status_copy(result.edition, True),
        "detail": "Verified on this device. No account, no network.",
    }


def get_status_cached(path=None):
    global _cache
    if _cache is None:
        _cache = get_status(path)
    return _cache


def get_active_edition(path=None):
    """The active edition. Core unless a valid license verifies."""
    return get_status_cached(path)["edition"]


def refresh():
    """Drop the in-process cache; the next read revalidates the file."""
    global _cache
    _cache = None


def _coerce_source(source):
    """A pasted license string, or a path to a license file. Returns raw text or
    None when unusable/oversized. Rejects oversize BEFORE parsing."""
    if not isinstance(source, str):
        return None
    s = source.strip()
    if not s:
        return None
    # A path only if it actually exists — otherwise treat the input as pasted
    # text (so a paste that merely looks path-ish is never opened).
    try:
        if len(s) < 4096 and os.path.isfile(s):
            return _read_raw(s)
    except (OSError, ValueError):
        return None
    if len(s.encode("utf-8", "ignore")) > MAX_IMPORT_BYTES:
        return None
    return s


def _atomic_write(path, raw):
    """Write via a temp file in the same directory + os.replace, so the existing
    license is never left half-overwritten."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(raw)
        os.replace(tmp, path)   # atomic on Windows + POSIX
        tmp = None
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def import_license(source, path=None):
    """Validate `source` (pasted text or a file path) and, ONLY if it verifies,
    install it atomically. A failed import leaves any existing valid license
    untouched. Never raises."""
    path = path or paths.license_path()
    raw = _coerce_source(source)
    if raw is None:
        return {"ok": False, "reason": "too_large",
                "message": reason_copy("too_large"), "edition": get_active_edition(path)}
    payload = license_mod.parse_license(raw)
    if payload is None:
        return {"ok": False, "reason": "malformed",
                "message": reason_copy("malformed"), "edition": get_active_edition(path)}
    result = license_mod.validate_license(payload)
    if not result.valid:
        # Existing license (if any) is deliberately left in place.
        return {"ok": False, "reason": result.reason,
                "message": reason_copy(result.reason),
                "edition": get_active_edition(path)}
    try:
        _atomic_write(path, raw)
    except Exception:
        return {"ok": False, "reason": "write_failed",
                "message": "ROAR could not save this license.",
                "edition": get_active_edition(path)}
    refresh()
    return {"ok": True, "reason": "ok", "edition": result.edition,
            "message": status_copy(result.edition, True)}


def remove_license(path=None):
    """Delete the license and return to Core. Removes ONLY the license file —
    never any user content (history, audio, snippets, vocabulary, settings)."""
    path = path or paths.license_path()
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        return {"ok": False, "reason": "remove_failed",
                "message": "ROAR could not remove the license.",
                "edition": get_active_edition(path)}
    refresh()
    return {"ok": True, "reason": "removed", "edition": CORE,
            "message": status_copy(CORE, False)}
