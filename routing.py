"""ROAR Flow output routing — one utterance, many destinations.

Pure core: which outputs are active, the delivery loop with per-output failure
isolation, the notes-file line format, and the "roar route …" voice-command
parser. The actual handlers (inject/clipboard/notes/speak) are supplied by
app.py; this module never imports the runtime.

Injection is always active and always first — multi-output is strictly additive
so dictation can never get quieter than it is today. Extra routes are
session-only state (they reset to off when the app exits); persistence of the
booleans is the caller's choice and the spec says: don't.
"""

import re

# Fixed order. inject first (it's the product), speak last (it's the slowest).
OUTPUTS = ("inject", "clipboard", "notes", "speak")

_TOGGLEABLE = ("clipboard", "notes", "speak")

_ROUTE_RE = re.compile(
    r"^\s*roar\s+routes?\s+(clipboard|notes|speak)\s+(on|off)\s*[.!?]?\s*$",
    re.IGNORECASE)
_ALL_OFF_RE = re.compile(r"^\s*roar\s+routes?\s+off\s*[.!?]?\s*$",
                         re.IGNORECASE)


def active_outputs(cfg) -> tuple:
    """The ordered outputs to deliver to, from session config booleans."""
    active = ["inject"]
    for name in _TOGGLEABLE:
        if cfg.get(f"route_{name}", False):
            active.append(name)
    return tuple(sorted(active, key=OUTPUTS.index))


def deliver(text, outputs, handlers, log) -> dict:
    """Call each output's handler in order. One failure never stops the rest —
    a locked notes file must not cost the user their injection. Returns a
    per-output status dict ('ok' or 'error: …')."""
    status = {}
    for name in outputs:
        handler = handlers.get(name)
        if handler is None:
            status[name] = "error: no handler"
            log(f"route {name}: no handler registered")
            continue
        try:
            handler(text)
            status[name] = "ok"
        except Exception as exc:  # noqa: BLE001 — isolation is the contract
            status[name] = f"error: {exc}"
            log(f"route {name} failed: {exc}")
    return status


def notes_line(text, now) -> str:
    """Append-only running-notes format: timestamped, one line per utterance."""
    return f"[{now:%Y-%m-%d %H:%M}] {text}\n"


def append_notes(path, line):
    """Append a line to the notes file, creating parent directories. Raises on
    failure — the caller (deliver) isolates it."""
    import pathlib
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="") as fh:
        fh.write(line)


def parse_route_command(text):
    """Parse a spoken routing toggle. Returns (output, on) for
    'roar route <name> on/off', 'all_off' for 'roar routes off', else None.
    Must match the WHOLE utterance — routing commands are never embedded in
    dictation."""
    if not isinstance(text, str):
        return None
    if _ALL_OFF_RE.match(text):
        return "all_off"
    m = _ROUTE_RE.match(text)
    if not m:
        return None
    return (m.group(1).lower(), m.group(2).lower() == "on")
