"""Request-owned classified snapshots must stay fresh without triplicate walks."""
from dataclasses import replace
import io
from pathlib import Path

import pikepdf
import pytest

import engine.recipe as recipe_module
from engine.classify_run import RunVerdict
from engine.index import RunIndex
from engine.recipe import RecipeOp, apply_recipe
from tools.build_security_fixtures import text_pdf


def _source(tmp_path: Path, encrypted: bool = False) -> tuple[Path, tuple[RecipeOp, ...]]:
    source = tmp_path / "source.pdf"
    with pikepdf.open(io.BytesIO(text_pdf(b"Hello world"))) as pdf:
        pdf.pages[0].Contents = pdf.make_stream(
            b"BT /F1 12 Tf 72 700 Td (Hello world) Tj ET\n"
            b"BT /F1 12 Tf 72 660 Td (Second line) Tj ET\n"
            b"BT /F1 12 Tf 72 620 Td (Third line) Tj ET\n")
        pdf.save(source, encryption=pikepdf.Encryption(user="secret", owner="owner") if encrypted else False)
    with RunIndex(source, password="secret" if encrypted else "") as index:
        ops = tuple(RecipeOp(run.run_id, run.display_text.replace("line", "lane"))
                    for run, _ in index.page(0).runs)
    assert len(ops) == 3
    return source, ops


def test_snapshot_one_post_classification_per_edit(tmp_path, monkeypatch):
    source, ops = _source(tmp_path)
    calls = []
    original = RunIndex._parse_page

    def counted(self, page):
        calls.append(page)
        return original(self, page)

    monkeypatch.setattr(RunIndex, "_parse_page", counted)
    result = apply_recipe(source, ops, tmp_path / "output.pdf")
    assert result.ok, result
    # One immutable-source planning walk, followed by exactly one fresh guard per op.
    assert calls == [0] * (len(ops) + 1)


@pytest.mark.parametrize("encrypted", [False, True])
def test_snapshot_fresh_classification_refusal_is_atomic(tmp_path, monkeypatch, encrypted):
    source, ops = _source(tmp_path, encrypted)
    original_bytes = source.read_bytes()
    original = RunIndex._parse_page
    calls = 0

    def newly_refused(self, page):
        nonlocal calls
        result = original(self, page)
        calls += 1
        if calls > 1:
            return replace(result, runs=[(run, RunVerdict(state="not_editable", reason="snapshot_test_refusal"))
                                         for run, _ in result.runs])
        return result

    monkeypatch.setattr(RunIndex, "_parse_page", newly_refused)
    output = tmp_path / "output.pdf"
    report = apply_recipe(source, ops, output, password="secret" if encrypted else "")
    assert not report.ok
    assert report.resolved[1].reason == "snapshot_test_refusal"
    assert source.read_bytes() == original_bytes
    assert not output.exists()
