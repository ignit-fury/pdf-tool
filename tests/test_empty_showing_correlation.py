"""Text instruction ordinals and clustered run IDs retain physical stream identity."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pikepdf
import pypdfium2 as pdfium
import pytest

from engine.index import RunIndex
from engine.recipe import RecipeOp, apply_recipe, plan_recipe
from engine.rewrite import rewrite_instructions, touched_instruction_indices
from engine.run_id import decode_run_id
from tools.build_security_fixtures import text_pdf


def _save_contents(path: Path, contents: list[bytes]) -> None:
    with pikepdf.open(io.BytesIO(text_pdf())) as pdf:
        streams = [pdf.make_stream(raw) for raw in contents]
        pdf.pages[0].Contents = streams[0] if len(streams) == 1 else pikepdf.Array(streams)
        pdf.save(path)


def _runs(path: Path):
    with RunIndex(path) as index:
        return [run for run, _verdict in index.page(0).runs]


def _text(path: Path) -> str:
    with pdfium.PdfDocument(path) as document:
        page = document[0]
        try:
            textpage = page.get_textpage()
            try:
                return textpage.get_text_range()
            finally:
                textpage.close()
        finally:
            page.close()


def test_empty_showing_operators_do_not_shift_rewrite_target_or_remove_advances(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    raw = (b"BT /F1 12 Tf 20 150 Td () Tj [120] TJ (Alpha) Tj "
           b"() Tj [-500 ()] TJ (Bravo) Tj [] TJ () ' 0 0 () \" ET")
    _save_contents(source, [raw])
    runs = _runs(source)
    target = next(run for run in runs if run.display_text == "Alpha")
    follower_before = next(run for run in runs if run.display_text == "Bravo")
    offsets = sorted({glyph.operator_byte_offset for run in runs for glyph in run.glyphs})
    with pikepdf.open(source) as pdf:
        before = pikepdf.parse_content_stream(pdf.pages[0])
        touched = touched_instruction_indices(
            before, {glyph.operator_byte_offset for glyph in target.glyphs}, offsets)
        assert touched == [5]
        # Same text preserves widths while exercising the real splice. Every
        # glyphless instruction, including its numeric pen advance, must survive.
        replacement = pikepdf.ContentStreamInstruction([pikepdf.String(b"Alpha")], pikepdf.Operator("Tj"))
        outcome = rewrite_instructions(pdf, 0, target, runs, [replacement])
        assert outcome.ok, outcome.reason
        after = pikepdf.parse_content_stream(pdf.pages[0])
        assert [pikepdf.unparse_content_stream([i]) for i in after] == [
            pikepdf.unparse_content_stream([i]) for i in before]
        pdf.save(output)
    follower_after = next(run for run in _runs(output) if run.display_text == "Bravo")
    assert [(g.x, g.y) for g in follower_after.glyphs] == pytest.approx(
        [(g.x, g.y) for g in follower_before.glyphs])
    assert "Alpha" in _text(output) and "Bravo" in _text(output)


def test_adjacent_contents_parts_have_independent_run_anchors(tmp_path: Path) -> None:
    source = tmp_path / "parts.pdf"
    # Adjacent same-style text can share a visual line but cannot share one
    # part-scoped run ID. A one-character fragment must retain its own part.
    _save_contents(source, [
        b"BT /F1 12 Tf 20 150 Td (Alpha) Tj",
        b"(Bravo) Tj ET",
    ])
    runs = _runs(source)
    assert len(runs) >= 2
    assert all(g.stream_id == decode_run_id(run.run_id)["part"] for run in runs for g in run.glyphs)
    assert all(len({g.stream_id for g in run.glyphs}) == 1 for run in runs)


@pytest.mark.corpus
def test_actual_corpus_run_anchors_and_shorter_edit_apply(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "corpus/public/govdocs1_010_010118.pdf"
    before = hashlib.sha256(source.read_bytes()).digest()
    with RunIndex(source) as index:
        indexed = index.page(0)
        assert all(g.stream_id == decode_run_id(run.run_id)["part"]
                   for run, _verdict in indexed.runs for g in run.glyphs)
        candidates = [run for run, verdict in indexed.runs if verdict.state.startswith("editable")
                      and len(run.display_text.strip()) >= 2]
    candidates.sort(key=lambda run: (-min(len(run.display_text), 80), run.run_id))
    target = candidates[0]
    replacement = target.display_text[:5].rstrip()
    recipe = (RecipeOp(target.run_id, replacement),)
    planned = plan_recipe(source, recipe)
    assert planned.ok, [r.reason for r in planned.resolved]
    output = tmp_path / "edited.pdf"
    applied = apply_recipe(source, recipe, output)
    assert applied.ok, [r.reason for r in applied.resolved]
    original_text = " ".join(_text(source).split())
    edited_text = " ".join(_text(output).split())
    original_run = " ".join(target.display_text.split())
    assert original_text.count(original_run) == 1
    expected = original_text.replace(original_run, " ".join(replacement.split()), 1)
    assert bool(edited_text == expected), "full-page searchable text differs from the requested replacement"
    assert hashlib.sha256(source.read_bytes()).digest() == before
