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
