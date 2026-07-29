"""The public pricing page must agree with commercial_config — no drift."""

import pathlib
import re

import commercial_config as cc

SITE = pathlib.Path("site/index.html")


def _html():
    return SITE.read_text(encoding="utf-8")


def _card_blocks():
    """Each pricing card's own chunk of HTML, keyed by nothing — just a list."""
    return re.split(r'<div class="tier', _html())[1:]


def _block_for(display_name):
    return next(b for b in _card_blocks() if display_name in b)


def test_all_four_editions_are_named():
    html = _html()
    for entry in cc.PRICING.values():
        assert entry["display_name"] in html, entry["display_name"]


def test_canonical_price_labels_render():
    html = _html()
    assert "$19" in html and "$29" in html and "$49" in html


def test_no_stale_supporter_price():
    # $99 was the OLD Supporter price and must be gone entirely.
    assert "$99" not in _html()


def test_price_belongs_to_the_right_card():
    """$29 and $49 are still valid prices — but only for the right editions,
    so check each card's own block rather than banning the numbers."""
    assert "$19" in _block_for("ROAR Pro")
    assert "$29" in _block_for("ROAR Developer")
    assert "$49" in _block_for("ROAR Supporter")
    core = _block_for("ROAR Core")
    assert "Free" in core
    assert "$" not in core.split("<ul>")[0]


def test_core_card_leads_to_the_download_not_a_purchase():
    core = _block_for("ROAR Core")
    assert "data-edition" not in core
    assert "Download ROAR" in core


def test_both_recommendation_labels_present():
    assert "Best for most people" in _block_for("ROAR Pro")
    assert "Best for developers" in _block_for("ROAR Developer")


def test_supporter_card_claims_no_exclusive_features():
    supporter = _block_for("ROAR Supporter")
    assert "Everything in Developer" in supporter
    for overclaim in ("lifetime support", "priority support", "tax",
                      "donation", "charit"):
        assert overclaim not in supporter.lower(), overclaim


def test_trust_copy_present():
    html = _html()
    for phrase in ("One payment. No subscription.", "No account required",
                   "No cloud transcription", "No telemetry",
                   "Offline license verification",
                   "Your purchased version keeps working",
                   "Includes all v1.x updates",
                   "Optional paid major upgrades may happen later"):
        assert phrase in html, phrase


def test_every_paid_card_states_v1x_updates():
    for edition in ("ROAR Pro", "ROAR Developer", "ROAR Supporter"):
        assert "All v1.x updates included" in _block_for(edition), edition


def test_no_stripe_secrets_in_the_page():
    html = _html()
    for forbidden in ("sk_live", "sk_test", "whsec_", "STRIPE_SECRET"):
        assert forbidden not in html, forbidden
