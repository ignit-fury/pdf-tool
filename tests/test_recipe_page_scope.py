"""Editing one page must not classify every unrelated page of a long document."""
import io
from pathlib import Path

import pikepdf
import pytest

import engine.classify_run as classify_module
import engine.index as index_module
from engine.index import RunIndex
from engine.recipe import RecipeOp, apply_recipe, plan_recipe
from tools.build_security_fixtures import text_pdf


@pytest.mark.parametrize('pages', [(7,), (2, 14)])
def test_planning_indexes_only_recipe_pages(tmp_path: Path, monkeypatch, pages) -> None:
    source = tmp_path / 'many.pdf'
    with pikepdf.open(io.BytesIO(text_pdf(b'Hello world'))) as pdf:
        for _ in range(15):
            pdf.pages.append(pdf.pages[0])
        pdf.save(source)
    with RunIndex(source) as index:
        operations = tuple(RecipeOp(index.page(p).runs[0][0].run_id, 'Hallo world') for p in pages)
    calls = []
    original = classify_module._classify_one_page

    def counted(*args, **kwargs):
        calls.append(args[3])
        return original(*args, **kwargs)

    monkeypatch.setattr(classify_module, '_classify_one_page', counted)
    monkeypatch.setattr(index_module, '_classify_one_page', counted)
    assert plan_recipe(source, operations).ok
    assert sorted(calls) == sorted(pages)
    calls.clear()
    assert apply_recipe(source, operations, tmp_path / 'output.pdf').ok
    assert set(calls) == set(pages)
