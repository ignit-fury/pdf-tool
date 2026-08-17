"""Tests for tools/measure_truetype_cmap_gaps.py's classifier (D-04 Open Question 1).

Exercises classify_font() against minimal in-memory cmap-subtable fixtures (no need for a fully
valid, loadable TrueType binary -- the classifier only reads platformID/platEncID off
tt["cmap"].tables), then runs measure() against the real public corpus to prove the full script
executes clean end to end.
"""

import json
import sys
from pathlib import Path

import pikepdf
from fontTools.fontBuilder import buildCmapSubTable
from fontTools.ttLib import TTFont, newTable

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"
MANIFEST_PATH = REPO_ROOT / "corpus" / "manifest.json"
sys.path.insert(0, str(REPO_ROOT / "tools"))

import measure_truetype_cmap_gaps as m  # noqa: E402


def _tt_with_cmap_subtables(pairs):
    """Build a bare TTFont whose 'cmap' table has one subtable per (platformID, platEncID) pair
    in `pairs` -- enough structure for classify_font(), not a loadable/saveable font."""
    tt = TTFont()
    cmap = newTable("cmap")
    cmap.tableVersion = 0
    cmap.tables = [
        buildCmapSubTable({65: "A"}, 4, platform_id, plat_enc_id) for platform_id, plat_enc_id in pairs
    ]
    tt["cmap"] = cmap
    return tt


def test_classify_usable_with_3_0_subtable():
    tt = _tt_with_cmap_subtables([(3, 0)])
    assert m.classify_font(tt) == "usable"


def test_classify_usable_with_1_0_subtable():
    tt = _tt_with_cmap_subtables([(1, 0)])
    assert m.classify_font(tt) == "usable"


def test_classify_tt_d_with_only_3_1_subtable():
    tt = _tt_with_cmap_subtables([(3, 1)])
    assert m.classify_font(tt) == "TT-d"


def test_classify_usable_when_3_1_and_3_0_both_present():
    # A (3,1) subtable alongside a usable (3,0) is NOT the TT-d case.
    tt = _tt_with_cmap_subtables([(3, 1), (3, 0)])
    assert m.classify_font(tt) == "usable"


def test_classify_tt_e_with_no_cmap_table_at_all():
    tt = TTFont()
    assert "cmap" not in tt
    assert m.classify_font(tt) == "TT-e"


def test_classify_font_bytes_raises_on_garbage_is_caught_by_measure():
    # classify_font_bytes() itself raises for a malformed program -- measure() is what catches
    # it and records "unparseable" (see test_measure_against_real_corpus_exits_clean below).
    try:
        m.classify_font_bytes(b"not a font")
    except Exception:
        pass
    else:
        raise AssertionError("expected classify_font_bytes to raise on garbage input")


def test_measure_against_real_corpus_exits_clean():
    """Pins the actual measured population (module docstring [VERIFIED] block, C1 fix) so any
    drift in enumeration or classification turns this test red -- not just "still an int"."""
    result = m.measure(str(MANIFEST_PATH), str(CORPUS_DIR))
    assert result["counts"] == {"TT-d": 0, "TT-e": 0, "usable": 80, "unparseable": 0}
    assert len(result["rows"]) == 80
    assert len({row["filename"] for row in result["rows"]}) == 25
    assert result["doc_failures"] == []


def test_document_level_traversal_survives_malformed_font_resources(tmp_path):
    """A page whose /Resources /Font entry is not dict-like (e.g. a bare int) makes
    iter_tt_b_fonts()'s `resources.get("/Font").items()` raise AttributeError, not
    pikepdf.PdfError. measure() must catch this at the document level and record a
    doc_failures row for that file -- not let the exception escape and abort every
    remaining document in the run. Reviewer-reported repro (see task-3-report.md addendum).
    """
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page()
    pdf.pages[0].Resources = pikepdf.Dictionary({"/Font": 5})
    pdf_path = tmp_path / "malformed_font_resources.pdf"
    pdf.save(pdf_path)
    pdf.close()

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps([{"filename": pdf_path.name}]))

    # measure() itself must not raise -- that is the crash this test guards against.
    result = m.measure(str(manifest_path), str(tmp_path))

    assert result["rows"] == []
    assert len(result["doc_failures"]) == 1
    assert result["doc_failures"][0]["filename"] == pdf_path.name
    assert "traversal failed" in result["doc_failures"][0]["reason"]


def test_pikepdf_open_non_pdferror_exception_recorded_not_raised(tmp_path):
    """pikepdf.open() can raise something other than pikepdf.PdfError -- e.g. an unreadable file
    raises PermissionError, an OSError subclass that pikepdf.PdfError is NOT (verified above).
    measure() must catch this at the pikepdf.open() call and record a doc_failures row, not let
    it escape and abort every remaining document in the manifest (I1: the traversal try/except
    was already broadened to bare Exception; the open() try/except was not). A second, readable
    document after it in the manifest must still be processed, proving the run survived.
    """
    assert not issubclass(pikepdf.PdfError, OSError)

    unreadable_path = tmp_path / "unreadable.pdf"
    unreadable_path.write_bytes(b"%PDF-1.4\n%not a real pdf")
    unreadable_path.chmod(0o000)

    ok_pdf = pikepdf.Pdf.new()
    ok_pdf.add_blank_page()
    ok_path = tmp_path / "ok.pdf"
    ok_pdf.save(ok_path)
    ok_pdf.close()

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps([{"filename": unreadable_path.name}, {"filename": ok_path.name}]))

    try:
        result = m.measure(str(manifest_path), str(tmp_path))
    finally:
        unreadable_path.chmod(0o644)

    assert len(result["doc_failures"]) == 1
    assert result["doc_failures"][0]["filename"] == unreadable_path.name
    assert "pikepdf.open failed" in result["doc_failures"][0]["reason"]


def test_never_reuses_content_stream_interpreter_or_imports_engine():
    source = (REPO_ROOT / "tools" / "measure_truetype_cmap_gaps.py").read_text()
    assert "parse_content_stream" not in source
    assert "unparse_content_stream" not in source
    assert "import engine" not in source
    assert "from engine" not in source
