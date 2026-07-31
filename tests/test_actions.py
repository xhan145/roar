"""Action executors: dispatch, trust gating, failure isolation."""

import pytest

import actions


class FakeDeps:
    """Records every call; entitlement and trust are controlled per-test."""

    def __init__(self, entitled=True):
        self.calls = []
        self.notices = []
        self.logs = []
        self._entitled = entitled

    def can(self, feature):
        self.calls.append(("can", feature))
        return self._entitled

    def notify(self, msg):
        self.notices.append(msg)

    def log(self, msg):
        self.logs.append(msg)

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name, *args))
        return record


def desc(action="open_app", params=None, trusted=False, phrase="do it",
         utterance="do it"):
    if params is None:
        params = {"target": "wt.exe"}
    return {"action": action, "params": params, "trusted": trusted,
            "phrase": phrase, "utterance": utterance}


# -- plain actions dispatch -------------------------------------------------

def test_open_app_dispatches():
    deps = FakeDeps()
    assert actions.execute(desc(), deps) == "ok"
    assert ("open_app", "wt.exe") in deps.calls


def test_open_url_dispatches():
    deps = FakeDeps()
    d = desc("open_url", {"url": "https://example.com"})
    assert actions.execute(d, deps) == "ok"
    assert ("open_url", "https://example.com") in deps.calls


def test_open_url_refuses_bad_scheme_at_runtime_too():
    deps = FakeDeps()
    d = desc("open_url", {"url": "file:///etc/passwd"})
    assert actions.execute(d, deps).startswith("skipped")
    assert not any(c[0] == "open_url" for c in deps.calls)


def test_hotkey_snippet_speak_dispatch():
    deps = FakeDeps()
    assert actions.execute(desc("hotkey", {"keys": "ctrl+shift+t"}), deps) == "ok"
    assert actions.execute(desc("snippet", {"name": "sig"}), deps) == "ok"
    assert actions.execute(desc("speak", {"text": "hello"}), deps) == "ok"
    assert ("hotkey", "ctrl+shift+t") in deps.calls
    assert ("snippet", "sig") in deps.calls
    assert ("speak", "hello") in deps.calls


def test_copy_defaults_to_the_utterance():
    deps = FakeDeps()
    d = desc("copy", {}, utterance="remember this line")
    assert actions.execute(d, deps) == "ok"
    assert ("copy", "remember this line") in deps.calls


def test_copy_uses_param_text_when_given():
    deps = FakeDeps()
    assert actions.execute(desc("copy", {"text": "fixed"}), deps) == "ok"
    assert ("copy", "fixed") in deps.calls


# -- trust gate -------------------------------------------------------------

@pytest.mark.parametrize("action,params", [
    ("run_script", {"path": "C:/x.ps1"}),
    ("webhook", {"url": "https://example.com/hook"}),
])
def test_scripted_actions_need_trusted_flag(action, params):
    deps = FakeDeps(entitled=True)
    result = actions.execute(desc(action, params, trusted=False), deps)
    assert result.startswith("skipped")
    assert not any(c[0] in ("run_script", "webhook") for c in deps.calls)
    assert deps.notices  # user is told why nothing happened


@pytest.mark.parametrize("action,params", [
    ("run_script", {"path": "C:/x.ps1"}),
    ("webhook", {"url": "https://example.com/hook"}),
])
def test_scripted_actions_need_entitlement(action, params):
    deps = FakeDeps(entitled=False)
    result = actions.execute(desc(action, params, trusted=True), deps)
    assert result.startswith("skipped")
    assert not any(c[0] in ("run_script", "webhook") for c in deps.calls)


def test_trusted_and_entitled_scripted_action_fires_with_a_toast():
    deps = FakeDeps(entitled=True)
    d = desc("run_script", {"path": "C:/x.ps1"}, trusted=True, phrase="deploy")
    assert actions.execute(d, deps) == "ok"
    assert ("run_script", "C:/x.ps1") in deps.calls
    assert any("deploy" in n for n in deps.notices)  # names the rule


def test_webhook_payload_contains_only_the_agreed_fields():
    deps = FakeDeps(entitled=True)
    d = desc("webhook", {"url": "https://example.com/h"}, trusted=True,
             utterance="hello world")
    assert actions.execute(d, deps) == "ok"
    call = next(c for c in deps.calls if c[0] == "webhook")
    _, url, payload = call
    assert url == "https://example.com/h"
    assert set(payload) == {"text", "rule", "ts"}
    assert payload["text"] == "hello world"


# -- isolation --------------------------------------------------------------

def test_executor_failure_is_reported_never_raised():
    class Exploding(FakeDeps):
        def __getattr__(self, name):
            def boom(*a):
                raise RuntimeError("nope")
            return boom

    result = actions.execute(desc(), Exploding())
    assert result.startswith("error")


def test_unknown_action_is_skipped():
    deps = FakeDeps()
    assert actions.execute(desc("format_disk", {}), deps).startswith("skipped")
