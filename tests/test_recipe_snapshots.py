"""Request-owned classified snapshots must stay fresh without triplicate walks."""
from dataclasses import replace
import io
from pathlib import Path

import pikepdf
import pytest

import engine.rewrite as rewrite_module
import engine.fonts as fonts_module
import engine.fit as fit_module
from engine.classify_run import RunVerdict
from engine.index import RunIndex
from engine.recipe import RecipeOp, apply_recipe
from tools.build_security_fixtures import text_pdf


def test_cid_advance_resolves_each_distinct_code_once_without_stale_widths(monkeypatch):
    font = pikepdf.Dictionary(Subtype=pikepdf.Name.Type0, DescendantFonts=pikepdf.Array([
        pikepdf.Dictionary(W=pikepdf.Array([1, pikepdf.Array([500, 600]), 10, 12, 700]), DW=1000)
    ]))
    calls = []
    original = fit_module.cid_width

    def counted(descendant, code):
        calls.append(code)
        return original(descendant, code)

    monkeypatch.setattr(fit_module, "cid_width", counted)
    assert fit_module.advance_pt_for_codes(font, [1, 1, 2, 10, 99], 12) == pytest.approx(39.6)
    assert sorted(calls) == [1, 2, 10, 99]
    calls.clear()
    font.DescendantFonts[0].W = pikepdf.Array([1, pikepdf.Array([800]), 9])
    # The next call sees changed /W; its truncated tail still falls through to /DW.
    assert fit_module.advance_pt_for_codes(font, [1, 1, 99], 10) == 26
    assert sorted(calls) == [1, 99]


@pytest.fixture
def full_classification_fallback(monkeypatch):
    from engine.part_snapshot import PartSnapshot
    monkeypatch.setattr(PartSnapshot, "create", lambda *_args: None)


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


def test_snapshot_one_post_classification_per_edit(tmp_path, monkeypatch, full_classification_fallback):
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


def test_snapshot_guard_sorts_each_before_and_after_part_once(tmp_path, monkeypatch):
    source, ops = _source(tmp_path)
    calls = []
    original = rewrite_module._part_glyphs_in_stream_order

    def counted(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(rewrite_module, "_part_glyphs_in_stream_order", counted)
    assert apply_recipe(source, ops, tmp_path / "output.pdf").ok
    assert len(calls) <= 2 * len(ops)


def test_fast_context_checks_every_splice_without_full_reclassification(tmp_path, monkeypatch):
    from engine.part_snapshot import PartSnapshot
    source, ops = _source(tmp_path)
    checks, parses = [], []
    original_check = PartSnapshot.check_after
    original_parse = RunIndex._parse_page

    def checked(self, pdf):
        checks.append(1)
        return original_check(self, pdf)

    def parsed(self, page):
        parses.append(page)
        return original_parse(self, page)

    monkeypatch.setattr(PartSnapshot, "check_after", checked)
    monkeypatch.setattr(RunIndex, "_parse_page", parsed)
    report = apply_recipe(source, ops, tmp_path / "output.pdf")
    assert report.ok, [row.reason for row in report.resolved]
    assert len(checks) == len(ops)
    assert parses == [0]


def test_fast_context_correlates_current_operator_domain_only_once(tmp_path, monkeypatch):
    source, ops = _source(tmp_path)
    original = rewrite_module._correlate
    calls = []

    def counted(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(rewrite_module, "_correlate", counted)
    assert apply_recipe(source, ops, tmp_path / "output.pdf").ok
    # Immutable-source planning plus one current proof per actual splice.
    assert len(calls) <= 2 * len(ops)


@pytest.mark.parametrize("encrypted", [False, True])
def test_fast_context_late_guard_refusal_discards_every_edit(tmp_path, monkeypatch, encrypted):
    from engine.part_snapshot import PartSnapshot
    source, ops = _source(tmp_path, encrypted)
    before = source.read_bytes()
    original = PartSnapshot.check_after
    calls = []

    def fail_second(self, pdf):
        result = original(self, pdf)
        calls.append(1)
        return "text_matrix_shifted_after_edit" if len(calls) == 2 else result

    monkeypatch.setattr(PartSnapshot, "check_after", fail_second)
    output = tmp_path / "output.pdf"
    report = apply_recipe(source, ops, output, password="secret" if encrypted else "")
    assert not report.ok
    assert report.resolved[1].reason == "text_matrix_shifted_after_edit"
    assert len(calls) == 2
    assert not output.exists()
    assert source.read_bytes() == before


@pytest.mark.parametrize("encrypted", [False, True])
def test_snapshot_fresh_classification_refusal_is_atomic(tmp_path, monkeypatch, encrypted, full_classification_fallback):
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


def test_snapshot_guard_refuses_real_following_glyph_shift(tmp_path, monkeypatch):
    source = tmp_path / "relative.pdf"
    with pikepdf.open(io.BytesIO(text_pdf(b"Hello"))) as pdf:
        pdf.pages[0].Contents = pdf.make_stream(
            b"BT /F1 12 Tf 72 700 Td (Hello) Tj 1 0 0 rg (world) Tj ET")
        pdf.save(source)
    with RunIndex(source) as index:
        runs = index.page(0).runs
        assert len(runs) == 2
        operation = RecipeOp(runs[0][0].run_id, "Hallo")
    original = rewrite_module._show_instruction
    monkeypatch.setattr(rewrite_module, "_show_instruction",
                        lambda units, fit: original(units + units, fit))
    output = tmp_path / "bad.pdf"
    report = apply_recipe(source, (operation,), output)
    assert not report.ok
    assert report.resolved[0].reason == "text_matrix_shifted_after_edit"
    assert not output.exists()


def test_snapshot_projection_preserves_geometry_and_unedited_pages(tmp_path):
    source, _ = _source(tmp_path)
    with pikepdf.open(source) as pdf:
        page = pdf.pages[0]
        page.Rotate = 90
        page.Annots = pikepdf.Array([pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Link,
            Rect=pikepdf.Array([0, 0, 10, 10])))])
        pdf.pages.append(page)
        pdf.save(tmp_path / "two-pages.pdf")
    path = tmp_path / "two-pages.pdf"
    with RunIndex(path) as index:
        before = index.page(1).runs
        operations = tuple(RecipeOp(run.run_id, run.display_text.replace("line", "lane"))
                           for run, _ in before)
    with pikepdf.open(path) as pdf:
        assert rewrite_module._can_project_page(pdf.pages[1])
        snapshot = rewrite_module._current_page_snapshot(pdf, 1)
        assert [(r.page, r.display_text, r.page_ctm, [(g.x, g.y, g.code) for g in r.glyphs], v)
                for r, v in snapshot.runs] == [
                    (r.page, r.display_text, r.page_ctm, [(g.x, g.y, g.code) for g in r.glyphs], v)
                    for r, v in before]
        other = pdf.pages[0].Contents.read_bytes()
    output = tmp_path / "edited.pdf"
    assert apply_recipe(path, operations, output).ok
    with pikepdf.open(output) as pdf:
        assert pdf.pages[0].Contents.read_bytes() == other
        assert len(pdf.pages[1].Annots) == 1


def test_snapshot_shared_form_keeps_full_document_classification(tmp_path):
    source, _ = _source(tmp_path)
    with pikepdf.open(source) as pdf:
        page = pdf.pages[0]
        form = pdf.make_stream(page.Contents.read_bytes())
        form.Type = pikepdf.Name.XObject
        form.Subtype = pikepdf.Name.Form
        form.BBox = pikepdf.Array([0, 0, 612, 792])
        form.Resources = page.Resources
        page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Shared=form))
        page.Contents = pdf.make_stream(b"/Shared Do")
        pdf.pages.append(page)
        pdf.save(tmp_path / "shared.pdf")
    with pikepdf.open(tmp_path / "shared.pdf") as pdf:
        assert not rewrite_module._can_project_page(pdf.pages[0])
        snapshot = rewrite_module._current_page_snapshot(pdf, 0)
        assert len(snapshot.runs) == 3
        assert all(verdict.state == "not_editable" and "shared" in verdict.reason
                   for _, verdict in snapshot.runs)


def test_bundled_metadata_loaded_once_without_caching_document_text(monkeypatch):
    # The metadata cache is bounded by the twelve installed bundled faces, never
    # by user text. Every call still shapes its own buffer.
    cache = getattr(fonts_module, "_bundled_shaping_metadata", None)
    if cache is not None:
        cache.cache_clear()
    calls = []
    original = fonts_module.TTFont

    def counted(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(fonts_module, "TTFont", counted)
    first = fonts_module.shape_glyph_names("Sans", "Regular", "Hello world")
    second = fonts_module.shape_glyph_names("Sans", "Regular", "Hello ﬁ world")
    assert first == ("H", "e", "l", "l", "o", "space", "w", "o", "r", "l", "d")
    assert second == ("H", "e", "l", "l", "o", "space", "uniFB01", "space", "w", "o", "r", "l", "d")
    assert len(calls) == 1
