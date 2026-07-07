import ast
import pathlib

import commercial_config as cc


def test_prices_are_the_agreed_one_time_amounts():
    assert cc.PRO_PRICE_USD == 29
    assert cc.DEVELOPER_PRICE_USD == 49
    assert cc.SUPPORTER_PRICE_USD == 99


def test_defaults():
    assert cc.DEFAULT_EDITION == "core"
    assert cc.CURRENT_MAJOR_VERSION == 1
    assert cc.IS_PRODUCTION is False


def test_purchase_urls_are_https():
    for url in (cc.PURCHASE_URL_PRO, cc.PURCHASE_URL_DEVELOPER, cc.PURCHASE_URL_SUPPORTER):
        assert url.startswith("https://")


def test_only_public_key_shipped():
    assert "BEGIN PUBLIC KEY" in cc.LICENSE_PUBLIC_KEY_PEM
    assert "PRIVATE KEY" not in cc.LICENSE_PUBLIC_KEY_PEM


def test_no_user_data_or_network_imports():
    tree = ast.parse(pathlib.Path("commercial_config.py").read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert not (mods & {"history", "audio", "transcriber", "recorder",
                        "clipboard", "socket", "urllib", "requests"})
