"""Fit must respect source TJ extent independently of following text placement."""
import json
import math
from pathlib import Path

import pikepdf
import pytest

from engine.classify_run import classify_document
from engine.recipe import RecipeOp, apply_recipe, parse_recipe
from test_recipe import _build_apply_fixture


def _extent(run):
    dx, dy = run.direction
    scale = math.hypot(dx, dy)
    x, y = run.glyphs[0].x, run.glyphs[0].y
    return max(((g.x + g.advance[0] - x) * dx + (g.y + g.advance[1] - y) * dy) / scale
               for g in run.glyphs)


@pytest.mark.corpus
def test_real_tj_compressed_lines_do_not_expand(tmp_path):
    source = Path(__file__).resolve().parents[1] / 'corpus/public/govdocs1_013_013050.pdf'
    if not source.exists():
        pytest.skip('public proxy absent')
    # Include a line whose replacement is naturally wider than its compressed source.
    offsets = (3749, 5086, 10861)
    before = [r for r, _ in classify_document(source).runs
              if (r.page == 5 and any(r.run_id.endswith(f':o{o}') for o in offsets[:2]))
              or (r.page == 8 and r.run_id.endswith(':o10861'))]
    import re
    ops = tuple(RecipeOp(r.run_id, re.sub('the', 'a', r.display_text, flags=re.I)) for r in before)
    assert len(ops) == 3
    output = tmp_path / 'edited.pdf'
    report = apply_recipe(source, ops, output)
    assert report.ok, report
    after = [r for r, _ in classify_document(output).runs]
    for original, op in zip(before, ops, strict=True):
        current = next(r for r in after if r.page == original.page and r.display_text == op.new_text)
        assert _extent(current) <= _extent(original) + 0.001


@pytest.mark.parametrize('matrix', ['12 0 0 12 72 700', '0 12 -18 0 300 200'])
def test_tj_spacing_and_final_pen_are_separate(tmp_path, matrix):
    source, output = tmp_path / 'source.pdf', tmp_path / 'edited.pdf'
    _build_apply_fixture(source)
    with pikepdf.open(source, allow_overwriting_input=True) as pdf:
        pdf.pages[0].Contents = pdf.make_stream(
            f'BT /F2 1 Tf 85 Tz 0.01 Tc 0.02 Tw {matrix} Tm '.encode()
            + b'[20 (the ordinary ) 35 (the ordinary text) 100] TJ '
            + b'0.4 g (FOLLOWER) Tj ET')
        pdf.save(source)
    before = [r for r, _ in classify_document(source).runs]
    original = next(r for r in before if 'ordinary' in r.display_text)
    follower = next(r for r in before if r.display_text == 'FOLLOWER')
    report = apply_recipe(source, (RecipeOp(original.run_id, 'a ordinary a ordinary text'),), output)
    assert report.ok, report
    after = [r for r, _ in classify_document(output).runs]
    current = next(r for r in after if 'ordinary' in r.display_text)
    following = next(r for r in after if r.display_text == 'FOLLOWER')
    assert _extent(current) <= _extent(original) + 0.001
    assert (current.glyphs[0].x, current.glyphs[0].y) == pytest.approx(
        (original.glyphs[0].x, original.glyphs[0].y), abs=1e-6)
    for a, b in zip(follower.glyphs, following.glyphs, strict=True):
        assert (a.x, a.y, *a.advance) == pytest.approx((b.x, b.y, *b.advance), abs=1e-6)
