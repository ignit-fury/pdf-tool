# Document Navigation Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline; one fresh final review. Track steps below.

**Goal:** Add safe local PDF outline navigation and an atomic exact-byte edit-history navigator.

**Architecture:** PDF.js resolves bookmarks from the committed proxy. Bounded pure
outline helpers and a lifecycle-aware panel reject stale results. History jumps move
existing snapshots through the existing transition semantics and prepare/publish once.

**Tech Stack:** Existing React/PDF.js/Vite and Node tests; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-29-document-navigation-design.md`.

## Global constraints

- Browser-only; no PDF rewrite/upload for navigation, persistent state or deployment.
- Keep original bytes, current-source binding, existing snapshot/memory admission,
  cache/password/signature behavior, undo branching and all prior release gates.
- Outline limits1000 nodes/16 levels/titles256/name2048; no external actions.

## Review focus

- Named destinations that fail, point outside the document, or resolve after source change.
- Deep/cyclic/large outline trees and external JavaScript/URL/attachment actions.
- Jumping past multiple text/page/image states and returning through Redo.
- Failed/stale restoration and branching after a jump without losing retained entries.
- Narrow panels, keyboard focus, previews/drafts and duplicate source-byte ownership.

## Task 1 — Local document outline

Files: new `client/src/viewer/outline.mjs`, `outline.test.mjs`, `OutlinePanel.jsx`.

- [x] RED tests for bounded nested outlines, safe destinations, cycle/depth limits,
  malformed/external data and stale named/page-reference resolution.
- [x] Implement `normalizeOutline(tree)` and `resolveOutlinePage(pdf,destination,isCurrent)`;
  return finite outcomes, use only local PDF.js methods, and check freshness after awaits.
- [x] Build nested collapsible list, empty/error/retry states and local disclosure.
- [x] Run `node --test client/src/viewer/outline.test.mjs`; observe all cases pass.
- [x] Commit only task-owned files after verification.

## Task 2 — Atomic history navigation and viewer integration

Files: new `client/src/viewer/history.mjs`, `history.test.mjs`, `HistoryPanel.jsx`;
modify `App.jsx`, `viewer.css`.

- [x] RED tests for timeline labels/current/future and multi-step undo/redo round trips,
  source/recipe/metadata identity, invalid targets and immutable input stacks.
- [x] Implement `historyRows(past,future)` and `historyJump({past,future,current},position)`
  using existing `historyTransition` action semantics; allocate no new PDF buffers.
- [x] Integrate Outline/History panels with clear draft/preview cancellation, current PDF
  binding, focus and bounded responsive styles. No unrelated visual redesign.
- [x] Extend `restoreHistory` to prepare one chosen retained snapshot and publish once;
  keep admission, failure/staleness guards and keyboard Undo/Redo on the same path.
- [x] Run focused history tests, full client tests and production build; commit owned files.

## Task 3 — Integrated proof and documentation

Files: new browser fixture/script and verification report; README/planning updates.

- [x] Actual browser: nested explicit/named destinations, no upload, empty outline,
  stale response after close/open; mixed edits/history jump/Redo/new branch, exact
  downloads and retained source content; responsive/focus behavior.
- [x] Run appropriate viewer/text-box browser regression and affected native download
  validation; no full backend rerun unless backend behavior changes.
- [x] Fresh final review; reproduce/fix real issues once, record any remaining limits.
- [x] Update evidence, plan checkboxes and project state; commit explicit owned paths.

## Execution ledger

Baseline `83ba6e2`, clean `feat/document-viewer-editor`. Existing isolated feature
branch retained; no worktree duplication or dependency installation needed.
Ruling: execute the scoped plan without another design approval — the user's existing
instruction explicitly requests a plan followed by execution and repeated next phases.
Ruling: destination page only, preserving current zoom — avoids unsupported PDF actions
and keeps navigation coordinated with the continuous viewer.

Task1 complete:4 bounded outline/destination tests observed RED then GREEN.
Task2 complete:3 timeline/jump tests observed RED then GREEN; full187 client suite
and build pass. Browser-confirmed panel/focus/error integration corrected.
Task3 complete:3 new browser journeys,6 earlier viewer/text-box journeys and actual
PDF download checks pass. Fresh review found2 Important issues, each reproduced
RED then fixed and GREEN; no deferred findings.
Ruling: navigation defers automatic analysis and stops indexing — avoids triggering
cache-recovery upload through ordinary page-visibility effects; explicit Edit/Find
resumes it. Existing in-flight work is not destructively canceled.
Ruling: synthetic fixture declares1.6 rather than1.7 for its minimal Base14 font;
the unchanged strict validator passes. No production writer/validation change.
Final evidence: `docs/verification/document-navigation-2026-10-29.md`.
