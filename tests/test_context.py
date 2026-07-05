import context


def test_code_editors_are_verbatim():
    p = context.profile_for("Code.exe")          # case-insensitive
    assert p["capitalize"] is False and p["cleanup"] is False
    assert context.profile_for("powershell.exe")["capitalize"] is False


def test_chat_apps_force_filler_removal():
    p = context.profile_for("slack.exe")
    assert p["discourse_fillers"] is True
    assert "capitalize" not in p                  # capitalize stays user default


def test_unknown_and_empty_use_user_settings():
    assert context.profile_for("notepad.exe") == {}
    assert context.profile_for("") == {}
    assert context.profile_for(None) == {}


def test_returned_dict_is_a_copy():
    a = context.profile_for("code.exe")
    a["capitalize"] = True
    assert context.profile_for("code.exe")["capitalize"] is False
