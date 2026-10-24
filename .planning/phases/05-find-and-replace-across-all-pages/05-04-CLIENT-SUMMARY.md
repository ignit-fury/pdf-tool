---
phase: 05-find-and-replace-across-all-pages
plan: 04
segment: task-1-client
status: client-complete-only
subsystem: client-transactions
completed: 2026-10-24
provides:
  - Exact reviewed full-recipe apply through the ordinary endpoint
  - Transactional PDF preparation before viewer, output and history publication
  - One batch history unit with existing full-recipe undo
key-files:
  created: [client/src/find/replaceAll.mjs, client/src/find/replaceAll.test.mjs]
  modified: [client/src/App.jsx]
---

# Phase 5 Plan 4 Task 1: Client Apply Transaction

**A current successful review applies once, then publishes the prepared PDF and one whole-recipe undo entry together.**

This segment completes **Task 1 only**. Backend integration, the full bounded-worker
performance proof, three-renderer G4 and actual browser verification remain owned by
the orchestrator and their assigned executors. This file does not mark plan 05-04 or
Phase 5 complete.

## Implementation

- `applyReviewedReplacement` accepts the existing immutable Review and injected App
  request/loading/commit callbacks. It rejects stale keys, failed or incomplete reports,
  duplicate recipe IDs, zero-change batches and missing signature acknowledgement before
  requesting mutation. The accepted complete recipe is cloned and frozen before awaiting.
- After the ordinary apply response, the helper checks current session/key/generation,
  requires successful PDF output, prepares the viewer, checks freshness again and invokes
  one synchronous commit. Refusal, transport/load failure and stale completion publish no
  output or history; a prepared stale viewer is disposed.
- App's existing `busyOwnerRef` synchronously locks batch apply, single-run apply and undo.
  A duplicate click cannot enter a second mutation. Completion releases only its owner.
- `prepareViewer` retains the current published document until the new PDF is loaded and
  still current. `publishViewer` performs the final current-state check and swaps viewers.
  Single-run apply and undo use this same transaction boundary.
- The panel's existing optional apply callback is connected to `applyBatch`, with exact
  accepted counts and the existing signature gate. Success preserves query/options,
  recomputes matches through committed recipe overlays and clears all previews.
- Each successful batch calls `commitRecipe` once. `Undo replacements` and the existing
  Ctrl/Cmd+Z handler outside text inputs restore the complete prior recipe, including earlier
  text/font/style edits. Native input undo is unchanged. Failed undo keeps current bytes and
  history. Source-address refusals require an index refresh.

## Contracts for Browser Verification

- Pure helper: `applyReviewedReplacement({review,currentKey,isCurrent,acknowledged,signed,
  requestApply,loadOutput,commit})` returns `applied`, `refused`, `failed`, `stale` or `blocked`.
  `currentKey` may be a callback. `requestApply` receives only the captured full recipe;
  `loadOutput` prepares the returned encoded PDF; `commit` synchronously publishes it.
- App: `applyBatch` captures target/version/prior state under `beginWork('batch-apply', ...)`.
  `currentReview` and `batchKeyRef` gate readiness. Existing `documentRequest` retains source
  recovery, password headers, queueing and signature acknowledgement.
- `FindPanel` receives `onApply={applyBatch}` and `applyAllowed` only for a current successful
  complete-document review with acknowledgement where required.
- Latest built JavaScript asset: `client/dist/assets/index-CQEYbvne.js`. Reload the local
  test page to load this build; an already open page retains its older JavaScript.

## Verification

- `npm --prefix client test`: **40 passed**, including six apply-transaction tests and all
  existing search, builder, indexing, preview and session tests.
- `npm --prefix client run build`: **passed** (43 modules). Existing bundle-size advisory
  remains; no dependency or lockfile changed.
- `git diff --check` for owned client files: **passed**.
- Installed pdf.js 6 declarations confirm loading-task completion returns a document and
  task destruction returns a promise. No new pdf.js API or external runtime dependency was
  introduced. Context7 MCP/CLI were unavailable; installed package declarations were used.
- No browser or Python worker benchmark was run by this executor, avoiding contention with
  the orchestrator's browser and the engine's strict timing check.

## Commits and Scope

- Existing RED: `ae32247` — transaction, failure, stale completion and prior-recipe undo tests.
- GREEN: `f269a1e` — helper plus App transactional publication, apply and undo wiring.

The continuation preserved and completed predecessor work instead of reverting it. Viewer
preparation was shared with single apply and undo because publishing a stale viewer would
violate the same atomicity requirement. No endpoint, authentication, persistence or logging
surface was added. State/roadmap/requirements are left to the orchestrator as assigned.

## Known Stubs

None in Task 1. Remaining plan tasks are verification work, not client placeholders.

## Self-Check: PASSED

The helper, tests and App exist; RED and GREEN commit hashes are present. Test/build claims
above are from this continuation's actual commands. No deployment occurred and Phase 4
Linux/container/CDN release gates remain open.
