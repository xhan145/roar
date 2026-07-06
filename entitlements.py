"""Pure entitlement primitives — NOT wired into any runtime gate yet.

Commercial-readiness scaffolding only. Policy invariants:
- Core (free, and the fallback for missing/corrupt/unknown editions) always
  includes dictation, privacy, and every local-data control.
- Privacy/data features are allowed for EVERY edition, no exceptions.
- Nothing here reads transcripts, audio, history, snippets, vocabulary,
  clipboard, or diagnostics, and nothing touches the network.

See docs/LICENSING.md for the offline-license architecture this plugs into.
"""

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


def normalize_edition(edition):
    """Unknown/missing/corrupt edition ALWAYS degrades to core — never raises."""
    if isinstance(edition, str) and edition.strip().lower() in _BY_EDITION:
        return edition.strip().lower()
    return CORE


def allowed(feature, edition=None):
    """Pure decision: may `edition` use `feature`? Free features are free for
    everyone; unknown features default to allowed (deny-listing new work by
    accident would be worse than the reverse)."""
    if feature in ALWAYS_FREE:
        return True
    paid = _PRO | _DEVELOPER
    if feature not in paid:
        return True
    return feature in _BY_EDITION[normalize_edition(edition)]
