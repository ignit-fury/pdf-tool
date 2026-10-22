"""EDIT-02/EDIT-04/FONT-06: the module that actually performs a text edit inside a real
PDF's content stream -- by instruction identity, never by byte range, and never by
reshaping `/Contents`.

`engine/identity_rewrite.py`'s own docstring draws the boundary this module crosses
("ZERO width-fitting, ZERO font subsetting, ZERO glyph substitution, ZERO TJ-array
arithmetic" -- Phase 3 is the phase that does all four). Its per-instruction
unparse-and-newline-join pattern is reused here verbatim; its `/Contents`-coalescing is
deliberately NOT (see Pitfall 3 below).

## Architecture decision (03-06-PLAN.md, Claude's Discretion per 03-CONTEXT.md)

`touched_instruction_indices` is **ported, not imported**. The corpus-validated
correlation bridge 03-02 built lives in `spike/instruction_correlation_probe.py`, and
`engine/` imports nothing from `spike/` anywhere in this codebase -- matching
`spike/tj_refit_prototype.py`'s own throwaway posture ("absorb, rewrite, or leave
alone"). The algorithm below is byte-for-byte the same logic 03-02 proved against the
217-document public corpus; only its module location changed. Re-deriving or
re-measuring it here would prove nothing 03-02 has not already proved.

The module is built in **three layers**, so each plan task hands the next a clean seam:
1. `rewrite_instructions` (this task) -- the low-level splice primitive. Given a run and
   an already-built `list[pikepdf.ContentStreamInstruction]` to install, it correlates,
   replaces the first touched instruction's slot with that list, deletes every other
   touched instruction by list index, and writes back.
2. `rewrite_run` (later task) -- the public entry point: Tz bracketing, D-04's post-edit
   text-matrix guard, and the substitution/non-substitution dispatch.
3. The recipe/CLI layer above it (plan 03-07).

## Pitfall 1 and Pitfall 2 are the SAME mechanism, with no special case for either

10.6% of editable runs span more than one text-showing operator (up to 167 measured),
and ~1.1% have another run's own operator sitting strictly between their first and last.
Deleting the run's own touched instructions **one at a time, by list index** handles both
at once: the multi-operator case is just "more than one index", and anything at an
intervening index is never referenced, so it survives untouched at its original relative
position. No span, no byte range, no "check for scary operators in between" -- the hazard
is a run's operators being non-contiguous, not something scary being nearby.

## Pitfall 3: never reshape `/Contents`

`identity_rewrite` collapses a page's `/Contents` ARRAY into one stream, which is correct
for proving a round-trip and the wrong default to copy here: collapsing N elements into 1
deletes N-1 indirect objects and renumbers every subsequent object in the file. Measured
directly in 03-RESEARCH.md -- a single-word text change produced a **13,689-line**
`qpdf --qdf` diff, dominated by renumbering of objects nothing touched, which is precisely
what Gate G2a's confined-diff criterion exists to catch. 52.5% of the corpus has an array
`/Contents`, so this is not a rare shape. `_write_part_bytes` therefore replaces only the
one array ELEMENT that changed (`contents[part] = pdf.make_stream(new_bytes)`), leaving
the array's length and every other element's object number untouched -- and writes an
XObject-sourced part in place (`xobj.write`), which does not allocate an object at all.

## Part-boundary truncation is refused, never silently written back

A run ID is part-scoped (`engine/run_id.py`: the byte offset "is only meaningful alongside
the part index, never in coalesced space"), so this module must parse ONE `/Contents` array
element in isolation -- it cannot take `identity_rewrite`'s route of letting
`pikepdf.parse_content_stream(page)` coalesce the whole page first. Some producers split a
single instruction's tokens across two array elements, which is legal PDF: measured on
`irs_form_w4.pdf` page 0, `contents[5]` ends `...BT\n/Content <</MCID 124 >> ` and the `BDC`
keyword that consumes those operands lives at the start of `contents[6]`. Parsing element 5
alone therefore discards the dangling operands (pikepdf reports this only as
`UserWarning: Unexpected end of stream`), and writing that parse back would delete them from
the document, leaving element 6's `BDC` with no operands.

`_correlate` captures that warning and refuses with `reason="part_boundary_truncated"` --
distinct from `"correlation_failed"` so a caller can tell "this document shape is not
editable by this engine" from "the correlation did not validate". Reattaching the truncated
tail was considered and explicitly not chosen: refusing matches this codebase's standing
fail-toward-safe posture (`classify_run`'s named refusals, `encoding_table`'s branch
refusals), and a wrong-but-silent rewrite is the exact failure mode this product exists to
avoid.

## D-04 / D-05 are NOT implemented in `rewrite_instructions`

D-04's runtime text-matrix guard and D-05's whole-run substitution trigger belong to
`rewrite_run` (layer 2), which decides WHAT instructions to install. `rewrite_instructions`
is told what to install and only performs the splice. Its own refusal vocabulary is exactly
three strings -- `"correlation_failed"`, `"part_boundary_truncated"` and
`"stale_run_index"`; `rewrite_run` adds `"text_matrix_shifted_after_edit"`,
`"operator_shared_by_multiple_runs"`, `"fit_refused"`, the substituted branch's own
`"substitution_required_but_no_target_provided"` and `"no_active_font_for_substitution"`,
and the non-substituted branch's own `"no_active_font_for_original_encoding"` and
`"character_has_no_code_in_original_encoding"`. EDIT-04's fixed-vocabulary posture: never
a generic failure, never document content in the reason. The one reason NOT from this fixed
set is a passed-through `FitResult.refusal_reason`, which `engine/fit.py` owns and which
carries measured point values only.

## What the D-04 guard does and does not catch -- MEASURED

D-04's invariant is "the text matrix following the edited run is unchanged", and
`_matrix_after_run` implements it as 03-06-PLAN.md specifies: the origin of the first glyph
following the run on the same part. That is a direct test of G2a's actual criterion --
*did anything after this run move* -- and it fires on a real fixture (proven by
`test_matrix_guard_fires_on_synthetic_shift`, a 57.88pt shift caught and refused).

It is silent, by construction, whenever the following text is ABSOLUTELY positioned: a
`Td`/`Tm` between the edited run and the next text-showing operator re-establishes the pen
position, so nothing downstream moves no matter what width was written. **Measured: over
page 0 of the first 20 corpus documents, only 9 of 2,106 correlatable editable runs (0.4%)
are followed by advance-dependent text; the other 99.6% -- including every editable run on
`irs_form_1040.pdf` page 0 -- pass this guard unconditionally.** So the guard is a genuine
backstop for the case where a width error propagates, and it is NOT a width check.

The stronger measure (the pen position after the run's own last glyph -- origin + advance,
which detects every width change) was considered and deliberately not used here: it would
refuse the Pitfall-1 consolidation this module is built around, since collapsing a run's N
individually-`Td`-positioned operators into one `Tj` legitimately changes where the pen
ends up. Width correctness is `engine/fit.py`'s job (and, at the corpus level, Gate G2a's);
recorded here rather than left implicit, per this project's standing "a check that reports
green while measuring the wrong thing" discipline.

## Refusal does NOT roll back (D-11)

`rewrite_run`'s D-04 guard runs AFTER the splice has already been applied to the in-memory
`pikepdf.Pdf` -- it cannot run before, because the thing it measures is where the following
glyph lands once the new bytes are in place. A `RewriteOutcome(ok=False)` from that guard
therefore leaves `pdf` MUTATED. No undo is attempted: reverting would mean either
re-serialising a saved copy of the part (state this module would have to own) or trusting
qpdf to reproduce byte-identical bytes, and D-11 already settles the question at the layer
above -- recipe application is all-or-nothing, so 03-07 discards the whole `pikepdf.Pdf`
handle on ANY refusal rather than calling `pdf.save()` on a partially-mutated one.
"""

from __future__ import annotations

import re
import tempfile
import warnings
from dataclasses import dataclass, replace
from pathlib import Path

import pikepdf
from fontTools.agl import UV2AGL

from engine.classify_run import RunVerdict, stream_bytes_and_resources
from engine.encoding_table import embedded_font_bytes, resolve_font
from engine.fit import FitResult, advance_pt_for_codes
from engine.fonts import (
    SubsetFont,
    reverse_encoding_map,
    run_needs_substitution,
    shape_cids,
    substitution_unicode_reason,
)
from engine.index import RunIndex
from engine.records import GlyphRecord, RunRecord
from engine.run_id import decode_run_id

TEXT_SHOWING_OPERATORS = frozenset({"Tj", "TJ", "'", '"'})

# What `pikepdf.parse_content_stream` actually returns an element of -- pikepdf folds a
# BI-ID-EI sequence into one virtual `ContentStreamInlineImage` instruction, which carries
# an `.operator` like any other and is therefore counted, skipped and re-serialised by
# exactly the same code paths below. pikepdf spells this union
# `pikepdf.models._content_stream.ContentStreamInstructions` but does not re-export it,
# and importing another package's private module is worse than naming the union here.
ParsedInstruction = pikepdf.ContentStreamInstruction | pikepdf.ContentStreamInlineImage

# pikepdf's own wording (lowercased for matching) when `parse_content_stream` reaches the
# end of the bytes mid-instruction and silently discards the dangling tokens. There is no
# structured signal for this -- pikepdf reports it only as a `UserWarning` -- so the text
# is matched, deliberately on the stable middle of the phrase rather than the whole string.
# See the "part-boundary truncation" section of the module docstring for why it is fatal.
#
# MEASURED REFUSAL RATE -- pinned here rather than left in a review transcript, per this
# project's "measure, then pin, state the basis" convention (cf. `SEAM_ADVANCE_DELTA_PT` in
# engine/fonts.py). Task review sampled 87 distinct `(part, xobj_path)` pairs across the
# first 12 corpus documents: 15/87 (17.2%) refuse with `"part_boundary_truncated"`. An
# independent spot-check over the same 12 documents (pages 0-1, 66 parts) found 8/66
# (12.1%) -- same order of magnitude, different sampled page set. So roughly 1 in 6
# content-stream parts in a representative sample cannot be edited at all under this
# module's current design, and that is a design ceiling, not a bug: lifting it means
# parsing adjacent parts together while keeping part-scoped run IDs, which is materially
# larger than this module. Re-measure if that changes.
_TRUNCATED_PARSE_WARNING = "unexpected end of stream"


@dataclass(frozen=True, slots=True)
class PageSnapshot:
    """Complete current classification, owned by one atomic recipe application.

    Only the caller that owns the PDF handle may assert freshness. No snapshot is
    accepted from the wire. A successful splice always produces a new snapshot.
    """

    page: int
    runs: tuple[tuple[RunRecord, RunVerdict], ...]


@dataclass(frozen=True, slots=True)
class RewriteOutcome:
    """The project's established verdict shape (frozen/slots, named reason). `reason` is
    populated only when `ok` is False, and is drawn from a fixed vocabulary -- it never
    carries document content."""

    ok: bool
    reason: str | None = None
    snapshot: PageSnapshot | None = None


def _instruction_has_text(instruction: ParsedInstruction) -> bool:
    """Count the same showing operators as the reader's nonempty-string gate.

    Empty strings and number-only TJ arrays produce no glyph operator offset.
    They retain their state/advance effects and stay in the instruction list;
    only the ordinal bridge omits them.
    """
    operator = str(instruction.operator)
    operands = instruction.operands
    if operator not in TEXT_SHOWING_OPERATORS or not operands:
        return False
    if operator == "TJ":
        array = operands[0]
        return isinstance(array, pikepdf.Array) and any(
            isinstance(item, pikepdf.String) and bool(bytes(item)) for item in array
        )
    return isinstance(operands[-1], pikepdf.String) and bool(bytes(operands[-1]))


def touched_instruction_indices(
    instructions: list[ParsedInstruction],
    run_operator_offsets: set[int],
    all_operator_offsets_sorted: list[int],
) -> list[int]:
    """Map a run's own operator byte offsets to `instructions`' own list indices, via
    ordinal position among text-showing operators -- NOT byte offset (pikepdf exposes
    none). Pure function, no I/O. Ported verbatim from 03-02's corpus-validated version;
    see the module docstring for why it is ported rather than imported.

    Both playa (which produced `operator_byte_offset`) and pikepdf (which produced
    `instructions`) walk the SAME bytes in the SAME order, so the Nth text-showing
    operator with a nonempty string counted by one is the Nth counted by the other,
    without either side ever exposing the other's addressing scheme. Glyphless showing
    instructions keep their original slots but do not consume these ordinals.
    """
    ordinal_of_offset = {off: i for i, off in enumerate(all_operator_offsets_sorted)}
    wanted_ordinals = {ordinal_of_offset[off] for off in run_operator_offsets}

    result: list[int] = []
    seen = 0
    for idx, instr in enumerate(instructions):
        if _instruction_has_text(instr):
            if seen in wanted_ordinals:
                result.append(idx)
            seen += 1
    return result


def _read_part_bytes(
    pdf: pikepdf.Pdf, page_index: int, part: int, xobj_path: tuple[int, ...]
) -> bytes:
    """The decoded bytes of the ONE content-stream part a run addresses. Thin wrapper --
    the page-vs-array vs. Form-XObject decision lives in `stream_bytes_and_resources`,
    which `engine.classify_run` and `engine.identity_rewrite` already share."""
    stream_bytes, _resources = stream_bytes_and_resources(pdf, page_index, part, xobj_path)
    return stream_bytes


def _write_part_bytes(
    pdf: pikepdf.Pdf,
    page_index: int,
    part: int,
    xobj_path: tuple[int, ...],
    new_bytes: bytes,
) -> None:
    """Write `new_bytes` back to exactly the part `_read_part_bytes` would read, changing
    nothing else about the object graph -- the Pitfall 3 fix (see module docstring).

    A Form XObject stream is rewritten in place, so its object number is untouched. A page
    whose `/Contents` is an array has ONLY `contents[part]` replaced, so the array's length
    and every other element's object number are untouched. A single-stream `/Contents`
    stays a single stream -- it never becomes an array.
    """
    if xobj_path:
        xobj = pdf.get_object((xobj_path[-1], 0))
        xobj.write(new_bytes)
        return

    page = pdf.pages[page_index]
    contents = page.obj.get("/Contents")
    if isinstance(contents, pikepdf.Array):
        contents[part] = pdf.make_stream(new_bytes)
    else:
        page.Contents = pdf.make_stream(new_bytes)


def _correlate(
    pdf: pikepdf.Pdf,
    page_index: int,
    run: RunRecord,
    all_page_runs: list[RunRecord],
) -> tuple[list[ParsedInstruction], list[int]] | RewriteOutcome:
    """`(instructions, touched_indices)` for `run`'s own content-stream part, or the
    `RewriteOutcome` refusal the caller should return unchanged.

    `all_operator_offsets_sorted` is built from every run on the page sharing the SAME
    `(part, xobj_path)` -- not only the editable ones. Pattern 1 requires the full ordinal
    sequence for that part, and Pitfall 2's interleaved operator that must not be corrupted
    can belong to a foreign run of any verdict.

    **`all_page_runs` MUST describe the part's CURRENT bytes.** The ordinal bridge is only
    valid while the run records and the parsed instructions describe the same content; see
    `rewrite_instructions`' own docstring for the caller-facing invariant, and the
    `"stale_run_index"` check below for what happens when they diverge.

    Classify-never-crash: a malformed part must never raise past this boundary, so the
    whole body is guarded and any unexpected failure becomes `"correlation_failed"`.
    """
    try:
        parts = decode_run_id(run.run_id)
        part = parts["part"]
        xobj_path = parts["xobj_path"]

        stream_bytes = _read_part_bytes(pdf, page_index, part, xobj_path)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            instructions = pikepdf.parse_content_stream(pdf.make_stream(stream_bytes))
        if any(_TRUNCATED_PARSE_WARNING in str(w.message).lower() for w in caught):
            return RewriteOutcome(ok=False, reason="part_boundary_truncated")

        run_operator_offsets = {g.operator_byte_offset for g in run.glyphs}

        all_offsets: set[int] = set()
        for other in all_page_runs:
            other_parts = decode_run_id(other.run_id)
            if (other_parts["part"], other_parts["xobj_path"]) == (part, xobj_path):
                all_offsets.update(g.operator_byte_offset for g in other.glyphs)

        # The ordinal bridge's own precondition, checked rather than assumed. Both sides
        # count text-showing operators over the same bytes, so the two counts must agree;
        # when they do not, ordinal N on one side is not ordinal N on the other and every
        # index this function could return would be confidently wrong. The in-range and
        # is-a-text-operator checks below cannot catch that -- a misaligned index still
        # lands on a perfectly valid `Tj`, just the wrong one.
        #
        # Use the reader's nonempty-string domain on both sides: numeric-only TJ
        # arrays and empty strings retain their state effects but supply no glyph
        # offset. Any remaining count mismatch still refuses; do not guess an ordinal
        # when the current instruction list and the caller's run records disagree.
        text_operator_count = sum(_instruction_has_text(instr) for instr in instructions)
        if text_operator_count != len(all_offsets):
            return RewriteOutcome(ok=False, reason="stale_run_index")

        touched = touched_instruction_indices(
            instructions, run_operator_offsets, sorted(all_offsets)
        )
        if not touched:
            return RewriteOutcome(ok=False, reason="correlation_failed")
        for i in touched:
            if not (0 <= i < len(instructions)):
                return RewriteOutcome(ok=False, reason="correlation_failed")
            if str(instructions[i].operator) not in TEXT_SHOWING_OPERATORS:
                return RewriteOutcome(ok=False, reason="correlation_failed")
        return instructions, touched
    except Exception:
        return RewriteOutcome(ok=False, reason="correlation_failed")


def rewrite_preflight_refusal(
    pdf: pikepdf.Pdf, page_index: int, run: RunRecord, all_page_runs: list[RunRecord]
) -> str | None:
    """Disclose detectable splice refusals before presenting a successful preview."""
    try:
        if _operator_shared_with_another_run(run, all_page_runs):
            return "operator_shared_by_multiple_runs"
    except Exception:
        return "correlation_failed"
    correlated = _correlate(pdf, page_index, run, all_page_runs)
    if isinstance(correlated, RewriteOutcome):
        return correlated.reason
    instructions, touched = correlated
    if any(str(instructions[i].operator) in ("'", '"') for i in touched):
        return "stateful_text_showing_unsupported"
    return None


def rewrite_instructions(
    pdf: pikepdf.Pdf,
    page_index: int,
    run: RunRecord,
    all_page_runs: list[RunRecord],
    new_instructions: list[pikepdf.ContentStreamInstruction],
) -> RewriteOutcome:
    """Install `new_instructions` in place of `run`'s own instructions, touching nothing
    else in the part and nothing at all outside it.

    ## CALLER INVARIANT: `all_page_runs` must reflect the part's CURRENT state

    `run` and `all_page_runs` are correlated to the content stream by ORDINAL position
    among text-showing operators, not by byte offset, so they are only valid against the
    bytes they were derived from. **A caller editing more than one run that shares a
    content-stream part MUST re-derive `all_page_runs` (re-walk and re-classify the
    edited document) after each edit to that part before calling again.** Reusing
    pre-edit run records against an already-edited part is undefined: this call
    consolidated N instructions into `len(new_instructions)`, so every other run on that
    part has had its true ordinal shift by the difference.

    That is not a theoretical hazard -- measured on `irs_form_1040.pdf` page 0, whose
    first `/Contents` part carries 32 runs: a second run correlated to instruction 250
    before the first edit and to instruction 782 after it, and 782 is a valid `Tj`
    belonging to a completely different run. The `"stale_run_index"` refusal exists to
    catch exactly that, so the second call refuses instead of silently overwriting the
    wrong text. Re-deriving between edits is the intended usage and proceeds normally.

    The splice: `new_instructions` takes the slot of the FIRST touched instruction, and
    every other touched instruction is deleted by list index. Index arithmetic, stated
    exactly, because an off-by-one here silently corrupts a real document -- `touched` is
    ascending and computed against the ORIGINAL list, so after the splice an original
    index `i > touched[0]` sits at `i + len(new_instructions) - 1`. Deleting
    `touched[1:]` highest-first at that shifted position means no earlier deletion can
    move a later one, and no untouched instruction is ever reached.

    Concretely, on 03-RESEARCH.md's own Pitfall 1 fixture (`irs_form_1040.pdf` page 0,
    the `:o1391` run): 62 touched instructions, one replacement instruction, so the part's
    instruction count drops by exactly 61.
    """
    correlated = _correlate(pdf, page_index, run, all_page_runs)
    if isinstance(correlated, RewriteOutcome):
        return correlated
    instructions, touched = correlated

    first = touched[0]
    surviving = instructions[:first] + new_instructions + instructions[first + 1 :]
    shift = len(new_instructions) - 1
    for i in sorted(touched[1:], reverse=True):
        del surviving[i + shift]

    # Per-instruction unparse, newline-joined -- `identity_rewrite.null_edit_rewrite`'s
    # own pattern, which is itself the pattern pikepdf's bundled `canvas.py` uses.
    new_bytes = b"\n".join(pikepdf.unparse_content_stream([i]) for i in surviving)

    parts = decode_run_id(run.run_id)
    _write_part_bytes(pdf, page_index, parts["part"], parts["xobj_path"], new_bytes)
    return RewriteOutcome(ok=True)


def _part_key(run: RunRecord) -> tuple[int, tuple[int, ...]]:
    """The `(part, xobj_path)` pair a run's ID addresses -- the identity of ONE
    content-stream part, and the scope every offset in this module is meaningful within."""
    parts = decode_run_id(run.run_id)
    return parts["part"], parts["xobj_path"]


def _stream_position(glyph: GlyphRecord) -> tuple[int, int, int]:
    """A glyph's total order within its own part: operator keyword offset first, then its
    position INSIDE that operator's operands (TJ array item, then byte within the string).
    Two glyphs shown by the same `TJ` share an `operator_byte_offset`, so the operator
    offset alone is not an order. `item_index_within_tj` is None for `Tj`/`'`/`"` (a single
    string, no array) -- sorted as -1 so the tuple stays homogeneous for comparison."""
    return (
        glyph.operator_byte_offset,
        -1 if glyph.item_index_within_tj is None else glyph.item_index_within_tj,
        glyph.byte_offset_within_string,
    )


def _part_glyphs_in_stream_order(
    runs: list[RunRecord], part_key: tuple[int, tuple[int, ...]]
) -> list[GlyphRecord]:
    return sorted(
        (glyph for run in runs if _part_key(run) == part_key for glyph in run.glyphs),
        key=_stream_position,
    )


def _current_page_snapshot(pdf: pikepdf.Pdf, page_index: int) -> PageSnapshot:
    """`page_index`'s runs as they stand in `pdf` RIGHT NOW, including any mutation this
    module has already applied in memory.

    Reuses `engine.index.RunIndex` -- the same walk/cluster/classify pass `_parse_page`
    already performs (03-CONTEXT.md names it "the natural re-walk hook for D-04's matrix
    assertion") -- rather than re-deriving a playa walk here. `RunIndex` opens a document by
    PATH and `pdf` is an in-memory handle whose edits are not on disk, so the current bytes
    are serialised to a scratch file first. Scratch-only writes, `tempfile`-issued and
    removed on exit, matching `engine.identity_rewrite`'s own convention (threat register
    T-02-01/T-02-06).

    MEASURED cost per call, pinned rather than assumed: 0.036s on
    `govdocs1_000_000011.pdf` page 0 (a sparse page), 1.20s on `irs_form_1040.pdf` page 0
    (220KB, 1,206 runs). `rewrite_run` calls this twice per edit, so a dense form page
    costs ~2.4s of guard per edit -- materially more than 03-CONTEXT.md's D-04 estimate
    ("Phase 2 measured page parse at ~9-15ms, so the re-walk is affordable per edit"),
    because this pass is the whole `_classify_one_page` pipeline (walk + font resolution +
    cluster + classify) plus a full `pdf.save`, not a bare parse. Still affordable for a
    CLI edit; if 03-07's recipe layer ever edits many runs on one dense page, the obvious
    lever is one shared re-walk per page per batch rather than two per edit.
    """
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "rewalk.pdf"
        pdf.save(path)
        with RunIndex(path) as index:
            return PageSnapshot(page_index, tuple(index.page(page_index).runs))


def _current_page_runs(pdf: pikepdf.Pdf, page_index: int) -> list[RunRecord]:
    return [run for run, _verdict in _current_page_snapshot(pdf, page_index).runs]


# D-04's comparison tolerance for a re-derived glyph origin, in PDF device-space units.
# Taken from `engine.identity_rewrite._FLOAT_EPSILON`, whose own comment explains why a
# hard `==` is wrong for re-derived floating-point position values, and confirmed to still
# be the right order of magnitude HERE by direct measurement rather than by inheritance:
# on this task's own positive test (`govdocs1_000_000011.pdf` page 0, the `:o487` run
# rewritten with its own original instruction) the following glyph's origin re-derives to a
# delta of exactly 0.0 in both x and y -- pikepdf parses content-stream numbers as
# arbitrary-precision Decimal and re-emits that same Decimal, so playa consumes bit-identical
# operands on both sides. Zero noise measured, so 1e-6 is NOT widened; it sits many orders of
# magnitude above anything observed while still catching a real shift -- the synthetic
# negative case (same run, operand doubled) measures a 57.88pt delta.
_POSITION_EPSILON = 1e-6


def _matrix_after_run(
    pdf: pikepdf.Pdf,
    page_index: int,
    run: RunRecord,
    all_page_runs: list[RunRecord],
) -> tuple[float, float] | None:
    """The `(x, y)` origin of the first glyph following `run` on `run`'s OWN part, as the
    page's CURRENT content places it -- D-04's observable proxy for "the text matrix
    immediately after the edited run". `None` means nothing follows the run on that part
    (it is the part's last content), so there is nothing to compare and the guard passes
    trivially.

    ## Why the following glyph is located by counting from the END of the part

    The obvious implementation -- "re-walk, find this run's own last glyph, take the next
    one" -- works before an edit and is meaningless after one. `rewrite_instructions`
    re-serialises the WHOLE part through `unparse_content_stream`, so every byte offset in
    the part changes, and `run`/`all_page_runs` still carry the PRE-edit offsets. Comparing
    a stale offset against fresh ones would select an essentially arbitrary glyph, and the
    guard would then compare two DIFFERENT glyphs' positions and refuse (or pass) at random.

    So the count of glyphs following the run on that part is used instead, and the same
    physical glyph is `tail_count` from the end of the part both before and after.
    `tail_count` is derived from `all_page_runs` (the caller's records, which describe the
    state the correlation was computed against); the coordinates come from the fresh walk.

    **The exact guarantee this rests on, stated narrowly (an earlier version of this
    docstring overstated it):** every instruction the splice touches lies between the run's
    first and last operator, so no instruction AFTER the run's last operator is touched --
    a foreign run's interleaved operator (Pitfall 2) sits inside the span, not after it, and
    survives. That makes the trailing glyph count invariant ONLY IF every glyph the splice
    destroys belongs to `run` itself. It does not, when a single text-showing operator backs
    more than one run: the splice deletes whole instructions, so a sibling run's glyphs
    inside a shared `TJ` die with the target's, and any of them sorting after the target's
    own last glyph were counted into `tail_count`. Sharing is common (measured: 30 of the
    text operators on `govdocs1_000_000009.pdf` page 0 part 5 back 2+ runs, one of them 36),
    so `rewrite_run` refuses it up front by name (`"operator_shared_by_multiple_runs"`)
    rather than letting this function compute a `tail_count` it cannot honour.

    A `tail_count` larger than the current part's own glyph count means the re-walk no
    longer describes a part with that much content -- `None` again, which (paired with a
    non-`None` "before") makes the guard REFUSE rather than pass.
    """
    last = max(_stream_position(glyph) for glyph in run.glyphs)
    if not any(_stream_position(glyph) > last
               for glyph in _part_glyphs_in_stream_order(all_page_runs, _part_key(run))):
        return None
    return _matrix_from_runs(run, all_page_runs, _current_page_runs(pdf, page_index))


def _matrix_from_runs(
    run: RunRecord, all_page_runs: list[RunRecord], current_runs: list[RunRecord]
) -> tuple[float, float] | None:
    """The same invariant tail-count lookup, using explicitly current records."""
    part_key = _part_key(run)
    last_position = max(_stream_position(glyph) for glyph in run.glyphs)
    recorded = _part_glyphs_in_stream_order(all_page_runs, part_key)
    tail_count = sum(1 for g in recorded if _stream_position(g) > last_position)
    if tail_count == 0:
        return None

    current = _part_glyphs_in_stream_order(current_runs, part_key)
    if tail_count > len(current):
        return None
    following = current[len(current) - tail_count]
    return following.x, following.y


def _positions_match(
    before: tuple[float, float] | None, after: tuple[float, float] | None
) -> bool:
    """Both `None` (nothing followed the run on either side) counts as a match; one `None`
    and one position does not."""
    if before is None or after is None:
        return before is None and after is None
    return (
        abs(before[0] - after[0]) <= _POSITION_EPSILON
        and abs(before[1] - after[1]) <= _POSITION_EPSILON
    )


# ISO 32000-1 9.3.4: `<number> Tz`, the horizontal-scaling text-state operator. Mirrors
# `engine.classify_run._TF_RE`'s idiom for the identical backward-scan question ("which
# value was in force at this byte offset"), with a stricter number pattern so every match
# is `float()`-able. Same known exposure as that regex, and inherited deliberately rather
# than solved twice: a raw byte scan cannot tell an operator from the same text inside a
# literal string, so `(90 Tz) Tj` would false-positive. A real fix is a tokenizer, which
# `_find_active_font_name` already declined to build for the more load-bearing `Tf` case.
_TZ_RE = re.compile(rb"([+-]?(?:\d+\.?\d*|\.\d+))\s+Tz\b")

# ISO 32000-1 Table 105: the initial value of the horizontal scaling text-state parameter,
# expressed in percent.
DEFAULT_HORIZONTAL_SCALE = 100.0


def _active_horizontal_scale(stream_bytes: bytes, byte_offset: int) -> float:
    """The `Tz` value in force at `byte_offset`: the operand of the LAST `Tz` at or before
    it, or the spec default if none precedes it.

    `engine/fit.py` states outright that it cannot answer this ("`original_scale_to_restore`
    is always the spec default (100.0) here because this module has no content-stream
    context to look one up") and assigns "finding/restoring any actual preceding `Tz`" to
    this module. This is that lookup. It matters twice over: restoring 100 into a text
    object that was at 87 renders everything after the edit ~15% wider, and it is not rare
    -- 851 of 941 `Tz` operators across the first 20 corpus documents (pages 0-2) set a
    non-100 value.
    """
    scale = DEFAULT_HORIZONTAL_SCALE
    for match in _TZ_RE.finditer(stream_bytes):
        if match.start() > byte_offset:
            break
        scale = float(match.group(1))
    return scale


def _bracket_for_fit(
    fit_result: FitResult,
    replacement: pikepdf.ContentStreamInstruction,
    active_scale: float,
) -> list[pikepdf.ContentStreamInstruction]:
    """03-RESEARCH.md Pattern 3's pseudocode, exactly: the `tz` rung emits the condensed
    scale immediately before the replacement and the ORIGINAL scale immediately after it, as
    plain explicit operators. Never `q`/`Q` -- `Tz` is a text-state parameter that persists
    past `BT` (D-02), and whether `q`/`Q` inside a text object restores text state at all is
    a documented spec ambiguity (pdf-association/pdf-issues#368). Every other rung emits the
    replacement alone.

    ## Both emitted values are rebased onto `active_scale`, the scale actually in force

    `Tz`'s operand is an ABSOLUTE percentage, but `fit_result.condensed_scale` is a RATIO:
    `fit_run` computes it as `original_advance_pt / shaped * 100`, and both of those
    advances come from `/Widths`-and-`hmtx` metrics with no horizontal scaling applied at
    all. Horizontal scaling multiplies every glyph displacement equally (ISO 32000-1 9.4.4:
    `tx = (w0 * Tfs + Tc + Tw) * Th`), so it cancels out of that ratio -- which is why
    fit.py's number is exactly the RELATIVE squeeze needed, and why `fit.py` needs no fix
    for this: to occupy a run rendered at `Th`, the replacement must render at
    `Th * condensed_scale / 100`. The 90% floor is likewise correctly a relative test --
    it asks how deformed the replacement looks NEXT TO the text around it, which is the
    only comparison a reader can make.

    `fit_result.original_scale_to_restore` is deliberately NOT read: it is fit.py's own
    documented placeholder (always 100.0), superseded by `active_scale`, which is the
    content stream's actual answer.

    A `"tz"` `FitResult` carrying no `condensed_scale` is malformed and falls through to the
    unbracketed form deliberately: that emits the replacement at its natural (uncondensed)
    width, which is exactly the case D-04's guard catches and refuses by name -- a named
    refusal, never a silently wrong width.
    """
    condensed = fit_result.condensed_scale
    if fit_result.strategy == "tz" and condensed is not None:
        return [
            pikepdf.ContentStreamInstruction(
                [condensed * active_scale / 100.0], pikepdf.Operator("Tz")
            ),
            replacement,
            pikepdf.ContentStreamInstruction([active_scale], pikepdf.Operator("Tz")),
        ]
    return [replacement]


def _operator_shared_with_another_run(
    run: RunRecord, all_page_runs: list[RunRecord]
) -> bool:
    """Does any OTHER run on the same part show glyphs through one of `run`'s OWN
    text-showing operators?

    The splice deletes whole INSTRUCTIONS, so a shared operator cannot be rewritten for one
    run without destroying the other's glyphs too -- and `_correlate`'s count check cannot
    see it, because it compares against a deduplicated offset SET, which one shared operator
    enters exactly once no matter how many runs stand behind it. `engine/clusterer.py`
    breaks runs on gap, font, size, colour, visibility and per-glyph verdict, none of which
    respect operator boundaries, so one `TJ` legitimately backing several sibling runs is
    ordinary rather than exotic (measured: 30 shared text operators on
    `govdocs1_000_000009.pdf` page 0 part 5, one of them backing 36 runs).

    Note what this does NOT match: a foreign run's own separate operator sitting between
    this run's first and last (Pitfall 2). That is supported and must keep working -- the
    test here is operator IDENTITY, not span overlap.
    """
    part_key = _part_key(run)
    own_operators = {glyph.operator_byte_offset for glyph in run.glyphs}
    for other in all_page_runs:
        if other is run or _part_key(other) != part_key:
            continue
        if own_operators & {glyph.operator_byte_offset for glyph in other.glyphs}:
            return True
    return False


# ISO 32000-1 Table 105/9.3: `/Name size Tf`, with the SIZE captured as well as the name.
#
# The pattern is `engine.classify_run._TF_RE`'s, character for character, plus one capture
# group -- and that exactness is load-bearing, not cosmetic (task-3 review finding). This
# module must select the SAME `Tf` occurrence `classify_run` did, because `classify_run`
# picked the font the run was CLASSIFIED against and this module builds the `Tf` bracket
# that restores it. Two regexes that merely usually agree are not enough: an earlier
# revision tightened the number class to `[+-]?(?:\d+\.?\d*|\.\d+)` so every match would be
# `float()`-able, and thereby made the two scans diverge on a malformed operand --
# `/F1 12 Tf ... /F2 1.2.3 Tf ... (x) Tj` classifies against `/F2` but would have bracketed
# and restored `/F1` at size 12, leaving a confidently WRONG font in force for every later
# run in the part. D-04's guard cannot catch that: it compares position, not font identity.
#
# So the looser class is kept, `float()` is allowed to fail, and a failure becomes a NAMED
# REFUSAL below rather than a silent second-choice match. (Corpus sweep at review time:
# 341,739 `Tf` matches, zero divergent cases -- this is a latent trap being closed, not an
# observed bug.) Same known exposure as `_TF_RE` and `_TZ_RE`, inherited deliberately
# rather than solved a third time: a raw byte scan cannot tell an operator from the same
# text inside a literal string.
_TF_NAME_SIZE_RE = re.compile(rb"/([^\s/\[\](){}<>%]+)\s+([+-]?[0-9.]+)\s+Tf\b")


def _active_font_operands(
    stream_bytes: bytes, byte_offset: int
) -> tuple[bytes, float] | None:
    """The `(resource name, size)` operands of the LAST `Tf` at or before `byte_offset` --
    `engine.classify_run._find_active_font_name`'s own scan, over the same pattern,
    returning both operands instead of one.

    `None` means this module must not proceed: either no `Tf` precedes the offset at all,
    or the one that does carries an operand that is `[0-9.]`-shaped but not a number
    (`1.2.3`). Never a fallback to an earlier, cleaner `Tf` -- that would be the divergence
    the pattern comment above exists to prevent.
    """
    found: re.Match[bytes] | None = None
    for match in _TF_NAME_SIZE_RE.finditer(stream_bytes):
        if match.start() > byte_offset:
            break
        found = match
    if found is None:
        return None
    try:
        return found.group(1), float(found.group(2))
    except ValueError:
        return None


def _run_font_object(
    pdf: pikepdf.Pdf, page_index: int, run: RunRecord
) -> pikepdf.Object | None:
    """The `/Resources /Font` entry for whichever font is active at `run`'s first operator
    -- `engine.classify_run._resolve_font_for_glyph`'s own lookup, at run granularity
    (D-01 breaks a run on font change, so a run has exactly one active font)."""
    part, xobj_path = _part_key(run)
    stream_bytes, resources = stream_bytes_and_resources(pdf, page_index, part, xobj_path)
    if resources is None:
        return None
    active = _active_font_operands(
        stream_bytes, min(glyph.operator_byte_offset for glyph in run.glyphs)
    )
    if active is None:
        return None
    fonts = resources.get("/Font")
    if fonts is None:
        return None
    font: pikepdf.Object | None = fonts.get("/" + active[0].decode("latin-1"))
    return font


def _substitution_triggered(
    pdf: pikepdf.Pdf,
    page_index: int,
    run: RunRecord,
    all_page_runs: list[RunRecord],
    new_text: str,
) -> bool:
    """D-05 / 03-RESEARCH.md Pattern 4's edit-time substitution trigger: does `new_text`
    contain a character this run's OWN font cannot show?

    This is a genuinely NEW question, not a re-reading of Phase 2's verdict. Phase 2's
    `editable_substitution` state is produced ONLY by an unembedded simple Type1 font
    (`_resolve_type1`'s `T1-c`/`T1-d`), and it was resolved at classification time, before
    any replacement text existed. A run can be `editable_original` -- its font embedded and
    fully usable for the text already on the page -- and still need the bundled substitute
    the moment the user proposes a character the embedded subset has no glyph for. That is
    D-05/FONT-06's actual headline scenario, and answering it needs the proposed text,
    which only an edit has.

    The answer itself is `engine.fonts.run_needs_substitution`'s (already built and tested,
    including its Type0/CID short-circuit); this function only resolves the three inputs it
    needs from the content stream and the object graph.

    `rewrite_run`'s own `or` short-circuits this away for a run Phase 2 ALREADY routed to
    substitution: such a run has no usable embedded program to check a character against in
    the first place, so asking the question would be meaningless as well as wasted work.

    Note what a `True` here does NOT require: an embedded program. `glyph_presence` treats
    an absent or unparseable program as "cannot confirm this glyph" and downgrades to
    substitution, so a non-embedded simple font (a bare `/ArialMT`, say) routes here for
    ANY replacement text. That is the intended outcome rather than an over-trigger -- D-07
    picked Liberation precisely because it is metric-compatible with Arial/Times/Courier,
    so substituting one is the seamless case, not the lossy one.

    Fails toward the ORIGINAL branch (`False`) on any resolution failure, deliberately: a
    font this cannot resolve is one whose encoding this module cannot re-encode into
    either, so the non-substituted resolver refuses it BY NAME rather than this function
    silently promoting an unresolvable run into a substitution it was never asked for.
    """
    try:
        font = _run_font_object(pdf, page_index, run)
        if font is None:
            return False
        font_verdict = resolve_font(font)
        program = embedded_font_bytes(font.get("/FontDescriptor"))
        return run_needs_substitution(font, font_verdict, program, new_text).substitute
    except Exception:
        return False


def _trailing_fit_for_written_font(
    fit: FitResult, font: pikepdf.Object, codes: list[int], font_size: float
) -> FitResult:
    """Preserve pen advance using the widths the PDF viewer will actually read.

    Font-program metrics and serialized /Widths or /W can differ by rounding.
    A terminal adjustment must cancel that difference too, particularly when the
    next showing operator relies on this run's pen position. Do not relax the guard.
    """
    if fit.strategy != "trailing_kern" or not fit.kerns:
        return fit
    actual = advance_pt_for_codes(font, codes, font_size)
    return replace(fit, replacement_shaped_advance_pt=actual, delta_pt=0.0,
                   kerns=[(actual - fit.original_advance_pt) / font_size * 1000.0])


def _show_instruction(
    units: tuple[tuple[bytes, str], ...], fit_result: FitResult
) -> pikepdf.ContentStreamInstruction:
    """The replacement text-showing instruction: a bare `Tj` when the fit needed no kern
    correction, otherwise the `TJ` array that CARRIES that correction into the document.

    `units` is `(encoded bytes, source character)` per glyph, which is the ONE thing the
    substituted and non-substituted branches disagree about: 2 big-endian CID bytes from
    `shape_cids` (`/Identity-H`, where code == CID == GID) on one side, one `/Encoding`
    byte from the run's own font on the other. Everything below -- which is the whole of
    the kern algorithm -- is identical for both, so it lives here once rather than in two
    copies that could drift apart on the edge cases the tests pin.

    ## Why this is a TJ at all (the gap this closes)

    `engine/fit.py`'s `trailing_kern` and `inter_word_kern` rungs do not merely measure a
    delta -- they compute the exact TJ numbers that cancel it, and a `FitResult` reporting
    `strategy="trailing_kern"` is asserting that the replacement occupies the original run's
    width ONCE THOSE KERNS ARE APPLIED. Emitting a bare `Tj` would silently drop them and
    render the replacement at its unfitted width while the ladder reported a clean fit --
    a confident wrong result, which is the failure mode this engine exists to avoid. Until
    this function, nothing anywhere in `engine/` consumed `FitResult.kerns`.

    ## Shapes, one per rung

    * `tz` / `refused` -- `kerns` is empty by `fit_run`'s own construction: a plain `Tj`.
    * `trailing_kern` -- exactly one kern, placed AFTER the whole run's single string, so
      it displaces whatever comes next rather than anything inside the run. That is the same
      "affects what follows" model `_matrix_after_run` measures the guard against.
    * `inter_word_kern` -- one kern per inter-word gap. The array is segmented at each SPACE
      GLYPH, with the space's own bytes closing the segment BEFORE the kern, so the
      correction lands in the gap the space renders. `fit_run` sizes its list from
      `replacement_text.count(" ")`, and harfbuzz emits exactly one glyph per space
      character (a ligature never swallows one), so the walk consumes exactly that many --
      including for leading, trailing and consecutive spaces, whose segments are legally
      empty rather than special cases.

    An unexpected `(strategy, kerns)` combination `fit_run` cannot currently produce is
    handled by the same segmented walk and, if any kern is still unconsumed at the end,
    appended rather than dropped: the one thing this function must never do is report a
    fitted width while discarding the number that makes it true.

    THREAT T-03-06-01 (content-stream injection): every operand below is built with
    `pikepdf.String`/`pikepdf.Array` and later serialised by `unparse_content_stream`, so
    escaping is pikepdf's job and replacement text can never break out of its string
    literal. There is deliberately no byte formatting anywhere on this path.
    """
    all_bytes = b"".join(encoded for encoded, _source_char in units)
    kerns = list(fit_result.kerns)
    if not kerns:
        return pikepdf.ContentStreamInstruction(
            [pikepdf.String(all_bytes)], pikepdf.Operator("Tj")
        )
    if fit_result.strategy == "trailing_kern":
        return pikepdf.ContentStreamInstruction(
            [pikepdf.Array([pikepdf.String(all_bytes), *kerns])],
            pikepdf.Operator("TJ"),
        )

    elements: list[pikepdf.Object | float] = []
    segment = b""
    used = 0
    for encoded, source_char in units:
        segment += encoded
        if source_char == " " and used < len(kerns):
            elements.append(pikepdf.String(segment))
            elements.append(kerns[used])
            used += 1
            segment = b""
    elements.append(pikepdf.String(segment))
    elements.extend(kerns[used:])
    return pikepdf.ContentStreamInstruction(
        [pikepdf.Array(elements)], pikepdf.Operator("TJ")
    )


def _substitution_resource_key(
    resources: pikepdf.Object, font_obj: pikepdf.Object, subset: SubsetFont
) -> str:
    """The `/Resources /Font` key naming `font_obj` in this part, adding one only if the
    dict does not already reference that SAME object.

    Identity is `objgen`, the stable indirect-object identity (the same choice
    `engine.classify_run._resolve_font_for_glyph` already makes for its own cache key, and
    for the same reason: `pikepdf.Object` wrappers are ephemeral and `id()` gets reused).
    A direct (non-indirect) value carries `objgen == (0, 0)`, which every other direct value
    also carries, so it is never treated as a match -- `embed_type0_font` always returns an
    indirect object, so the guard costs nothing and removes a false-match class entirely.

    D-13's per-document invariant is 03-07's to maintain (one subset per family per
    document); this function only guarantees the per-PART consequence of it -- however many
    runs on a part substitute through one font object, the part's resource dict gains at
    most one entry. `f"/F{subset.tag}"` is collision-safe by FONT-05's own construction: the
    tag is a fresh 6-uppercase-letter digest of the exact glyph union.
    """
    fonts = resources.get("/Font")
    if fonts is None:
        resources["/Font"] = pikepdf.Dictionary()
        fonts = resources["/Font"]

    objgen = font_obj.objgen
    if objgen != (0, 0):
        for key, value in fonts.items():
            if value.objgen == objgen:
                return str(key)

    resource_key = f"/F{subset.tag}"
    # The `objgen` scan above already returned for every key naming THIS object, so any
    # surviving collision names a DIFFERENT one -- structurally near-impossible against
    # real producers (`/F1`, `/TT0`, `/T1_0`), and a silent clobber of another font's
    # resource if it ever happened.
    while resource_key in fonts:
        resource_key += "A"
    fonts[resource_key] = font_obj
    return resource_key


def _resolve_substituted_operand(
    pdf: pikepdf.Pdf,
    page_index: int,
    run: RunRecord,
    all_page_runs: list[RunRecord],
    new_text: str,
    substitution_target: tuple[SubsetFont, pikepdf.Object],
    fit_result: FitResult,
) -> (
    tuple[pikepdf.ContentStreamInstruction, list[pikepdf.ContentStreamInstruction]]
    | RewriteOutcome
):
    """FONT-06/D-05: the whole run re-encoded through the already-embedded bundled font --
    the replacement `Tj`/`TJ` plus the `[tf_new, tf_restore]` pair that brackets it.

    `shape_cids` is called ONCE, over the WHOLE `new_text`, and its output is the operand
    in its entirety. FONT-06's structural guarantee falls out of that shape rather than
    being checked afterwards: there is no per-character branch here that could emit one
    glyph in the original encoding and the next as a CID, so a partial-run seam is not
    something this code declines to do -- it is something it has no way to express.

    D-13 is likewise enforced by the SIGNATURE, exactly as `engine.fonts
    .build_cid_font_descriptor` already establishes its own invariant: this function takes
    an ALREADY-BUILT `(SubsetFont, font object)` pair and never calls
    `subset_font_for_family`/`embed_type0_font` itself, so it cannot subset or embed twice
    even by accident. Collecting the document-wide glyph union and embedding one subset per
    family is 03-07's recipe-level concern.

    `Tf` is bracketed and restored the identical way `_bracket_for_fit` already brackets
    `Tz`, for the identical reason: `Tf` is a text-state parameter that persists past `BT`
    (D-02), so leaving the substituted run's font in force would silently re-render every
    later run in the text object -- and in the bundled face's CID codespace at that, where
    the original single-byte codes decode to entirely different glyphs. Restored to the
    run's own previously-active resource NAME and SIZE, both read back from the part's
    bytes.

    Returns `RewriteOutcome(ok=False, reason="no_active_font_for_substitution")` -- never
    raises, never guesses -- when the part carries no `/Resources`, or when
    `_active_font_operands` cannot answer with the SAME `Tf` `classify_run` classified this
    run against. Both are structurally unreachable for a run that reached an editable
    verdict (`classify_run._resolve_font_for_glyph` refuses `NO-TF` and an unresolvable
    resource name first), so this is a backstop rather than an expected path -- but it must
    be a NAMED refusal all the same: `rewrite_run`'s pre-mutation `try` block has already
    closed by the time this is called, so an exception here would escape as an unhandled
    crash and violate EDIT-04's "never a generic failure" posture. The mirror of
    `_resolve_non_substituted_operand`'s own `... | RewriteOutcome` shape.
    """
    subset, font_obj = substitution_target
    unicode_reason = substitution_unicode_reason(subset.family, subset.variant, (new_text,))
    if unicode_reason is not None:
        return RewriteOutcome(ok=False, reason=unicode_reason)
    part, xobj_path = _part_key(run)
    stream_bytes, resources = stream_bytes_and_resources(pdf, page_index, part, xobj_path)
    active = (
        None
        if resources is None
        else _active_font_operands(
            stream_bytes, min(glyph.operator_byte_offset for glyph in run.glyphs)
        )
    )
    if resources is None or active is None:
        return RewriteOutcome(ok=False, reason="no_active_font_for_substitution")
    original_name, font_size = active

    # Validate the active source font before shaping or installing resources.
    # THREAT T-03-06-01: operands are pikepdf.String-built inside _show_instruction.
    try:
        units = tuple((cid.to_bytes(2, "big"), source_char)
                      for cid, source_char in shape_cids(subset, new_text))
    except ValueError as exc:
        if str(exc) in {"multi_character_shaping_unsupported", "ambiguous_glyph_unicode_mapping"}:
            return RewriteOutcome(ok=False, reason=str(exc))
        raise
    fitted = _trailing_fit_for_written_font(
        fit_result, font_obj, [int.from_bytes(code, "big") for code, _ in units], font_size)
    replacement = _show_instruction(units, fitted)
    resource_key = _substitution_resource_key(resources, font_obj, subset)
    tf_new = pikepdf.ContentStreamInstruction(
        [pikepdf.Name(resource_key), font_size], pikepdf.Operator("Tf")
    )
    tf_restore = pikepdf.ContentStreamInstruction(
        [pikepdf.Name("/" + original_name.decode("latin-1")), font_size],
        pikepdf.Operator("Tf"),
    )
    return replacement, [tf_new, tf_restore]


def _original_code_map(font: pikepdf.Object, new_text: str) -> dict[str, int] | None:
    """Each DISTINCT character of `new_text` -> its single-byte code in `font`'s OWN
    `/Encoding`, or `None` if any character has none.

    Two steps, exactly `engine.fonts.run_needs_substitution`'s own checks 1a and 1b and in
    the same order, because this function must agree with it character for character: a
    character it says needs no substitution must be one this can encode. Unicode -> AGL
    glyph NAME (`UV2AGL`), then name -> code (`reverse_encoding_map`, which is keyed by
    glyph name). Going straight from character to code is not possible -- a font's
    `/Encoding` maps codes to glyph NAMES, and `/Differences` routinely puts a glyph at a
    code its Unicode value has nothing to do with.

    Simple fonts only. Structurally guaranteed by the caller chain rather than re-checked
    here: `run_needs_substitution` returns `substitute=True` UNCONDITIONALLY for any font
    whose verdict branch starts `"C-"` (every Type0/CIDFontType2 branch), before it ever
    builds a reverse map, so `rewrite_run` routes every CID-keyed run to the substituted
    branch and this function is unreachable for one. Pinned executably by
    `test_non_substituted_operand_is_unreachable_for_type0_fonts`, at the dispatch level.
    """
    code_map: dict[str, int] = {}
    reverse = reverse_encoding_map(font)
    for ch in new_text:
        if ch in code_map:
            continue
        glyph_name = UV2AGL.get(ord(ch))
        code = None if glyph_name is None else reverse.get(glyph_name)
        if code is None:
            return None
        code_map[ch] = code
    return code_map


def _resolve_non_substituted_operand(
    pdf: pikepdf.Pdf,
    page_index: int,
    run: RunRecord,
    all_page_runs: list[RunRecord],
    new_text: str,
    fit_result: FitResult,
) -> pikepdf.ContentStreamInstruction | RewriteOutcome:
    """`new_text` encoded through the run's OWN original font -- no `Tf` change, no
    `/Resources` mutation, no `shape_cids` call, nothing touched outside the one
    instruction this returns.

    The mirror of `_resolve_substituted_operand` in every structural respect, and
    deliberately so: the same backward-`Tf`-scan font lookup (`_run_font_object`, which is
    `engine.classify_run._resolve_font_for_glyph`'s own pattern, so this path re-encodes
    into the SAME font object the run was classified against), the same
    `... | RewriteOutcome` return shape, and the same rule that every failure is a NAMED
    refusal rather than a raise -- `rewrite_run`'s pre-mutation `try` block has already
    closed by the time this runs.

    Two named refusals, kept distinct because they mean different things to a caller:
    `"no_active_font_for_original_encoding"` (the part carries no `/Resources`, or the
    active `Tf` cannot be resolved -- the same backstop condition the substituted branch
    calls `"no_active_font_for_substitution"`), and
    `"character_has_no_code_in_original_encoding"` (the font resolved, but a character of
    `new_text` has no code in its encoding). The second is DEFENSIVE: Task 3's Pattern-4
    wiring routes exactly those characters to the substituted branch before this function
    is reached, so it should be unreachable in normal operation -- and classify-never-crash
    discipline says an unreachable `KeyError` is still a crash.

    `fit_result` is a parameter the plan's original signature did not list; it is required
    by the 2026-08-24 amendment, which makes this path emit the `TJ` array carrying
    `fit_result.kerns` exactly as the substituted path does. Added the same way Task 3
    added it to `_resolve_substituted_operand`.
    """
    font = _run_font_object(pdf, page_index, run)
    if font is None:
        return RewriteOutcome(ok=False, reason="no_active_font_for_original_encoding")

    code_map = _original_code_map(font, new_text)
    if code_map is None:
        return RewriteOutcome(
            ok=False, reason="character_has_no_code_in_original_encoding"
        )

    # THREAT T-03-06-01: the operand is `pikepdf.String`-built inside `_show_instruction`,
    # from single-byte codes this module looked up -- never from `new_text`'s own bytes and
    # never by formatting. Hostile PDF syntax in the replacement text (`(`, `)`, `\`) is
    # therefore escaped by pikepdf on unparse and cannot break out of the string literal.
    part, xobj_path = _part_key(run)
    stream_bytes, _resources = stream_bytes_and_resources(pdf, page_index, part, xobj_path)
    active = _active_font_operands(stream_bytes, min(g.operator_byte_offset for g in run.glyphs))
    if active is None:
        return RewriteOutcome(ok=False, reason="no_active_font_for_original_encoding")
    fitted = _trailing_fit_for_written_font(
        fit_result, font, [code_map[ch] for ch in new_text], active[1])
    return _show_instruction(tuple((bytes([code_map[ch]]), ch) for ch in new_text), fitted)


def rewrite_run(
    pdf: pikepdf.Pdf,
    page_index: int,
    run: RunRecord,
    verdict: RunVerdict,
    all_page_runs: list[RunRecord],
    new_text: str,
    fit_result: FitResult,
    substitution_target: tuple[SubsetFont, pikepdf.Object] | None = None,
    color: tuple[float, ...] | None = None,
    force_substitution: bool = False,
    current_snapshot: PageSnapshot | None = None,
) -> RewriteOutcome:
    """EDIT-02/EDIT-03/EDIT-04: the module's public entry point. Builds the replacement
    instruction for `run` (substituted or not), brackets it per the fit ladder's chosen
    rung, splices it in, and then re-walks the page to check D-04's post-run text-matrix
    invariant -- refusing by name rather than writing a confident wrong result.

    `rewrite_instructions`' CALLER INVARIANT applies unchanged: `all_page_runs` must
    describe the part's CURRENT bytes, so an orchestrator editing two runs on one part
    re-derives it between edits.

    **A refusal here does not undo the mutation** -- see the module docstring's D-11 note.
    """
    # `engine.fit.fit_run` spells the refusing rung `"refused"` (and sets `refused=True`);
    # 03-06-PLAN.md's prose calls it `"refuse"`. Both are accepted rather than picking one
    # and silently editing on the other spelling, which would apply a fit the ladder
    # explicitly declined to make. The reason is passed through verbatim: it is fit.py's
    # own measured-point-values string, content-free by construction.
    if fit_result.refused or fit_result.strategy in ("refuse", "refused"):
        # `or "fit_refused"`: a FitResult may carry `refused=True` with no reason set, and
        # `RewriteOutcome(ok=False, reason=None)` is the unnamed failure EDIT-04 forbids.
        return RewriteOutcome(ok=False, reason=fit_result.refusal_reason or "fit_refused")

    stateful_reason = rewrite_preflight_refusal(pdf, page_index, run, all_page_runs)
    if stateful_reason is not None:
        return RewriteOutcome(ok=False, reason=stateful_reason)

    # BEFORE any mutation. A page whose current content cannot be walked, or a run whose ID
    # cannot be decoded, is exactly "the records and the content stream cannot be put in
    # correspondence" -- `"correlation_failed"`, the same reason `_correlate` gives, rather
    # than a new name for the same condition or a silent skip of the guard.
    try:
        if _operator_shared_with_another_run(run, all_page_runs):
            return RewriteOutcome(ok=False, reason="operator_shared_by_multiple_runs")
        # Only the `tz` rung needs the part's bytes; every other rung emits no Tz at all,
        # so the read is skipped rather than paid for on every edit.
        active_scale = DEFAULT_HORIZONTAL_SCALE
        if fit_result.strategy == "tz":
            part, xobj_path = _part_key(run)
            active_scale = _active_horizontal_scale(
                _read_part_bytes(pdf, page_index, part, xobj_path),
                min(glyph.operator_byte_offset for glyph in run.glyphs),
            )
        if current_snapshot is not None:
            if current_snapshot.page != page_index:
                return RewriteOutcome(ok=False, reason="correlation_failed")
            matrix_before = _matrix_from_runs(
                run, all_page_runs, [r for r, _ in current_snapshot.runs])
        else:
            matrix_before = _matrix_after_run(pdf, page_index, run, all_page_runs)
    except Exception:
        return RewriteOutcome(ok=False, reason="correlation_failed")

    new_instructions: list[pikepdf.ContentStreamInstruction]
    if force_substitution or verdict.state == "editable_substitution" or _substitution_triggered(
        pdf, page_index, run, all_page_runs, new_text
    ):
        # Per D-13 this module never builds a substitution target itself -- it only ever
        # consumes one 03-07 already built, so having none is a named refusal, not a cue
        # to subset a font here.
        if substitution_target is None:
            return RewriteOutcome(
                ok=False, reason="substitution_required_but_no_target_provided"
            )
        substituted = _resolve_substituted_operand(
            pdf,
            page_index,
            run,
            all_page_runs,
            new_text,
            substitution_target,
            fit_result,
        )
        if isinstance(substituted, RewriteOutcome):
            return substituted
        replacement, (tf_new, tf_restore) = substituted
        # Tf wraps OUTSIDE the Tz bracket -- both are text-state parameters with the same
        # persistence hazard, and the font must be in force for the condensed showing.
        new_instructions = (
            [tf_new]
            + _bracket_for_fit(fit_result, replacement, active_scale)
            + [tf_restore]
        )
    else:
        resolved = _resolve_non_substituted_operand(
            pdf, page_index, run, all_page_runs, new_text, fit_result
        )
        if isinstance(resolved, RewriteOutcome):
            return resolved
        new_instructions = _bracket_for_fit(fit_result, resolved, active_scale)

    if color is not None:
        # q/Q preserves the complete graphics state, including inherited DeviceGray,
        # DeviceCMYK and pattern colors, but does NOT restore the text matrix. The
        # fitted text advance therefore survives, while following glyphs retain their
        # original color. Set both painting channels: Tr=1 is stroke-only and Tr=2
        # fills and strokes, so rg alone would report success without recoloring the
        # visible outline. Explicit Tf/Tz brackets remain valid inside this pair.
        new_instructions = [
            pikepdf.ContentStreamInstruction([], pikepdf.Operator("q")),
            pikepdf.ContentStreamInstruction(list(color), pikepdf.Operator("rg")),
            pikepdf.ContentStreamInstruction(list(color), pikepdf.Operator("RG")),
            *new_instructions,
            pikepdf.ContentStreamInstruction([], pikepdf.Operator("Q")),
        ]
    outcome = rewrite_instructions(pdf, page_index, run, all_page_runs, new_instructions)
    if not outcome.ok:
        return outcome

    try:
        snapshot = None
        if current_snapshot is not None:
            snapshot = _current_page_snapshot(pdf, page_index)
            matrix_after = _matrix_from_runs(
                run, all_page_runs, [r for r, _ in snapshot.runs])
        else:
            matrix_after = _matrix_after_run(pdf, page_index, run, all_page_runs)
    except Exception:
        return RewriteOutcome(ok=False, reason="correlation_failed")
    if not _positions_match(matrix_before, matrix_after):
        return RewriteOutcome(ok=False, reason="text_matrix_shifted_after_edit")
    return RewriteOutcome(ok=True, snapshot=snapshot)


__all__ = [
    "RewriteOutcome",
    "rewrite_instructions",
    "rewrite_run",
    "touched_instruction_indices",
]
