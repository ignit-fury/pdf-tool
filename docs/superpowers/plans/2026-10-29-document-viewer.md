# Document Viewer Editor Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for isolated engine/image tasks and superpowers:executing-plans for the integrated viewer. Track verified completion here.

**Goal:** Make the existing PDF document the primary editing surface, with continuous pages, safe inline edits, formatting, image management, exact Undo/Redo and single/batch replacement.

**Architecture:** Retain authoritative server run IDs and atomic content-stream recipes. Add bounded continuous PDF.js page shells and a positioned draft input. Extend existing browser page-worker/history transactions; no alternate text writer.

**Tech Stack:** Existing React 18, Vite, PDF.js, @cantoo/pdf-lib, FastAPI, pikepdf, playa-pdf, fontTools and uharfbuzz. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-29-document-viewer-design.md`; detailed user request of 2026-10-29.

## Global constraints

- No ordinary text white-box/annotation output, automatic upload on open, persistent server storage, runtime AGPL, reduced worker/CSP protections or deployment.
- Original/source/current bytes and full recipe are authoritative; retain existing cache-loss recovery.
- Preview and apply must validate; refusals leave bytes/history unchanged. No clipping, text loss or simulated successful replacement.
- Prefer supported working slices over unreliable arbitrary-PDF reflow. Document unsupported multiline/movement/foreign-image cases.
- Preserve page tools, merge, image admission, search exclusions and all exports.

## Review focus

- Rotated/cropped/nonzero-origin/UserUnit pages: inline geometry must agree with authoritative boxes; unsupported rotated editing must refuse clearly.
- Long PDFs: offscreen canvases must unmount; document navigation, zoom and search must still land on the requested page.
- Stale drafts/late replies after scrolling, replacement, close, Undo or options changes: never publish to the wrong run/session.
- Undo/Redo retained bytes and new mutation after Undo: enforce both memory and branching history limits.
- Source images shared/reused across streams: never remove/rewrite unrelated content using unverifiable image ownership.

## Task 1: Continuous viewer and inline editing (root)

Files: `client/src/Viewer.jsx`, new `client/src/viewer/*`, `App.jsx`, scoped viewer CSS, tests.

- [x] Write/run failing geometry/render-window and inline-draft validation tests.
- [x] Add continuous shells, visible-page tracking, explicit navigation and bounded canvas/text layers. Keep PDF.js selection/read mode and source-issued edit targets.
- [x] Add positioned textarea with source-based typography, contextual font/color/weight/style controls, Preview/Apply/Cancel and refusal guidance. Keep existing recipe validation/publication.
- [x] Coordinate selection/page changes, zoom, focus, keyboard shortcuts, document close and actual-output rerender.
- [x] Verify client tests/build and actual multipage browser editing/scroll/zoom/refusal.

## Task 2: Safe formatting and expansion (engine worker)

Owned files: `engine/recipe.py`, `engine/rewrite.py`, `engine/fit.py` if necessary, `server/worker.py`, relevant Python tests. No frontend changes.

- [x] Inspect source state/rewrite geometry, write RED tests for source formatting metadata and supported bounded font-size/character-spacing changes.
- [x] Implement only cases that retain searchable text, actual glyph metrics and following content positions. Restore font/spacing state after edited instructions and retain current preflight/refusal guards.
- [x] Expose additive run formatting metadata (`font_size`, `bold`, `italic`, `color` when known; no fabricated values).
- [x] Existing width ladder handles longer/shorter strings; refuse unsafe overflow/newlines/reflow with finite reasons and alternatives. Test bad bounds, adjacent text, source hash and unchanged source bytes.
- [x] Verify focused rewrite/fit/style/preview/search tests and strict typing. Report exact supported style field names/limits to root before UI integration.

## Task 3: Exact mixed Undo/Redo (root)

Files: `App.jsx`, `pageOps/documentHistory.mjs` and tests, session helpers if needed.

- [x] Add RED tests for two-stack restoration/admission/new-mutation branch clearing.
- [x] Capture current snapshot before Undo/Redo, prepare PDF before publication, restore analysis/UI without eager upload, include both stacks in byte/entry budgets.
- [x] Add toolbar and Ctrl/Cmd+Shift+Z/Ctrl+Y outside text inputs; retain native draft Undo inside textarea.
- [x] Verify exact-byte text/page/batch Undo/Redo and new edit clears Redo.

## Task 4: Managed native image operations (image worker + root UI)

Worker-owned files: new `client/src/pageOps/managedImages.mjs`/tests, `images.mjs`, `pdfDocument.mjs`, `pdfJob.worker.mjs`. Root owns `Viewer.jsx`, `App.jsx`, image toolbar/handles.

- [x] RED tests: native managed placement retains unrelated streams; verified move/resize/rotation/replacement/deletion; reject malformed/spoofed ownership/foreign images; preserve signatures/password checks and caps.
- [x] Provide `managedImages` additive page metadata and an isolated worker command for exact managed-image updates, preserving existing image/page APIs.
- [x] UI: direct selection, pointer move/resize preview, aspect lock default, numeric dimensions/position, rotation, replacement picker, Apply/Cancel/Delete confirmation. Existing validated PNG/JPEG/WebP decode and new-page placement remain usable.
- [x] Verify actual browser operations, exact Undo/Redo, native rendering/searchable original text and existing image/page tests.

## Task 5: Replace One/All and truthful walkthrough (root)

Files: `find/FindPanel.jsx`, `App.jsx`, new `find/walkthrough.mjs`/tests and single-occurrence helper/tests.

- [x] RED tests for replacing only the active occurrence, complete-index prerequisite, preserved earlier style/recipe, post-commit tour pause/resume/stop/reduced motion and stale-session cancellation.
- [x] Add Previous/Next and explicit Review/Replace One versus Review/Replace All using existing candidate/preview/atomic application.
- [x] Capture accepted occurrence targets before commit, then show the real final PDF sequentially with honest progress/skipped/refused counts. No per-occurrence rewrite or simulated pre-commit result; stop leaves committed batch intact and Undo remains atomic.
- [x] Verify multipage local browser search, one/all results, actual text output and one-step Undo/Redo; check reduced motion.

## Task 6: Integration, review and evidence (root + fresh reviewer)

- [x] Run full client/Python regression, strict typing, build, Unicode/license checks; target native fidelity checks after engine/image changes.
- [x] Browser journeys: scroll, inline short/long edit, source font controls/fit refusal, size/color/weight/style, image operations, search One/All/tour, history, password/cache loss, page operations/export, 320/760px and zoom.
- [x] Fresh source review of final diff; fix confirmed integrity/security/stale-state issues and rerun affected checks.
- [x] Update README, roadmap/state and concise verification report with actual results and explicit unsupported cases. No deployment or claim of universal PDF reflow.

## Execution record

Baseline: `25775b1`, clean checkout. Prior verified baseline: 147 client tests, 760 selected Python tests covered (OS exceptions separately rerun), 38 strict-typed files. Existing virtualenv script shebangs point to an old checkout: always use `.venv/bin/python -m pytest` / `-m mypy`.


2026-10-29 execution complete within the stated conservative scope. All six tasks
are delivered. Source size growth, multiline/reflow/movement and unowned source
image editing remain explicit refusals, as anticipated in the design.

Validation: 787 selected Python tests plus one mandatory cross-runtime test;
170 client tests; 12 native export/removal gates; 38 typed files; build, license
gates and Unicode checks. Automated local Chromium scripts cover inline edits,
formatting, geometry, images/pointer handles, One/All, walkthrough, Undo/Redo,
responsive/refusal and Unicode-password/cache-recovery transport.

Independent integration review reproduced four defects; all fixed with RED/GREEN
regressions. Full G2a regression also exposed redundant Tf wrappers; implementation
corrected without weakening the gate. Detailed evidence and limitations:
`docs/verification/document-viewer-2026-10-29.md`. No deployment/new dependency.
