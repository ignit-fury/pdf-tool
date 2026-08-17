"""D-06: the page-at-a-time cached run index -- the first place the whole Phase 2
pipeline (`engine.walker` -> `engine.encoding_table` -> `engine.clusterer` ->
`engine.classify_page`/`engine.classify_run`) composes into one document-scale API.

`RunIndex(path).page(n)` parses page `n` on first access and caches the result;
a second call is a cache hit. Nothing is parsed eagerly (02-RESEARCH.md Pitfall 8):
`engine.classify_run.classify_document` already exists as the eager, whole-document
alternative and is measured at 21.0s/166MB on a 126-page document
(`irs_1040_instructions.pdf`) -- lazy per-page parsing is ~15ms for the same first page.
`RunIndex` reuses `classify_document`'s own per-page pipeline body,
`engine.classify_run._classify_one_page`, rather than duplicating it (02-09-PLAN.md
Task 1 brief, ruling 1) -- this module owns none of the walk/cluster/classify logic
itself, only the lazy-open/cache/evict shell around it.

## What "columnar per-page glyph storage" means here (brief ruling 2)

The walker/clusterer/classify_run pipeline still operates on real `GlyphRecord` objects
internally per page -- that interface is locked (`engine/records.py`) and this module
does not touch it. "Columnar, not one Python object per glyph" governs what `RunIndex`
RETAINS after a page is processed, not what the pipeline uses while running one.

02-RESEARCH.md Section 10's own recommendation: "Keeping the run records (~50/page,
negligible) while evicting the glyph arrays is the natural two-tier split." Concretely,
`RunIndex` retains exactly `PageIndex` per cached page -- `bucket`, the small `runs` list
(each `RunRecord` already carries only the glyphs that survived into an actual run, not
every glyph the page walk touched), and a `glyph_count` scalar. There is no separate,
literal `array.array`-per-field cache tier: once a page's pipeline has produced its runs,
the transient per-glyph `GlyphRecord` list the walker built is simply not retained at
all, which is a stricter memory posture than a columnar array (a columnar array is what
you would need if you WERE retaining raw per-glyph geometry for every located glyph --
this module deliberately does not, so building one would add a structure with nothing
to hold). `glyph_count` is retained specifically because it is the unit the eviction
budget below is denominated in, matching 02-RESEARCH.md Section 10's own "cap the cache
by glyph count, not page count" framing and its measured 178MB/1.9M-glyph/400-page
figure -- even though what `RunIndex` actually retains per page is much smaller than
that figure, using the same budget number keeps this module's eviction policy honest
against the research's own measurement rather than an arbitrary smaller one.

## The pathological-document cap (brief ruling 4, this plan's own threat register T-02-01)

02-RESEARCH.md Section 10 / the threat register: "anything above ~10M glyphs is
pathological -- abort with a named reason." `RunIndex` tracks the CUMULATIVE glyph count
walked across the document's whole lifetime (every page ever parsed, not just what is
currently cached -- an evicted page's glyphs already cost real CPU time to walk once,
and re-walking it on a cache miss must count again toward the same document-wide ceiling
or a script that repeatedly evicts and re-requests the same pages could walk unbounded
total work while this check only ever sees a small `_cache`). Crossing
`MAX_DOCUMENT_GLYPHS` raises `DocumentTooLargeError`, never a bare `Exception`, and the
message carries counts only -- never document content (T-02-04).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import pikepdf

from engine.classify_page import Bucket
from engine.classify_run import RunVerdict, _classify_one_page
from engine.encoding_table import FontVerdict
from engine.playa_boundary import Document, open_document
from engine.records import RunRecord
from engine.shared_xobjects import shared_form_xobjects

# 02-RESEARCH.md Section 10, memory profile table: columnar storage of a 400-page
# IRS-density document (~1.9M glyphs, extrapolated from the measured 595,373 glyphs over
# 126 pages) costs 178MB. Page density varies 26x across the corpus (178-4,725
# glyphs/page -- Section 10), so the budget is denominated in glyphs, never pages, or a
# dense document would starve the cache while a sparse one wastes it.
CACHE_GLYPH_BUDGET = 1_900_000

# 02-RESEARCH.md Section 10 / this plan's own threat register T-02-01: "anything above
# ~10M glyphs is pathological -- abort with a named reason." Cumulative across the whole
# RunIndex's lifetime (see module docstring), not just what is currently cached.
MAX_DOCUMENT_GLYPHS = 10_000_000


class DocumentTooLargeError(Exception):
    """T-02-01: raised once a `RunIndex`'s cumulative walked glyph count exceeds
    `MAX_DOCUMENT_GLYPHS`. Never document content in the message -- counts only
    (T-02-04)."""


@dataclass(frozen=True, slots=True)
class PageIndex:
    """One page's cached classification result -- the "negligible" tier (brief ruling 2)
    that is never itself evicted once a page has been parsed. `glyph_count` is the page's
    own total located-glyph count (every location, visible and invisible), the unit
    `RunIndex`'s LRU eviction is denominated in."""

    bucket: Bucket
    runs: list[tuple[RunRecord, RunVerdict]]
    glyph_count: int


class RunIndex:
    """D-06. Opens a document once; parses (and caches) one page's run map only on first
    access to that page; evicts cached pages LRU by cumulative `glyph_count` once
    `CACHE_GLYPH_BUDGET` is exceeded.

    A `pikepdf.Pdf` and a `playa.Document` handle onto the same bytes are both opened in
    `__init__` and held for the object's whole lifetime (rather than per page): the
    per-page pipeline (`_classify_one_page`) needs both simultaneously, and `_shared`/
    `_font_cache` are computed/populated once and reused across every page, exactly as
    `classify_document` reuses them across its own single-pass loop. Use as a context
    manager, or call `close()` directly, to release both handles.
    """

    def __init__(self, path: str | Path) -> None:
        self._pdf = pikepdf.open(path)
        self._doc: Document = open_document(path)
        self._shared = shared_form_xobjects(self._pdf)
        self._font_cache: dict[tuple[tuple[int, int], bytes], FontVerdict] = {}
        self._cache: OrderedDict[int, PageIndex] = OrderedDict()
        self._cached_glyphs = 0
        self._total_glyphs_walked = 0

    def __enter__(self) -> RunIndex:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._doc.close()
        self._pdf.close()

    @property
    def page_count(self) -> int:
        return len(self._pdf.pages)

    def _parse_page(self, page_index: int) -> PageIndex:
        """The single per-page parse step, factored out as its own patchable method
        (brief ruling 5) so a test can `monkeypatch.setattr` it and assert it runs
        exactly once across two `.page(n)` calls -- the non-vacuous proof that `.page()`
        actually caches rather than re-parsing."""
        page = self._doc.pages[page_index]
        bucket, runs, glyph_count = _classify_one_page(
            self._pdf, self._doc, page, page_index, self._shared, self._font_cache
        )
        self._total_glyphs_walked += glyph_count
        if self._total_glyphs_walked > MAX_DOCUMENT_GLYPHS:
            raise DocumentTooLargeError(
                f"cumulative walked glyph count {self._total_glyphs_walked} exceeds "
                f"MAX_DOCUMENT_GLYPHS={MAX_DOCUMENT_GLYPHS}"
            )
        return PageIndex(bucket=bucket, runs=runs, glyph_count=glyph_count)

    def page(self, page_index: int) -> PageIndex:
        """Page `page_index`'s `PageIndex`, from cache if this page was parsed before and
        is still resident, else parsed fresh via `_parse_page` and cached."""
        cached = self._cache.get(page_index)
        if cached is not None:
            self._cache.move_to_end(page_index)  # real LRU: mark most-recently-used
            return cached

        result = self._parse_page(page_index)
        self._cache[page_index] = result
        self._cached_glyphs += result.glyph_count
        self._evict_if_needed()
        return result

    def _evict_if_needed(self) -> None:
        """Evicts the least-recently-used cached page ENTIRELY (bucket + runs +
        glyph_count all drop together -- brief ruling 2) until the running total is back
        at or under budget. Always keeps at least one page cached: a single page whose
        own glyph count exceeds the budget must not thrash on every access to itself."""
        while self._cached_glyphs > CACHE_GLYPH_BUDGET and len(self._cache) > 1:
            _evicted_index, evicted = self._cache.popitem(last=False)
            self._cached_glyphs -= evicted.glyph_count


__all__ = [
    "CACHE_GLYPH_BUDGET",
    "MAX_DOCUMENT_GLYPHS",
    "DocumentTooLargeError",
    "PageIndex",
    "RunIndex",
]
