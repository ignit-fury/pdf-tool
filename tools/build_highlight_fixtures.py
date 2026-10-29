"""Synthetic repeated, normalized, rotated and ambiguous search text."""
from pathlib import Path
import sys

import pikepdf


def build(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    with pikepdf.Pdf.new() as pdf:
        font=pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font,Subtype=pikepdf.Name.Type1,
            BaseFont=pikepdf.Name.Helvetica,Encoding=pikepdf.Name.WinAnsiEncoding))
        for number in range(3):
            page=pdf.add_blank_page(page_size=(600,800))
            page.obj.Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
            content=(b'BT /F1 16 Tf 1 0 0 1 60 680 Tm (alpha cat cat omega) Tj ET\n'
                b'BT /F1 14 Tf 1 0 0 1 60 630 Tm (caf\xe9 CAF\xc9) Tj ET\n'
                b'BT /F1 12 Tf 1 0 0 1 60 580 Tm (Neighbor remains unchanged) Tj ET\n')
            if number==2:
                content+=b'BT /F1 16 Tf 1 0 0 1 60 680 Tm (alpha cat cat omega) Tj ET\n'
            page.obj.Contents=pdf.make_stream(content)
            if number==1:
                page.obj.Rotate=90;page.obj.CropBox=[20,40,580,760];page.obj.UserUnit=2
        pdf.save(directory/'highlights.pdf',min_version='1.6')


if __name__=='__main__':
    build(Path(sys.argv[1] if len(sys.argv)>1 else '/private/tmp/pdf-tool-highlights-20261029'))
