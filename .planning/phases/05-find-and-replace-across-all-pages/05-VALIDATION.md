---
phase: 5
slug: find-and-replace-across-all-pages
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-31
updated: 2026-10-22
---

# Phase 5 — Validation Strategy

This refresh follows `05-RESEARCH-UPDATE.md` and the current delivered Phase 4 contracts. Planner must assign the proposed test files to tasks. Feature tests and G4 are pending; current baseline tests passing do not make this phase compliant. [VERIFIED: current tests and phase implementation state]

## Test Infrastructure

| Property | Value |
|---|---|
| Python | pytest 9.1.1, existing `pyproject.toml` configuration. [VERIFIED: installed version/config] |
| Client | Node 22.23.2 built-in test runner; existing `client/src/session.test.mjs` has 12 passing tests. No Vitest/Jest install. [VERIFIED: node --test run] |
| Existing focused baseline | `.venv/bin/python -m pytest -q tests/test_recipe_page_scope.py tests/test_preview_layout_guard.py tests/test_unicode_edit_refusal.py tests/test_shaping_safety.py tests/test_recipe.py` — 46 passed in 3.39s. [VERIFIED: research run] |
| Current client baseline | `node --test client/src/session.test.mjs` — 12 passed. [VERIFIED: research run] |
| Future quick Python | `.venv/bin/python -m pytest -q -m "not corpus" tests/test_find_normalize_parity.py tests/test_find_replace_recipe.py tests/test_recipe_page_scope.py tests/test_preview_layout_guard.py tests/test_recipe.py` |
| Future quick client | `node --test client/src/session.test.mjs client/src/find/*.test.mjs` |
| Build | `npm --prefix client run build`; prove shared JSON imported from engine outside client root works. |
| Full phase | `.venv/bin/python -m pytest -q -m "not linux_only and not cdn"` + client tests + build + `.venv/bin/python -m mypy engine/ server/` |
| Release gates | Existing Linux isolation/container and configured CDN checks remain pending; do not deploy during Phase 5. [VERIFIED: CONTEXT execution amendment] |

Future commands are implementation acceptance targets, not claims those files exist. Keep the fast tests under 30 seconds per targeted invocation; the real corpus renderer gate is deliberately separate. `uv run --frozen` currently fails on this sandbox's external cache; local `.venv` is available. [VERIFIED: tool probes]

## Phase Requirements → Test Map

| Req ID | Required proof | Type / proposed file | Command | Exists? |
|---|---|---|---|---|
| FIND-01 | Shared versioned NFKD/fullfold, no second TJ gap rules; original text unchanged | Python + JS parity, `tests/test_find_normalize_parity.py` | `.venv/bin/python -m pytest -q tests/test_find_normalize_parity.py -x` | ❌ |
| FIND-01 | All Unicode scalar mappings plus adversarial sequences; generated artifact fresh | Generator and parity | `.venv/bin/python tools/build_search_unicode.py --check` + parity row above | ❌ |
| FIND-01 | All pages requested with queue limit 2; failed page retained/retryable; partial count never complete; abort/document replacement blocks late rows | Node, `client/src/find/search.test.mjs` / `replaceAll.test.mjs` | `node --test client/src/find/*.test.mjs` | ❌ |
| FIND-02 | Insensitive substring default; match-case changes result; Unicode fullfold includes ß/SS, sigma variants; no accent stripping | Node, `search.test.mjs` | `node --test client/src/find/search.test.mjs` | ❌ |
| FIND-02 | Whole words uses native Unicode boundaries for accented/Greek/combining/CJK text, underscore/apostrophe and astral prefix; unsupported Segmenter is explicit | Node + recorded browsers | `node --test client/src/find/search.test.mjs` | ❌ |
| FIND-03 | Page/context/count data, effective current recipe text and stable match identity | Node, `search.test.mjs` | `node --test client/src/find/search.test.mjs` | ❌ |
| FIND-03 | Click result goes to matching page/run and highlights correct source context after prior edit | Recorded browser journey | `05-G4-RESULTS.md` dated evidence | ❌ |
| FIND-04 | Individual opt-out, including two matches in one run; unchanged instance preserved; one op per run; existing style/other ops preserved | Node, `buildRecipe.test.mjs` | `node --test client/src/find/buildRecipe.test.mjs` | ❌ |
| FIND-05 | Full ligature/casefold expansion replaceable; partial expansion visible disabled; decomposed marks/surrogate halves not lost | Node + Python projection | Client search tests + parity command | ❌ |
| FIND-05 | Classify, fit, mapping and actual-splice refusals stay visible with engine reason; unknown reason has safe copy | Integration + Node | `.venv/bin/python -m pytest -q tests/test_find_replace_recipe.py -x` + client tests | ❌ |
| FIND-05 | Overall failed preview's other rows not treated as validated; worker failure retains all rows; refused prior committed op blocks batch | Integration + Node, `replaceAll.test.mjs` | Same Python command + `node --test client/src/find/replaceAll.test.mjs` | ❌ |
| FIND-06 | Filter only new requested edits; exact filtered full recipe must pass actual preview before apply; one apply/one history entry; failure preserves bytes/history | Node + worker integration | Same integration and replaceAll test commands | ❌ |
| FIND-06 | Stale query/replacement/toggle/opt-out/recipe/document preview cannot apply; signed acknowledgment and source cache retry preserved | Node + existing web tests | Client tests + `.venv/bin/python -m pytest -q tests/test_web_contract.py tests/test_ephemerality.py -x` | Existing base; new cases ❌ |
| FIND-06 | Snapshot optimization preserves each D04 splice check, fresh match/resolve and subset-key refusal; unrelated-page work not added | Python engine regression | `.venv/bin/python -m pytest -q tests/test_recipe.py tests/test_recipe_page_scope.py tests/test_preview_layout_guard.py tests/test_find_replace_recipe.py -x` | Existing base; new cases ❌ |
| G4 / FIND-06 | Real 40-page source, individual opt-out, all remaining safe instances changed, actual isolated preview/apply fit existing CPU/wall/body caps | Corpus gate, `tests/test_gate_g4.py` | `.venv/bin/python -m pytest -q -m corpus tests/test_gate_g4.py -x` | ❌ |
| G4 criterion 4 | Each changed page in all 3 renderers; no differences outside union of edited-run masks; whole-page unchanged/opt-out comparisons | Same corpus gate | Same gate command | ❌ |
| G4 criterion 5 | Ctrl/Cmd+Z restores prior whole recipe/output/style in one step, including prior nonempty recipe | Node + recorded browser | `node --test client/src/find/replaceAll.test.mjs`; results document | ❌ |

Rows are derived from FIND-01..06 and roadmap G4; proposed test paths are the planner's task boundaries. Existing Python/Node tests are reusable infrastructure, not feature proof. [VERIFIED: REQUIREMENTS.md; ROADMAP.md; tests]

## Canonical Offset Acceptance Cases

Pin `engine/search.py:project_text/project_search_text`, `client/src/find/search.mjs:projectText/projectSearchText`, shared `engine/data/search-unicode-15.1.json` and `tools/build_search_unicode.py --check`. Page run `search` shape is `{version,sensitive:{text,spans},folded:{text,spans}}`; every normalized UTF-16 unit has a half-open source UTF-16 interval. [VERIFIED: agreed research contract in 05-RESEARCH-UPDATE.md]

- Whole query `fi` in source `ﬁ` spans source `[0,1)` and is eligible; partial `f` stays visible disabled with `normalization_boundary_unreplaceable`.
- Whole insensitive `ss` in `ß` is eligible; single `s` cannot remove only half the expansion.
- Precomposed/decomposed canonical text compares equally; a base-only match cannot delete its combining marks. Multiple combining classes exercise stable canonical reordering and provenance.
- An astral prefix occupies two UTF-16 source units; no surrogate is split or miscounted.
- Repeated matching in one run, neighboring ligatures and per-instance opt-outs do not duplicate source edits.
- Current recipe override text is projected using the exact shared data; original source text/run ID remain available and untouched.
- Exhaustively compare generated scalar mappings with Python and sample sequence normalization; include real corpus projections without logging decoded text.

These are new contract tests, not claims the helper already exists. [VERIFIED: current normalization gap and recommended contract]

## Engine Performance and Fidelity Gate

Baseline source SHA-256: `d0a3b06606378733a2ec96cfa01e3b12c111d13059d070e3e039b751347a4529`, `govdocs1_013_013050.pdf`, 40 pages / 3,000 runs. Fixed `the` → `a` insensitive substring gives 1,029 instances in 772 run ops on 38 pages. Full ordinary preview reports 97 refusals (75 shared-operator, 22 mapping); the 675 accepted ops occupy 107,593 JSON bytes yet actual preview/apply both fail around 23s with `WORKER_FAILED` under unchanged 20s CPU cap. A direct 100-op profile yields 296 page parses and 292 PDF saves. [VERIFIED: research measurement/profile artifacts]

Before G4:
1. Implement verified fresh snapshot reuse across `rewrite.py` and `recipe.py`; preserve current standalone rewrite behavior.
2. Assert each successful splice compares actual current before/after sentinel at `1e-6`; same-page next op uses fresh `_match_run`, `_resolve_op`, fresh offsets and verdicts; substitution-key changes still refuse.
3. Count real page walks/saves to demonstrate avoided duplicate work. Inject a moving-tail failure and a stale/ambiguous next-op failure to prove no shortcut passes incorrectly.
4. Run actual isolated worker `edit` preview and apply on the full accepted batch with source IDs, unchanged caps, successful reports and no PDF returned for preview.
5. Include an individual opt-out, not merely an opted-out run; rebuild the candidate, preview the exact final recipe and commit once. Verify opt-out text remains.
6. Reclassify rewritten output and prove remaining eligible instances changed; verify each changed page in PDFium, Poppler and MuPDF at existing harness settings.
7. Use separate edited-run masks or their union. Never mask the bounding rectangle spanning unrelated runs or a whole edited page. Compare unchanged pages outside any mask.
8. Confirm source hash/bytes unchanged, no partial output on refusal, and one client undo unit.

Requirements follow existing recipe/rewrite invariants; test implementation remains pending. A successful 100-op direct profile or one-op worker edit is a positive control, not a G4 pass. [VERIFIED: recipe/rewrite contracts; measured blocker]

The live successful ordinary source ID is `d0a3b06606378733a2ec96cfa01e3b12c111d13059d070e3e039b751347a4529:p5:c0:o1759` for this fixed replacement. Older research's refusal fixtures may now refuse earlier due to preflight; establish each fixture's live precondition rather than weakening guards to preserve old expectations. [VERIFIED: live preview/apply; current rewrite preflight]

**Literal contract-document gap:** manifest tags this 40-page source `weight_class: other`. Label its evidence a 40-page public corpus proof proxy. Do not declare literal contract-source coverage established; record this distinction in `05-G4-RESULTS.md`. Preserve public corpus sources and manifest immutability. [VERIFIED: corpus/manifest.json; phase task constraints]

**Limits to preserve:** recipe 50,000 ops; 10,000 characters per new_text; 1MiB API/worker recipe body; 20s worker CPU; 30s worker default wall; request middleware default 50s. Research used explicit 40s worker allowance only. Report the actual gate timeout, never relabel it as production default or raise any cap. [VERIFIED: engine/recipe.py; server/app.py/isolation.py/worker.py]

## Sampling Rate

- Per task: relevant focused Python file(s) and `node --test client/src/session.test.mjs client/src/find/*.test.mjs`.
- Per wave: all phase Python tests except the expensive corpus renderer gate; client tests, client build, strict mypy.
- Phase gate: focused suite green, actual bounded 40-page preview/apply, full three-renderer per-page gate and dated browser journey results.
- Release: preserve outstanding Phase 4 Linux/container/CDN gates as separate pending work; no deployment.

Commands and sampling are proposed execution requirements. [VERIFIED: current workflows and execution amendment]

## Wave 0 Gaps

- [ ] Generate canonical data and shared projection APIs; add `tests/test_find_normalize_parity.py`.
- [ ] Add Node `client/src/find/{search,buildRecipe,replaceAll}.test.mjs`; reuse `node:test`.
- [ ] Add complete/partial/failed-page loading and stale-preview tests.
- [ ] Add `tests/test_find_replace_recipe.py` covering actual preview/filter/commit and snapshot regression invariants.
- [ ] Add `tests/test_gate_g4.py` with actual worker budget and three-renderer union-mask proof.
- [ ] Assign `05-G4-RESULTS.md` an owning task for dated browser/coverage evidence.
- [ ] Treat recipe/rewrite batching optimization as required implementation work before G4.
- [ ] Add `npm test` convenience script only if useful; a new framework is unnecessary.

These gaps supersede the old Vitest installation requirement. [VERIFIED: existing Node infrastructure; current phase tests absent]

## Manual Browser Evidence

Record date, browser version, actual result, decision and “What was not tested” in `05-G4-RESULTS.md`. [VERIFIED: Phase 4 recorded-journey precedent]

| Check | Required evidence |
|---|---|
| All-page search | Live partial count/progress, failed-page retry, completed search distinction. |
| Match navigation | Page/context/count, click result jump/highlight, next/previous navigation and scroll behavior. |
| Opt-outs/refusals | Individual opt-out, disabled rows readable, unchanged match text not lost. |
| Stale preview | Edit query/replacement/options/selection while preview runs; stale response never enables Apply. |
| One action/one undo | Apply full filtered batch once; Ctrl/Cmd+Z returns full prior recipe, including previous single-run edit/style. |
| Session recovery | Close/reopen while indexing or previewing; source eviction reupload; old-document results never leak into new document. |
| Privacy/location | Local search disclosure; server preview/apply disclosure; no decoded text in logs/artifacts. |

## Validation Sign-Off

- [ ] FIND-01..06 each have passing implementation tests.
- [ ] No new runtime dependency or test framework.
- [ ] Unicode partial expansions and UTF-16 provenance safety proven.
- [ ] Full-document completeness/failure and current recipe search proven.
- [ ] Per-op safety/atomicity regressions stay green after optimization.
- [ ] Actual 40-page isolated preview and commit succeed without limit changes.
- [ ] Every changed page passes all three renderers outside exact masks; unchanged/opted-out content verified.
- [ ] One-step undo and stale-preview/browser journeys recorded.
- [ ] Public proxy vs literal contract coverage stated honestly.
- [ ] Phase 4 Linux/container/CDN status retained, no deployment performed.

*Research refresh baseline: 46 focused Python tests and 12 Node tests passed. Phase 5 feature/G4 validation is pending.* [VERIFIED: 2026-10-22 research execution]
