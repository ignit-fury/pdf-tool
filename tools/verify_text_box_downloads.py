"""Verify actual native text-box browser downloads; run after text-boxes*.js."""
from pathlib import Path
import io
import hashlib
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


def verify(directory: Path, candidate_hash: str | None = None):
    source = (directory / 'source.pdf').read_bytes()
    assert (directory / 'after-cancel.pdf').read_bytes() == source
    results = []
    with pikepdf.open(io.BytesIO(source)) as original_pdf, pdfium.PdfDocument(source) as original:
        source_image = original_pdf.pages[0].Resources.XObject.Im0.read_bytes()
        for name in ('inserted.pdf', 'updated.pdf', 'removed.pdf', 'mixed.pdf'):
            path = directory / name
            for command in (['qpdf', '--check', str(path)], ['pdfcpu', 'validate', '--mode', 'strict', str(path)]):
                subprocess.run(command, check=True, capture_output=True)
            data = path.read_bytes()
            with pikepdf.open(io.BytesIO(data)) as pdf:
                boxes = prepare_text_box(pdf, data, {'operation': 'list'})['boxes']
                offset = int(name == 'mixed.pdf')
                assert len(pdf.pages) == 12 + offset
                assert len(boxes) == (0 if name == 'removed.pdf' else 1)
                first = pdf.pages[offset]
                assert first.Resources.XObject.Im0.read_bytes() == source_image
                assert len(first.obj.Annots) == 1
                assert str(first.obj.Annots[0].A.URI) == 'https://example.invalid/'
                assert not any(page.obj.get('/Annots') for page in pdf.pages[offset+1:])
                if boxes:
                    assert boxes[0]['page_index'] == offset
                    style = boxes[0]['style']
                    assert style['bold'] and style['font_family'] == 'Serif'
                    assert style['font_size'] == (18 if name == 'updated.pdf' else 14)
                    assert style['alignment'] == ('center' if name == 'inserted.pdf' else 'right')
            texts = []
            with pdfium.PdfDocument(data) as output:
                for number in range(12):
                    page = output[number+offset]
                    textpage = page.get_textpage()
                    try:
                        text = textpage.get_text_range()
                    finally:
                        textpage.close()
                    texts.append(text)
                    assert 'Neighbor must stay unchanged' in text
                    assert text.count('Hello world') == 2
                    assert ('Changed title' if offset and number == 0 else f'Document page {number+1}') in text
                    difference = ImageChops.difference(render(original[number]), render(page))
                    if number == 0:
                        for box in boxes:
                            r = box['rect']
                            difference.paste((0, 0, 0), (math.floor(r['left'])-1, math.floor(r['top'])-1,
                                math.ceil(r['left']+r['width'])+1, math.ceil(r['top']+r['height'])+1))
                        if offset:
                            difference.paste((0, 0, 0), (45, 45, 300, 85))
                            difference.paste((0, 0, 0), (449, 499, 532, 552))
                    assert difference.getbbox() is None, (name, number, 'unrelated pixels changed')
            if name == 'inserted.pdf':
                assert 'café' in texts[0] and 'First paragraph' in texts[0]
            if name == 'updated.pdf':
                assert 'Updated paragraph' in texts[0] and 'A second line.' in texts[0]
            if name == 'mixed.pdf':
                assert 'Mixed workflow' in texts[0] and 'Native text remains editable.' in texts[0]
            if name == 'removed.pdf':
                assert 'Updated paragraph' not in '\n'.join(texts)
            results.append({'name': name, 'pages': 12+offset, 'structural_validations': 2,
                'unrelated_pixel_comparisons': 12, 'searchable_text': True,
                'source_image_and_link_preserved': True})
    rotated = directory / 'rotated-inserted.pdf'
    for command in (['qpdf', '--check'], ['pdfcpu', 'validate', '--mode', 'strict']):
        subprocess.run([*command, str(rotated)], check=True, capture_output=True)
    data = rotated.read_bytes()
    if candidate_hash is not None:
        assert hashlib.sha256(data).hexdigest() == candidate_hash
    with pikepdf.open(io.BytesIO(data)) as pdf:
        box = prepare_text_box(pdf, data, {'operation': 'list'})['boxes'][0]
        assert box['rect'] == {'left': 400, 'top': 300, 'width': 300, 'height': 120}
        assert 'rotation' not in box
    with pdfium.PdfDocument(directory / 'rotated-source.pdf') as original, pdfium.PdfDocument(data) as output:
        textpage = output[0].get_textpage()
        try:
            assert 'Rotated page supports upright new text.' in textpage.get_text_range()
        finally:
            textpage.close()
        # PDFium's default ignores UserUnit2; 2x gives physical point pixels.
        before = original[0].render(scale=2).to_pil().convert('RGB')
        after = output[0].render(scale=2).to_pil().convert('RGB')
        difference = ImageChops.difference(before, after)
        difference.paste((0, 0, 0), (399, 299, 701, 421))
        assert difference.getbbox() is None
    results.append({'name': rotated.name, 'pages': 1, 'structural_validations': 2,
        'unrelated_pixel_comparisons': 1, 'searchable_text': True,
        'exact_candidate_bytes_applied': candidate_hash is not None})
    result = {'passed': True, 'cancel_byte_identical': True, 'documents': results}
    (directory / 'native-download-results.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    print(json.dumps(verify(Path(sys.argv[1] if len(sys.argv)>1 else '/private/tmp/pdf-tool-text-boxes-20261029'),
        sys.argv[2] if len(sys.argv)>2 else None), indent=2))
