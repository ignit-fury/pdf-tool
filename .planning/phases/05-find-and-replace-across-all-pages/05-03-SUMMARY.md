---
phase: 05-find-and-replace-across-all-pages
plan: 03
subsystem: ui
tags: [find, replacement-preview, accessibility, generations]
requires:
  - phase: 05-02
    provides: Canonical matcher and complete-recipe builder
provides:
  - Resumable all-page search with honest completed-page visibility
  - Per-occurrence selection, named refusals, font recovery and actual rewrite review
  - Real server-box navigation in the rendered PDF
affects: [05-04]
tech-stack:
  added: []
  patterns: [Controlled find panel, complete-page visibility snapshot, shared mutation owner]
key-files:
  created: [client/src/find/FindPanel.jsx]
  modified: [client/src/App.jsx, client/src/Viewer.jsx, client/src/style.css, client/src/session.mjs, client/src/session.test.mjs, client/src/find/indexing.mjs, client/src/find/indexing.test.mjs, client/src/find/preview.mjs, client/src/find/preview.test.mjs]
key-decisions:
  - Keep search page visibility separate from viewer-cache completion through completedPages.
  - Navigation and result pagination preserve batch review; replacement inputs invalidate its key.
  - Lost original run addresses require an explicit index refresh, not per-row fit filtering.
requirements-completed: [FIND-01, FIND-02, FIND-03, FIND-04, FIND-05]
duration: 29 min
completed: 2026-10-23
---

# Phase 5 Plan 3: Find and Preview Interface Summary

**All-page local search now exposes individual occurrences, safe opt-outs, readable refusals, explicit font recovery and an exact successful server rewrite preview before batch apply is connected.**

## Accomplishments

- Added the controlled `FindPanel`, preserving existing workstation columns and responsive layout. It has labeled native inputs, match-case and Unicode whole-word controls, indexing progress/stop/resume/retry, 50-row pagination, separately focusable inclusion and page-jump controls, linked reasons, active-run Before/After review and an empty-replacement removal notice.
- Counts explicitly distinguish partial results, changing selections, exclusions and blocked matches. Result announcements coalesce at 500ms. Unsupported `Intl.Segmenter` disables whole-word search with readable guidance.
- `fetchRuns` returns and promotes existing cached promises. The sequential producer uses the same two-slot queue, bounded retry, source recovery and password transport as normal viewing. Only controller-accepted `completedPages` enter search; late stopped responses may fill the viewer cache without altering stopped search results.
- Search uses current committed recipe overlays and original run IDs. Query/options reset exclusions; replacement/font changes preserve intentional exclusions and remove old replacement refusals. Review includes all prior recipe operations and only becomes ready after actual successful preview of its exact final recipe.
- App shares mutation ownership across single-run and batch preview, apply and undo. Canceling a batch preview invalidates its generation and releases only its owner; an older request's `finally` cannot clear a newer operation's busy state. Navigation and pagination do not clear a batch review.
- Results navigate to real one-based pages, wait for rendering, scroll server-issued run bounds through `viewportBox`, and retain a separate highlight in select/edit modes. Back to results restores row focus. No guessed substring geometry is used; excerpts mark exact matched source spans.
- A lost original address yields `SOURCE_MISMATCH`, clears cached/indexed review data and offers Refresh index. Unknown diagnostic codes receive readable generic refusal copy plus their named code. Unresolved Type1/CFF original-font rows also receive explicit font-choice guidance.

## Exported Contracts and 05-04 Handoff

- `createIndexingController({fetchPage,onProgress,isCurrent})` exposes `start(pageCount)`, `stop()`, `resume()`, `dispose()`. Progress is `{completed,completedPages,total,failedPages,status}`; both page arrays are sorted one-based numbers. `completedPages` is the authoritative search-visibility snapshot.
- `previewReplacement({buildCandidate,requestPreview,isCurrent,key})` returns a deeply frozen Review `{key,recipe,result,changes,refusals,selectedCount,changedPages,unchangedCount}`. `refusals` is a plain frozen run-ID record, not a Map. `changedPages` is an array. `SOURCE_MISMATCH` is thrown for lost original addresses. Actual failed-rewrite rows are filtered only from proposed overrides and the exact full surviving recipe is re-previewed.
- App stores `batchReview`, derives `currentReview` only when its key equals `batchKey`, and maintains `batchKeyRef` for asynchronous freshness checks. Keys cover session/source identity, committed recipe, query/options, replacement/font, exclusions, indexed match IDs and completeness.
- App's `beginWork(kind,label)` returns an owner or null when occupied. `finishWork(owner)` releases only that owner. `busyOwnerRef`, `editVersion`, `sessionRef`, `documentRequest`, `loadViewer`, `recipeState` and `setOutput` are the ordinary apply seams. Use kind `batch-apply`; run selection ignores mutations during that kind.
- `FindPanel` already accepts optional `onApply` and `applyAllowed`. 05-03 deliberately does not supply these props. 05-04 connects a validated current Review to one ordinary POST, one successful viewer replacement and one whole-recipe history commit, preserving signature acknowledgment.

## Task Commits

1. Controller RED/GREEN, authored by the orchestrator before this continuation: `d254e55`, `09dbd3b`.
2. Refusal/font RED: `8d99e0e`; panel/reason GREEN: `f643145`.
3. Lost-address RED: `864f594`; complete App/Viewer/controller integration GREEN: `8e7d40f`.

## Verification

- `npm --prefix client test`: **33 passed**.
- `npm --prefix client run build`: **passed**, including the actual App import of engine-owned Unicode data. Existing bundle-size advisory remains.
- `.venv/bin/python -m pytest -q tests/test_worker.py tests/test_web_contract.py tests/test_ephemerality.py`: **27 passed**, one existing Starlette/httpx deprecation warning.
- `git diff --check`: passed before commits.
- No browser interaction was performed by this executor, avoiding interference with the orchestrator's browser. Latest built assets are available on its existing local server at `http://127.0.0.1:8766`; dated real-browser evidence belongs to 05-04.
- No deployment occurred. Phase 4 Linux/container/CDN release gates remain open.

## Deviations from Plan

1. **[Rule 2 — Correctness] Completed-page visibility snapshot.** Added `completedPages` to controller progress and used it to derive App search pages. A shared viewer cache alone would publish a late stopped-page result. Existing stop/resume deferred tests now assert accepted page IDs. Included in `8e7d40f`.
2. **[Rule 2 — Correctness] Explicit lost-address refresh.** Added a regression and named source-mismatch path instead of treating lost original IDs as ordinary fit refusal. Commits `864f594`, `8e7d40f`.
3. **Shared-index commit collision.** The first narrowly staged RED commit `8d99e0e` also captured another executor's already-staged `tests/test_recipe_snapshots.py` changes. The orchestrator was notified immediately. No changes were reverted; subsequent commits used `git commit --only` with explicit owned paths. The engine executor retains responsibility for those tests and their evidence.
4. Metadata ownership remains with the orchestrator: this executor did not change STATE, ROADMAP or REQUIREMENTS, as explicitly assigned.

## Known Stubs

None blocking this plan's find/preview objective. Batch apply is deliberately owned by 05-04 and is not exposed until that integration exists. No mock document data, placeholder endpoint or persistence was added.

## Self-Check: PASSED

The new panel and all modified client modules/tests exist. All listed task commit hashes exist. Verification above records only checks actually performed.
