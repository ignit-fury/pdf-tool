"""Check actual source-expansion browser downloads, including genuine removal."""
from pathlib import Path
import io
import json
import math
import subprocess
import sys

import pikepdf
import pypdfium2 as pdfium
from PIL import ImageChops

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine.text_boxes import prepare_text_box


def render(page):
    bitmap=page.render(scale=1)
    try:return bitmap.to_pil().convert('RGB')
    finally:bitmap.close()


def verify(directory: Path):
    before=(directory/'before-expansion.pdf').read_bytes()
    assert (directory/'after-cancel.pdf').read_bytes()==before
    assert (directory/'undone.pdf').read_bytes()==before
    assert (directory/'redone.pdf').read_bytes()==(directory/'expanded.pdf').read_bytes()
    comparisons=0
    with pdfium.PdfDocument(before) as original:
        for name in ('expanded','grown-again'):
            data=(directory/f'{name}.pdf').read_bytes()
            for command in (['qpdf','--check'],['pdfcpu','validate','--mode','strict']):
                subprocess.run([*command,str(directory/f'{name}.pdf')],check=True,capture_output=True)
            with pikepdf.open(io.BytesIO(data)) as pdf:
                box=prepare_text_box(pdf,data,{'operation':'list'})['boxes'][0]
                assert len(pdf.pages)==12
                assert len(pdf.pages[0].obj.Annots)==1
                assert str(pdf.pages[0].obj.Annots[0].A.URI)=='https://example.invalid/'
            with pdfium.PdfDocument(data) as output:
                for number in range(12):
                    extraction=output[number].get_textpage()
                    try:text=extraction.get_text_range()
                    finally:extraction.close()
                    assert text.count('Hello world')==2
                    assert ('Neighbor intact' if number==0 else 'Neighbor must stay unchanged') in text
                    if number==0:
                        assert 'Document page 1' not in text and 'Second title line' in text
                        if name=='grown-again':assert 'Third line needs room' in text
                    else:assert f'Document page {number+1}' in text
                    difference=ImageChops.difference(render(original[number]),render(output[number]))
                    if number==0:
                        difference.paste((0,0,0),(55,45,300,85))
                        r=box['rect'];difference.paste((0,0,0),(math.floor(r['left'])-1,math.floor(r['top'])-1,math.ceil(r['left']+r['width'])+1,math.ceil(r['top']+r['height'])+1))
                    assert difference.getbbox() is None,(name,number,'Unrelated pixels changed')
                    comparisons+=1
    result={'passed':True,'byte_identity_checks':3,'structural_validations':4,'unrelated_pixel_comparisons':comparisons,'original_source_text_removed':True,'prior_recipe_preserved':True}
    (directory/'native-results.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    print(json.dumps(verify(Path(sys.argv[1] if len(sys.argv)>1 else '/private/tmp/pdf-tool-source-expansion-20261029')),indent=2))
