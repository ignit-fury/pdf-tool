"""Style edits preserve unrelated text positions and graphics state."""
import json
from pathlib import Path

import pikepdf
import pytest

from engine.classify_run import classify_document
from engine.recipe import RecipeOp, apply_recipe, parse_recipe, plan_recipe
from engine.playa_boundary import open_document, walk_page
from test_recipe import _build_apply_fixture


def test_bold_style_preserves_word_separation_and_unicode(tmp_path: Path) -> None:
    from tools.build_security_fixtures import text_pdf
    source, output = tmp_path / 'in.pdf', tmp_path / 'out.pdf'
    source.write_bytes(text_pdf(b'Hello world'))
    run, _ = classify_document(source).runs[0]
    recipe = (RecipeOp(run.run_id, 'Hallo world', style={'bold': True}),)
    report = apply_recipe(source, recipe, output)
    assert report.ok
    assert report.resolved[0].strategy == 'tz'
    assert ''.join(r.display_text for r, _ in classify_document(output).runs) == 'Hallo world'


@pytest.mark.parametrize("style", [{"color": [1, 0.2, 0]}, {"bold": True}, {"italic": False}])
def test_optional_style_parses(style: dict[str, object]) -> None:
    op = parse_recipe(json.dumps([{"run_id": "x", "new_text": "a", "style": style}]).encode())[0]
    assert op.style == style
    assert parse_recipe(b'[{"run_id":"x","new_text":"a"}]')[0].style is None


@pytest.mark.parametrize("style", [{"color": [2, 0, 0]}, {"color": [True, 0, 0]}, {"color": [0, 1]}, {"bold": 1}, {"italic": "yes"}, {"font_size": float("nan")}, {"unknown": True}, None])
def test_invalid_styles_rejected(style: object) -> None:
    with pytest.raises(ValueError):
        parse_recipe(json.dumps([{"run_id": "x", "new_text": "a", "style": style}]).encode())


def test_size_change_named_refusal_and_no_output(tmp_path: Path) -> None:
    path = tmp_path / "in.pdf"
    _build_apply_fixture(path)
    run, _ = classify_document(path).runs[0]
    recipe = (RecipeOp(run.run_id, run.display_text, style={"font_size": 18}),)
    report = apply_recipe(path, recipe, tmp_path / "out.pdf")
    assert report.resolved[0].reason == "font_size_growth_unsupported"
    assert not (tmp_path / "out.pdf").exists()


def test_color_and_weight_preserve_other_glyphs_and_positions(tmp_path: Path) -> None:
    path = tmp_path / "in.pdf"
    output = tmp_path / "out.pdf"
    _build_apply_fixture(path)
    before = classify_document(path).runs
    run, _ = before[0]
    recipe = (RecipeOp(run.run_id, run.display_text, style={"color": [1, 0, 0], "bold": True, "italic": True}),)
    planned = plan_recipe(path, recipe)
    assert planned.ok
    assert planned.resolved[0].substitution_key == ("Sans", "BoldItalic")
    assert apply_recipe(path, recipe, output).ok
    after = classify_document(output).runs
    for original, _ in before[1:]:
        current = next(r for r, _ in after if r.page == original.page and r.display_text == original.display_text)
        assert [(g.x, g.y) for g in original.glyphs] == [(g.x, g.y) for g in current.glyphs]
    with pikepdf.open(output) as pdf:
        instructions = list(pikepdf.parse_content_stream(pdf.pages[0]))
        assert any(str(ins.operator) == "rg" and list(ins.operands) == [1, 0, 0] for ins in instructions)
        assert any(str(ins.operator) == "q" for ins in instructions)
        assert any(str(ins.operator) == "Q" for ins in instructions)


@pytest.mark.parametrize("color_state", [b"0.4 g", b"0.2 0.3 0.4 rg", b"0.1 0.2 0.3 0.4 k"])
@pytest.mark.parametrize("render_mode", [0, 1, 2])
def test_color_restores_existing_color_space_and_following_text_matrix(tmp_path: Path, color_state: bytes, render_mode: int) -> None:
    path = tmp_path / "color.pdf"
    output = tmp_path / "out.pdf"
    _build_apply_fixture(path)
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        # Both showing operators share one BT, so Q must retain the first one's
        # text advance while restoring its original nonstroking color space.
        pdf.pages[0].Contents = pdf.make_stream(color_state + f" {render_mode} Tr 0.15 0.25 0.35 RG".encode() + b" BT /F1 12 Tf 72 700 Td (Hello world) Tj 100 0 Td (Second line) Tj ET")
        pdf.save(path)
    with open_document(path) as doc:
        objects = [item[3] for item in walk_page(doc.pages[0], doc)]
        original = objects[1].gstate.ncolor
        original_stroke = objects[1].gstate.scolor
        position = objects[1].matrix
    target = next(r for r, _ in classify_document(path).runs if r.display_text == "Hello world")
    assert apply_recipe(path, (RecipeOp(target.run_id, target.display_text, style={"color": [1, 0, 0]}),), output).ok
    with open_document(output) as doc:
        objects = [item[3] for item in walk_page(doc.pages[0], doc)]
        assert objects[0].gstate.ncolor.values == (1, 0, 0)
        if render_mode in (1, 2):
            assert objects[0].gstate.scolor.values == (1, 0, 0)
        assert objects[1].gstate.ncolor == original
        assert objects[1].gstate.scolor == original_stroke
        assert objects[1].matrix == position


def test_two_style_variants_share_one_subset_each(tmp_path: Path) -> None:
    path = tmp_path / "in.pdf"
    output = tmp_path / "out.pdf"
    _build_apply_fixture(path)
    runs = classify_document(path).runs
    selected = [r for r, _ in runs if r.page == 0][:2]
    recipe = tuple(RecipeOp(r.run_id, r.display_text, style={"bold": i == 0, "italic": i == 1}) for i, r in enumerate(selected))
    report = apply_recipe(path, recipe, output)
    assert report.ok
    assert {r.substitution_key for r in report.resolved} == {("Sans", "Bold"), ("Sans", "Italic")}
    with pikepdf.open(output) as pdf:
        embedded = [font for font in pdf.pages[0].Resources.Font.values() if font.get("/Subtype") == pikepdf.Name("/Type0")]
        assert len(embedded) == 2
