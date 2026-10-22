"""Large text shrink preserves natural glyph widths and subsequent text advance."""
from pathlib import Path

import pikepdf
import pypdfium2 as pdfium
import pytest
from fontTools.ttLib import TTFont

from engine.classify_run import classify_document
from engine.fonts import liberation_font_path
from engine.recipe import RecipeOp, apply_recipe
from test_recipe import _build_apply_fixture


@pytest.mark.parametrize("source_font,family", [("F1", None), ("F2", None), ("F1", "Serif"), ("F2", "Serif")])
@pytest.mark.parametrize("replacement", ["Tiny", "A B"])
def test_large_shrink_preserves_following_text_and_natural_widths(
    tmp_path: Path, source_font: str, family: str | None, replacement: str
) -> None:
    source, output = tmp_path / "source.pdf", tmp_path / "edited.pdf"
    _build_apply_fixture(source)
    with pikepdf.open(source, allow_overwriting_input=True) as pdf:
        # No Td/Tm between shows: the follower's location depends on the edited
        # operator's advance. A color change keeps it in a separate classified run.
        pdf.pages[0].Contents = pdf.make_stream(
            f"BT /{source_font} 12 Tf 72 700 Td ".encode()
            + b"(Original content needs substantially less replacement text) Tj "
            + b"0.4 g (FOLLOWER) Tj ET"
        )
        pdf.save(source)
    original_bytes = source.read_bytes()
    before = [run for run, _ in classify_document(source).runs if run.page == 0]
    target = next(run for run in before if run.display_text.startswith("Original"))
    follower = next(run for run in before if run.display_text == "FOLLOWER")
    assert follower.glyphs[0].x - target.glyphs[0].x > 200

    style = {"font_family": family} if family is not None else None
    report = apply_recipe(source, (RecipeOp(target.run_id, replacement, style=style),), output)
    assert report.ok, report
    assert report.resolved[0].strategy == "trailing_kern"
    expected_family = family or "Sans"
    if source_font == "F2" or family is not None:
        assert report.resolved[0].substitution_key == (expected_family, "Regular")
    else:
        assert report.resolved[0].substitution_key is None
    assert source.read_bytes() == original_bytes

    after = [run for run, _ in classify_document(output).runs if run.page == 0]
    changed = next(run for run in after if run.display_text == replacement)
    following = next(run for run in after if run.display_text == "FOLLOWER")
    assert (changed.glyphs[0].x, changed.glyphs[0].y) == pytest.approx(
        (target.glyphs[0].x, target.glyphs[0].y), abs=0.001
    )
    for original, current in zip(follower.glyphs, following.glyphs, strict=True):
        assert (current.x, current.y, *current.advance) == pytest.approx(
            (original.x, original.y, *original.advance), abs=0.001
        )
    # Independent font metrics pin each painted glyph's natural PDF width (the
    # font dictionary uses integer thousandths). This also catches interior
    # kerns that could stretch the replacement's spaces.
    with TTFont(liberation_font_path(expected_family, "Regular")) as font:
        cmap, hmtx = font.getBestCmap(), font["hmtx"]
        upem = font["head"].unitsPerEm
        cursor = target.glyphs[0].x
        for char, glyph in zip(replacement, changed.glyphs, strict=True):
            width = round(hmtx[cmap[ord(char)]][0] * 1000 / upem) / 1000 * 12
            assert glyph.x == pytest.approx(cursor, abs=0.001)
            assert glyph.advance[0] == pytest.approx(width, abs=0.001)
            cursor += width

    with pikepdf.open(output) as pdf:
        instructions = list(pikepdf.parse_content_stream(pdf.pages[0]))
        assert not any(str(ins.operator) == "Tz" for ins in instructions)
        showing = next(ins for ins in instructions if str(ins.operator) == "TJ")
        assert len(showing.operands[0]) == 2
        assert isinstance(showing.operands[0][0], pikepdf.String)
        assert float(showing.operands[0][1]) < 0
    # Searchability is checked by a separate PDF engine, not just our run decoder.
    with pdfium.PdfDocument(output) as pdf:
        page = pdf[0]
        text = page.get_textpage()
        try:
            extracted = text.get_text_range(0, text.count_chars())
            assert replacement in extracted
            assert "Original content" not in extracted
            assert "FOLLOWER" in extracted
        finally:
            text.close()
            page.close()
