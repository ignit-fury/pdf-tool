"""Independent, bounded G5 fixtures and acceptance assertions (dev tooling only)."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pikepdf
from PIL import Image

from harness.masked_diff import masked_pixel_diff
from harness.render_diff import RENDER_DPI

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
    _graph(directory / 'graph-source.pdf')
    _graph(directory / 'unsafe-source.pdf', unsafe=True)
    # Fully flattened, oriented PNG. Browser native decode/compositing is a separate gate.
    image = Image.new('RGBA', (12, 8), (0, 0, 0, 0))
    for x in range(6):
        for y in range(8):
            image.putpixel((x, y), (240, 30, 10, 128))
    white = Image.new('RGBA', image.size, 'white')
    white.alpha_composite(image)
    white.convert('RGB').save(directory / 'white-flattened.png')
    manifest = {'sources': sources, 'fonts': fonts}
    target = directory / 'fixtures.json'
    target.write_text(json.dumps(manifest, indent=2))
    return target


def assert_pixels(before, after, rect=None, *, changed=False):
    # Deliberately incomplete RED assertion: corruption must make controls fail.
    return masked_pixel_diff(before, after)


def assert_graph(pdf):
    # Deliberately incomplete RED assertion; implemented after real corruption run.
    return None
