# Download experience design record

## Existing tokens retained

The page retains `--bg`, `--surface`, `--surface-2`, `--border`, `--border-hi`, `--text`, `--muted`, `--accent`, `--accent-2`, `--accent-ink`, `--ok`, `--r`, `--maxw`, `--dur`, and `--ease`. The existing ROAR logo and system font stack remain in use; no remote assets or framework were added.

## New semantic tokens

`--preview` and `--preview-bg` identify the text-labelled Preview state. `--unavailable` is reserved for a neutral unavailable state, and `--focus-ring` is the high-contrast lavender 3 px focus ring. Each is paired with the near-black background or tonal surface for WCAG AA-readable text.

## Download-card anatomy

Windows Stable and Linux Preview are equal-weight cards: platform name, visible text badge with inline SVG, status, action or disabled state, definition-list metadata, checksum control, release notes, and installation disclosure. The cards are always shown; the visitor chooses a platform.

## Metadata hierarchy

The action and release status come first. Version, UTC release date, package, architecture, exact binary size, release notes, and SHA-256 follow. A shortened digest is only visual; the full digest remains in the DOM for copying, title text, and manual verification.

## Responsive behavior at 375/768/1024/1440

At 1440 and 1024 px the equal cards share two columns. At 768 px and below they stack in one column. At 375 px actions are full width, definition-list labels stack, checksum text wraps anywhere, and the page does not introduce horizontal scrolling.

## Accessibility rules

Status never relies on color alone. Preview/unavailable state uses visible words and an icon. Definition lists preserve metadata relationships, links are underlined when not button-shaped, and each checksum status uses its own polite live region.

## Focus/touch rules

Keyboard focus uses `--focus-ring` with a visible offset. Download actions and checksum-copy controls are at least 44 px tall or square. Disabled actions remain visibly disabled and provide a Releases recovery path.

## Checksum feedback

Only an explicit copy-button activation requests clipboard access. Success announces “Checksum copied”. If copying is unavailable, the full digest is selected and the live region explains how to copy it manually.

## Unavailable/error state

The static cards begin safe: Windows metadata loads and Linux Preview availability is checked. If the same-origin manifest fails validation or loading, both platform actions stay disabled and a repository Releases recovery link appears. No guessed or versioned fallback URL is made.

## Installation disclosure

The Linux card links to a narrow Preview guide with executable permission, checksum verification, direct launch, Ubuntu 24.04 package-smoke scope, x86_64, X11, unsupported Wayland, and manual-device gates. It makes no Linux GPU claim.

## Motion/reduced-motion

The existing restrained transition timing is retained. The download controller adds no loading animation or decorative motion. The page-wide reduced-motion rule continues to suppress nonessential animation.

## Do examples

- Do show both platforms before and after metadata loads.
- Do use the manifest's exact URL, digest, date, and byte count after validation.
- Do give unavailable channels a clear disabled state and recovery link.

## Do-not examples

- Do not inspect the browser OS, preselect a card, or hide the other platform.
- Do not attach download-click analytics, events, beacons, or remote release requests.
- Do not call Preview production-ready, promise Wayland support, or imply Linux GPU support.

## Rationale for Material Design 3-inspired decisions

Tonal surfaces, 16 px corners, compact text badges, and border/shadow elevation make related release details scannable without replacing ROAR's established identity. The balanced card layout preserves choice, while explicit status and strong focus treatment make release safety and interaction state understandable without decorative complexity.
