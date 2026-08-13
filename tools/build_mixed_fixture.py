"""One-off builder for two synthetic test fixtures the corpus cannot supply.

Run once; its output is committed under tests/fixtures/. Re-running regenerates
byte-identical-in-structure fixtures from the same source pages, so this script
is the audit trail for how they were built.

    uv run --frozen python tools/build_mixed_fixture.py

Fixture 1: tests/fixtures/mixed_scanned.pdf
--------------------------------------------
CLAS-05 ("refuse the operation, never the document") needs a document that
genuinely mixes editable text pages with scanned image-only pages. No corpus
document does this — invoice_book_1842.pdf is all-scanned, the inverse case.

Sources (verified 2026-08-13 by direct pikepdf inspection, see
.superpowers/sdd/02-02-PLAN/task-2-report.md for the measurement commands):

- corpus/public/irs_publication_17.pdf, pages 0-6 (0-indexed) — 7 editable
  text pages. Each page carries 18-369 Tj/TJ/'/" text-showing operators;
  confirmed non-scanned (not in the ocr_scan category; IRS Publication 17
  is a typeset, non-OCR document).
- corpus/public/invoice_book_1842.pdf, pages 0, 1, 16 (0-indexed) — 3 of the
  document's 7 known zero-glyph scan pages (the manifest/research-verified
  "bucket 1" pages: full image coverage via two /Image XObjects each,
  zero Tj/TJ/'/" text-showing operators — no OCR text layer at all). The
  other 45 pages of invoice_book_1842.pdf carry an invisible OCR text layer
  (Tr 3) and are NOT used here; this fixture wants unambiguous scan pages.

Output order interleaves the two sources (10 pages total) to resemble the
CLAS-05 motivating case — "a contract with a few scanned pages mixed in" —
rather than grouping all scans at the end:

    0 irs_pub17 p0    5 irs_pub17 p4
    1 irs_pub17 p1    6 invoice   p1   <- scan
    2 irs_pub17 p2    7 irs_pub17 p5
    3 invoice   p0    <- scan     8 irs_pub17 p6
    4 irs_pub17 p3    9 invoice   p16  <- scan

Fixture 2: tests/fixtures/render_mode_7.pdf
--------------------------------------------
CLAS-02's visible-glyph rule excludes render mode 3 (invisible) and 7
(add-to-clip). The 217-document corpus contains zero Tr=7 glyphs anywhere
(verified: measured render-mode distribution is Tr=0/Tr=3 only), so a check
written against the corpus alone cannot detect a Tr=7 regression. This
fixture is a minimal single-page PDF, built by hand (no source document —
there is nothing to lift, this property does not occur in nature here),
with one text-showing operation under `7 Tr` using the Standard-14 Helvetica
base font (no embedding required for a Standard-14 name).
"""

from pathlib import Path

import pikepdf
from pikepdf import Dictionary, Name

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"

TEXT_SOURCE = "irs_publication_17.pdf"
TEXT_PAGES = [0, 1, 2, 3, 4, 5, 6]

SCAN_SOURCE = "invoice_book_1842.pdf"
SCAN_PAGES = [0, 1, 16]

# (source, index-into-that-source's-page-list) in final page order.
PAGE_PLAN = [
    ("text", 0),
    ("text", 1),
    ("text", 2),
    ("scan", 0),
    ("text", 3),
    ("text", 4),
    ("scan", 1),
    ("text", 5),
    ("text", 6),
    ("scan", 2),
]


def build_mixed_scanned():
    text_src = pikepdf.open(CORPUS_DIR / TEXT_SOURCE)
    scan_src = pikepdf.open(CORPUS_DIR / SCAN_SOURCE)
    out = pikepdf.Pdf.new()
    try:
        for kind, i in PAGE_PLAN:
            if kind == "text":
                out.pages.append(text_src.pages[TEXT_PAGES[i]])
            else:
                out.pages.append(scan_src.pages[SCAN_PAGES[i]])
        out.save(FIXTURES_DIR / "mixed_scanned.pdf")
    finally:
        out.close()
        text_src.close()
        scan_src.close()


def build_render_mode_7():
    pdf = pikepdf.Pdf.new()
    try:
        page = pdf.add_blank_page(page_size=(612, 792))
        font = pdf.make_indirect(
            Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica)
        )
        page.Resources = Dictionary(Font=Dictionary(F1=font))
        content = b"BT /F1 24 Tf 100 700 Td 7 Tr (Invisible add-to-clip text) Tj ET"
        page.Contents = pdf.make_stream(content)
        pdf.save(FIXTURES_DIR / "render_mode_7.pdf")
    finally:
        pdf.close()


if __name__ == "__main__":
    build_mixed_scanned()
    build_render_mode_7()
    print("Wrote tests/fixtures/mixed_scanned.pdf and tests/fixtures/render_mode_7.pdf")
