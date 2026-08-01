# Standalone transcript window + per-app routing profiles — Design

**Date:** 2026-08-01 · **Status:** approved (autonomous build) · **Repo:** `xhan145/roar`

## Decisions (user-approved)

1. **Transcript window shows everything, filterable** — dictations and
   meeting-capture lines interleaved chronologically, with All / Dictation /
   Capture filter chips (capture rows are `model == "listen"` in history).
2. **Per-app routing = per-route override** — each app rule sets
   clipboard/notes/speak to on, off, or inherit; unset routes follow the live
   session toggles. Injection is never configurable.

## Component 1 — standalone live transcript window

- **Process:** `app.py --transcript` launches a lightweight pywebview window,
  exactly like the Settings process: **no ML imports** (guarded by the same
  discipline as `test_settings_no_ml`), reads the history DB read-only.
- **`transcript_ui.py`:** `TranscriptAPI` (slim bridge: `list(filter, query)`
  via `history.list` + source filter, `export(filter, query)` reusing the
  timestamped-file export shape, `state()` → history_enabled) and
  `run_transcript(smoke=False)` building the window (compact 420×560 default,
  resizable, `on_top` toggleable from the page via a bridge call).
- **`transcript.html`:** aurora-dark tokens matching Settings; chat-style rows
  (timestamp, source tag chip for capture rows, text; Copy per row);
  newest-at-bottom with auto-scroll pinned unless the user scrolled up;
  header = All/Dictation/Capture chips, search box, always-on-top toggle,
  Export button; 1.5 s poll, paused while the document is hidden.
- **Empty/disabled states:** history off → explains where to turn it on;
  no rows → friendly hint. Never a blank pane.
- **Launch points:** tray menu "Live transcript…" + fob right-click menu item.
- **Free tier.** It is a window onto data the user already owns.

## Component 2 — per-app routing profiles

- **Config:** `route_profiles`: dict, lowercased exe basename →
  `{"clipboard": bool, "notes": bool, "speak": bool}` with ABSENT keys meaning
  inherit. Persisted on purpose (unlike session toggles); privacy doc gains a
  line. Sanitized on load (exe non-empty str, route keys ⊆ the three, bool).
- **Pure core:** `routing.effective_routes(session_routes, rules, exe)` →
  `{"clipboard": bool, "notes": bool, "speak": bool}`; exe matched
  case-insensitively on basename; unknown exe or empty rules → session as-is;
  never returns an "inject" key (inject is unconditional).
- **Delivery:** `app._deliver` computes effective routes from
  `self._foreground_exe()` when `access.can("routing.per_app")`; otherwise
  session toggles alone. Notes-failure auto-disable keeps flipping only the
  session toggle (a per-app notes rule that fails just logs + notifies once).
- **Entitlement:** new `routing.per_app` → Developer (profiles family), with
  FEATURE_COPY entry, FEATURE_MATRIX row, guard tests.
- **Settings UI:** Flow section gains a "Per-app routing" table: exe input +
  three tri-state selects (Inherit/On/Off) + add/delete; bridge CRUD
  (`flow_route_profiles`, `flow_set_route_profile`, `flow_delete_route_profile`)
  with validation; hint explains inherit semantics + Developer gating.

## Error handling

Transcript window: DB read failures render a retrying error row, never crash;
export errors surface in-page. Routing: malformed rules dropped at config load;
effective_routes is pure and total.

## Testing

`tests/test_routing.py` additions (effective_routes matrix: override on/off,
inherit, unknown exe, case-insensitivity, no inject key);
`tests/test_flow_bridge.py` CRUD + validation; new
`tests/test_transcript_ui.py` (list filter/query/source-tagging, export,
disabled-history state, no-ML import guard); settings smoke unchanged;
transcript smoke (`--transcript --smoke` prints probe counters);
docs/version/full-suite per release discipline.

## Out of scope

Editing/deleting history from the transcript window (Settings owns that),
per-app notes paths, wake-mode, MIDI.
