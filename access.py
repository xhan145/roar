"""The one place the app asks: may THIS install use THIS feature?

Combines the two impure inputs — the signed license (edition) and the one-time
grandfathering grant (feature IDs) — and defers the actual decision to the pure
`entitlements` module. Runtime code should call `can()` / `requires_upgrade()`
here rather than comparing edition strings anywhere else.

Everything degrades to Core-with-grants on any error: a licensing problem must
never break dictation. Reads only the license + grant files — never transcript,
audio, history, snippets, vocabulary, clipboard, or the network.
"""
import os
import time

import entitlements
import legacy_grant
import license_service
import paths
import trial
import trial_store

_grants = None
_trial_service = None
_trial_cache = None          # (monotonic_fetched, TrialStatus)
_TRIAL_CACHE_SECONDS = 30.0  # gate checks run on hot paths; reads are cached
_license_stamp = None        # (mtime_ns, size) of the licence file when cached


def grants():
    """Grandfathered feature IDs for this install (cached in-process)."""
    global _grants
    if _grants is None:
        try:
            _grants = legacy_grant.load_grants()
        except Exception:
            _grants = frozenset()
    return _grants


def _license_file_stamp():
    """Cheap fingerprint of the licence file: (mtime_ns, size), or None."""
    try:
        st = os.stat(paths.license_path())
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def edition():
    """Active edition from the signed license; Core unless one verifies.

    Settings runs in a SEPARATE process, so a licence imported there is
    invisible to this process's cache. Watch the file itself: when it appears,
    changes, or is removed, drop the cached status so a purchase takes effect
    immediately — no restart, even mid-session after a trial ended.
    """
    global _license_stamp
    try:
        stamp = _license_file_stamp()
        if stamp != _license_stamp:
            _license_stamp = stamp
            license_service.refresh()
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


def mark_trial_notice_seen():
    """Remember (in the trial record) that the one-time ended notice was
    shown. Never raises — a bookkeeping fault must not disturb the app."""
    global _trial_cache
    try:
        service = _trial_service or trial_store.TrialService()
        service.mark_expired_notice_seen()
    except Exception:
        pass
    _trial_cache = None


def minimum_edition_for(feature):
    return entitlements.minimum_edition_for(feature)
