"""A PDF-split title retains its two point sizes in preserve-layout edits."""
from __future__ import annotations

import base64
import json
from pathlib import Path

from server.isolation import run_worker


def test_federal_title_keeps_initial_and_tail_sizes() -> None:
    source = (Path(__file__).resolve().parents[1] / "corpus/public/far_federal_acquisition_regulation.pdf").read_bytes()
    before = run_worker("page", source, page=0)
    initial = next(run for run in before["runs"] if run["text"] == "F" and run.get("font_size") == 75)
    tail = next(run for run in before["runs"] if run["text"] == "EDERAL" and run.get("font_size") == 60)
    assert initial["source_font_reusable"] is False
    assert tail["source_font_reusable"] is False

    recipe = json.dumps([{"run_id": initial["run_id"], "new_text": "F"},
                         {"run_id": tail["run_id"], "new_text": "EDS"}]).encode()
    result = run_worker("edit", source, recipe=recipe, timeout=45)
    assert result["ok"] is True
    assert all(row["font_substituted"] is True for row in result["resolved"])
    after = run_worker("page", base64.b64decode(result["pdf"]), page=0, timeout=45)
    assert any(run["text"] == "F" and run.get("font_size") == 75 for run in after["runs"])
    assert any(run["text"] == "EDS" and run.get("font_size") == 60 for run in after["runs"])
