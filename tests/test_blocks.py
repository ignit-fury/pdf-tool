from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.blocks import build_document, HEADING_RATIO
from engine.index import RunIndex
from tools.build_export_fixtures import build_export_fixture


def texts(blocks: object) -> list[str]:
    return [''.join(span.text for span in block.spans) for block in blocks]  # type: ignore[attr-defined,union-attr]


def test_headings_styles_lists_and_columns(tmp_path: Path) -> None:
    path = tmp_path / 'layout.pdf'
    build_export_fixture(path)
    with RunIndex(path) as index:
        doc = build_document(index)
        page = doc.pages[0]
        assert texts(page.blocks) == ['Export heading', 'Left first\nLeft second', 'Right first\nRight second', 'Bold body', 'Italic body', '- First item']
        assert page.blocks[0].kind == 'heading' and page.blocks[0].heading_level == 1
        assert next(b for b in page.blocks if texts([b]) == ['Bold body']).kind == 'paragraph'
        assert any(s.bold is True for b in page.blocks for s in b.spans if 'Bold' in s.text)
        assert any(s.italic is True for b in page.blocks for s in b.spans if 'Italic' in s.text)
        assert page.blocks[-1].kind == 'list'
        assert doc.pages[1].blocks[0].kind == 'table'
        assert [[''.join(s.text for s in cell) for cell in row] for row in doc.pages[1].blocks[0].rows] == [['A1', 'B1'], ['A2', 'B2']]
        assert not doc.pages[2].blocks
        assert 'no-indexed-text' in doc.pages[2].warnings


def test_unruled_or_incomplete_grid_remains_text(tmp_path: Path) -> None:
    for ruled in (False, 'incomplete'):
        path = tmp_path / f'{ruled}.pdf'
        build_export_fixture(path, ruled=ruled)
        with RunIndex(path) as index:
            page = build_document(index).pages[1]
            assert all(b.kind != 'table' for b in page.blocks)
            assert all(text in '\n'.join(texts(page.blocks)) for text in ['A1', 'B1', 'A2', 'B2'])
            assert any('table' in warning or 'column' in warning for warning in page.warnings)


def test_heading_threshold_and_input_immutability(tmp_path: Path) -> None:
    path = tmp_path / 'layout.pdf'
    build_export_fixture(path)
    with RunIndex(path) as index:
        page = index.page(0)
        before = [(r.run_id, r.display_text, r.effective_em) for r, _ in page.runs]
        title = page.runs[0][0]
        title.effective_em = 12 * HEADING_RATIO - .1
        assert build_document(index).pages[0].blocks[0].kind == 'paragraph'
        title.effective_em = 12 * HEADING_RATIO + .1
        assert build_document(index).pages[0].blocks[0].kind == 'heading'
        title.effective_em = before[0][2]
        assert [(r.run_id, r.display_text, r.effective_em) for r, _ in page.runs] == before


def test_bounds_fail_with_content_free_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.blocks as blocks
    monkeypatch.setattr(blocks, 'MAX_BLOCK_PAGES', 1)
    with pytest.raises(ValueError, match='page-limit'):
        build_document(SimpleNamespace(page_count=2))


def test_fixture_contains_actual_sizes_fonts_and_closed_grid(tmp_path: Path) -> None:
    import pikepdf
    path = tmp_path / 'layout.pdf'
    build_export_fixture(path)
    with pikepdf.open(path) as pdf:
        assert len(pdf.pages) == 3
        raw = pdf.pages[0].Contents.read_bytes()
        assert b'/F2 24 Tf' in raw and b'/F1 12 Tf' in raw
        assert str(pdf.pages[0].Resources.Font.F3.BaseFont) == '/Helvetica-Oblique'
        grid = pdf.pages[1].Contents.read_bytes()
        assert b'240 100 re S' in grid and b'160 500 l S' in grid and b'280 450 l S' in grid
        assert pdf.pages[2].Resources.XObject.Im.Subtype == pikepdf.Name.Image


def test_run_limit_and_grid_work_limit_are_conservative(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.blocks as blocks
    path = tmp_path / 'layout.pdf'
    build_export_fixture(path)
    with RunIndex(path) as index:
        monkeypatch.setattr(blocks, 'MAX_GRID_COMPARISONS', 1)
        table = build_document(index).pages[1]
        assert 'table-work-limit' in table.warnings
        assert all(b.kind != 'table' for b in table.blocks)
        monkeypatch.setattr(blocks, 'MAX_BLOCK_RUNS', 1)
        with pytest.raises(ValueError, match='run-limit'):
            build_document(index)


def test_layout_measures_each_run_once_per_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.blocks as blocks
    path = tmp_path / 'layout.pdf'
    build_export_fixture(path)
    original = blocks._bounds
    measured: list[int] = []

    def measure(run):
        measured.append(id(run))
        return original(run)

    monkeypatch.setattr(blocks, '_bounds', measure)
    with RunIndex(path) as index:
        doc = build_document(index)
        assert texts(doc.pages[0].blocks)[0] == 'Export heading'
        assert [[''.join(s.text for s in cell) for cell in row] for row in doc.pages[1].blocks[0].rows] == [['A1', 'B1'], ['A2', 'B2']]
        assert len(measured) == len(set(measured)), 'layout rescanned glyph geometry'
        measured.clear()
        # A second export must measure again: source runs are mutable between edits.
        build_document(index)
        assert measured
