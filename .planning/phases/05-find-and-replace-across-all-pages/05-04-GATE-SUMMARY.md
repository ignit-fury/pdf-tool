---
phase: 05-find-and-replace-across-all-pages
plan: 04
subsystem: testing
status: in_progress
tags: [batch, fidelity, corpus, renderers]
key-files:
  created: [tests/test_find_replace_recipe.py]
  modified: [tests/test_gate_g4.py]
completed: null
---

# Phase 5 Plan 4: Server Integration and G4 Evidence

The real client recipe builder and ordinary HTTP edit endpoint pass batch integration;
the complete 675-operation corpus gate currently exposes a visible width-fit defect.
This is a continuation record, not a completed G4 or Phase 5 sign-off.

## Completed Server Integration

Committed `456f3ca` adds five integration cases, exercising actual shipped Node helpers
and real worker/API mutation rather than mocking rewrite success:

- Exclude one of two occurrences in the same run while preserving an unrelated prior operation.
- Actual HTTP failed-preview → refusal-filter → exact successful preview → one apply.
- Older text, bold font program and RGB style survive, and a second batch searches
  the current recipe overlay using immutable original addresses.
- Fit and foreign-source refusals return no partial PDF from preview or apply.
- Explicit replacement font recovers both an unmapped substitution font and a real
  embedded original CFF source (`govdocs1_000_000013.pdf`).

Verification: four non-corpus integration cases plus the corpus CFF case passed.
The combined focused command with G4 helper controls passed **9 tests in 5.14s**.
After adding outward-rounding/rotated-device-space geometry coverage, the G4 fast
helper command passed **6 tests**. The existing Starlette/httpx deprecation warning
is unchanged; no package was installed.

The generated subset alias names its family without a weight suffix. The integration
test verifies the embedded font program's actual OS/2 weight (≥700), rather than
assuming `Bold` appears in that PDF alias.

## Complete Batch Proof — What Passed

Source: immutable 40-page public USGS technical-document proxy
`govdocs1_013_013050.pdf`, SHA-256
`d0a3b06606378733a2ec96cfa01e3b12c111d13059d070e3e039b751347a4529`.
This source is not a literal legal contract.

The browser model retains all **1,029 occurrences / 772 distinct matching run IDs**.
The new ambiguous-address guard disables **69** shared-address runs before preview;
the actual initial preview therefore receives **703 operations** and reports **28**
further refusals (**6** shared-operator, **22** font-mapping). Aggregate refusals remain
**97** and the entire **675-operation** accepted workload is retained. No eligible
operation was sampled, silently omitted or split into another apply.

The final candidate excludes exactly one occurrence in an otherwise changed run and
preserves an earlier color operation on that same run. It still contains 675 operations.
Actual unchanged-limit worker evidence from the 2026-10-24 G4 run:

| Stage | Operations | Child CPU | Wall | Result |
|---|---:|---:|---:|---|
| Initial preview | 703 | 3.306s | 3.339s | Expected refusal report, no PDF |
| Earlier style preview | 1 | 0.376s | 0.404s | Passed, no PDF |
| Earlier style apply | 1 | 0.391s | 0.422s | Passed |
| Exact final preview | 675 | 18.137s | 18.312s | Passed, no PDF |
| Exact final apply | 675 | 18.285s | 18.439s | Passed, matching report |

The full output passed qpdf validation. Before the renderer failure, the gate verified:

- Every requested run's exact newly written Unicode at its original physical part/anchor.
- Independent PDFium full-page character deltas on all 40 pages, without assuming
  engine and PDFium reading orders match.
- Every untouched instruction retained in its original part and relative order.
- The individual opt-out retained and the earlier RGB style still present at its anchor.
- Original source bytes unchanged.

These checks are complementary: a character counter alone is not a proof of correct placement.

## G4 RED — Width-Fit Defect Under Repair

Commit `7491ec5` records the full all-page gate and its passing fast controls. The gate
compares every original/output page in PDFium, Poppler and MuPDF, requiring zero
same-engine changed pixels outside the union of individual run regions and zero
unmasked changes on unchanged pages. Cross-engine comparisons alone use the existing
measured antialiasing tolerance. A control proves a changed pixel between disjoint
masks cannot be hidden by an enclosing rectangle; another rejects unchanged output.

The actual run stopped on **page 6 / PDFium**, with **76 changed pixels outside**
the original-run bounds plus 3pt padding. Pages 1–5 passed all three engines first.
The mask was not widened and the gate was not marked passed.

Two concrete original addresses (page index 5, part 0):

- `:o3749`, anchor `(54, 213.48)`: original advance-right 440.964pt,
  rewritten advance-right 447.445pt.
- `:o5086`, anchor `(54, 242.28)`: original advance-right 441.0pt,
  rewritten advance-right 451.105pt.

Both planning rows claimed `inter_word_kern` with zero remaining width delta. An
independent PDFium crop confirmed the actual ink edge moves from device x=912 to
x=926 on the first affected row, so this is not only an advance-box estimate.
The engine owner has the exact two-operation recipe and is correcting actual written
width fitting. D-04 alone does not catch this case because following lines are absolutely
positioned. No renderer tolerance, mask, worker cap or accepted workload was relaxed.

Private local diagnostic artifacts:

- `/private/tmp/phase5-g4-overflow-recipe.json`
- `/private/tmp/phase5-g4-crop-page6.png`
- `/private/tmp/phase5-g4-overflow-pair.png`
- `/private/tmp/pdf-tool-phase5-g4-before-fit-fix-20261024.log`
- `/private/var/folders/qg/ht00h1254_97sydt041dfvtr0000gn/T/pytest-of-prempatel/pytest-129/test_g4_full_40page_batch_text0/batch.pdf`

## Remaining Work

1. Finish the engine fit correction with its focused regression.
2. Rerun the full unchanged-limit 675-operation preview/apply proof.
3. Rerun `pytest -q -s -m corpus tests/test_gate_g4.py -x`, completing all 40 pages
   and all 120 same-engine original/output comparisons. Preserve the current zero threshold.
4. Root combines these results with actual browser apply/undo evidence and final review.

No deployment occurred. Literal contract-specimen coverage and Phase 4 Linux/container/CDN
release gates remain unproven. Root owns STATE, ROADMAP, REQUIREMENTS and the final
05-G4-RESULTS/05-04-SUMMARY; this executor has not marked them complete.

## Self-Check

Both owned test files and commits `456f3ca`, `7491ec5` exist. Server integration is
verified; the complete G4 criterion remains RED until the reproduced defect is fixed
and the all-page run finishes.
