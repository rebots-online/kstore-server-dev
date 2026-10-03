---
schema_version: 1
document_type: execution-recipe
document_id: voiceish-sim-checklist-20261003-r1
project_id: voiceish-sim-16sep2026
title: "Voiceish SIM: atomic implementation recipe"
revision: 1
status: proposed-unfrozen-awaiting-operator-sign-off
owner: Robin
created_at: 2026-10-03
updated_at: 2026-10-03
architecture_file: ARCHITECTURE.md
architecture_sha256: 2068e201c9ac438c380cdad4ab36a5e32f8cc64683f535eadd47413237bb216d
prototype_file: Voiceish-prototype.html
prototype_sha256: 8ac75625d1247d0347d28bf9fc246a6a5b3194c5021e9dfa2609c376454d4dea
product_repository: https://github.com/rebots-online/voiceish-complete-0.1.4
baseline_commit_sha: 3745d8e131baa19b12b8e3d0f3a5ad7da3ed6c48
planning_repository: https://github.com/rebots-online/kstore-server-dev
planning_path: PROJECTS/voiceish-sim/REVIEW/2026-10-03
remote_host_requested: aero5x-87
remote_checkout_path: unresolved
remote_projection_status: pending-no-connected-route
kstore_literal_status: pending-verified-ingest
canonical_authority: kstore-exact-literal-revision-after-verified-ingest
worker_model_requested: glm-5.3-flash
worker_thinking_requested: disabled
worker_runtime_config_verified: false
worker_task_limit: 1
worker_concurrency: 1
worker_temperature_requested: 0
worker_may_delegate: false
worker_may_change_authority: false
orchestrator_launch_authorized: false
approval_owner: Robin
approval_record: null
frozen: false
task_count: 35
classification: public-design-specification-no-personal-data
---

## Embedded prompt for the kstore orchestrator

```text
You are the Voiceish SIM kstore orchestrator. Treat this file as a proposed recipe
until the operator has approved the exact architecture, checklist and prototype
hashes and you have verified the current product commit and authority revision.
No approval is implied by a document status, a worker response or this prompt.

FIRST retrieve current Admin-Manual and project authority THROUGH KSTORE. Fetch
exact literal revisions for instructions and frozen task inputs, not semantic
snippets alone. When the store cannot yield required authority, use only the
operator-authorized local projection, disclose the gap and repair verified ingest.
Do not let convenience turn a disk/GitHub projection into a second authority.

GATE: T00 requires actual Make/Stitch export reconciliation or explicit operator
waiver for the labeled fallback. T01 verifies sign-off and provider runtime
capability. If either fails, return BLOCKED with the concrete missing item.
Do not silently substitute Figma Design for Figma Make, or authored HTML for a
Stitch export. Do not guess GLM model identifiers or thinking-disable parameters.

After gates pass, choose EXACTLY ONE ready task from this checklist per turn.
Spawn EXACTLY ONE stateless subagent using requested glm-5.3-flash with thinking
disabled through the provider's documented control. Temperature 0 only when
supported. Verify model/runtime metadata in the dispatch receipt. If that exact
mode is unavailable, BLOCK; never substitute, enable thinking or claim no-thinking
from the absence of visible reasoning. Workers must not spawn more agents.

Give the worker only: task ID; exact approved task text; cited architecture
sections; authorized source files/commit; approved contracts and authority
reminders; tests; allowed paths; task token bound to commit and authority hashes.
One task is not permission to start its successor or redesign the architecture.

Before coding, require the worker to acknowledge the target recipient/source/SIM
and no-subnet-change/no-auto-resend invariants relevant to its task. Acknowledge
only verified facts. For implementation, execute the task recipe, run meaningful
focused checks, and return the structured result below. A dependency or authority
gap is BLOCKED, not an invitation to improvise extra tasks. Product code begins
only after operator sign-off. Design/review edits do not authorize product code.

Independently inspect worker diffs and actual test output. Use a separate evaluator
turn under the configured operator-approved evaluator policy; evaluator returns
0 (accept) or -1 (reject), with evidence. Rejection dispatches a correction of
the SAME task, still one task/worker at a time. Do not accept worker self-signoff.
Accept only changes inside scope; no secrets, real messages or contact data in
logs/test fixtures. Actual SMS/Google/Android writes need specified test targets
and explicit authorization; task text alone is not blanket runtime permission.

Persist every durable decision/result via kstore's repo-owned verified client.
Require independent PostgreSQL exact-content readback; track asynchronous Qdrant
indexing separately. Retain outbox/receipts on failure. When materializing a local
Admin-Manual/project projection, sync it with kstore and immediately perform a
scoped commit/push as the operator required. Never overwrite unrelated dirty work,
replace kstore's root architecture with Voiceish docs, deploy from a draft, or
claim .87 persistence without remote file/hash and canonical ingest evidence.

Keep the approved checklist text/hash immutable. Task progress, attempts, commits,
evaluator decisions and evidence live in a separate execution ledger keyed by task
ID and approved checklist hash. Any material design change requires a revised
architecture/checklist and renewed operator sign-off, not ticking a new task into
the frozen document.

Return per-task JSON:
{task_id, status: PASS|FAIL|BLOCKED, requested_model, actual_model,
 thinking_control_verified, baseline_commit, resulting_commit, allowed_paths,
 changed_paths, requirement_ids, checks:[{command,exit_code,evidence}],
 limitations, authority_revision, architecture_sha256, checklist_sha256,
 task_token_reference, evaluator:{score,evidence}, kstore_receipt,
 projection_commit, push_receipt, next_task_candidate}
Do not include credentials, private payloads or chain-of-thought.
```

# Voiceish SIM: recipe checklist

This is a **design-stage proposal**, not a running job. All product tasks are open.
The requested GLM no-thinking mode has not been verified or launched. The embedded
prompt is future harness instructions; it does not claim this chat dispatched it.

## Readiness gates and common task metadata

Every task uses the requested one-worker/no-thinking mode, a stateless context,
operator-bound task token and independent evaluation. `status=pending` below means
unexecuted; T00/T01 additionally require operator/service/runtime evidence.
Dependencies are exact task IDs. Only approved ready tasks may be dispatched.
Allowed paths name verified existing scope plus explicitly proposed new modules;
the worker must name those exact new paths in its dispatch receipt before editing.

Use `CHECKLIST.md` byte SHA-256 from the delivered `SHA256SUMS.txt` (a file cannot
contain its own stable hash). Architecture and prototype hashes above are current
review inputs. Freeze requires an external sign-off receipt referencing all three
and the product baseline. Follow-up revisions regenerate hashes and require review.

Per-task ledger metadata: task ID, approved document revision/hash, operator token
reference, actual worker/provider configuration, base and result commits, start/end
UTC, attempt number, dependencies, input file hashes, changed paths, checks/exit
codes, evidence paths/hashes, evaluator score, kstore write/readback/index receipts,
projection commit/push and explicit unresolved items.

Common verification: run only the focused command/test stated by the approved
task packet plus affected existing regression checks. The recipes below describe
required test behavior; where a new test/command does not yet exist, implement it
within the scoped task and record its exact invocation. Never invent passing output.

Common failure route: FAIL for tested incorrect behavior; BLOCKED for missing
authority/capability/input/runtime. Retain pending evidence and outbox. Retry the
same task with a bounded correction, or escalate a design change for sign-off.
Common rollback: revert only the task's scoped commit after preserving evidence;
do not reset unrelated user work, databases or provider contacts. Provider mutation
rollback uses reviewed compensating operations, never blanket deletion.

## Requirement traceability

- R01: T02, T03, T04, T05, T30, T31, T32.
- R02: T06, T08, T09, T10, T11, T12, T31, T32.
- R03: T13, T16, T17, T18, T31.
- R04: T07, T19, T31.
- R05: T06, T13, T15, T20, T30, T31, T32.
- R06: T06, T13, T21, T22, T23, T27, T30, T31, T32.
- R07: T03, T14, T16, T17, T22, T31.
- R08: T13, T20, T23, T24, T25, T26, T27, T30, T31, T32.
- R09: T28, T29, T31, T32.
- R10: T02, T03, T06, T07, T09, T28, T31, T32, T33.
- R11: T00, T01, T33, T34.

## Ordered task recipes

### T00 — Complete or explicitly waive Make/Stitch exports

- [ ] **Status:** pending; not dispatched.
- **Phase:** design/sign-off gate.
- **Dependencies:** none.
- **Requirements:** R11.
- **Inputs / allowed scope:** DESIGN.md; screens.json; Voiceish-prototype.html.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Restore authorized Figma Make/Stitch access; submit the DESIGN.md generation contract and exact screen inventory. Export every linked screen to runnable HTML. Compare routes, state fields and interactions with CONTRACTS.json. If still blocked, record the operator’s explicit waiver for authored HTML plus Figma Design; do not mark the exports complete.
- **Acceptance and focused verification:** 31 routes reachable; natural actions and review navigation work; exported provenance and service links recorded. A waiver is operator-authored, exact and attached to the gate.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T01 — Freeze authority and runtime configuration

- [ ] **Status:** pending; not dispatched.
- **Phase:** design/sign-off gate.
- **Dependencies:** T00.
- **Requirements:** R11.
- **Inputs / allowed scope:** kstore authority retrieval; approval record; provider model metadata.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Retrieve current Admin-Manual/project authority through kstore first. If unavailable, read the authorized local projection, report the gap and repair its verified ingest. Pin the product commit, architecture and checklist hashes. Verify requested glm-5.3-flash model availability and documented thinking-disable option using provider metadata. Obtain explicit operator sign-off and task token; issue no worker until every gate passes.
- **Acceptance and focused verification:** Approval binds exact files/product commit; provider capability proves requested model and disabled thinking. Missing model/configuration/sign-off is BLOCKED; no substituted model or guessed disable parameter.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T02 — Capture baseline and reproduce layout

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T01.
- **Requirements:** R01, R10.
- **Inputs / allowed scope:** source/web/dist; source/extension; source/package.json.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Create an isolated product checkout at the approved commit. Read applicable AGENTS.md. Run existing checks without changing them. Reproduce recipient clipping at short popup height and phone keyboard-open geometry; capture viewport metrics and synthetic screenshots. Record working pairing/SIM/send behavior as regression baseline.
- **Acceptance and focused verification:** Baseline test evidence and a reproducible geometry case exist. npm test from source and npm test from source/web pass or pre-existing failures are documented before changes.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T03 — Introduce typed recipient and per-thread draft model

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T02.
- **Requirements:** R01, R07, R10.
- **Inputs / allowed scope:** source/web/dist/core.js; source/extension/core.js; proposed shared domain module.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Define ThreadRef and immutable RecipientRef including device/SIM/address identity. Store drafts by thread key with recipient snapshot. Resolve chosen numbers explicitly; save and restore when switching. Share one contract across web and extension without implicit reassignment on contact-name changes.
- **Acceptance and focused verification:** A draft written for number A never appears under B; same contact with two numbers has separate drafts/histories; stale changed-number draft requests review. Unit fixtures cover SIM/device separation.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T04 — Repair web composer viewport

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T03.
- **Requirements:** R01.
- **Inputs / allowed scope:** source/web/dist/index.html; style.css; app.js.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Replace oversized workspace minimum height with header/history/composer grid and bounded inner scrolling. Repeat resolved name and full number in composer; associate accessible labels with input and Send. Handle visual viewport changes, safe-area and IME. Keep messages independently scrollable.
- **Acceptance and focused verification:** 320/390/768/1440 widths, 420px popup height, 200% text zoom and reduced viewport height show full destination beside editable input. No horizontal overflow or overlap; long names/numbers wrap.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T05 — Repair extension popup and full-tab composer

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T03.
- **Requirements:** R01.
- **Inputs / allowed scope:** source/extension/popup.html; popup.css; popup.js.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Apply the same recipient/composer invariant in popup and full-tab mode. Preserve selection and draft when popup is reopened. Keep transient notifications outside input geometry. Prevent Enter during IME composition from submitting.
- **Acceptance and focused verification:** Popup focus, long input, reopening and number switching keep visible correct recipient. Full-tab and compact popup use the same domain selection.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T06 — Version new capabilities without breaking v1

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T02.
- **Requirements:** R02, R05, R06, R10.
- **Inputs / allowed scope:** source/android/app/src/main/java/com/voiceish/sim/Protocol.java; browser RPC adapters.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Define explicit v2 capabilities and typed error envelopes in the protocol specification. Negotiate each added feature; keep existing v1 status/messages/send unchanged. Enforce message size, SIM and pairing-generation validation at dispatch.
- **Acceptance and focused verification:** Old phone/new browser retains v1 SMS and clearly disables contacts/events. Unknown actions, invalid schemas and stale SIM/generation fail without side effects. Java/JS fixtures agree.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T07 — Add paged inbound history

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T06.
- **Requirements:** R04, R10.
- **Inputs / allowed scope:** SmsStore.java; Protocol.java; history cursor specification.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Implement keyset paging for pinned-SIM inbound provider records with scan-start upper bound, stable date/id ordering and bounded page size. Return coverage/excluded-unknown-subscription counts and resumable opaque cursor. Preserve capped v1 snapshot.
- **Acceptance and focused verification:** History exceeding 300 messages is scanned without dropped/duplicated pages. Concurrent new SMS does not destabilize the bounded scan. Wrong-SIM/missing-subscription records never cross identities.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T08 — Persist inbound event journal and enrollment baseline

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T07.
- **Requirements:** R02.
- **Inputs / allowed scope:** SmsStore.java; BridgeService.java; new inbound event repository.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Add transactional schema migration for event IDs, epoch and cursor. Observe provider changes plus bounded fallback rescan while bridge runs. Seed baseline on new enrollment; derive one inbound event per completed provider message. Implement retention and explicit stale-cursor gap.
- **Acceptance and focused verification:** Initial history produces no notification flood; multipart/provider-change bursts deduplicate; restart resumes; journal trimming returns a typed gap and reconciliation coverage, not silence.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T09 — Implement authenticated local event socket

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T06, T08.
- **Requirements:** R02, R10.
- **Inputs / allowed scope:** LocalServer.java; Crypto.java; event stream codec.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Add v2 WebSocket upgrade on existing host/port and local-peer boundary. Require encrypted authenticated subscribe before data; bind epoch/session/SIM, direction-separated AAD and nonce policy. Add bounded clients, heartbeat, frame-size/time limits. Use reviewed primitives and pinned dependencies where necessary.
- **Acceptance and focused verification:** Unauthenticated/malformed/replayed/oversized frames receive no payload; only current paired local client gets events. Encryption vectors and actual socket integration pass. Listener/subnet scope is unchanged.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T10 — Run inbound client in MV3 background

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T09.
- **Requirements:** R02.
- **Inputs / allowed scope:** source/extension/background.js; manifest.json; new event-client.js.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Own event subscription in the service worker. Persist cursor/pending dedup metadata, send encrypted heartbeat within 20 seconds, reconnect using alarms with bounded backoff. Restore registrations on startup; close stale pairing/SIM sessions. Add documented alarms permission.
- **Acceptance and focused verification:** Popup/page closed still receives sample phone events. Worker termination/restart, offline/reconnect and stale epoch recover without normal duplicate alerts. No setInterval-only lifecycle assumption.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T11 — Deliver and route Chrome notification previews

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T10, T03.
- **Requirements:** R02.
- **Inputs / allowed scope:** background.js; manifest.json; NotificationRouter; notification setup UI.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Add notifications permission, sender/number/body preview, preview-hide option and test notification. Use deterministic event notification IDs and record failures honestly. Click focuses a controlled extension tab at exact ThreadRef; show fallback unread/banner when blocked.
- **Acceptance and focused verification:** Closed popup incoming SMS creates expected preview. Clicking opens the correct number without sending. Permission denial, DND user check and click-after-restart are documented; dismissed preview never changes draft.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T12 — Add open-page incoming banner and capability guidance

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T11, T04.
- **Requirements:** R02.
- **Inputs / allowed scope:** source/web/dist/app.js; site-bridge.js; direct-browser engine.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Display new incoming event banner in its own layout row; retain active draft and recipient. Deduplicate UI/OS presentation through the notification policy. Explain that closed-page background alerts require extension; expose actual last-seen/offline status.
- **Acceptance and focused verification:** Receiving for A while typing to B preserves B and its draft; Open message explicitly moves to A. Direct page does not claim closed-page background delivery.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T13 — Define contact schema and safe migration

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T06.
- **Requirements:** R03, R05, R06, R08.
- **Inputs / allowed scope:** new Android ContactStore; SQLite schema; CONTRACTS.json.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Create contacts/addresses/source mappings/changes/outbox/conflicts tables with constraints and transaction-backed migrations. Separate address identity from display names. Protect app-private data; preserve pairing/SMS receipts/drafts through upgrade.
- **Acceptance and focused verification:** Migration from existing 0.1.4 DB succeeds and rollback retains data. Multiple numbers and shared numbers are representable; source identity is account-qualified.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T14 — Implement canonical number parsing

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T13.
- **Requirements:** R07.
- **Inputs / allowed scope:** Android PhoneAddress normalizer; Gradle dependency configuration; JS parity fixtures.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Pin a reviewed libphonenumber Java dependency and metadata version. Preserve raw values; require confirmed region for national parsing; distinguish short codes, extensions and alphanumeric/non-dialable senders. Supply canonical keys to browsers. Add dependency-aware build path rather than pretending SDK-only builder resolves jars.
- **Acceptance and focused verification:** Formatting variants link for valid regional numbers; country ambiguity/service-code/extension fixtures remain separate. No last-seven-digit matching; parser parity/build verification passes.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T15 — Read Android contacts and observe changes

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T13, T14.
- **Requirements:** R05.
- **Inputs / allowed scope:** new AndroidContactsAdapter; MainActivity.java; AndroidManifest.xml.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Request READ_CONTACTS only from import/lookup enrollment. Read selected accounts with aggregate lookup and raw-contact/source IDs, all numbers and labels. Record writable capabilities. Observe changes and page/reconcile snapshots.
- **Acceptance and focused verification:** Import, Android-side rename/number change, aggregation changes, read-only account and denial produce correct derived views; texting still works without contacts permission.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T16 — Expose contact read API and search

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T15.
- **Requirements:** R03, R07.
- **Inputs / allowed scope:** Protocol.java; ContactRepository RPC; web/extension contact index.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Implement versioned contact list/get/search with paging, source capabilities and canonical-address lookup. Build derived client search across name and all number forms. Invalidate on contact events while preserving selected actual number.
- **Acceptance and focused verification:** Search finds punctuation variants and alternate numbers. Shared-number results remain candidates; message thread identity never changes with contact name.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T17 — Build address-book and number-picker screens

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T16, T04, T05.
- **Requirements:** R03, R07.
- **Inputs / allowed scope:** web/extension contacts views; screens contacts/detail/number-picker.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Adapt reviewed HTML and Figma layouts into existing product views. Add address-book navigation, source badges, details and explicit per-number Text action. Unknown thread offers Add and Link. Reuse shared RecipientController.
- **Acceptance and focused verification:** One contact with two numbers requires selection, shows chosen number by input and restores separate draft. All prototype routes have corresponding reachable production views.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T18 — Preview and create local received contacts

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T17.
- **Requirements:** R03.
- **Inputs / allowed scope:** ContactStore write API; contact-add/contact-link views.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Create revision-aware local contact apply/preview with operation ID. Add unknown sender as new identity or operator-selected existing contact. Preview destinations and retain original address. Reject duplicate/ambiguous automatic association.
- **Acceptance and focused verification:** Retry same operation is idempotent; blank name/invalid address errors inline. Linking preserves SMS history and all existing source identities.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T19 — Review all received numbers

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T07, T18.
- **Requirements:** R04.
- **Inputs / allowed scope:** received-number scan service; bulk-review UI.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Scan paged inbound history, canonicalize and collect unique addresses, classify existing/unknown/service/ambiguous identities, track scan coverage and progress. Allow selection/exclusion and resume. Apply selected local contacts under batch operation ID.
- **Acceptance and focused verification:** More than 300 records, duplicate formatting and short codes yield accurate unique candidates. Cancel/resume and repeated apply create no duplicates; original SMS records unchanged.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T20 — Write Android source records with verification

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T18, T15.
- **Requirements:** R05, R08.
- **Inputs / allowed scope:** AndroidContactsAdapter mutation path; runtime WRITE_CONTACTS flow.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Request WRITE_CONTACTS at chosen write enrollment. Apply field-aware patches to writable raw contact or create under explicit target account. Preserve unknown fields; validate source revision and re-read provider result. Record ambiguous create outcome for reconciliation.
- **Acceptance and focused verification:** Permission denial/read-only/error leaves pending state. Create/update re-read matches patch, retries do not duplicate contact, and source account never substitutes.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T21 — Enroll native Google authorization

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T13.
- **Requirements:** R06.
- **Inputs / allowed scope:** new GoogleAuthAdapter; Android Gradle/config; google-import view.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Verify current official native authorization SDK contract and supported token renewal. Register intended OAuth client/package/signing identity through authorized configuration. Add selected-account read-only enrollment and incremental write consent. Return status/account capabilities to browser; keep tokens on phone. Use Gradle for dependency-aware full variant.
- **Acceptance and focused verification:** Real account authorization succeeds; missing Play Services/client config, denied consent, revoked access and account mismatch are typed failures. No tokens/client secrets in browser, logs or source. Renewal evidence exists.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T22 — Import all Google contact pages

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T21, T14.
- **Requirements:** R06, R07.
- **Inputs / allowed scope:** GoogleContactsAdapter read path; import-review view.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Fetch People API connections pages using consistent masks and selected account. Persist complete snapshot and next sync token only at end. Link exact validated numbers, retaining Google resource/source etag and unresolved candidates.
- **Acceptance and focused verification:** Multi-page import preserves all phone numbers/labels and source identity. Mid-page failure retains resumable state without publishing incomplete sync token. Google-only/Android-linked candidates correctly distinguished.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T23 — Implement Google source mutations

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T22, T18.
- **Requirements:** R06, R08.
- **Inputs / allowed scope:** GoogleContactsAdapter write path; SyncOperation store.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Serialize mutations per account; use source etags and minimum field masks. Persist operation/result before declaring completion. Handle create uncertainty by reconciliation; updates/deletes require approved source target. Do not overwrite unrelated People fields.
- **Acceptance and focused verification:** Create/update/reviewed delete readback evidence passes; stale etag produces conflict; ambiguous create never blindly duplicates; revoked write consent keeps queue.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T24 — Establish source mapping and one write owner

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T20, T22, T23.
- **Requirements:** R08.
- **Inputs / allowed scope:** SourceLink ownership service; linked-source UI.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Map Google-backed Android raw contacts to Google resource identity when evidence supports it. Pick one write owner per logical source record. Use native Google sync ownership for mapped Android records; API ownership for Google-only records; hold uncertain pairs read-only pending review.
- **Acceptance and focused verification:** A local change to a mapped Google/Android identity produces one source mutation, not two. Missing mapping does not guess by name; source ownership visible in review.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T25 — Merge bidirectional changes and suppress echoes

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T24.
- **Requirements:** R08.
- **Inputs / allowed scope:** ContactSyncEngine; ContactChange/SyncOperation journal.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Implement three-way field merge using last-synced base, origin and version. Apply remote-only edits to merged view, enqueue authorized propagation, merge disjoint edits and create same-field conflicts. Detect echoed operations by mapping/version/hash. Persist sync policy per source/account.
- **Acceptance and focused verification:** Android→Voiceish→Google and Google→Voiceish→Android paths work under write-owner policy. Repeated cycles converge without duplicate contacts or infinite writes; conflict preserves both source values.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T26 — Render conflict and deletion decisions

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T25, T17.
- **Requirements:** R08.
- **Inputs / allowed scope:** sync-conflict/sync-review views; resolution API.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Show base/local/remote field values and provider destinations. Require explicit preferred value or postpone. Separate Unlink, Keep elsewhere and Delete everywhere; validate conflict base revision before applying resolution. Include multi-source deletion preview.
- **Acceptance and focused verification:** Stale resolution rejected; postponed conflict keeps data; unlink changes no provider record/SMS. No automatic cascading delete from a tombstone.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T27 — Recover sync after offline and expired tokens

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T25, T21.
- **Requirements:** R06, R08.
- **Inputs / allowed scope:** sync recovery scheduler; Google token/sync cursor state; offline UI.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Run durable outbox with bounded backoff and reconnect. On Google sync-token expiry, perform full paged reconciliation while preserving unsent edits and tombstones. On authorization expiry, stop writes and ask same-account reconnect. Respect delayed read-after-write visibility.
- **Acceptance and focused verification:** Offline edits survive process restart; seven-day token-expiry fixture triggers rescan; no account fallback, edit loss, false Synced badge or duplicate uncertain create.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T28 — Implement secure ephemeral QR pairing

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T06.
- **Requirements:** R09, R10.
- **Inputs / allowed scope:** Crypto.java; LocalServer.java; MainActivity.java; PairingAdapter.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Specify reviewed ephemeral key exchange, challenge/public key QR fields, expiry, endpoint/session binding and short comparison phrase. Use fresh approved primitives and Java/JS vectors. Keep permanent shared key off QR. Store confirmed pairing only after authenticated verification and correct SIM check.
- **Acceptance and focused verification:** Expired/replayed/mismatched/wrong-phone QR fails. Both screens show phrase/SIM; pairing is not marked ready on scan alone. Existing v1 compatibility remains explicit.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T29 — Build scanner and permission-led setup

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T28, T11.
- **Requirements:** R09.
- **Inputs / allowed scope:** pair scan/fallback/confirm/check screens; phone setup flow.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Request desktop camera on scan action; parse validated QR using a pinned decoder or supported browser capability with fallback. Show correct phone/SIM/phrase and finish reachability check. Offer advanced file/code fallback when camera unavailable. Keep SMS/contact permission requests just in time.
- **Acceptance and focused verification:** Phone→computer scan avoids long-string transfer on equipped desktop; no-camera/denied/unreachable/wrong-SIM states actionable. No relay/subnet changes or false completion.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T30 — Align native contact and status screens

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T26, T29.
- **Requirements:** R01, R05, R06, R08.
- **Inputs / allowed scope:** Android MainActivity and new contact/setup views.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Expose contact enrollment, account/source choice, sync queue/conflicts and bridge/notification status on phone using the same contracts. Provide Android contact creation/edit completion and native authorization return states. Preserve keyboard insets and explicit destination when composing is available.
- **Acceptance and focused verification:** Phone UI resolves imports/conflicts and displays true provider/permission states. Z Fold layout has no obscured controls or silent source substitution.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T31 — Run integrated synthetic regression suite

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T12, T19, T27, T30.
- **Requirements:** R01, R02, R03, R04, R05, R06, R07, R08, R09, R10.
- **Inputs / allowed scope:** source test suites; synthetic phone/provider adapters.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Run existing root/web/extension checks, new domain/provider/socket tests and responsive interaction tests. Exercise popup-closed MV3 termination, encrypted event replay, stale SIM, unknown send, bulk history and two-way conflict/expiry paths. Record test counts/commands rather than inferred success.
- **Acceptance and focused verification:** Existing and new relevant tests pass; event auth/subnet/pairing/send safeguards intact. No real SMS or contact write during automated tests.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T32 — Qualify actual phone and Chrome runtime

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T31.
- **Requirements:** R01, R02, R05, R06, R08, R09, R10.
- **Inputs / allowed scope:** operator-approved test number/account; Z Fold5; Chrome on target OS.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Arrange an explicitly authorized test number and isolated contacts; never use arbitrary contacts. Verify incoming preview with popup/site closed and phone asleep, route click, keyboard recipient, native Google/Android mutations/conflicts, SIM change and QR setup. Measure latency and idle/battery; record DND/browser-exit boundaries.
- **Acceptance and focused verification:** Physical runtime evidence covers full requirements and permission recovery. Synthetic success alone cannot close this task. All actual SMS/account writes are specifically authorized.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T33 — Generate one coherent release and reproducible builds

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T32.
- **Requirements:** R10, R11.
- **Inputs / allowed scope:** canonical release manifest; build/export/package scripts; source/docs/BUILD.md.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Select operator-approved next version mapping; generate all platform versions and documentation from one manifest. Run dependency-aware signed Android build, embed exact payload in setup app, package extension, regenerate standalone HTML and complete-source bundle including build instructions and checksums. Never overwrite old immutable release filenames.
- **Acceptance and focused verification:** APK, extension ZIP and complete sources ZIP agree with manifest; signatures/payload hashes/extension CSP/external assets checked. Rebuild instructions produce equivalent source-derived outputs.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

### T34 — Record verified kstore delivery and release report

- [ ] **Status:** pending; not dispatched.
- **Phase:** implementation after sign-off.
- **Dependencies:** T33.
- **Requirements:** R11.
- **Inputs / allowed scope:** verified kstore client; development repo projection; release evidence.
- **Worker:** requested `glm-5.3-flash`; thinking disabled only through verified provider control; one task, no delegation.
- **Authority:** approved architecture/checklist hash, baseline commit and per-task token; common ledger metadata applies.
- **Recipe:** Write updated architecture/checklist/results into canonical kstore with exact PostgreSQL readback and indexing status. Materialize authorized projections on .87, verify byte hashes and commit/push scoped files. Record links and actual revision/commit identifiers; report any unavailable destination as pending. Publish only under separate release authorization.
- **Acceptance and focused verification:** Exact literal hashes, remote files and GitHub commit receipts exist. No HTTP response alone counted as ingest verification; no deployment inferred from pushed source.
- **Outputs:** scoped diff/commit; exact checks and evidence; structured worker result; independent evaluator score; verified kstore receipt and projection/push status.
- **Failure / rollback:** common failure route and scoped rollback above; do not start dependencies or successor work to conceal a failure.

## Current review and persistence ledger

| Item | State | Evidence needed to close |
|---|---|---|
| Source lineage | Identified | SIM 0.1.4 repository and manifest 0.2.2 recorded in architecture. |
| Linked review HTML | Authored fallback | 31-route interaction/layout validation report; no real runtime effects. |
| Editable Figma Design | Created | Companion file contains editable text/components and navigation; distinct from Make. |
| Figma Make | Blocked | Browser returned Site Unavailable; actual generation/export or explicit waiver pending. |
| Google Stitch | Blocked | Google sign-in cancelled; actual generation/export or explicit waiver pending. |
| Architecture/checklist | Proposed | Operator discussion/sign-off for exact revision/hashes. |
| Requested GLM worker mode | Unverified | Provider-supported exact model/disabled-thinking evidence. |
| .87 checkout projection | Pending | Authorized connection and correct development checkout/path, file hashes and commit/push. |
| Literal kstore ingest | Pending | Repo-owned verified-client receipt and PostgreSQL exact readback. |
| Product implementation/release | Not started | Approval gates and every acceptance task remain open. |

Saving this proposal in GitHub or attaching it for discussion does not close any
runtime/implementation gate. The final delivery receipt identifies actual saved
locations and hashes without rewriting the frozen plan later.
