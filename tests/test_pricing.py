"""Canonical pricing lives in ONE place; everything else derives from it."""

import commercial_config as cc


def test_canonical_prices():
    assert cc.PRICING["core"]["price_usd"] == 0
    assert cc.PRICING["pro"]["price_usd"] == 19
    assert cc.PRICING["developer"]["price_usd"] == 29
    assert cc.PRICING["supporter"]["price_usd"] == 49


def test_price_labels():
    assert cc.PRICING["core"]["price_label"] == "Free"
    assert cc.PRICING["pro"]["price_label"] == "$19 once"
    assert cc.PRICING["developer"]["price_label"] == "$29 once"
    assert cc.PRICING["supporter"]["price_label"] == "$49 once"


def test_display_names_use_developer_not_developer_pack():
    assert cc.PRICING["developer"]["display_name"] == "ROAR Developer"
    assert all(p["display_name"].startswith("ROAR ") for p in cc.PRICING.values())


def test_legacy_constants_derive_from_pricing():
    # upgrade_prompts.py consumes these; they must never drift.
    assert cc.PRO_PRICE_USD == cc.PRICING["pro"]["price_usd"]
    assert cc.DEVELOPER_PRICE_USD == cc.PRICING["developer"]["price_usd"]
    assert cc.SUPPORTER_PRICE_USD == cc.PRICING["supporter"]["price_usd"]


def test_paid_editions_excludes_core():
    assert cc.PAID_EDITIONS == ("pro", "developer", "supporter")
    assert "core" not in cc.PAID_EDITIONS
    assert cc.PRICING["core"]["purchase_url"] is None


def test_purchase_urls_derive_from_pricing():
    assert cc.PURCHASE_URL_PRO == cc.PRICING["pro"]["purchase_url"]
    assert cc.PURCHASE_URL_DEVELOPER == cc.PRICING["developer"]["purchase_url"]
    assert cc.PURCHASE_URL_SUPPORTER == cc.PRICING["supporter"]["purchase_url"]


def test_purchase_urls_are_our_own_page_not_a_processor():
    for edition in cc.PAID_EDITIONS:
        url = cc.PRICING[edition]["purchase_url"]
        assert url.startswith("https://xhan145.github.io/roar/"), edition
        assert "stripe" not in url.lower(), edition
