# ROAR Speech Cleanup (SP8) — Design

**Version:** v0.11.0
**Date:** 2026-07-04
**Status:** approved

## Goal

Make dictated text read like writing, not raw speech: remove filler words and
light disfluencies (stutters, doubled words, cut-off false starts) from the
transcript before it is typed into the focused app. 100% local, deterministic,
no new dependencies, no language model.

## Non-goals

- **No grammar rewrite / rephrasing.** Explicitly ruled out — that would need a
  local LLM and betray ROAR's lightweight, instant design.
- **No text-to-speech.** ROAR is dictation-only; there is no user-facing TTS.
  ("tts" in the original request was loose phrasing for the transcribed text.)
- **No decode-time suppression.** Whisper `suppress_tokens`/`initial_prompt`
  are unreliable, model-dependent, and untestable; cleanup is post-processing.

## Architecture

A new pure module `cleanup.py` (same shape as `snippets.py`) exposing:

```python
def clean(text: str, *, discourse: bool = False) -> str
```

It applies, in order, then normalizes whitespace and orphaned punctuation:

1. **Interjection removal (always on when cleanup is enabled).**
   Standalone filler tokens, word-bounded and case-insensitive:
   `um, umm, ummm, uh, uhh, uhm, er, err, erm, hmm, hmmm, hm, mm, mmm`.
   Word boundary means "umbrella"/"summer" are never touched. Removal tidies
   the comma/space it leaves behind ("Um, hello" -> "hello").

2. **Stutter / repeat collapse (always on).**
   An immediately repeated identical word collapses to one — but **only** for a
   curated stutter-prone allowlist, so grammatical doubles survive:
   - Collapse set (plain `\w+` words only): `i, a, an, the, to, and, we, you,
     it, is, so, but, my, of, in, on, at, for, he, she, they`. Contractions
     are out of MVP scope (keeps matching apostrophe-free and word-bounded).
   - Deliberately NOT collapsed: `had, that, very, really, no` and anything
     off the allowlist ("had had", "very very", "that that" stay intact).
   - Case-insensitive match; the FIRST occurrence's casing is kept.

3. **Dangling false-start trim (always on).**
   A cut-off fragment immediately before an em/en/hyphen dash is dropped:
   `"I— I think" -> "I think"`, `"wh- what" -> "what"`, `"go— go to" -> "go to"`.
   Only fires when a dash directly follows a short (<=4 char) word fragment and
   is followed by whitespace, to avoid eating real hyphenates ("well-known").

4. **Discourse fillers (opt-in, default OFF).**
   `like, you know, i mean, i guess, sort of, kind of, basically, actually,
   literally, right, you see` removed **only when comma-bounded** — i.e. the
   filler sits between commas or at a clause edge next to a comma
   (`", like,"`, `"^so,"`). This is how Whisper punctuates true fillers, so
   `"I like it"` (no bounding commas) is never touched. Off by default because
   the false-positive cost erodes trust instantly.

After all passes: collapse runs of spaces, drop spaces before punctuation, drop
leading orphan commas/spaces, and strip. Empty result returns `""`.

### Pipeline placement

`commands.process` gains cleanup as the FIRST transform, before replacements:

```
strip -> cleanup -> replacements -> capitalize -> snippets
```

Rationale: cleanup runs on the raw transcript so capitalization then lands on
the real first word after a leading "Um," is gone, and so spoken commands
("new line") and snippets see already-cleaned text. New signature:

```python
def process(text, replacements, snippets=None, snippet_keyword="snippet",
            cleanup=False, discourse_fillers=False) -> str
```

`cleanup`/`discourse_fillers` are plain bools (back-compatible: existing
two/four-arg callers and tests are unaffected; cleanup defaults off at the
function boundary, and `app.py` passes the config values).

## Configuration

Two keys in `config.DEFAULTS`, both instant-apply (no restart), following the
existing toggle pattern:

| Key | Default | Effect |
|---|---|---|
| `cleanup_enabled` | `true` | Interjections + stutter/repeat collapse + false-start trim |
| `remove_discourse_fillers` | `false` | The comma-bounded discourse-filler pass (only consulted when `cleanup_enabled`) |

`cleanup_enabled` defaults **on** — it is the feature, and its transforms are
safe (word-bounded, allowlisted). `remove_discourse_fillers` defaults **off**
because of false-positive risk. Both added to `settings_ui.INSTANT_KEYS` and
coerced with `bool()` on write. Existing users upgrading from 0.10.0 get
`cleanup_enabled` on by default (their `config.json` lacks the key, so
`DEFAULTS` supplies it) — a deliberate, safe behavior change.

## Settings UI

Two toggles in the **Transcription** tab (where vocabulary already lives):

- **Clean up speech** — "Removes 'um', 'uh', stutters, and repeated words."
  bound to `cleanup_enabled`.
- **Remove filler phrases** — "Also strips 'like', 'you know', 'I mean' when
  they're used as fillers. May occasionally remove a real word." bound to
  `remove_discourse_fillers`.

Toggle handlers reuse the existing `set_value` instant-key path. The smoke
probe asserts both toggles exist (`t-cleanup`, `t-discourse`).

## Multilingual

Filler word lists are English (consistent with Insights being English-centric,
per the multilingual design). The stutter/repeat collapse and false-start trim
are language-agnostic and benefit every language. Documented as a known
limitation in the README; non-English dictation simply sees fewer removals.

## Error handling

`cleanup.clean` is pure and total: any input string returns a string, never
raises. Non-string / empty inputs short-circuit to `""`. The pipeline stage is
guarded by the `cleanup` bool, so a disabled feature is a no-op with zero cost.

## Testing

- `tests/test_cleanup.py` — before/after tables per transform: interjections
  (incl. word-boundary safety), stutter collapse (allowlist in, grammatical
  doubles preserved), false-start trim (incl. hyphenate safety), discourse
  fillers (comma-bounded removed, bare "I like it" preserved), whitespace/
  punctuation normalization, empty/whitespace input.
- `tests/test_commands.py` — pipeline integration: cleanup runs before
  replacements and capitalize; disabled by default in the bare signature;
  discourse gated by its flag.
- `tests/test_config.py` — new keys present in defaults; sanitized to bool.
- `tests/test_settings_bridge.py` — `set_value` accepts both new instant keys.
- Settings smoke probe asserts `cleanup=1 discourse=1`.

## Release

Version bump to `0.11.0` (`paths.APP_VERSION` + `test_paths` + bridge + smoke
asserts). Full train: exe rebuild, external-CAB MSI (per the 2 GB `.msi` cap
fixed in 0.10.0), frozen settings probe, upgrade install over 0.10.0 with data
intact, adversarial review, push, tag `v0.11.0`, relaunch, memory update.
