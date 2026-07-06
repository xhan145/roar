# Known issues & caveats

- **Backspace-undo precision**: apps that transform typed text (auto-indent or
  autocomplete in code editors, autocorrect) can make "scratch that" counts
  imprecise. Emoji/astral undo is best-effort — backspace granularity for
  surrogate pairs is app-dependent.
- **Desktop-bound test flakes**: `test_sendinput_types_into_focused_window`
  types into a real focused tkinter Entry and can flake if another window
  (e.g. a closing webview from the settings smoke test) steals focus mid-run.
  Rerun; it passes in isolation.
- **Smoke-test flake when ROAR is running**: `test_smoke.py` and
  `test_settings_smoke.py` report "already running" if a ROAR instance holds
  the singleton/settings mutex. Kill ROAR.exe (and its msedgewebview2
  children) before running the suite.
- **Setup exe uses `/qb`**: if any ROAR process lingers, the MSI shows a
  blocking "Files in Use" dialog. Fully quit ROAR first, or install the MSI
  directly with `/qn`.
- **MSI + external cabs must travel together**: the `.msi` file format is
  hard-capped at 2 GB, so the ~2.8 GB payload lives in `roar1..4.cab` next to
  the msi. Moving the msi alone breaks installation; use the single-file
  `ROAR-Setup-<v>.exe` when sharing.
- **Window chrome flashes dark** for a moment when opening Settings in light
  mode (the WebView2 window pre-paints with the dark chrome color).
- **Browser-title profile routing is heuristic**: a browser tab whose title
  contains a keyword ("facebook", "github", …) selects that profile; unusual
  titles can misroute. Scoped to browsers only; add a `title:` override in
  app_profiles to pin behavior.
- **Spoken commands are English** ("new line", "scratch that") even when
  dictating other languages; add per-language `replacements` for equivalents.
- **Insights word analysis is English-centric** (stopword list).
- **First GPU load after boot takes a few seconds** (CUDA/cuDNN warmup);
  dictation is queued, not lost.
