"""Preview must disclose structural rewrite refusals before offering Apply."""
import io
from pathlib import Path

import pikepdf
import pytest

from engine.index import RunIndex
from engine.recipe import RecipeOp, apply_recipe, plan_recipe
from tools.build_security_fixtures import text_pdf


@pytest.mark.parametrize("parts,reason", [
    ([b"BT /F1 12 Tf 20 100 Td (Hello world) Tj (", b"After) Tj ET"],
     "part_boundary_truncated"),
    ([b"BT /F1 12 Tf 20 100 Td [(Hello) -1000 (world)] TJ ET"],
     "operator_shared_by_multiple_runs"),
])
def test_preview_and_apply_refuse_unsafe_splices(tmp_path: Path, parts, reason) -> None:
    source, output = tmp_path / "source.pdf", tmp_path / "output.pdf"
    with pikepdf.open(io.BytesIO(text_pdf())) as pdf:
        pdf.pages[0].Contents = pikepdf.Array([pdf.make_stream(raw) for raw in parts])
        pdf.save(source)
    original = source.read_bytes()
    with RunIndex(source) as index:
        target = next(run for run, verdict in index.page(0).runs
                      if verdict.state.startswith("editable"))
    recipe = (RecipeOp(target.run_id, "Hi"),)
    preview = plan_recipe(source, recipe)
    assert not preview.ok
    assert preview.resolved[0].reason == reason
    applied = apply_recipe(source, recipe, output)
    assert not applied.ok
    assert applied.resolved[0].reason == reason
    assert not output.exists()
    assert source.read_bytes() == original
