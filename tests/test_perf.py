"""02-09 Task 1: engine/index.py -- D-06's page-at-a-time caching and LRU-by-glyph-count
eviction, proven under a real performance and caching test rather than merely described.

`irs_1040_instructions.pdf` (126 pages) is the SAME document 02-RESEARCH.md Section 10
measured: ~15ms for `playa.open()` + page 1 lazily, vs. 21.0s/166MB to walk it eagerly,
whole-document, up front. Both numbers are exercised here, on the real document, not a
synthetic stand-in -- that is the point of a "permanent negative-case test", per this
task's brief.

No document content (page text) appears in any assertion message, per this project's
standing convention (T-02-04) -- only counts and timings.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

import engine.index as index_module
from engine.classify_run import classify_document
from engine.index import CACHE_GLYPH_BUDGET, DocumentTooLargeError, PageIndex, RunIndex

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"
IRS_1040_INSTRUCTIONS = CORPUS_DIR / "irs_1040_instructions.pdf"

# Generous margin over 02-RESEARCH.md's measured ~15ms open+first-page -- "well under
# 100ms" per the task's own D-06 acceptance criterion.
LATENCY_BUDGET_SECONDS = 0.1


def test_first_page_latency_under_100ms() -> None:
    """D-06's pinned latency test: `RunIndex(path).page(0)` -- construction (opens the
    pikepdf and playa handles, walks shared-XObject detection once) plus the first page's
    own lazy parse -- completes well under the 100ms budget."""
    start = time.perf_counter()
    idx = RunIndex(IRS_1040_INSTRUCTIONS)
    try:
        idx.page(0)
    finally:
        idx.close()
    elapsed = time.perf_counter() - start
    assert elapsed < LATENCY_BUDGET_SECONDS, (
        f"RunIndex(...).page(0) took {elapsed:.3f}s, expected well under "
        f"{LATENCY_BUDGET_SECONDS}s (D-06)"
    )


def test_page_zero_is_cached_not_reparsed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A second `.page(0)` call is a cache hit: `_parse_page` -- the one, single patchable
    per-page parse step (brief ruling 5) -- runs exactly once across two `.page(0)`
    calls."""
    idx = RunIndex(IRS_1040_INSTRUCTIONS)
    try:
        calls: list[int] = []
        original = idx._parse_page

        def _counting_parse(page_index: int) -> PageIndex:
            calls.append(page_index)
            return original(page_index)

        monkeypatch.setattr(idx, "_parse_page", _counting_parse)

        idx.page(0)
        idx.page(0)
        assert calls == [0], (
            f"expected exactly one _parse_page call across two .page(0) calls, got "
            f"{len(calls)} -- caching is broken"
        )
    finally:
        idx.close()


def test_page_zero_reparses_if_cache_is_bypassed(monkeypatch: pytest.MonkeyPatch) -> None:
    """THE MUTATION: proves the counter in `test_page_zero_is_cached_not_reparsed` is not
    vacuous. With the cache actually cleared between the two `.page(0)` calls (simulating
    caching being broken), the identical counting harness reads two calls, not one --
    confirming the counter would NOT read 1 if caching genuinely were not working."""
    idx = RunIndex(IRS_1040_INSTRUCTIONS)
    try:
        calls: list[int] = []
        original = idx._parse_page

        def _counting_parse(page_index: int) -> PageIndex:
            calls.append(page_index)
            return original(page_index)

        monkeypatch.setattr(idx, "_parse_page", _counting_parse)

        idx.page(0)
        # Simulate broken caching: forget everything the cache knows about page 0.
        idx._cache.clear()
        idx._cached_glyphs = 0
        idx.page(0)

        assert calls == [0, 0], (
            "expected _parse_page to run twice once the cache was bypassed -- if it "
            "didn't, test_page_zero_is_cached_not_reparsed's counter proves nothing about "
            "real caching behaviour"
        )
    finally:
        idx.close()


def test_eager_full_document_walk_blows_the_100ms_budget() -> None:
    """The permanent negative case (task acceptance criteria): replacing RunIndex's lazy
    per-page parse with `classify_document`'s eager whole-document walk on the SAME
    126-page document blows the 100ms budget by orders of magnitude -- 02-RESEARCH.md
    Section 10 measured 21.0s on this exact document. `classify_document` is the
    pipeline's own eager alternative (see its own docstring, updated by this task), not a
    strawman built for this test alone."""
    start = time.perf_counter()
    classify_document(IRS_1040_INSTRUCTIONS)
    elapsed = time.perf_counter() - start
    assert elapsed > 1.0, (
        f"eager classify_document() took only {elapsed:.3f}s -- expected it to blow the "
        f"100ms budget by a wide margin (measured 21.0s in 02-RESEARCH.md Section 10); if "
        f"this no longer holds, the negative case this test exists for is no longer "
        f"demonstrating D-06's motivation"
    )


def test_page_index_shape_and_glyph_count() -> None:
    """Sanity check that the fully-composed pipeline actually produced something:
    TEXT-01's "a run record per text run" -- page 0 of a normal, editable document
    reports the editable bucket, at least one run, and a positive glyph count."""
    idx = RunIndex(IRS_1040_INSTRUCTIONS)
    try:
        page0 = idx.page(0)
    finally:
        idx.close()
    assert page0.bucket == "editable"
    assert page0.runs, "expected at least one run on page 0 of an editable document"
    assert page0.glyph_count > 0


def test_document_too_large_raises_named_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """T-02-01 (threat register): once cumulative walked glyphs exceed
    MAX_DOCUMENT_GLYPHS, RunIndex aborts with a NAMED exception, never a bare
    `Exception`. Forces the ceiling far below one page's own glyph count so the very
    first `.page()` call trips it."""
    monkeypatch.setattr(index_module, "MAX_DOCUMENT_GLYPHS", 1)
    idx = RunIndex(IRS_1040_INSTRUCTIONS)
    try:
        with pytest.raises(DocumentTooLargeError):
            idx.page(0)
    finally:
        idx.close()


def test_eviction_is_by_glyph_count_not_page_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-06's own truth: eviction targets cumulative glyph_count against
    CACHE_GLYPH_BUDGET, never page count. Forcing the budget to 1 (below any real page's
    own glyph count) makes every subsequent `.page()` call evict everything else already
    cached; re-accessing an evicted page must reparse it (a fresh `_parse_page` call),
    proving eviction actually drops cache entries rather than merely tracking a number
    that is never acted on."""
    idx = RunIndex(IRS_1040_INSTRUCTIONS)
    try:
        first = idx.page(0)
        assert first.glyph_count > 0, "expected page 0 to have located glyphs"

        monkeypatch.setattr(index_module, "CACHE_GLYPH_BUDGET", 1)

        idx.page(1)  # under a 1-glyph budget, this must evict page 0
        assert 0 not in idx._cache, "page 0 should have been evicted under a 1-glyph budget"

        calls: list[int] = []
        original = idx._parse_page

        def _counting_parse(page_index: int) -> PageIndex:
            calls.append(page_index)
            return original(page_index)

        monkeypatch.setattr(idx, "_parse_page", _counting_parse)
        idx.page(0)
        assert calls == [0], "an evicted page must reparse exactly once on re-access"
    finally:
        idx.close()


def test_cache_glyph_budget_matches_researched_figure() -> None:
    """Guards the constant itself against silent drift -- 02-RESEARCH.md Section 10's
    measured 400-page/~1.9M-glyph/178MB figure, named next to CACHE_GLYPH_BUDGET in
    engine/index.py's own module docstring."""
    assert CACHE_GLYPH_BUDGET == 1_900_000
