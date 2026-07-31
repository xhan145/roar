"""Flow settings bridge: rule CRUD round-trips config.json with validation."""

import config as config_mod
from settings_ui import SettingsAPI


def _api(tmp_path):
    return SettingsAPI(config_path=str(tmp_path / "config.json"))


def good_rule(**over):
    r = {"phrase": "open terminal", "action": "open_app",
         "params": {"target": "wt.exe"}, "enabled": True,
         "trusted": False, "consume": True}
    r.update(over)
    return r


def test_flow_get_shape(tmp_path):
    state = _api(tmp_path).flow_get()
    assert state["rules"] == []
    assert state["notes_path"] == ""
    assert "open_app" in state["actions"]
    assert state["scripted_actions"] == ["run_script", "webhook"]
    assert isinstance(state["can_rules"], bool)


def test_add_persists_and_lists(tmp_path):
    api = _api(tmp_path)
    out = api.flow_add_rule(good_rule())
    assert out["ok"] is True
    saved = config_mod.load(str(tmp_path / "config.json"))["automation_rules"]
    assert saved[0]["phrase"] == "open terminal"
    assert saved[0]["trusted"] is False


def test_add_rejects_bad_rules(tmp_path):
    api = _api(tmp_path)
    assert "error" in api.flow_add_rule(good_rule(phrase=""))
    assert "error" in api.flow_add_rule(good_rule(action="format_disk"))
    api.flow_add_rule(good_rule())
    assert "error" in api.flow_add_rule(good_rule())  # duplicate phrase


def test_delete_and_toggle(tmp_path):
    api = _api(tmp_path)
    api.flow_add_rule(good_rule())
    assert api.flow_toggle_rule(0, False)["rules"][0]["enabled"] is False
    assert api.flow_delete_rule(0)["ok"] is True
    assert api.flow_get()["rules"] == []
    assert "error" in api.flow_delete_rule(5)


def test_notes_path_round_trip(tmp_path):
    api = _api(tmp_path)
    api.flow_set_notes_path("D:/notes/roar.md")
    assert api.flow_get()["notes_path"] == "D:/notes/roar.md"


def test_trusted_flag_survives_round_trip(tmp_path):
    api = _api(tmp_path)
    api.flow_add_rule(good_rule(phrase="deploy now", action="run_script",
                                params={"path": "C:/deploy.ps1"},
                                trusted=True))
    saved = api.flow_get()["rules"][0]
    assert saved["trusted"] is True and saved["action"] == "run_script"
