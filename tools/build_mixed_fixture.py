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

Sizing is the ROADMAP's Phase 2 Success Criterion 3 verbatim: "a 40-page
contract with 3 scanned pages reports 37 editable pages and 40 page-op-able
pages". The fixture is therefore exactly 40 pages = 37 editable + 3 scanned.
(It was originally a scaled-down 10-page analog, 7 + 3; Gate G1 verification
flagged that the literal numbers were asserted nowhere, so it was grown to the
literal scenario.)

Sources (page-bucket classification re-measured 2026-08-17 by running
engine.classify_page.classify_page over every candidate page; earlier pikepdf
inspection of the scan pages recorded in .superpowers/sdd/02-02-PLAN/
task-2-report.md):

- corpus/public/irs_publication_17.pdf, pages 0-36 (0-indexed) — 37 editable
  text pages. The document has 142 pages; pages 0-36 are used because all 37
  of them measured bucket `editable` (no blank, image-heavy, or otherwise
  differently-bucketed page in the range), so no substitution from deeper in
  the document was needed. IRS Publication 17 is a typeset, non-OCR document.
- corpus/public/invoice_book_1842.pdf, pages 0, 1, 16 (0-indexed) — 3 of the
  document's 7 known zero-glyph scan pages (the manifest/research-verified
  "bucket 1" pages: full image coverage via two /Image XObjects each,
  zero Tj/TJ/'/" text-showing operators — no OCR text layer at all). The
  other 45 pages of invoice_book_1842.pdf carry an invisible OCR text layer
  (Tr 3) and are NOT used here; this fixture wants unambiguous scan pages.

Output order interleaves the two sources (40 pages total) to resemble the
CLAS-05 motivating case — "a contract with a few scanned pages mixed in" —
rather than grouping all scans at the end. The 3 scan pages land at 0-based
output indices 12, 25 and 38 (SCAN_POSITIONS below); every other output index
is the next unused irs_publication_17.pdf page in order.

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
TEXT_PAGES = list(range(37))

SCAN_SOURCE = "invoice_book_1842.pdf"
SCAN_PAGES = [0, 1, 16]

# 0-based indices in the 40-page output where a scan page goes.
SCAN_POSITIONS = (12, 25, 38)


def _page_plan() -> list[tuple[str, int]]:
    """(source, index-into-that-source's-page-list) in final page order."""
    plan: list[tuple[str, int]] = []
    text_i = scan_i = 0
    for out_i in range(len(TEXT_PAGES) + len(SCAN_PAGES)):
        if out_i in SCAN_POSITIONS:
            plan.append(("scan", scan_i))
            scan_i += 1
        else:
            plan.append(("text", text_i))
            text_i += 1
    return plan


PAGE_PLAN = _page_plan()


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
