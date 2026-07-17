"""Commercial config migration: old configs keep loading, the new keys get
defaults, migration is idempotent, and grandfathering distinguishes a real
pre-gating install from a fresh one."""
import json

import config as config_mod
import legacy_grant as lg


def _write(tmp_path, data):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def test_old_config_still_loads_and_gets_commercial_defaults(tmp_path):
    """A config written before the commercial keys existed must load untouched
    and simply receive defaults for the new ones."""
    path = _write(tmp_path, {"model": "auto", "language": "en",
                             "history_enabled": True, "snippets": {"sig": "Greg"}})
    cfg = config_mod.load(path)
    assert cfg["model"] == "auto"                    # existing settings intact
    assert cfg["snippets"] == {"sig": "Greg"}        # user data untouched
    assert cfg["license_notifications"] is True      # new default
    assert cfg["purchase_urls"] == {}
    assert cfg["commercial_schema"] == 0             # unstamped -> legacy


def test_unknown_settings_do_not_crash(tmp_path):
    path = _write(tmp_path, {"model": "auto", "from_the_future": {"x": 1}})
    cfg = config_mod.load(path)
    assert cfg["model"] == "auto"


def test_broken_config_falls_back_without_crashing(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{not json", encoding="utf-8")
    cfg = config_mod.load(str(p))
    assert cfg["model"] == config_mod.DEFAULTS["model"]


def test_commercial_schema_is_validated(tmp_path):
    path = _write(tmp_path, {"commercial_schema": "nonsense"})
    assert config_mod.load(path)["commercial_schema"] == 0


def test_purchase_urls_only_accept_https_known_keys(tmp_path):
    path = _write(tmp_path, {"purchase_urls": {
        "pro": "https://buy.example/pro",
        "developer": "http://insecure",       # dropped: not https
        "evil": "https://evil.example",       # dropped: unknown key
    }})
    assert config_mod.load(path)["purchase_urls"] == {"pro": "https://buy.example/pro"}


def test_edition_is_never_a_config_key():
    """The signed license is authoritative — an edition must not be settable."""
    assert "edition" not in config_mod.DEFAULTS
    assert "license_edition" not in config_mod.DEFAULTS


# -- grandfathering: legacy vs fresh --------------------------------------

def test_existing_unstamped_config_is_legacy(tmp_path):
    path = _write(tmp_path, {"model": "auto"})
    cfg = config_mod.load(path)          # merges defaults -> schema present, ==0
    assert lg.is_legacy_install(cfg) is True


def test_fresh_install_is_not_legacy_even_though_defaults_are_unstamped(tmp_path):
    """config.load() creates a config from defaults on a fresh install; the
    caller passes {} because no file existed, so no grant is issued."""
    cfg = config_mod.load(str(tmp_path / "config.json"))   # creates it
    assert cfg["commercial_schema"] == 0
    assert lg.is_legacy_install({}) is False               # what app.py passes


def test_stamped_config_is_not_legacy(tmp_path):
    path = _write(tmp_path, {"model": "auto",
                             lg.SCHEMA_KEY: lg.SCHEMA_VERSION})
    assert lg.is_legacy_install(config_mod.load(path)) is False


def test_migration_is_idempotent(tmp_path):
    path = _write(tmp_path, {"model": "auto"})
    first = config_mod.load(path)
    first[lg.SCHEMA_KEY] = lg.SCHEMA_VERSION
    config_mod.save(first, path)
    second = config_mod.load(path)
    assert lg.is_legacy_install(second) is False
    third = config_mod.load(path)
    assert second == third                               # stable
