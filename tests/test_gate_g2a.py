"""Gate G2a: the targeted confined-diff proof, end to end on one real edit.

This test IS the gate. It drives the real pipeline built across 03-01..03-07 --
`classify_document` -> `parse_recipe` -> `apply_recipe` (`plan_recipe` + fit ladder +
`rewrite_run`) -- against a real fixture, one real single-instruction run, and then asserts
all six of G2a's roadmap clauses against that single edit:

1. the structural diff is CONFINED: exactly one instruction changed in the ONE
   content-stream part the edit touched (`harness/structural_diff.py`, the fix for
   03-RESEARCH.md's Pitfall 3 -- a whole-file `qpdf --qdf` diff measures 13,689 lines for a
   one-word change and proves nothing);
2. the refit width delta is sub-0.5pt;
3. the following run's text-matrix position is unchanged;
4. `qpdf --check` is clean on the output;
5. per engine, the rendered page is pixel-identical outside the edited run's own box;
6. the three engines still agree with each other on the rewritten output.

Scope note -- this is G2a, NOT G2b: the edit is deliberately chosen so no new glyph is
needed (`new_text` is built from the characters the run already shows), and the resolved
op's own `substitution_key is None` is asserted as a PRECONDITION. A run whose font forces
substitution is skipped, never accommodated by weakening an assertion; the substitution
pipeline is 03-09/G2b's gate, not this one.

No assertion message here embeds `new_text`, `display_text`, or any decoded document
content -- only counts, booleans, coordinates, engine labels and fixture paths (the standing
convention T-02-04, as in tests/test_roundtrip.py).
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pikepdf
import pytest

from engine.classify_run import DocumentClassification, classify_document, stream_bytes_and_resources
from engine.recipe import apply_recipe, parse_recipe, plan_recipe
from engine.records import RunRecord
from engine.run_id import decode_run_id

REPO_ROOT = Path(__file__).parent.parent

# harness/ has no __init__.py -- sibling-module import, matching tests/test_roundtrip.py's
# and tests/test_structural_diff.py's own established convention.
sys.path.insert(0, str(REPO_ROOT / "harness"))
from masked_diff import masked_pixel_diff  # noqa: E402
from render_diff import RENDER_DPI, render_all  # noqa: E402
from run_corpus_harness import _cross_engine_pair_ok  # noqa: E402
from structural_diff import confined_instruction_diff  # noqa: E402

# Generous fixed padding standing in for real font ascent/descent, since clause 1's
# structural diff is the precise confinement proof and this mask is only a coarse visual
# sanity check. ponytail: fixed padding, upgrade to real font-program metrics if a corpus
# run ever produces a false pass (a mask so large it hides a genuine regression).
MASK_VERTICAL_PAD_PT = 14.0
# Same spirit, one axis over: a small fixed margin against normal renderer/font-hinting
# variance. MEASURED without it, the three engines' real differing pixel columns landed
# exactly ON both boundary columns (poppler: 1 px on the left edge, 3 px on the right), so a
# renderer version bump or a different candidate run would have flipped this gate to a false
# failure. 3pt keeps the whole mask under 0.3% of the page, so clause 5's confinement proof
# is unweakened.
MASK_HORIZONTAL_PAD_PT = 3.0
POSITION_EPSILON_PT = 1e-6
WIDTH_DELTA_TOLERANCE_PT = 0.5
# Matches harness/render_diff.py's SUBPROCESS_TIMEOUT_SECONDS and
# harness/run_corpus_harness.py's STRUCTURAL_TIMEOUT_SECONDS.
QPDF_CHECK_TIMEOUT_SECONDS = 30

# Fixture preference order. `spike/fixtures/tj_refit_sample.pdf` is the exact fixture
# 03-RESEARCH.md measured the 13,689-line whole-file diff against, so it is tried FIRST --
# but every font it embeds is Type1/CFF, which `engine.fit.load_font`'s `TTFont` cannot
# parse, so today every candidate run in it resolves `"resolution_failed"` and the corpus
# document below is what actually drives this gate. The probe is kept (rather than the
# corpus document hardcoded) so this test moves back to the research fixture by itself the
# day the fit ladder learns to load a Type1 program.
_CANDIDATE_FIXTURES = (
    REPO_ROOT / "spike" / "fixtures" / "tj_refit_sample.pdf",
    REPO_ROOT / "corpus" / "public" / "govdocs1_000_000011.pdf",
)

# One `plan_recipe` call resolves this many candidate runs at once (it writes nothing), so
# the whole search costs ONE classification per fixture, not one per candidate.
MAX_CANDIDATE_PROBES = 40

_ENGINE_LABELS = ("pdfium", "poppler", "mupdf")


def _edited_run_pixel_mask(run: RunRecord, cropbox_height_pt: float) -> tuple[int, int, int, int]:
    """The edited run's own bounding box in PNG pixel coordinates, for `masked_pixel_diff`.

    Glyph `x`/`y`/`advance` are DEVICE space (playa's, `Tm` already applied -- see
    `engine/records.py`: they are `matrix[4]`/`matrix[5]` of the glyph's own text-rendering
    matrix), and playa's device space is already y-DOWN from the top-left corner, the same
    orientation the PNG has. So this scales straight through with no y flip.

    MEASURED, because this plan's brief prescribed a `cropbox_height_pt - y` flip and that is
    wrong for playa's coordinates: on `govdocs1_000_000011.pdf` page 0 the edited run's
    glyphs sit at y=98.22pt and the three engines' real pixel differences land at rows
    189-206 (98.22 * 150/72 = 204.6, the baseline), while the flipped formula produced rows
    1416-1474 -- a mask that covered no changed pixel at all and made the clause vacuous.
    `cropbox_height_pt` is kept in the signature since a future page whose CropBox origin is
    not (0, 0) will need it; it is deliberately unused for the y axis today.

    Every edge rounds OUTWARD -- `floor` on left/top, `ceil` on right/bottom -- so the mask
    always fully contains the box it is built from. `int()` truncates toward zero, which is
    the wrong direction for the right/bottom edges (it shrinks the mask inward) and only
    happens to be right for left/top while the coordinates are positive.

    Both axes carry a fixed pad (`MASK_VERTICAL_PAD_PT`, `MASK_HORIZONTAL_PAD_PT`) -- see
    those constants for what each stands in for and what was measured without them.

    `scale` is recomputed locally rather than importing `render_diff._SCALE` (private to that
    module -- 03-07's established reimplement-small-cross-module-logic-locally precedent).
    """
    left_pt = min(g.x for g in run.glyphs) - MASK_HORIZONTAL_PAD_PT
    right_pt = max(g.x + g.advance[0] for g in run.glyphs) + MASK_HORIZONTAL_PAD_PT
    top_pt = min(g.y for g in run.glyphs) - MASK_VERTICAL_PAD_PT
    bottom_pt = max(g.y for g in run.glyphs) + MASK_VERTICAL_PAD_PT

    scale = RENDER_DPI / 72
    return (
        math.floor(left_pt * scale),
        math.floor(top_pt * scale),
        math.ceil(right_pt * scale),
        math.ceil(bottom_pt * scale),
    )


def _new_text_for(display_text: str) -> str | None:
    """Replacement text built from the SAME characters the run already shows, so no glyph
    the embedded program lacks is ever required (G2a's no-substitution scope). Reversed;
    first/last swapped when reversal is a no-op; `None` when neither changes anything."""
    reversed_text = display_text[::-1]
    if reversed_text != display_text:
        return reversed_text
    if len(display_text) < 2:
        return None
    swapped = display_text[-1] + display_text[1:-1] + display_text[0]
    return swapped if swapped != display_text else None


def _page_runs(classification: DocumentClassification) -> dict[int, list[RunRecord]]:
    """Every run, grouped by page, in classification order -- the same grouping and order
    `plan_recipe` builds its `ResolvedOp.all_page_runs` from."""
    grouped: dict[int, list[RunRecord]] = {}
    for run, _verdict in classification.runs:
        grouped.setdefault(run.page, []).append(run)
    return grouped


def _instruction_key(run: RunRecord) -> tuple[int, int, tuple[int, ...], int]:
    """The ONE text-showing instruction this run lives in: `(page, part, xobj_path,
    operator byte offset)` -- which is exactly what its run ID addresses. Only meaningful
    for a run whose glyphs all share one operator offset."""
    parts = decode_run_id(run.run_id)
    return (run.page, parts["part"], parts["xobj_path"], run.glyphs[0].operator_byte_offset)


def _select_edit() -> tuple[Path, RunRecord, str]:
    """The first (fixture, run, new_text) satisfying EVERY G2a precondition: the run is
    `editable_original`, lives in exactly ONE content-stream instruction that no OTHER run
    shares, has a following run on its own page, and resolves with `substitution_key is
    None`."""
    probed = 0
    for fixture in _CANDIDATE_FIXTURES:
        if not fixture.is_file():
            continue
        classification = classify_document(fixture)
        grouped = _page_runs(classification)

        # One instruction can carry several runs (`rewrite_run` refuses those by name,
        # `"operator_shared_by_multiple_runs"`), and such runs share a run ID -- which
        # `plan_recipe` refuses whole as `"duplicate_run_id_in_recipe"`. Both are correct
        # behaviour and neither is what this gate is measuring, so a shared instruction
        # disqualifies a candidate before it is ever probed.
        shared: dict[tuple[int, int, tuple[int, ...], int], int] = {}
        for run, _verdict in classification.runs:
            if run.glyphs:
                key = _instruction_key(run)
                shared[key] = shared.get(key, 0) + 1

        candidates: list[RunRecord] = []
        for run, verdict in classification.runs:
            if verdict.state != "editable_original":
                continue
            if len({g.operator_byte_offset for g in run.glyphs}) != 1:
                continue
            if shared[_instruction_key(run)] != 1:
                continue
            page = grouped[run.page]
            # By run ID, never `list.index(run)`: `RunRecord` is a plain (eq-by-field)
            # dataclass, so an identical earlier run would return the wrong position.
            position = next(i for i, r in enumerate(page) if r.run_id == run.run_id)
            if position + 1 >= len(page):
                continue
            if _new_text_for(run.display_text) is None:
                continue
            candidates.append(run)
            if len(candidates) >= MAX_CANDIDATE_PROBES:
                break

        if not candidates:
            continue

        by_run_id = {run.run_id: run for run in candidates}
        probe = parse_recipe(
            json.dumps(
                [
                    {"run_id": run.run_id, "new_text": _new_text_for(run.display_text)}
                    for run in candidates
                ]
            ).encode()
        )
        # Writes nothing: `plan_recipe` is D-03's dry run. Its report is per-op, so one
        # call classifies once and resolves every candidate independently.
        report = plan_recipe(fixture, probe)
        probed += len(report.resolved)
        for resolved in report.resolved:
            if resolved.ok and resolved.substitution_key is None:
                return fixture, by_run_id[resolved.op.run_id], resolved.op.new_text

    pytest.fail(
        f"no G2a-eligible run found: probed {probed} candidate run(s) across "
        f"{len(_CANDIDATE_FIXTURES)} fixture(s) "
        f"({', '.join(str(f) for f in _CANDIDATE_FIXTURES)}); a single-instruction "
        f"editable_original run with a following run on the same page and no substitution "
        f"is required"
    )


def test_confined_diff_isolated_to_edited_stream(tmp_path: Path) -> None:
    """Gate G2a, all six clauses, on one real edit through the real pipeline."""
    fixture_path, run, new_text = _select_edit()

    recipe = parse_recipe(
        json.dumps([{"run_id": run.run_id, "new_text": new_text}]).encode()
    )
    output_path = tmp_path / "g2a_output.pdf"
    report = apply_recipe(fixture_path, recipe, output_path)

    assert report.ok is True, f"{fixture_path}: recipe refused ({report.resolved[0].reason})"
    assert len(report.resolved) == 1
    resolved_op = report.resolved[0]
    # G2a's scope precondition: this edit needs NO bundled substitute. Never weakened --
    # a substituting run belongs to G2b.
    assert resolved_op.substitution_key is None

    orig_pdf = pikepdf.open(fixture_path)
    new_pdf = pikepdf.open(output_path)
    try:
        # Clause 1: the confined structural diff -- exactly one instruction changed, in the
        # ONE part this run's own run_id addresses.
        parts = decode_run_id(run.run_id)
        old_bytes, _old_resources = stream_bytes_and_resources(
            orig_pdf, run.page, parts["part"], parts["xobj_path"]
        )
        new_bytes, _new_resources = stream_bytes_and_resources(
            new_pdf, run.page, parts["part"], parts["xobj_path"]
        )
        changed, total = confined_instruction_diff(old_bytes, new_bytes)
        assert total > 1, (
            f"{fixture_path} page {run.page}: part has {total} instruction(s); "
            f"'exactly one changed' is only meaningful above 1"
        )
        assert changed == 1, (
            f"{fixture_path} page {run.page}: {changed} of {total} instructions changed, "
            f"expected exactly 1"
        )

        # Clause 2: the refit put the replacement inside half a point of the original width.
        assert resolved_op.delta_pt is not None
        assert abs(resolved_op.delta_pt) < WIDTH_DELTA_TOLERANCE_PT, (
            f"width delta {resolved_op.delta_pt} exceeds {WIDTH_DELTA_TOLERANCE_PT}pt"
        )

        # Clause 3: the FOLLOWING run on the page has not moved. Compared by list position
        # within the page's run list, which is valid here precisely because this edit is
        # instruction-count-preserving (clause 1 just proved the part's instruction count is
        # unchanged, so the walker yields the same runs in the same order).
        #
        # KNOWN LIMITATION, disclosed for whoever builds on this gate (G2b especially): on
        # the currently-selected fixture/run the downstream run is positioned by `Td`, which
        # is line-matrix-relative and therefore mathematically INDEPENDENT of the edited run's
        # rendered width -- so a width error confined entirely inside the edited run's own box
        # would pass this clause, and clause 5 masks exactly that box. Clause 2's sub-0.5pt
        # delta is what actually constrains the width; clause 3 constrains a REAL downstream
        # shift (the `TJ`/`Tm`-chained case), which is what it is here to catch.
        assert resolved_op.all_page_runs is not None
        page_runs = resolved_op.all_page_runs
        index = next(
            i for i, r in enumerate(page_runs) if r.run_id == run.run_id
        )
        assert index + 1 < len(page_runs)
        downstream_before = page_runs[index + 1]

        new_classification = classify_document(output_path)
        new_page_runs = _page_runs(new_classification).get(run.page, [])
        assert index + 1 < len(new_page_runs), (
            f"{fixture_path} page {run.page}: rewritten page has {len(new_page_runs)} run(s), "
            f"expected more than {index + 1}"
        )
        downstream_after = new_page_runs[index + 1]

        assert abs(downstream_before.glyphs[0].x - downstream_after.glyphs[0].x) < POSITION_EPSILON_PT, (
            f"following run moved in x: {downstream_before.glyphs[0].x} -> "
            f"{downstream_after.glyphs[0].x}"
        )
        assert abs(downstream_before.glyphs[0].y - downstream_after.glyphs[0].y) < POSITION_EPSILON_PT, (
            f"following run moved in y: {downstream_before.glyphs[0].y} -> "
            f"{downstream_after.glyphs[0].y}"
        )

        # Clause 4: the output is structurally clean.
        result = subprocess.run(
            ["qpdf", "--check", "--warning-exit-0", str(output_path)],
            capture_output=True,
            timeout=QPDF_CHECK_TIMEOUT_SECONDS,
        )
        assert result.returncode == 0, f"qpdf --check exited {result.returncode}"

        # Clause 5: same-engine, zero-tolerance pixel identity everywhere outside the
        # edited run's own box.
        cropbox = orig_pdf.pages[run.page].cropbox
        cropbox_height_pt = float(cropbox[3]) - float(cropbox[1])
    finally:
        orig_pdf.close()
        new_pdf.close()

    mask = _edited_run_pixel_mask(run, cropbox_height_pt)
    orig_pngs = render_all(fixture_path, run.page, tmp_path / "orig")
    new_pngs = render_all(output_path, run.page, tmp_path / "new")

    for label, orig_png, new_png in zip(_ENGINE_LABELS, orig_pngs, new_pngs):
        diff = masked_pixel_diff(orig_png, new_png, mask=mask)
        assert diff == 0, (
            f"{label}: expected zero pixel diff outside the edited run's box, got {diff}"
        )

    # Clause 6: the three engines still agree with each other on the REWRITTEN output --
    # reusing clause 5's renders, not re-rendering.
    pdfium_png, poppler_png, mupdf_png = new_pngs
    for pair_label, png_a, png_b in (
        ("pdfium-vs-poppler", pdfium_png, poppler_png),
        ("pdfium-vs-mupdf", pdfium_png, mupdf_png),
        ("poppler-vs-mupdf", poppler_png, mupdf_png),
    ):
        ok, detail = _cross_engine_pair_ok(pair_label, png_a, png_b)
        assert ok, detail
