---
phase: 5
slug: find-and-replace-across-all-pages
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-31
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived verbatim from `05-RESEARCH.md` § Validation Architecture. Task IDs are filled in by the
> planner; every command below was written to be runnable, and every file marked `❌ Wave 0` does not
> exist yet.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| Framework (server/engine) | pytest ≥9.1.1 (already configured, reused unchanged from Phase 3) |
| Framework (client) | **none exists yet** — `client/package.json` has no test script and no `vitest`/`jest` devDependency (measured this session). Recommend `vitest`: MIT, maintained by the Vite team (same maintainers as the already-pinned `vite`), zero-config against the existing `vite.config.js`. This is the phase's one Wave 0 tooling gap. |
| Config file (server) | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths=["tests"]` (existing) |
| Config file (client) | `client/vitest.config.ts` or a `test` block added to the existing `vite.config.js` — ❌ Wave 0 |
| Quick run command (server) | `uv run --frozen pytest -q -m "not corpus" tests/test_recipe.py tests/test_find_replace_recipe.py` |
| Quick run command (client) | `npm --prefix client test` (❌ Wave 0 — script does not exist yet) |
| Full suite command | `uv run --frozen pytest -q` (server, includes `corpus`-marked) + `npm --prefix client test` (client) |

## Per-Task Verification Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| FIND-01 | Ligature fold matches interpreter normalization (7 standard Latin ligatures) | unit (client) | `npm --prefix client test -- search.test.ts -t "normalizes ligatures"` | ❌ Wave 0 |
| FIND-01 | Client and server normalization agree on real corpus text, not just the 7 spot-checked ligatures (closes Assumption A2) | corpus | `pytest -m corpus tests/test_find_normalize_parity.py::test_js_and_python_nfkd_agree_on_corpus_text -x` | ❌ Wave 0 |
| FIND-02 | Case-insensitive substring is the default | unit (client) | `npm --prefix client test -- search.test.ts -t "case insensitive by default"` | ❌ Wave 0 |
| FIND-02 | "Match case" toggle changes results | unit (client) | `npm --prefix client test -- search.test.ts -t "match case toggle"` | ❌ Wave 0 |
| FIND-02 | "Whole words only" toggle changes results | unit (client) | `npm --prefix client test -- search.test.ts -t "whole word toggle"` | ❌ Wave 0 |
| FIND-03 | Match list shows page number, context, live count (data) | unit (client, component) | `npm --prefix client test -- MatchList.test.tsx -t "renders page context and live count"` | ❌ Wave 0 |
| FIND-03 | Click a match jumps to it (journey) | recorded manual check (per `04-CONTEXT.md` A-4.3 precedent: journey rows are recorded, not automated, absent an e2e browser harness) | N/A — dated results doc with a `## Decision` header, per `G2B-GATE-RESULTS.md`'s precedent | ❌ Wave 0 (no e2e harness) |
| FIND-04 | Opted-out match instance excluded from the built `RecipeOp.new_text` | unit (client) | `npm --prefix client test -- buildRecipe.test.ts -t "opted-out instance excluded, run still edited for remaining matches"` | ❌ Wave 0 |
| FIND-05 | Classify-time-refused match (`"shared Form XObject"`) shown disabled with reason, never filtered | corpus integration | `pytest -m corpus tests/test_find_replace_recipe.py::test_shared_xobject_match_shown_disabled_with_reason -x` (fixture: `corpus/public/irs_1040_tax_tables.pdf`, term `"CAUTION"`) | ❌ Wave 0 |
| FIND-05 | Plan-time-refused match (font-mapping-table miss) shown disabled with reason, never filtered | corpus integration | `pytest -m corpus tests/test_find_replace_recipe.py::test_mapping_table_refusal_shown_disabled_with_reason -x` (fixture: `corpus/public/govdocs1_013_013050.pdf`, term `"mineral"`→`"minerals"`) | ❌ Wave 0 |
| FIND-05 | Unknown/future reason string falls back to a generic disabled state, never crashes the UI | unit (client) | `npm --prefix client test -- reasonCopy.test.ts -t "unknown reason falls back gracefully"` | ❌ Wave 0 |
| FIND-06 | Op count for a real 40-page replace-all stays under `MAX_RECIPE_OPS` (cheap insurance per §Key Measurement) | corpus | `pytest -m corpus tests/test_find_replace_recipe.py::test_40page_replace_all_op_count_under_cap -x` (fixture: `govdocs1_013_013050.pdf`) | ❌ Wave 0 |
| FIND-06 | Dry-run-then-filter: refused ops excluded, committed ops all resolve `ok=True` | integration | `pytest tests/test_find_replace_recipe.py::test_filtered_commit_matches_dry_run_verdicts -x` | ❌ Wave 0 |
| FIND-06 | Multi-match-per-run collapses to one op (Pattern 2), no `duplicate_run_id_in_recipe` | unit (client) + integration | `npm --prefix client test -- buildRecipe.test.ts -t "collapses multiple matches in one run to one op"` AND `pytest tests/test_find_replace_recipe.py::test_multi_match_run_produces_single_op -x` | ❌ Wave 0 |
| G4 criterion 4 | Replace-all changes every REMAINING match (opt-out exercised) across the 40-page corpus contract; masked diff confined to edited runs, on every changed page, in all 3 engines | corpus + pixel-diff (gate) | `pytest -m corpus tests/test_gate_g4.py::test_g4_replace_all_masked_diff_all_engines -x` (fixture: `govdocs1_013_013050.pdf`; N-region mask per §Code Examples) | ❌ Wave 0 |
| D-5.5 / G4 criterion 5 | One Ctrl+Z reverts the entire replace-all batch as a single step | unit (client, undo stack) | `npm --prefix client test -- useReplaceAll.test.ts -t "single undo reverts whole replace-all batch"` | ❌ Wave 0 |
| (existing coverage, not new) | `MAX_RECIPE_OPS`/`MAX_NEW_TEXT_CHARS` parse-time boundary | unit (already exists) | `uv run --frozen pytest tests/test_recipe.py -k max_ops` | ✅ Exists (`tests/test_recipe.py`, boundary test already present — Phase 5 does not need to re-test `parse_recipe`'s own cap, only that realistic usage stays under it, per the row above) |

## Sampling Rate

- **Per task commit:** `uv run --frozen pytest -q -m "not corpus" tests/test_recipe.py tests/test_find_replace_recipe.py` (server) + `npm --prefix client test` (client) — fast, hand-picked fixtures named above (`govdocs1_013_013050.pdf` "the"/"mineral" runs, `irs_1040_tax_tables.pdf` "CAUTION" run — all already-measured, named-by-run examples, not freshly discovered each time).
- **Per wave merge:** `uv run --frozen pytest -q` (includes `corpus`-marked tests, ~12s+ per corpus-touching test per the measurements above — expect this suite to take longer than Phase 3's, budget for it) + `npm --prefix client test` (client full suite) + `mypy engine/` (existing project convention, unchanged).
- **Phase gate:** full suite green, plus `tests/test_gate_g4.py` run directly against the two named fixtures, plus `04-CONTEXT.md` A-4.3's recorded-manual-check for the journey row (click-to-jump) — a dated results document with a `## Decision` header and an explicit "what was NOT tested" section, following the `G2B-GATE-RESULTS.md` precedent — before `/gsd:verify-work`.

## Wave 0 Requirements

- [ ] `client` test framework: add `vitest` devDependency + `client/vitest.config.ts` (or extend
      `vite.config.js`) and an `npm test` script — none exists today.
- [ ] `client/src/features/find-replace/search.ts` + `search.test.ts` — normalize/match logic,
      framework-free.
- [ ] `client/src/features/find-replace/buildRecipe.ts` + `buildRecipe.test.ts` — matches → ops,
      the per-run dedup logic (Pattern 2).
- [ ] `client/src/features/find-replace/reasonCopy.ts` — the reason-string → user-facing-copy
      lookup, including the dynamic fit-ladder-reason prefix match and the explicit unknown-reason
      fallback (§Don't Hand-Roll vocabulary table).
- [ ] `tests/test_find_replace_recipe.py` — server/engine-level integration tests for the
      dry-run-then-filter flow, using the exact named corpus fixtures/terms measured in this
      research (no new fixture construction needed).
- [ ] `tests/test_find_normalize_parity.py` — cross-checks the JS and Python NFKD+casefold
      transforms agree on real corpus text, not just the 7 ligatures spot-checked this session
      (closes Assumption A2); likely shells out to `node` the way this research did.
- [ ] `tests/test_gate_g4.py` — the masked-diff-all-engines gate test, generalizing
      `_two_region_masked_diff` from `tests/test_gate_g2b.py` to N regions (§Code Examples),
      against `govdocs1_013_013050.pdf`.
- [ ] Confirm whatever recipe dry-run/commit endpoint(s) Phase 4 ships accept a `RecipeOp` list of
      arbitrary length (Assumption A1) — a five-minute check once Phase 4's server code exists,
      before Phase 5 client work assumes it.

---

## Manual-Only Verifications

| Check | Why it cannot be automated | Recorded where |
|---|---|---|
| The match list reads correctly on a real 40-page contract (FIND-03) | Page number, surrounding-context window, and live count are asserted structurally; that the list is *usable* to find a match is a judgement call. | A dated results doc |
| Disabled/unreplaceable rows are legible as refusals, not as bugs (FIND-05) | The reason string is asserted verbatim against the engine vocabulary; that a user reads it as a deliberate refusal rather than a failure is not machine-checkable. | A dated results doc |
| One Ctrl+Z reverts the whole batch in a real browser (FIND-06 / EDIT-05) | The engine-side invariant — a length-N recipe is one undo unit — is a Python test. The keystroke path through the browser stack is a recorded manual check, per Phase 4's A-4.3. | A dated results doc |

---

## Validation Sign-Off

- [ ] Every requirement ID in this phase appears in at least one row of the verification map
- [ ] Every `❌ Wave 0` file has an owning task in a plan
- [ ] Every manual-only check has a named results document and an owning task
- [ ] The phase gate rows run green in CI, on Linux
- [ ] No row was dropped for being inconvenient to automate — it became a manual check instead

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
