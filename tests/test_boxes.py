"""Server selection boxes are in unrotated, bottom-left PDF user space."""
from pathlib import Path

import pikepdf
import pytest

from engine.classify_run import stream_bytes_and_resources
from engine.index import RunIndex
from engine.run_id import decode_run_id
from test_recipe import _build_apply_fixture


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_boxes_cover_original_pdf_baseline(tmp_path: Path, rotation: int) -> None:
    from engine.boxes import run_box
    path = tmp_path / "in.pdf"
    _build_apply_fixture(path)
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        pdf.pages[0].Rotate = rotation
        pdf.pages[0].MediaBox = pikepdf.Array([50, 100, 662, 892])
        pdf.save(path)
    with RunIndex(path) as index, pikepdf.open(path) as pdf:
        for run, _ in index.page(0).runs:
            parts = decode_run_id(run.run_id)
            raw, resources = stream_bytes_and_resources(pdf, run.page, parts["part"], parts["xobj_path"])
            x0, y0, x1, y1 = run_box(run, raw, resources)
            assert x1 > x0
            assert y1 > y0
            assert x0 <= 72 <= x1
            baseline = {"Hello world": 700, "Second line": 660, "Third line": 620}[run.display_text]
            assert y0 < baseline < y1
            assert y1 - y0 == pytest.approx(12)
            assert 0 < y0 < 792
            assert y1 < 792


def test_box_height_includes_text_matrix_scale(tmp_path: Path) -> None:
    from engine.boxes import run_box
    path = tmp_path / "scaled.pdf"
    _build_apply_fixture(path)
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        raw = pdf.pages[0].Contents.read_bytes().replace(b"72 700 Td", b"2 0 0 2 72 700 Tm")
        pdf.pages[0].Contents = pdf.make_stream(raw)
        pdf.save(path)
    with RunIndex(path) as index, pikepdf.open(path) as pdf:
        run = next(r for r, _ in index.page(0).runs if r.display_text == "Hello world")
        box = run_box(run, raw, pdf.pages[0].Resources)
        assert box[3] - box[1] == pytest.approx(24)
        assert box[1] < 700 < box[3]
