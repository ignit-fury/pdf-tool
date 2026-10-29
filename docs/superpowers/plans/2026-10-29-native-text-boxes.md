# Native Text Boxes Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for owned native/API tasks and superpowers:executing-plans for the integrated client. Track actual verification below.

**Goal:** Insert, wrap, format, edit and remove transparent native text containers directly on PDF pages, with exact preview, collision protection and mixed Undo/Redo.

**Architecture:** Existing font/subset pipeline and isolated worker produce real PDF candidates from current materialized bytes. The client owns preview lifecycle, immutable source binding and atomic exact-byte publication. Original text edits retain their original engine.

**Tech Stack:** Existing Python/pikepdf/fontTools/uharfbuzz/PDFium and React/PDF.js/FastAPI; no new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-10-29-native-text-boxes-design.md` and the user's editor objective.

## Global constraints

- No white-box source replacement, rasterized text, persistent server documents, new runtime dependency, deployment, relaxed limits/CSP/isolation or automatic source reflow.
- Analyze/preview upload only on explicit action. Operations target current edited bytes; original bytes and recipe/source history remain recoverable.
- Actual preview PDF is never committed/downloaded as current until Apply. All stale, failed, canceled and overflow paths preserve bytes/history.
- Bounds: source50MiB, output48MiB, worker output80MiB, text10000 chars, boxes200, pages2000. Reuse existing process/admission limits.

## Review focus

- Source already edited/page-mutated or recovered from cache loss: new block operations must use its current bytes.
- Unicode shaping, trailing spaces, explicit paragraphs, long tokens and italic overhang: no lost/clipped glyphs or fabricated text.
- Nonzero crop origins, rotation/UserUnit and annotations/backgrounds: placement and overlap checks must use consistent physical geometry.
- Forged/modified/compressed owned metadata or shared font resources: update/remove only an exclusively verified drawing.
- Preview candidate lifetime, close/Undo/format changes and retained memory: no stale publication, URLs or disposed viewer reuse.

## Task 1 — Native layout and owned streams (native worker)

Own `engine/text_boxes.py` and `tests/test_text_boxes.py` only.

- [x] Inspect existing fonts/geometry/index/security helpers; write meaningful RED tests.
- [x] Implement finite list/upsert/remove spec validation and engine interface in the design.
- [x] Build complete multiline/wrap/spacing/alignment layout from bundled serialized font metrics, with glyph/ink guards and overflow facts.
- [x] Embed searchable native Type0 text in isolated verified streams. Handle compressed/reopened blocks and source resource sharing safely.
- [x] Protect placement against actual existing rendered content/annotations by default; explicit overlap is transparent new content. Preserve source bytes.
- [x] Verify native text/searchability/geometry/pixels/structural validity, malformed metadata/limits and strict typing.

## Task 2 — Bounded isolated API (API worker)

Own `server/app.py`, `server/isolation.py`, `server/worker.py`, `server/errors.py`, `tests/test_text_box_api.py`.

- [x] RED tests for route, current source/cache/password/signature transport, output/error shape and malformed/oversized inputs.
- [x] Add finite text-box action and job route using existing recipe-byte transport/body/concurrency/process limits. Warm native module before restriction if needed.
- [x] Delegate to engine function; map fixed errors only and preserve all existing actions/request shapes.
- [x] Verify actual worker execution, cache recovery, no persistent state, typing and existing API/worker contracts.

## Task 3 — Preview controller and direct UI (root)

Own new `client/src/textBoxes/*`, `App.jsx`, `viewer/*` integration and client tests.

- [x] RED lifecycle tests: current-byte upload/source binding, strict envelopes, stale/cancel/session changes, failure/no-commit, preview disposal/admission.
- [x] Reuse withSourceRetry in a separate current-byte context; list and preview use explicit actions.
- [x] Add page click insertion, multiline inline draft and contextual geometry/font/spacing/alignment/overlap controls. Load/select existing verified boxes.
- [x] Render exact candidate PDF with preview banner, expand-height guidance, Edit/Apply/Cancel and no working-PDF download ambiguity.
- [x] Publish exact candidate bytes as one history operation, re-inspect local metadata and invalidate analysis; preserve native image/source text workflows and Undo/Redo.

## Task 4 — Integrated evidence/review (root and fresh reviewer)

- [x] Add deterministic browser/native fixtures and actual browser scripts for insertion/wrapping/formatting/edit/remove, overlap/overflow, exact preview/cancel, history and stale source.
- [x] Verify actual downloads retain searchable new/original text and unrelated content; include rotated/cropped/UserUnit and annotation fixtures in native tests.
- [x] Run appropriate complete regressions/build/types/license checks once after integration; retain earlier release gates honestly.
- [x] Fresh integration review; reproduce/fix real findings with regressions; update README/state/roadmap and a concise verification report.

## Execution record

Baseline `35c9307`, clean feature branch `feat/document-viewer-editor`. Prior selected baseline:787 Python plus one added native integration test,170 client tests,12 export/removal gates,38 typed files. Use `.venv/bin/python -m pytest`/`-m mypy` because script shebangs reference an old checkout. No deployment.

Final evidence: `docs/verification/native-text-boxes-2026-10-29.md`. Independent
review completed; actual mixed browser/source/image failures were reproduced and
fixed. All tasks are delivered within the stated new-container scope; arbitrary
source reflow and prior external release gates remain explicitly open.
