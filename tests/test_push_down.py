"""engine.push_down: content below a cut moves down by exactly dy, or nothing changes."""
import base64
import io
import shutil
import subprocess
from pathlib import Path

import pikepdf
import pypdfium2 as pdfium
import pytest
from PIL import ImageChops

from engine.push_down import PushDownRefused, push_down
from engine.text_boxes import prepare_text_box
from tools.build_export_fixtures import build_export_fixture

CORPUS = Path(__file__).resolve().parents[1] / 'corpus' / 'public'
SCALE = 2.0


def saved(pdf: pikepdf.Pdf) -> bytes:
    out = io.BytesIO()
    pdf.save(out, deterministic_id=True)
    return out.getvalue()


def text_lines(data: bytes, page: int = 0) -> dict[str, tuple[float, float]]:
    """pdfium's text rects: text -> (left, bottom)."""
    with pdfium.PdfDocument(data) as doc:
        textpage = doc[page].get_textpage()
        result = {}
        for i in range(textpage.count_rects()):
            left, bottom, right, top = textpage.get_rect(i)
            result[textpage.get_text_bounded(left, bottom, right, top).strip()] = (round(left, 3), round(bottom, 3))
        return result


def qpdf_check(data: bytes, tmp_path: Path) -> None:
    qpdf = shutil.which('qpdf')
    if qpdf is None:
        pytest.skip('qpdf CLI is not installed')
    path = tmp_path / 'checked.pdf'
    path.write_bytes(data)
    result = subprocess.run([qpdf, '--check', str(path)], capture_output=True, text=True)
    assert result.returncode in (0, 3), result.stdout + result.stderr  # 3: warnings only


def one_page(content: bytes, annots: list[pikepdf.Dictionary] | None = None) -> bytes:
    with pikepdf.Pdf.new() as pdf:
        font = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                                                    BaseFont=pikepdf.Name.Helvetica))
        page = pdf.add_blank_page(page_size=(400, 600))
        page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
        page.Contents = pdf.make_stream(content)
        if annots:
            page.Annots = pdf.make_indirect(pikepdf.Array([pdf.make_indirect(a) for a in annots]))
        return saved(pdf)


MULTILINE = (b'BT /F1 12 Tf 16 TL 72 500 Td (Line one) Tj T* (Line two) Tj '
             b'T* (Line three) Tj T* (Line four) Tj ET')


def push(data: bytes, y_cut: float, dy: float, **kw: object) -> tuple[int, bytes]:
    with pikepdf.open(io.BytesIO(data)) as pdf:
        moved = push_down(pdf, 0, y_cut, dy, **kw)  # type: ignore[arg-type]
        return moved, saved(pdf)


def refused(data: bytes, y_cut: float, dy: float, **kw: object) -> str:
    with pikepdf.open(io.BytesIO(data)) as pdf:
        before = saved(pdf)
        with pytest.raises(PushDownRefused) as caught:
            push_down(pdf, 0, y_cut, dy, **kw)  # type: ignore[arg-type]
        assert saved(pdf) == before  # atomic: nothing was mutated
        return caught.value.code


@pytest.fixture
def export_fixture(tmp_path: Path) -> bytes:
    path = tmp_path / 'export.pdf'
    build_export_fixture(path)
    return path.read_bytes()


def test_export_fixture_moves_body_by_exactly_dy(export_fixture: bytes, tmp_path: Path) -> None:
    moved, after = push(export_fixture, 470, 40)
    assert moved == 3
    before_lines, after_lines = text_lines(export_fixture), text_lines(after)
    assert before_lines.keys() == after_lines.keys()
    for text, (left, bottom) in before_lines.items():
        shift = 40 if text in ('Bold body', 'Italic body', '- First item') else 0
        assert after_lines[text] == (left, round(bottom - shift, 3)), text
    qpdf_check(after, tmp_path)


def test_export_fixture_cut_through_columns_straddles(export_fixture: bytes) -> None:
    # Through the second row of both columns (baselines 484, Helvetica 12 pt).
    assert refused(export_fixture, 488, 40) == 'PUSH_DOWN_STRADDLE'


def test_one_text_object_splits_between_lines(tmp_path: Path) -> None:
    data = one_page(MULTILINE)
    moved, after = push(data, 479, 30)  # between "Line two" (484) and "Line three" (468) baselines
    assert moved == 2
    before_lines, after_lines = text_lines(data), text_lines(after)
    assert after_lines == {text: (left, round(bottom - (30 if text in ('Line three', 'Line four') else 0), 3))
                           for text, (left, bottom) in before_lines.items()}
    with pdfium.PdfDocument(data) as a, pdfium.PdfDocument(after) as b:
        assert a[0].get_textpage().get_text_range() == b[0].get_textpage().get_text_range()
    qpdf_check(after, tmp_path)


def test_marked_content_across_the_split_is_unsupported() -> None:
    data = one_page(b'BT /F1 12 Tf 16 TL 72 500 Td (Line one) Tj /Span <</MCID 0>> BDC T* (Line two) Tj '
                    b'T* (Line three) Tj EMC T* (Line four) Tj ET')
    assert refused(data, 479, 30) == 'PUSH_DOWN_UNSUPPORTED'


def test_marked_content_per_line_still_splits() -> None:
    data = one_page(b'BT /F1 12 Tf 16 TL 72 500 Td /P <</MCID 0>> BDC (Line one) Tj EMC '
                    b'/P <</MCID 1>> BDC T* (Line two) Tj EMC /P <</MCID 2>> BDC T* (Line three) Tj EMC ET')
    moved, after = push(data, 479, 30)
    assert moved == 1
    assert text_lines(after)['Line three'][1] == round(text_lines(data)['Line three'][1] - 30, 3)


def test_page_full_refuses_and_leaves_bytes(export_fixture: bytes) -> None:
    assert refused(export_fixture, 470, 400) == 'PUSH_DOWN_PAGE_FULL'


def test_link_annotation_moves_with_its_text() -> None:
    link = pikepdf.Dictionary(Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Link,
                              Rect=[70, 465, 160, 477], QuadPoints=[70, 477, 160, 477, 70, 465, 160, 465])
    above = pikepdf.Dictionary(Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Link, Rect=[70, 495, 160, 512])
    data = one_page(MULTILINE, [link, above])
    moved, after = push(data, 479, 30)
    assert moved == 3  # two text lines and one annotation
    with pikepdf.open(io.BytesIO(after)) as pdf:
        moved_link, kept_link = pdf.pages[0].Annots
        assert [float(v) for v in moved_link.Rect] == [70, 435, 160, 447]
        assert [float(v) for v in moved_link.QuadPoints] == [70, 447, 160, 447, 70, 435, 160, 435]
        assert [float(v) for v in kept_link.Rect] == [70, 495, 160, 512]


def test_annotation_across_the_cut_straddles() -> None:
    link = pikepdf.Dictionary(Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Link, Rect=[70, 470, 160, 490])
    assert refused(one_page(MULTILINE, [link]), 479, 30) == 'PUSH_DOWN_STRADDLE'


def test_page_background_stays_and_a_table_grid_straddles() -> None:
    page_fill = b'0.9 g 0 0 400 600 re f 0 g '
    moved, after = push(one_page(page_fill + MULTILINE), 479, 30)
    assert moved == 2
    grid = b'72 440 200 80 re 72 480 m 272 480 l 72 460 m 272 460 l S '
    assert refused(one_page(grid + MULTILINE), 479, 30) == 'PUSH_DOWN_STRADDLE'


def test_stays_inside_a_clip_that_stays() -> None:
    """A margin clip is left in place, so content must not be pushed out of it."""
    content = b'q 0 100 400 500 re W n ' + MULTILINE + b' Q'
    assert push(one_page(content), 479, 30)[0] == 2
    assert refused(one_page(content), 479, 360) == 'PUSH_DOWN_PAGE_FULL'


def test_instruction_split_across_parts_keeps_its_operands(tmp_path: Path) -> None:
    with pikepdf.Pdf.new() as pdf:
        font = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)
        page = pdf.add_blank_page(page_size=(400, 600))
        page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
        page.Contents = pikepdf.Array([
            pdf.make_stream(b'BT /F1 12 Tf 16 TL 72 500 Td (Line one) Tj T* (Line two) Tj T* [(Line three)]'),
            pdf.make_stream(b'TJ T* (Line four) Tj ET')])
        data = saved(pdf)
    moved, after = push(data, 479, 30)
    assert moved == 2
    lines = text_lines(after)
    assert lines['Line three'][1] == round(text_lines(data)['Line three'][1] - 30, 3)
    with pikepdf.open(io.BytesIO(after)) as pdf:
        assert len(pdf.pages[0].Contents) == 2  # never coalesced: part indices are run-ID addresses
    qpdf_check(after, tmp_path)


def test_managed_image_below_the_cut_refuses() -> None:
    with pikepdf.open(io.BytesIO(one_page(MULTILINE))) as pdf:
        page = pdf.pages[0]
        managed = pdf.make_stream(b'q 50 0 0 50 300 100 cm /ImageManagedx Do Q\n')
        managed.PdfToolImage = pikepdf.Dictionary(Id=pikepdf.Name('/mi_abcdefgh'), Version=1)
        image = pdf.make_stream(b'\xff\xff\xff', Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image,
                                Width=1, Height=1, ColorSpace=pikepdf.Name.DeviceRGB, BitsPerComponent=8)
        page.Resources.XObject = pikepdf.Dictionary(ImageManagedx=image)
        page.Contents = pikepdf.Array([page.Contents, managed])
        data = saved(pdf)
    assert refused(data, 479, 30) == 'PUSH_DOWN_MANAGED_IMAGE'
    assert push(data, 50, 10)[0] == 0  # wholly above the cut: no move, no refusal


def test_native_text_box_is_reported_not_moved() -> None:
    with pikepdf.Pdf.new() as pdf:
        pdf.add_blank_page(page_size=(400, 600))
        source = saved(pdf)
    with pikepdf.open(io.BytesIO(source)) as pdf:
        result = prepare_text_box(pdf, source, {
            'operation': 'upsert', 'page_index': 0, 'text': 'Boxed text',
            'rect': {'left': 40, 'top': 400, 'width': 200, 'height': 40}})
    data = base64.b64decode(str(result['pdf']))
    [box] = result['boxes']  # type: ignore[misc]
    assert refused(data, 300, 20) == 'PUSH_DOWN_UNSUPPORTED'  # nobody took the box over
    seen: list[str] = []
    moved, after = push(data, 300, 20, keep=lambda box: seen.append(box) is None)
    assert (moved, seen) == (0, [box['id']])
    with pikepdf.open(io.BytesIO(data)) as pdf:
        assert after == saved(pdf)  # untouched: the box is the caller's to move, by re-upserting it
    assert push(data, 100, 20, keep=lambda box: False)[0] == 0  # wholly above: never asked


def test_rotated_page_is_unsupported() -> None:
    with pikepdf.open(io.BytesIO(one_page(MULTILINE))) as pdf:
        pdf.pages[0].Rotate = 90
        data = saved(pdf)
    assert refused(data, 479, 30) == 'PUSH_DOWN_UNSUPPORTED'


def render(data: bytes) -> object:
    with pdfium.PdfDocument(data) as doc:
        # Text anti-aliasing off: pdfium's float32 glyph placement differs by ~1e-4 pt
        # between "Td accumulated" and "Tm restored", which flips edge pixels only.
        return doc[0].render(scale=SCALE, no_smoothtext=True).to_pil().convert('RGB')


@pytest.mark.parametrize(('name', 'y_cut'), [
    ('far_federal_acquisition_regulation.pdf', 308.3),
    ('govdocs1_007_007020.pdf', 388.2),   # one text object for the whole page
    ('govdocs1_002_002145.pdf', 399.3),   # one text object for the whole page
])
def test_corpus_page_moves_below_and_keeps_above(name: str, y_cut: float, tmp_path: Path) -> None:
    data = (CORPUS / name).read_bytes()
    dy = 14.0
    moved, after = push(data, y_cut, dy)
    assert moved > 0
    a, b = render(data), render(after)
    width, height = a.size  # type: ignore[attr-defined]
    with pdfium.PdfDocument(data) as doc:
        top = doc[0].get_cropbox()[3]
    cut, shift = round((top - y_cut) * SCALE), round(dy * SCALE)
    assert ImageChops.difference(a.crop((0, 0, width, cut)), b.crop((0, 0, width, cut))).getbbox() is None  # type: ignore[attr-defined]
    assert ImageChops.difference(a.crop((0, cut, width, height - shift)),  # type: ignore[attr-defined]
                                 b.crop((0, cut + shift, width, height))).getbbox() is None  # type: ignore[attr-defined]
    qpdf_check(after, tmp_path)
