"""Pure entitlement primitives — the single source of truth for editions and
the feature vocabulary. NOT wired into any runtime gate (the shipped app is
"everything on"; this is policy only — see docs/FEATURE_MATRIX.md).

Policy invariants:
- Core (free, and the fallback for missing/corrupt/unknown editions) always
  includes dictation, privacy, and every local-data control.
- Privacy/data features are allowed for EVERY edition, no exceptions.
- Unknown features default to ALLOWED (locking new work by accident is worse
  than the reverse) but emit a warning, and `KNOWN_FEATURES` + a guard test
  force explicit registration before any real gate could ever ship.
- Nothing here reads transcripts, audio, history, snippets, vocabulary,
  clipboard, or diagnostics, and nothing touches the network.
"""

import logging

_log = logging.getLogger("roar.entitlements")

CORE, PRO, DEVELOPER, SUPPORTER = "core", "pro", "developer", "supporter"
EDITIONS = (CORE, PRO, DEVELOPER, SUPPORTER)

# always allowed, for every edition, forever — gating any of these would break
# the product promise
ALWAYS_FREE = frozenset({
    "dictation.push_to_talk", "dictation.hands_free", "dictation.streaming",
    "dictation.multilingual", "dictation.scratch_that", "commands.basic",
    "history.basic", "history.delete", "audio.delete", "privacy.controls",
    "vocabulary.basic", "diagnostics.safe", "updates.manual_check",
})

_PRO = frozenset({
    "milestones.advanced", "formatting.smart", "snippets.packs",
    "snippets.variables_extended", "vocabulary.suggestions",
    "history.filters", "cleanup.advanced", "settings.import_export",
})

_DEVELOPER = frozenset({
    "profiles.apps", "profiles.per_app_language", "code.mode",
    "code.symbols", "vocabulary.project", "snippets.developer_packs",
    "files.tagging",
})

_BY_EDITION = {
    CORE: frozenset(),
    PRO: _PRO,
    DEVELOPER: _PRO | _DEVELOPER,
    SUPPORTER: _PRO | _DEVELOPER,  # supporters get everything
}

_PAID = _PRO | _DEVELOPER

# every feature the policy knows about. A guard test asserts nothing in the app
# references a feature outside this set, so gates can never silently miss one.
KNOWN_FEATURES = ALWAYS_FREE | _PAID


def normalize_edition(edition):
    """Unknown/missing/corrupt edition ALWAYS degrades to core — never raises."""
    if isinstance(edition, str) and edition.strip().lower() in _BY_EDITION:
        return edition.strip().lower()
    return CORE


def allowed(feature, edition=None):
    """Pure decision: may `edition` use `feature`? Free features are free for
    everyone; unknown features default to allowed (and warn — see module doc)."""
    if feature in ALWAYS_FREE:
        return True
    if feature not in _PAID:
        _log.warning("unregistered entitlement feature: %s", feature)
        return True
    return feature in _BY_EDITION[normalize_edition(edition)]


# `can_use` is the name used by callers that read as a gate check; same logic.
can_use = allowed


def features_for_edition(edition=None):
    """The full set of features available to `edition` (free + its paid tier)."""
    return set(ALWAYS_FREE | _BY_EDITION[normalize_edition(edition)])


def requires_upgrade(feature, edition=None):
    """True only for a KNOWN paid feature this edition doesn't have. Unknown or
    always-free features never require an upgrade."""
    return feature in _PAID and not allowed(feature, edition)


def minimum_edition_for(feature):
    """Lowest edition that unlocks `feature`; None for unknown features."""
    if feature in ALWAYS_FREE:
        return CORE
    if feature in _PRO:
        return PRO
    if feature in _DEVELOPER:
        return DEVELOPER
    return None
