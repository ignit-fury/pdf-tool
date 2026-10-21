# Instruction-Correlation Bridge: Measured Results

**Phase:** 03-rewrite-engine-font-pipeline, Plan 02 (Tasks 1-2)
**Question answered:** Can a run's own byte-offset-addressed operators
(`GlyphRecord.operator_byte_offset`, from `playa`) be correlated to
`pikepdf.parse_content_stream()`'s byte-offset-free instruction-list indices, reliably enough that
plan 03-06's `engine/rewrite.py` can find and replace exactly the instructions belonging to one run
without touching any other instruction on the page?

**Answer: Yes, with one residual risk explicitly not ruled out** — see "What This Does NOT Prove"
below. The mechanism (`touched_instruction_indices`, ordinal position among text-showing operators)
held on all 4 hand-picked hard cases and produced zero false-`ok` results across a 217-document,
129,491-run corpus sweep. The verdict is **GO**, conditioned on 03-06's own already-planned D-04
runtime guard remaining in place as an independent second layer — see "GO/NO-GO Verdict" below.

---

## Task 1: Four named hard cases

Measured directly from `tests/test_instruction_correlation_probe.py`.

| Case | Fixture | Detail | Result |
|---|---|---|---|
| Single-operator baseline | `spike/fixtures/tj_refit_sample.pdf`, page 0 | Programmatically-selected editable run whose glyphs span exactly one operator byte offset | `ok=True`, exactly 1 touched instruction |
| Pitfall 1 — 62-operator run | `corpus/public/irs_form_1040.pdf`, page 0, run `:o1391` | RESEARCH.md's own measured multi-operator case | `ok=True`, exactly 62 touched instructions |
| Pitfall 2 — non-contiguous | `corpus/public/irs_form_w4.pdf`, page 0 | A foreign run's own operator sits strictly between this run's first and last operator | `ok=True`; foreign run's own touched indices are disjoint from this run's — its instruction was not claimed |
| Pitfall 2 — non-contiguous | `corpus/public/irs_form_w4.pdf`, page 4 | Same shape, different page | `ok=True`; foreign run's own touched indices disjoint, same guarantee holds |

Both `irs_form_w4.pdf` cases exercise a known, separately-documented artifact: parsing one
`/Contents` array part in isolation reproduces a `pikepdf` `UserWarning: Unexpected end of stream`
where a token legitimately spans two parts. Neither touched run's own operators sit near that
truncation point in these two cases — both resolve `ok=True` with disjoint indices, and the page-0
case pins the warning explicitly via `pytest.warns` rather than letting it print silently.

## Task 2: Corpus-wide sweep

Measured directly from `tests/test_instruction_correlation_corpus.py`, running
`test_correlation_holds_across_corpus` against all 217 manifest documents (including the 17
known-malformed/edge-case documents), up to 5 pages per document (03-RESEARCH.md's own measurement
cap, keeping counts comparable to its published 129,491/13,752/1,431 figures).

| Metric | Measured value |
|---|---|
| Documents in manifest | 217 |
| Editable runs checked | 129,491 |
| Multi-operator runs checked (Pitfall 1's risk case) | 13,752 |
| Correlation failures | **89**, across 19 documents |
| Walk exceptions | **2** |

**Every one of the 89 correlation failures has the identical reason string**:
`"correlation produced zero touched instructions"` — `touched_instruction_indices`'s own most
conservative refusal path. This is not a case where the mechanism returned a wrong-but-plausible
index; it is the mechanism declining to return anything at all. Confirmed directly by tracing
`correlate_run`'s own validation code (`spike/instruction_correlation_probe.py`): there is no code
path that returns `ok=True` except after every touched index has passed both the in-range check
and the text-showing-operator check. A zero-touched result is therefore structurally incapable of
being a silent wrong-index — it is the mechanism's safest possible failure mode. The 89 failures
span 17 `govdocs1_*` documents plus `irs_form_1040.pdf` and `irs_form_1040_spanish.pdf` and
`irs_publication_17.pdf` (19 distinct documents total); the likely cause (not verified further,
out of this task's scope) is the same part-boundary truncation named in "What This Does NOT Prove"
below, undercounting rather than shifting.

The 2 walk exceptions are `govdocs1_011_011089.pdf` (`PDFSyntaxError`, malformed structure) and
`irs_form_w9_encrypted.pdf` (`PDFEncryptionError`, a real encrypted fixture) — both pre-existing,
already-documented Phase 2 findings (both are among the manifest's 17 known-malformed/edge-case
documents), not new failure modes this task discovered. Neither is a correlation disagreement —
both are refusals to open/walk the document at all, before any instruction correlation is
attempted.

## What This Does NOT Prove

`touched_instruction_indices`'s own validation — every returned index in range, every returned
index addressing a text-showing operator — cannot distinguish a **correct** ordinal from a
**shifted-but-still-plausible** one. `spike/instruction_correlation_probe.py`'s own module
docstring names this open risk directly: `correlate_run` parses one isolated content-stream
*part* at a time. A `/Contents` array part boundary that truncates a token mid-stream could, in
principle, leave orphaned leading bytes at the **start** of the *next* part; if pikepdf's recovery
there mis-tokenizes those orphaned bytes in a way that still produces valid-looking text-showing
operators, the ordinal count for **every run in that next part** could be silently shifted — while
every one of `correlate_run`'s own checks (in-range, text-showing operator) would still pass.

Neither the 4 hand-picked cases (Task 1) nor the 217-document sweep (Task 2) rules this out. No
case in either task happens to touch a run addressed near a part boundary's leading edge, and the
corpus sweep has no visibility into which runs sit in a part immediately following a
truncation-affected part — it does not track part-boundary adjacency at all, so it cannot report
whether that specific scenario was ever exercised. This is a real, unprobed residual risk, not one
resolved by either task.

Two distinct gaps limit how much 03-06's own D-04 guard (see "GO/NO-GO Verdict" below) can be
trusted to catch this risk as a downstream symptom, and both must be named plainly rather than
folded into one optimistic sentence:

1. **An intervening absolute `Tm`/`Td` reset.** If a repositioning operator sits between the
   mis-edited instruction and D-04's checkpoint glyph, the checkpoint's position is set fresh from
   that operator, not accumulated from the mis-edited instruction's advance — masking the
   corruption from this specific check.
2. **A downstream ordinal shift (a second, distinct gap, not a restatement of the first).** D-04's
   reasoning that a wrong-instruction edit "shifts every glyph's position downstream of it"
   silently assumes the mis-targeted instruction sits *upstream* of the checkpoint glyph in stream
   order. The shift mechanism (playa and pikepdf disagreeing on operator count near a
   truncation-recovery point) has no reason to favor upstream over downstream — it could just as
   plausibly point to an instruction that comes *after* both the intended run and its own D-04
   checkpoint glyph. In that case the checkpoint glyph's position is already fixed **before** the
   wrongly-edited instruction ever executes, and D-04 would pass cleanly on a genuinely corrupted
   document. Unlike the `Tm`/`Td` case, this needs no special coincidence in the document's own
   structure — only an ordinal shift that happens to land past the checkpoint, which is roughly as
   likely as one landing before it.

## GO/NO-GO Verdict

**GO.** `engine/rewrite.py` (03-06) may proceed building on this correlation bridge, conditioned on
03-06's own D-04 runtime text-matrix-invariant guard remaining a required part of the design, not
an optional add-on.

Reasoning for the condition: 03-06-PLAN.md's own D-04 guard re-walks the page after every
content-stream mutation and compares the text matrix immediately following the edited run against
its pre-edit value, refusing by name (`"text_matrix_shifted_after_edit"`) on a genuine violation.
This re-walk uses the same ground-truth playa-based page parse `engine/index.py`'s `RunIndex`
already performs on the actual, final document bytes — it is not built on the same
part-isolated-instruction-list indexing that carries this task's residual risk, so it is an
independent check, not a second application of the same blind spot.

If the undetected-ordinal-shift scenario ever occurred in practice, `rewrite_run` would have built
its replacement instructions to fit the *intended* run's original advance width, then spliced them
into whatever instruction the shifted ordinal actually pointed at — almost certainly a different
instruction with a different original width. That mismatch would often propagate as a detectable
position change in the actual rendered content: PDF text positioning within a `BT`/`ET` block
accumulates from prior operators' advances, so editing the wrong instruction *upstream* of D-04's
checkpoint glyph would often, not generally, shift that checkpoint glyph's position along with
everything else downstream of the mis-edited instruction. This is not a mathematical guarantee, and
two distinct gaps limit it (both named in full in "What This Does NOT Prove" above, restated here
briefly): an intervening absolute `Tm`/`Td` repositioning operator between the mis-edited
instruction and the checkpoint glyph could reset position and mask the corruption from this
specific check; and, distinctly, the shifted ordinal could just as plausibly point to an
instruction *downstream* of the checkpoint glyph rather than upstream of it — in which case the
checkpoint's position is already fixed before the mis-edited instruction ever executes, and D-04
would pass cleanly on a genuinely corrupted document. Neither gap needs an unusual document
structure to occur; the second needs nothing more than the ordinal shift landing on the "wrong"
side of the checkpoint, which is roughly as likely as landing on the other side. So the catch is
real but partial: a corrupted rewrite would often, not generally or with any guarantee, produce a
detectably-wrong post-run text matrix.

The honest basis for GO is therefore not that the residual risk is zero — it is not — but that the
overall system has two independent layers against it: the correlation mechanism's own conservative
refusal-on-zero-touched behavior (Task 2's measured 89-for-89 clean refusal record), and 03-06's
separately-planned, ground-truth re-walk guard that would often, though not always (per the
Tm/Td-reset and downstream-shift gaps above), surface this specific failure mode as a symptom even
though this correlation task alone cannot rule out its cause. If 03-06's D-04 guard is ever
weakened, removed, or made test-only rather than a runtime check, this GO verdict should be
revisited.

---

## Reusable for Phase 3

The following are carried forward for 03-06 to build on directly, per
`.planning/phases/03-rewrite-engine-font-pipeline/03-CONTEXT.md`'s Claude's-Discretion note on
spike code disposition ("Absorb, rewrite, or leave alone" — that specific choice is deferred to
03-06, not resolved here):

1. **`spike/instruction_correlation_probe.py`** — specifically `touched_instruction_indices`, the
   pure, no-I/O ordinal-correlation algorithm itself. Whether 03-06 imports this module directly,
   ports the function's body verbatim into `engine/rewrite.py` (03-06-PLAN.md's own stated
   architecture decision is to port, not import, matching `spike/tj_refit_prototype.py`'s
   established throwaway posture), or leaves the module standalone is 03-06's call to make — but
   the algorithm itself and the measured results in this document are carried forward regardless
   of that packaging decision.
2. **`tests/test_instruction_correlation_probe.py`** — the 4 named hard-case tests (single-operator
   baseline, the 62-operator `irs_form_1040.pdf` case, both `irs_form_w4.pdf` non-contiguous
   cases). 03-06's own `tests/test_rewrite.py` should port these as its
   `test_multi_operator_run_consolidates_to_one_instruction` and
   `test_foreign_interleaved_operator_survives_unedited` regression fixtures (both names already
   reserved in `03-VALIDATION.md`) — port the test *cases*, not re-derive them.
3. **`tests/test_instruction_correlation_corpus.py`** — the corpus-wide sweep harness and its
   `KNOWN_CORRELATION_FAILURES`/`KNOWN_WALK_EXCEPTIONS` pinned exact-set constants. Any future
   change to the correlation mechanism should be checked against this sweep before being trusted at
   corpus scale.
4. **`irs_form_1040.pdf` run `:o1391`** (62 touched instructions) — the named regression fixture
   for `test_multi_operator_run_consolidates_to_one_instruction`.
5. **`irs_form_w4.pdf` pages 0 and 4** (both non-contiguous, foreign-run-interleaved cases) — the
   named regression fixtures for `test_foreign_interleaved_operator_survives_unedited`.
