"""Native assertions on actual browser downloads from tests/browser/viewer-*.js."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

from PIL import ImageChops
import pikepdf
import pypdfium2 as pdfium

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.classify_run import classify_document


def verify(directory: Path) -> dict[str, object]:
    source = directory / 'viewer-fixture.pdf'
    documents: list[dict[str, object]] = []
    report: dict[str, object] = {'passed': True, 'documents': documents}
    with pdfium.PdfDocument(source) as original:
        for name in ('inline-edited.pdf', 'image-replaced.pdf', 'replaced-all.pdf'):
            path = directory / name
            subprocess.run(['qpdf', '--check', str(path)], check=True, capture_output=True)
            subprocess.run(['pdfcpu', 'validate', '--mode', 'strict', str(path)], check=True, capture_output=True)
            text = []
            with pdfium.PdfDocument(path) as output:
                assert len(output) == 12
                for number in range(12):
                    page = output[number]
                    extraction = page.get_textpage()
                    try:
                        page_text = extraction.get_text_range()
                    finally:
                        extraction.close()
                    text.append(page_text)
                    assert f'Document page {number+1}' in page_text
                    assert 'Neighbor must stay unchanged' in page_text
                    a = original[number].render(scale=1).to_pil().convert('RGB')
                    b = page.render(scale=1).to_pil().convert('RGB')
                    diff = ImageChops.difference(a, b)
                    if name == 'replaced-all.pdf' or number == 0:
                        diff.paste((0, 0, 0), (50, 105, 200, 135))
                    if name == 'replaced-all.pdf':
                        diff.paste((0, 0, 0), (50, 145, 200, 175))
                    if name == 'image-replaced.pdf' and number == 0:
                        diff.paste((0, 0, 0), (80, 225, 160, 350))
                    assert diff.getbbox() is None, (name, number, 'unrelated pixels changed')
            whole = '\n'.join(text)
            if name == 'replaced-all.pdf':
                assert 'Hello' not in whole and whole.count('Hi') == 24
                assert 'Hi new world' in text[0]
            else:
                assert whole.count('Hello') == 24 and 'Hello new world' in text[0]
            with pikepdf.open(path) as pdf:
                assert not any(page.obj.get('/Annots') for page in pdf.pages)
            documents.append({'name': name, 'pages': 12,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'structural_validations': 2, 'unrelated_pixel_comparisons': 12,
                'searchable_text_verified': True})
    source_runs = classify_document(source).runs
    for name in ('inline-edited.pdf', 'image-replaced.pdf', 'replaced-all.pdf'):
        runs = classify_document(directory / name).runs
        for original, _ in source_runs:
            if original.display_text == 'Neighbor must stay unchanged' or original.display_text.startswith('Document page '):
                result = next(r for r, _ in runs if r.page == original.page and r.display_text == original.display_text)
                assert [(g.x, g.y) for g in result.glyphs] == [(g.x, g.y) for g in original.glyphs]
    styled = next(r for r, _ in classify_document(directory / 'image-replaced.pdf').runs if r.display_text == 'Hello new world')
    assert styled.bold and styled.italic and abs(styled.effective_em-7) < 0.001
    (directory / 'native-download-results.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    print(json.dumps(verify(Path(sys.argv[1] if len(sys.argv)>1 else '/private/tmp/pdf-tool-viewer-20261029')), indent=2))
