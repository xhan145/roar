import ipc_commands


def test_send_only_allowed_commands(tmp_path):
    p = str(tmp_path / "command.json")
    assert ipc_commands.send_command("toggle", p) is True
    assert ipc_commands.send_command("scratch", p) is True
    assert ipc_commands.send_command("rm -rf /", p) is False
    assert ipc_commands.send_command("evil", p) is False
    assert ipc_commands.send_command("", p) is False


def test_take_only_fires_once_per_command(tmp_path):
    p = str(tmp_path / "command.json")
    ipc_commands.send_command("toggle", p)
    cmd, ts = ipc_commands.take_command(0, p)
    assert cmd == "toggle" and ts > 0
    # same file, last_ts == ts -> no re-fire
    cmd2, ts2 = ipc_commands.take_command(ts, p)
    assert cmd2 is None and ts2 == ts


def test_missing_or_corrupt_is_safe(tmp_path):
    assert ipc_commands.take_command(0, str(tmp_path / "nope.json")) == (None, 0)
    bad = tmp_path / "command.json"
    bad.write_text("{not json", encoding="utf-8")
    assert ipc_commands.take_command(0, str(bad)) == (None, 0)


def test_atomic_no_temp_left(tmp_path):
    p = str(tmp_path / "command.json")
    ipc_commands.send_command("toggle", p)
    assert not (tmp_path / "command.json.tmp").exists()


def test_settings_send_command_respects_flag(tmp_path, monkeypatch):
    import config as config_mod
    import paths
    import settings_ui
    api = settings_ui.SettingsAPI(config_path=str(tmp_path / "config.json"))

    # flag OFF -> disabled, nothing written
    monkeypatch.setattr(config_mod, "load", lambda p=None: {"dashboard_controls": False})
    assert api.send_command("toggle") == {"ok": False, "reason": "disabled"}

    # flag ON -> writes to a temp command path
    cmdfile = tmp_path / "command.json"
    monkeypatch.setattr(config_mod, "load", lambda p=None: {"dashboard_controls": True})
    monkeypatch.setattr(paths, "command_path", lambda: str(cmdfile))
    assert api.send_command("toggle")["ok"] is True
    assert cmdfile.exists()

    # unknown command rejected even with the flag on
    assert api.send_command("evil")["ok"] is False
