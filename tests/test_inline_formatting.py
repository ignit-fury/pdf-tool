"""Native inline styles retain source positions and refuse layout reconstruction."""
import hashlib
import io
import json
from pathlib import Path

import pikepdf
import pytest

from engine.classify_run import classify_document
from engine.playa_boundary import open_document, walk_page
from engine.recipe import RecipeOp, apply_recipe, parse_recipe, plan_recipe
from server.isolation import run_worker
from test_recipe import _build_apply_fixture
from tools.build_security_fixtures import text_pdf


def fixture(path: Path, content: bytes) -> None:
    _build_apply_fixture(path)
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        pdf.pages[0].Contents = pdf.make_stream(content)
        pdf.save(path)


@pytest.mark.parametrize('style', [
    {'font_size': 9}, {'font_size': 9, 'bold': True},
    {'font_size': 9, 'character_spacing': 0.4},
    {'character_spacing': 0.2},
])
def test_size_and_spacing_change_native_state_restore_following_text(tmp_path: Path, style: dict) -> None:
    source, output = tmp_path / 'in.pdf', tmp_path / 'out.pdf'
    fixture(source, b'BT /F1 12 Tf 0.5 Tc 1 Tw 72 700 Td (Hello world) Tj 0.3 g (NEXT) Tj ET')
    before_bytes = source.read_bytes()
    target = next(r for r, _ in classify_document(source).runs if r.display_text.startswith('Hello'))
    with open_document(source) as doc:
        before = list(walk_page(doc.pages[0], doc))[-1][3]
        following_position, following_size = before.matrix, before.gstate.fontsize
    recipe = (RecipeOp(target.run_id, 'Hello', style=style),)
    assert plan_recipe(source, recipe).ok
    report = apply_recipe(source, recipe, output)
    assert report.ok, report
    assert source.read_bytes() == before_bytes
    with open_document(output) as doc:
        objects = [(o.matrix, o.gstate.fontsize, o.gstate.charspace, o.gstate.wordspace)
                   for _, _, _, o in walk_page(doc.pages[0], doc)]
        assert objects[0][1] == style.get('font_size', 12)
        assert objects[0][2] == style.get('character_spacing', 0)
        assert objects[-1][0] == pytest.approx(following_position, abs=1e-6)
        assert objects[-1][1] == following_size
        assert objects[-1][2] == 0.5
        assert objects[-1][3] == 1
    assert ''.join(g.unicode or '' for r, _ in classify_document(output).runs for g in r.glyphs).startswith('HelloNEXT')


@pytest.mark.parametrize('style', [{'font_size': 0.9}, {'font_size': 513}, {'font_size': True},
                                   {'character_spacing': -0.01}, {'character_spacing': 10.1},
                                   {'character_spacing': float('inf')}, {'character_spacing': True}])
def test_format_bounds_reject_untrusted_recipe(style: dict) -> None:
    with pytest.raises(ValueError):
        parse_recipe(json.dumps([{'run_id': 'x', 'new_text': 'Hello', 'style': style}]).encode())


@pytest.mark.parametrize('text', ['Hello\nworld', 'Hello\rworld', 'Hello\u2028world', 'Hello\u2029world'])
def test_multiline_has_named_refusal_and_preserves_source(tmp_path: Path, text: str) -> None:
    source, output = tmp_path / 'in.pdf', tmp_path / 'out.pdf'
    _build_apply_fixture(source)
    before = hashlib.sha256(source.read_bytes()).digest()
    run, _ = classify_document(source).runs[0]
    recipe = (RecipeOp(run.run_id, text),)
    assert plan_recipe(source, recipe).resolved[0].reason == 'multiline_text_unsupported'
    assert apply_recipe(source, recipe, output).resolved[0].reason == 'multiline_text_unsupported'
    assert not output.exists()
    assert hashlib.sha256(source.read_bytes()).digest() == before


def test_spacing_overflow_refuses_without_output(tmp_path: Path) -> None:
    source, output = tmp_path / 'in.pdf', tmp_path / 'out.pdf'
    _build_apply_fixture(source)
    run, _ = classify_document(source).runs[0]
    recipe = (RecipeOp(run.run_id, run.display_text, style={'character_spacing': 10}),)
    report = apply_recipe(source, recipe, output)
    assert not report.ok
    assert not output.exists()


def test_source_metadata_is_parsed_state_and_not_pdf_literal_syntax() -> None:
    with pikepdf.open(io.BytesIO(text_pdf())) as pdf:
        pdf.pages[0].Contents = pdf.make_stream(
            b'0.2 0.3 0.4 rg BT /F1 12 Tf 0.25 Tc 20 150 Td '
            b'(literal /F1 77 Tf 1 0 0 rg) Tj '
            b'q /F1 9 Tf 0.5 Tc 0.6 g 0 -30 Td (Small) Tj Q '
            b'1 0 0 1 20 80 Tm (Restored) Tj ET')
        data = io.BytesIO()
        pdf.save(data)
    result = run_worker('page', data.getvalue(), page=0)
    assert result.get('error') is None, result
    runs = result['runs']
    literal = next(r for r in runs if r['text'].startswith('literal'))
    small = next(r for r in runs if r['text'] == 'Small')
    restored = next(r for r in runs if r['text'] == 'Restored')
    assert literal['font_size'] == 12
    assert literal['character_spacing'] == 0.25
    assert literal['color'] == [0.2, 0.3, 0.4]
    assert literal['bold'] is False and literal['italic'] is False
    assert small['font_size'] == 9 and small['character_spacing'] == 0.5
    assert small['color'] == [0.6, 0.6, 0.6]
    assert restored['font_size'] == 12 and restored['character_spacing'] == 0.25
    assert restored['color'] == [0.2, 0.3, 0.4]


@pytest.mark.parametrize('substitute', [False, True])
def test_size_spacing_with_leading_terminal_tj_and_horizontal_scale(tmp_path: Path, substitute: bool) -> None:
    source, output = tmp_path / 'in.pdf', tmp_path / 'out.pdf'
    fixture(source, b'BT /F1 12 Tf 80 Tz 72 700 Td [80 (Hello world) -60] TJ 0.3 g (NEXT) Tj ET')
    run = next(r for r, _ in classify_document(source).runs if r.display_text.startswith('Hello'))
    before_first = run.glyphs[0]
    with open_document(source) as doc:
        before = [tuple(o.matrix) for _, _, _, o in walk_page(doc.pages[0], doc)][-1]
    style = {'font_size': 9, 'character_spacing': 0.3}
    if substitute:
        style['bold'] = True
    report = apply_recipe(source, (RecipeOp(run.run_id, 'Hello', style=style),), output)
    assert report.ok, report
    with open_document(output) as doc:
        objects = [(tuple(o.matrix), o.gstate.fontsize, o.gstate.scaling)
                   for _, _, _, o in walk_page(doc.pages[0], doc)]
    assert objects[-1][0] == pytest.approx(before, abs=1e-6)
    assert objects[-1][1:] == (12, 80)
    after_first = classify_document(output).runs[0][0].glyphs[0]
    assert (after_first.x, after_first.y) == pytest.approx((before_first.x, before_first.y), abs=1e-6)


def test_metadata_omits_unknown_inherited_state_and_cmyk_color(tmp_path: Path) -> None:
    source = tmp_path / 'in.pdf'
    fixture(source, b'BT /F1 12 Tf 72 700 Td (Hello) Tj ET')
    with pikepdf.open(source, allow_overwriting_input=True) as pdf:
        pdf.pages[0].Contents = pikepdf.Array([
            pdf.make_stream(b'BT /F1 12 Tf 0.4 Tc 0 1 0 rg 72 700 Td (First) Tj ET'),
            pdf.make_stream(b'BT 0 -30 Td (Inherited) Tj ET 0 1 0 0 k BT /F1 9 Tf 72 600 Td (CMYK) Tj ET'),
        ])
        pdf.save(source)
    result = run_worker('page', source.read_bytes(), page=0)
    assert result.get('error') is None, result
    inherited = [r for r in result['runs'] if r['reason'] == 'no /Tf operator precedes this glyph']
    assert inherited
    assert all(k not in r for r in inherited for k in ('font_size', 'character_spacing', 'color'))
    cmyk = next(r for r in result['runs'] if r['text'] == 'CMYK')
    assert cmyk['font_size'] == 9
    assert 'color' not in cmyk


def test_source_hash_still_precedes_inline_style_resolution(tmp_path: Path) -> None:
    source, other = tmp_path / 'in.pdf', tmp_path / 'other.pdf'
    _build_apply_fixture(source)
    run, _ = classify_document(source).runs[0]
    other.write_bytes(text_pdf())
    report = apply_recipe(other, (RecipeOp(run.run_id, 'Hello', style={'font_size': 9}),), tmp_path / 'out.pdf')
    assert report.resolved[0].reason == 'source_hash_mismatch'
    assert not (tmp_path / 'out.pdf').exists()


@pytest.mark.parametrize('prefix', [
    b'BT /F1 12 Tf 72 700 Td (literal /F1 77 Tf) Tj 0 -30 Td ',
    b'BT /F1 12 Tf q /F1 11 Tf Q 72 700 Td ',
])
def test_unproven_source_font_state_refuses_style_without_output(tmp_path: Path, prefix: bytes) -> None:
    source, output = tmp_path / 'in.pdf', tmp_path / 'out.pdf'
    fixture(source, prefix + b'(Hello world) Tj ET')
    run = next(r for r, _ in classify_document(source).runs if r.display_text == 'Hello world')
    report = apply_recipe(source, (RecipeOp(run.run_id, 'Hello', style={'font_size': 9}),), output)
    assert not report.ok
    assert report.resolved[0].reason == 'source_font_state_unsupported'
    assert not output.exists()


def test_shrinking_allows_longer_searchable_text_with_bounded_tz(tmp_path: Path) -> None:
    source, output = tmp_path / 'in.pdf', tmp_path / 'out.pdf'
    with pikepdf.open(io.BytesIO(text_pdf(b'Hello world'))) as pdf:
        pdf.pages[0].Contents = pdf.make_stream(
            b'BT /F1 12 Tf 20 150 Td (Hello world) Tj 0.3 g (NEXT) Tj ET')
        pdf.save(source)
    run = next(r for r, _ in classify_document(source).runs if r.display_text == 'Hello world')
    recipe = (RecipeOp(run.run_id, 'Hello new world', style={'font_size': 9, 'character_spacing': 0.1}),)
    planned = plan_recipe(source, recipe)
    assert planned.ok and planned.resolved[0].strategy == 'tz'
    assert apply_recipe(source, recipe, output).ok
    after = classify_document(output).runs
    assert ''.join(g.unicode or '' for r, _ in after for g in r.glyphs) == 'Hello new worldNEXT'
    with open_document(output) as doc:
        states = [(o.gstate.fontsize, o.gstate.scaling, o.gstate.charspace)
                  for _, _, _, o in walk_page(doc.pages[0], doc)]
    assert states[0][0] == 9 and states[0][2] == 0.1
    assert 90 <= states[0][1] < 100
    assert states[-1] == (12, 100, 0)


@pytest.mark.parametrize('rotation', [0, 90])
def test_metadata_display_em_includes_tm_scale_without_squaring_tf(rotation: int) -> None:
    with pikepdf.open(io.BytesIO(text_pdf())) as pdf:
        pdf.pages[0].Rotate = rotation
        pdf.pages[0].Contents = pdf.make_stream(
            b'BT /F1 12 Tf 2 0 0 2 20 80 Tm (Scaled) Tj ET')
        data = io.BytesIO()
        pdf.save(data)
    result = run_worker('page', data.getvalue(), page=0)
    assert result.get('error') is None, result
    run = result['runs'][0]
    assert run['font_size'] == 12
    assert run['font_display_size'] == 24
    assert sum(v * v for v in run['direction']) == 576


def test_plain_edit_refuses_ambiguous_restored_font_without_changing_size(tmp_path: Path) -> None:
    source, output = tmp_path / 'in.pdf', tmp_path / 'out.pdf'
    fixture(source, b'BT /F1 12 Tf 72 700 Td q /F1 9 Tf Q (Hello world) Tj ET')
    before = source.read_bytes()
    run = next(r for r, _ in classify_document(source).runs if r.display_text == 'Hello world')
    report = apply_recipe(source, (RecipeOp(run.run_id, 'Hello'),), output)
    assert not report.ok
    assert report.resolved[0].reason == 'source_font_state_unsupported'
    assert source.read_bytes() == before
    assert not output.exists()
