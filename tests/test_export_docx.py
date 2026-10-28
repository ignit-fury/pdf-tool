"""Direct OOXML and this-document warnings from one shared layout snapshot."""
import io
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

import pytest

from engine.blocks import Block, DocumentBlocks, PageBlocks, Span, build_document
from engine.index import RunIndex
from tools.build_export_fixtures import build_export_fixture

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def document(text='A & <B>', *, bold=True):
    return DocumentBlocks((PageBlocks(0, (
        Block('heading', (), (Span('Title'),), 1),
        Block('paragraph', (), (Span(text, bold, True),))), image_analysis_complete=True),))


def package(snapshot):
    from engine.export.docx import serialize_docx
    archive = zipfile.ZipFile(io.BytesIO(serialize_docx(snapshot)))
    assert archive.testzip() is None
    assert {'[Content_Types].xml', '_rels/.rels', 'word/document.xml',
            'word/styles.xml', 'word/_rels/document.xml.rels'} <= set(archive.namelist())
    assert all(not name.startswith('/') and '..' not in name for name in archive.namelist())
    for name in archive.namelist():
        if name.endswith(('.xml', '.rels')):
            ET.fromstring(archive.read(name))
    return archive, ET.fromstring(archive.read('word/document.xml'))


def test_text_headings_styles_and_whitespace_form_a_valid_package():
    from engine.export.docx import prepare_docx
    snapshot = prepare_docx(document(' A & <B>\tline\nnext '))
    archive, root = package(snapshot)
    assert root.find('.//' + W + 'pStyle').attrib[W + 'val'] == 'Heading1'
    assert root.findall('.//' + W + 'b') and root.findall('.//' + W + 'i')
    assert root.findall('.//' + W + 'tab') and root.findall('.//' + W + 'br')
    assert ' A & <B>' in ''.join(root.itertext())
    assert snapshot.review['facts'] == [] and snapshot.review['has_text'] is True
    assert b'TargetMode="External"' not in archive.read('word/_rels/document.xml.rels')


def test_digest_covers_content_and_style_even_when_warnings_are_equal():
    from engine.export.docx import prepare_docx, snapshot_digest
    a, b, c = [prepare_docx(d) for d in [document(), document('changed'), document(bold=False)]]
    assert a.review == b.review == c.review
    assert len({snapshot_digest(s) for s in (a, b, c)}) == 3


def test_actual_columns_flatten_and_ruled_table_survives_without_second_parse(tmp_path, monkeypatch):
    from engine.export.docx import prepare_docx
    path = tmp_path / 'layout.pdf'
    build_export_fixture(path)
    original, calls = RunIndex._parse_page, []
    def counted(self, page):
        calls.append(page)
        return original(self, page)
    monkeypatch.setattr(RunIndex, '_parse_page', counted)
    with RunIndex(path, include_images=True) as index:
        shared = build_document(index)
        snapshot = prepare_docx(shared)
        archive, root = package(snapshot)
        assert calls == [0, 1, 2]
    assert len(root.findall('.//' + W + 'tbl')) == 1
    assert snapshot.review['supported_ruled_tables'] == 1
    facts = {f['code']: f for f in snapshot.review['facts']}
    assert facts['COLUMN_LAYOUT']['pages'] == [0]
    assert facts['COLUMN_LAYOUT']['count'] is None
    text = ''.join(root.itertext())
    assert text.index('Left first') < text.index('Right first') < text.index('Left second')
    assert facts['NO_EXTRACTABLE_TEXT']['pages'] == [2]


def test_supported_images_survive_image_only_pages(tmp_path):
    from engine.export.docx import prepare_docx
    from harness.pdfa_fixture import build_fixtures
    from PIL import Image
    path = build_fixtures(tmp_path)['image-only']
    with RunIndex(path, include_images=True) as index:
        page = index.page(0)
        assert len(page.images) == 1 and page.image_analysis_complete
        assert index.page(0) is page
        snapshot = prepare_docx(build_document(index))
        archive, root = package(snapshot)
    media = [p for p in archive.namelist() if p.startswith('word/media/')]
    assert len(media) == 1 and len(root.findall('.//' + W + 'drawing')) == 1
    with Image.open(io.BytesIO(archive.read(media[0]))) as image:
        assert image.size == (16, 12)
    assert snapshot.review['images_complete'] is True
    assert snapshot.review['has_text'] is False


def test_missing_image_analysis_is_unknown_and_never_reported_as_complete():
    from engine.export.docx import prepare_docx
    snapshot = prepare_docx(DocumentBlocks((PageBlocks(0, ()),)))
    assert snapshot.review['images_complete'] is False
    assert any(f['code'] == 'IMAGE_UNSUPPORTED' for f in snapshot.review['facts'])


def test_invalid_xml_text_refuses_with_a_fixed_code():
    from engine.export.docx import DocxRefusal, prepare_docx
    with pytest.raises(DocxRefusal, match='DOCX_UNSUPPORTED'):
        prepare_docx(document('bad\x00text'))


def test_ordinary_text_index_does_not_start_image_analysis(tmp_path, monkeypatch):
    import engine.index as module
    path = tmp_path / 'text.pdf'
    build_export_fixture(path)
    def unexpected(*args, **kwargs):
        raise AssertionError('ordinary editing/extraction decoded images')
    monkeypatch.setattr(module, 'page_images', unexpected)
    with RunIndex(path) as index:
        assert build_document(index).pages[0].blocks


@pytest.mark.parametrize('kind,count', [('mask', 1), ('form', None)])
def test_unsupported_images_are_disclosed_without_inventing_counts(tmp_path, kind, count):
    import pikepdf
    from engine.export.docx import prepare_docx
    from harness.pdfa_fixture import build_fixtures
    path = build_fixtures(tmp_path)['image-rgb']
    output = tmp_path / 'unsupported.pdf'
    with pikepdf.open(path) as pdf:
        if kind == 'mask':
            pdf.pages[0].Resources.XObject.Im1.Mask = [0, 0, 0, 0, 0, 0]
        else:
            form = pdf.make_stream(b'')
            form.Type, form.Subtype = pikepdf.Name.XObject, pikepdf.Name.Form
            form.BBox = [0, 0, 1, 1]
            form.Resources = pikepdf.Dictionary()
            pdf.pages[0].Resources.XObject.Im1 = form
        pdf.save(output)
    with RunIndex(output, include_images=True) as index:
        snapshot = prepare_docx(build_document(index))
    assert not snapshot.review['images_complete']
    fact = next(f for f in snapshot.review['facts'] if f['code'] == 'IMAGE_UNSUPPORTED')
    assert fact['pages'] == [0] and fact['count'] == count
    archive, _ = package(snapshot)
    assert not any(name.startswith('word/media/') for name in archive.namelist())


def test_image_placement_count_is_bounded_before_conversion(tmp_path):
    import pikepdf
    from engine.index import DocumentTooLargeError
    from harness.pdfa_fixture import build_fixtures
    path = build_fixtures(tmp_path)['image-only']
    output = tmp_path / 'too-many.pdf'
    with pikepdf.open(path) as pdf:
        pdf.pages[0].Contents.write(b'q 64 0 0 48 140 40 cm /Im1 Do Q\n' * 201)
        pdf.save(output)
    with RunIndex(output, include_images=True) as index:
        with pytest.raises(DocumentTooLargeError, match='export-image-limit'):
            build_document(index)


def test_text_projection_is_bounded(monkeypatch):
    import engine.export.docx as module
    from engine.blocks import ExportLimitError
    monkeypatch.setattr(module, 'MAX_TEXT', 2)
    with pytest.raises(ExportLimitError, match='docx-text-limit'):
        module.prepare_docx(document())


def test_annotation_omission_is_reported_for_this_page(tmp_path):
    import pikepdf
    from engine.export.docx import prepare_docx
    from harness.pdfa_fixture import build_fixtures
    path = build_fixtures(tmp_path)['text-sans']
    output = tmp_path / 'note.pdf'
    with pikepdf.open(path) as pdf:
        pdf.pages[0].Annots = [pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Text,
            Rect=[20,20,40,40], Contents=pikepdf.String('private annotation text')))]
        pdf.save(output)
    with RunIndex(output, include_images=True) as index:
        snapshot = prepare_docx(build_document(index))
    fact = next(f for f in snapshot.review['facts'] if f['code'] == 'ANNOTATIONS_OMITTED')
    assert fact == {'code':'ANNOTATIONS_OMITTED','pages':[0],'count':1}
    _, root = package(snapshot)
    assert 'private annotation text' not in ''.join(root.itertext())
