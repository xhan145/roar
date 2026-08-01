"""Checkout is Stripe-Payment-Link based: no server, no secrets, safe fallback."""

import pathlib
import re

import commercial_config as cc

SITE = pathlib.Path("site/index.html")


def _html():
    return SITE.read_text(encoding="utf-8")


def test_buttons_carry_edition_ids_not_prices():
    html = _html()
    for edition in cc.PAID_EDITIONS:
        assert f'data-edition="{edition}"' in html, edition
    # A price must never be the thing handed to a payment processor.
    assert "data-price=" not in html
    assert "data-amount=" not in html


def test_core_is_not_purchasable_from_the_page():
    assert 'data-edition="core"' not in _html()


def test_purchase_config_is_keyed_by_every_paid_edition():
    block = _html().split("purchase:")[1].split("}")[0]
    for edition in cc.PAID_EDITIONS:
        assert f"{edition}:" in block, edition


def test_checkout_readiness_is_derived_from_the_links():
    html = _html()
    assert "checkoutReady" in html
    assert "checkoutReady = true" not in html


def test_paid_buttons_never_dead_link_to_hash():
    """With no Payment Link configured a button must explain itself and open
    the pre-order email, not silently do nothing."""
    html = _html()
    assert "Checkout coming soon" in html
    assert "mailto:" in html


def test_no_secrets_or_server_config_in_the_page():
    html = _html()
    for forbidden in ("sk_live", "sk_test", "whsec_", "STRIPE_SECRET_KEY",
                      "STRIPE_WEBHOOK_SECRET"):
        assert forbidden not in html, forbidden


# The ONLY hosts a buy button may ever point at. Payment links are public by
# design, but a typo'd or attacker-supplied host would silently take payments —
# widening this list is a deliberate decision, never a drive-by edit.
TRUSTED_CHECKOUT_PREFIXES = (
    "https://buy.stripe.com/",
    "https://www.paypal.com/ncp/payment/",   # PayPal no-code payment links
    "https://paypal.me/",                    # PayPal.Me (prefilled amount)
)


def test_payment_links_if_present_are_trusted_processor_urls():
    block = _html().split("purchase:")[1].split("}")[0]
    for url in re.findall(r'"(\w+://[^"]*)"', block):
        assert url.startswith(TRUSTED_CHECKOUT_PREFIXES), url
