# Changelog

## Unreleased

- Hardened focus safety: ROAR captures the target window at recording start and refuses to type if focus changes before injection.
- Bounded clipboard paste fallback and restored clipboard contents on paste errors when possible.
- Added safe diagnostics, reversible Safe Mode settings, and diagnostics redaction helpers.
- Added local offline licensing/entitlement primitives without gating Core dictation or privacy controls.
- Added appearance setting with system/light/dark modes.
- Hardened snippet clipboard variables and snippet pack import validation.
- Added raw/clean/code format-mode separation for deterministic local formatting.

## 0.13.0

- Private offline word milestones.
- Lavender ROAR branding and logo assets.
- Milestone notification de-duplication after history clear.
