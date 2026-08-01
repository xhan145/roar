"""Standalone live transcript window — a compact, always-available view of
everything ROAR has transcribed (dictations + meeting capture), live.

Runs as its own lightweight process (`app.py --transcript`), exactly like the
Settings window: NO ML imports here or in anything this module imports — the
window must open in well under a second. It reads the history DB read-only
(WAL sqlite; the tray process writes, we only SELECT) and re-polls every 1.5 s
from the page.

Capture rows are the ones recorded by listen mode (model == "listen"); the
page tags them and can filter either source. Deleting/editing history stays in
Settings — this window is a monitor, not a manager.
"""

import ctypes
import os
import threading

import config as config_mod
import history as history_mod
import paths

TRANSCRIPT_MUTEX = "ROAR_TRANSCRIPT_WINDOW"
LISTEN_TAG = "listen"          # keep in sync with listen_mode.MODEL_TAG
_WINDOW = None


class TranscriptAPI:
    """Bridge for transcript.html. Read-only over history + one window verb."""

    def __init__(self, config_path=None):
        self.config_path = config_path

    @property
    def _history(self):
        # a fresh handle per call keeps this process stateless and WAL-friendly
        return history_mod.History()

    def state(self):
        cfg = config_mod.load(self.config_path)
        return {"history_enabled": bool(cfg.get("history_enabled", True))}

    def transcript_list(self, source="all", query=None, limit=200):
        """Newest-first rows shaped for the page. source: all|dictation|capture."""
        rows = self._history.list(limit=int(limit), query=query or None)
        out = []
        for r in rows:
            is_capture = (r["model"] == LISTEN_TAG)
            if source == "dictation" and is_capture:
                continue
            if source == "capture" and not is_capture:
                continue
            out.append({"id": r["id"], "ts_utc": r["ts_utc"], "text": r["text"],
                        "capture": is_capture})
        return {"rows": out}

    def transcript_export(self, source="all", query=None):
        """Current view -> timestamped text file in Documents (local only)."""
        import datetime
        rows = self.transcript_list(source=source, query=query,
                                    limit=5000)["rows"]
        if not rows:
            return {"error": "Nothing to export."}
        stamp = datetime.datetime.now()
        out = os.path.join(os.path.expanduser("~"), "Documents",
                           f"ROAR Transcript {stamp:%Y-%m-%d %H%M}.txt")
        lines = []
        for r in rows:
            ts = datetime.datetime.fromtimestamp(r["ts_utc"])
            tag = " [capture]" if r["capture"] else ""
            lines.append(f"[{ts:%Y-%m-%d %H:%M}]{tag} {r['text']}")
        with open(out, "w", encoding="utf-8", newline="") as fh:
            fh.write("\n".join(lines) + "\n")
        return {"ok": True, "path": out, "count": len(rows)}

    def set_on_top(self, on):
        try:
            _WINDOW.on_top = bool(on)
            return {"ok": True, "on_top": bool(on)}
        except Exception as exc:
            return {"error": str(exc)}


def run_transcript(smoke=False):
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, TRANSCRIPT_MUTEX)
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        print("ROAR: transcript window already open", flush=True)
        return 0
    try:
        import webview
    except Exception as e:
        print(f"ROAR: transcript UI unavailable ({e})", flush=True)
        return 1
    html = paths.resource_path("transcript.html")
    if not os.path.exists(html):
        print(f"ROAR: transcript.html missing at {html}", flush=True)
        return 1
    global _WINDOW
    api = TranscriptAPI()
    window = webview.create_window(
        "ROAR Live Transcript", url=html, js_api=api,
        width=430, height=580, min_size=(340, 380),
        background_color="#08080D")
    _WINDOW = window
    print("ROAR: transcript window ready", flush=True)

    page_loaded = threading.Event()
    window.events.loaded += page_loaded.set

    if smoke:
        def probe_and_close():
            try:
                page_loaded.wait(timeout=30)
                import time as _time
                _time.sleep(1.0)
                for attempt in range(3):
                    try:
                        ok = window.evaluate_js(
                            "(document.getElementById('tr-list') && "
                            "document.getElementById('tr-search') && "
                            "document.getElementById('tr-ontop') && "
                            "document.getElementById('tr-export') && "
                            "document.querySelectorAll('.tr-chip').length===3)"
                            " ? 1 : 0")
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        _time.sleep(1.5)
                print(f"ROAR: transcript probe ui={ok}", flush=True)
            finally:
                window.destroy()
        threading.Thread(target=probe_and_close, daemon=True).start()

    webview.start()
    print("ROAR: transcript closed", flush=True)
    return 0
