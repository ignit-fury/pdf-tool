"""Tests for `tools/pdftool.py`'s `edit` subcommand -- D-03's dry-run default, `--commit`,
and the structured-then-human report.

Relies on [tool.pytest.ini_options] pythonpath = ["."] in pyproject.toml for a bare
`import engine`/`import tools`, matching tests/test_recipe.py's own convention.
"""

import argparse
import json
import re
from pathlib import Path

import pikepdf
import pytest
from fontTools.ttLib import TTFont

import tools.pdftool as pdftool_module
from engine.classify_run import classify_document
from engine.fonts import BundledFamily, BundledVariant, liberation_font_path
from engine.recipe import RecipeOp, apply_recipe, plan_recipe
from tools.pdftool import _cmd_edit

# Same span tests/test_recipe.py's fixtures use -- the bundled Liberation Sans face's
# printable-ASCII /Widths.
FIRST_CHAR = 32
LAST_CHAR = 126


def _liberation_widths(family: BundledFamily, variant: BundledVariant) -> list[int]:
    """A `/Widths` array over FIRST_CHAR..LAST_CHAR from a bundled Liberation face, in the
    1000-unit space `/Widths` is always expressed in. Copied from
    tests/test_recipe.py's own helper of the same name -- no shared import between test
    modules exists in this suite, and this one is a handful of lines."""
    ttf = TTFont(str(liberation_font_path(family, variant)))
    units_per_em = ttf["head"].unitsPerEm
    cmap = ttf.getBestCmap()
    hmtx = ttf["hmtx"]
    return [
        round(hmtx[cmap[code]][0] * 1000 / units_per_em) if code in cmap else 0
        for code in range(FIRST_CHAR, LAST_CHAR + 1)
    ]


def _build_fixture(path: Path) -> None:
    """A one-run, one-page document: `/F1` is BaseFont `/Arial` with the bundled
    LiberationSans-Regular embedded as `/FontFile2` -- classifies `editable_original`
    (embedded, so Phase 2 sees no substitution need), the same combination
    `tests/test_recipe.py::_build_apply_fixture`'s own `/F1` uses for its non-substituting
    rewrite path. Only one `Tj` in the whole part, so this run's own content-stream
    operator cannot be shared by another run -- sidesteps the one pre-existing dry-run/
    commit divergence Task 3's review flagged (`operator_shared_by_multiple_runs`).
    """
    pdf = pikepdf.Pdf.new()
    page = pdf.add_blank_page(page_size=(612, 792))

    descriptor = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/FontDescriptor"),
                "/FontName": pikepdf.Name("/Arial"),
                "/Flags": 32,  # non-symbolic
                "/FontBBox": pikepdf.Array([-203, -303, 1050, 910]),
                "/ItalicAngle": 0,
                "/Ascent": 905,
                "/Descent": -212,
                "/CapHeight": 715,
                "/StemV": 80,
                "/FontFile2": pdf.make_stream(
                    liberation_font_path("Sans", "Regular").read_bytes()
                ),
            }
        )
    )
    font = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/Font"),
                "/Subtype": pikepdf.Name("/TrueType"),
                "/BaseFont": pikepdf.Name("/Arial"),
                "/FirstChar": FIRST_CHAR,
                "/LastChar": LAST_CHAR,
                "/Widths": pikepdf.Array(_liberation_widths("Sans", "Regular")),
                "/Encoding": pikepdf.Name("/WinAnsiEncoding"),
                "/FontDescriptor": descriptor,
            }
        )
    )
    page.Resources = pikepdf.Dictionary({"/Font": pikepdf.Dictionary({"/F1": font})})
    page.Contents = pdf.make_stream(b"BT /F1 12 Tf 72 700 Td (Hello world) Tj ET\n")
    pdf.save(str(path))
    pdf.close()


@pytest.fixture()
def fixture_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "fixture.pdf"
    _build_fixture(path)
    return path


def _run_id(path: Path) -> str:
    """The fixture's one real run ID, obtained by calling `classify_document` directly --
    exactly as Task 2's own hash-proof test does, rather than hand-constructing a fake one."""
    runs = classify_document(path).runs
    assert len(runs) == 1, "fixture must produce exactly one run"
    run, verdict = runs[0]
    assert verdict.state == "editable_original"
    return run.run_id


def _write_recipe(dest: Path, run_id: str, new_text: str = "Hallo world") -> Path:
    recipe_path = dest.parent / "recipe.json"
    recipe_path.write_text(json.dumps([{"run_id": run_id, "new_text": new_text}]))
    return recipe_path


def _namespace(pdf_path: Path, recipe: Path, output: Path, *, commit: bool) -> argparse.Namespace:
    return argparse.Namespace(
        pdf_path=str(pdf_path), recipe=str(recipe), output=str(output), commit=commit
    )


def test_dry_run_writes_no_file_even_when_recipe_would_succeed(
    fixture_pdf: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_id = _run_id(fixture_pdf)
    recipe_path = _write_recipe(fixture_pdf, run_id)
    out = tmp_path / "out.pdf"

    exit_code = _cmd_edit(_namespace(fixture_pdf, recipe_path, out, commit=False))

    assert exit_code == 0
    assert not out.exists()
    captured = capsys.readouterr()
    assert run_id in captured.out
    assert "dry run" in captured.out


def test_commit_writes_file_when_recipe_succeeds(fixture_pdf: Path, tmp_path: Path) -> None:
    run_id = _run_id(fixture_pdf)
    recipe_path = _write_recipe(fixture_pdf, run_id)
    out = tmp_path / "out.pdf"

    exit_code = _cmd_edit(_namespace(fixture_pdf, recipe_path, out, commit=True))

    assert exit_code == 0
    assert out.exists()

    direct_out = tmp_path / "direct.pdf"
    apply_recipe(
        fixture_pdf, (RecipeOp(run_id=run_id, new_text="Hallo world"),), direct_out
    )
    # qpdf's modification ID includes time; two identical saves crossing a second
    # boundary legitimately differ there. Compare every other byte, including the
    # stable source ID, rather than depending on both saves finishing in one second.
    modified_id = rb'(/ID\s*\[\s*<[0-9A-Fa-f]+>\s*)<[0-9A-Fa-f]+>(\s*\])'
    left, left_count = re.subn(modified_id, rb'\1<modified-id>\2', out.read_bytes())
    right, right_count = re.subn(modified_id, rb'\1<modified-id>\2', direct_out.read_bytes())
    assert left_count == right_count == 1
    assert left == right


def test_commit_writes_no_file_when_recipe_refused(
    fixture_pdf: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recipe_path = _write_recipe(fixture_pdf, "not-a-run-id")
    out = tmp_path / "out.pdf"

    exit_code = _cmd_edit(_namespace(fixture_pdf, recipe_path, out, commit=True))

    assert exit_code == 1
    assert not out.exists()
    captured = capsys.readouterr()
    assert "malformed_run_id" in captured.out


def test_dry_run_matches_commit(fixture_pdf: Path, tmp_path: Path) -> None:
    """VALIDATION.md's pinned name: dry-run's `ok`/`reason`/`strategy`/`delta_pt` per op
    equal the SAME fields on the report `apply_recipe` returns for the same document and
    recipe -- proven by comparing the structured report objects, not printed text."""
    run_id = _run_id(fixture_pdf)
    recipe_ops = (RecipeOp(run_id=run_id, new_text="Hallo world"),)

    dry_report = plan_recipe(fixture_pdf, recipe_ops)
    commit_report = apply_recipe(fixture_pdf, recipe_ops, tmp_path / "committed.pdf")

    dry_fields = [(r.ok, r.reason, r.strategy, r.delta_pt) for r in dry_report.resolved]
    commit_fields = [
        (r.ok, r.reason, r.strategy, r.delta_pt) for r in commit_report.resolved
    ]
    assert dry_fields == commit_fields


def test_exit_code_reflects_report_ok(fixture_pdf: Path, tmp_path: Path) -> None:
    run_id = _run_id(fixture_pdf)
    ok_recipe = _write_recipe(fixture_pdf, run_id)

    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    bad_recipe = _write_recipe(bad_dir / "unused.pdf", "not-a-run-id")

    assert _cmd_edit(_namespace(fixture_pdf, ok_recipe, tmp_path / "a.pdf", commit=False)) == 0
    assert _cmd_edit(_namespace(fixture_pdf, ok_recipe, tmp_path / "b.pdf", commit=True)) == 0
    assert (
        _cmd_edit(_namespace(fixture_pdf, bad_recipe, tmp_path / "c.pdf", commit=False)) != 0
    )
    assert (
        _cmd_edit(_namespace(fixture_pdf, bad_recipe, tmp_path / "d.pdf", commit=True)) != 0
    )


def test_malformed_recipe_file_rejected_before_plan_recipe_runs(
    fixture_pdf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("plan_recipe must not be called for a malformed recipe file")

    monkeypatch.setattr(pdftool_module, "plan_recipe", _boom)

    malformed = tmp_path / "malformed.json"
    malformed.write_text("this is not json")
    out = tmp_path / "out.pdf"

    exit_code = _cmd_edit(_namespace(fixture_pdf, malformed, out, commit=False))

    assert exit_code == 1
    assert not out.exists()
