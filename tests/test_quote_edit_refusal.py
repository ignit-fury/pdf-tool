"""Stateful quote text operators must never lose line movement during editing."""
from pathlib import Path

import pikepdf
import pytest

from engine.index import RunIndex
from engine.fit import FitResult
from engine.recipe import RecipeOp, apply_recipe, plan_recipe
from engine.rewrite import rewrite_run
from tools.build_security_fixtures import text_pdf


@pytest.mark.parametrize('operator', [b"(world) '", b'2 0.5 (world) "'])
@pytest.mark.parametrize('follower', [b'', b' (after) Tj'])
def test_quote_edit_refuses_before_preview_or_output(tmp_path: Path, operator: bytes, follower: bytes) -> None:
    source = tmp_path / 'quote.pdf'
    source.write_bytes(text_pdf())
    with pikepdf.open(source, allow_overwriting_input=True) as pdf:
        pdf.pages[0].Contents = pdf.make_stream(
            b'BT /F1 12 Tf 20 TL 20 150 Td (Hello) Tj ' + operator + follower + b' ET')
        pdf.save(source)
    original = source.read_bytes()
    with RunIndex(source) as index:
        runs = list(index.page(0).runs)
        run, verdict = next((run, verdict) for run, verdict in runs if 'world' in run.display_text)
    with pikepdf.open(source) as pdf:
        before = pdf.pages[0].Contents.read_bytes()
        outcome = rewrite_run(pdf, 0, run, verdict, [r for r, _ in runs], run.display_text,
                              FitResult(0, 0, 0, 'trailing_kern', []))
        assert not outcome.ok
        assert outcome.reason == 'stateful_text_showing_unsupported'
        assert pdf.pages[0].Contents.read_bytes() == before
    recipe = (RecipeOp(run.run_id, run.display_text),)
    plan = plan_recipe(source, recipe)
    assert not plan.ok
    assert plan.resolved[0].reason == 'stateful_text_showing_unsupported'
    output = tmp_path / 'output.pdf'
    report = apply_recipe(source, recipe, output)
    assert not report.ok
    assert not output.exists()
    assert source.read_bytes() == original
