"""ROAR Flow action executors — the ONLY place a matched rule becomes a side
effect.

`execute(desc, deps)` dispatches one action descriptor (from automations.match)
against a deps object that carries the actual capability functions:

    deps.can(feature) -> bool          entitlement check (access.can)
    deps.notify(msg)                   user-visible toast
    deps.log(msg)                      diagnostic line
    deps.open_app(target)              launch an application
    deps.open_url(url)                 open in the default browser
    deps.hotkey(keys)                  send a key chord ("ctrl+shift+t")
    deps.snippet(name)                 inject a named snippet's body
    deps.speak(text)                   Read Aloud
    deps.copy(text)                    clipboard
    deps.run_script(path)              TRUSTED ONLY
    deps.webhook(url, payload)         TRUSTED ONLY

Tests pass fakes; app.py passes the real thing (build_deps). The trust gate
lives HERE, on the execution side, so no alternative code path can reach a
scripted action without passing it:

  run_script / webhook fire only when the rule is marked trusted AND the
  edition allows automations.scripted — and the user sees a toast naming the
  rule before it fires. Everything else is freely usable.

Failures are contained: execute never raises, dictation always completes.
"""

import automations

SCRIPTED_FEATURE = "automations.scripted"


def execute(desc, deps) -> str:
    """Run one matched action. Returns 'ok', 'skipped: …', or 'error: …'."""
    action = desc.get("action")
    params = desc.get("params") or {}
    phrase = desc.get("phrase", "")
    try:
        if action in automations.SCRIPTED_ACTIONS:
            if not desc.get("trusted"):
                deps.notify(f"Flow: '{phrase}' is not marked trusted — "
                            f"{action} was not run.")
                return "skipped: untrusted"
            if not deps.can(SCRIPTED_FEATURE):
                deps.notify("Script and webhook actions are part of "
                            "ROAR Developer.")
                return "skipped: not entitled"
            deps.notify(f"Flow: '{phrase}' → {action}")

        if action == "open_app":
            deps.open_app(params["target"])
        elif action == "open_url":
            url = params.get("url", "")
            if not url.startswith(("http://", "https://")):
                deps.log(f"flow: refused non-http url {url!r}")
                return "skipped: bad url scheme"
            deps.open_url(url)
        elif action == "hotkey":
            deps.hotkey(params["keys"])
        elif action == "snippet":
            deps.snippet(params["name"])
        elif action == "speak":
            deps.speak(params["text"])
        elif action == "copy":
            deps.copy(params.get("text") or desc.get("utterance", ""))
        elif action == "run_script":
            deps.run_script(params["path"])
        elif action == "osc":
            deps.osc(params["target"],
                     params.get("value") or desc.get("utterance", ""))
        elif action == "webhook":
            import datetime
            payload = {"text": desc.get("utterance", ""),
                       "rule": phrase,
                       "ts": datetime.datetime.now().isoformat(
                           timespec="seconds")}
            deps.webhook(params["url"], payload)
        else:
            deps.log(f"flow: unknown action {action!r} skipped")
            return f"skipped: unknown action {action!r}"
        return "ok"
    except Exception as exc:  # noqa: BLE001 — dictation must never break
        try:
            deps.log(f"flow action {action} failed: {exc}")
        except Exception:
            pass
        return f"error: {exc}"


def build_deps(app):
    """Real capability functions wired to the running tray app. Kept here so
    app.py stays a thin composition layer."""
    import subprocess
    import threading
    import webbrowser
    from types import SimpleNamespace

    import access
    import injector

    def open_app(target):
        try:
            subprocess.Popen(target)
        except (FileNotFoundError, OSError):
            import os
            os.startfile(target)  # shortcuts, documents, registered names

    def open_url(url):
        webbrowser.open(url)

    def hotkey(keys):
        injector.send_hotkey(keys)

    def snippet(name):
        body = (app.cfg.get("snippets") or {}).get(name)
        if not body:
            raise KeyError(f"no snippet named {name!r}")
        injector.inject_text(body, paste_fallback=app.cfg["paste_fallback"])

    def speak(text):
        app.tts_service.speak(text, source="flow_rule", remember=False)

    def copy(text):
        import pyperclip
        pyperclip.copy(text)

    def run_script(path):
        subprocess.Popen([path], shell=False,
                         creationflags=getattr(subprocess,
                                               "CREATE_NEW_CONSOLE", 0))

    def osc_send(target, value):
        """One UDP datagram to a show-control box on the local network.
        Trusted-rule gated like every scripted action; fire-and-forget."""
        import socket

        import osc as osc_mod
        host, port, address = osc_mod.parse_target(target)
        message = osc_mod.encode_message(address, [value] if value else [])
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.sendto(message, (host, port))
        finally:
            sock.close()

    def webhook(url, payload):
        def _post():
            import json
            import urllib.request
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(req, timeout=3).close()
            except Exception as exc:  # fire-and-forget: log only
                app.log(f"flow webhook failed: {exc}")
        threading.Thread(target=_post, daemon=True).start()

    return SimpleNamespace(
        can=access.can, notify=app.notify, log=app.log,
        open_app=open_app, open_url=open_url, hotkey=hotkey,
        snippet=snippet, speak=speak, copy=copy,
        run_script=run_script, webhook=webhook, osc=osc_send)
