"""Tests for engine/rewrite.py (plan 03-06 Tasks 1-3: the splice primitive, the
`rewrite_run` entry point's Tz bracket / D-04 matrix guard / refusal vocabulary, and the
substituted branch's own operand path).

The four named cases from task-1-brief.md's `<behavior>` block, three of which are
VALIDATION.md-pinned regression names:

1. `test_multi_operator_run_consolidates_to_one_instruction` -- `irs_form_1040.pdf`
   page 0, the `:o1391` run: RESEARCH.md Pitfall 1's own measured 62-operator case.
2. `test_foreign_interleaved_operator_survives_unedited` -- `irs_form_w4.pdf` pages 0
   AND 4: RESEARCH.md Pitfall 2's own non-contiguous case, where another run's operator
   sits strictly between the target run's first and last. Page 4 proves survival; page 0's
   only Pitfall-2 pair sits on a part-boundary-truncated part and therefore proves the
   refusal instead -- see that test's own docstring for the measurement behind it, and
   `test_part_boundary_truncation_is_refused_not_silently_corrupted` for the pinned
   regression proof of the truncation bug itself.
3. `test_contents_array_preserved_after_edit` -- RESEARCH.md Pitfall 3's structural
   proof: the array keeps its length and every untouched element keeps its exact bytes.
4. `test_contents_single_stream_never_becomes_array` -- the non-array shape, which must
   also survive unreshaped.

Plus the splice's own index arithmetic
(`test_multi_instruction_replacement_shifts_later_indices`, the only case where the
`len(new_instructions) - 1` shift is non-zero) and the two refusal guards:
`test_part_boundary_truncation_is_refused_not_silently_corrupted` and the
`stale_run_index` pair (`test_stale_run_index_after_first_edit_is_refused` /
`test_re_derived_run_index_allows_sequential_edits_to_one_part`).

The replacement instruction is deliberately a trivial `(x) Tj` -- the mechanism under
test is the splice, not character mapping (Tasks 3-4 cover that separately).

No test asserts on decoded glyph text content -- only counts, indices and bytes of
instructions the test itself constructed, per this project's no-document-content
convention.

## Task 2's own cases, and the stand-in that makes them possible

`rewrite_run`'s two operand-resolution helpers (`_resolve_substituted_operand`,
`_resolve_non_substituted_operand`) are font-aware and land in Tasks 3 and 4. Task 2 owns
the dispatch/bracket/guard skeleton AROUND them, so every Task-2 test monkeypatches
`engine.rewrite._resolve_non_substituted_operand` with `_stand_in(...)` below -- a
one-line resolver that returns whatever instruction the test hands it. That keeps these
tests about the skeleton (Tz bracketing, the D-04 re-walk, refusal naming) rather than
about character mapping, and it is what lets the D-04 guard be exercised in BOTH
directions: an identity replacement (same operand, therefore provably the same width) and
a deliberately doubled operand (provably wider), on the same fixture run.

## Task 3's own cases

`_resolve_substituted_operand` is real from Task 3 on, so its tests (the block at the end
of this file) use NO stand-in at all: each builds a genuine `SubsetFont` + embedded Type0
font through `engine.fonts`' public pipeline and asserts on the content-stream bytes
actually written back. Task 2's tests still stand in for the NON-substituted resolver,
which Task 4 owns -- and now also switch off Task 3's edit-time substitution trigger
(`_no_edit_time_trigger`), because both of their fixture runs use a non-embedded font that
legitimately fires it.
"""

from __future__ import annotations

import ast
import re
import sys
import tempfile
from pathlib import Path
from typing import Callable

import pikepdf
import pytest
from fontTools.agl import UV2AGL

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

import engine.classify_run  # noqa: E402
import engine.rewrite  # noqa: E402
from engine.classify_run import RunVerdict, stream_bytes_and_resources  # noqa: E402
from engine.encoding_table import resolve_font  # noqa: E402
from engine.fit import FitResult, advance_pt_for_codes  # noqa: E402
from engine.fonts import (  # noqa: E402
    SubsetFont,
    embed_type0_font,
    reverse_encoding_map,
    shape_cids,
    shape_glyph_names,
    subset_cid_widths,
    subset_font_for_family,
)
from engine.index import RunIndex  # noqa: E402
from engine.records import RunRecord  # noqa: E402
from engine.rewrite import (  # noqa: E402
    ParsedInstruction,
    rewrite_instructions,
    rewrite_run,
    touched_instruction_indices,
)
from engine.run_id import decode_run_id  # noqa: E402

IRS_1040 = REPO_ROOT / "corpus" / "public" / "irs_form_1040.pdf"
IRS_W4 = REPO_ROOT / "corpus" / "public" / "irs_form_w4.pdf"

# The two fixture runs Task 2's own cases need, both picked by direct measurement.
#
# `GUARDED_RUN` -- `govdocs1_000_000011.pdf` page 0, `/Contents[0]`, the `:o487` run: one
# touched instruction (so an identity replacement is exactly the original run), and the
# next text-showing operator on that part follows it with NO intervening positioning
# operator (`Td`/`TD`/`Tm`/`T*`/`BT`/`ET`/`cm`/`q`/`Q`). That last property is what makes
# the D-04 guard non-vacuous: the following glyph's origin is the PEN POSITION left by this
# run, so changing this run's width provably moves it.
#
# MEASURED, and load-bearing for why this is NOT one of the IRS fixtures Task 1 uses: over
# page 0 of the first 20 corpus documents, 9 of 2,106 correlatable editable runs (0.4%) have
# an advance-dependent follower like this. Everything else -- including every editable run
# on `irs_form_1040.pdf` page 0 -- is followed by absolutely-positioned text, against which
# D-04's invariant holds no matter what width is written. See `engine/rewrite.py`'s own
# "What the D-04 guard does and does not catch" note for the consequence.
#
# `LAST_RUN_ON_PART` -- `irs_form_1040.pdf` page 0, `/Contents[0]`, the `:o9116` run: the
# LAST run on that part, so `_matrix_after_run` returns None on both sides and the guard
# passes trivially. Used by the Tz test, whose subject is the emitted bracket rather than
# width fitting (condensing genuinely narrows a run; fitting to it is Task 4's job).
GOVDOCS_11 = REPO_ROOT / "corpus" / "public" / "govdocs1_000_000011.pdf"
GUARDED_RUN = ":o487"
LAST_RUN_ON_PART = ":o9116"

# The four refusal reasons `engine/rewrite.py` itself can produce, pinned here as a literal
# rather than imported from the module (a test that imports the set it is checking proves
# nothing). EDIT-04: short, fixed, named -- never a generic failure, never document content.
MODULE_REFUSAL_REASONS = frozenset(
    {
        "correlation_failed",
        "part_boundary_truncated",
        "stale_run_index",
        "text_matrix_shifted_after_edit",
        "operator_shared_by_multiple_runs",
        "fit_refused",
        "substitution_required_but_no_target_provided",
        "no_active_font_for_substitution",
        "no_active_font_for_original_encoding",
        "character_has_no_code_in_original_encoding",
    }
)

# `govdocs1_000_000137.pdf` page 0, `/Contents[0]`, the `:c0:o94` run: the reviewer-named
# non-100 `Tz` document, measured -- the run is preceded by `87 Tz`, correlates to exactly
# one instruction, and shares its operator with no other run. 851 of 941 `Tz` operators
# across the first 20 corpus documents (pages 0-2) set a non-100 value, concentrated here.
GOVDOCS_137 = REPO_ROOT / "corpus" / "public" / "govdocs1_000_000137.pdf"
NON_DEFAULT_TZ_RUN = ":c0:o94"
NON_DEFAULT_TZ_BASELINE = 87.0

# `govdocs1_000_000009.pdf` page 0, `/Contents[5]`: 30 of its text-showing operators back
# 2+ runs, one of them 36 -- the shared-operator hazard, picked by measurement at test time
# rather than pinned to a run ID, since which run is chosen does not matter.
GOVDOCS_9 = REPO_ROOT / "corpus" / "public" / "govdocs1_000_000009.pdf"


def _replacement() -> pikepdf.ContentStreamInstruction:
    return pikepdf.ContentStreamInstruction(
        [pikepdf.String(b"x")], pikepdf.Operator("Tj")
    )


def _page_runs(pdf_path: Path, page_index: int) -> list[RunRecord]:
    with RunIndex(pdf_path) as idx:
        return [run for run, _verdict in idx.page(page_index).runs]


def _part_key(run: RunRecord) -> tuple[int, tuple[int, ...]]:
    parts = decode_run_id(run.run_id)
    return parts["part"], parts["xobj_path"]


def _parse_part(
    pdf: pikepdf.Pdf, page_index: int, run: RunRecord
) -> list[ParsedInstruction]:
    """The instruction list of whichever content-stream part `run` lives in, read fresh
    from `pdf` -- so calling it after a rewrite sees the rewritten bytes."""
    part, xobj_path = _part_key(run)
    stream_bytes, _resources = stream_bytes_and_resources(pdf, page_index, part, xobj_path)
    return pikepdf.parse_content_stream(pdf.make_stream(stream_bytes))


def _touched(
    instructions: list[ParsedInstruction],
    run: RunRecord,
    all_page_runs: list[RunRecord],
) -> list[int]:
    """The test's OWN independent correlation, using the same public pure function the
    module under test uses -- never reaching into `engine.rewrite`'s private helpers."""
    key = _part_key(run)
    all_offsets: set[int] = set()
    for other in all_page_runs:
        if _part_key(other) == key:
            all_offsets.update(g.operator_byte_offset for g in other.glyphs)
    return touched_instruction_indices(
        instructions,
        {g.operator_byte_offset for g in run.glyphs},
        sorted(all_offsets),
    )


def _unparse(instruction: ParsedInstruction) -> bytes:
    return bytes(pikepdf.unparse_content_stream([instruction]))


def _find_noncontiguous_pair(
    runs: list[RunRecord],
) -> tuple[RunRecord, RunRecord]:
    """A (target, foreign) pair on the same part where `foreign` has an operator strictly
    between `target`'s own first and last -- RESEARCH.md Pitfall 2's own detection."""
    groups: dict[tuple[int, tuple[int, ...]], list[RunRecord]] = {}
    for run in runs:
        groups.setdefault(_part_key(run), []).append(run)

    for group in groups.values():
        if len(group) < 2:
            continue
        for run in group:
            offsets = sorted({g.operator_byte_offset for g in run.glyphs})
            if len(offsets) < 2:
                continue
            lo, hi = offsets[0], offsets[-1]
            for other in group:
                if other is run:
                    continue
                if any(lo < g.operator_byte_offset < hi for g in other.glyphs):
                    return run, other
    raise AssertionError("no non-contiguous run pair found")


def test_multi_operator_run_consolidates_to_one_instruction() -> None:
    """Pitfall 1: 62 touched instructions become exactly one. The part's instruction
    count therefore drops by exactly 61, and the survivor at the first-touched position
    is the replacement the caller supplied."""
    runs = _page_runs(IRS_1040, 0)
    target = next(run for run in runs if run.run_id.endswith(":o1391"))

    with pikepdf.open(IRS_1040) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs)
        assert len(touched) == 62

        replacement = _replacement()
        outcome = rewrite_instructions(pdf, 0, target, runs, [replacement])
        assert outcome.ok is True
        assert outcome.reason is None

        after = _parse_part(pdf, 0, target)
        assert len(after) == len(before) - 61
        assert _unparse(after[touched[0]]) == _unparse(replacement)


def test_multi_instruction_replacement_shifts_later_indices() -> None:
    """The only case that actually exercises the `len(new_instructions) - 1` shift in the
    deletion loop -- every other test installs exactly one instruction, where the shift is
    zero and an off-by-one there would be invisible."""
    runs = _page_runs(IRS_1040, 0)
    target = next(run for run in runs if run.run_id.endswith(":o1391"))

    with pikepdf.open(IRS_1040) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs)
        # An instruction of the target's OWN part that the run does not touch, sitting
        # strictly inside the touched span (the run interleaves Tj with Td).
        untouched_index = next(
            i for i in range(touched[0] + 1, touched[-1]) if i not in set(touched)
        )
        expected = _unparse(before[untouched_index])

        replacements = [_replacement(), _replacement(), _replacement()]
        assert rewrite_instructions(pdf, 0, target, runs, replacements).ok is True

        after = _parse_part(pdf, 0, target)
        shift = len(replacements) - 1
        assert len(after) == len(before) - len(touched) + len(replacements)
        for offset, replacement in enumerate(replacements):
            assert _unparse(after[touched[0] + offset]) == _unparse(replacement)
        expected_index = (
            untouched_index
            + shift
            - len([t for t in touched[1:] if t < untouched_index])
        )
        assert _unparse(after[expected_index]) == expected


def _assert_foreign_survives(page_index: int) -> None:
    runs = _page_runs(IRS_W4, page_index)
    target, foreign = _find_noncontiguous_pair(runs)

    with pikepdf.open(IRS_W4) as pdf:
        before = _parse_part(pdf, page_index, target)
        touched = _touched(before, target, runs)
        foreign_touched = _touched(before, foreign, runs)
        interleaved = [i for i in foreign_touched if touched[0] < i < touched[-1]]
        assert interleaved, "fixture no longer reproduces Pitfall 2's interleaving"
        foreign_index = interleaved[0]
        expected = _unparse(before[foreign_index])

        outcome = rewrite_instructions(pdf, page_index, target, runs, [_replacement()])
        assert outcome.ok is True

        # Where that untouched instruction must now sit: one instruction took the slot
        # of `touched[0]` (net shift len(new_instructions) - 1 == 0 here), and every
        # touched index below it was deleted.
        shift = 1 - 1
        expected_index = (
            foreign_index + shift - len([t for t in touched[1:] if t < foreign_index])
        )

        after = _parse_part(pdf, page_index, target)
        assert len(after) == len(before) - (len(touched) - 1)
        assert _unparse(after[expected_index]) == expected


def _assert_foreign_pair_refused_as_truncated(page_index: int) -> None:
    """The same Pitfall-2 pair, on a part whose isolated parse is truncated: the edit must
    refuse by name and leave the part's bytes byte-for-byte untouched."""
    runs = _page_runs(IRS_W4, page_index)
    target, _foreign = _find_noncontiguous_pair(runs)
    part, xobj_path = _part_key(target)

    with pikepdf.open(IRS_W4) as pdf:
        before_bytes, _res = stream_bytes_and_resources(pdf, page_index, part, xobj_path)

        outcome = rewrite_instructions(pdf, page_index, target, runs, [_replacement()])
        assert outcome.ok is False
        assert outcome.reason == "part_boundary_truncated"

        after_bytes, _res = stream_bytes_and_resources(pdf, page_index, part, xobj_path)
        assert after_bytes == before_bytes


def test_foreign_interleaved_operator_survives_unedited() -> None:
    """Pitfall 2, both measured `irs_form_w4.pdf` pages.

    Page 4 proves the survival property directly: the interleaved foreign instruction is
    byte-for-byte identical and at its original relative position among the survivors.

    Page 0 cannot prove it, and the reason is a measured property of the fixture rather
    than a choice: enumerated directly, page 0's `/Contents` array has exactly ONE
    non-contiguous run in all 8 parts, and it lives on part 5 -- the part whose isolated
    parse is truncated at the part-5/part-6 boundary. There is no clean Pitfall-2 pair on
    that page to move the assertion to. The correct behaviour for that pair is now the
    refusal (rewriting it would delete part 5's dangling operands), so page 0 asserts
    exactly that, and the survival property stands proven on page 4 plus, for a non-run
    interleaved instruction, on `irs_form_1040.pdf` in
    `test_multi_instruction_replacement_shifts_later_indices`.
    """
    _assert_foreign_pair_refused_as_truncated(0)
    _assert_foreign_survives(4)


def test_part_boundary_truncation_is_refused_not_silently_corrupted() -> None:
    """The direct regression proof for the truncation bug, pinned to the exact known-bad
    fixture rather than to whatever `_find_noncontiguous_pair` happens to select:
    `irs_form_w4.pdf` page 0, `/Contents[5]`, which ends mid-instruction
    (`... BT /Content <</MCID 124 >>`) with the consuming `BDC` keyword living at the start
    of `/Contents[6]`. Parsing part 5 alone discards those dangling operands, so writing
    that parse back would delete them from the document. Every editable run on that part
    must refuse, by name, and leave the bytes alone."""
    truncated_part = 5
    runs = _page_runs(IRS_W4, 0)
    on_part = [run for run in runs if _part_key(run) == (truncated_part, ())]
    assert on_part, "fixture no longer has runs on irs_form_w4.pdf page 0 part 5"

    with pikepdf.open(IRS_W4) as pdf:
        contents = pdf.pages[0].obj["/Contents"]
        before = bytes(contents[truncated_part].read_bytes())
        # The exact shape under test: the part ends mid-instruction, and the operator
        # keyword that consumes its trailing operands is the next part's first token.
        assert not before.rstrip().endswith(b"BDC")
        assert bytes(contents[truncated_part + 1].read_bytes()).lstrip().startswith(b"BDC")

        for run in on_part:
            outcome = rewrite_instructions(pdf, 0, run, runs, [_replacement()])
            assert outcome.ok is False
            assert outcome.reason == "part_boundary_truncated"

        assert bytes(pdf.pages[0].obj["/Contents"][truncated_part].read_bytes()) == before


def test_contents_array_preserved_after_edit() -> None:
    """Pitfall 3, the 13,689-line-diff regression: an array `/Contents` keeps its shape,
    its length, and every untouched element's exact bytes."""
    runs = _page_runs(IRS_1040, 0)
    target = next(run for run in runs if run.run_id.endswith(":o1391"))
    edited_part, xobj_path = _part_key(target)
    assert xobj_path == ()

    with pikepdf.open(IRS_1040) as pdf:
        contents = pdf.pages[0].obj["/Contents"]
        assert isinstance(contents, pikepdf.Array)
        before_len = len(contents)
        before_bytes = {i: bytes(contents[i].read_bytes()) for i in range(before_len)}

        assert rewrite_instructions(pdf, 0, target, runs, [_replacement()]).ok is True

        after_contents = pdf.pages[0].obj["/Contents"]
        assert isinstance(after_contents, pikepdf.Array)
        assert len(after_contents) == before_len
        for i in range(before_len):
            if i == edited_part:
                continue
            assert bytes(after_contents[i].read_bytes()) == before_bytes[i]
        assert bytes(after_contents[edited_part].read_bytes()) != before_bytes[edited_part]


def test_contents_single_stream_never_becomes_array() -> None:
    """The other 47.5% of the corpus: a single-stream `/Contents` is still a single
    stream after an edit -- the rewrite never reshapes `/Contents` in either direction."""
    runs = _page_runs(IRS_W4, 4)
    target, _foreign = _find_noncontiguous_pair(runs)

    with pikepdf.open(IRS_W4) as pdf:
        contents = pdf.pages[4].obj["/Contents"]
        assert not isinstance(contents, pikepdf.Array)

        assert rewrite_instructions(pdf, 4, target, runs, [_replacement()]).ok is True

        after_contents = pdf.pages[4].obj["/Contents"]
        assert not isinstance(after_contents, pikepdf.Array)
        assert isinstance(after_contents, pikepdf.Stream)


def _second_run_sharing_part(
    instructions: list[ParsedInstruction],
    first: RunRecord,
    runs: list[RunRecord],
) -> RunRecord:
    """Another run on the SAME content-stream part as `first`, whose own instructions all
    sit AFTER `first`'s last touched one -- so a first edit to `first` shifts its true
    ordinal. `irs_form_1040.pdf` page 0 part 0 carries 32 such runs."""
    first_touched = _touched(instructions, first, runs)
    for run in runs:
        if run is first or _part_key(run) != _part_key(first):
            continue
        touched = _touched(instructions, run, runs)
        if touched and touched[0] > first_touched[-1]:
            return run
    raise AssertionError("no later run sharing the target's part")


def test_stale_run_index_after_first_edit_is_refused() -> None:
    """Two sequential edits to the same part, reusing the SAME pre-edit `all_page_runs`
    for both. Correlation is by ordinal among text-showing operators, so after the first
    edit consolidated 62 instructions into 1, every other run on that part has a stale
    ordinal -- and the stale index still lands on a syntactically valid `Tj`, just a
    different run's. The second call must refuse rather than silently overwrite it."""
    runs = _page_runs(IRS_1040, 0)
    first = next(run for run in runs if run.run_id.endswith(":o1391"))

    with pikepdf.open(IRS_1040) as pdf:
        before = _parse_part(pdf, 0, first)
        second = _second_run_sharing_part(before, first, runs)
        true_target = _unparse(before[_touched(before, second, runs)[0]])

        assert rewrite_instructions(pdf, 0, first, runs, [_replacement()]).ok is True

        after_first = _parse_part(pdf, 0, first)
        stale_index = _touched(after_first, second, runs)[0]
        # The exact silent-corruption shape: still a valid text-showing instruction, at a
        # valid index, and NOT the run the caller asked to edit.
        assert str(after_first[stale_index].operator) in {"Tj", "TJ", "'", '"'}
        assert _unparse(after_first[stale_index]) != true_target

        outcome = rewrite_instructions(pdf, 0, second, runs, [_replacement()])
        assert outcome.ok is False
        assert outcome.reason == "stale_run_index"

        # Nothing was written: the instruction the stale correlation pointed at survives.
        after_second = _parse_part(pdf, 0, first)
        assert [_unparse(i) for i in after_second] == [_unparse(i) for i in after_first]


def test_re_derived_run_index_allows_sequential_edits_to_one_part() -> None:
    """The legitimate usage the `stale_run_index` refusal must not block: re-derive
    `all_page_runs` from the edited document between the two edits, and both succeed --
    with the second edit landing on the run that was actually requested, leaving the
    instruction the stale path would have clobbered byte-identical."""
    runs = _page_runs(IRS_1040, 0)
    first = next(run for run in runs if run.run_id.endswith(":o1391"))

    with tempfile.TemporaryDirectory() as scratch:
        edited = Path(scratch) / "edited.pdf"
        with pikepdf.open(IRS_1040) as pdf:
            before = _parse_part(pdf, 0, first)
            second = _second_run_sharing_part(before, first, runs)
            second_text = second.display_text

            assert rewrite_instructions(pdf, 0, first, runs, [_replacement()]).ok is True

            after_first = _parse_part(pdf, 0, first)
            would_clobber = _unparse(after_first[_touched(after_first, second, runs)[0]])
            pdf.save(edited)

        # Re-derive: re-walk and re-classify the EDITED document.
        fresh_runs = _page_runs(edited, 0)
        fresh = [
            run
            for run in fresh_runs
            if _part_key(run) == _part_key(first) and run.display_text == second_text
        ]
        assert len(fresh) == 1, "second run no longer uniquely identifiable after edit 1"

        with pikepdf.open(edited) as pdf2:
            b = _parse_part(pdf2, 0, fresh[0])
            fresh_touched = _touched(b, fresh[0], fresh_runs)
            clobber_count = [_unparse(i) for i in b].count(would_clobber)

            outcome = rewrite_instructions(pdf2, 0, fresh[0], fresh_runs, [_replacement()])
            assert outcome.ok is True
            assert outcome.reason is None

            after = _parse_part(pdf2, 0, fresh[0])
            assert len(after) == len(b) - (len(fresh_touched) - 1)
            assert _unparse(after[fresh_touched[0]]) == _unparse(_replacement())
            # The instruction the stale path would have destroyed is still there.
            assert [_unparse(i) for i in after].count(would_clobber) == clobber_count


# --------------------------------------------------------------------------------------
# Task 2: rewrite_run -- Tz bracket, D-04 runtime matrix guard, refusal vocabulary
# --------------------------------------------------------------------------------------


def _stand_in(
    instruction: pikepdf.ContentStreamInstruction,
) -> Callable[..., pikepdf.ContentStreamInstruction]:
    """The MINIMAL operand-resolution stand-in Task 2's tests run against, in place of the
    font-aware `_resolve_non_substituted_operand` Task 4 implements: it ignores `new_text`
    and `fit_result` entirely and installs exactly the instruction the test chose. That is
    the point -- it makes the replacement's WIDTH something the test controls exactly, which
    is what both directions of the D-04 guard need. Task 4's own tests use no stand-in at
    all; they drive the real resolver."""

    def _resolve(
        pdf: pikepdf.Pdf,
        page_index: int,
        run: RunRecord,
        all_page_runs: list[RunRecord],
        new_text: str,
        fit_result: FitResult,
    ) -> pikepdf.ContentStreamInstruction:
        return instruction

    return _resolve


def _use_stand_in(
    monkeypatch: pytest.MonkeyPatch, instruction: pikepdf.ContentStreamInstruction
) -> None:
    monkeypatch.setattr(
        engine.rewrite, "_resolve_non_substituted_operand", _stand_in(instruction)
    )


def _no_edit_time_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch OFF Pattern 4's edit-time substitution trigger, leaving `rewrite_run`'s
    dispatch on Phase 2's own `editable_substitution` state alone (which `rewrite_run`
    tests first, and which this does not touch).

    Needed once Task 3 made the trigger live, because both Task-2 fixture runs use a font
    that is NOT EMBEDDED -- measured: `govdocs1_000_000011.pdf`'s `/ArialMT` (TrueType,
    `TT-a`) and `govdocs1_000_000137.pdf`'s `/Times-Roman` (Type1, `T1-c`) both have no
    `/FontFile*` at all -- and `glyph_presence` treats an absent program as "cannot confirm
    this glyph", i.e. substitute. So every edit on those two fixtures now routes to the
    substituted branch. That is correct behaviour, not an over-trigger (D-07 chose
    Liberation for exactly the metric-compatible Arial/Times case), but it is not what
    these tests are about: their subject is the Tz bracket, the D-04 guard and the refusal
    vocabulary AROUND the operand resolver. The trigger itself is proven in both directions
    by `test_editable_original_run_substitutes_when_trigger_fires`.
    """

    def _never(
        pdf: pikepdf.Pdf,
        page_index: int,
        run: RunRecord,
        all_page_runs: list[RunRecord],
        new_text: str,
    ) -> bool:
        return False

    monkeypatch.setattr(engine.rewrite, "_substitution_triggered", _never)


def _contents_bytes(pdf: pikepdf.Pdf, page_index: int) -> list[bytes]:
    """Every `/Contents` part's decoded bytes, for either page shape (array or single
    stream) -- the before/after evidence that a refusal wrote nothing at all."""
    contents = pdf.pages[page_index].obj["/Contents"]
    parts = contents if isinstance(contents, pikepdf.Array) else [contents]
    return [bytes(part.read_bytes()) for part in parts]


def _verdict() -> RunVerdict:
    return RunVerdict("editable_original")


def _fit_no_width_change() -> FitResult:
    """A `trailing_kern` FitResult -- the rung whose whole purpose is that the run's total
    advance is unchanged. Paired in every test below with an identity replacement, so the
    "no width change" the ladder promises is actually true of the bytes written."""
    return FitResult(10.0, 10.0, 0.0, "trailing_kern", [0.0])


def _fit_tz() -> FitResult:
    return FitResult(
        10.0, 11.0, 0.0, "tz", [], condensed_scale=90.9, original_scale_to_restore=100.0
    )


def _fit_refused() -> FitResult:
    """`engine/fit.py`'s own refusal shape. NOTE the spelling: `fit_run` produces
    `strategy == "refused"` (plus `refused=True`), where 03-06-PLAN.md's prose says
    "refuse" -- `rewrite_run` accepts both, see its own comment."""
    return FitResult(
        10.0,
        30.0,
        20.0,
        "refused",
        [],
        refused=True,
        refusal_reason="delta 20.00pt exceeds trailing-kern (+/-2.00pt) absorption range",
    )


def _only_run(runs: list[RunRecord], suffix: str) -> RunRecord:
    matches = [run for run in runs if run.run_id.endswith(suffix)]
    assert len(matches) == 1, f"fixture no longer has exactly one run ending {suffix}"
    return matches[0]


def _doubled(instruction: ParsedInstruction) -> pikepdf.ContentStreamInstruction:
    """The same `Tj` with its string operand repeated twice -- the same character codes, so
    the same per-glyph widths, therefore an operand of provably DOUBLE the original run's
    advance. The synthetic "wrong width" the D-04 guard must catch, built by bypassing the
    fit ladder entirely rather than by asking it for a bad answer."""
    operand = instruction.operands[0]
    assert isinstance(operand, pikepdf.String)
    raw = bytes(operand)
    return pikepdf.ContentStreamInstruction(
        [pikepdf.String(raw + raw)], pikepdf.Operator("Tj")
    )


def _operand_number(instruction: ParsedInstruction) -> float:
    return float(instruction.operands[0])


def test_tz_bracket_restores_scale_instruction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pattern 3 / D-02: the `tz` rung emits exactly three instructions in the replaced
    slot -- condensed `Tz`, the replacement, then the ORIGINAL scale re-asserted as a plain
    explicit operator (never a `q`/`Q` bracket). Proven restored, not merely emitted: from
    the replacement forward, the first `Tz` encountered is the restore, and no further `Tz`
    intervenes before the next text-showing operator, so the scale in force at the next
    shown text is `original_scale_to_restore`, not the condensed value.

    Runs against `LAST_RUN_ON_PART` so the D-04 guard is trivially satisfied (nothing
    follows the run on that part): condensing genuinely narrows the run, and fitting the
    replacement to the condensed width is Task 4's job, not this test's subject.
    """
    runs = _page_runs(IRS_1040, 0)
    target = _only_run(runs, LAST_RUN_ON_PART)
    fit = _fit_tz()

    with pikepdf.open(IRS_1040) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs)
        assert len(touched) == 1
        original = before[touched[0]]
        _use_stand_in(monkeypatch, original)

        outcome = rewrite_run(pdf, 0, target, _verdict(), runs, "x", fit)
        assert outcome.ok is True, outcome.reason

        after = _parse_part(pdf, 0, target)
        first = touched[0]
        assert str(after[first].operator) == "Tz"
        assert _operand_number(after[first]) == pytest.approx(fit.condensed_scale)
        assert _unparse(after[first + 1]) == _unparse(original)
        assert str(after[first + 2].operator) == "Tz"
        assert _operand_number(after[first + 2]) == pytest.approx(
            fit.original_scale_to_restore
        )

        # Nothing re-condenses the scale between the restore and the next shown text.
        for instr in after[first + 3 :]:
            if str(instr.operator) in {"Tj", "TJ", "'", '"'}:
                break
            assert str(instr.operator) != "Tz"


def test_edit02_matrix_invariant_holds_after_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    """EDIT-02/D-04, the positive case: an edit the fit ladder guarantees costs no width
    (here made exactly true -- the replacement IS the original instruction) leaves the
    first glyph after the edited run where it was, and `rewrite_run` reports ok.

    Non-vacuous by construction: the same fixture run, edited with a deliberately wider
    operand, makes the guard fire in `test_matrix_guard_fires_on_synthetic_shift` -- so
    there demonstrably IS a following glyph whose position this test is comparing.
    """
    runs = _page_runs(GOVDOCS_11, 0)
    target = _only_run(runs, GUARDED_RUN)

    with pikepdf.open(GOVDOCS_11) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs)
        assert len(touched) == 1
        _use_stand_in(monkeypatch, before[touched[0]])
        _no_edit_time_trigger(monkeypatch)

        outcome = rewrite_run(pdf, 0, target, _verdict(), runs, "x", _fit_no_width_change())
        assert outcome.ok is True, outcome.reason
        assert outcome.reason is None


def test_matrix_guard_fires_on_synthetic_shift(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-04's negative case -- the one that proves the guard is load-bearing rather than
    merely never-failing. The replacement is built by bypassing the fit ladder entirely
    (the run's own operand, doubled), so the glyph after the run genuinely moves, and
    `rewrite_run` must refuse BY NAME."""
    runs = _page_runs(GOVDOCS_11, 0)
    target = _only_run(runs, GUARDED_RUN)

    with pikepdf.open(GOVDOCS_11) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs)
        _use_stand_in(monkeypatch, _doubled(before[touched[0]]))
        _no_edit_time_trigger(monkeypatch)

        outcome = rewrite_run(pdf, 0, target, _verdict(), runs, "x", _fit_no_width_change())
        assert outcome.ok is False
        assert outcome.reason == "text_matrix_shifted_after_edit"


def test_refuse_strategy_never_mutates_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """A refusing `FitResult` short-circuits before any content-stream work at all: the
    outcome carries the fit's own reason, the page's `/Contents` bytes are byte-identical,
    and the operand resolver was never called (a spy proves the short-circuit happened
    before the dispatch, not merely that the write was skipped)."""
    runs = _page_runs(GOVDOCS_11, 0)
    target = _only_run(runs, GUARDED_RUN)
    fit = _fit_refused()
    calls: list[str] = []

    def _spy(*args: object, **kwargs: object) -> pikepdf.ContentStreamInstruction:
        calls.append("called")
        return _replacement()

    monkeypatch.setattr(engine.rewrite, "_resolve_non_substituted_operand", _spy)

    with pikepdf.open(GOVDOCS_11) as pdf:
        before = _contents_bytes(pdf, 0)

        outcome = rewrite_run(pdf, 0, target, _verdict(), runs, "x", fit)
        assert outcome.ok is False
        assert outcome.reason == fit.refusal_reason
        assert calls == []

        assert _contents_bytes(pdf, 0) == before


def _malformed_run(template: RunRecord) -> RunRecord:
    """A run whose ID cannot be decoded at all -- the `correlation_failed` path, reached
    through `rewrite_run`'s own pre-mutation guard rather than by monkeypatching."""
    return RunRecord(
        run_id="not-a-run-id",
        glyphs=template.glyphs,
        display_text="",
        page=template.page,
    )


def test_rewrite_refusal_reasons_are_named(monkeypatch: pytest.MonkeyPatch) -> None:
    """EDIT-04: every reason this module produces itself is one short, fixed, named string
    from `MODULE_REFUSAL_REASONS` -- never a generic failure, never an f-string carrying
    `new_text` or any decoded character. Collected by direct unit calls that each drive one
    distinct code path, not by reading the source.

    The one reason that is NOT from that set is the `FitResult` pass-through, which
    `engine/fit.py` owns and which carries measured point values (no document content);
    it is asserted separately, to the same no-document-content standard.
    """
    new_text = "ZZQQ-sentinel"
    reasons: set[str] = set()

    # Captured BEFORE the stand-ins below replace them, so cases 9 and 10 can drive the
    # real non-substituted resolver inside the same monkeypatched block.
    real_resolver = engine.rewrite._resolve_non_substituted_operand
    real_font_operands = engine.rewrite._active_font_operands

    runs_gov = _page_runs(GOVDOCS_11, 0)
    target = _only_run(runs_gov, GUARDED_RUN)

    with pikepdf.open(GOVDOCS_11) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs_gov)
        _use_stand_in(monkeypatch, _doubled(before[touched[0]]))
        _no_edit_time_trigger(monkeypatch)

        # 1. the D-04 guard.
        shifted = rewrite_run(
            pdf, 0, target, _verdict(), runs_gov, new_text, _fit_no_width_change()
        )
        assert shifted.reason is not None
        reasons.add(shifted.reason)

        # 2. an undecodable run ID, refused before any mutation is attempted.
        broken = rewrite_run(
            pdf,
            0,
            _malformed_run(target),
            _verdict(),
            runs_gov,
            new_text,
            _fit_no_width_change(),
        )
        assert broken.reason is not None
        reasons.add(broken.reason)

        # 3. an `all_page_runs` that does not describe the part's current text operators.
        stale = rewrite_instructions(pdf, 0, target, [target], [_replacement()])
        assert stale.reason is not None
        reasons.add(stale.reason)

        # 4. a FitResult that refuses without setting a reason of its own.
        unnamed = FitResult(10.0, 30.0, 20.0, "refused", [], refused=True)
        no_reason = rewrite_run(
            pdf, 0, target, _verdict(), runs_gov, new_text, unnamed
        )
        assert no_reason.reason is not None
        reasons.add(no_reason.reason)

        # 5. a run needing substitution with no target supplied (D-13: this module never
        #    builds one itself).
        no_target = rewrite_run(
            pdf,
            0,
            target,
            RunVerdict("editable_substitution"),
            runs_gov,
            new_text,
            _fit_no_width_change(),
        )
        assert no_target.reason is not None
        reasons.add(no_target.reason)

        # 8. a run whose active `Tf` cannot be resolved to a (name, size) pair -- the
        #    substituted branch's own pre-flight, refused by name rather than raised.
        monkeypatch.setattr(engine.rewrite, "_active_font_operands", lambda *a: None)
        no_font = rewrite_run(
            pdf,
            0,
            target,
            RunVerdict("editable_substitution"),
            runs_gov,
            new_text,
            _fit_no_width_change(),
            _substitution_target(pdf, "x"),
        )
        assert no_font.reason is not None
        reasons.add(no_font.reason)

        # 9. the SAME declined `Tf` scan, reached down the NON-substituted branch (which
        #    resolves the run's own font through it too) -- its own distinct name, so a
        #    caller can tell which encoding path could not be built.
        monkeypatch.setattr(
            engine.rewrite, "_resolve_non_substituted_operand", real_resolver
        )
        no_original_font = rewrite_run(
            pdf, 0, target, _verdict(), runs_gov, new_text, _fit_no_width_change()
        )
        assert no_original_font.reason is not None
        reasons.add(no_original_font.reason)

        # 10. a character the run's own `/Encoding` has no code for. U+6F22 has no Adobe
        #     Glyph List name at all, so it cannot map through ANY simple font's encoding.
        monkeypatch.setattr(
            engine.rewrite, "_active_font_operands", real_font_operands
        )
        unmappable = rewrite_run(
            pdf, 0, target, _verdict(), runs_gov, "漢", _fit_no_width_change()
        )
        assert unmappable.reason is not None
        reasons.add(unmappable.reason)

    # Cases 6 and 7 both refuse BEFORE any operand resolution, so the patches above
    # (deliberately left in place) cannot reach them.
    # 6. an operator shared by more than one run.
    runs_9 = _page_runs(GOVDOCS_9, 0)
    with pikepdf.open(GOVDOCS_9) as pdf_9:
        shared = rewrite_run(
            pdf_9,
            0,
            _run_sharing_an_operator(runs_9, part=5),
            _verdict(),
            runs_9,
            new_text,
            _fit_no_width_change(),
        )
        assert shared.reason is not None
        reasons.add(shared.reason)

    # 7. the part-boundary truncation refusal (irs_form_w4.pdf page 0, /Contents[5]).
    runs_w4 = _page_runs(IRS_W4, 0)
    on_truncated_part = [run for run in runs_w4 if _part_key(run) == (5, ())]
    assert on_truncated_part
    with pikepdf.open(IRS_W4) as pdf_w4:
        truncated = rewrite_instructions(
            pdf_w4, 0, on_truncated_part[0], runs_w4, [_replacement()]
        )
        assert truncated.reason is not None
        reasons.add(truncated.reason)

    assert reasons == MODULE_REFUSAL_REASONS
    for reason in reasons:
        assert re.fullmatch(r"[a-z][a-z_]{,63}", reason), reason
        assert new_text not in reason

    # The pass-through: `fit_result.refusal_reason`, verbatim, and content-free.
    fit = _fit_refused()
    with pikepdf.open(GOVDOCS_11) as pdf:
        passthrough = rewrite_run(pdf, 0, target, _verdict(), runs_gov, new_text, fit)
    assert passthrough.reason == fit.refusal_reason
    assert new_text not in (passthrough.reason or "")


def _run_sharing_an_operator(runs: list[RunRecord], part: int) -> RunRecord:
    """A run on `part` that shows glyphs through a text-showing operator ANOTHER run on the
    same part also uses -- the hazard `_operator_shared_with_another_run` refuses. Found by
    measurement rather than pinned to a run ID: the fixture has dozens."""
    owners: dict[int, set[int]] = {}
    on_part = [run for run in runs if _part_key(run) == (part, ())]
    for run in on_part:
        for glyph in run.glyphs:
            owners.setdefault(glyph.operator_byte_offset, set()).add(id(run))
    shared = {offset for offset, ids in owners.items() if len(ids) > 1}
    assert shared, f"fixture no longer has a shared text operator on part {part}"
    for run in on_part:
        if {glyph.operator_byte_offset for glyph in run.glyphs} & shared:
            return run
    raise AssertionError("unreachable: a shared operator has at least one owning run")


def test_tz_bracket_rebases_onto_active_scale(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `Tz` bracket is built against the scale ACTUALLY in force, not the spec default
    `engine/fit.py` had to assume.

    On this fixture the text object is already at `87 Tz`, so restoring 100 would render
    everything after the edit ~15% wider (D-02's persistence hazard, inverted), and a
    `condensed_scale` of R% -- which `fit_run` computes as a metric RATIO, with no
    horizontal scaling in it at all -- must be emitted as `87 * R / 100`, not as R.
    """
    runs = _page_runs(GOVDOCS_137, 0)
    target = _only_run(runs, NON_DEFAULT_TZ_RUN)
    fit = _fit_tz()
    assert fit.condensed_scale is not None

    with pikepdf.open(GOVDOCS_137) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs)
        assert len(touched) == 1
        _use_stand_in(monkeypatch, before[touched[0]])
        _no_edit_time_trigger(monkeypatch)

        outcome = rewrite_run(pdf, 0, target, _verdict(), runs, "x", fit)
        assert outcome.ok is True, outcome.reason

        after = _parse_part(pdf, 0, target)
        first = touched[0]
        assert _operand_number(after[first]) == pytest.approx(
            NON_DEFAULT_TZ_BASELINE * fit.condensed_scale / 100.0
        )
        assert _operand_number(after[first + 2]) == pytest.approx(
            NON_DEFAULT_TZ_BASELINE
        )
        # The value fit.py had to assume, which this run is NOT at.
        assert fit.original_scale_to_restore == 100.0


def test_shared_operator_refuses_before_any_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A text-showing operator backing more than one run cannot be spliced for one of them
    without destroying the other's glyphs -- and `_correlate`'s count check cannot see it
    (it compares against a deduplicated offset SET, which one shared operator enters once
    however many runs stand behind it). `rewrite_run` refuses by name, deliberately and
    before any mutation -- not as a caught exception from a downstream re-walk."""
    runs = _page_runs(GOVDOCS_9, 0)
    target = _run_sharing_an_operator(runs, part=5)
    _use_stand_in(monkeypatch, _replacement())

    with pikepdf.open(GOVDOCS_9) as pdf:
        before = _contents_bytes(pdf, 0)

        outcome = rewrite_run(
            pdf, 0, target, _verdict(), runs, "x", _fit_no_width_change()
        )
        assert outcome.ok is False
        assert outcome.reason == "operator_shared_by_multiple_runs"
        assert _contents_bytes(pdf, 0) == before


# --------------------------------------------------------------------------------------
# Task 3: the substituted branch -- shape_cids/embed_type0_font wiring, Tf bracket,
# and the TJ array that carries `FitResult.kerns` (FONT-06, D-05, D-13 boundary)
# --------------------------------------------------------------------------------------
#
# Every test below runs against `LAST_RUN_ON_PART` (`irs_form_1040.pdf` page 0,
# `/Contents[0]`, the `:o9116` run) unless it says otherwise. Two measured properties make
# it the right subject: it is the LAST run on its part, so `_matrix_after_run` returns None
# on both sides and D-04's guard passes trivially (a substituted run genuinely changes the
# run's width, which is `engine/fit.py`'s problem, not this task's); and its active font is
# `/T1_0 1 Tf` with a `T1-a` verdict -- an EMBEDDED Type1, i.e. `editable_original`, which
# is exactly the state Pattern 4's edit-time trigger has to fire against.
#
# MEASURED against that font's own embedded program: "A" is available (no trigger), and
# U+20AC EURO SIGN is NOT -- it reaches `run_needs_substitution`'s check 2 ("glyph absent
# from embedded program"), which is the harder of Pattern 4's two checks and the one that
# genuinely could not have been answered at classification time.
SUBSTITUTING_TEXT = "A€"
NON_SUBSTITUTING_TEXT = "AB"


def _substitution_target(
    pdf: pikepdf.Pdf, text: str
) -> tuple[SubsetFont, pikepdf.Object]:
    """A real `(SubsetFont, embedded Type0 font object)` pair for `text`, built through
    `engine.fonts`' own public pipeline exactly as 03-05's tests construct one -- shape to
    glyph names, subset, embed with `/W` and `/ToUnicode`.

    D-13 lives HERE, in the test, and not in `engine/rewrite.py`: building the subset and
    embedding it is a cross-run, recipe-level concern (03-07's), so `rewrite_run` only ever
    consumes an already-built pair. Every test below builds exactly one and hands it in.
    """
    subset = subset_font_for_family(
        "Sans", "Regular", frozenset(shape_glyph_names("Sans", "Regular", text))
    )
    cids = shape_cids(subset, text)
    font_obj = embed_type0_font(
        pdf, subset, subset_cid_widths(subset), {cid: ch for cid, ch in cids}
    )
    return subset, font_obj


def _expected_cid_bytes(subset: SubsetFont, text: str) -> bytes:
    """What the replacement operand must contain, end to end: every shaped glyph of the
    WHOLE `text`, 2 bytes per CID big-endian (the `/Identity-H` shape 03-05 established)."""
    return b"".join(cid.to_bytes(2, "big") for cid, _ch in shape_cids(subset, text))


def _shown_bytes(instruction: ParsedInstruction) -> bytes:
    """Every string byte a text-showing instruction actually shows, `Tj` or `TJ` alike --
    the TJ array's string elements concatenated in order, kerns skipped."""
    operand = instruction.operands[0]
    if isinstance(operand, pikepdf.String):
        return bytes(operand)
    return b"".join(bytes(e) for e in operand if isinstance(e, pikepdf.String))


def _shown_kerns(instruction: ParsedInstruction) -> list[float]:
    """A `TJ` array's numeric elements, in order (empty for a bare `Tj`)."""
    operand = instruction.operands[0]
    if isinstance(operand, pikepdf.String):
        return []
    return [float(e) for e in operand if not isinstance(e, pikepdf.String)]


def _font_resource_keys(
    pdf: pikepdf.Pdf, page_index: int, run: RunRecord
) -> set[str]:
    part, xobj_path = _part_key(run)
    _bytes, resources = stream_bytes_and_resources(pdf, page_index, part, xobj_path)
    assert resources is not None
    fonts = resources.get("/Font")
    return set() if fonts is None else {str(key) for key in fonts.keys()}


def _fit_kerns(strategy: str, kerns: list[float]) -> FitResult:
    """A FitResult carrying exactly the kerns under test. Constructed directly rather than
    via `fit_run` on purpose: this task's subject is that the kerns REACH the written
    operand, so the test must own their exact values."""
    return FitResult(10.0, 10.0, 0.0, strategy, kerns)


def _fit_prescribed_trailing(pdf, run, font, codes, kern) -> FitResult:
    # Terminal adjustment is now reconciled against written font widths. Give the
    # high-level rewrite a real measured fit, rather than placeholder 10pt metrics.
    raw, _resources = stream_bytes_and_resources(pdf, run.page, *_part_key(run))
    active = engine.rewrite._active_font_operands(raw, run.glyphs[0].operator_byte_offset)
    assert active is not None
    size = active[1]
    shaped = advance_pt_for_codes(font, codes, size)
    original = shaped - kern / 1000.0 * size
    return FitResult(original, shaped, 0.0, "trailing_kern", [kern])


def _substituted_slot(
    pdf: pikepdf.Pdf, run: RunRecord, first_touched: int, length: int
) -> list[ParsedInstruction]:
    """The `length` instructions now occupying the replaced slot, re-parsed from the bytes
    actually written back -- never the instruction objects handed to the splice."""
    after = _parse_part(pdf, 0, run)
    return after[first_touched : first_touched + length]


def test_editable_substitution_state_always_takes_substituted_branch() -> None:
    """Phase 2's own `editable_substitution` state means "no usable embedded program", so
    there is no original-encoding path to fall back to: the substituted branch is taken
    unconditionally, WITHOUT consulting the edit-time trigger.

    Non-vacuous by construction: the text is `NON_SUBSTITUTING_TEXT`, which
    `test_editable_original_run_substitutes_when_trigger_fires`' own negative control
    proves does NOT fire the trigger on this exact run. So the only thing that can have
    routed this edit through the substituted branch is the verdict state itself.
    """
    runs = _page_runs(IRS_1040, 0)
    target = _only_run(runs, LAST_RUN_ON_PART)

    with pikepdf.open(IRS_1040) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs)
        assert len(touched) == 1
        subset, font_obj = _substitution_target(pdf, NON_SUBSTITUTING_TEXT)

        outcome = rewrite_run(
            pdf,
            0,
            target,
            RunVerdict("editable_substitution"),
            runs,
            NON_SUBSTITUTING_TEXT,
            _fit_no_width_change(),
            (subset, font_obj),
        )
        assert outcome.ok is True, outcome.reason

        slot = _substituted_slot(pdf, target, touched[0], 3)
        assert [str(i.operator) for i in slot] == ["Tf", "TJ", "Tf"]
        assert _shown_bytes(slot[1]) == _expected_cid_bytes(
            subset, NON_SUBSTITUTING_TEXT
        )


def test_editable_original_run_substitutes_when_trigger_fires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """03-RESEARCH.md Pattern 4's headline finding, proven directly: a run whose font IS
    embedded (`editable_original`, `T1-a`) still substitutes once the proposed text
    contains a character its embedded program has no glyph for. That check does not exist
    anywhere in Phase 2 -- Phase 2 classified this font before any replacement text existed.

    Both directions, on the SAME fixture run, so the trigger is proven DISCRIMINATING
    rather than merely always-on: U+20AC substitutes, "AB" does not (it reaches the
    non-substituted resolver instead, here a stand-in, since Task 4 owns that body).
    """
    runs = _page_runs(IRS_1040, 0)
    target = _only_run(runs, LAST_RUN_ON_PART)

    with pikepdf.open(IRS_1040) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs)
        subset, font_obj = _substitution_target(pdf, SUBSTITUTING_TEXT)

        outcome = rewrite_run(
            pdf,
            0,
            target,
            RunVerdict("editable_original"),
            runs,
            SUBSTITUTING_TEXT,
            _fit_no_width_change(),
            (subset, font_obj),
        )
        assert outcome.ok is True, outcome.reason

        slot = _substituted_slot(pdf, target, touched[0], 3)
        assert [str(i.operator) for i in slot] == ["Tf", "TJ", "Tf"]
        assert _shown_bytes(slot[1]) == _expected_cid_bytes(subset, SUBSTITUTING_TEXT)

    # The negative control: same run, same verdict, a character the embedded program DOES
    # have -- the non-substituted branch, proven by the stand-in's own instruction landing.
    with pikepdf.open(IRS_1040) as pdf2:
        before2 = _parse_part(pdf2, 0, target)
        touched2 = _touched(before2, target, runs)
        subset2, font_obj2 = _substitution_target(pdf2, NON_SUBSTITUTING_TEXT)
        _use_stand_in(monkeypatch, _replacement())

        outcome2 = rewrite_run(
            pdf2,
            0,
            target,
            RunVerdict("editable_original"),
            runs,
            NON_SUBSTITUTING_TEXT,
            _fit_no_width_change(),
            (subset2, font_obj2),
        )
        assert outcome2.ok is True, outcome2.reason

        slot2 = _substituted_slot(pdf2, target, touched2[0], 1)
        assert str(slot2[0].operator) == "Tj"
        assert _unparse(slot2[0]) == _unparse(_replacement())


def test_rewrite_whole_run_substitutes_never_half() -> None:
    """FONT-06/D-05's structural guarantee, asserted on the written bytes: a substituted
    run's replacement is ONE text-showing instruction whose every byte came from
    `shape_cids` over the WHOLE `new_text` -- never a mix of original-encoding and
    CID-encoded operands, and never a per-character split.

    Proven three ways over the same slot: exactly one text-showing instruction sits between
    the Tf bracket; its shown bytes equal the whole text's CID bytes exactly (so nothing
    was dropped and nothing foreign was added); and its length is exactly 2 bytes per
    shaped glyph, which a mixed operand could not be.
    """
    text = "Total€ amount"
    runs = _page_runs(IRS_1040, 0)
    target = _only_run(runs, LAST_RUN_ON_PART)

    with pikepdf.open(IRS_1040) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs)
        original_bytes = _shown_bytes(before[touched[0]])
        subset, font_obj = _substitution_target(pdf, text)

        outcome = rewrite_run(
            pdf,
            0,
            target,
            RunVerdict("editable_substitution"),
            runs,
            text,
            _fit_no_width_change(),
            (subset, font_obj),
        )
        assert outcome.ok is True, outcome.reason

        slot = _substituted_slot(pdf, target, touched[0], 3)
        showing = [i for i in slot if str(i.operator) in {"Tj", "TJ", "'", '"'}]
        assert len(showing) == 1

        shaped = shape_cids(subset, text)
        shown = _shown_bytes(showing[0])
        assert shown == _expected_cid_bytes(subset, text)
        assert len(shown) == 2 * len(shaped)
        # Nothing of the original run's own encoded operand survives into the replacement.
        assert original_bytes not in shown


def _rederive(pdf: pikepdf.Pdf, scratch: Path) -> list[RunRecord]:
    """`pdf`'s page-0 runs as its CURRENT (already-edited) in-memory bytes define them --
    `rewrite_instructions`' documented CALLER INVARIANT for a second edit to the same part.
    Serialising to scratch and re-walking is the only route (`RunIndex` opens by path), and
    it keeps the same in-memory `pdf` handle, so an already-embedded font object stays
    valid across both edits, which is the whole point of this test."""
    path = scratch / "rederived.pdf"
    pdf.save(path)
    with RunIndex(path) as idx:
        return [run for run, _verdict in idx.page(0).runs]


def test_substitution_reuses_existing_resource_entry_for_same_font_object() -> None:
    """D-13's consequence at the content-stream layer: the part's `/Resources /Font` gains
    at most ONE entry per distinct embedded font object, however many runs substitute
    through it. The second run reuses the key the first added -- matched by `objgen`, the
    stable indirect-object identity, not by name.

    Two different runs on the SAME part (`irs_form_1040.pdf` page 0, `/Contents[0]`, which
    carries 32 runs), with `all_page_runs` re-derived between them exactly as
    `rewrite_instructions`' caller invariant requires -- so the second edit genuinely
    succeeds rather than refusing `stale_run_index` before the resource path is reached.
    """
    text = "Amount€"
    runs = _page_runs(IRS_1040, 0)
    first = _only_run(runs, ":o221")

    with tempfile.TemporaryDirectory() as scratch:
        with pikepdf.open(IRS_1040) as pdf:
            keys_before = _font_resource_keys(pdf, 0, first)
            subset, font_obj = _substitution_target(pdf, text)

            outcome = rewrite_run(
                pdf,
                0,
                first,
                RunVerdict("editable_substitution"),
                runs,
                text,
                _fit_no_width_change(),
                (subset, font_obj),
            )
            assert outcome.ok is True, outcome.reason
            keys_after_first = _font_resource_keys(pdf, 0, first)
            added = keys_after_first - keys_before
            assert len(added) == 1

            fresh_runs = _rederive(pdf, Path(scratch))
            # The LAST run on the part, selected positionally rather than by text (page 0
            # repeats several labels verbatim, and no display text on it is unique). The
            # first edit landed strictly earlier in the part, so "last" still names the
            # same physical run -- and being last is what keeps D-04's guard trivial here.
            on_part = [
                run for run in fresh_runs if _part_key(run) == _part_key(first)
            ]
            fresh = max(
                on_part, key=lambda r: min(g.operator_byte_offset for g in r.glyphs)
            )

            second = rewrite_run(
                pdf,
                0,
                fresh,
                RunVerdict("editable_substitution"),
                fresh_runs,
                text,
                _fit_no_width_change(),
                (subset, font_obj),
            )
            assert second.ok is True, second.reason
            assert _font_resource_keys(pdf, 0, first) == keys_after_first


def test_tf_bracket_restores_original_resource_after_substituted_run() -> None:
    """Pattern 3's bracket/restore discipline applied to `Tf`, which is the same class of
    hazard as `Tz` (a text-state parameter that persists past `BT`, D-02): a substituting,
    Tz-condensed run writes exactly five instructions, in order -- new `Tf`, condensed
    `Tz`, the CID-encoded showing operator, `Tz` restore, original `Tf` restore.

    Restored to the run's OWN previously-active font resource and size, both read back from
    the part's bytes rather than assumed: `irs_form_1040.pdf` page 0 has `/T1_0 1 Tf` in
    force at this run, and eight distinct font resources on that part, so restoring the
    wrong one would be silently plausible.
    """
    runs = _page_runs(IRS_1040, 0)
    target = _only_run(runs, LAST_RUN_ON_PART)
    fit = _fit_tz()

    with pikepdf.open(IRS_1040) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs)
        subset, font_obj = _substitution_target(pdf, SUBSTITUTING_TEXT)
        keys_before = _font_resource_keys(pdf, 0, target)

        outcome = rewrite_run(
            pdf,
            0,
            target,
            RunVerdict("editable_substitution"),
            runs,
            SUBSTITUTING_TEXT,
            fit,
            (subset, font_obj),
        )
        assert outcome.ok is True, outcome.reason

        slot = _substituted_slot(pdf, target, touched[0], 5)
        assert [str(i.operator) for i in slot] == ["Tf", "Tz", "Tj", "Tz", "Tf"]

        added = _font_resource_keys(pdf, 0, target) - keys_before
        assert len(added) == 1
        new_key = added.pop()
        assert str(slot[0].operands[0]) == new_key
        assert str(slot[4].operands[0]) == "/T1_0"
        assert float(slot[0].operands[1]) == float(slot[4].operands[1]) == 1.0
        assert _shown_bytes(slot[2]) == _expected_cid_bytes(subset, SUBSTITUTING_TEXT)


def test_trailing_kern_strategy_emits_tj_array_with_correct_kern() -> None:
    """The `trailing_kern` rung's correction must reach the document. `fit.py` computes it;
    before this task nothing in `engine/` consumed `FitResult.kerns` at all, so a bare `Tj`
    silently discarded it and the replacement rendered at its unfitted width.

    Asserted on the RE-PARSED content-stream bytes, never on the instruction object handed
    to the splice -- the array has to survive a real unparse/parse round trip to be worth
    anything.
    """
    kern = -12.5
    runs = _page_runs(IRS_1040, 0)
    target = _only_run(runs, LAST_RUN_ON_PART)

    with pikepdf.open(IRS_1040) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs)
        subset, font_obj = _substitution_target(pdf, SUBSTITUTING_TEXT)
        fit = _fit_prescribed_trailing(pdf, target, font_obj,
            [cid for cid, _ in shape_cids(subset, SUBSTITUTING_TEXT)], kern)

        outcome = rewrite_run(
            pdf,
            0,
            target,
            RunVerdict("editable_substitution"),
            runs,
            SUBSTITUTING_TEXT,
            fit,
            (subset, font_obj),
        )
        assert outcome.ok is True, outcome.reason

        showing = _substituted_slot(pdf, target, touched[0], 3)[1]
        assert str(showing.operator) == "TJ"
        assert _shown_kerns(showing) == pytest.approx([kern])
        # The kern TRAILS the whole run's glyphs -- one string, then the correction.
        assert _shown_bytes(showing) == _expected_cid_bytes(subset, SUBSTITUTING_TEXT)


def test_inter_word_kern_strategy_emits_tj_array_with_all_kerns() -> None:
    """The `inter_word_kern` rung distributes its correction across the replacement's own
    inter-word gaps, so EVERY kern must appear, in order, one per space -- the same
    `gap_count == new_text.count(" ")` rule `fit_run` itself computes them from."""
    text = "a b€ c"
    kerns = [-8.25, 4.5]
    assert text.count(" ") == len(kerns)
    runs = _page_runs(IRS_1040, 0)
    target = _only_run(runs, LAST_RUN_ON_PART)

    with pikepdf.open(IRS_1040) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs)
        subset, font_obj = _substitution_target(pdf, text)

        outcome = rewrite_run(
            pdf,
            0,
            target,
            RunVerdict("editable_substitution"),
            runs,
            text,
            _fit_kerns("inter_word_kern", kerns),
            (subset, font_obj),
        )
        assert outcome.ok is True, outcome.reason

        showing = _substituted_slot(pdf, target, touched[0], 3)[1]
        assert str(showing.operator) == "TJ"
        assert _shown_kerns(showing) == pytest.approx(kerns)
        assert len(_shown_kerns(showing)) == text.count(" ")
        # Segmenting the array must not change WHICH glyphs are shown, only where the
        # corrections sit between them.
        assert _shown_bytes(showing) == _expected_cid_bytes(subset, text)


def test_inter_word_kern_handles_leading_trailing_and_consecutive_spaces() -> None:
    """The three space shapes a naive "split on space" builder gets wrong: a LEADING space
    (first segment is empty), a TRAILING space (last segment is empty), and CONSECUTIVE
    spaces (a zero-glyph segment between two kerns). Each must still emit exactly
    `new_text.count(" ")` kerns -- the same count `fit_run` sized its `kerns` list from --
    and must still show every glyph of the whole run."""
    shapes = [" ab", "ab ", "a  b"]
    runs = _page_runs(IRS_1040, 0)
    target = _only_run(runs, LAST_RUN_ON_PART)

    for text in shapes:
        gap_count = text.count(" ")
        kerns = [3.0 * (i + 1) for i in range(gap_count)]
        with pikepdf.open(IRS_1040) as pdf:
            before = _parse_part(pdf, 0, target)
            touched = _touched(before, target, runs)
            subset, font_obj = _substitution_target(pdf, text)

            outcome = rewrite_run(
                pdf,
                0,
                target,
                RunVerdict("editable_substitution"),
                runs,
                text,
                _fit_kerns("inter_word_kern", kerns),
                (subset, font_obj),
            )
            assert outcome.ok is True, (text, outcome.reason)

            showing = _substituted_slot(pdf, target, touched[0], 3)[1]
            assert str(showing.operator) == "TJ", text
            assert _shown_kerns(showing) == pytest.approx(kerns), text
            assert len(_shown_kerns(showing)) == gap_count, text
            assert _shown_bytes(showing) == _expected_cid_bytes(subset, text), text


def test_active_font_scan_never_diverges_from_classify_runs_own_scan() -> None:
    """The two backward `Tf` scans must select the SAME occurrence, or the substituted
    branch brackets and restores a font the run was never classified against -- a
    confidently WRONG font left in force for every later run in the part, which D-04's
    guard cannot catch (it compares position, not font identity).

    The exact divergent input a review found: an earlier revision tightened this module's
    number class so every match would be `float()`-able, and a malformed-but-more-recent
    `/F2 1.2.3 Tf` was then skipped in favour of the older, cleaner `/F1 12 Tf`.
    `classify_run` selects `/F2`. So the requirement is not "agree when both parse" but
    "select the same match, or decline" -- proven here over the whole scan, not just the
    malformed operand: every prefix offset must agree.
    """
    stream = b"BT /F1 12 Tf (a) Tj /F2 1.2.3 Tf (x) Tj /F3 9 Tf (y) Tj ET"

    for offset in range(len(stream) + 1):
        classified = engine.classify_run._find_active_font_name(stream, offset)
        active = engine.rewrite._active_font_operands(stream, offset)
        if active is None:
            # Declining is allowed only when there is no name to agree on, or when the
            # agreed-on match carries an operand that is not a number.
            assert classified is None or b"1.2.3" in stream
        else:
            assert active[0] == classified, offset

    # And the malformed case specifically: decline, never fall back to `/F1`.
    malformed_offset = stream.index(b"(x)")
    assert engine.classify_run._find_active_font_name(stream, malformed_offset) == b"F2"
    assert engine.rewrite._active_font_operands(stream, malformed_offset) is None
    # The clean `Tf` after it resolves normally -- the decline is scoped, not sticky.
    assert engine.rewrite._active_font_operands(stream, stream.index(b"(y)")) == (
        b"F3",
        9.0,
    )


def test_unresolvable_active_font_refuses_by_name_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A declined `Tf` scan must reach the caller as a NAMED `RewriteOutcome`, not as an
    exception. `rewrite_run`'s pre-mutation `try` block has already closed by the time the
    operand resolver runs, so a raise here would escape as an unhandled crash -- and
    EDIT-04's whole posture is that a refusal is always named."""
    runs = _page_runs(IRS_1040, 0)
    target = _only_run(runs, LAST_RUN_ON_PART)
    monkeypatch.setattr(engine.rewrite, "_active_font_operands", lambda *args: None)

    with pikepdf.open(IRS_1040) as pdf:
        before = _contents_bytes(pdf, 0)
        outcome = rewrite_run(
            pdf,
            0,
            target,
            RunVerdict("editable_substitution"),
            runs,
            SUBSTITUTING_TEXT,
            _fit_no_width_change(),
            _substitution_target(pdf, SUBSTITUTING_TEXT),
        )
        assert outcome.ok is False
        assert outcome.reason == "no_active_font_for_substitution"
        assert _contents_bytes(pdf, 0) == before


def test_non_embedded_font_always_substitutes_whatever_the_text() -> None:
    """The task's own biggest behavioural discovery, pinned executably rather than left in
    a docstring: a run whose font is NOT EMBEDDED substitutes for ANY replacement text.

    MEASURED on `govdocs1_000_000011.pdf` page 0, the `:o487` run -- `/ArialMT`, `/TrueType`,
    verdict `TT-a` (`editable_original`, `substitution=False`), and no `/FontFile*` anywhere
    on its descriptor. `encoding_table.glyph_presence` treats an absent program as "cannot
    confirm this glyph" and downgrades to substitution, so `_substitution_triggered` fires
    for plain ASCII the original page already renders.

    That is the intended outcome, not an over-trigger -- D-07 chose Liberation precisely
    because it is metric-compatible with Arial/Times/Courier, so this is the seamless case.
    It is also the single most common real-world shape (unembedded Arial/Times), so 03-07
    must supply a substitution target for it. Without this test, "fixing" the trigger to
    skip a missing program would leave every other test green while D-05 silently regressed
    for exactly that shape.
    """
    runs = _page_runs(GOVDOCS_11, 0)
    target = _only_run(runs, GUARDED_RUN)

    # The fixture property the assertions below rest on, checked rather than assumed.
    with pikepdf.open(GOVDOCS_11) as probe:
        font = engine.rewrite._run_font_object(probe, 0, target)
        assert font is not None
        assert str(font.get("/Subtype")) == "/TrueType"
        descriptor = font.get("/FontDescriptor")
        assert descriptor is None or not any(
            key in descriptor for key in ("/FontFile", "/FontFile2", "/FontFile3")
        )

    for text in ["x", NON_SUBSTITUTING_TEXT, "hello world"]:
        # 1. No target: the substituted branch is demonstrably taken, and refuses by name
        #    rather than silently re-encoding through a font program that is not there.
        with pikepdf.open(GOVDOCS_11) as pdf:
            outcome = rewrite_run(
                pdf,
                0,
                target,
                RunVerdict("editable_original"),
                runs,
                text,
                _fit_no_width_change(),
                None,
            )
            assert outcome.ok is False, text
            assert outcome.reason == "substitution_required_but_no_target_provided", text

    # 2. With a real target: a sibling run on the SAME non-embedded `/ArialMT` substitutes
    #    successfully, CID-encoded end to end. A different run than above by necessity, not
    #    preference: `GUARDED_RUN` is the measured 0.4% case whose follower is
    #    advance-dependent, so a genuinely-narrower CID replacement moves it and D-04
    #    refuses -- correctly, and orthogonally to what this test is about. `:o1117` is the
    #    last run on its own part, so the guard is trivially satisfied.
    text = NON_SUBSTITUTING_TEXT
    target = _only_run(runs, ":o1117")
    with pikepdf.open(GOVDOCS_11) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs)
        subset, font_obj = _substitution_target(pdf, text)

        outcome = rewrite_run(
            pdf,
            0,
            target,
            RunVerdict("editable_original"),
            runs,
            text,
            _fit_no_width_change(),
            (subset, font_obj),
        )
        assert outcome.ok is True, outcome.reason

        slot = _substituted_slot(pdf, target, touched[0], 3)
        assert [str(i.operator) for i in slot] == ["Tf", "TJ", "Tf"]
        assert _shown_bytes(slot[1]) == _expected_cid_bytes(subset, text)


# --------------------------------------------------------------------------------------
# Task 4: the NON-substituted branch -- the run's own original encoding, content-stream
# injection prevention (T-03-06-01), and the two Task-1 regressions re-run end to end
# --------------------------------------------------------------------------------------
#
# `LAST_RUN_ON_PART` again (`irs_form_1040.pdf` page 0, `:o9116`): its active font is
# `/T1_0`, an EMBEDDED Type1 (`T1-a`, `editable_original`), and MEASURED against its own
# embedded program, plain ASCII fires NO substitution trigger -- so it is the fixture that
# actually reaches this branch. Being the part's last run keeps D-04's guard trivial, which
# matters here because re-encoding into the original font legitimately changes the run's
# width (fitting that width is `engine/fit.py`'s job, not this branch's).
#
# MEASURED on that font's `/Encoding`: `A`->65, `B`->66, space->32, `(`->40, `)`->41,
# `\`->92 -- i.e. ASCII-transparent for every character these tests use, which is what
# lets the expected operand bytes be stated as plain ASCII below.
NON_SUBSTITUTED_TEXT = "AB"

# A character with an Adobe Glyph List name whose name has NO code in that font's own
# `/Encoding` (`alpha`, 213 codes, no Greek), and one with no AGL name at all (U+6F22).
# Together they cover both of `run_needs_substitution`'s own check-1 sub-cases.
UNMAPPABLE_TEXTS = ("α", "漢")


def _original_codes(
    pdf: pikepdf.Pdf, run: RunRecord, text: str, page_index: int = 0
) -> bytes:
    """What `text` must encode to in `run`'s OWN font: each character's single-byte code
    from that font's `/Encoding`, derived here through `engine.fonts`' own public
    `reverse_encoding_map` rather than through anything in `engine/rewrite.py`."""
    font = engine.rewrite._run_font_object(pdf, page_index, run)
    assert font is not None
    reverse = reverse_encoding_map(font)
    return bytes(reverse[UV2AGL[ord(ch)]] for ch in text)


def _font_dict_digest(pdf: pikepdf.Pdf, page_index: int, run: RunRecord) -> bytes:
    """The part's own `/Resources /Font` dictionary, serialised -- the before/after evidence
    that the non-substituted path added no resource entry and repointed none."""
    part, xobj_path = _part_key(run)
    _bytes, resources = stream_bytes_and_resources(pdf, page_index, part, xobj_path)
    assert resources is not None
    return bytes(resources["/Font"].unparse())


def _fit_plain() -> FitResult:
    """A FitResult with NO kerns -- the shape that must produce a bare `Tj`."""
    return FitResult(10.0, 10.0, 0.0, "trailing_kern", [])


def test_non_substituted_run_keeps_original_font_resource() -> None:
    """The whole point of this branch: the replacement is written in the run's OWN font, so
    nothing about the font resource may move. Exactly one instruction lands in the slot (no
    `Tf` bracket, unlike the substituted branch's five-instruction worst case), and the
    part's `/Resources /Font` dictionary is byte-identical before and after.

    The operand itself is asserted too, in the run's own encoding -- a test that only
    checked the resource dict would pass just as happily on an empty replacement.
    """
    runs = _page_runs(IRS_1040, 0)
    target = _only_run(runs, LAST_RUN_ON_PART)

    with pikepdf.open(IRS_1040) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs)
        assert len(touched) == 1
        fonts_before = _font_dict_digest(pdf, 0, target)

        outcome = rewrite_run(
            pdf, 0, target, _verdict(), runs, NON_SUBSTITUTED_TEXT, _fit_plain()
        )
        assert outcome.ok is True, outcome.reason

        after = _parse_part(pdf, 0, target)
        assert len(after) == len(before)
        slot = after[touched[0]]
        assert str(slot.operator) == "Tj"
        assert _shown_bytes(slot) == _original_codes(pdf, target, NON_SUBSTITUTED_TEXT)
        # The measured ASCII-transparency of this font's encoding, pinned executably.
        assert _shown_bytes(slot) == NON_SUBSTITUTED_TEXT.encode("ascii")
        assert _font_dict_digest(pdf, 0, target) == fonts_before
        # No `Tf` anywhere near the replacement -- the substituted branch's bracket must
        # not appear on a path that never changes the active font.
        assert "Tf" not in {str(i.operator) for i in after[touched[0] : touched[0] + 2]}


def test_character_missing_from_original_encoding_refuses_by_name() -> None:
    """The defensive negative case: a character the run's own `/Encoding` has no code for
    must come back as a NAMED `RewriteOutcome`, never a `KeyError` escaping the resolver.

    `run_needs_substitution` would normally route such a character to the substituted
    branch before this function is reached (Task 3's Pattern-4 wiring), so this is
    unreachable in normal operation -- which is exactly why it is driven by a DIRECT call
    here rather than through `rewrite_run`.
    """
    runs = _page_runs(IRS_1040, 0)
    target = _only_run(runs, LAST_RUN_ON_PART)

    with pikepdf.open(IRS_1040) as pdf:
        for text in UNMAPPABLE_TEXTS:
            result = engine.rewrite._resolve_non_substituted_operand(
                pdf, 0, target, runs, text, _fit_plain()
            )
            assert isinstance(result, engine.rewrite.RewriteOutcome), text
            assert result.ok is False, text
            assert result.reason == "character_has_no_code_in_original_encoding", text


def test_content_stream_injection_prevented_via_pikepdf_operand_types() -> None:
    """T-03-06-01: replacement text that is hostile PDF SYNTAX -- an unbalanced `(`, a bare
    `)`, a literal backslash -- must not be able to break out of the string literal it is
    written into. Structurally prevented by construction (every operand is a
    `pikepdf.String` unparsed by `pikepdf.unparse_content_stream`, never assembled by
    formatting), and proven here rather than argued: the part is re-parsed from the bytes
    actually written, and must come back as ONE `Tj` whose operand bytes are exactly the
    original codes.

    A breakout would show up as a different instruction COUNT (extra operators parsed out
    of the escaped text), so the count is asserted too, not just the operand.

    MEASURED on this fixture font: `(` and `)` are both present in its embedded program, so
    parenthesis cases route down the non-substituted branch end to end. A literal BACKSLASH
    is not (a subset font of a tax form has no use for one), so `run_needs_substitution`
    legitimately sends it to the substituted branch instead -- correct behaviour that would
    make an end-to-end assertion vacuous. The backslash cases are therefore driven at the
    resolver and round-tripped through `unparse_content_stream`/`parse_content_stream`
    directly, which is the exact layer the threat row names.
    """
    runs = _page_runs(IRS_1040, 0)
    target = _only_run(runs, LAST_RUN_ON_PART)

    for text in ["A)B", "A(B", "((A)", "A) Tj (B", ") 0 0 Td ("]:
        with pikepdf.open(IRS_1040) as pdf:
            before = _parse_part(pdf, 0, target)
            touched = _touched(before, target, runs)
            expected = _original_codes(pdf, target, text)

            outcome = rewrite_run(pdf, 0, target, _verdict(), runs, text, _fit_plain())
            assert outcome.ok is True, (text, outcome.reason)

            after = _parse_part(pdf, 0, target)
            assert len(after) == len(before), text
            slot = after[touched[0]]
            assert str(slot.operator) == "Tj", text
            assert _shown_bytes(slot) == expected, text
            assert _shown_bytes(slot) == text.encode("ascii"), text

    # The backslash cases, at the resolver plus a real unparse/parse round trip.
    with pikepdf.open(IRS_1040) as pdf:
        for text in ["A\\B", ")\\(", "\\) Tj ("]:
            resolved = engine.rewrite._resolve_non_substituted_operand(
                pdf, 0, target, runs, text, _fit_plain()
            )
            assert isinstance(resolved, pikepdf.ContentStreamInstruction), text
            reparsed = pikepdf.parse_content_stream(
                pdf.make_stream(pikepdf.unparse_content_stream([resolved]))
            )
            assert len(reparsed) == 1, text
            assert str(reparsed[0].operator) == "Tj", text
            assert _shown_bytes(reparsed[0]) == _original_codes(pdf, target, text), text


def test_no_raw_string_formatting_builds_content_stream_bytes() -> None:
    """T-03-06-01's static half, enforced in CI rather than only at review time: no
    f-string and no `+`-concatenation anywhere in `engine/rewrite.py` may assemble anything
    from `new_text`. Checked over the module's own AST -- not a text grep, which would trip
    over prose in docstrings and miss a multi-line expression.

    The rule is deliberately blunt: `new_text` reaches the content stream ONLY by being
    mapped character-by-character to codes and handed to `pikepdf.String`, so any f-string
    or concatenation touching it is, by construction, the failure this row exists to
    prevent.
    """
    module = ast.parse((REPO_ROOT / "engine" / "rewrite.py").read_text())

    def mentions_new_text(node: ast.AST) -> bool:
        return any(
            isinstance(child, ast.Name) and child.id == "new_text"
            for child in ast.walk(node)
        )

    offenders = [
        f"{type(node).__name__} at line {node.lineno}"
        for node in ast.walk(module)
        if (
            isinstance(node, ast.JoinedStr)
            or (isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)))
        )
        and mentions_new_text(node)
    ]
    assert offenders == []

    # And the positive half: the module does build its operands through pikepdf's own
    # constructors, so the check above is guarding a real mechanism rather than an
    # accidentally-absent one.
    source = (REPO_ROOT / "engine" / "rewrite.py").read_text()
    assert "pikepdf.String(" in source
    assert "pikepdf.unparse_content_stream(" in source


def test_non_substituted_operand_is_unreachable_for_type0_fonts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The boundary 03-04's amendment establishes, proven at the `rewrite_run` DISPATCH
    level rather than by cross-reading two plans: a Type0/CIDFontType2 run never reaches
    `_resolve_non_substituted_operand` at all, so that function's single-byte
    `reverse_encoding_map` construction can never run against a CID-keyed font (whose
    `/Encoding` is `/Identity-H`, a 2-byte codespace `encoding_map` would silently
    mis-answer with a StandardEncoding table).

    Driven with `new_text` that IS plain-ASCII-mappable -- exactly the text a wrongly
    permissive simple-font check would happily encode -- and asserted by a CALL SPY proving
    zero invocations, never by the output merely "looking right".

    The Type0 font installed as the run's active resource is a REAL one, built by
    `engine.fonts.embed_type0_font` through the same public pipeline every other Task-3
    test uses, rather than a hand-built dictionary: it is strictly closer to what 03-07
    will actually put in a document, and its `C-` branch is asserted rather than assumed.
    """
    calls: list[str] = []

    def _spy(*args: object, **kwargs: object) -> object:
        calls.append("called")
        raise AssertionError("_resolve_non_substituted_operand must not run for Type0")

    monkeypatch.setattr(engine.rewrite, "_resolve_non_substituted_operand", _spy)

    runs = _page_runs(IRS_1040, 0)
    target = _only_run(runs, LAST_RUN_ON_PART)

    with pikepdf.open(IRS_1040) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs)
        subset, font_obj = _substitution_target(pdf, NON_SUBSTITUTED_TEXT)

        # Make the run's OWN active font a Type0/CIDFontType2 one.
        part, xobj_path = _part_key(target)
        _bytes, resources = stream_bytes_and_resources(pdf, 0, part, xobj_path)
        assert resources is not None
        resources["/Font"]["/T1_0"] = font_obj

        active = engine.rewrite._run_font_object(pdf, 0, target)
        assert active is not None
        assert str(active.get("/Subtype")) == "/Type0"
        assert resolve_font(active).branch_id.startswith("C-")

        outcome = rewrite_run(
            pdf,
            0,
            target,
            RunVerdict("editable_original"),
            runs,
            NON_SUBSTITUTED_TEXT,
            _fit_plain(),
            (subset, font_obj),
        )
        assert outcome.ok is True, outcome.reason
        assert calls == []

        slot = _substituted_slot(pdf, target, touched[0], 3)
        assert [str(i.operator) for i in slot] == ["Tf", "Tj", "Tf"]
        assert _shown_bytes(slot[1]) == _expected_cid_bytes(subset, NON_SUBSTITUTED_TEXT)


def test_non_substituted_trailing_kern_emits_tj_array() -> None:
    """The `trailing_kern` rung's correction must reach the document down THIS branch too --
    the non-substitution path gets no pass on width correctness just because it does not
    call `shape_cids`. One string, then the kern, asserted on the re-parsed bytes."""
    kern = -9.75
    runs = _page_runs(IRS_1040, 0)
    target = _only_run(runs, LAST_RUN_ON_PART)

    with pikepdf.open(IRS_1040) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs)
        font = engine.rewrite._run_font_object(pdf, 0, target)
        fit = _fit_prescribed_trailing(pdf, target, font,
                                      list(_original_codes(pdf, target, NON_SUBSTITUTED_TEXT)), kern)

        outcome = rewrite_run(
            pdf,
            0,
            target,
            _verdict(),
            runs,
            NON_SUBSTITUTED_TEXT,
            fit,
        )
        assert outcome.ok is True, outcome.reason

        slot = _parse_part(pdf, 0, target)[touched[0]]
        assert str(slot.operator) == "TJ"
        assert _shown_kerns(slot) == pytest.approx([kern])
        assert _shown_bytes(slot) == _original_codes(pdf, target, NON_SUBSTITUTED_TEXT)


def test_non_substituted_inter_word_kern_handles_leading_trailing_and_consecutive_spaces() -> (
    None
):
    """The same three space shapes Task 3's own edge-case test covers, over single-byte
    codes instead of CIDs: a LEADING space (empty first segment), a TRAILING space (empty
    last segment) and CONSECUTIVE spaces (an empty segment between two kerns). Each must
    emit exactly `new_text.count(" ")` kerns -- the count `fit_run` sized its list from --
    and must still show every code of the whole run, in order."""
    runs = _page_runs(IRS_1040, 0)
    target = _only_run(runs, LAST_RUN_ON_PART)

    for text in [" AB", "AB ", "A  B", "A B C"]:
        gap_count = text.count(" ")
        kerns = [2.5 * (i + 1) for i in range(gap_count)]
        with pikepdf.open(IRS_1040) as pdf:
            before = _parse_part(pdf, 0, target)
            touched = _touched(before, target, runs)

            outcome = rewrite_run(
                pdf,
                0,
                target,
                _verdict(),
                runs,
                text,
                _fit_kerns("inter_word_kern", kerns),
            )
            assert outcome.ok is True, (text, outcome.reason)

            slot = _parse_part(pdf, 0, target)[touched[0]]
            assert str(slot.operator) == "TJ", text
            assert _shown_kerns(slot) == pytest.approx(kerns), text
            assert len(_shown_kerns(slot)) == gap_count, text
            assert _shown_bytes(slot) == _original_codes(pdf, target, text), text


def test_multi_operator_run_consolidates_to_one_instruction_via_rewrite_run() -> None:
    """Pitfall 1's own fixture again (`irs_form_1040.pdf` page 0, `:o1391`, 62 touched
    instructions), but composed through the FULL `rewrite_run` -- dispatch, real
    original-encoding operand, Tz bracket decision and D-04 guard included -- rather than
    through the `rewrite_instructions` primitive Task 1 tested in isolation. 62 operators
    still become exactly one, and the survivor is the run's own re-encoded text.

    MEASURED premises, checked rather than assumed: this run's font is an embedded Type1
    whose program has glyphs for the replacement text (so the non-substituted branch is
    genuinely taken), and no other run shares any of its 62 operators.
    """
    runs = _page_runs(IRS_1040, 0)
    target = _only_run(runs, ":o1391")

    with pikepdf.open(IRS_1040) as pdf:
        before = _parse_part(pdf, 0, target)
        touched = _touched(before, target, runs)
        assert len(touched) == 62
        fonts_before = _font_dict_digest(pdf, 0, target)

        outcome = rewrite_run(
            pdf, 0, target, _verdict(), runs, NON_SUBSTITUTED_TEXT, _fit_plain()
        )
        assert outcome.ok is True, outcome.reason

        after = _parse_part(pdf, 0, target)
        assert len(after) == len(before) - 61
        slot = after[touched[0]]
        assert str(slot.operator) == "Tj"
        assert _shown_bytes(slot) == _original_codes(pdf, target, NON_SUBSTITUTED_TEXT)
        # The non-substituted branch was the one taken, not a substitution that happened
        # to consolidate: no font resource was added.
        assert _font_dict_digest(pdf, 0, target) == fonts_before


def test_foreign_interleaved_operator_survives_unedited_via_rewrite_run() -> None:
    """Pitfall 2's page-4 `irs_form_w4.pdf` case, composed through the FULL `rewrite_run`:
    another run's operator sitting strictly between the target's first and last is still
    never referenced, so it survives byte-for-byte at its correct shifted index.

    Page 0's own Pitfall-2 pair is deliberately not re-run here: it sits on a
    part-boundary-truncated part, which `rewrite_instructions` already refuses by name
    (`test_foreign_interleaved_operator_survives_unedited` pins that half), and the
    refusal happens below `rewrite_run` unchanged.
    """
    page_index = 4
    runs = _page_runs(IRS_W4, page_index)
    target, foreign = _find_noncontiguous_pair(runs)

    with pikepdf.open(IRS_W4) as pdf:
        before = _parse_part(pdf, page_index, target)
        touched = _touched(before, target, runs)
        foreign_touched = _touched(before, foreign, runs)
        interleaved = [i for i in foreign_touched if touched[0] < i < touched[-1]]
        assert interleaved, "fixture no longer reproduces Pitfall 2's interleaving"
        foreign_index = interleaved[0]
        expected = _unparse(before[foreign_index])

        font = engine.rewrite._run_font_object(pdf, page_index, target)
        assert font is not None
        text = NON_SUBSTITUTED_TEXT

        outcome = rewrite_run(
            pdf, page_index, target, _verdict(), runs, text, _fit_plain()
        )
        assert outcome.ok is True, outcome.reason

        expected_index = foreign_index - len([t for t in touched[1:] if t < foreign_index])
        after = _parse_part(pdf, page_index, target)
        assert len(after) == len(before) - (len(touched) - 1)
        assert _unparse(after[expected_index]) == expected
        assert _shown_bytes(after[touched[0]]) == _original_codes(
            pdf, target, text, page_index
        )
