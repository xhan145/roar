"""In-app upgrade copy must match canonical pricing and never nag or discount."""

import commercial_config as cc
import upgrade_prompts as up


def test_copy_quotes_the_canonical_price():
    for edition in cc.PAID_EDITIONS:
        body = up._COPY[edition]["body"]
        assert f"${cc.PRICING[edition]['price_usd']} once" in body, edition


def test_developer_copy_says_developer_not_developer_pack():
    assert "Developer Pack" not in up._COPY["developer"]["title"]
    assert up._COPY["developer"]["title"] == "Unlock ROAR Developer"


def test_terms_line_is_the_agreed_promise():
    for edition in cc.PAID_EDITIONS:
        assert "No subscription" in up._COPY[edition]["body"], edition


def test_no_fake_urgency_or_discounts():
    banned = ("was $", "50% off", "limited time", "expires", "hurry",
              "only today", "trial")
    blob = " ".join(c["title"] + c["body"] for c in up._COPY.values()).lower()
    for phrase in banned:
        assert phrase not in blob, phrase


def test_price_lookup_covers_every_paid_edition():
    # The old inline lookup mapped only pro/developer, so a Supporter-gated
    # feature would have shown no price at all.
    for edition in cc.PAID_EDITIONS:
        assert up._price_for_edition(edition) == cc.PRICING[edition]["price_usd"]


def test_price_lookup_returns_none_for_free_and_unknown():
    assert up._price_for_edition("core") is None
    assert up._price_for_edition("bogus") is None
    assert up._price_for_edition(None) is None


def test_prompt_carries_a_price_for_a_real_gated_feature():
    prompt = up.prompt_for("code.mode")
    assert prompt["required_edition"] == "developer"
    assert prompt["price_usd"] == cc.PRICING["developer"]["price_usd"]
    assert prompt["required_edition_name"] == "ROAR Developer"


def test_prompt_is_none_for_free_features():
    assert up.prompt_for("privacy.controls") is None
    assert up.prompt_for("history.delete") is None
