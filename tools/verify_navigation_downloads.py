"""Native verification of actual bookmark/history browser downloads."""
from pathlib import Path
import io
import json
import math
import subprocess
import sys

import pikepdf
import pypdfium2 as pdfium
from PIL import ImageChops

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.text_boxes import prepare_text_box


def render(page):
    bitmap = page.render(scale=1)
    try:
        return bitmap.to_pil().convert('RGB')
    finally:
        bitmap.close()


def text(page):
    extraction = page.get_textpage()
    try:
        return extraction.get_text_range()
    finally:
        extraction.close()


def verify(directory: Path):
    original = (directory / 'bookmarks.pdf').read_bytes()
    latest = (directory / 'latest.pdf').read_bytes()
    assert (directory / 'restored-original.pdf').read_bytes() == original
    assert (directory / 'after-canceled-jump.pdf').read_bytes() == (directory / 'source.pdf').read_bytes()
    for name in ('restored-latest', 'after-failed-restore', 'redone-latest'):
        assert (directory / f'{name}.pdf').read_bytes() == latest, name
    names = ('latest', 'restored-original', 'restored-latest', 'after-failed-restore', 'restored-middle', 'redone-latest')
    for name in names:
        path = directory / f'{name}.pdf'
        for command in (['qpdf', '--check'], ['pdfcpu', 'validate', '--mode', 'strict']):
            subprocess.run([*command, str(path)], check=True, capture_output=True)
    with pikepdf.open(io.BytesIO(latest)) as pdf, pikepdf.open(directory / 'restored-middle.pdf') as middle, pikepdf.open(io.BytesIO(original)) as source:
        assert len(pdf.pages) == len(middle.pages) == 13
        assert int(pdf.pages[4].obj.Rotate) == int(middle.pages[4].obj.Rotate) == 90
        boxes = prepare_text_box(pdf, latest, {'operation': 'list'})['boxes']
        assert len(boxes) == 1 and boxes[0]['page_index'] == 0
        assert boxes[0]['text'] == 'History preserves searchable inserted text.'
        assert not prepare_text_box(middle, (directory / 'restored-middle.pdf').read_bytes(), {'operation': 'list'})['boxes']
        assert pdf.pages[0].Resources.XObject.Im0.read_bytes() == source.pages[0].Resources.XObject.Im0.read_bytes()
        assert str(pdf.pages[0].obj.Annots[0].A.URI) == 'https://example.invalid/'
        # Actual named destination remains attached to source page4 after insertion.
        assert pdf.Root.Names.Dests.Names[1][0].objgen == pdf.pages[4].obj.objgen
        assert pdf.Root.Outlines.First.First.Dest == pikepdf.String('chapter-four')
    with pdfium.PdfDocument(latest) as pdf, pdfium.PdfDocument(directory / 'restored-middle.pdf') as middle:
        assert 'History preserves searchable inserted text.' in text(pdf[0])
        assert 'History preserves searchable inserted text.' not in text(middle[0])
        assert not text(pdf[3]).strip()
        for number in range(13):
            difference = ImageChops.difference(render(pdf[number]), render(middle[number]))
            if number == 0:
                rect = boxes[0]['rect']
                difference.paste((0, 0, 0), (math.floor(rect['left'])-1, math.floor(rect['top'])-1,
                    math.ceil(rect['left']+rect['width'])+1, math.ceil(rect['top']+rect['height'])+1))
                difference.paste((0, 0, 0), (449, 499, 532, 552))
            assert difference.getbbox() is None, (number, 'Unrelated content changed')
    result = {'passed': True, 'byte_identity_checks': 5, 'structural_validations': 12,
        'unrelated_pixel_comparisons': 13, 'searchable_native_text': True,
        'source_image_link_and_bookmarks_preserved': True}
    (directory / 'native-results.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    print(json.dumps(verify(Path(sys.argv[1] if len(sys.argv)>1 else '/private/tmp/pdf-tool-navigation-20261029')), indent=2))
