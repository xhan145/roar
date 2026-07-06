"""Offline licensing primitives.

ROAR does not require a license for local dictation. This module is deliberately
pure: it never reads transcript, audio, history, snippets, vocabulary,
clipboard, diagnostics, or the network.
"""
from dataclasses import dataclass
import json

CORE = "Core"
PRO = "Pro"
DEVELOPER = "Developer"
SUPPORTER = "Supporter"


@dataclass(frozen=True)
class License:
    edition: str = CORE
    valid: bool = False
    reason: str = "missing"


BASE_ENTITLEMENTS = {
    "dictation": True,
    "toggle_dictation": True,
    "streaming_preview": True,
    "multilingual_dictation": True,
    "basic_history": True,
    "privacy_controls": True,
    "delete_history_audio": True,
    "basic_vocabulary": True,
    "basic_commands": True,
    "scratch_that": True,
    "advanced_milestones": False,
    "advanced_snippets": False,
    "vocabulary_suggestions": False,
    "history_filters_tags": False,
    "advanced_cleanup": False,
    "settings_import_export": False,
    "code_mode": False,
    "symbol_dictation": False,
    "app_profiles": False,
    "project_vocabulary": False,
    "developer_snippet_packs": False,
}

PRO_ENTITLEMENTS = {
    "advanced_milestones": True,
    "advanced_snippets": True,
    "vocabulary_suggestions": True,
    "history_filters_tags": True,
    "advanced_cleanup": True,
    "settings_import_export": True,
}

DEVELOPER_ENTITLEMENTS = {
    **PRO_ENTITLEMENTS,
    "code_mode": True,
    "symbol_dictation": True,
    "app_profiles": True,
    "project_vocabulary": True,
    "developer_snippet_packs": True,
}


def normalize_edition(value):
    if value in {CORE, PRO, DEVELOPER, SUPPORTER}:
        return value
    return CORE


def entitlements_for(edition):
    edition = normalize_edition(edition)
    ent = dict(BASE_ENTITLEMENTS)
    if edition == PRO:
        ent.update(PRO_ENTITLEMENTS)
    elif edition in {DEVELOPER, SUPPORTER}:
        ent.update(DEVELOPER_ENTITLEMENTS)
    return ent


def load_license(raw):
    if not raw:
        return License()
    try:
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:
        return License(reason="corrupt")
    edition = normalize_edition(data.get("edition"))
    if edition == CORE:
        return License(reason="core")
    # Signature verification can be added here with a production public key.
    # Until then, non-Core payloads are descriptive only and do not unlock.
    return License(edition=CORE, valid=False, reason="unsigned")
