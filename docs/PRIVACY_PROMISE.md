# Privacy Promise

ROAR is built so your words stay yours.

- **Local transcription.** Speech is turned into text on your computer.
- **No cloud transcription.** Your audio and transcripts never leave your machine.
- **No account.** No login, no profile, no identity required.
- **No telemetry.** No analytics, no usage tracking, no background network calls.
- **No transcript upload.** ROAR does not send your dictation anywhere.
- **You control history.** View, filter, and delete history whenever you want.
- **You control audio retention.** Where audio is retained, you decide and can
  delete it.
- **Licensing is blind to your data.** The license/entitlement code never reads
  your transcripts, audio, history, vocabulary, or clipboard, and a paid license
  never inspects your dictation.

These are enforced in code and covered by tests (`tests/test_commercial_privacy.py`,
`tests/test_network_hygiene.py`). Privacy controls and deleting history/audio are
**free in every edition**, including Core.

## ROAR Flow (v0.31+)

Flow adds two places your text can go — both entirely under your control:

- **Notes route (opt-in, off at every start).** When you turn it on, each
  dictation is also appended, timestamped, to ONE plain-text file at a path you
  chose. It lives on your machine and you can delete it like any file.
- **Per-app routing rules (v0.34+) are persisted settings.** Unlike the live
  route toggles (which always reset to off), an app rule you create — e.g.
  "notes on in Word" — stays until you delete it in Settings → Flow. It's
  plain config on your machine, and it only ever governs the local routes
  above.
- **Webhook action (trusted rules only).** The only way ROAR can ever make an
  outbound network call with your text is a Flow rule that YOU created, YOU
  marked trusted, pointing at a URL YOU chose. It sends only that one
  utterance's text, the rule's name, and a timestamp — never history, audio,
  vocabulary, or settings. No rule ships with ROAR; nothing is on by default.
  The network scan in `tests/test_network_hygiene.py` pins this as the single
  outbound call site.
