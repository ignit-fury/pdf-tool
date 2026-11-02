"""Fit must respect source TJ extent independently of following text placement."""
import math
from dataclasses import replace
from pathlib import Path

import pikepdf
import pytest

from engine.classify_run import classify_document
from engine.recipe import RecipeOp, apply_recipe
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
@pytest.mark.parametrize('multi_op', [False, True])
@pytest.mark.parametrize('replacement', ['a ordinary a ordinary text', 'the ordinary the ordinary textss'])
def test_tj_spacing_and_final_pen_are_separate(tmp_path, matrix, multi_op, replacement):
    source, output = tmp_path / 'source.pdf', tmp_path / 'edited.pdf'
    _build_apply_fixture(source)
    with pikepdf.open(source, allow_overwriting_input=True) as pdf:
        pdf.pages[0].Contents = pdf.make_stream(
            f'BT /F2 1 Tf 85 Tz 0.01 Tc 0.02 Tw {matrix} Tm '.encode()
            + (b'[20 (the ordinary ) 35] TJ [(the ordinary text) 100] TJ ' if multi_op
               else b'[20 (the ordinary ) 35 (the ordinary text) 100] TJ ')
            + b'0.4 g (FOLLOWER) Tj ET')
        pdf.save(source)
    before = [r for r, _ in classify_document(source).runs]
    original = next(r for r in before if 'ordinary' in r.display_text)
    follower = next(r for r in before if r.display_text == 'FOLLOWER')
    report = apply_recipe(source, (RecipeOp(original.run_id, replacement),), output)
    assert report.ok, report
    assert report.resolved[0].strategy == ('tz' if replacement.endswith('ss') else 'trailing_kern')
    after = [r for r, _ in classify_document(output).runs]
    current = next(r for r in after if 'ordinary' in r.display_text)
    following = next(r for r in after if r.display_text == 'FOLLOWER')
    assert _extent(current) <= _extent(original) + 0.001
    assert (current.glyphs[0].x, current.glyphs[0].y) == pytest.approx(
        (original.glyphs[0].x, original.glyphs[0].y), abs=1e-6)
    for a, b in zip(follower.glyphs, following.glyphs, strict=True):
        assert (a.x, a.y, *a.advance) == pytest.approx((b.x, b.y, *b.advance), abs=1e-6)


@pytest.mark.parametrize('fallback', [False, True])
def test_visible_guard_refuses_corrupted_emission_with_absolute_follower(tmp_path, monkeypatch, fallback):
    import engine.rewrite as rewrite
    from engine.part_snapshot import PartSnapshot
    source, output = tmp_path / 'source.pdf', tmp_path / 'edited.pdf'
    _build_apply_fixture(source)
    with pikepdf.open(source, allow_overwriting_input=True) as pdf:
        pdf.pages[0].Contents = pdf.make_stream(
            b'BT /F2 12 Tf 72 700 Td (Original content) Tj '
            b'1 0 0 1 72 650 Tm (FOLLOWER) Tj ET')
        pdf.save(source)
    original = next(r for r, _ in classify_document(source).runs if r.display_text == 'Original content')
    real = rewrite._show_instruction
    def corrupted(units, fit):
        return real(units * 20, replace(fit, kerns=[]))
    monkeypatch.setattr(rewrite, '_show_instruction', corrupted)
    if fallback:
        monkeypatch.setattr(PartSnapshot, 'create', classmethod(lambda cls, *args: None))
    report = apply_recipe(source, (RecipeOp(original.run_id, 'Tiny'),), output)
    assert not report.ok
    assert report.resolved[0].reason == 'replacement_exceeds_visible_extent'
    assert not output.exists()


def test_original_pdf_space_width_bounds_positive_tightening(tmp_path):
    source, output = tmp_path / 'source.pdf', tmp_path / 'edited.pdf'
    _build_apply_fixture(source)
    with pikepdf.open(source, allow_overwriting_input=True) as pdf:
        font = pdf.pages[0].Resources.Font['/F1']
        font.Widths[97 - int(font.FirstChar)] = 333.333333
        font.Widths[32 - int(font.FirstChar)] = 8.333333
        pdf.pages[0].Contents = pdf.make_stream(
            b'BT /F1 12 Tf 72 700 Td (a a a a a a a a a ) Tj '
            b'1 0 0 1 72 650 Tm (FOLLOWER) Tj ET')
        pdf.save(source)
    original, verdict = next((r, v) for r, v in classify_document(source).runs
                             if r.display_text.startswith('a '))
    assert verdict.state == 'editable_original'
    replacement = 'a a a a a a a a a a'
    report = apply_recipe(source, (RecipeOp(original.run_id, replacement),), output)
    assert report.ok, report
    assert report.resolved[0].strategy == 'tz'
    assert report.resolved[0].fit_result.condensed_scale >= 90
    current = next(r for r, _ in classify_document(output).runs if r.display_text == replacement)
    assert _extent(current) <= _extent(original) + 1e-6
    for previous, following in zip(current.glyphs, current.glyphs[1:]):
        if previous.unicode == ' ':
            assert following.x > previous.x
