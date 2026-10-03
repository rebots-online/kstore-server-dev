---
schema_version: 1
document_id: voiceish-sim-design-review-20261003
project_id: voiceish-sim-16sep2026
title: "Voiceish SIM: messaging, notifications and address book"
revision: 1
status: proposed
owner: Robin
created_at: 2026-10-03
source_repository: https://github.com/rebots-online/voiceish-complete-0.1.4
baseline: "SIM 0.1.4 / extension manifest 0.2.2"
figma_design: https://www.figma.com/design/jgQ6af7U751btRN5FPzJ5w
figma_make_status: blocked-site-unavailable
stitch_status: blocked-google-sign-in-cancelled
prototype_provenance: authored-review-draft-not-a-make-or-stitch-export
approval_required: operator-sign-off-before-product-code
---

# Design System: Voiceish SIM

## 1. Visual Theme & Atmosphere

A practical communications desk, using the established 0.1.4 navy, gold and cobalt theme. Density 6, variance 3, motion 2. The reading surface stays quiet. Recipient identity is more prominent than decoration. This software has no marketing hero.

## 2. Color Palette & Roles

- Deep Navy `#040f1b`: application canvas.
- Raised Navy `#0a1c2c`: navigation, header and composer.
- Panel Navy `#122a3e`: incoming bubbles and selected controls.
- Hairline Slate `#294256`: borders and section dividers.
- Cool Ink `#ebf3fc`: body text and primary identity.
- Muted Slate `#a2b5c9`: timestamps and secondary labels.
- Brand Gold `#ffbc32`: primary actions and persistent recipient label.
- Outgoing Cobalt `#1d70da`: outgoing message bubbles.

The existing operator-approved gold/cobalt palette takes precedence over the Stitch taste workflow's usual one-accent rule. Do not introduce neon glows, purple gradients or another decorative accent.

## 3. Typography Rules

Geist, inherited from the verified source, with locally embedded font bytes in the HTML draft. Full numbers use tabular numerals and wrap without ellipsis. Body 16px; minimum functional labels 14px; secondary review metadata 12px. Heading scale 22–30px. No serif. No substituted Inter. All messages are escaped text.

## 4. Component Stylings

Buttons use 44px minimum touch targets. The primary button is gold with navy text. Inputs always have a label. Errors appear near the affected control. Message bubbles use 15px corners, with outgoing messages on cobalt. Contact lists use dividers and source labels, not a forest of cards. Loading placeholders retain the final content's geometry.

Notification previews show name, full number, body preview and an Open message action. An in-app incoming banner occupies its own row above the workspace. It must neither cover the composer nor change the active recipient without a user action.

## 5. Layout Principles

Desktop: a 260px navigation/conversation column and a flexible workspace. Production may keep the current rail plus list as long as the recipient/composer invariant is preserved. The HTML draft combines these columns to make review clearer. Below 768px, show one primary pane and explicit navigation.

Conversation: header; independently scrollable history; composer. The composer repeats **To: name + full actual destination number**. Keep the SIM label beside the draft. Use `minmax(0,1fr)`, `min-height:0`, dynamic viewport measurements and keyboard insets. Remove the current global 580px minimum workspace height. No element may require sideways scrolling at 320px. A contact with several numbers always gets a number picker.

## 6. Motion & Interaction

Restrained transform/opacity feedback only. No perpetual animation while reading. Respect reduced motion. Enter sends only after a valid destination is selected; Shift+Enter adds a newline; IME composition never sends. Notifications preserve per-thread drafts. Selecting a different recipient restores that recipient's draft, never the prior recipient's text.

## 7. Anti-Patterns

No concealed or truncated recipient. No absolute positioning that overlaps header, history or composer. No automatic uncertain resend. No name-only contact merge. No guessed country code. No silent SIM change. No silent Google account change. No claiming old 300-message snapshots cover all received history. No prototypes presented as working SMS or completed sync. No real contacts, messages or pairing secrets in design files.

## Screen generation contract for Figma Make and Stitch

Use `screens.json` as the exact route and action inventory. Generate every screen listed there, including blocked permissions, uncertain send, offline, expired Google authorization and contact conflict. Keep the navy theme and Geist. All screens must link through natural actions and a review screen selector. Use identical state fields and adapter names from `CONTRACTS.json`. Export runnable HTML/CSS/JS, not screenshots or disconnected snippets. Preserve sample-only labeling. Do not claim working APIs in the export.

The connected Figma **Design** file contains 31 editable screen frames and linked navigation actions. It is a design companion, not Figma Make. Completion of actual Figma Make and Google Stitch generation, export and reconciliation remains a release-planning gate, rather than fabricated provenance.
