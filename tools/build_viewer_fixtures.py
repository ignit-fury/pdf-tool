"""Synthetic browser test inputs; no source-corpus or user-document mutations."""
from pathlib import Path
import sys
import pikepdf
from PIL import Image, ImageDraw


def build(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with pikepdf.Pdf.new() as pdf:
        font = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font,
            Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica))
        for number in range(1, 13):
            page = pdf.add_blank_page(page_size=(600, 800))
            page.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
            page.obj.Contents = pdf.make_stream((
                f'BT /F1 20 Tf 1 0 0 1 60 730 Tm (Document page {number}) Tj ET\n'
                'BT /F1 12 Tf 1 0 0 1 60 680 Tm (Hello world) Tj ET\n'
                'BT /F1 12 Tf 1 0 0 1 60 640 Tm (Hello world) Tj ET\n'
                'BT /F1 12 Tf 1 0 0 1 60 600 Tm (Neighbor must stay unchanged) Tj ET\n'
            ).encode())
        pdf.save(directory / 'viewer-fixture.pdf')
        pdf.save(directory / 'unicode-password.pdf', encryption=pikepdf.Encryption(owner='owner', user='密碼', R=6))
    image = Image.new('RGB', (160, 100), '#e3e8ef')
    draw = ImageDraw.Draw(image)
    draw.rectangle((15, 15, 145, 85), fill='#2458df')
    draw.text((30, 40), 'Image preview', fill='white')
    image.save(directory / 'image.png')
    image.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(directory / 'replacement.webp')


if __name__ == '__main__':
    build(Path(sys.argv[1] if len(sys.argv)>1 else '/private/tmp/pdf-tool-viewer-20261029'))
