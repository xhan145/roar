"""The one place the app asks: may THIS install use THIS feature?

Combines the two impure inputs — the signed license (edition) and the one-time
grandfathering grant (feature IDs) — and defers the actual decision to the pure
`entitlements` module. Runtime code should call `can()` / `requires_upgrade()`
here rather than comparing edition strings anywhere else.

Everything degrades to Core-with-grants on any error: a licensing problem must
never break dictation. Reads only the license + grant files — never transcript,
audio, history, snippets, vocabulary, clipboard, or the network.
"""
import entitlements
import legacy_grant
import license_service

_grants = None


def grants():
    """Grandfathered feature IDs for this install (cached in-process)."""
    global _grants
    if _grants is None:
        try:
            _grants = legacy_grant.load_grants()
        except Exception:
            _grants = frozenset()
    return _grants


def edition():
    """Active edition from the signed license; Core unless one verifies."""
    try:
        return license_service.get_active_edition()
    except Exception:
        return entitlements.CORE


def refresh():
    """Re-read both inputs on the next call (after import/remove)."""
    global _grants
    _grants = None
    license_service.refresh()


def can(feature):
    """May this install use `feature`? Never raises; on any error the answer is
    whatever Core + grants allow, so a licensing fault can't lock the app."""
    try:
        return entitlements.allowed(feature, edition(), grants())
    except Exception:
        return entitlements.allowed(feature, entitlements.CORE, frozenset())


def requires_upgrade(feature):
    """True only for a known paid feature this install doesn't have."""
    try:
        return entitlements.requires_upgrade(feature, edition(), grants())
    except Exception:
        return False


def minimum_edition_for(feature):
    return entitlements.minimum_edition_for(feature)
