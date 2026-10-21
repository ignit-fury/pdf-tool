"""Instruction-ordinal correlation probe.

THROWAWAY SPIKE CODE, per this repo's `spike/` convention (see `spike/tj_refit_prototype.py`'s
own module docstring for the precedent). Answers exactly one question, per
`.planning/phases/03-rewrite-engine-font-pipeline/03-02-PLAN/task-1-brief.md`: can a run's own
`GlyphRecord.operator_byte_offset` values (playa-derived, byte-offset-addressed) be correlated to
`pikepdf.parse_content_stream()`'s instruction-list indices (byte-offset-free), reliably enough
that a later module (plan 03-06's `engine/rewrite.py`) can find and replace exactly the
instructions belonging to one run without touching any other instruction on the page?

## What IS proven here
`touched_instruction_indices` -- the correlation is by ORDINAL POSITION among text-showing
operators (`Tj`/`TJ`/`'`/`"`), never by byte offset (pikepdf's `ContentStreamInstruction` exposes
none). Both playa (via `RunIndex`/`GlyphRecord.operator_byte_offset`) and pikepdf
(`parse_content_stream`) walk the SAME bytes in the SAME order, so the Nth text-showing operator
counted by playa's own offsets and the Nth text-showing instruction counted by pikepdf's own
instruction list are the same operator, without either side ever exposing the other's addressing
scheme.

## What is NOT proven here
Nothing about content-stream SURGERY (replace/delete/reserialize) -- that is plan 03-06's job.
This module only locates. No width-fitting, no font substitution, no TJ-array arithmetic.

**Open risk, not ruled out by this module's own tests -- Task 2/3's corpus sweep must actually
probe it:** `correlate_run` parses ONE isolated content-stream PART at a time
(`stream_bytes_and_resources` + `pdf.make_stream()` + `parse_content_stream()` on that one
part's own bytes), because run IDs are part-scoped, never coalesced-page-scoped
(`engine/run_id.py`'s own stated rule -- `o` "is only meaningful alongside the part index, never
in coalesced space"). `engine/identity_rewrite.py` sidesteps the consequence of this by parsing
the WHOLE PAGE and letting `pikepdf.parse_content_stream(page)` coalesce every array element
itself before tokenizing -- a structurally different code path this function cannot take, since
it must address one part in isolation. Parsing a part in isolation reintroduces exactly the
split-token-across-`/Contents`-array-elements truncation `identity_rewrite.py`'s own docstring
already documents (a token's bytes legitimately span two parts in some producers' output): this
module's four test cases confirm the TESTED part's own ordinals are unaffected by the truncation
at THAT part's tail (`pytest.warns` in `tests/test_instruction_correlation_probe.py` pins the
exact warning pikepdf emits there), but they do NOT prove the truncated token's orphaned LEADING
bytes can't corrupt the ordinal count at the START of the NEXT part in the same `/Contents`
array. No case tested here happens to touch a run addressed near a part boundary's leading edge.
Whoever writes plan 03-06/Task 2-3's corpus sweep needs to actually construct or find that case
and confirm `touched_instruction_indices` still produces correct ordinals on it -- this is an
open question this spike leaves unanswered, not a verified-safe one.

Algorithm and pseudocode source: `.planning/phases/03-rewrite-engine-font-pipeline/03-RESEARCH.md`,
Architecture Patterns, Pattern 1 ("Instruction-identity content-stream surgery, not byte-range
splicing" -> "Correlating a byte-offset-addressed run to pikepdf's byte-offset-free instruction
list"). The two hard cases this module is required to reproduce exactly are RESEARCH.md's own
measured numbers: Pitfall 1 (a 62-operator, 63-glyph run on `irs_form_1040.pdf`) and Pitfall 2 (a
non-contiguous run on `irs_form_w4.pdf` with a foreign run's own operator interleaved between its
first and last).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pikepdf

from engine.classify_run import stream_bytes_and_resources
from engine.index import RunIndex
from engine.run_id import decode_run_id

TEXT_SHOWING_OPERATORS = frozenset({"Tj", "TJ", "'", '"'})


@dataclass(frozen=True, slots=True)
class CorrelationResult:
    """The project's established verdict shape (03-PATTERNS.md "Shared Patterns" --
    frozen/slots, named-reason). `reason` is populated only when `ok` is False."""

    run_id: str
    touched_indices: tuple[int, ...]
    ok: bool
    reason: str | None = None


def touched_instruction_indices(
    instructions: list[pikepdf.ContentStreamInstruction],
    run_operator_offsets: set[int],
    all_operator_offsets_sorted: list[int],
) -> list[int]:
    """Map a run's own operator byte offsets to `instructions`' own list indices, via
    ordinal position among text-showing operators -- NOT byte offset (pikepdf exposes
    none). Pure function, no I/O. RESEARCH.md Pattern 1's own pseudocode, verbatim.
    """
    ordinal_of_offset = {off: i for i, off in enumerate(all_operator_offsets_sorted)}
    wanted_ordinals = {ordinal_of_offset[off] for off in run_operator_offsets}

    result: list[int] = []
    seen = 0
    for idx, instr in enumerate(instructions):
        if str(instr.operator) in TEXT_SHOWING_OPERATORS:
            if seen in wanted_ordinals:
                result.append(idx)
            seen += 1
    return result


def correlate_run(pdf_path: Path, page_index: int, run_id_suffix: str) -> CorrelationResult:
    """Resolve a real run (matched by `run_id_suffix` against its full run_id) via
    `RunIndex`, correlate it against the same content-stream part's pikepdf instruction
    list, and validate every returned index. `ok=True` only when every touched index is
    in range AND addresses a Tj/TJ/'/" instruction -- never a crash on a bad
    correlation, a named `reason` instead.
    """
    with RunIndex(pdf_path) as idx:
        page = idx.page(page_index)
        target = next(
            (run for run, _verdict in page.runs if run.run_id.endswith(run_id_suffix)), None
        )
        if target is None:
            return CorrelationResult(
                run_id=run_id_suffix,
                touched_indices=(),
                ok=False,
                reason=f"no run on page {page_index} with run_id ending {run_id_suffix!r}",
            )

        target_parts = decode_run_id(target.run_id)
        target_key = (target_parts["xobj_path"], target_parts["part"])

        run_operator_offsets = {g.operator_byte_offset for g in target.glyphs}

        # Every run sharing the same part -- not only editable runs (RESEARCH.md Pitfall 2:
        # the interleaved operator that must NOT be corrupted can belong to a foreign run
        # of any verdict).
        all_offsets: set[int] = set()
        for run, _verdict in page.runs:
            parts = decode_run_id(run.run_id)
            if (parts["xobj_path"], parts["part"]) == target_key:
                all_offsets.update(g.operator_byte_offset for g in run.glyphs)
        all_operator_offsets_sorted = sorted(all_offsets)

        with pikepdf.open(pdf_path) as pdf:
            stream_bytes, _resources = stream_bytes_and_resources(
                pdf, page_index, target_parts["part"], target_parts["xobj_path"]
            )
            stream_obj = pdf.make_stream(stream_bytes)
            instructions = pikepdf.parse_content_stream(stream_obj)

            touched = touched_instruction_indices(
                instructions, run_operator_offsets, all_operator_offsets_sorted
            )

            if not touched:
                return CorrelationResult(
                    run_id=target.run_id,
                    touched_indices=(),
                    ok=False,
                    reason="correlation produced zero touched instructions",
                )

            for i in touched:
                if not (0 <= i < len(instructions)):
                    return CorrelationResult(
                        run_id=target.run_id,
                        touched_indices=tuple(touched),
                        ok=False,
                        reason=f"index {i} out of range for {len(instructions)} instructions",
                    )
                operator = str(instructions[i].operator)
                if operator not in TEXT_SHOWING_OPERATORS:
                    return CorrelationResult(
                        run_id=target.run_id,
                        touched_indices=tuple(touched),
                        ok=False,
                        reason=(
                            f"index {i} addresses operator {operator!r}, not a "
                            "text-showing instruction"
                        ),
                    )

            return CorrelationResult(
                run_id=target.run_id, touched_indices=tuple(touched), ok=True
            )


__all__ = ["CorrelationResult", "correlate_run", "touched_instruction_indices"]
