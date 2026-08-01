"""In-app fulfilment boundary — this module NEVER signs, by design.

Automated delivery EXISTS, but not here: it runs as a separate Vercel service
(`fulfillment-service/`, see docs/VERCEL_FULFILLMENT.md) that verifies a
PayPal payment, signs with the SUBORDINATE fulfilment key held only in that
service's environment, and emails the buyer. The FOUNDER key stays offline in
the owner's ~/.roar-signing/, and the desktop app itself contains no signing
capability at all — this module refuses so that no in-app code path can ever
pretend otherwise.

The manual fallback (refunds, service outages, old builds):
    1. Verify the payment in the processor's dashboard.
    2. Run scripts/issue_license.py to sign a licence offline.
    3. Send the resulting file to the buyer.

The deployed service upholds the same rules this docstring always demanded:
payment confirmed with the processor (webhook signature over raw bytes),
edition validated, idempotent per capture id, delivery to the buyer's own
email, no voice/transcript/usage data anywhere near it.

Pure validation only: no file access, no network, and nothing that reads the
user's transcripts, audio, history, clipboard, vocabulary, or usage insights.
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
        "The desktop app never signs licences. Automated delivery runs on the "
        "separate Vercel service (see docs/VERCEL_FULFILLMENT.md); the manual "
        "path is scripts/issue_license.py, then send the file to the buyer.")
