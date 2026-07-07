"""Upgrade-prompt copy — pure strings, NOT wired to block any feature.

ROAR ships "everything on"; this copy exists only for an intentional paid-feature
click if runtime gates are ever enabled. No subscription/account/cloud wording.
"""
import commercial_config as cc

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
