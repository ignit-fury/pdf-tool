"""A visually composed glyph must not silently lose searchable Unicode."""
from pathlib import Path

from engine.index import RunIndex
from engine.recipe import RecipeOp, apply_recipe, plan_recipe
from tools.build_security_fixtures import text_pdf


def test_combining_accent_refuses_before_preview_and_output(tmp_path: Path) -> None:
    source = tmp_path / 'original.pdf'
    source.write_bytes(text_pdf(b'e'))
    with RunIndex(source) as index:
        run, _ = index.page(0).runs[0]
    recipe = (RecipeOp(run.run_id, 'e\u0301'),)
    report = plan_recipe(source, recipe)
    assert not report.ok
    assert report.resolved[0].reason == 'multi_character_shaping_unsupported'
    output = tmp_path / 'output.pdf'
    assert not apply_recipe(source, recipe, output).ok
    assert not output.exists()
