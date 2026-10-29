"""Synthetic native text-box browser fixtures, never user/corpus mutations."""
from pathlib import Path
import sys
import zlib
import pikepdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build_viewer_fixtures import build


def build_text_boxes(directory: Path) -> None:
    build(directory)
    with pikepdf.open(directory / 'viewer-fixture.pdf') as pdf:
        page = pdf.pages[0]
        image = pdf.make_stream(zlib.compress(bytes([40, 90, 180])*16*16))
        image.Type = pikepdf.Name.XObject
        image.Subtype = pikepdf.Name.Image
        image.Width = image.Height = 16
        image.BitsPerComponent = 8
        image.ColorSpace = pikepdf.Name.DeviceRGB
        image.Filter = pikepdf.Name.FlateDecode
        page.obj.Resources.XObject = pikepdf.Dictionary(Im0=image)
        page.obj.Contents = pikepdf.Array([page.obj.Contents,
            pdf.make_stream(b'q 60 0 0 60 500 700 cm /Im0 Do Q\n')])
        page.obj.Annots = pikepdf.Array([pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Link,
            Rect=[350, 500, 420, 530], Border=[0, 0, 0],
            A=pikepdf.Dictionary(S=pikepdf.Name.URI, URI=pikepdf.String('https://example.invalid/'))))])
        pdf.save(directory / 'source.pdf')
        pdf.save(directory / 'unicode-source.pdf', encryption=pikepdf.Encryption(owner='owner', user='密碼', R=6))
        with pikepdf.Pdf.new() as rotated:
            rotated.pages.append(page)
            rotated.pages[0].obj.CropBox = [40, 60, 550, 750]
            rotated.pages[0].obj.Rotate = 90
            rotated.pages[0].obj.UserUnit = 2
            rotated.save(directory / 'rotated-source.pdf')


if __name__ == '__main__':
    build_text_boxes(Path(sys.argv[1] if len(sys.argv)>1 else '/private/tmp/pdf-tool-text-boxes-20261029'))
