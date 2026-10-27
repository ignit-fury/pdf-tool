"""Deliberate G6 fixtures and independent output oracles (dev/test only).

The painted reference never calls flatten or reuses annotation appearance streams.
Exact region unions are derived from crop/rotation and each engine's actual raster
extent, preserving the known UserUnit renderer disagreement without tolerances.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path
import random
import shutil
import zipfile

import pikepdf
from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
RECTS = [(24, 24, 72, 48), (96, 72, 168, 96), (144, 24, 192, 48)]


def _save(pdf, path):
    pdf.save(path, compress_streams=False, object_stream_mode=pikepdf.ObjectStreamMode.disable,
             static_id=True)


def _font(pdf):
    return pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font,
        Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica))


def _annotation_source(path, *, painted=False):
    with pikepdf.Pdf.new() as pdf:
        font = _font(pdf)
        resources = pdf.make_indirect(pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font)))
        fields = []
        for index in range(3):
            page = pdf.add_blank_page(page_size=(216, 144))
            page.obj.Resources = resources
            page.obj.G6Page = index
            if index == 1:
                page.obj.CropBox = [12, 12, 204, 132]
                page.obj.Rotate = 90
                page.obj.UserUnit = 1.25
            base = (f'q .9 .9 .9 rg 12 108 192 12 re f '
                    f'0 0 {0.2 + index * 0.3:.1f} rg 12 12 6 6 re f Q\n').encode()
            if index < 2 and painted:
                # Written directly in page space, independently of native AP math.
                base += (b'q 1 0 0 rg 24 24 48 24 re f Q\n'
                         b'q 0 1 0 rg 96 72 72 24 re f 0 0 0 rg '
                         b'BT /F1 9 Tf 100 80 Td (FILLED) Tj ET Q\n'
                         b'q 0 0 1 rg 144 24 48 24 re f '
                         b'0 0 0 rg 168 24 24 12 re f Q\n')
            page.obj.Contents = pdf.make_stream(base)
            if index >= 2 or painted:
                continue
            ap_specs = [
                (b'q 1 0 0 rg 0 0 48 24 re f Q', [0, 0, 48, 24], None),
                (b'q 0 1 0 rg 0 0 72 24 re f 0 0 0 rg BT /F1 9 Tf 4 8 Td (FILLED) Tj ET Q',
                 [0, 0, 72, 24], None),
                (b'q 0 0 1 rg 0 0 24 24 re f 0 0 0 rg 0 0 12 12 re f Q',
                 [0, 0, 24, 24], [0, 1, -1, 0, 24, 0]),
            ]
            annots = []
            for ordinal, (content, bbox, matrix) in enumerate(ap_specs):
                appearance = pdf.make_stream(content)
                appearance.update(pikepdf.Dictionary(Type=pikepdf.Name.XObject,
                    Subtype=pikepdf.Name.Form, BBox=bbox, Resources=resources))
                if matrix:
                    appearance.Matrix = matrix
                annot = pikepdf.Dictionary(Type=pikepdf.Name.Annot,
                    Subtype=pikepdf.Name.Stamp if ordinal == 0 else pikepdf.Name.Widget,
                    Rect=RECTS[ordinal], F=4, P=page.obj)
                if ordinal == 1:
                    annot.update(pikepdf.Dictionary(FT=pikepdf.Name.Tx,
                        T=f'filled-{index}', V='FILLED', DA='/F1 9 Tf 0 g'))
                if ordinal == 2:
                    annot.update(pikepdf.Dictionary(FT=pikepdf.Name.Btn,
                        T=f'checked-{index}', V=pikepdf.Name.Yes, AS=pikepdf.Name.Yes))
                    annot.AP = pikepdf.Dictionary(N=pikepdf.Dictionary(Yes=appearance))
                else:
                    annot.AP = pikepdf.Dictionary(N=appearance)
                obj = pdf.make_indirect(annot)
                annots.append(obj)
                if ordinal:
                    fields.append(obj)
            page.obj.Annots = annots
        if not painted:
            pdf.Root.AcroForm = pikepdf.Dictionary(Fields=fields, DA='/F1 9 Tf 0 g', DR=resources,
                                                 NeedAppearances=False)
        pdf.Root.Names = pikepdf.Dictionary(Dests=pikepdf.Dictionary(
            Names=pikepdf.Array(['target', pikepdf.Array([pdf.pages[1].obj, pikepdf.Name.Fit])])))
        _save(pdf, path)


def build_fixtures(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    _annotation_source(directory / 'annotations.pdf')
    _annotation_source(directory / 'painted-reference.pdf', painted=True)
    for filename, unsafe in [('missing-appearance.pdf', False), ('unsafe-appearance.pdf', True)]:
        with pikepdf.open(directory / 'annotations.pdf') as pdf:
            if unsafe:
                pdf.pages[0].Annots[0].AP.N.Matrix = [0, 0, 0, 0, 0, 0]
            else:
                del pdf.pages[0].Annots[1]['/AP']
            _save(pdf, directory / filename)
    with pikepdf.Pdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(216, 144))
        image = pdf.make_stream(random.Random(73).randbytes(2048 * 1024 * 3))
        image.update(pikepdf.Dictionary(Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image,
            Width=2048, Height=1024, BitsPerComponent=8, ColorSpace=pikepdf.Name.DeviceRGB))
        page.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im=image))
        page.obj.Contents = pdf.make_stream(b'q 0 0 1 rg 12 12 12 12 re f '
                                          b'144 0 0 72 36 48 cm /Im Do Q')
        _save(pdf, directory / 'image.pdf')
    # Two-page public form: bounded real structural-compression coverage, all pages.
    corpus = ROOT / 'corpus/public/irs_form_1040.pdf'
    shutil.copyfile(corpus, directory / 'corpus.pdf')
    sources = ['annotations.pdf', 'painted-reference.pdf', 'missing-appearance.pdf',
               'unsafe-appearance.pdf', 'image.pdf', 'corpus.pdf']
    data = {'sources': [{'file': file, 'sha256': hashlib.sha256((directory / file).read_bytes()).hexdigest()}
                        for file in sources],
            'corpusSource': str(corpus),
            'geometry': {'0': {'crop': [0, 0, 216, 144], 'rotation': 0, 'userUnit': 1, 'rects': RECTS},
                         '1': {'crop': [12, 12, 204, 132], 'rotation': 90, 'userUnit': 1.25, 'rects': RECTS},
                         '2': {'crop': [0, 0, 216, 144], 'rotation': 0, 'userUnit': 1, 'rects': []}},
            'image_geometry': {'crop': [0, 0, 216, 144], 'rotation': 0, 'userUnit': 1,
                               'rects': [[36, 48, 180, 120]]}}
    manifest = directory / 'fixtures.json'
    manifest.write_text(json.dumps(data, indent=2))
    return manifest


def _rgb(value):
    if isinstance(value, Image.Image):
        return value.convert('RGB')
    with Image.open(value) as image:
        return image.convert('RGB')


def assert_exact_pixels(expected, actual):
    a, b = _rgb(expected), _rgb(actual)
    assert a.size == b.size, f'raster size: {a.size} != {b.size}'
    assert ImageChops.difference(a, b).getbbox() is None, 'pixels differ outside permitted regions'


def physical_regions(geometry, raster_size):
    x0, y0, x1, y1 = geometry['crop']
    w, h = x1 - x0, y1 - y0
    rotation = geometry['rotation'] % 360
    width, height = (h, w) if rotation % 180 else (w, h)
    sx, sy = raster_size[0] / width, raster_size[1] / height
    def point(x, y):
        x, y = x - x0, y - y0
        if rotation == 90:
            return y * sx, x * sy
        if rotation == 180:
            return (w - x) * sx, y * sy
        if rotation == 270:
            return (h - y) * sx, (w - x) * sy
        return x * sx, (h - y) * sy
    result = []
    for left, bottom, right, top in geometry['rects']:
        corners = [point(x, y) for x in (left, right) for y in (bottom, top)]
        # Only pixels intersecting the exact physical rectangle, no padding.
        result.append((math.floor(min(x for x, _ in corners)), math.floor(min(y for _, y in corners)),
                       math.ceil(max(x for x, _ in corners)), math.ceil(max(y for _, y in corners))))
    return result


def assert_region_pixels(expected, actual, regions, *, check_inside=True):
    a, b = _rgb(expected), _rgb(actual)
    assert a.size == b.size, f'raster size: {a.size} != {b.size}'
    diff = ImageChops.difference(a, b)
    mask = Image.new('L', a.size, 0)
    draw = ImageDraw.Draw(mask)
    for left, top, right, bottom in regions:
        assert right > left and bottom > top, 'appearance region must be nonempty'
        draw.rectangle((left, top, right - 1, bottom - 1), fill=255)
    outside = ImageChops.composite(Image.new('RGB', a.size), diff, mask)
    assert outside.getbbox() is None, 'pixels differ outside exact annotation/image region union'
    if check_inside:
        for region in regions:
            assert diff.crop(region).getbbox() is None, 'saved appearance differs from independent painted reference'


def assert_archive(data: bytes, entries: dict[str, bytes]):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            assert archive.namelist() == list(entries), 'archive entries/count/order'
            assert archive.testzip() is None, 'archive CRC mismatch'
            for info in archive.infolist():
                assert not info.is_dir() and info.compress_type == zipfile.ZIP_STORED, 'archive header'
                assert archive.read(info) == entries[info.filename], 'archive extracted bytes'
    except zipfile.BadZipFile as error:
        raise AssertionError('archive CRC/header/central directory invalid') from error


def _contents(page):
    value = page.obj.get('/Contents', [])
    return (value.read_bytes() if isinstance(value, pikepdf.Stream)
            else b'\n'.join(stream.read_bytes() for stream in value))


def assert_page_mapping(source, actual, mapping):
    assert len(actual.pages) == len(mapping), 'split page count mismatch'
    for page, index in zip(actual.pages, mapping, strict=True):
        expected = source.pages[index]
        for key, default in [('/MediaBox', None), ('/CropBox', expected.MediaBox),
                             ('/Rotate', 0), ('/UserUnit', 1)]:
            left, right = page.obj.get(key, default), expected.obj.get(key, default)
            assert left == right, f'mapping geometry {key}'
        if '/G6Page' in expected.obj:
            assert page.obj.get('/G6Page') == expected.obj.G6Page, 'mapping physical page identity'


def resource_fingerprint(page):
    """Semantic resource values and decoded streams; ignore serializer object IDs."""
    def visit(value, stack=()):
        if isinstance(value, (pikepdf.Dictionary, pikepdf.Stream)):
            identity = value.objgen
            if identity != (0, 0) and identity in stack:
                return 'cycle'
            child_stack = (*stack, identity) if identity != (0, 0) else stack
            pairs = {str(key): visit(child, child_stack) for key, child in sorted(value.items())
                     if str(key) not in ('/Length', '/Filter', '/DecodeParms')}
            if isinstance(value, pikepdf.Stream):
                pairs['decodedSha256'] = hashlib.sha256(value.read_bytes()).hexdigest()
            return pairs
        if isinstance(value, pikepdf.Array):
            return [visit(child, stack) for child in value]
        return str(value)
    return visit(page.Resources)


def image_samples(pdf):
    result = []
    for obj in pdf.objects:
        if isinstance(obj, pikepdf.Stream) and obj.get('/Subtype') == pikepdf.Name.Image:
            with pikepdf.PdfImage(obj).as_pil_image() as image:
                result.append((image.mode, image.size, hashlib.sha256(image.tobytes()).hexdigest()))
    return sorted(result)


def assert_graph(pdf):
    pages = {page.obj.objgen for page in pdf.pages}
    widgets = {}
    for page in pdf.pages:
        for annot in page.obj.get('/Annots', []):
            if annot.get('/Subtype') == pikepdf.Name.Widget:
                assert annot.get('/P') is not None and annot.P.objgen == page.obj.objgen, 'widget physical page'
                widgets[annot.objgen] = annot
    fields = set()
    def field(value):
        assert value.objgen not in fields, 'widget field cycle'
        fields.add(value.objgen)
        if value.get('/Subtype') == pikepdf.Name.Widget:
            assert value.objgen in widgets, 'widget field ownership'
        for child in value.get('/Kids', []):
            field(child)
    for value in pdf.Root.get('/AcroForm', {}).get('/Fields', []):
        field(value)
    assert set(widgets) <= fields, 'widget detached from field tree'
    names = pdf.Root.get('/Names', {}).get('/Dests', {}).get('/Names', [])
    for index in range(1, len(names), 2):
        value = names[index]
        dest = value.get('/D') if isinstance(value, pikepdf.Dictionary) else value
        assert dest[0].objgen in pages, 'destination detached from physical page tree'
