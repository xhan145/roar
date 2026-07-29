"""Docs and code must agree on price — drift here is a customer-facing lie."""

import pathlib

import commercial_config as cc

CUSTOMER_FACING = [
    pathlib.Path("README.md"),
    pathlib.Path("ROADMAP-14DAY.md"),
    pathlib.Path("docs/PRICING.md"),
    pathlib.Path("docs/FEATURE_MATRIX.md"),
    pathlib.Path("docs/MONETIZATION.md"),
    pathlib.Path("docs/FAQ.md"),
    pathlib.Path("site/index.html"),
]


def _texts():
    return {p: p.read_text(encoding="utf-8") for p in CUSTOMER_FACING if p.is_file()}


def test_no_stale_99_dollar_supporter_anywhere():
    for path, text in _texts().items():
        assert "$99" not in text, path


def test_no_customer_facing_developer_pack():
    for path, text in _texts().items():
        assert "Developer Pack" not in text, path


def test_pricing_doc_states_all_four_canonical_prices():
    text = pathlib.Path("docs/PRICING.md").read_text(encoding="utf-8")
    assert "Free" in text
    for edition in cc.PAID_EDITIONS:
        assert f"${cc.PRICING[edition]['price_usd']}" in text, edition


def test_pricing_doc_pairs_each_price_with_its_own_edition():
    text = pathlib.Path("docs/PRICING.md").read_text(encoding="utf-8")
    for edition in cc.PAID_EDITIONS:
        name = cc.PRICING[edition]["display_name"]
        price = cc.PRICING[edition]["price_usd"]
        assert f"{name} is ${price} once." in text, edition


def test_promise_lines_present_in_pricing_doc():
    text = pathlib.Path("docs/PRICING.md").read_text(encoding="utf-8")
    assert "No subscription" in text
    assert "No account required" in text
    assert "all v1.x updates" in text.lower()


def test_stripe_setup_doc_warns_payment_is_not_delivery():
    text = pathlib.Path("docs/STRIPE_SETUP.md").read_text(encoding="utf-8")
    assert "must not automatically imply" in text
    assert "one-time" in text.lower()
    assert "buy.stripe.com" in text


def test_website_implementation_doc_records_the_server_contract():
    text = pathlib.Path("docs/WEBSITE_IMPLEMENTATION.md").read_text(
        encoding="utf-8")
    assert "/api/checkout" in text
    assert "STRIPE_WEBHOOK_SECRET" in text
    assert "idempotent" in text.lower()


def test_docs_never_leak_a_secret_key():
    # Assembled at runtime so this file doesn't itself trip the repo-wide
    # private-key scanner in tests/test_commercial_packaging.py.
    pem_marker = "BEGIN " + "PRIVATE KEY"
    paths = list(CUSTOMER_FACING) + [
        pathlib.Path("docs/STRIPE_SETUP.md"),
        pathlib.Path("docs/WEBSITE_IMPLEMENTATION.md"),
    ]
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        assert "sk_live" not in text, path
        assert "sk_test" not in text, path
        assert pem_marker not in text, path
