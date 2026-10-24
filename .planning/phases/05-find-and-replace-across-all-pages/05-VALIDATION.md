---
phase: 5
slug: find-and-replace-across-all-pages
status: local-validation-complete
nyquist_compliant: false
wave_0_complete: true
created: 2026-08-31
updated: 2026-10-24
---

# Phase 5 — Validation Record

Implementation, focused tests, code review and the complete technical-document G4
proof are delivered. The final applicable regression against `630ca28` is complete;
one obsolete test expectation was corrected with independent evidence and rerun.
This record distinguishes automated proof, agent-operated browser
observations and deferred release/specimen coverage.
Formal whole-phase validation sign-off remains open for the literal contract
specimen item; the local implementation and test coverage below are delivered.

## Requirement Coverage

| Requirement | Actual executable evidence | Browser/evidence link |
|---|---|---|
| FIND-01 | `tests/test_find_normalize_parity.py`; exhaustive generated Unicode 15.1 data check; `client/src/find/indexing.test.mjs` proves successful/empty pages, failed-page retry, stop/resume, disposal and late-result guards | 40/40 public-proxy pages; partial/stop/resume on 126-page IRS source |
| FIND-02 | `client/src/find/search.test.mjs`: literal case-insensitive default, case option, Unicode words/CJK, full-fold expansion, grapheme and UTF-16 boundaries | Firefox default 1,029 / whole-word 851 / whole-word case-sensitive 723 |
| FIND-03 | Search tests retain page/context, stable occurrence identities and exact source fragment navigation, including repeated shared operator IDs | Actual source-box highlight at 115%/200%; result pagination and focus recorded in G4 results |
| FIND-04 | `client/src/find/buildRecipe.test.mjs`; real Node/API integration excludes one occurrence in an otherwise edited run, preserving prior recipe order/style | Three `l` matches in one run, one opt-out, two applied; complete G4 also retains one individual occurrence |
| FIND-05 | Search tests retain partial normalization matches locked; preview tests retain classification/runtime failures and require another exact preview after filtering; real API fit/font/source refusals | Actual too-wide disabled row; automatic unknown-font refusal and successful explicit Serif recovery |
| FIND-06 | `client/src/find/replaceAll.test.mjs`; real HTTP tests; strict 675-operation worker preview/apply; all-page G4 verifies requested Unicode, anchors, untouched instructions, style, opt-out, source immutability and renderers | One action/one Undo; prior bold/color retained; native input undo; signature and encrypted-source recovery |

All referenced test files exist and are included in the shipped test discovery.
Commands use the existing Python virtual environment and Node test runner; no
runtime dependency or test framework was added.

## Final Commands and Current Results

| Check | Command | Result |
|---|---|---|
| Client suite | `npm --prefix client test` | 41 passed |
| Production build | `npm --prefix client run build` | Passed; existing large-chunk advisory remains |
| Strict types | `.venv/bin/python -m mypy engine/ server/` | 30 source files clean |
| Canonical data | `.venv/bin/python tools/build_search_unicode.py --check` | Unicode 15.1.0 data current |
| Engine/fit/snapshot focused | Owned executor command in 05-01 summary | 133 passed |
| Complete bounded workload | `.venv/bin/python -m pytest -q -s -m corpus tests/test_find_replace_performance.py -x` | Final `630ca28`: 2 passed in 59.93s; 18.302/18.319 CPU previews, 18.467 CPU apply |
| Real batch integration + G4 | `.venv/bin/python -m pytest -q -s tests/test_find_replace_recipe.py tests/test_gate_g4.py -x` | 12 passed in 101.38s after source-TJ correction; G4 passed again in the final full suite after the space-budget fix |
| G4 mask/control checks | `.venv/bin/python -m pytest -q tests/test_gate_g4.py -k 'mask_union or outside_change or nonvacuous' -x` | 6 passed after report-only page-count correction |
| Full applicable local suite | `.venv/bin/python -m pytest -q -m 'not linux_only and not cdn'` | 556 passed, one obsolete refusal expectation failed; 5 release checks deselected; 1,406.65s |
| Corrected layout/atomicity file | `.venv/bin/python -m pytest -q tests/test_preview_layout_guard.py` | 3 passed in 2.41s after test-only `1f9af02`; no production change |

Final logs are under `/private/tmp/pdf-tool-phase5-*-20261024.log`.
An interrupted pre-space-fix run is separately labeled and is not counted as the
final regression result. The final suite was temporarily suspended during the
large browser batch to avoid competing CPU load, then resumed unchanged. Its raw
one-failure outcome is retained: the actual-width fix made a formerly unsafe
corpus edit safe, invalidating an old refusal expectation. Before changing it,
all 663 following glyphs, independent text and outside-region pixels were checked.
The corrected file proves that safe result and a real late corrupted-TJ refusal
with no partial output. Its three tests pass independently. The other 555 cases
and these three corrected cases cover the current 558 selected tests; this is
aggregate verification, not a claim the raw broad run had zero failures.

## Acceptance Invariants

- The shared generated data, engine projection and browser projection agree on
  Unicode normalization and UTF-16 source provenance. Whole ligature/case-fold
  expansions are editable; partial expansions remain visible and locked.
- Original server addresses and source bytes remain authoritative. Shared physical
  addresses are visible but independently unaddressable fragments are locked.
- Each replacement recipe contains at most one operation per run, preserving prior
  text/font/style operations. Filtering can remove only new proposals, never prior
  committed edits, and the exact final full recipe must pass an actual dry run.
- Apply captures the reviewed recipe, checks session/key/generation around awaits,
  prepares the viewer before publication and commits exactly one undo entry.
- Every splice retains fresh interpreter, font/state/address, following-glyph and
  source-anchor/envelope checks. Complex provenance uses the classified fallback.
  Source TJ geometry, terminal pen and actual serialized space widths are handled
  separately; positive word gaps and the 90% horizontal-scale floor remain guarded.
- Limits remain CPU20, default worker wall30, recipe body 1MiB, 50,000 operations
  and 10,000 Unicode characters per replacement. No acceptance timeout was raised.
- All 40 proxy pages are compared in all three engines: 28 changed pages use unions
  of individual run masks; 12 unchanged pages use no masks. All 120 same-engine
  pairs have zero outside changes. Cross-engine antialiasing tolerance is separate.
  Negative controls catch changes in the gap between disjoint masks and vacuous output.

## Browser and Coverage Boundaries

Dated actual results, browser versions and untested items are in
`05-G4-RESULTS.md`. Observations are agent-operated local UI checks, not claimed
user acceptance. Controller tests prove failed-page retry and deferred response
races without manufacturing HTTP errors in the live browser.

The immutable 40-page source is a USGS technical-document proxy, not a legal
contract. Literal contract-specimen coverage remains unproven. Linux resource
limits, tmpfs/seccomp/container execution and live CDN/cache verification remain
open Phase 4 release gates. No deployment occurred or is authorized by this phase.

## Sign-Off

- [x] FIND-01..06 have implementation and focused test evidence.
- [x] Shared Unicode/provenance and partial-expansion safety are tested.
- [x] Full-document and partial/stopped/failed indexing contracts are tested.
- [x] Complete 675-operation worker proof succeeds with unchanged limits.
- [x] All-page three-renderer G4 passes after the source-TJ correction.
- [x] All three code review blockers are fixed with recorded RED/GREEN evidence.
- [x] One-step undo, native input undo and prior style preservation observed.
- [x] Proxy/specimen and platform/release coverage boundaries are explicit.
- [x] Final applicable regression resolved: 556 broad-run passes plus the corrected three-test layout/atomicity file; no unresolved failure.
- [x] Final phase goal verification recorded: 15/16 truths, all six FIND requirements satisfied locally; `human_needed` only for the literal contract specimen.
