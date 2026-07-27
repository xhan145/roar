"""Teach-ROAR wiring: settings bridge, config round-trip, hotword mirroring."""
import app as app_mod
import config as config_mod
from settings_ui import SettingsAPI


def _api(tmp_path):
    return SettingsAPI(config_path=str(tmp_path / "config.json"))


# --- bridge: add / list / remove -------------------------------------------

def test_add_lists_and_removes_a_correction(tmp_path):
    api = _api(tmp_path)
    assert api.corrections_get()["pairs"] == []
    assert api.correction_add("pie plot", "PyPlot")["ok"] is True
    assert api.corrections_get()["pairs"] == [{"heard": "pie plot",
                                               "meant": "PyPlot"}]
    assert api.correction_remove("Pie Plot")["ok"] is True   # case-insensitive
    assert api.corrections_get()["pairs"] == []


def test_add_rejects_duplicate_and_self_mapping(tmp_path):
    api = _api(tmp_path)
    api.correction_add("pie plot", "PyPlot")
    assert "error" in api.correction_add("PIE PLOT", "Matplotlib")
    assert "error" in api.correction_add("same", "same")


def test_correction_persists_to_config(tmp_path):
    path = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=path)
    api.correction_add("cuber netes", "Kubernetes")
    assert config_mod.load(path)["corrections"] == {"cuber netes": "Kubernetes"}


def test_removal_survives_reload(tmp_path):
    # corrections are REPLACED (not merged) on load, so a removal must stick
    path = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=path)
    api.correction_add("pie plot", "PyPlot")
    api.correction_remove("pie plot")
    assert config_mod.load(path)["corrections"] == {}


# --- the "prevent" half: intended word becomes a hotword --------------------

def test_add_mirrors_the_intended_word_into_vocabulary(tmp_path):
    path = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=path)
    api.correction_add("pie plot", "PyPlot")
    assert "PyPlot" in config_mod.load(path)["custom_vocabulary"]


def test_config_change_triggers_hotword_rebuild():
    old = dict(config_mod.DEFAULTS)
    new = dict(config_mod.DEFAULTS)
    new["corrections"] = {"pie plot": "PyPlot"}
    assert ("rebuild_hotwords", None) in app_mod.diff_config(old, new)


# --- learning from a history edit ------------------------------------------

def test_learn_proposes_a_pair_without_saving(tmp_path):
    path = str(tmp_path / "config.json")
    api = SettingsAPI(config_path=path)
    out = api.correction_learn("I use pie plot daily", "I use PyPlot daily")
    assert out["ok"] is True and out["heard"] == "pie plot"
    assert out["meant"] == "PyPlot"
    # proposing must NOT persist anything — the user confirms first
    assert config_mod.load(path)["corrections"] == {}


def test_learn_refuses_a_wholesale_rewrite(tmp_path):
    api = _api(tmp_path)
    assert "error" in api.correction_learn("one two three four",
                                           "a completely different sentence")


def test_learn_refuses_when_already_taught(tmp_path):
    api = _api(tmp_path)
    api.correction_add("pie plot", "PyPlot")
    assert "error" in api.correction_learn("use pie plot", "use PyPlot")


# --- corrections are free (never gated) ------------------------------------

def test_corrections_are_not_an_entitlement_gated_feature():
    import entitlements
    # accuracy for your own voice must never be a paid tier
    assert entitlements.allowed("corrections", edition="core") is True
