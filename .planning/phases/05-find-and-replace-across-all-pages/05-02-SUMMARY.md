---
phase: 05-find-and-replace-across-all-pages
plan: 02
subsystem: search
tags: [unicode, provenance, recipes, javascript, python]
requires:
  - phase: 04-browser-workstation
    provides: Server-issued run IDs, page index and ordinary recipe transport
provides:
  - Canonical Unicode 15.1 NFKD/full-fold projection with UTF-16 source spans
  - Literal matcher with safe normalized boundaries and current-recipe overlays
  - Bounded full-recipe assembly with per-occurrence exclusions
affects: [05-03, 05-04]
tech-stack:
  added: []
  patterns: [Shared generated engine-owned Unicode data, inverse source-span closure]
key-files:
  created: [tools/build_search_unicode.py, engine/data/search-unicode-15.1.json, engine/search.py, client/src/find/search.mjs, client/src/find/search.test.mjs, client/src/find/buildRecipe.mjs, client/src/find/buildRecipe.test.mjs, tests/test_find_normalize_parity.py]
  modified: [server/worker.py, client/package.json, client/vite.config.js, Dockerfile.ci, Dockerfile]
key-decisions:
  - Both runtimes consume the sole engine-owned Unicode 15.1 table; no native JS normalization.
  - A replacement requires inverse source-span closure and source grapheme boundaries.
  - Existing per-run font choices survive; batch font fills missing fallback only.
requirements-completed: [FIND-01, FIND-02, FIND-04, FIND-05, FIND-06]
duration: 15 min
completed: 2026-10-22
---

# Phase 5 Plan 2: Canonical Search and Recipe Assembly Summary

**Shared Unicode projection maps literal document matches back to safe source spans and assembles selected occurrences into one complete recipe.**

## Accomplishments

- Generated deterministic Unicode 15.1 sparse NFKD/full-case-fold/CCC tables. Generator rejects another Unicode version and `--check` detects drift. Python and JS preserve source UTF-16 provenance through decomposition, folding, stable canonical ordering and astral characters.
- Existing page rows expose `search: {version,sensitive,folded}` while retaining authoritative text, IDs, geometry and classification.
- Default case-insensitive literal matching, case and Unicode whole-word options, current-recipe text overlays, stable per-occurrence IDs, 48-scalar context and visible locked partial expansions are implemented.
- Safe selected source slices become one ordinary operation per run, preserving every earlier operation and style. Exclusions and refused runs remain separate; unchanged selections create no operations. Existing 50,000-operation, 10,000-Unicode-scalar text and 1MiB UTF-8 recipe limits refuse atomically.
- Node test discovery covers session and nested find modules; both Docker client build stages include the same shared JSON. No dependencies or lockfiles changed.

## Exported Contracts

- Python `project_text(text, *, match_case=False) -> {text,spans}`; `project_search_text(text) -> {version,sensitive,folded}`.
- JS `projectText(text,{matchCase=false}={})`, `projectSearchText(text)`, `SEARCH_VERSION`.
- `findMatches(pages,query,{matchCase=false,wholeWords=false,recipe=[]}={})`: pages may be a one-based object or Map, whose values are page responses or run arrays. Results contain the exact reviewed Match fields. Whole-word search without `Intl.Segmenter` raises actionable copy; unavailable grapheme segmentation locks replacements.
- `buildReplacementRecipe({pages,recipe=[],matches,excludedIds=new Set(),replacement,fontFamily='',refusedRunIds=new Set()}) -> {recipe,changes,selectedCount,changedPages,unchangedCount}`. `changedPages` is a sorted array; counts refer to changing instances. `assertRecipeLimits(recipe)` throws an Error with `code='RECIPE_TOO_LARGE'` and user-facing guidance.

## Task Commits

1. Projection RED `3c1dae6`; GREEN `b76e9ca`.
2. Matcher RED `ef482ca`; GREEN `7f8e6ef`.
3. Builder RED `a79b66c`; GREEN `c106cc5`.
4. Long-source regression RED `da2fe16`; fix and production build data inclusion `452536e`.

## Verification

- Generator `--check`: passed. Exhaustive 1,112,064 non-surrogate scalar table comparisons pass.
- Focused Python projection/worker/page-scope run initially **16 passed**. Subsequent run after concurrent engine edits: **14 passed, 2 failed**, both `test_planning_indexes_only_recipe_pages` parametrizations, because apply classified unrelated page 0. Root and engine executor notified; no changes made outside ownership. This integration failure must be resolved before phase completion.
- Corpus parity: **1 passed**, comparing exact strings and span arrays for all 3,000 runs across the 40-page `govdocs1_013_013050.pdf` technical-document acceptance proxy. This is not a legal-contract fixture.
- Final Node discovery: **31 passed** (includes independently authored indexing/preview controller tests).
- `mypy engine/ server/`: **29 files clean** before the latest concurrent engine edits.
- Production `npm run build`: passed, existing chunk-size advisory remains. Separate Vite direct-entry library build of `search.mjs` proved the external engine JSON resolves and bundles (2 modules, 299.96kB / 92.27kB gzip), even before App imports the feature. Docker execution was not performed.
- Long 150,000-character literal query regression passes; astral context clipping and all normalized safety seams pass.
- `git diff --check`: passed. No implementation stubs or new endpoint/auth/storage surfaces introduced.

## Deviations from Plan

1. **[Rule 1 — Bug] Long literal source-span overflow.** A new 150,000-character test reproduced argument-count overflow in `Math.min(...spans)`. Replaced spread with loops, preindexed inverse provenance once per run and bounded context slicing. Commits `da2fe16`, `452536e`.
2. **[Rule 3 — Blocking issue] Production client image shared-data copy.** Dockerfile.ci was planned, but production Dockerfile also builds the client in isolation. Root explicitly extended ownership for the identical JSON COPY; included in `452536e`.

## Issues Encountered

The concurrent engine page-scope regression above was historical and is resolved
by the completed 05-01 integration. Both `test_planning_indexes_only_recipe_pages`
parametrizations passed in the final applicable broad suite against `630ca28`.
The orchestrator's final client suite passed 41 tests, with production build,
strict typing and browser verification recorded in 05-G4-RESULTS. No deployment
occurred; Phase 4 Linux/container/CDN release gates remain open.

## Self-Check: PASSED

All eight newly created implementation/test/data files exist. All eight listed task commits exist. Summary describes the actual focused integration failure rather than claiming final phase verification.
