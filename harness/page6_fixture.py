"""Independent, bounded G5 fixtures and acceptance assertions (dev tooling only)."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pikepdf
from PIL import Image, ImageChops

from harness.masked_diff import masked_pixel_diff

ROOT = Path(__file__).resolve().parents[1]
FONTS = [
    ('govdocs1_003_003063.pdf', 0, '/TT2', 'CCEBGE+Arial',
     '8c54d9074cb803ce67f4bc1db58cfcd8defca27d27407a39a5c0f6f48dfe5a5b'),
    ('govdocs1_001_001038.pdf', 2, '/TT0', 'ACKMHB+Arial',
     '674ab0feea74f3f5ae754f3223bde2bfa75473b56cb455172bee5318907d584e'),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def font_provenance(page, key):
    font = page.Resources.Font[key]
    active = None
    letters = set()
    for instruction in pikepdf.parse_content_stream(page):
        op, args = str(instruction.operator), instruction.operands
        if op == 'Tf':
            active = str(args[0])
        if active != key:
            continue
        values = ([args[0]] if op in ('Tj', "'") else
                  [args[2]] if op == '"' else list(args[0]) if op == 'TJ' else [])
        for value in values:
            if isinstance(value, pikepdf.String):
                letters.update(c for c in bytes(value) if 65 <= c <= 90 or 97 <= c <= 122)
    assert letters, 'selected font must actually execute nonspace letter codes'
    return {'baseFont': str(font.BaseFont), 'fontName': str(font.FontDescriptor.FontName),
            'programSha256': hashlib.sha256(font.FontDescriptor.FontFile2.read_bytes()).hexdigest(),
            'usedLetters': ''.join(chr(c) for c in sorted(letters))}


def _simple(path, *, inherited=False, rotation=0, shared=True):
    pdf = pikepdf.Pdf.new()
    resources = pdf.make_indirect(pikepdf.Dictionary(Font=pikepdf.Dictionary(
        F1=pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font,
            Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)))))
    for index in range(2):
        page = pdf.add_blank_page(page_size=(160, 120))
        page.obj.MediaBox = [10, 20, 170, 140]
        page.obj.CropBox = [20, 30, 150, 130]
        page.obj.Rotate = rotation
        page.obj.UserUnit = 2
        page.obj.Resources = resources if shared else pikepdf.Dictionary(resources)
        page.obj.Contents = pdf.make_stream(
            f'q 0.2 0.4 0.7 rg {30+index*10} 45 20 20 re f Q\nBT /F1 10 Tf 30 95 Td (Page {index}) Tj ET'.encode())
    if inherited:
        pdf.Root.Pages.Resources = resources
        for page in pdf.pages:
            del page.obj.Resources
    pdf.save(path)


def _graph(path, *, unsafe=False):
    pdf = pikepdf.Pdf.new()
    page = pdf.add_blank_page(page_size=(160, 120))
    font = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font,
        Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica))
    page.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(Helv=font))
    page.obj.Contents = pdf.make_stream(b'BT /Helv 12 Tf 15 95 Td (Graph fixture) Tj ET')
    page.obj.Annots = []
    fields = []
    parent = pdf.make_indirect(pikepdf.Dictionary(T='group', Kids=[]))
    for i, kind in enumerate(('Tx', 'Btn', 'Ch', 'Sig')):
        field = pdf.make_indirect(pikepdf.Dictionary(FT=pikepdf.Name('/'+kind),
            T='field'+str(i), Parent=parent, DA='/Helv 9 Tf 0 g', Kids=[]))
        if kind == 'Tx':
            field.V = 'value'
        if kind == 'Btn':
            field.V = pikepdf.Name.Yes
        if kind == 'Ch':
            field.Opt = ['one', 'two']
            field.V = 'two'
        ap = pdf.make_stream(b'q 0.7 0.1 0.2 rg 0 0 20 10 re f Q')
        ap.Type = pikepdf.Name.XObject
        ap.Subtype = pikepdf.Name.Form
        ap.BBox = [0, 0, 20, 10]
        ap.Resources = pikepdf.Dictionary()
        normal = pikepdf.Dictionary(Off=ap, Yes=ap) if kind == 'Btn' else ap
        widget = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Annot,
            Subtype=pikepdf.Name.Widget, Rect=[15+i*30, 20, 35+i*30, 30],
            Parent=field, P=page.obj, AP=pikepdf.Dictionary(N=normal), F=4))
        if kind == 'Btn':
            widget.AS = pikepdf.Name.Yes
        field.Kids.append(widget)
        fields.append(field)
        page.obj.Annots.append(widget)
    parent.Kids = fields
    pdf.Root.AcroForm = pdf.make_indirect(pikepdf.Dictionary(Fields=[parent],
        DR=pikepdf.Dictionary(Font=pikepdf.Dictionary(Helv=font)),
        DA='/Helv 9 Tf 0 g', CO=[fields[0]], NeedAppearances=False))
    outline = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Outlines, Count=2))
    first = pdf.make_indirect(pikepdf.Dictionary(Title='parent', Parent=outline,
        Dest='chapter', Count=1))
    child = pdf.make_indirect(pikepdf.Dictionary(Title='child', Parent=first,
        A=pikepdf.Dictionary(S=pikepdf.Name.GoTo, D=[page.obj, pikepdf.Name.Fit])))
    first.First = child
    first.Last = child
    outline.First = first
    outline.Last = first
    pdf.Root.Outlines = outline
    pdf.Root.Names = pikepdf.Dictionary(Dests=pikepdf.Dictionary(
        Names=['chapter', [page.obj, pikepdf.Name.Fit]]))
    pdf.Root.OpenAction = [page.obj, pikepdf.Name.Fit]
    link = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Annot,
        Subtype=pikepdf.Name.Link, Rect=[10, 60, 60, 75], P=page.obj,
        A=pikepdf.Dictionary(S=pikepdf.Name.GoTo, D='chapter')))
    page.obj.Annots.append(link)
    if unsafe:
        pdf.Root.AcroForm.XFA = 'unsafe'
    pdf.save(path)


def _scanned(directory):
    pdf = pikepdf.Pdf.new()
    for color in ((30, 70, 210), (220, 60, 20)):
        page = pdf.add_blank_page(page_size=(240, 160))
        image = pdf.make_stream(Image.new('RGB', (10, 10), color).tobytes())
        image.Type, image.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
        image.Width = image.Height = 10
        image.ColorSpace, image.BitsPerComponent = pikepdf.Name.DeviceRGB, 8
        page.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Scan=image))
        page.obj.Contents = pdf.make_stream(b'q 200 0 0 120 20 20 cm /Scan Do Q')
    pdf.save(directory / 'scanned.pdf')
    pdf.pages[0].obj.Rotate = 90
    pdf.save(directory / 'scanned-rotated-reference.pdf')
    blank = pikepdf.Pdf.new()
    blank.add_blank_page(page_size=(240, 160))
    blank.save(directory / 'scanned-blank-reference.pdf')


def build_fixtures(directory):
    directory = Path(directory)
    sources, fonts = [], []
    for index, (filename, page_index, key, base, digest) in enumerate(FONTS):
        source = ROOT / 'corpus/public' / filename
        sources.append({'path': str(source), 'sha256': sha(source)})
        with pikepdf.open(source) as original:
            measured = font_provenance(original.pages[page_index], key)
            assert measured['programSha256'] == digest
            assert measured['baseFont'] == '/'+base
            fonts.append(measured)
            out = pikepdf.Pdf.new()
            out.pages.append(original.pages[page_index])
            out.save(directory / f'font-real-{index}.pdf')
            font = out.pages[0].Resources.Font[key]
            font.BaseFont = pikepdf.Name('/ABCDEF+Arial')
            font.FontDescriptor.FontName = pikepdf.Name('/ABCDEF+Arial')
            out.save(directory / f'font-literal-{index}.pdf')
    assert fonts[0]['programSha256'] != fonts[1]['programSha256']
    for inherited in (False, True):
        for rotation in (0, 90, 180, 270):
            _simple(directory / f'resources-{int(inherited)}-{rotation}.pdf',
                    inherited=inherited, rotation=rotation)
    # Independent empty reference with inherited physical geometry.
    blank = pikepdf.Pdf.new()
    page = blank.add_blank_page(page_size=(160, 120))
    page.obj.MediaBox = [10, 20, 170, 140]
    page.obj.CropBox = [20, 30, 150, 130]
    page.obj.UserUnit = 2
    page.obj.Rotate = 0
    blank.save(directory / 'blank-reference.pdf')
    # Explicit 90-degree/crop-origin/UserUnit normalization reference.
    # x'=2(y-30), y'=2(150-x); clip in the original coordinate space.
    with pikepdf.open(directory / 'resources-0-90.pdf') as src:
        for index in range(2):
            normalized = pikepdf.Pdf.new()
            normalized.pages.append(src.pages[index])
            page = normalized.pages[0]
            original = page.obj.Contents.read_bytes()
            page.obj.Contents = normalized.make_stream(
                b'q 0 -2 2 0 -60 300 cm 20 30 130 100 re W n\n' + original + b'\nQ')
            page.obj.MediaBox = [0, 0, 200, 260]
            page.obj.CropBox = [0, 0, 200, 260]
            page.obj.Rotate = 0
            page.obj.UserUnit = 1
            normalized.save(directory / ('normalized-reference.pdf' if index == 0 else 'normalized-reference-1.pdf'))
    _graph(directory / 'graph-source.pdf')
    _graph(directory / 'unsafe-source.pdf', unsafe=True)
    _scanned(directory)
    # Fully flattened, oriented PNG. Browser native decode/compositing is a separate gate.
    image = Image.new('RGBA', (12, 8), (0, 0, 0, 0))
    for x in range(6):
        for y in range(8):
            image.putpixel((x, y), (240, 30, 10, 128))
    white = Image.new('RGBA', image.size, 'white')
    white.alpha_composite(image)
    white.convert('RGB').save(directory / 'white-flattened.png')
    rect = {'left': 24, 'top': 26, 'width': 48, 'height': 32}
    for inherited in (0, 1):
        for rotation in (0, 90, 180, 270):
            for region in (False, True):
                _image_reference(directory / f'resources-{inherited}-{rotation}.pdf',
                    directory / f'image-{"region" if region else "expected"}-{inherited}-{rotation}.pdf',
                    white.convert('RGB'), rect, rotation, region=region)
    _image_reference(directory / 'blank-reference.pdf', directory / 'image-new-page-reference.pdf',
                     white.convert('RGB'), {'left': 0, 'top': 40/3, 'width': 260, 'height': 520/3}, 0)
    sources.extend({'path': str(file), 'sha256': sha(file)}
                   for file in sorted(directory.glob('*')) if file.is_file())
    manifest = {'sources': sources, 'fonts': fonts,
                'fontOriginals': [{'file': str(ROOT / 'corpus/public' / f[0]), 'page': f[1]} for f in FONTS]}
    target = directory / 'fixtures.json'
    target.write_text(json.dumps(manifest, indent=2))
    return target


def _image_reference(source, output, image, rect, rotation, *, region=False):
    """Independent PDF writer, only for the acceptance oracle, never materialization.

    Region file is an image-only black tile, so native raster crop rounding defines
    its exact footprint. The expected file uses independently decoded RGB pixels.
    Neither reference reads production output or production geometry helpers.
    """
    with pikepdf.open(source) as pdf:
        page = pdf.pages[0]
        # Explicit inverse crop rotations, UserUnit=2, CropBox=(20,30,150,130).
        l, t, w, h = (rect[k]/2 for k in ('left', 'top', 'width', 'height'))
        matrix = {0: [w, 0, 0, h, 20+l, 130-t-h],
                  90: [0, w, -h, 0, 20+t+h, 30+l],
                  180: [-w, 0, 0, -h, 150-l, 30+t+h],
                  270: [0, -w, h, 0, 150-t-h, 130-l]}[rotation]
        pixels = Image.new('RGB', image.size, 'black') if region else image
        stream = pdf.make_stream(pixels.tobytes())
        stream.Type, stream.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
        stream.Width, stream.Height = image.size
        stream.ColorSpace, stream.BitsPerComponent = pikepdf.Name.DeviceRGB, 8
        resources = pikepdf.Dictionary(page.Resources)
        resources.XObject = pikepdf.Dictionary(G5Image=stream)
        page.obj.Resources = resources
        content = b'' if region else page.obj.Contents.read_bytes()
        page.obj.Contents = pdf.make_stream(content + b'\nq ' +
            ' '.join(str(v) for v in matrix).encode() + b' cm /G5Image Do Q\n')
        # These are one-page oracles; siblings stay covered by their own source.
        while len(pdf.pages) > 1:
            del pdf.pages[1]
        pdf.save(output)


def assert_pixels(before, after, rect=None, *, changed=False, region=None):
    unmasked = masked_pixel_diff(before, after)
    mask = None
    if region:
        with Image.open(region) as image:
            image = image.convert('RGB')
            mask = ImageChops.difference(image, Image.new('RGB', image.size, 'white')).getbbox()
            assert mask is not None, 'independent image footprint must be nonempty'
            assert (mask[2]-mask[0]) * (mask[3]-mask[1]) < image.width*image.height/4, 'mask must cover only target image'
    elif rect:
        raise AssertionError('image placement requires independently rendered intended footprint')
    outside = masked_pixel_diff(before, after, mask)
    assert outside == 0, f'outside intended image region changed pixels: {outside}'
    if changed:
        assert unmasked > 0, 'image placement must have nonvacuous visible change'
    return unmasked, outside


def assert_graph(pdf):
    pages = {page.obj.objgen for page in pdf.pages}
    widgets, fields, field_types, appearances = {}, {}, set(), []
    destinations = {}
    names = pdf.Root.get('/Names', {}).get('/Dests')
    def name_tree(node):
        values = node.get('/Names', [])
        assert len(values) % 2 == 0, 'destination name pairs'
        for index in range(0, len(values), 2):
            destinations[str(values[index])] = values[index+1]
        for kid in node.get('/Kids', []):
            name_tree(kid)
    if names is not None:
        name_tree(names)
    destinations.update({str(k): v for k, v in pdf.Root.get('/Dests', {}).items()})
    def dest(value):
        if isinstance(value, (pikepdf.String, pikepdf.Name)):
            assert str(value) in destinations, 'named destination must exist'
            return dest(destinations[str(value)])
        if isinstance(value, pikepdf.Dictionary):
            return dest(value.D)
        assert isinstance(value, pikepdf.Array) and len(value) >= 2, 'destination array'
        assert value[0].objgen in pages, 'destination must target inserted surviving page'
    def target(obj):
        if '/Dest' in obj:
            dest(obj.Dest)
        action = obj.get('/A')
        if action is not None and action.get('/S') == pikepdf.Name.GoTo:
            dest(action.D)
    for page in pdf.pages:
        for annot in page.obj.get('/Annots', []):
            target(annot)
            if annot.get('/Subtype') == pikepdf.Name.Widget:
                assert annot.objgen not in widgets, 'widget cannot belong to two pages'
                assert annot.get('/P').objgen == page.obj.objgen, 'widget P must be actual owner'
                widgets[annot.objgen] = annot
    form = pdf.Root.get('/AcroForm')
    def appearance(value):
        if isinstance(value, pikepdf.Stream):
            assert len(value.read_bytes()) > 0, 'widget appearance must have real operators'
            appearances.append(value.objgen)
        else:
            for stream in value.values():
                appearance(stream)
    def field_walk(field, parent=None, inherited=None, defaults=None):
        assert field.objgen not in fields, 'field hierarchy cannot repeat'
        fields[field.objgen] = field
        if parent is not None:
            assert field.get('/Parent').objgen == parent.objgen, 'field Parent hierarchy'
        kind = field.get('/FT', inherited)
        da, dr = defaults or (form.get('/DA'), form.get('/DR'))
        da, dr = field.get('/DA', da), field.get('/DR', dr)
        if kind is not None:
            field_types.add(str(kind))
            if str(kind) in ('/Tx', '/Ch'):
                assert da is not None and dr is not None, 'effective field defaults must survive'
                fonts = re.findall(r'/([^\s]+)\s+[\d.]+\s+Tf', str(da))
                assert fonts and all('/'+font in dr.Font for font in fonts), 'DA font must resolve in DR'
        if field.get('/Subtype') == pikepdf.Name.Widget:
            assert field.objgen in widgets, 'field widget must occur in owning page Annots'
            assert '/AP' in field, 'widget appearance must survive'
            appearance(field.AP.N)
        for child in field.get('/Kids', []):
            field_walk(child, field, kind, (da, dr))
    if form is not None:
        for field in form.get('/Fields', []):
            field_walk(field)
        for field in form.get('/CO', []):
            assert field.objgen in fields, 'calculation order must target surviving fields'
        assert set(widgets) <= set(fields), 'every page widget must attach to field tree'
        if widgets:
            assert field_types == {'/Tx', '/Btn', '/Ch', '/Sig'}, 'all four field types survive'
            assert len(appearances) >= len(widgets), 'all widget appearance identities survive'
            assert '/DR' in form, 'form default resources survive'
    outlines = pdf.Root.get('/Outlines')
    visited = set()
    def outline_walk(node, parent):
        previous = None
        while node is not None:
            assert node.objgen not in visited, 'outline cannot repeat'
            visited.add(node.objgen)
            assert node.Parent.objgen == parent.objgen, 'outline Parent hierarchy'
            if previous is not None:
                assert node.Prev.objgen == previous.objgen, 'outline sibling linkage'
            target(node)
            if '/First' in node:
                outline_walk(node.First, node)
            previous = node
            node = node.get('/Next')
        if previous is not None:
            assert parent.Last.objgen == previous.objgen, 'outline Last linkage'
    if outlines is not None and '/First' in outlines:
        outline_walk(outlines.First, outlines)
    for value in destinations.values():
        dest(value)
    if '/OpenAction' in pdf.Root:
        value = pdf.Root.OpenAction
        dest(value.D if isinstance(value, pikepdf.Dictionary) else value)
