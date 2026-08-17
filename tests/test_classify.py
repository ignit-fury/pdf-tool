"""02-08 Task 1: engine/classify_page.py -- CLAS-01 four-bucket page classification.

Validated against the two corpus documents 02-RESEARCH.md Section 7 used to derive the
signal definitions and threshold table:
- nasa_graphics_standards_manual.pdf, page 52 -- an OCR'd scan, previously (and wrongly)
  labelled vector_outlined_text; the naive-sum coverage bug's own reproduction case
  (measured 2.749, see Pitfall 5).
- invoice_book_1842.pdf -- 52 pages, 7 pure-image scans plus 45 OCR'd-scan pages; one
  document supplying both scan buckets.

No document content (page text, counts derived from it) appears in assertion messages,
per this project's standing convention.
"""

import tempfile
from pathlib import Path

import pikepdf
import playa
import pytest

from engine.classify_page import (
    P_PATH_OBJECT_THRESHOLD,
    _path_object_count,
    classify_page,
    image_coverage,
)
import engine.classify_run as classify_run_module
import engine.walker as walker_module
from engine.classify_run import DocumentClassification, RunVerdict, classify_document
from engine.playa_boundary import Document, Page, image_bboxes
from engine.records import RunRecord
from engine.walker import glyph_records

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"

NASA_MANUAL = CORPUS_DIR / "nasa_graphics_standards_manual.pdf"
INVOICE_BOOK = CORPUS_DIR / "invoice_book_1842.pdf"
VECTOR_OUTLINED_SAMPLE = CORPUS_DIR / "vector_outlined_text_sample.pdf"
RENDER_MODE_7_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "render_mode_7.pdf"
MIXED_SCANNED_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "mixed_scanned.pdf"
IRS_1040_INSTRUCTIONS = CORPUS_DIR / "irs_1040_instructions.pdf"

# tools/build_mixed_fixture.py's own PAGE_PLAN: 0-based indices of the 3 constructed
# zero-glyph scan pages, interleaved among 7 editable irs_publication_17.pdf pages.
MIXED_SCANNED_SCAN_PAGES = {3, 6, 9}

# The specific page 02-08's brief verified: naive-sum coverage on this document is 2.749
# only here, not on an arbitrary page -- most pages of this document give a different
# naive-sum value.
NASA_PITFALL5_PAGE = 52


def _naive_sum_coverage(page: Page, doc: Document) -> float:
    """The WRONG formulation Pitfall 5 names: sum of each image bbox's own area (no
    clipping, no union) divided by CropBox area. Reproduced here, once, as a permanent
    negative-case mutation -- never as part of classify_page.py itself.
    """
    x0, y0, x1, y1 = page.cropbox
    area = (x1 - x0) * (y1 - y0)
    total = sum(
        max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
        for bx0, by0, bx1, by1 in image_bboxes(page, doc)
    )
    return total / area if area else 0.0


def test_ocr_scan_fixture() -> None:
    """nasa_graphics_standards_manual.pdf page 52 classifies as ocr_scan, not
    vector_outlined -- the corrected manifest label (02-RESEARCH.md Section 7's table:
    "Originally mislabelled vector_outlined_text... every glyph render mode 3... over
    984x1200 image XObjects")."""
    with playa.open(str(NASA_MANUAL)) as doc:
        page = doc.pages[NASA_PITFALL5_PAGE]
        records = glyph_records(page, doc)
        assert classify_page(records, page) == "ocr_scan"


def test_buckets_and_coverage_bounded() -> None:
    """Two things on the same page, together:

    1. image_coverage() never exceeds 1.0 across a sample of pages from both documents
       02-RESEARCH.md measured a naive-sum coverage above 1.0 on -- the union fix holds
       under the exact conditions that broke the old formulation.
    2. Pitfall 5's own reproduction: the naive-sum mutation, run against the SAME page,
       DOES reproduce the measured 2.749 value -- proving the bug is real and the fix is
       load-bearing, not merely described as fixed. Kept as a permanent negative case.
    """
    with playa.open(str(NASA_MANUAL)) as doc:
        page = doc.pages[NASA_PITFALL5_PAGE]
        naive = _naive_sum_coverage(page, doc)
        assert naive == pytest.approx(2.749, abs=5e-4), (
            "naive-sum mutation no longer reproduces the measured Pitfall-5 value -- "
            "the reproduction case itself has drifted"
        )
        fixed = image_coverage(page)
        assert 0.0 <= fixed <= 1.0
        assert fixed < naive, "union coverage must stay below the naive (broken) sum"

    with playa.open(str(INVOICE_BOOK)) as doc2:
        for page in doc2.pages:
            assert 0.0 <= image_coverage(page) <= 1.0


def test_invoice_book_scan_split() -> None:
    """invoice_book_1842.pdf's 52 pages classify as exactly 7 scan_no_text (pure image,
    no text layer) plus 45 ocr_scan (image + invisible OCR text layer) -- the measured
    split 02-RESEARCH.md Section 7's own table records for this document."""
    with playa.open(str(INVOICE_BOOK)) as doc:
        buckets: dict[str, int] = {}
        for page in doc.pages:
            records = glyph_records(page, doc)
            bucket = classify_page(records, page)
            buckets[bucket] = buckets.get(bucket, 0) + 1

    assert buckets == {"scan_no_text": 7, "ocr_scan": 45}, (
        f"bucket counts diverged from the measured split: {buckets}"
    )


def test_editable_fixture() -> None:
    """A page with real visible text and no image coverage classifies as editable --
    the common case, exercised on a normal (non-scan) corpus document."""
    with playa.open(str(CORPUS_DIR / "irs_form_w9.pdf")) as doc:
        page = doc.pages[0]
        records = glyph_records(page, doc)
        assert classify_page(records, page) == "editable"


def test_vector_outlined_fixture_path_count_crosses_threshold() -> None:
    """RESOLVED FINDING (2026-08-16, controller, pre-02-08-Task-2, revised after task
    review): the original vector_outlined_text_sample.pdf rendered one short line
    ("OUTLINED VECTOR TEXT", 18 letters, 18 filled paths) -- a demonstration case, not
    the page-scale sample 02-RESEARCH.md Section 7's `[ASSUMED: P ~= 200]` reasons from
    ("a page of outlined body text produces one path object per glyph, so hundreds"). It
    classified `empty`, not `vector_outlined`, which would have blocked 02-08 Task 2's
    own acceptance criterion.

    Fixed by EXTENDING the fixture, never by lowering `P_PATH_OBJECT_THRESHOLD` to fit
    one small file -- that would be exactly the test-fitting this project's validation
    strategy forbids. A first regeneration (12 lines, 216 fills) crossed P but only by an
    8% margin and was fairly flagged on review as itself still threshold-adjacent; the
    fixture now repeats the same glyph-outline construction 60 times (1080 glyphs, 1080
    `f` operators, same method, same licence, same disclosure -- see
    corpus/manifest.json's updated notes), 5.4x the threshold on the only count
    `_path_object_count` actually computes (fill operators only, never the construction
    operators `m`/`l`/`c`).
    """
    with playa.open(str(VECTOR_OUTLINED_SAMPLE)) as doc:
        page = doc.pages[0]
        count = _path_object_count(page)
        assert count == 1080
        assert count >= P_PATH_OBJECT_THRESHOLD
        records = glyph_records(page, doc)
        # Zero glyphs (it's outlined, not drawn text) and zero image coverage, so the
        # only discriminator in play is path_object_count -- at/above P, so
        # "vector_outlined", not "empty".
        assert classify_page(records, page) == "vector_outlined"


def test_low_path_count_classifies_empty() -> None:
    """The lower-side P guard (review finding, both on the task and on 88bece7 --
    deleted without replacement when the original below-threshold test was resolved).
    A synthetic page with zero glyphs, zero image coverage, and a path count well under
    P_PATH_OBJECT_THRESHOLD -- built inline, not `tests/fixtures/render_mode_7.pdf`,
    which carries glyphs and is the wrong shape for isolating this branch -- must
    classify `empty`, not `vector_outlined`.

    MUTATION: lowering P_PATH_OBJECT_THRESHOLD to 3 (below this fixture's 5 fills) turns
    this red -- confirmed by running it against the mutated threshold before restoring
    (10 was tried first and did NOT redden it, since 5 < 10 still holds; the mutation
    must cross below the fixture's own count, not merely below the real threshold).
    """
    pdf = pikepdf.Pdf.new()
    page = pdf.add_blank_page(page_size=(200, 200))
    # Five trivial triangle fills, drawn via m/l/h/f rather than the `re` shorthand --
    # _path_object_count groups `re` in with the painting operators (controller ruling
    # 5), so this isolates a plain count of 5 `f`s, one per shape, unambiguously.
    def _triangle(i: int) -> str:
        x = i * 10
        return f"{x} {x} m {x+5} {x} l {x+2} {x+5} l h f"

    content = "0 0 0 rg\n" + "\n".join(_triangle(i) for i in range(5)) + "\n"
    page.Contents = pdf.make_stream(content.encode("latin-1"))
    page.Resources = pikepdf.Dictionary({})

    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        pdf.save(tmp.name)
        pdf.close()
        with playa.open(tmp.name) as doc:
            playa_page = doc.pages[0]
            assert _path_object_count(playa_page) == 5
            assert _path_object_count(playa_page) < P_PATH_OBJECT_THRESHOLD
            records = glyph_records(playa_page, doc)
            assert classify_page(records, playa_page) == "empty"


def test_tr7_glyphs_are_invisible_and_a_render_mode_3_only_rule_misses_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLAS-02's stated Validation Architecture gap: "no mutation can make this check
    meaningful until a fixture exists" -- 02-02 built tests/fixtures/render_mode_7.pdf
    specifically to close it. Zero real Tr=7 glyphs exist anywhere in the 217-document
    corpus, so this fixture is the only place this rule can ever be proven to matter.

    CORRECTED (controller, pre-dispatch): the plan's action text said "its single glyph"
    -- the fixture actually has 26, all render_mode 7. Asserted against the real count.

    Tr=7 (add-to-clip-only) is invisible for a DIFFERENT reason than Tr=3 (neither fill
    nor stroke): a `render_mode != 3` check -- plausible if someone "simplified" the
    invisibility rule to the one case the OCR corpus actually exercises -- would
    misclassify every glyph on this fixture as visible. The mutation genuinely patches
    `engine.walker.INVISIBLE_RENDER_MODES` (module-level lookup, read at call time inside
    `glyph_records`, so `monkeypatch.setattr` on the module attribute takes effect on the
    next call) rather than reimplementing the old wrong predicate inline, which could
    silently drift from the real code path and prove nothing about it.
    """
    with playa.open(str(RENDER_MODE_7_FIXTURE)) as doc:
        page = doc.pages[0]
        records = glyph_records(page, doc)

    assert records, "expected glyphs on render_mode_7.pdf"
    assert len(records) == 26
    assert all(r.render_mode == 7 for r in records)
    assert all(r.visible is False for r in records)  # the correct rule

    # THE MUTATION: the old wrong rule, applied to the real code path.
    monkeypatch.setattr(walker_module, "INVISIBLE_RENDER_MODES", frozenset({3}))
    with playa.open(str(RENDER_MODE_7_FIXTURE)) as doc:
        page = doc.pages[0]
        mutated_records = glyph_records(page, doc)

    assert mutated_records
    assert all(r.visible is True for r in mutated_records), (
        "the render_mode != 3 mutation should have misclassified every Tr=7 glyph as "
        "visible -- if it did not, this test is no longer exercising the mutation it "
        "names, and is vacuous"
    )


# --------------------------------------------------------------------------------------
# 02-08 Task 3: CLAS-04/CLAS-05 -- engine/classify_run.py
# --------------------------------------------------------------------------------------


def test_mixed_scanned_page_buckets_match_construction() -> None:
    """tools/build_mixed_fixture.py's own PAGE_PLAN: 7 editable irs_publication_17.pdf
    pages interleaved with 3 zero-glyph scan pages from invoice_book_1842.pdf, at 0-based
    indices 3, 6, 9. classify_document's page_buckets must reproduce this exactly."""
    result = classify_document(MIXED_SCANNED_FIXTURE)
    assert len(result.page_buckets) == 10
    scan_indices = {i for i, b in enumerate(result.page_buckets) if b == "scan_no_text"}
    assert scan_indices == MIXED_SCANNED_SCAN_PAGES
    editable_indices = set(range(10)) - MIXED_SCANNED_SCAN_PAGES
    assert all(result.page_buckets[i] == "editable" for i in editable_indices)


def test_mixed_scanned_editable_pages_produce_editable_runs() -> None:
    """CLAS-04's acceptance criterion: the 7 constructed editable pages report
    editable_original/editable_substitution runs. irs_publication_17.pdf is a typeset,
    non-OCR document with ordinary embedded fonts, so editable_original is expected, but
    this asserts the weaker, more robust claim (either editable state) since exact font
    resolution branch is not this test's concern -- test_shared_xobject_run_refuses_with_
    share_count and the corpus-wide encoding_table tests already cover branch-level
    correctness."""
    result = classify_document(MIXED_SCANNED_FIXTURE)
    assert result.runs, "expected runs on the 7 editable pages"
    states = {v.state for _, v in result.runs}
    assert states <= {"editable_original", "editable_substitution"}, (
        f"expected only editable states on mixed_scanned.pdf's constructed editable "
        f"pages, got {states}"
    )


def test_mixed_scanned_scan_pages_contribute_zero_runs() -> None:
    """The 3 scan pages have zero glyphs by construction (build_mixed_fixture.py's own
    docstring: "zero Tj/TJ/'/\" text-showing operators -- no OCR text layer at all"), so
    clustering produces zero runs from them -- not a gap, the page_buckets entry already
    says scan_no_text. Verified by checking every run's page number against the known
    editable page indices, never against the scan indices."""
    result = classify_document(MIXED_SCANNED_FIXTURE)
    run_pages = {run.page for run, _ in result.runs}
    assert run_pages.isdisjoint(MIXED_SCANNED_SCAN_PAGES), (
        f"found runs on scan pages {run_pages & MIXED_SCANNED_SCAN_PAGES} -- scan pages "
        f"must contribute zero runs"
    )


def _document_uneditable_if_any_page_scanned(result: DocumentClassification) -> bool:
    """THE CLAS-05 MUTATION, replicated as a standalone helper -- never applied to
    classify_document itself, which must never gain a whole-document verdict. Proves the
    rejected design ("any scanned page makes the whole document uneditable") would have
    been wrong on this exact fixture."""
    return any(b != "editable" for b in result.page_buckets)


def test_clas05_whole_document_refusal_is_wrong() -> None:
    """CLAS-05's negative case: mixed_scanned.pdf genuinely has 3 non-editable pages
    (correctly bucketed scan_no_text) alongside 7 editable ones. The REJECTED rule would
    flag the whole document uneditable; classify_document's real per-page/per-run
    granularity correctly keeps the 7 editable pages' runs editable regardless."""
    result = classify_document(MIXED_SCANNED_FIXTURE)

    assert _document_uneditable_if_any_page_scanned(result) is True, (
        "the mutation should find at least one non-editable page bucket on this fixture "
        "-- if it does not, the fixture no longer mixes scan and editable pages and this "
        "negative case is vacuous"
    )
    # classify_document's REAL behaviour: the 7 editable pages' runs are still editable,
    # proving the document was never treated as wholesale uneditable.
    editable_states = {"editable_original", "editable_substitution"}
    assert any(v.state in editable_states for _, v in result.runs), (
        "classify_document incorrectly refused every run on a document that has "
        "genuinely editable pages -- CLAS-05 requires per-page/per-run refusal, never "
        "whole-document"
    )
    assert not hasattr(result, "editable"), (
        "DocumentClassification must carry no whole-document editability field at all"
    )


@pytest.mark.corpus
def test_shared_xobject_run_refuses_with_share_count() -> None:
    """The acceptance criterion's own named case: irs_1040_instructions.pdf's headline
    "TIP" callout is drawn inside Form XObject objid 351, shared across exactly 43 pages
    (engine.shared_xobjects, re-verified directly before this task's dispatch). The run
    sourced from it must verdict not_editable with a reason naming that count.
    """
    result = classify_document(IRS_1040_INSTRUCTIONS)
    shared_runs = [
        v for _r, v in result.runs if v.reason is not None and "shared Form XObject" in v.reason
    ]
    assert shared_runs, "expected at least one shared-Form-XObject run"
    assert all(v.state == "not_editable" for v in shared_runs)
    assert any("43 pages" in (v.reason or "") for v in shared_runs), (
        "expected a shared-XObject run naming the 43-page share count specifically"
    )


def test_classify_run_precedence_shared_xobject_before_type3() -> None:
    """The brief's specified precedence: a run inside a shared Form XObject refuses for
    THAT reason even if its font would also independently refuse as Type3 -- shared-
    XObject is checked first. Constructed directly against classify_run (not
    classify_document), isolating the precedence rule from real-document plumbing.

    MUTATION: swapping the order in classify_run (checking font_verdict.branch_id ==
    "T3-a" before the shared_xobject_ids check) would make this assert "Type3" instead
    -- confirmed by temporarily reordering the two checks and re-running this test before
    restoring, per the report.
    """
    from engine.classify_run import classify_run
    from engine.encoding_table import FontVerdict
    from engine.records import GlyphRecord, RunRecord
    from engine.types import CharCode, Unicode

    glyph = GlyphRecord(
        code=CharCode(1),
        glyph=None,
        unicode=Unicode("A"),
        x=0.0,
        y=0.0,
        advance=(1.0, 0.0),
        font_id=0,
        render_mode=0,
        visible=True,
        stream_id=0,
        operator_byte_offset=0,
        item_index_within_tj=None,
        byte_offset_within_string=0,
    )
    run = RunRecord(run_id="dummy", glyphs=[glyph], display_text="A", page=0)
    type3_font = FontVerdict("T3-a", True, False, None)
    verdict = classify_run(run, type3_font, shared_xobject_ids={5: 10}, xobj_path=(5,))
    assert verdict.state == "not_editable"
    assert verdict.reason is not None and "shared Form XObject" in verdict.reason


def _dummy_run(display_text: str, unicode: str = "A") -> RunRecord:
    from engine.records import GlyphRecord
    from engine.types import CharCode, Unicode

    glyph = GlyphRecord(
        code=CharCode(1),
        glyph=None,
        unicode=Unicode(unicode),
        x=0.0,
        y=0.0,
        advance=(1.0, 0.0),
        font_id=0,
        render_mode=0,
        visible=True,
        stream_id=0,
        operator_byte_offset=0,
        item_index_within_tj=None,
        byte_offset_within_string=0,
    )
    return RunRecord(run_id="dummy", glyphs=[glyph], display_text=display_text, page=0)


def test_classify_run_type3_always_refuses_regardless_of_font_verdict_editable() -> None:
    """The brief's Type3 rule: branch_id == 'T3-a' refuses NO MATTER what
    font_verdict.editable says (Type3 glyphs need their own CharProc rewrite, out of v1
    scope) -- unlike test_classify_run_precedence_shared_xobject_before_type3, this run
    has NO shared Form XObject, isolating the Type3 override itself rather than the
    shared-XObject-first precedence rule.

    MUTATION: patching classify_run to check `font_verdict.editable` instead of
    `branch_id == "T3-a"` would make this editable, since the constructed FontVerdict
    deliberately sets editable=True -- confirmed by monkeypatching the branch_id check
    away (forcing the Type3 branch to be skipped) and observing the run falls through to
    editable.
    """
    from engine.classify_run import classify_run
    from engine.encoding_table import FontVerdict

    run = _dummy_run("A")
    type3_font = FontVerdict("T3-a", True, False, None)

    verdict = classify_run(run, type3_font, shared_xobject_ids={}, xobj_path=())
    assert verdict.state == "not_editable"
    assert verdict.reason == "Type3"

    # THE MUTATION: disable the Type3-specific check the real precedence relies on by
    # feeding a font_verdict with the same editable=True but a non-Type3 branch_id --
    # if branch_id were NOT what classify_run actually keys on, this would still refuse.
    non_type3_but_editable = FontVerdict("SIMPLE", True, False, None)
    mutated = classify_run(run, non_type3_but_editable, shared_xobject_ids={}, xobj_path=())
    assert mutated.state != "not_editable" or mutated.reason != "Type3", (
        "expected branch_id=='T3-a' to be the thing producing the Type3 refusal -- if a "
        "non-Type3-but-otherwise-identical FontVerdict still refuses as Type3, this test "
        "proves nothing about the override"
    )


def test_classify_run_refuses_rtl_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLAS-04's RTL branch (02-07's own carry-forward: 'the VERDICT itself is 02-08's
    job'): a run whose display_text is RTL refuses even though its font is fully
    editable and it lives in no shared Form XObject and is not Type3.

    MUTATION: monkeypatching classify_run_module._is_rtl to always return False makes
    this run editable instead -- confirmed below before restoring (monkeypatch fixture
    auto-restores at test teardown).
    """
    from engine.classify_run import classify_run
    from engine.encoding_table import FontVerdict

    run = _dummy_run("א", unicode="א")  # Hebrew alef -- unambiguously RTL
    font_verdict = FontVerdict("SIMPLE", True, False, None)

    verdict = classify_run(run, font_verdict, shared_xobject_ids={}, xobj_path=())
    assert verdict.state == "not_editable"
    assert verdict.reason == "right-to-left text"

    # THE MUTATION: the real code path's own RTL predicate, disabled.
    monkeypatch.setattr(classify_run_module, "_is_rtl", lambda _text: False)
    mutated = classify_run(run, font_verdict, shared_xobject_ids={}, xobj_path=())
    assert mutated.state != "not_editable" or mutated.reason != "right-to-left text", (
        "expected _is_rtl to be the thing producing the RTL refusal -- if disabling it "
        "still refuses for the same reason, this test proves nothing"
    )


def test_classify_run_defensive_per_glyph_recheck_refuses_no_unicode_glyph() -> None:
    """The brief's third named mutation target: the defensive per-glyph re-check
    (D-05's isolation happens upstream in the clusterer; classify_run does not trust
    that blindly). A run whose font-level verdict is fully editable but whose one glyph
    has no resolvable unicode (glyph_verdict's NOUNI branch) must still refuse -- proving
    the per-glyph loop in classify_run, not just the font-level check, actually runs and
    is not dead code.
    """
    from engine.classify_run import classify_run
    from engine.encoding_table import FontVerdict

    run = _dummy_run("A", unicode="")  # empty unicode -- glyph_verdict's NOUNI branch
    font_verdict = FontVerdict("SIMPLE", True, False, None)

    verdict = classify_run(run, font_verdict, shared_xobject_ids={}, xobj_path=())
    assert verdict.state == "not_editable"
    assert verdict.reason == "NOUNI", (
        "expected the per-glyph re-check to refuse with glyph_verdict's own NOUNI "
        "reason -- a font-level verdict alone (editable=True here) would have passed "
        "this run, so this proves the per-glyph loop actually executes"
    )
