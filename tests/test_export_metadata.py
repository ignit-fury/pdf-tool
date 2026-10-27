"""Additive export metadata must not change the editable text index."""
from pathlib import Path

import pikepdf
import pytest

from engine.index import RunIndex
from engine.classify_run import classify_document


def make_pdf(path: Path, content: bytes = b"BT /F1 12 Tf 40 100 Td (Body) Tj ET", *, base: str = "Helvetica", descriptor: bool = False) -> None:
    with pikepdf.Pdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(400, 300))
        font = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name('/' + base))
        if descriptor:
            font.FontDescriptor = pikepdf.Dictionary(Flags=64, FontWeight=700)
        page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pdf.make_indirect(font)))
        page.Contents = pdf.make_stream(content)
        pdf.save(path)


def test_metadata_preserves_run_identity_and_verdict(tmp_path: Path) -> None:
    path = tmp_path / 'in.pdf'
    make_pdf(path, base='ABCDEF+Helvetica-BoldOblique', descriptor=True)
    original = classify_document(path).runs
    with RunIndex(path) as index:
        page = index.page(0)
        assert page is index.page(0)
        run, verdict = page.runs[0]
        assert (run.run_id, run.glyphs, verdict) == (original[0][0].run_id, original[0][0].glyphs, original[0][1])
        assert run.font_name == 'Helvetica-BoldOblique'
        assert run.bold is True and run.italic is True
        assert run.effective_em == pytest.approx(12)
        assert page.geometry.media_box == (0, 0, 400, 300)


def test_unknown_style_is_unknown(tmp_path: Path) -> None:
    path = tmp_path / 'in.pdf'
    make_pdf(path, base='Mystery-Bold')
    with RunIndex(path) as index:
        run = index.page(0).runs[0][0]
        assert run.bold is None and run.italic is None


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_geometry_and_stroked_rulings_share_glyph_frame(tmp_path: Path, rotation: int) -> None:
    path = tmp_path / 'in.pdf'
    make_pdf(path, b'q 2 0 0 2 10 20 cm 0 0 50 40 re S Q BT /F1 12 Tf 10 20 Td (Body) Tj ET')
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        page = pdf.pages[0]
        page.Rotate = rotation
        page.CropBox = pikepdf.Array([5, 10, 390, 290])
        page.UserUnit = 2
        pdf.save(path)
    with RunIndex(path) as index:
        page = index.page(0)
        assert page.geometry.rotation == rotation
        assert page.geometry.user_unit == 2
        assert page.geometry.crop_box == (5, 10, 390, 290)
        assert len(page.rulings) == 4
        a,b,c,d,e,f = page.geometry.page_ctm
        point = (a*10+c*20+e, b*10+d*20+f)
        assert any(point == pytest.approx(line[:2]) for line in page.rulings)


def test_curved_filled_and_clipped_paths_are_not_rulings(tmp_path: Path) -> None:
    path = tmp_path / 'in.pdf'
    make_pdf(path, b'0 0 10 10 re f 0 0 m 10 10 20 20 30 30 c S 0 0 30 30 re W n 0 0 50 50 re S')
    with RunIndex(path) as index:
        assert index.page(0).rulings == ()


def test_same_named_fonts_in_distinct_resources_have_distinct_identity(tmp_path: Path) -> None:
    path = tmp_path / 'in.pdf'
    make_pdf(path)
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        page = pdf.add_blank_page(page_size=(400, 300))
        page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica))))
        page.Contents = pdf.make_stream(b'BT /F1 12 Tf 40 100 Td (Other) Tj ET')
        pdf.save(path)
    with RunIndex(path) as index:
        assert index.page(0).runs[0][0].font_identity != index.page(1).runs[0][0].font_identity


def test_direct_same_named_font_resources_keep_their_page_owner(tmp_path: Path) -> None:
    path = tmp_path / 'direct.pdf'
    with pikepdf.Pdf.new() as pdf:
        for _ in range(2):
            page = pdf.add_blank_page(page_size=(400,300))
            page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)))
            page.Contents = pdf.make_stream(b'BT /F1 12 Tf 40 100 Td (Body) Tj ET')
        pdf.save(path)
    with RunIndex(path) as index:
        assert index.page(0).runs[0][0].font_identity != index.page(1).runs[0][0].font_identity
