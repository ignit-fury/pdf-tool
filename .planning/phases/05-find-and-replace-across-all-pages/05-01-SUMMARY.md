---
phase: 05-find-and-replace-across-all-pages
plan: 01
subsystem: engine
tags: [atomic-recipes, fidelity, performance, worker-limits]
requires:
  - phase: 03-rewrite-engine-font-pipeline
    provides: Content-stream rewriting, font subsetting and atomic recipes
provides:
  - Fresh per-splice interpreter and following-glyph validation with current target resolution
  - Complete 675-operation preview and apply within existing isolated-worker limits
affects: [05-03, 05-04, batch-fidelity]
tech-stack:
  added: []
  patterns: [Request-owned instruction witnesses, fresh memory-backed PDF projections]
key-files:
  created: [engine/part_snapshot.py, tests/test_part_snapshot.py, tests/test_recipe_snapshots.py, tests/test_find_replace_performance.py, tests/test_batch_ink_bounds.py]
  modified: [engine/recipe.py, engine/rewrite.py, engine/fonts.py, engine/fit.py, engine/playa_boundary.py]
key-decisions:
  - Every splice receives a fresh complete interpreter pass and the existing 1e-6 following-glyph guard.
  - Eligible ordinary streams reuse records only after exact instruction and rendering-state equivalence; complex provenance retains full-classification fallback.
  - Fresh PDF projections use the same parser through bounded in-memory bytes, avoiding repeated scratch mmap operations.
  - CID-width lookup sharing lasts one measurement only; bundled shaping metadata is bounded to twelve trusted faces.
  - Source TJ glyph extent and final pen are separate targets; fresh replacement anchor and extent are checked independently of following text.
requirements-completed: [FIND-06]
duration: multi-session; final continuation 11min
completed: 2026-10-24
---

# Phase 5 Plan 1: Guarded Batch Rewrite Performance Summary

**The ordinary atomic recipe path previews and applies all 675 accepted common-term operations under the unchanged CPU20 / wall30 worker limits.**

## Accomplishments

- Retained classified page snapshots for the safe standalone/full-classification fallback, eliminating repeated before/after/rederive page walks.
- Added request-owned `PartSnapshot` for eligible page content. A full fresh two-pass interpreter zip, including its trailing alignment assertion, runs after every splice. Stable instruction tokens, exact operands, owning font aliases/objects and complete rendering state prove which retained records remain valid. Current target, replacement and following-witness glyphs are freshly decoded.
- Each next operation is uniquely resolved and reclassified against current font, encoding, widths and subset keys. Shared operators, ambiguous/lost addresses, changed font/state, unsupported provenance and real following-glyph shifts continue to refuse by name. Any late failure discards the entire mutated handle without output; encrypted sources have the same guarantee.
- Complex Forms, appearance streams, patterns and Type3 provenance retain the full classified-page fallback. Link annotations without appearances may be omitted only from the disposable projection; final annotations and unrelated pages remain intact.
- Froze each yielded Playa text object's mutable graphics state before advancing the interpreter, preventing an earlier run from accidentally using a later font.
- Reused correlation only for the exact current part bytes and owned record identities. Identical frozen glyph records are retained; changed addresses are rebuilt without reflective per-glyph replacement overhead.
- Added a twelve-face cache of immutable bundled shaping metadata, without caching document text or shaping results. CID widths are resolved once per distinct code within a single advance measurement; subsequent calls reread changed `/W` and `/DW` data.
- Replaced scratch file/mmap reopening with `playa.parse(bytes, max_workers=1)` behind the existing sole Playa import boundary. Every projection still creates a fresh document and performs the full interpreter pass; no old parser state is reused.
- Corrected the G4-discovered source-TJ overflow: fit to the actual projected source glyph envelope, use actual written font widths, preserve natural underflow spacing, and reconcile the terminal pen separately. Initial/final TJ adjustments and Tc/Tw state survive; positive tightening remains bounded and relative Tz retains its90% floor. Freshly interpreted replacement glyphs must retain the source anchor and fit its extent even when following text is absolutely positioned.

## Actual Full-Workload Evidence

Fixture: `govdocs1_013_013050.pdf`, SHA-256 `d0a3b06606378733a2ec96cfa01e3b12c111d13059d070e3e039b751347a4529`. It is a **40-page public USGS technical-document proxy, not a legal contract specimen**.

The test indexes all 40 pages and 3,000 source runs: 1,029 case-insensitive substring occurrences of the fixed common query produce 772 candidate run operations. Actual unfiltered preview reports the same 97 refusals: 75 shared operators and 22 unmapped Univers variants. Only these proposed refused operations are removed, retaining **all 675 accepted operations**. No page or operation sampling, recipe splitting, font override or raised timeout was used.

Final command after the G4 correction: `.venv/bin/python -m pytest -q -s -m corpus tests/test_find_replace_performance.py -x` — **2 passed in61.39s**.

| Actual isolated-worker call | Operations | Child CPU seconds | Wall seconds | Outcome |
|---|---:|---:|---:|---|
| Unfiltered actual preview | 772 | 3.525 | 3.562 | 97 expected named refusals, no PDF |
| Exact filtered actual preview | 675 | 18.802 | 18.855 | Successful, PDF null |
| Independent exact preview before apply | 675 | 18.871 | 18.977 | Successful, PDF null |
| Actual apply of that same complete recipe | 675 | 18.607 | 18.695 | Successful, PDF returned |

The successful preview/apply resolved reports are equal. The output starts with a valid PDF header, and the original bytes/digest remain unchanged. The unchanged constants are CPU20, worker default wall30, memory target1GiB, recipe50,000 operations and 10,000 characters per replacement; the complete recipe body is 107,593 bytes, below1MiB. No intermediate PDF is returned on preview or refusal.

These are **macOS local CPU/wall results**. They do not prove Linux address-space enforcement, tmpfs, seccomp, container execution, live CDN behavior or literal contract-specimen coverage. Gate G3 remains open and no deployment occurred. Output text/render fidelity across every page is the separate 05-04/G4 proof, not inferred from timing.

## Failing-to-Passing Measurements

- Initial research: filtered675 preview/apply were CPU-killed around22 child CPU seconds with an explicit40-second research wall allowance; this did not establish production-default success.
- One full classified snapshot per edit completed only in an unbounded diagnostic run:42.630 CPU /45.464 wall. Its703 page walks materialized about2.5 million glyph records. This falsified the plan's initial performance hypothesis and led to the recorded23October internal-strategy amendment.
- After selective decoding but before the final changes, strict675 preview still failed with `WORKER_FAILED`:20.151 CPU /23.016 wall.
- Per-call CID widths reduced the initial772 preview from4.532 to3.808 CPU, but strict675 still hit20.160 CPU. The retained full675 profile succeeded in32.814 instrumented seconds and identified703 scratch opens spending2.739 seconds in mmap/input setup.
- The final fresh memory projection removed that measured I/O cost, producing the successful unchanged-limit results above. Profiling/direct calls were diagnostic only; the acceptance results are actual `run_worker` calls without relaxed limits.

## Verification

- Focused recipe/rewrite/snapshot/password/page-scope suite: **98 passed in8.66s** before the final two narrow optimizations.
- Snapshot/fit/encoding suite after CID-width sharing: **76 passed in13.85s**.
- Helper/snapshot/recipe/rewrite/page-scope suite after memory projection: **98 passed in7.67s**.
- Helper/snapshot/Playa-probe/license checks, including rotated multipart path/bytes parity: **34 passed in1.16s**.
- Latest strict typing: `.venv/bin/python -m mypy engine/ server/` — **30 source files clean**.
- Final focused fit/recipe/rewrite/snapshot suite after source-TJ correction: **132 passed in11.49s**. Eleven new regression cases include three real compressed lines; rotation and nonuniform1Tf/Tm scaling;85Tz;Tc/Tw; initial/final TJ numbers; single/multioperator runs; short and condensed replacement followers; and corrupted-emission negative controls on both fast and fallback paths.
- Full675 actual isolated preview/apply corpus tests: **2 passed**, exact timings above.
- `git diff --check`: passed before the integration commit. The orchestrator owns the final full-suite and phase review.

Negative controls include every-splice validation, real following-glyph movement, late atomic failure for plain/encrypted inputs, prefix-state and operand tampering, mutable font-state freezing, same-name/different-alias fonts, shared source IDs, interleaved multioperator targets, multiple parts, lost identities, shared Form fallback, unchanged-page/annotation preservation and the existing glyph ceiling.

## Task Commits and TDD Evidence

1. Initial snapshot RED `c461159`; GREEN `b292d30`.
2. Repeated-sort RED `9ea7313`; scratch/bundled metadata optimization `aa7efda`.
3. Projection/font tests were captured in shared-index RED `8d99e0e`; no history was rewritten. The executor's owned tests remained responsible for their verification.
4. Guarded fast-path RED `50ebc73`; selective helper GREEN `262f05e`.
5. Repeated CID-width RED `6cd487f`; GREEN `b943c9e`.
6. Scratch mmap RED `0d32029`; fresh memory projection GREEN `805eff2`.
7. Guarded recipe/rewrite integration and complete-workload report checks `f4670cb`.
8. Source-TJ visible-overflow RED `fd8484d`; separate envelope/pen GREEN `a49976a`.

## Deviations from Plan

1. **[Rule3 — Blocking issue] Full classification per splice did not meet the measured budget.** The orchestrator explicitly amended the internal strategy on23October after the42.630-CPU diagnostic. Fresh interpretation, target reclassification and every individual fidelity guard remain mandatory; only unrelated glyph construction/clustering is avoided.
2. **[Rule2 — Performance correctness] Extended narrow ownership to bundled metadata, `engine/fit.py` per-call CID lookup sharing and `engine/playa_boundary.py`'s existing bytes-parser alias.** Each extension was approved by the orchestrator, profiled, tested and committed separately. No dependency, public API, external service or security limit changed.
3. **[Rule1 — Bug] G4 exposed visible source-TJ overflow despite a zero fit delta.** On page6 the source spans386.964/387.000pt while nominal dictionary sums are394.248/398.580pt. Inter-word widening targeted those larger sums and produced6.48/10.105pt overhang; an absolute following line hid it from D04. A full accepted-set check also found64 natural-width overflows, ruling out merely disabling widening. The corrected fit uses actual projected source extent, actual written widths, and a separate terminal-pen target, with an independent fresh anchor/envelope guard. An old direct-refusal expectation now reconstructs actual dictionary widths (283.50pt rather than program-derived283.53pt); no threshold was relaxed. Narrow engine/test extensions were explicitly approved. RED `fd8484d`, GREEN `a49976a`.
4. **Metadata coordination:** STATE, ROADMAP and REQUIREMENTS are reserved to the orchestrator to avoid concurrent updates. This executor supplies the committed plan summary and exact evidence for those updates.

## Known Stubs and Threat Flags

No blocking stubs, new network endpoint, authentication flow, persistent document cache or external dependency was introduced. Temporary/current document state is owned by the disposable recipe worker; every context/document is closed on success and refusal.

## Self-Check: PASSED

All listed implementation/test files exist, all listed commit hashes are present, the complete675-operation acceptance tests pass, and the original corpus source remains unchanged. Phase completion, G4 fidelity and public-release gates are not claimed here.
