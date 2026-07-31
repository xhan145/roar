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
        "body": f"${cc.PRICING['pro']['price_usd']} once. No subscription. "
                "No account. No cloud transcription.",
        "url": cc.PURCHASE_URL_PRO,
    },
    "developer": {
        "title": "Unlock ROAR Developer",
        "body": f"${cc.PRICING['developer']['price_usd']} once. Code-aware "
                "dictation, symbol dictation, and app profiles. "
                "No subscription.",
        "url": cc.PURCHASE_URL_DEVELOPER,
    },
    "supporter": {
        "title": "Support ROAR",
        "body": f"${cc.PRICING['supporter']['price_usd']} once. Everything in "
                "ROAR Developer, and it supports continued independent "
                "development. No subscription.",
        "url": cc.PURCHASE_URL_SUPPORTER,
    },
}


def _price_for_edition(edition):
    """Canonical price for an edition id, or None when it isn't purchasable."""
    entry = cc.PRICING.get(edition)
    if not entry or entry["price_usd"] == 0:
        return None
    return entry["price_usd"]


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
    "automations.rules": ("Flow automations",
                          "Say a trigger phrase and ROAR acts — open an app, "
                          "press a hotkey, speak a reply."),
    "routing.multi": ("Multi-output routing",
                      "Send one dictation to extra places: clipboard, a "
                      "running notes file, or spoken back aloud."),
    "automations.scripted": ("Scripted actions",
                             "Let trusted Flow rules run a script, call a "
                             "webhook, or send OSC to show-control gear."),
    "capture.system_audio": ("Meeting capture",
                             "Transcribe what your PC is playing — calls and "
                             "meetings — into local history, live."),
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
        "price_usd": _price_for_edition(required),
        "terms": "No subscription. No account required. No cloud transcription.",
        "purchase_url": copy["url"],
        "buttons": [f"Buy ROAR {required.title()}", "Enter License", "Not Now"],
    }
