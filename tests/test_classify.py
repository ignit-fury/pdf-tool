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

from pathlib import Path

import playa
import pytest

from engine.classify_page import (
    P_PATH_OBJECT_THRESHOLD,
    _path_object_count,
    classify_page,
    image_coverage,
)
from engine.playa_boundary import Document, Page, image_bboxes
from engine.walker import glyph_records

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"

NASA_MANUAL = CORPUS_DIR / "nasa_graphics_standards_manual.pdf"
INVOICE_BOOK = CORPUS_DIR / "invoice_book_1842.pdf"
VECTOR_OUTLINED_SAMPLE = CORPUS_DIR / "vector_outlined_text_sample.pdf"

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
    """RESOLVED FINDING (2026-08-16, controller, pre-02-08-Task-2): the original
    vector_outlined_text_sample.pdf rendered one short line ("OUTLINED VECTOR TEXT", 18
    letters, 18 filled paths) -- a demonstration case, not the page-scale sample
    02-RESEARCH.md Section 7's `[ASSUMED: P ~= 200]` reasons from ("a page of outlined
    body text produces one path object per glyph, so hundreds"). It classified `empty`,
    not `vector_outlined`, which would have blocked 02-08 Task 2's own acceptance
    criterion.

    Fixed by EXTENDING the fixture, never by lowering `P_PATH_OBJECT_THRESHOLD` to fit
    one small file -- that would be exactly the test-fitting this project's validation
    strategy forbids. The corpus fixture now repeats the same glyph-outline construction
    12 times (216 glyphs, 216 `f` operators, same method, same licence, same disclosure
    -- see corpus/manifest.json's updated notes), a genuinely page-scale sample that
    crosses P on its own terms.
    """
    with playa.open(str(VECTOR_OUTLINED_SAMPLE)) as doc:
        page = doc.pages[0]
        count = _path_object_count(page)
        assert count == 216
        assert count >= P_PATH_OBJECT_THRESHOLD
        records = glyph_records(page, doc)
        # Zero glyphs (it's outlined, not drawn text) and zero image coverage, so the
        # only discriminator in play is path_object_count -- at/above P, so
        # "vector_outlined", not "empty".
        assert classify_page(records, page) == "vector_outlined"
