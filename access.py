"""The one place the app asks: may THIS install use THIS feature?

Combines the two impure inputs — the signed license (edition) and the one-time
grandfathering grant (feature IDs) — and defers the actual decision to the pure
`entitlements` module. Runtime code should call `can()` / `requires_upgrade()`
here rather than comparing edition strings anywhere else.

Everything degrades to Core-with-grants on any error: a licensing problem must
never break dictation. Reads only the license + grant files — never transcript,
audio, history, snippets, vocabulary, clipboard, or the network.
"""
import time

import entitlements
import legacy_grant
import license_service
import trial
import trial_store

_grants = None
_trial_service = None
_trial_cache = None          # (monotonic_fetched, TrialStatus)
_TRIAL_CACHE_SECONDS = 30.0  # gate checks run on hot paths; reads are cached


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


def trial_status(now=None):
    """Cached Full-Feature Trial status. Any storage fault reads as
    not_started — a trial problem must never break dictation."""
    global _trial_service, _trial_cache
    tick = time.monotonic()
    if _trial_cache is not None and tick - _trial_cache[0] < _TRIAL_CACHE_SECONDS:
        return _trial_cache[1]
    try:
        if _trial_service is None:
            _trial_service = trial_store.TrialService()
        status = _trial_service.status(now=now)
    except Exception:
        status = trial.TrialStatus(trial.NOT_STARTED, None, None, 0, 0, False)
    _trial_cache = (tick, status)
    return status


def effective_edition():
    """The single runtime answer to "what edition is this install?":
    valid paid licence > active trial > core."""
    lic = edition()
    try:
        return trial.resolve_effective_edition(
            license_edition=lic,
            license_valid=lic in ("pro", "developer", "supporter"),
            trial_status=trial_status())
    except Exception:
        return lic


def refresh():
    """Re-read all inputs on the next call (after import/remove/trial start)."""
    global _grants, _trial_cache
    _grants = None
    _trial_cache = None
    license_service.refresh()


def can(feature):
    """May this install use `feature`? Never raises; on any error the answer is
    whatever Core + grants allow, so a licensing fault can't lock the app."""
    try:
        return entitlements.allowed(feature, effective_edition(), grants())
    except Exception:
        return entitlements.allowed(feature, entitlements.CORE, frozenset())


def requires_upgrade(feature):
    """True only for a known paid feature this install doesn't have."""
    try:
        return entitlements.requires_upgrade(feature, effective_edition(),
                                             grants())
    except Exception:
        return False


def minimum_edition_for(feature):
    return entitlements.minimum_edition_for(feature)
