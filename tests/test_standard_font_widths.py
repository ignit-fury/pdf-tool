"""Standard PDF fonts may legally omit their explicit width arrays."""
from pathlib import Path

import pikepdf
import pytest

from engine.classify_run import classify_document
from engine.fit import advance_pt_for_codes
from engine.recipe import RecipeOp, apply_recipe
from tools.build_security_fixtures import text_pdf


@pytest.mark.parametrize('name', ['Helvetica', 'Helvetica-Bold', 'Times-Roman', 'Courier'])
def test_standard_font_without_widths_edits_and_preserves_following_text(tmp_path: Path, name) -> None:
    source, output = tmp_path / 'source.pdf', tmp_path / 'output.pdf'
    source.write_bytes(text_pdf(b'Hello world'))
    with pikepdf.open(source, allow_overwriting_input=True) as pdf:
        font = pdf.pages[0].Resources.Font.F1
        font.BaseFont = pikepdf.Name('/' + name)
        for key in ('/Widths', '/FirstChar', '/LastChar'):
            del font[key]
        pdf.pages[0].Contents = pdf.make_stream(b'BT /F1 12 Tf 20 100 Td (Hello world) Tj 0.4 g (AFTER) Tj ET')
        pdf.save(source)
    original = source.read_bytes()
    before = classify_document(source).runs
    target = next(r for r, _ in before if r.display_text == 'Hello world')
    following = next(r for r, _ in before if r.display_text == 'AFTER')
    with pikepdf.open(source) as pdf:
        declared = advance_pt_for_codes(pdf.pages[0].Resources.Font.F1, list(b'Hello world'), 12)
        assert declared == pytest.approx(sum(g.advance[0] for g in target.glyphs))
    report = apply_recipe(source, (RecipeOp(target.run_id, 'Hi'),), output)
    assert report.ok, report
    after = classify_document(output).runs
    changed = next(r for r, _ in after if r.display_text == 'Hi')
    kept = next(r for r, _ in after if r.display_text == 'AFTER')
    assert changed.glyphs[0].x == pytest.approx(target.glyphs[0].x, abs=1e-6)
    assert kept.glyphs[0].x == pytest.approx(following.glyphs[0].x, abs=1e-6)
    assert source.read_bytes() == original


def test_unknown_font_does_not_guess_missing_widths() -> None:
    font = pikepdf.Dictionary(Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.UnrecognizedFont,
                              Encoding=pikepdf.Name.WinAnsiEncoding)
    with pytest.raises((KeyError, ValueError)):
        advance_pt_for_codes(font, [65], 12)
