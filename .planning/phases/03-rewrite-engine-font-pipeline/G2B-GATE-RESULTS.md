# Gate G2b Manual Verification Results

**Date:** 2026-08-28
**Requirement:** D-15 (03-CONTEXT.md) — the three checks that have no CLI/API surface to
automate: viewer repair-prompt behavior, Acrobat copy-paste Unicode fidelity, and D-08's
contact-sheet seam review. Task 2's automated D-15 gate (`tests/test_gate_g2b.py::test_g2b_full_pipeline`)
already passed before this checkpoint was opened, per this task's own threat model (T-03-09-04:
never ask a human to open a file that has not already passed OTS-sanitize / `qpdf --check`).

## Decision

**GO.** All three manual checks pass. Gate G2b is closed — the entire web tier (Phase 4
onward) is unblocked.

## Evidence (2026-08-28)

Reproduction command:

```
python -m harness.g2b_fixture --output-dir /tmp/g2b_manual_review --samples 3
```

Produced three rewritten PDFs and three before/after contact-sheet PNGs from real corpus
documents (`govdocs1_000_000019.pdf`, `govdocs1_000_000016.pdf`, `govdocs1_000_000018.pdf`),
each carrying one live, substitution-forcing edit (per `harness/g2b_fixture.py`'s own
never-asserted-by-construction discipline — every edit was proven via a real `plan_recipe`
call to force `engine.fonts`'s substitution trigger before being applied).

### Viewer open test — no repair/recovery prompt

| Viewer | Opened without repair prompt | Notes |
|---|---|---|
| Acrobat Reader | Yes | All three rewritten PDFs opened cleanly. |
| macOS Preview | Yes | All three rewritten PDFs opened cleanly. |
| Chrome | Yes | All three rewritten PDFs opened cleanly. |

### Copy-paste Unicode check

| Check | Result | Notes |
|---|---|---|
| Acrobat Reader: select substituted run, copy, paste into a plain-text editor | Pass | Pasted text matched the recipe's own replacement text exactly, including the substituted accented character. Neither the pasted text nor the recipe text is recorded here (T-03-09-05). |

### Contact-sheet seam review (D-08)

| Check | Result | Notes |
|---|---|---|
| Visual seam review at 100% zoom | Pass | 3 of 3 contact sheets reviewed (`govdocs1_000_000019`, `govdocs1_000_000016`, `govdocs1_000_000018`). No visible seam mid-run in any sample — the substituted run reads as continuous with its surrounding, untouched text at full zoom. |

## Why GO

- Task 2's automated gate already proved, on a real corpus document: an OTS-clean emitted
  Liberation subset, a structurally valid `qpdf --check` output, zero same-engine masked
  pixel diff outside the substituted run's own bounding box across pdfium/poppler/mupdf,
  cross-engine tolerant agreement on the rewritten output, and an exact ToUnicode text
  round-trip through the real read pipeline.
- Task 3 extended that proof to the case the automated suite cannot reach alone: two edits
  sharing one bundled-family subset, confirmed (by real object identity, not value equality)
  to be served by a single embedded font object, with both edits' text recovering correctly
  and neither edit's own untouched-elsewhere text visibly disturbed.
- This checkpoint closes the three remaining D-15 clauses that have no CLI/API surface:
  real desktop/browser viewers do not flag the rewritten files as damaged, Acrobat's own
  Unicode copy-paste path recovers the substituted character correctly (the actual
  user-facing proof "select and copy this text" works, not just a programmatic proxy for
  it), and a human eye confirms no visible seam at the pixel level the automated
  same-engine clause's coarse mask (a fixed padding standing in for real font
  ascent/descent, per `tests/test_gate_g2b.py`'s own ponytail-tagged simplification) could
  in principle miss.
- Combined, D-15's full clause set — five automated (Task 2), one extended-scope automated
  (Task 3, FONT-02 criterion 3), three manual (this document) — all pass on real corpus
  data. No clause was skipped, weakened, or asserted by construction anywhere in this
  gate's evidence chain.

## What was NOT tested (explicitly out of scope for this checkpoint)

- Only 3 of the 12 measured-good candidate documents were sampled for the manual review
  (`--samples 3`); the other pinned candidates and the full corpus were not manually opened.
  Task 2's automated gate is the standing per-commit proof for the general case — this
  checkpoint is a one-time sanity check on real viewer behavior, not a corpus sweep.
- Only Acrobat Reader's copy-paste path was checked interactively. macOS Preview's and
  Chrome's own text-selection/copy behavior were not separately verified (Task 2's
  automated ToUnicode-round-trip clause already covers the underlying CMap correctness
  every viewer's copy-paste ultimately depends on).
- Glyph-level rendering fidelity (hinting, anti-aliasing, sub-pixel positioning differences
  between viewers) was not assessed beyond "no visible seam" — D-15 does not require
  pixel-perfect cross-viewer rendering parity, only that the same-engine and cross-engine
  automated clauses (Task 2) and this checkpoint's seam review together rule out a visibly
  broken edit.
- Non-Latin substitution (CJK, RTL scripts) was not exercised in this checkpoint's sample —
  the forcing mechanism (`harness/g2b_fixture.py`'s accent-mapping + CJK fallback) can
  reach this case, but none of the three sampled documents happened to need it. Not a
  blocker: D-05's whole-run substitution and D-13's per-family subsetting are
  script-agnostic by construction, and the automated gate's own coverage is not limited to
  Latin scripts.
