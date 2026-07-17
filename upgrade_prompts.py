"""Upgrade-prompt copy + the ONE reusable upgrade descriptor.

Pure strings and pure lookups: this module never blocks anything itself. Callers
ask `prompt_for(feature)` when the user has intentionally reached for a locked
paid feature, and render the result. Rules the copy honours:
  * shown only on intentional paid-feature interaction — never at startup, never
    during dictation, never blocking Settings/privacy/deletion
  * no countdown, no fake scarcity, no "trial expired", no subscription wording
  * Core is never described as a trial, and no one's access ever "expires"

No I/O, no UI imports, no network.
"""
import commercial_config as cc
import entitlements

_COPY = {
    "pro": {
        "title": "Unlock ROAR Pro",
        "body": f"${cc.PRO_PRICE_USD} once. No subscription. No account. "
                "No cloud transcription.",
        "url": cc.PURCHASE_URL_PRO,
    },
    "developer": {
        "title": "Unlock Developer Pack",
        "body": f"${cc.DEVELOPER_PRICE_USD} once. Code-aware dictation, symbol "
                "dictation, and app profiles.",
        "url": cc.PURCHASE_URL_DEVELOPER,
    },
    "supporter": {
        "title": "Support ROAR",
        "body": f"${cc.SUPPORTER_PRICE_USD} once. Includes Developer features and "
                "supports continued development.",
        "url": cc.PURCHASE_URL_SUPPORTER,
    },
}


def copy_for(edition):
    """Copy dict for an upgrade target ('pro'/'developer'/'supporter'), or None."""
    return _COPY.get(str(edition).strip().lower())


def all_copy():
    return {k: dict(v) for k, v in _COPY.items()}


# Human-facing name + one line of "what this actually does", per gated feature.
# Only registered paid features appear here (a guard test keeps them in sync).
FEATURE_COPY = {
    "code.mode": ("Code Mode",
                  "Dictate into editors and terminals verbatim, with code-aware "
                  "spacing."),
    "code.symbols": ("Programming symbols",
                     "Speak brackets, operators, and punctuation as symbols."),
    "profiles.apps": ("Per-app profiles",
                      "Different formatting per application — verbatim in your "
                      "editor, polished in email."),
    "profiles.per_app_language": ("Per-app language",
                                  "Pick a dictation language per application."),
    "snippets.packs": ("ROAR Snippets",
                       "Expand a spoken keyword into stored text."),
    "snippets.variables_extended": ("Snippet variables",
                                    "Insert {date}, {time}, and {clipboard} into "
                                    "snippets."),
    "formatting.smart": ("Smart formatting",
                         "Context-aware formatting that adapts to where you're "
                         "typing."),
    "cleanup.advanced": ("Advanced cleanup",
                         "Remove discourse fillers like \"you know\" and \"I "
                         "mean\"."),
    "vocabulary.suggestions": ("Vocabulary suggestions",
                               "Automatically bias recognition toward the words "
                               "you actually use."),
    "milestones.advanced": ("Advanced milestones",
                            "Private, offline word-count milestones."),
    "history.filters": ("History filters",
                        "Search and filter your local dictation history."),
    "settings.import_export": ("Settings export & import",
                               "Move your snippets and settings between machines."),
    "vocabulary.project": ("Project vocabulary",
                           "Per-project term lists."),
    "snippets.developer_packs": ("Developer snippet packs",
                                 "Shareable snippet packs for code workflows."),
    "files.tagging": ("Developer tagging",
                      "Tag dictations by file or project."),
}


def prompt_for(feature):
    """The ONE upgrade descriptor: what a locked feature is, which edition
    unlocks it, and where to buy. Returns None for free/unknown features, so a
    caller can never accidentally show an upgrade for something that isn't
    actually gated. Pure."""
    required = entitlements.minimum_edition_for(feature)
    if required in (None, entitlements.CORE):
        return None
    copy = _COPY.get(required)
    if copy is None:
        return None
    name, description = FEATURE_COPY.get(feature, (feature, ""))
    return {
        "feature": feature,
        "feature_name": name,
        "description": description,
        "required_edition": required,
        "required_edition_name": "ROAR " + required.title(),
        "headline": f"{name} is included with ROAR {required.title()}.",
        "price_usd": {"pro": cc.PRO_PRICE_USD,
                      "developer": cc.DEVELOPER_PRICE_USD}.get(required),
        "terms": "No subscription. No account required. No cloud transcription.",
        "purchase_url": copy["url"],
        "buttons": [f"Buy ROAR {required.title()}", "Enter License", "Not Now"],
    }
