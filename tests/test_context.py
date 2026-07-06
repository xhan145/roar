import context


def test_builtin_profiles_resolve():
    code = context.profile_for("Code.exe")          # case-insensitive
    assert code == {"capitalize": False, "cleanup": False}
    assert context.profile_for("powershell.exe") == code
    assert context.profile_for("cursor.exe") == code

    casual = {"capitalize": False, "cleanup": True, "discourse_fillers": False}
    assert context.profile_for("whatsapp.exe") == casual
    assert context.profile_for("discord.exe") == casual
    assert context.profile_for("slack.exe") == casual
    assert context.profile_for("spotify.exe") == casual
    assert context.profile_for("teams.exe") == casual  # back-compat for old chat map

    formal = {"capitalize": True, "cleanup": True, "discourse_fillers": True}
    assert context.profile_for("outlook.exe") == formal
    assert context.profile_for("winword.exe") == formal


def test_chat_alias_is_casual():
    assert context.profile_for("chat.exe", user_map={"chat.exe": "chat"}) == {
        "capitalize": False,
        "cleanup": True,
        "discourse_fillers": False,
    }


def test_ableton_prefix_match():
    casual = {"capitalize": False, "cleanup": True, "discourse_fillers": False}
    assert context.profile_for("Ableton Live 12 Suite.exe") == casual
    assert context.profile_for("ableton live 9 intro.exe") == casual


def test_unknown_and_empty_use_user_settings():
    assert context.profile_for("notepad.exe") == {}
    assert context.profile_for("") == {}
    assert context.profile_for(None) == {}


def test_user_map_overrides_builtins():
    assert context.profile_for("code.exe", user_map={"code.exe": "formal"}) == {
        "capitalize": True,
        "cleanup": True,
        "discourse_fillers": True,
    }
    assert context.profile_for("notepad.exe", user_map={"notepad.exe": "casual"}) == {
        "capitalize": False,
        "cleanup": True,
        "discourse_fillers": False,
    }


def test_browser_title_routing_is_browser_scoped():
    casual = {"capitalize": False, "cleanup": True, "discourse_fillers": False}
    code = {"capitalize": False, "cleanup": False}
    assert context.profile_for("chrome.exe", "WhatsApp - chat") == casual
    assert context.profile_for("chrome.exe", "GitHub - repo") == code
    assert context.profile_for("notepad.exe", "WhatsApp notes") == {}


def test_title_user_override_is_browser_scoped_and_wins():
    formal = {"capitalize": True, "cleanup": True, "discourse_fillers": True}
    user_map = {"title:facebook plan": "formal"}
    assert context.profile_for("chrome.exe", "Facebook Plan", user_map) == formal
    assert context.profile_for("notepad.exe", "Facebook Plan", user_map) == {}


def test_returned_dict_is_a_copy():
    a = context.profile_for("code.exe")
    a["capitalize"] = True
    assert context.profile_for("code.exe")["capitalize"] is False
