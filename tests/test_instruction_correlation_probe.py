"""Tests for spike/instruction_correlation_probe.py (plan 03-02 Task 1).

Four named cases from task-1-brief.md's `<behavior>` block:
1. A single-operator baseline on `spike/fixtures/tj_refit_sample.pdf` page 0 (picked
   programmatically -- the exact run identity is not load-bearing for this case).
2. `irs_form_1040.pdf` page 0, the `:o1391` run -- RESEARCH.md's own measured
   62-operator, 63-glyph case.
3-4. `irs_form_w4.pdf` pages 0 and 4 -- non-contiguous runs (a foreign run's own
   operator sits between the target run's first and last operator), picked
   programmatically by the same detection this session used to find them (see
   RESEARCH.md Pitfall 2's own methodology).

No test asserts on decoded glyph text content -- only counts, indices, and booleans,
per this project's no-document-content convention.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.index import RunIndex  # noqa: E402
from engine.run_id import decode_run_id  # noqa: E402
from spike.instruction_correlation_probe import correlate_run  # noqa: E402

TJ_REFIT_SAMPLE = REPO_ROOT / "spike" / "fixtures" / "tj_refit_sample.pdf"
IRS_1040 = REPO_ROOT / "corpus" / "public" / "irs_form_1040.pdf"
IRS_W4 = REPO_ROOT / "corpus" / "public" / "irs_form_w4.pdf"


def _find_single_operator_editable_run(pdf_path: Path, page_index: int) -> str:
    """Programmatically pick any editable run on `page_index` whose own glyphs span
    exactly one distinct operator byte offset -- the baseline single-operator case.
    The exact run identity is not load-bearing (task-1-brief.md)."""
    with RunIndex(pdf_path) as idx:
        page = idx.page(page_index)
        for run, verdict in page.runs:
            if verdict.state == "not_editable":
                continue
            offsets = {g.operator_byte_offset for g in run.glyphs}
            if len(offsets) == 1:
                return run.run_id
    raise AssertionError(f"no single-operator editable run found on page {page_index}")


def _find_noncontiguous_run(pdf_path: Path, page_index: int) -> str:
    """Programmatically pick a run on `page_index` whose own operators are NOT
    stream-contiguous -- some OTHER run sharing the same part has an operator strictly
    between this run's own first and last operator byte offset. Same detection
    methodology as RESEARCH.md Pitfall 2."""
    with RunIndex(pdf_path) as idx:
        page = idx.page(page_index)
        groups: dict[tuple[tuple[int, ...], int], list] = {}
        for run, verdict in page.runs:
            parts = decode_run_id(run.run_id)
            key = (parts["xobj_path"], parts["part"])
            groups.setdefault(key, []).append(run)

        for runs in groups.values():
            if len(runs) < 2:
                continue
            for run in runs:
                offsets = sorted({g.operator_byte_offset for g in run.glyphs})
                if len(offsets) < 2:
                    continue
                lo, hi = offsets[0], offsets[-1]
                for other in runs:
                    if other is run:
                        continue
                    if any(lo < g.operator_byte_offset < hi for g in other.glyphs):
                        return run.run_id
    raise AssertionError(f"no non-contiguous run found on page {page_index}")


def test_single_operator_baseline() -> None:
    run_id = _find_single_operator_editable_run(TJ_REFIT_SAMPLE, 0)
    result = correlate_run(TJ_REFIT_SAMPLE, 0, run_id)
    assert result.ok is True
    assert len(result.touched_indices) == 1


def test_irs_1040_o1391_case_is_exactly_62_instructions() -> None:
    result = correlate_run(IRS_1040, 0, ":o1391")
    assert result.ok is True
    assert len(result.touched_indices) == 62


def test_irs_w4_page0_noncontiguous_run_does_not_touch_foreign_indices() -> None:
    """Both `correlate_run` calls below re-parse the SAME isolated /Contents array
    element in isolation, which reproduces a known artifact (see
    spike/instruction_correlation_probe.py's module docstring, "What is NOT proven
    here"): the array splits a token across parts, so pikepdf's own
    `parse_content_stream` hits the truncated tail and emits `UserWarning: Unexpected
    end of stream`. Neither touched run's own operators are near that truncation
    point (verified: both resolve `ok is True` with disjoint indices), but the warning
    is captured explicitly here rather than left to print silently -- escalating it to
    an error (`pytest -W error::UserWarning`) surfaces a `SystemError` from pikepdf's
    C-extension boundary, which is a stronger signal than a print."""
    run_id = _find_noncontiguous_run(IRS_W4, 0)

    with RunIndex(IRS_W4) as idx:
        page = idx.page(0)
        target = next(r for r, _v in page.runs if r.run_id == run_id)
        target_parts = decode_run_id(target.run_id)
        target_key = (target_parts["xobj_path"], target_parts["part"])
        offsets = sorted({g.operator_byte_offset for g in target.glyphs})
        lo, hi = offsets[0], offsets[-1]

        foreign_run = next(
            r
            for r, _v in page.runs
            if r.run_id != run_id
            and decode_run_id(r.run_id)["xobj_path"] == target_key[0]
            and decode_run_id(r.run_id)["part"] == target_key[1]
            and any(lo < g.operator_byte_offset < hi for g in r.glyphs)
        )
        with pytest.warns(UserWarning, match="Unexpected end of stream"):
            foreign_result = correlate_run(IRS_W4, 0, foreign_run.run_id)

    with pytest.warns(UserWarning, match="Unexpected end of stream"):
        result = correlate_run(IRS_W4, 0, run_id)
    assert result.ok is True
    assert foreign_result.ok is True
    assert set(foreign_result.touched_indices).isdisjoint(result.touched_indices)


def test_irs_w4_page4_noncontiguous_run_does_not_touch_foreign_indices() -> None:
    run_id = _find_noncontiguous_run(IRS_W4, 4)

    with RunIndex(IRS_W4) as idx:
        page = idx.page(4)
        target = next(r for r, _v in page.runs if r.run_id == run_id)
        target_parts = decode_run_id(target.run_id)
        target_key = (target_parts["xobj_path"], target_parts["part"])
        offsets = sorted({g.operator_byte_offset for g in target.glyphs})
        lo, hi = offsets[0], offsets[-1]

        foreign_run = next(
            r
            for r, _v in page.runs
            if r.run_id != run_id
            and decode_run_id(r.run_id)["xobj_path"] == target_key[0]
            and decode_run_id(r.run_id)["part"] == target_key[1]
            and any(lo < g.operator_byte_offset < hi for g in r.glyphs)
        )
        foreign_result = correlate_run(IRS_W4, 4, foreign_run.run_id)

    result = correlate_run(IRS_W4, 4, run_id)
    assert result.ok is True
    assert foreign_result.ok is True
    assert set(foreign_result.touched_indices).isdisjoint(result.touched_indices)
