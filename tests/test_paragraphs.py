# tests/test_paragraphs.py
from pathlib import Path

from engine.index import RunIndex
from engine.paragraphs import page_paragraphs, paragraph_id
from tools.build_export_fixtures import build_export_fixture


def line_texts(paragraph):
    return [''.join(r.display_text for r in line) for line in paragraph.lines]


def test_multiline_paragraph_keeps_lines_and_stable_id(tmp_path: Path) -> None:
    path = tmp_path / 'layout.pdf'
    build_export_fixture(path)
    with RunIndex(path) as index:
        paragraphs = page_paragraphs(0, index.page(0))
    left = next(p for p in paragraphs if line_texts(p) == ['Left first', 'Left second'])
    assert left.kind == 'paragraph'
    assert left.paragraph_id == paragraph_id(left.run_ids)
    assert left.paragraph_id.startswith('p_') and len(left.paragraph_id) == 18
    assert [line_texts(p) for p in paragraphs if p.kind == 'heading'] == [['Export heading']]


def test_tables_are_not_paragraphs(tmp_path: Path) -> None:
    path = tmp_path / 'layout.pdf'
    build_export_fixture(path)
    with RunIndex(path) as index:
        assert page_paragraphs(1, index.page(1)) == ()


def test_paragraph_id_depends_on_order() -> None:
    assert paragraph_id(['a', 'b']) != paragraph_id(['b', 'a'])
