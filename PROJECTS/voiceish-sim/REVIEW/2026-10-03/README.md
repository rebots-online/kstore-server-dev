---
schema_version: 1
project_id: voiceish-sim-16sep2026
revision: 1
status: review-draft-awaiting-sign-off
created_at: 2026-10-03
---

# Voiceish SIM: review package

1. Open `Voiceish-prototype.html` in a browser. Use natural action buttons or the numbered screen selector to inspect all 31 screens. All SMS, notification, contact and sync effects are sample-only.
2. Review `ARCHITECTURE.md` for proposed system behavior, ownership and constraints.
3. Review `CHECKLIST.md` for 35 dependency-ordered task recipes and its embedded kstore-orchestrator prompt. Product work is gated on operator sign-off and verified requested GLM configuration.

[Editable Figma Design companion](https://www.figma.com/design/jgQ6af7U751btRN5FPzJ5w)

`screens.json` contains exact screen/action IDs. `CONTRACTS.json` defines state fields, adapter methods and typed errors. `DESIGN.md` is the exact generation brief for Figma Make and Google Stitch. `task-recipes.json` provides machine-readable task dependencies, scopes and acceptance conditions. `SHA256SUMS.txt` binds delivered byte versions. `VALIDATION.json` reports only checks actually performed.

The primary layout change is visible in the conversation: recipient name and full number are repeated beside the input. The Keyboard test button reduces the available area for review; it is not a physical Android keyboard test. A sample incoming preview preserves the active draft. Choose Ellis to inspect separate numbers/drafts, or Unknown sender to add/link a received number.

## Provenance and unfinished destinations

- This HTML is an authored fallback draft, not an export from Figma Make or Google Stitch.
- Figma Design has 31 editable frames, imported UI components, application variables and navigation. Design inputs represent proposed fields; live state mutation is in the HTML draft.
- Figma Make returned Site Unavailable in the available browser.
- Google Stitch required sign-in; the secure sign-in was cancelled. No generation/export occurred.
- The requested `.87` host was not available through the connected remote-device route. Its exact development checkout path remains unresolved. No remote file copy or literal kstore ingest is claimed.
- The package is saved in the development repository at `PROJECTS/voiceish-sim/REVIEW/2026-10-03`, with a separate delivery receipt giving actual commit/hash results.

## Host continuation for .87 and kstore

Use the authorized host session to retrieve current authority and the correct **development** checkout through kstore. Do not infer its path from the old production `~/kstore/app` deployment or overwrite kstore root architecture.

Pull or materialize this exact project review directory at the receipt's commit into the verified development checkout. Run `sha256sum -c SHA256SUMS.txt`. Feed `ARCHITECTURE.md`, `CHECKLIST.md` and this review evidence to the repo-owned verified client using invocation manifest entries (`file`, `id`, `source_type`, `title`); the schema is documented by `client/kstore_client.py`. Use project IDs under `PROJECTS/voiceish-sim/REVIEW/2026-10-03/`. Keep credentials in existing private client configuration, never in command text or manifests.

Require independent PostgreSQL exact-content revision readback and record asynchronous Qdrant status. Keep outbox on failure. Only after verified ingest should an authorized local projection be labeled synchronized. If any Admin-Manual projection is edited, immediately perform the operator-required scoped commit/push. Record remote file hashes, checkout/commit and verified-client receipts in a separate execution ledger. These instructions are a continuation recipe, not evidence that this host step has run.

## Discussion and sign-off

The draft proposes camera-based scanning of a phone QR, preserving the current subnet boundary; background previews through the extension; phone-owned contact identity and outbox; and one write owner for Google-backed Android contact records. Confirm these decisions after reviewing the screens. Resolve the actual Make/Stitch export requirement or explicitly waive it before freezing. Approval references exact document/prototype hashes, product commit and kstore authority revision. Do not mark a worker launched or thinking disabled without provider/runtime proof.
