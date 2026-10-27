from html.parser import HTMLParser
from pathlib import Path

import pytest

from engine.blocks import Block, DocumentBlocks, PageBlocks, Span
from engine.export.text import export_document, serialize_text, serialize_markdown, serialize_html
from engine.index import RunIndex
from tools.build_export_fixtures import build_export_fixture


def test_formats_share_blocks_and_preserve_structure(tmp_path: Path) -> None:
    path = tmp_path / 'in.pdf'
    build_export_fixture(path)
    with RunIndex(path) as index:
        plain = export_document(index, 'text')
        md = export_document(index, 'markdown')
        html = export_document(index, 'html')
    assert 'Left first\nLeft second' in plain and plain.count('\f') == 2
    assert 'A1\tB1\nA2\tB2' in plain
    assert '# **Export heading**' in md
    assert '**Bold body**' in md and '*Italic body*' in md
    assert '- First item' in md and '| A1 | B1 |' in md
    assert '<h1><strong>Export heading</strong></h1>' in html
    assert '<table>' in html and '<td>B2</td>' in html and '<li>First item</li>' in html
    assert '<meta charset="utf-8">' in html


def test_hostile_pdf_strings_stay_inert_in_same_model() -> None:
    text = '<script>alert("x")</script> <img src="https://bad/" onerror="x"> & [link](javascript:x) | *em* `code`'
    document = DocumentBlocks((PageBlocks(0, (Block('paragraph', (), (Span(text),)),)),))
    assert serialize_text(document) == text + '\n'
    md = serialize_markdown(document)
    assert '<script>' not in md and '\\[link\\]' in md and '\\*em\\*' in md and '\\|' in md
    html = serialize_html(document)
    class Tags(HTMLParser):
        tags: list[str] = []
        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            self.tags.append(tag)
            assert not any(key.startswith('on') or key in {'src','href'} for key,_ in attrs)
    parsed = Tags()
    parsed.feed(html)
    assert not {'script', 'img', 'a'} & set(parsed.tags)
    assert '&lt;script&gt;' in html and '&amp;' in html


def test_invalid_format_does_not_touch_index() -> None:
    with pytest.raises(ValueError, match='unsupported-export-format'):
        export_document(object(), 'pdf')


@pytest.mark.parametrize('serializer', [serialize_text, serialize_markdown, serialize_html])
def test_output_limit_is_fail_closed(monkeypatch: pytest.MonkeyPatch, serializer: object) -> None:
    import engine.export.text as text
    monkeypatch.setattr(text, 'MAX_OUTPUT_CHARS', 100)
    doc = DocumentBlocks((PageBlocks(0,(Block('paragraph',(),(Span('x'*101),)),)),))
    with pytest.raises(ValueError, match='output-limit'):
        serializer(doc)  # type: ignore[operator]


def test_markdown_escapes_markers_and_table_breaks() -> None:
    doc = DocumentBlocks((PageBlocks(0,(
        Block('paragraph',(),(Span('# title\n1. item'),)),
        Block('table',(),(),rows=(((Span('A|B\nC'),),(Span('[x](url)'),)),)),
    )),))
    value = serialize_markdown(doc)
    assert '\\# title' in value and '1\\. item' in value
    assert 'A\\|B<br>C' in value and '\\[x\\]\\(url\\)' in value


@pytest.mark.parametrize('format', ['html', 'markdown'])
def test_empty_scanned_exports_report_no_actual_text(tmp_path: Path, format: str) -> None:
    import pikepdf
    import engine.export.text as module
    path = tmp_path / 'scanned.pdf'
    build_export_fixture(path)
    with pikepdf.open(path,allow_overwriting_input=True) as pdf:
        del pdf.pages[0]
        del pdf.pages[0]
        pdf.pages.append(pdf.pages[0])
        pdf.save(path)
    with RunIndex(path) as index:
        result = module.export_document_result(index,format)
    assert result.text.strip()  # Complete HTML/page separators are not source text.
    assert result.has_text is False


@pytest.mark.parametrize('spans, rows, expected', [
    ((Span('  \n\t'),), (), False),
    ((Span('Actual text'),), (), True),
    ((), (((Span('Cell text'),),),), True),
    ((), (((Span(' \n'),),),), False),
])
def test_result_uses_same_model_and_actual_spans(monkeypatch: pytest.MonkeyPatch, spans: tuple, rows: tuple, expected: bool) -> None:
    import engine.export.text as module
    document = DocumentBlocks((PageBlocks(0,(Block('table' if rows else 'paragraph',(),spans,rows=rows),)),))
    builds: list[object] = []
    serialized: list[DocumentBlocks] = []
    def building(index: object) -> DocumentBlocks:
        builds.append(index)
        return document
    def serializing(model: DocumentBlocks) -> str:
        serialized.append(model)
        return 'serialized'
    monkeypatch.setattr(module,'build_document',building)
    monkeypatch.setattr(module,'serialize_html',serializing)
    index = object()
    result = module.export_document_result(index,'html')
    assert result.text == 'serialized' and result.has_text is expected
    assert builds == [index] and serialized == [document]


def test_font_split_list_marker_preserves_body_style_and_provenance(tmp_path: Path) -> None:
    import pikepdf
    from engine.blocks import build_document
    from engine.export.text import _list_body
    path = tmp_path / 'split-marker.pdf'
    with pikepdf.Pdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(300,200))
        fonts = pikepdf.Dictionary()
        for key,name in [('F1','Helvetica'),('F2','Helvetica-Bold'),('F3','Helvetica-Oblique')]:
            fonts['/'+key] = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font,Subtype=pikepdf.Name.Type1,BaseFont=pikepdf.Name('/'+name)))
        page.Resources = pikepdf.Dictionary(Font=fonts)
        page.Contents = pdf.make_stream(b'BT /F1 12 Tf 40 100 Td (-) Tj /F2 12 Tf ( ) Tj /F3 12 Tf (First item) Tj ET')
        pdf.save(path)
    with RunIndex(path) as index:
        document = build_document(index)
    block = document.pages[0].blocks[0]
    assert block.kind == 'list'
    assert len(block.spans) >= 2 and ''.join(s.text for s in block.spans) == '- First item'
    original = next(s for s in block.spans if 'First item' in s.text)
    body = _list_body(block)
    assert ''.join(s.text for s in body) == 'First item'
    assert body[-1].source_runs == original.source_runs and body[-1].italic is True
    assert serialize_markdown(document) == '- *First item*\n\n'
    assert '<li><em>First item</em></li>' in serialize_html(document)
    assert serialize_text(document) == '- First item\n'


def test_named_limit_errors_cover_output_and_block_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace
    import engine.blocks as blocks
    import engine.export.text as text
    monkeypatch.setattr(text,'MAX_OUTPUT_CHARS',10)
    doc = DocumentBlocks((PageBlocks(0,(Block('paragraph',(),(Span('x'*11),)),)),))
    with pytest.raises(text.ExportLimitError,match='export-output-limit'):
        serialize_text(doc)
    monkeypatch.setattr(blocks,'MAX_BLOCK_PAGES',1)
    with pytest.raises(text.ExportLimitError,match='export-page-limit'):
        blocks.build_document(SimpleNamespace(page_count=2))
    monkeypatch.setattr(blocks,'MAX_BLOCK_RUNS',0)
    with pytest.raises(text.ExportLimitError,match='export-run-limit'):
        blocks.build_document(SimpleNamespace(page_count=1,page=lambda _:SimpleNamespace(runs=[object()])))
