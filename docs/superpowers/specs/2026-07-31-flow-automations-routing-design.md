# ROAR Flow — voice automations + multi-channel output — Design

**Date:** 2026-07-31 · **Status:** approved (user waived review gate; autonomous build) · **Repo:** `xhan145/roar`

## Context and roadmap

Inspired by ProdCom ("Transcribe. Translate. Automate.") but rebuilt around
ROAR's identity: a single user's PC, fully local. The user approved a six-part
roadmap, each part its own spec → plan → build cycle:

1. **This spec.** Automation + multi-channel output engine.
2. Live transcript panel (a registered output).
3. Meetings capture — WASAPI loopback as a second source feeding the same chain.
4. Show-control outputs — MIDI/OSC as additional outputs and rule actions.
5. Translation as a pipeline stage.
6. Website + release marketing the whole story.

## Decisions (user-approved)

1. **Trigger model:** phrases are spotted inside the normal dictation flow only
   (like "scratch that" today). No separate always-listening mode in this pass.
2. **Actions v1:** open_app, open_url, hotkey, snippet, speak, copy are freely
   usable. `run_script` and `webhook` exist but fire ONLY on rules the user
   marked **trusted**, and every such fire shows a toast naming the rule with a
   short cancel window first.
3. **Outputs v1:** focused-app injection (default, as today), clipboard,
   append-to-notes-file, TTS speak-back. All local. Webhook-as-output is NOT in
   v1 (webhook exists only as a gated rule action).
4. **Routing control:** voice ("roar route notes on/off" etc.) + always-visible
   state (pill badges + tray) + Settings toggles. Extra outputs reset to off on
   app exit.
5. **Architecture:** registry + pipeline stage (option A). No event-bus rework.

## Architecture

Text flow in `app.py._handle_transcription` today:
`transcribe → scratch? → read-back? → commands.process → corrections.apply → _inject_final`.

New flow inserts two stages:

```
… corrections.apply
→ automations.match(text, rules)      # pure; returns (actions, remaining_text)
→ actions.execute(matched, deps)      # side effects, isolated failures
→ if remaining_text: deliver to every active output (routing.py)
```

`_inject_final` becomes the **injection output's** deliver function; history,
milestones, scratch-stack, and status writing stay attached to injection
exactly as today (other outputs do not duplicate them).

## Components

### `automations.py` — pure rule engine (no I/O)

Rule dict (stored in `config.json` under `"automation_rules"`, a list):

```python
{"phrase": "open terminal", "action": "open_app", "params": {"target": "wt.exe"},
 "enabled": True, "trusted": False, "consume": True}
```

API:

- `normalize(text) -> str` — lowercase, strip punctuation/extra spaces
  (reuses the corrections normalizer's semantics).
- `match(text, rules) -> MatchResult(actions, remaining_text)` — a rule fires
  when its normalized phrase equals the normalized utterance OR is its prefix
  ending on a word boundary. **Never mid-sentence.** `consume=True` removes the
  phrase (whole-utterance match ⇒ remaining_text == ""); `consume=False`
  leaves text untouched. Disabled rules never match. First match wins per rule;
  multiple distinct rules can fire only when the utterance is exactly one
  phrase (no chaining in v1 — simplest predictable semantics).
- `validate_rule(rule, existing) -> error | None` — phrase non-empty ≤ 60
  chars, known action, params shape, duplicate-phrase rejection.

`SCRIPTED_ACTIONS = {"run_script", "webhook"}` — the set needing trust.

### `routing.py` — output registry (pure core + tiny adapters)

- `OUTPUTS = ("inject", "clipboard", "notes", "speak")` — fixed order;
  `inject` is always active and not toggleable.
- `active_outputs(cfg) -> tuple` — reads `"route_clipboard"/"route_notes"/
  "route_speak"` booleans (all default False).
- `deliver(text, outputs, handlers, log) -> dict` — calls each handler in
  order; one handler raising never stops the rest; returns per-output status.
- `notes_line(text, now) -> str` — `[YYYY-MM-DD HH:MM] text\n`.
- `append_notes(path, line)` — append-only, UTF-8, creates parent dir; raises
  cleanly on failure (caller isolates).
- Voice command parsing: `parse_route_command(text) -> (output, on) | "all_off" | None`
  for "roar route(s) <clipboard|notes|speak> <on|off>" and "roar routes off".

### `actions.py` — executors + trust gate

`execute(action, params, deps) -> None` where `deps` carries injector, tts
dispatch, notify, cfg. Executors:

- `open_app` — `subprocess.Popen` detached; target validated non-empty.
- `open_url` — `webbrowser.open`; scheme must be http/https.
- `hotkey` — send a chord via the injector backend (e.g. "ctrl+shift+t").
- `snippet` — insert a named snippet's body via the normal injection path.
- `speak` — TTS speak of `params["text"]`.
- `copy` — put `params["text"]` (or the utterance) on the clipboard.
- `run_script` / `webhook` — ONLY when `rule["trusted"]` AND the edition allows
  `automations.scripted`; otherwise notify-and-skip. Before firing, show
  a toast "Flow: <rule phrase> → running in 2 s (say/press to cancel handled by
  notify only in v1: the toast informs; cancellation = disable the rule)".
  v1 keeps the gate simple: trusted + entitled + informative toast; no timer
  race in the dictation thread.
- `webhook` — `urllib.request` POST JSON `{"text", "rule", "ts"}` to the rule's
  URL, 3 s timeout, fire-and-forget thread. This is ROAR's only outbound
  network path, exists only inside an explicitly trusted rule, ships off, and
  is documented in the privacy docs.

Failures notify once and log; they never break dictation.

### `app.py` wiring

- After `corrections.apply`: check `routing.parse_route_command` first (a route
  command is consumed, toggles config-in-memory, notifies, and returns).
- Then `automations.match`; execute matched actions via `actions.execute`.
- Remaining text delivers through `routing.deliver` with handlers:
  `inject` → existing `_inject_final`; `clipboard` → set clipboard;
  `notes` → `append_notes`; `speak` → tts dispatch (remember=False).
- Route toggles are session-only: written to the in-memory cfg, NOT persisted;
  on start they are always off (spec decision 4). Settings shows them as
  session switches.
- Tray tooltip + menu show active routes; the overlay pill gains a compact
  suffix (e.g. "▸notes ▸clip") while extra routes are on.

### Settings — new "Flow" section

- Rules table: phrase, action, params, enabled, trusted (checkbox with inline
  warning), delete. Add-rule form with per-action param fields. "Test" button
  fires the rule's action immediately (same trust gate).
- Output switches (session): clipboard / notes / speak, plus notes-file path
  picker (default `Documents/ROAR Notes.md` under the user profile).
- Plain-language security note: what trusted means, why scripts are gated.
- Bridge methods on `SettingsAPI`: `flow_state()`, `flow_set_output(output,on)`,
  `flow_rules()`, `flow_add_rule(rule)`, `flow_update_rule(i, rule)`,
  `flow_delete_rule(i)`, `flow_test_rule(i)`. Rules persist in config.json;
  bridge validates via `automations.validate_rule`.

### Entitlements

New registered features (added to the vocabulary, gates display-only as today):

- `automations.rules` — Pro
- `routing.multi` — Pro
- `automations.scripted` — Developer (run_script/webhook actions)

Core keeps everything it has today; no existing feature moves.

## Error handling

- Rule engine and route parsing are pure — they cannot raise in the hot path.
- Every action executor and output handler is individually try/excepted with a
  single user-visible notify and a log line; dictation always completes.
- Notes path unwritable → notify once per session, auto-disable notes route.
- Unknown action in stored config (forward compat) → skipped with log.

## Privacy

- All processing local. The notes file is a new persistence location: opt-in,
  user-chosen path, plain text, called out in PRIVACY docs, user-deletable.
- Webhook: off by default, only inside a trusted rule, only the utterance text
  + rule name + timestamp, never history/audio/config. Documented.
- Nothing here reads history, audio, vocabulary, or clipboard beyond the
  explicit copy/clipboard-output the user configured.

## Testing

- `tests/test_automations.py` — matching (normalization, whole/prefix boundary,
  no mid-sentence, consume semantics, disabled, multiple rules), validation.
- `tests/test_routing.py` — active-set from cfg, delivery order, failure
  isolation, notes line format/append, route-command parsing table.
- `tests/test_actions.py` — each executor with fakes; trust gate matrix
  (trusted × entitled), scheme validation, failure isolation.
- `tests/test_flow_bridge.py` — bridge round-trip, validation errors, session
  toggles not persisted.
- Existing suite stays green; live smoke via installed app after build.

## Out of scope (later roadmap slices)

Live transcript panel, loopback capture, MIDI/OSC, translation, wake-mode
listening, rule chaining, per-app-profile routing, website update (slice 6).
