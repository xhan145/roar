# Read Aloud accessibility

The Read Aloud Settings view uses native buttons, inputs, selects, checkboxes,
and labels. Status changes use a polite `aria-live` region. Every voice preview
has a text label; Stop is a real button and can be reached without a mouse.
Visible focus, Windows forced-colors/high-contrast behavior, reduced motion,
responsive reflow, zoom, and a resizable typed-text area are covered by the
static accessibility tests.

The optional global Stop hotkey remains available while speech is synthesizing
or playing. Other optional Read Aloud hotkeys are empty by default and are
validated against dictation and each other after modifier canonicalization.

Preview-before-insertion uses the standard Windows Yes/No/Cancel dialog:

- Yes accepts and inserts.
- No repeats the preview.
- Cancel discards it.

This preserves keyboard navigation and Windows screen-reader semantics without
introducing a custom inaccessible modal.

## Manual release checks

Automated markup checks cannot validate the complete assistive-technology
experience. Before release, test the frozen build at 100%, 200%, and 400% text
zoom; Windows High Contrast; keyboard-only navigation; Narrator; and the
standard preview-before dialog. Confirm status announcements are useful but
not repetitive, Stop remains reachable, disabled controls explain why, and no
control is clipped at a narrow window width.

Voice labels deliberately avoid demographic inference. The included catalog
uses stable upstream IDs and neutral display names. English (`en-us`) is the
only supported language in this MVP.
