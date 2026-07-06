# Known Issues

- OS-level injection tests can skip or fail if desktop focus is actively contested during the run.
- Release packaging depends on large model payloads and external CAB files for the MSI path.
- Fresh source checkouts do not include gitignored `models-seed/`; run `scripts/fetch_models.py` before building a fully offline multilingual installer.
- Some target apps transform typed text after injection, so scratch-that undo is best-effort for those apps.
