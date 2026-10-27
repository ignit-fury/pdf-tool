"""Small reproducible layout specimens; public corpus tags lack these categories.

No downloaded corpus, OCR or renderer is required. Consumers assert extracted
content AND actual page operators/resources, so these specimens cannot pass empty.
"""
from pathlib import Path

import pikepdf


def build_export_fixture(path: Path, *, ruled: bool | str = True) -> None:
    with pikepdf.Pdf.new() as pdf:
        fonts = pikepdf.Dictionary()
        for resource, name in [('F1', 'Helvetica'), ('F2', 'Helvetica-Bold'), ('F3', 'Helvetica-Oblique')]:
            fonts['/' + resource] = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name('/' + name)))
        page = pdf.add_blank_page(page_size=(500, 600))
        page.Resources = pikepdf.Dictionary(Font=fonts)
        lines = [('F2',24,40,550,'Export heading'),
                 ('F1',12,40,500,'Left first'), ('F1',12,40,484,'Left second'),
                 ('F1',12,300,500,'Right first'), ('F1',12,300,484,'Right second'),
                 ('F2',12,40,400,'Bold body'), ('F3',12,40,360,'Italic body'),
                 ('F1',12,40,320,'- First item')]
        page.Contents = pdf.make_stream('\n'.join(f'BT /{f} {s} Tf {x} {y} Td ({t}) Tj ET' for f,s,x,y,t in lines).encode())
        table = pdf.add_blank_page(page_size=(500, 600))
        table.Resources = pikepdf.Dictionary(Font=fonts)
        ruling = ''
        if ruled:
            ruling = '40 400 240 100 re S 160 400 m 160 500 l S '
            if ruled is True:
                ruling += '40 450 m 280 450 l S '
            else:
                ruling += '40 450 m 150 450 l S '
        rows = [(50,475,'A1'),(170,475,'B1'),(50,425,'A2'),(170,425,'B2')]
        table.Contents = pdf.make_stream((ruling + '\n'.join(f'BT /F1 12 Tf {x} {y} Td ({t}) Tj ET' for x,y,t in rows)).encode())
        scanned = pdf.add_blank_page(page_size=(500,600))
        image = pdf.make_stream(bytes([255,255,255]))
        image.Type = pikepdf.Name.XObject
        image.Subtype = pikepdf.Name.Image
        image.Width, image.Height = 1, 1
        image.ColorSpace, image.BitsPerComponent = pikepdf.Name.DeviceRGB, 8
        scanned.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im=image))
        scanned.Contents = pdf.make_stream(b'q 500 0 0 600 0 0 cm /Im Do Q')
        pdf.save(path)
