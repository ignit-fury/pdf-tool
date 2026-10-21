"""Encrypted sources use the same immutable-source recipe contract."""
from pathlib import Path

import pikepdf
import pytest

from engine.classify_run import classify_document
from engine.index import RunIndex
from engine.recipe import RecipeOp, apply_recipe, plan_recipe
from test_recipe import _build_apply_fixture


def test_encrypted_public_corpus_fixture_is_no_longer_an_exclusion() -> None:
    path = Path(__file__).resolve().parents[1] / 'corpus/public/irs_form_w9_encrypted.pdf'
    with RunIndex(path) as index:
        assert index.page_count == 6
        assert index.page(0).runs


def test_password_threaded_through_index_plan_and_apply(tmp_path: Path) -> None:
    source = tmp_path / "plain.pdf"
    encrypted = tmp_path / "encrypted.pdf"
    output = tmp_path / "out.pdf"
    _build_apply_fixture(source)
    with pikepdf.open(source) as pdf:
        pdf.save(encrypted, encryption=pikepdf.Encryption(owner="owner", user="secret", R=6))
    with pytest.raises(pikepdf.PasswordError):
        RunIndex(encrypted)
    with RunIndex(encrypted, password="secret") as index:
        run, _ = next((r, v) for r, v in index.page(0).runs if v.state != "not_editable")
    classified = classify_document(encrypted, password="secret")
    assert run.run_id in {r.run_id for r, _ in classified.runs}
    recipe = (RecipeOp(run.run_id, run.display_text),)
    assert plan_recipe(encrypted, recipe, password="secret").ok
    assert apply_recipe(encrypted, recipe, output, password="secret").ok
    assert output.exists()
