"""A successful fit preview must also pass the actual rewrite layout guard."""
import json
from pathlib import Path

import pytest

from engine.index import RunIndex
from server.isolation import run_worker
from tools.build_security_fixtures import text_pdf


@pytest.mark.corpus
def test_preview_refuses_actual_layout_shift_without_returning_output() -> None:
    source = Path(__file__).resolve().parents[1] / "corpus/public/govdocs1_002_002154.pdf"
    original = source.read_bytes()
    with RunIndex(source) as index:
        target = next(run for run, _verdict in index.page(0).runs
                      if run.run_id.endswith(":p0:c0:o198"))
    recipe = json.dumps([{"run_id": target.run_id, "new_text": target.display_text[:3],
                          "style": {"font_family": "Sans"}}]).encode()
    preview = run_worker("edit", original, recipe=recipe, dry_run=True)
    applied = run_worker("edit", original, recipe=recipe)
    assert preview.get("ok") is False, preview
    assert preview["resolved"] == applied["resolved"]
    assert preview["resolved"][0]["reason"] == "text_matrix_shifted_after_edit"
    assert preview["pdf"] is None and applied["pdf"] is None
    assert source.read_bytes() == original


def test_successful_preview_returns_report_without_pdf_bytes() -> None:
    source = text_pdf(b"Hello world")
    page = run_worker("page", source, page=0)
    recipe = json.dumps([{"run_id": page["runs"][0]["run_id"], "new_text": "Hi"}]).encode()
    preview = run_worker("edit", source, recipe=recipe, dry_run=True)
    applied = run_worker("edit", source, recipe=recipe)
    assert preview.get("ok") is True, preview
    assert preview["resolved"] == applied["resolved"]
    assert preview["pdf"] is None
    assert applied["pdf"] is not None
