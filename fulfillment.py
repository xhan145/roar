"""Boundary for future automated licence delivery — deliberately NOT implemented.

ROAR sells through Stripe Payment Links on a STATIC site, so there is no server
to receive a webhook and no secure home for the Ed25519 signing key (it lives
only in the owner's ~/.roar-signing/ directory, never in this repository and
never in a shipped build). Signing here would mean putting that key somewhere it
does not belong, so this module refuses instead of pretending.

Today's real path is manual and honest:
    1. Stripe notifies the owner that a payment completed.
    2. The owner confirms it in the Stripe Dashboard.
    3. The owner runs scripts/issue_license.py to sign a licence offline.
    4. The owner sends the resulting file to the buyer.

A production implementation MUST:
    1. Confirm the payment really completed by asking Stripe directly — never
       trust the browser, a redirect, or a query parameter.
    2. Validate the purchased edition against PAID_EDITIONS.
    3. Be idempotent on the Stripe Checkout Session id, so one sale can never
       produce two licences.
    4. Sign with the existing offline licence format, on a secure server only.
    5. Deliver over a channel the buyer controls.
    6. Store no voice, transcript, history, or application-usage data.
    7. Follow a written refund and revocation policy.

Pure validation only: no file access, no network, and nothing that reads the
user's transcripts, audio, history, clipboard, vocabulary, or usage insights.
See docs/STRIPE_SETUP.md and docs/WEBSITE_IMPLEMENTATION.md.
"""

from dataclasses import dataclass

import commercial_config as cc


class FulfillmentUnavailable(RuntimeError):
    """Automated delivery is not configured; use the manual path."""


@dataclass(frozen=True)
class LicenseDeliveryResult:
    """What a real implementation would return once one exists."""

    delivered: bool
    edition: str
    stripe_session_id: str
    reason: str


def issue_license(edition, stripe_session_id, customer_email=None,
                  major_version=cc.CURRENT_MAJOR_VERSION):
    """Validate a fulfilment call, then refuse to sign.

    Raises ValueError for a malformed call, and FulfillmentUnavailable for a
    well-formed one — a valid call failing loudly is the entire point. It never
    returns a LicenseDeliveryResult claiming success.
    """
    if edition not in cc.PAID_EDITIONS:
        raise ValueError(f"{edition!r} is not a purchasable edition")
    if not isinstance(stripe_session_id, str) or not stripe_session_id.strip():
        raise ValueError("a Stripe Checkout Session id is required")
    if customer_email is not None and not isinstance(customer_email, str):
        raise ValueError("customer_email must be a string when given")
    try:
        version = int(major_version)
    except (TypeError, ValueError):
        raise ValueError(f"unsupported major version {major_version!r}") from None
    if version != cc.CURRENT_MAJOR_VERSION:
        raise ValueError(f"unsupported major version {major_version!r}")
    raise FulfillmentUnavailable(
        "Automated licence delivery is not available: the site is static and "
        "the signing key is intentionally offline. Issue the licence manually "
        "with scripts/issue_license.py, then send it to the buyer.")
