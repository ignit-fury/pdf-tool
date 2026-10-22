"""Readable Type 1/CFF source fonts must reach the replacement-font path."""
from pathlib import Path

import pytest
import pikepdf

from engine.index import RunIndex
from engine.recipe import RecipeOp, apply_recipe, plan_recipe
from tools.audit_corpus_edits import validate_output

CORPUS = Path(__file__).resolve().parents[1] / "corpus/public"


def _target(source: Path):
    with RunIndex(source) as index:
        runs = [run for run, verdict in index.page(0).runs
                if verdict.state.startswith("editable") and len(run.display_text.strip()) >= 2]
    return sorted(runs, key=lambda run: (-min(len(run.display_text), 80), run.run_id))[0]


@pytest.mark.corpus
@pytest.mark.parametrize("filename,family", [
    ("govdocs1_012_012084.pdf", None),
    ("govdocs1_000_000013.pdf", "Serif"),
])
def test_non_sfnt_font_can_apply_with_replacement_font(tmp_path: Path, filename, family) -> None:
    source = CORPUS / filename
    original = source.read_bytes()
    target = _target(source)
    replacement = target.display_text[:3].rstrip()
    style = {"font_family": family} if family else None
    recipe = (RecipeOp(target.run_id, replacement, style=style),)
    planned = plan_recipe(source, recipe)
    assert planned.ok, [item.reason for item in planned.resolved]
    assert planned.resolved[0].substitution_key == ("Serif", "Regular")
    output = tmp_path / "edited.pdf"
    applied = apply_recipe(source, recipe, output)
    assert applied.ok, [item.reason for item in applied.resolved]
    with pikepdf.open(output) as pdf:
        assert any("LiberationSerif" in str(font.get("/BaseFont", ""))
                   for font in pdf.pages[0].Resources.Font.values())
    with RunIndex(source) as index:
        pages = index.page_count
    checked = validate_output(original, output.read_bytes(), 0, target.display_text, replacement, pages)
    assert checked["independent_text"] == "verified", checked
    assert not checked["corrupt"]
    assert source.read_bytes() == original


@pytest.mark.corpus
def test_unmapped_non_sfnt_font_requests_explicit_font_choice() -> None:
    source = CORPUS / "govdocs1_000_000013.pdf"
    target = _target(source)
    planned = plan_recipe(source, (RecipeOp(target.run_id, "Hi"),))
    assert not planned.ok
    assert planned.resolved[0].reason.startswith("no mapping table entry for BaseFont")
