---
phase: 06-page-ops-and-merge
plan: "05"
subsystem: client-workstation
tags: [react, local-first, worker, exact-history, page-tools, image-placement, heic, tdd]
requires:
  - phase: 06-01
    provides: Local PDF inspection/transforms, snapshot admission, transaction and terminating worker facade
  - phase: 06-02
    provides: Explicit image-only HEIC conversion boundary
  - phase: 06-03
    provides: Safe local PDF merge and serializable import review
  - phase: 06-04
    provides: White native image decode and physical-point image writing
provides:
  - Local PDF opening with separate protection/geometry metadata and explicit Analyze text consent
  - Controlled page, merge, image and HEIC review controls with real viewer draft previews
  - One owner and exact document history across text, batch replacements, page work and local Undo
  - Independent original/current/replay-baseline byte ownership and fresh restored session controllers
affects: [06-06, PAGE-01, PAGE-02, PAGE-03, PAGE-04, PAGE-05, PAGE-06, PAGE-07, PAGE-08, PAGE-09]
tech-stack:
  added: []
  patterns: [prepare-before-publication, explicit-analysis-consent, native-controlled-forms, exact-local-undo]
key-files:
  created: [client/src/pageOps/pdfJob.worker.mjs, client/src/pageOps/PageOpsPanel.jsx]
  modified: [client/src/App.jsx, client/src/session.mjs, client/src/session.test.mjs, client/src/Viewer.jsx, client/src/style.css]
key-decisions:
  - Keep localMetadata separate from analysis consent and metadata; only Analyze text uploads a new PDF baseline.
  - Restore exact snapshots locally with fresh controllers/queues and defer restored analysis until explicit text interaction.
  - Admit unique known snapshot backing-store copies before allocation, refuse limits without evicting history, and retain the existing larger server output allowance.
  - Keep HEIC selection local; Convert sends only the raw selected image and validates the bounded returned PNG before local placement.
requirements-completed: [PAGE-01, PAGE-02, PAGE-03, PAGE-04, PAGE-05, PAGE-06, PAGE-07, PAGE-08, PAGE-09]
duration: approximately 30min
completed: 2026-10-25
---

# Phase 6 Plan 5: Local Workstation and Mixed Exact Undo Summary

**PDF opening, page edits, merge and image placement run locally behind one prepared-publication owner, while explicit text analysis and image-only HEIC conversion retain separate server boundaries.**

All three implementation tasks are complete. Requirement IDs above record the integration surface delivered by this plan. Actual observed network, native browser layout/codec/keyboard and three-renderer acceptance belong to plan 06/G5; Node tests and builds do not establish those observations.

## Task Commits

| Task | RED | GREEN | Result |
| --- | --- | --- | --- |
| 1: Local opening and explicit analysis | `dc6900a` | `94ee73d` | Fresh local session construction/restoration and copy prediction; local worker metadata and explicit analysis gate |
| 2: Controlled page/import/image UI | — | `4c58eb4` | Native page controls, signature gates, exact disclosure, import/placement forms, actual canvas draft overlay and responsive styles |
| 3: Mixed transactions and Undo | `343cd8b` | `5c6168c` | Closed-session regression, mixed snapshot assertions and complete shared-owner wiring; real import preview and explicit raw HEIC conversion |

RED session runs were observed failing before their implementations. Task 1's missing-export RED failed module loading, then all lifecycle assertions passed. Task 3's additional regression reproduced a closed session invoking upload; the mixed snapshot test passed against the already delivered snapshot primitive and protects its integration contract. Native UI styling has no tests that merely mirror JSX.

## Delivered Behavior

- Pages is initial. Opening reads bytes and renders via pdf.js, then inspects password/signature/encryption/geometry inside the concrete module worker. It never uploads. Rail visibility/selection, panel entry and edit-mode selection cannot request analysis before consent. Text panels show the approved Analyze text gate.
- `openedBytes` stays independent and immutable by ownership for original download. `bytes` is current display/download state; `sourceBytes` is the immutable baseline for ordinary full-recipe text requests and cache recovery. Successful local materialization rebases only the latter two, clears recipes/jobs/run addresses/index/search/previews and revokes analysis.
- `pdfJob.worker.mjs` dispatches inspect, transform, import inspection, merge and image writing. Cantoo loads/saves occur in that worker; the existing runner clones disposable buffers and terminates each job on success/failure/abort/deadline, using fixed caller error codes. Native image decode/canvas and pdf.js rendering remain their documented main-thread boundaries.
- Blank before/after, earlier/later/numeric move, clockwise rotation and inline protected deletion are wired. Geometry and inheritance appear before mutation; page selection follows core results. Keep page restores Delete focus. Page success restores focus to the panel heading and announces one result.
- PDF review includes a password input for encrypted imports, insertion position, unchecked normalization, real imported-page preview with previous/next controls, bookmark nesting, no-fields/no-collision/collision notices and separate imported-signature acknowledgement. Normalization previews fit the actual imported artwork within the selected target proportions.
- PNG/JPEG/WebP enter the bounded native decode path. The decoded white canvas supplies the preview, PDF PNG and temporary viewer placement. Numeric physical-point fields, visible checked aspect lock, linked bounds validation and destination/page changes use shared geometry helpers. New-page placement inherits the adjacent geometry.
- HEIC selection shows disclosure without fetch. Convert posts the selected raw file alone to `/images/heic-decode`, with image content type, no PDF/password/job/query payload, response type/stream bounds and normal local image validation. Dismiss conversion aborts client work and invalidates the draft without claiming already-running server work terminated. Production `HEIC_UNAVAILABLE` remains visible and is not hidden by a local fallback.
- Single text apply and reviewed batch apply retain their existing exact review and full-recipe API. They capture complete preceding document snapshots before requesting output and prepare replacements before publishing. Every successful page/text/image/merge action contributes one entry to the same stack.
- Undo prepares exact snapshot bytes, constructs a fresh controller/queue, then publishes and pops once. It restores the baseline/password/recipe/style/run selection/page/find state without network. Restored analysis is deferred so rail and indexing effects cannot upload during Undo; explicit subsequent text interaction may lazily reacquire an evicted source.
- Unknown signature detection disables rewriting; signed edits require current acknowledgement and imported signed PDFs require their own acknowledgement. The unlocked local-output notice precedes encrypted rewrites. Untouched original download preserves exact signature/encryption bytes.
- Closing/reopening aborts current requests and worker jobs, disposes image/import previews and viewer tasks, clears byte/password/history references, and invalidates old owners. Only the matching owner can clear busy state. Draft updates, first Delete click, no-op transformations, failures and refusals do not append history.

## Verification

- `node --test client/src/session.test.mjs client/src/pageOps/pdfWorker.test.mjs`: initial focused Task 1 run **19 passed, 0 failed**.
- Final `npm --prefix client test`: **114 passed, 0 failed**, recorded in `/tmp/06-05-client-tests.log`.
- Final `npm --prefix client run build`: **passed**, recorded in `/tmp/06-05-build.log`; existing Vite large-chunk advisory remains. The concrete module worker is a separate emitted bundle.
- `git diff --check`: passed. No owned tracked deletion occurred. Only authorized owned paths were committed with `git commit --only`; other agents' review/test changes were left intact.
- Focused new session coverage proves no synthesized jobs, fresh nonaborted restored controllers, exact UTF-8/password baseline retry, preference for sourceBytes over a different original, closed-session refusal, unique full-backing-store copy prediction, and repeated mixed byte/style/selection/find snapshot restoration.
- Existing worker and transaction tests supply adversarial stale/failed/preparation/admission coverage; existing font/style/find/cache tests remain green. Actual App/browser integration observations are explicitly downstream G5 evidence.

## Decisions and Deviations

**[Rule 1 — Bug] Closed sessions could start baseline restoration.** The Task 3 RED test observed an upload callback after abort. `withSourceRetry` now refuses an already-aborted controller before upload or retained-job calls and checks abort again before accepting restored job identity.

**[Rule 2 — Correctness] Snapshot restore must not immediately trigger old metadata effects.** Undo reconstructs fresh live session resources and marks restored analysis deferred. Explicit text interaction clears that gate, while automatic rail/default-page/index effects stay local during restoration.

**[Rule 2 — Correctness] Preserve server output allowance without weakening local input caps.** Local operations use the 50 MiB core admission, while shared application backing-store/history/transient accounting retains the existing larger text-server output allowance. An oversized current text output remains downloadable and undoable, but local page work returns a named refusal. History never silently evicts entries.

The configured `.Codex/get-shit-done/references/mandatory-initial-read.md` and project-skills-discovery reference were absent. Existing project/plan/context/pattern/research/UI artifacts, available TDD/verification skill instructions and actual delivered module interfaces supplied context. No dependencies were installed. SDK init/state were read; shared STATE/ROADMAP/REQUIREMENTS bookkeeping is reserved for the root orchestrator under explicit ownership instructions.

## Remaining Evidence and Limits

No implementation stub was found in the seven owned source/test files. Empty recipes, indexes and nullable drafts are actual lifecycle state and are connected to data sources/actions.

G5 must independently observe zero API traffic during the full local journey, explicit analysis/HEIC boundaries, rotated/cropped preview and native image pixels, responsive 320/760px keyboard/focus behavior, mixed App history and renderer fidelity. This plan does not claim those observations, Linux HEIC certification, G3 release closure, the earlier literal contract specimen check, or deployment. Browser memory accounting bounds application-owned buffers and known image pixel stores; it cannot guarantee the entire native parser/renderer heap.

## Self-Check: PASSED

All seven owned source/test paths and this summary exist. All five listed RED/GREEN/task commits exist in git history. The final 114-test suite, production build and whitespace checks passed. No generated owned untracked files or unexpected tracked deletions remain.
