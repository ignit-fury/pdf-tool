"""Actual browser output proof: viewer highlights never become PDF content."""
from pathlib import Path
import json
import subprocess
import sys

import pikepdf
import pypdfium2 as pdfium
from PIL import ImageChops

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine.classify_run import classify_document


def render(page):
    bitmap=page.render(scale=1)
    try:return bitmap.to_pil().convert('RGB')
    finally:bitmap.close()


def verify(directory: Path):
    source=directory/'highlights.pdf'
    assert (directory/'after-highlighting.pdf').read_bytes()==source.read_bytes()
    assert (directory/'after-stale-source.pdf').read_bytes()==source.read_bytes()
    assert (directory/'undo-removal.pdf').read_bytes()==(directory/'replaced.pdf').read_bytes()
    names=('after-highlighting','replaced','removed','undo-removal')
    with pdfium.PdfDocument(source) as original:
        for name in names:
            path=directory/f'{name}.pdf'
            for command in (['qpdf','--check'],['pdfcpu','validate','--mode','strict']):
                subprocess.run([*command,str(path)],check=True,capture_output=True)
            with pikepdf.open(path) as pdf:
                assert len(pdf.pages)==3
                assert not any(page.obj.get('/Annots') for page in pdf.pages)
                assert pdf.pages[1].obj.Rotate==90 and pdf.pages[1].obj.UserUnit==2
                assert list(pdf.pages[1].obj.CropBox)==[20,40,580,760]
            with pdfium.PdfDocument(path) as output:
                for number in range(3):
                    page=output[number];extraction=page.get_textpage()
                    try:actual=extraction.get_text_range()
                    finally:extraction.close()
                    assert 'Neighbor remains unchanged' in actual
                    assert 'café CAFÉ' in actual
                    if name in ('replaced','undo-removal') and number<2:
                        assert actual.count('otter')==2 and 'cat' not in actual
                    if name=='removed' and number<2:
                        assert 'otter' not in actual and 'alpha' in actual and 'omega' in actual
                    difference=ImageChops.difference(render(original[number]),render(page))
                    if name!='after-highlighting' and number==0:difference.paste((0,0,0),(58,102,400,134))
                    if name!='after-highlighting' and number==1:difference.paste((0,0,0),(630,35,670,350))
                    assert difference.getbbox() is None,(name,number,'Unrelated PDF pixels changed')
    before=classify_document(source).runs
    for name in ('replaced','removed','undo-removal'):
        after=classify_document(directory/f'{name}.pdf').runs
        for run,_ in before:
            if run.display_text not in ('Neighbor remains unchanged','café CAFÉ'):continue
            match=next(other for other,_ in after if other.page==run.page and other.display_text==run.display_text)
            assert [(g.x,g.y) for g in match.glyphs]==[(g.x,g.y) for g in run.glyphs]
    result={'passed':True,'byte_identity_checks':3,'structural_validations':8,
        'unrelated_pixel_comparisons':12,'searchable_replacement_and_neighbor_glyphs':True,
        'viewer_highlights_not_exported':True}
    (directory/'native-results.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    print(json.dumps(verify(Path(sys.argv[1] if len(sys.argv)>1 else '/private/tmp/pdf-tool-highlights-20261029')),indent=2))
