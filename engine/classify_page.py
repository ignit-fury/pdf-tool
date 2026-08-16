"""CLAS-01/02/03/05: page-level six-bucket classification.

The last stage before Phase 2's data model is complete -- given a page's `GlyphRecord`s
(02-04's `engine.walker.glyph_records`) and its playa `Page`, decides which of six buckets
the page falls into: `scan_no_text`, `ocr_scan`, `vector_outlined`, `empty`, `editable`,
`mixed_degraded`. Transcribes 02-RESEARCH.md Section 7's three signals and threshold table
exactly (Pitfall 5's union-not-sum fix included), per the 02-08 plan's controller rulings.

## Signal 1 -- visible glyph count

`GlyphRecord.visible` (set by `engine.walker`) is ALREADY `render_mode not in {3, 7}` --
used directly here, not re-derived (controller ruling 1). The other half of signal 1's
definition (02-RESEARCH.md Section 7, second bullet) is clipping: a glyph whose `(x, y)`
falls outside the page's CropBox does not count as visible even if its render mode says it
should. playa 1.1.0 does not populate `GraphicState.clipping_path`
(`[VERIFIED: read playa/content.py GraphicState]`), so this module approximates true
clipping with a CropBox point-in-rect test -- a KNOWN, ACCEPTED LIMITATION, not a silent
gap (controller ruling 3): a glyph clipped by a non-rectangular or nested clip path that
still falls inside the CropBox is (incorrectly) counted visible.

## Signal 2 -- image coverage (Pitfall 5)

Summing image-XObject bbox areas and dividing by page area is WRONG -- it exceeds 1.0 on
real scanned documents (a scanner emits several overlapping/tiled image XObjects per page;
measured 2.749 on a real corpus document, see tests/test_classify.py's permanent
negative-case mutation test). `image_coverage` instead rasterises the CropBox-clipped union
of image bboxes onto an 80x80 boolean occupancy grid and reports the occupied fraction --
bounded to [0, 1] by construction, never a sum.

## Signal 3 -- invisible:visible glyph ratio

`invisible / max(visible, 1)`, both counts as defined by signal 1 above.

## The OCG `/D /OFF` check is OUT OF SCOPE (controller ruling 4, deliberate)

02-RESEARCH.md Section 7's third visibility bullet (an optional-content group OFF by
default) needs per-glyph marked-content stack info (`mcstack`) that `GlyphRecord`'s fixed 13
fields do not carry, and only 3 of 216 corpus documents have `/OCProperties` at all
(`[VERIFIED: measured]`) -- "low frequency... do not over-invest." Threading `mcstack`
through the walker for that frequency is new plumbing disproportionate to the payoff;
deferred to a later task if the frequency ever justifies it. A page with glyphs hidden by
an OFF OCG is therefore (incorrectly) counted visible here.

White-on-white text hiding (signal 1's fourth bullet) is also out of scope -- it requires
compositing, which this module does not do.

## The vector-outlined discriminator (Assumption A3)

Vector-outlined text and a scan both present zero glyphs (`visible + invisible == 0`); they
differ on signal 2 only. Below the coverage threshold, `path_object_count` -- occurrences of
ISO 32000-1's path-painting operators (Table 60: `f F f* S s B B* b b*`, plus `re`, Table
59's rectangle shorthand, per controller ruling 5's grouping) on the page's own /Contents --
discriminates a page of outlined body text (one path object per glyph, hundreds) from a
decorative or empty page (tens). `P_PATH_OBJECT_THRESHOLD` is `[ASSUMED: P ~= 200]`,
02-RESEARCH.md Section 7's own unvalidated starting value -- no fixture existed to pick it
until 02-02 built `vector_outlined_text_sample.pdf`.

Implemented with `pikepdf.parse_content_stream` directly rather than through
`engine.playa_boundary` (which does not expose an operator-count API and, per the
one-module rule, is the only file allowed to `import playa`): this makes classify_page.py
the first module needing both pikepdf and playa-derived types, which is fine -- only
`import playa` is restricted to one file, and this module never writes that import.
`/Contents` parts are joined with a plain separator before parsing; the run-ID discipline
that governs part-boundary correctness elsewhere in this codebase does not apply to a plain
threshold count (controller ruling 5).
"""

from __future__ import annotations

import math
from typing import Literal

import pikepdf

from engine.playa_boundary import Page, image_bboxes
from engine.records import GlyphRecord

Bucket = Literal[
    "scan_no_text",
    "ocr_scan",
    "vector_outlined",
    "empty",
    "editable",
    "mixed_degraded",
]

# 02-RESEARCH.md Section 7: "an 80x80 boolean grid over the CropBox is sufficient and
# O(images)".
GRID = 80

COVERAGE_THRESHOLD = 0.5
MIXED_INVISIBLE_RATIO_THRESHOLD = 3

# ISO 32000-1 Table 60 (path-painting) plus `re` (Table 59, grouped in per controller
# ruling 5): each occurrence closes one filled/stroked path object.
_PATH_PAINT_OPS = "re f F f* S s B B* b b*"
P_PATH_OBJECT_THRESHOLD = 200


def _path_object_count(page: Page) -> int:
    """Occurrences of path-painting operators on the page's own /Contents (Assumption
    A3's discriminator). A scratch, throwaway `pikepdf.Pdf` wraps the joined stream bytes
    so `pikepdf.parse_content_stream` -- which needs a pikepdf `Object | Page`, not raw
    bytes -- has something to operate on; nothing about this scratch object is retained.
    """
    joined = b"\n".join(bytes(stream.buffer) for stream in page.streams)
    scratch = pikepdf.new()
    stream_obj = pikepdf.Stream(scratch, joined)
    return len(pikepdf.parse_content_stream(stream_obj, _PATH_PAINT_OPS))


def image_coverage(page: Page) -> float:
    """Fraction of the CropBox covered by the union of image-XObject bboxes, via an
    80x80 boolean occupancy grid -- bounded to [0, 1] by construction. Pitfall 5: never
    sum bbox areas, which double-counts overlapping/tiled scan images and exceeds 1.0.
    """
    x0, y0, x1, y1 = page.cropbox
    width, height = x1 - x0, y1 - y0
    if width <= 0 or height <= 0:
        return 0.0
    occupied: set[tuple[int, int]] = set()
    for bx0, by0, bx1, by1 in image_bboxes(page, page.doc):
        cx0, cy0 = max(bx0, x0), max(by0, y0)
        cx1, cy1 = min(bx1, x1), min(by1, y1)
        if cx1 <= cx0 or cy1 <= cy0:
            continue  # no overlap with the CropBox at all
        col0 = max(0, min(GRID - 1, math.floor((cx0 - x0) / width * GRID)))
        col1 = max(0, min(GRID, math.ceil((cx1 - x0) / width * GRID)))
        row0 = max(0, min(GRID - 1, math.floor((cy0 - y0) / height * GRID)))
        row1 = max(0, min(GRID, math.ceil((cy1 - y0) / height * GRID)))
        for row in range(row0, row1):
            for col in range(col0, col1):
                occupied.add((row, col))
    coverage = len(occupied) / (GRID * GRID)
    # Pitfall 5's own warning sign, as an always-on tripwire (matching this codebase's
    # tripwire convention, e.g. playa_boundary's _curpos assertion): a grid-occupancy
    # fraction is bounded by construction, so this can only fire if that construction is
    # broken, not from a bad input document.
    assert 0.0 <= coverage <= 1.0, f"image_coverage escaped its bound: {coverage}"
    return coverage


def classify_page(glyph_records: list[GlyphRecord], page: Page) -> Bucket:
    """One of six buckets, per 02-RESEARCH.md Section 7's threshold table. See the
    module docstring for signal definitions and known, accepted limitations (CropBox
    clipping approximation, no OCG /D /OFF check, no white-on-white detection).
    """
    x0, y0, x1, y1 = page.cropbox

    def _visible(rec: GlyphRecord) -> bool:
        return rec.visible and x0 <= rec.x <= x1 and y0 <= rec.y <= y1

    visible = sum(1 for r in glyph_records if _visible(r))
    invisible = sum(1 for r in glyph_records if not r.visible)
    coverage = image_coverage(page)

    if visible > 0:
        if (
            coverage >= COVERAGE_THRESHOLD
            and invisible / visible >= MIXED_INVISIBLE_RATIO_THRESHOLD
        ):
            return "mixed_degraded"
        return "editable"

    if coverage >= COVERAGE_THRESHOLD:
        return "ocr_scan" if invisible > 0 else "scan_no_text"

    if _path_object_count(page) >= P_PATH_OBJECT_THRESHOLD:
        return "vector_outlined"
    return "empty"


__all__ = [
    "Bucket",
    "COVERAGE_THRESHOLD",
    "GRID",
    "MIXED_INVISIBLE_RATIO_THRESHOLD",
    "P_PATH_OBJECT_THRESHOLD",
    "classify_page",
    "image_coverage",
]
