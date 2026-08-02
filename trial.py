"""14-day Full-Feature Trial — pure state primitives.

This module is policy and arithmetic only: it never touches the filesystem,
registry, network, or clock on its own. Timestamps are timezone-aware UTC and
every function takes `now` so tests inject fake clocks (no real waiting).
Persistence, protection, and rollback bookkeeping live in trial_store.py.

Product invariants encoded here:
- The trial lasts exactly ``timedelta(days=14)`` from the explicit start.
- Countdown is whole days (floor); under 24 hours reads "Less than one day".
- Clock rollback beyond a small tolerance is *detected*, never punished by
  destroying state — the caller keeps Core available and offers a retry.
- A valid paid licence always outranks the trial; expiry resolves to core.
- The record carries only trial bookkeeping — never transcripts, audio,
  history, clipboard, vocabulary, or window titles.
"""

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

SCHEMA_VERSION = 1
TRIAL_DURATION = timedelta(days=14)
CLOCK_TOLERANCE = timedelta(minutes=5)
TRIAL_EDITION = "trial"

# explicit status vocabulary — the UI never interprets raw timestamps
NOT_STARTED = "not_started"
ACTIVE = "active"
EXPIRED = "expired"
INVALID = "invalid"
CLOCK_ROLLBACK_DETECTED = "clock_rollback_detected"
LICENSED = "licensed"

_RECORD_KEYS = {
    "schema_version", "trial_id", "started_at_utc", "expires_at_utc",
    "last_seen_at_utc", "expired_notice_seen",
}
# the immutable core covered by the integrity signature; last_seen and the
# notice flag mutate during normal operation and stay outside it
_SIGNED_FIELDS = ("schema_version", "trial_id", "started_at_utc",
                  "expires_at_utc")


@dataclass(frozen=True)
class TrialStatus:
    state: str
    started_at: object  # datetime | None
    expires_at: object  # datetime | None
    seconds_remaining: int
    days_remaining: int
    expired_notice_seen: bool


def utc_now():
    return datetime.now(timezone.utc)


def parse_utc(value):
    """ISO-8601 → aware UTC datetime, or None. Accepts a trailing Z."""
    if not isinstance(value, str) or not value:
        return None
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def format_utc(dt):
    return dt.astimezone(timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def new_record(now=None, trial_id=None):
    """A fresh, unsigned trial record starting at `now` for exactly 14 days."""
    started = (now or utc_now()).astimezone(timezone.utc)
    return {
        "schema_version": SCHEMA_VERSION,
        "trial_id": trial_id or uuid.uuid4().hex,
        "started_at_utc": format_utc(started),
        "expires_at_utc": format_utc(started + TRIAL_DURATION),
        "last_seen_at_utc": format_utc(started),
        "expired_notice_seen": False,
    }


def validate_record(record):
    """The record if structurally sound, else None. Never raises."""
    if not isinstance(record, dict):
        return None
    if record.get("schema_version") != SCHEMA_VERSION:
        return None
    if not isinstance(record.get("trial_id"), str) or not record["trial_id"]:
        return None
    started = parse_utc(record.get("started_at_utc"))
    expires = parse_utc(record.get("expires_at_utc"))
    last_seen = parse_utc(record.get("last_seen_at_utc"))
    if started is None or expires is None or last_seen is None:
        return None
    if expires <= started:
        return None
    if not isinstance(record.get("expired_notice_seen"), bool):
        return None
    return record


def canonical_bytes(record):
    subset = {k: record.get(k) for k in _SIGNED_FIELDS}
    return json.dumps(subset, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sign_record(record, key):
    """Return the record with a local integrity signature attached."""
    digest = hmac.new(key, canonical_bytes(record), hashlib.sha256).hexdigest()
    signed = dict(record)
    signed["signature"] = digest
    return signed


def verify_record(record, key):
    if not isinstance(record, dict):
        return False
    provided = record.get("signature")
    if not isinstance(provided, str):
        return False
    expected = hmac.new(key, canonical_bytes(record),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)


def status_of(record, now=None):
    """Structured status for a record (which may be None or damaged)."""
    if record is None:
        return TrialStatus(NOT_STARTED, None, None, 0, 0, False)
    valid = validate_record({k: v for k, v in record.items()
                             if k in _RECORD_KEYS})
    if valid is None:
        return TrialStatus(INVALID, None, None, 0, 0, False)
    moment = (now or utc_now()).astimezone(timezone.utc)
    started = parse_utc(valid["started_at_utc"])
    expires = parse_utc(valid["expires_at_utc"])
    last_seen = parse_utc(valid["last_seen_at_utc"])
    notice_seen = bool(valid.get("expired_notice_seen"))
    if moment < last_seen - CLOCK_TOLERANCE:
        return TrialStatus(CLOCK_ROLLBACK_DETECTED, started, expires,
                           0, 0, notice_seen)
    remaining = int((expires - moment).total_seconds())
    if remaining > 0:
        return TrialStatus(ACTIVE, started, expires, remaining,
                           remaining // 86400, notice_seen)
    return TrialStatus(EXPIRED, started, expires, 0, 0, notice_seen)


def remaining_label(status):
    """Whole-day countdown copy. Empty when there is nothing to count."""
    if status.state != ACTIVE:
        return ""
    if status.seconds_remaining < 86400:
        return "Less than one day remaining"
    days = status.days_remaining
    return f"{days} day{'s' if days != 1 else ''} remaining"


def resolve_effective_edition(license_edition=None, license_valid=False,
                              trial_status=None):
    """The single place licence state and trial state combine.

    Priority: valid paid licence > active trial > core. A licence always
    outranks the trial — even ROAR Pro, although the trial temporarily
    granted more. Rollback, expiry, invalid state: core.
    """
    if license_valid and license_edition in ("pro", "developer", "supporter"):
        return license_edition
    if trial_status is not None and trial_status.state == ACTIVE:
        return TRIAL_EDITION
    return "core"


def display_state(status, license_valid=False):
    """What the trial UI should present as the headline state."""
    if license_valid:
        return LICENSED
    return status.state
