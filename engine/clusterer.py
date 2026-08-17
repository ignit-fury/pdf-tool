"""D-01/D-02/D-03/D-05: turn a page's flat glyph stream into the visual lines a user would
click to edit.

`cluster_page` is the single entry point (02-07). Its input is exactly what
`engine.walker.located_cluster_records`/`cluster_document_records` yield --
`(StreamPath, GlyphRecord, ClusterAttrs)` triples -- covering a page's own /Contents AND
everything reachable outside it (Form XObjects, annotations, patterns, CharProcs). Nothing
here imports playa: GlyphRecord, ClusterAttrs, StreamPath and GlyphVerdict are all plain,
already-decoded dataclasses by the time they reach this module (engine/playa_boundary.py is
the only file that may import playa).

## The pipeline, four stages

1. **Group by StreamPath** (required, not optional). A run must never span two different
   StreamPaths -- they are different physical byte ranges, and `encode_run_id` only has
   room for one `:c{part}` anchor. `StreamPath` is frozen/hashable, so it is used directly
   as a dict key; two glyphs both inside Form XObject /I1 share one StreamPath's field
   values regardless of which glyph produced it.
2. **Band by baseline, per rotation angle** (02-RESEARCH.md Section 3, "Rotated text").
   Glyphs are bucketed by their quantized text-direction angle (~1 degree) so 0/45/90-degree
   text bands independently, then each bucket is banded into visual lines by ONE sort (on
   the position projected onto the direction PERPENDICULAR to reading direction) followed by
   a single linear scan chaining adjacent glyphs within `BAND_TOLERANCE_EM * effective_em`
   of each other -- this is the "single sort-then-linear-scan pass, not a nested per-pair
   comparison" the task calls for: O(n log n) per StreamPath, never O(n^2).
3. **Within a band, sort by projected reading-direction position BEFORE computing gaps**
   (Pitfall 3 -- the two-column requirement). Producers commonly emit two columns
   interleaved in stream order; walking gaps in stream order sees huge alternating
   positive/negative gaps and shatters the page into garbage runs. Sorting first is what
   makes the wide inter-column gutter show up as exactly one gap, in the right place.
4. **Split each band into logical runs by the D-01 break-cause table**, then split each
   logical run further into D-02 sub-runs wherever a glyph fails `glyph_verdict_fn` (D-05).
   Every fragment of one logical run -- editable sub-runs AND the isolated bad-glyph
   fragment -- shares that logical run's own anchor (first glyph's stream_id/byte_offset,
   plus the StreamPath) and is disambiguated only by `subrange`, a half-open `[start, end)`
   index range into the logical run's OWN (unfiltered) glyph list. A logical run that is
   not split by a bad glyph gets `subrange=None`.

## What is deliberately NOT a break condition

D-01's extension names fill colour, never stroke colour or text render mode: Tr 0 (fill),
1 (stroke) and 2 (fill+stroke) are all visible and must cluster together. This module
breaks on `GlyphRecord.visible` (the walker's already-derived boolean: false only for the
invisible Tr 3 / Tr 7 render modes) -- never on the raw `render_mode` value. Reading raw
`render_mode` here would split a run on every stroke-only heading, which is exactly the
mistake D-01 rejected.
"""

from __future__ import annotations

import math
from typing import Callable, Iterable

from engine.encoding_table import GlyphVerdict
from engine.records import ClusterAttrs, GlyphRecord, RunRecord
from engine.run_id import encode_run_id
from engine.space_threshold import BREAK_EM, K_EM
from engine.walker import StreamPath

# Research Section 3, Step 1: "|baseline(g) - baseline(g_prev)| < 0.2 x effective_font_size".
BAND_TOLERANCE_EM = 0.2

# D-01's size-change break condition: "differs by > 1%".
SIZE_CHANGE_TOLERANCE = 0.01

# Research Section 3 / the pdf.js negativeSpaceMax rule: "backwards by more than 0.2 x fs".
REVERSAL_TOLERANCE_EM = 0.2

# Research Section 3, "Superscript vs. line break": "a line break has |Delta y| >= 0.5 x fs".
# A rise change alone is NOT a break -- only a horizontal reset (no forward advance) or a
# rise delta at or past this fraction of the em is. Below it, with forward advance intact,
# is exactly a superscript: state changed (Ts), position did not reset.
SUPERSCRIPT_RISE_TOLERANCE_EM = 0.5

_GlyphItem = tuple[GlyphRecord, ClusterAttrs]


def _unit(direction: tuple[float, float]) -> tuple[float, float]:
    """The text rendering matrix's reading-direction row, normalised to a unit vector.

    A degenerate (zero-length) direction -- Tz == 0, or a degenerate Tm -- has no angle to
    recover; falling back to horizontal (1, 0) is a documented simplification for that
    corner, not a claim that the text really is horizontal.
    """
    dx, dy = direction
    norm = math.hypot(dx, dy)
    if norm == 0.0:
        return (1.0, 0.0)
    return (dx / norm, dy / norm)


def _project_along(vec: tuple[float, float], unit: tuple[float, float]) -> float:
    """Component of `vec` along the reading direction -- the axis Pitfall 3's sort and the
    gap/space/break thresholds all operate on."""
    return vec[0] * unit[0] + vec[1] * unit[1]


def _project_perp(vec: tuple[float, float], unit: tuple[float, float]) -> float:
    """Component of `vec` perpendicular to the reading direction (rotate `unit` +90 degrees)
    -- the "baseline" axis Step 1 bands on. For unrotated horizontal text `unit == (1, 0)`
    and this reduces to plain `y`, matching the un-rotated case exactly."""
    ux, uy = unit
    return vec[0] * -uy + vec[1] * ux


def _angle_bucket(direction: tuple[float, float]) -> int:
    """Quantises a text direction to the nearest degree, so 0/45/90-degree text (and any
    other rotation) bands independently (Section 3, "Rotated text")."""
    dx, dy = direction
    if dx == 0.0 and dy == 0.0:
        return 0
    return round(math.degrees(math.atan2(dy, dx)))


def _band_by_baseline(items: list[_GlyphItem]) -> list[list[_GlyphItem]]:
    """Step 1: ONE sort by perpendicular (baseline) position, then ONE linear scan chaining
    adjacent glyphs within tolerance -- O(n log n) total, never a nested per-pair comparison
    (the complexity the task's <action> asks to be named explicitly)."""
    decorated = sorted(
        ((_project_perp((r.x, r.y), _unit(a.direction)), r, a) for r, a in items),
        key=lambda t: t[0],
    )
    bands: list[list[_GlyphItem]] = []
    current: list[_GlyphItem] = []
    prev_perp: float | None = None
    for perp, record, attrs in decorated:
        if prev_perp is not None and abs(perp - prev_perp) >= BAND_TOLERANCE_EM * attrs.effective_em:
            bands.append(current)
            current = []
        current.append((record, attrs))
        prev_perp = perp
    if current:
        bands.append(current)
    return bands


def _gaps_em(ordered: list[_GlyphItem]) -> list[float]:
    """`gaps[i]` is the em-normalised gap between glyph `i-1`'s end and glyph `i`'s origin,
    both projected onto glyph `i`'s own reading direction. `gaps[0]` is unused (no
    predecessor). Computed once per band and reused for both the D-01 break decision and
    D-03's synthetic-space insertion -- one number, two consumers, never two computations
    that could silently disagree."""
    gaps = [0.0] * len(ordered)
    for i in range(1, len(ordered)):
        record, attrs = ordered[i]
        prev_record, prev_attrs = ordered[i - 1]
        unit = _unit(attrs.direction)
        prev_unit = _unit(prev_attrs.direction)
        along = _project_along((record.x, record.y), unit)
        prev_along = _project_along((prev_record.x, prev_record.y), prev_unit)
        prev_end = prev_along + _project_along(prev_record.advance, prev_unit)
        em = attrs.effective_em
        gaps[i] = (along - prev_end) / em if em else 0.0
    return gaps


def _is_line_break_not_superscript(attrs: ClusterAttrs, prev_attrs: ClusterAttrs) -> bool:
    """Research Section 3, "Superscript vs. line break": a rise (`Ts`) change alone is not
    a break. `gstate.rise` is checked FIRST per Assumption A2's Ts-first heuristic -- no
    rise change at all means no superscript question to ask.

    CORRECTED 2026-08-14 after independent review of the original fix (f1f968c) found the
    "horizontal reset" clause both unreachable and wrong, and untested -- deleted rather
    than re-tuned:
    - Unreachable as intended: `cluster_page` SORTS each band by projected position before
      this function ever runs (Pitfall 3). A genuine carriage return (Section 3's `Delta x
      < 0`) cannot survive that sort -- origins are monotonically non-decreasing by the
      time `gap_em` is computed, so the clause never fires for what it was named for.
      A real carriage return still breaks the run, just via the ordinary `gap_em >
      BREAK_EM` clause below, not this one.
      - What the clause DID fire on instead: `gap_em < 0` after the sort means glyph
      OVERLAP (kerning pulls the current glyph's origin behind the previous glyph's own
      advance), which is common on a tucked superscript with negative kerning -- so the
      clause reintroduced a false break on exactly the case it was written to protect.
      - Untested: mutating it to `False` left every existing test green; nothing pinned
      its boundary.
    Left after the correction: `Ts` changing AT OR PAST the 0.5em threshold is a genuine
    line break; a smaller `Ts` change is a superscript and does not break, full stop --
    matching the plan's own Task 2 wording's remaining, measurable half: "a rise of over
    0.5 times font size" breaks a run.

    KNOWN LIMITATION, root-caused to two research constants disagreeing rather than to this
    function: `GlyphRecord.y` already carries `Ts`'s contribution (playa folds rise into
    the text rendering matrix's translation), so a typical superscript's rise (commonly
    ~0.33em) EXCEEDS `BAND_TOLERANCE_EM` (0.2) and is already split into a different band
    at Step 1, before this function is ever reached. This function only sees rise changes
    small enough to stay in-band -- under ~0.2em -- which is a narrower guarantee than
    "superscripts stay in one run" for the typical case. Recorded for 02-08 rather than
    fixed here: reconciling the two thresholds is a research-level decision, not a
    clusterer bug.
    """
    if attrs.rise == prev_attrs.rise:
        return False
    em = attrs.effective_em
    return em > 0 and abs(attrs.rise - prev_attrs.rise) >= SUPERSCRIPT_RISE_TOLERANCE_EM * em


def _split_logical_runs(ordered: list[_GlyphItem], gaps: list[float]) -> list[tuple[int, int]]:
    """Step 2 (D-01): the break-cause table, walked once over the band's own reading-order
    sequence (already sorted by `cluster_page` -- Pitfall 3). Returns half-open `[start,
    end)` index ranges into `ordered` -- never the glyph items themselves, so a caller can
    slice both `ordered` and its parallel `gaps` list by plain integer index. (An earlier
    version returned lists of items and re-located each logical run's start via
    `list.index()`; `GlyphRecord`/`ClusterAttrs` are value-equal frozen dataclasses, so two
    structurally-identical glyphs -- rare but real -- would have collided on the wrong
    index. Integer ranges have no such hazard.)

    Deliberately does NOT consult `glyph_verdict_fn` -- D-05's bad-glyph split happens
    afterwards, per logical run, in `_fragment_by_editability`. A bad glyph still
    participates in font/size/colour continuity like any other glyph; it is isolated as a
    second, independent pass over each logical run's own glyph list.
    """
    if not ordered:
        return []
    ranges: list[tuple[int, int]] = []
    start = 0
    for i in range(1, len(ordered)):
        record, attrs = ordered[i]
        prev_record, prev_attrs = ordered[i - 1]
        gap_em = gaps[i]
        break_here = (
            record.font_id != prev_record.font_id
            or abs(attrs.effective_em - prev_attrs.effective_em)
            > SIZE_CHANGE_TOLERANCE * prev_attrs.effective_em
            or _is_line_break_not_superscript(attrs, prev_attrs)
            # D-01: the derived `visible` boolean, NEVER raw render_mode -- Tr 0/1/2 are
            # all visible and must cluster together; only crossing Tr 3/Tr 7 breaks.
            or record.visible != prev_record.visible
            or attrs.fill_color != prev_attrs.fill_color
            or gap_em > BREAK_EM
            or gap_em < -REVERSAL_TOLERANCE_EM
        )
        if break_here:
            ranges.append((start, i))
            start = i
    ranges.append((start, len(ordered)))
    return ranges


def _fragment_by_editability(verdicts: list[GlyphVerdict]) -> list[tuple[int, int]]:
    """D-05: half-open `[start, end)` fragments over one logical run's glyph indices. A
    non-editable glyph is ALWAYS its own single-glyph fragment (D-02: "locks only itself" --
    two adjacent bad glyphs do not merge into one two-glyph locked fragment); a maximal
    stretch of editable glyphs is one fragment."""
    fragments: list[tuple[int, int]] = []
    i = 0
    n = len(verdicts)
    while i < n:
        if not verdicts[i].editable:
            fragments.append((i, i + 1))
            i += 1
            continue
        j = i
        while j < n and verdicts[j].editable:
            j += 1
        fragments.append((i, j))
        i = j
    return fragments


def _display_text(fragment: list[_GlyphItem], gaps: list[float]) -> str:
    """D-03: the fragment's own glyphs joined, with a synthetic space wherever the gap
    BEFORE a glyph (never the leading position) falls strictly between K_EM and BREAK_EM.
    `gaps` is aligned to `fragment` (same length, same indices) -- callers pass the parent
    logical run's own gap slice."""
    parts: list[str] = []
    for i, (record, _attrs) in enumerate(fragment):
        if i > 0 and K_EM < gaps[i] <= BREAK_EM:
            parts.append(" ")
        parts.append(record.unicode or "")
    return "".join(parts)


def _emit_logical_run(
    page_index: int,
    path: StreamPath,
    logical: list[_GlyphItem],
    gaps: list[float],
    source_hash: str,
    glyph_verdict_fn: Callable[[GlyphRecord], GlyphVerdict],
) -> list[RunRecord]:
    """One logical (D-01) run -> one or more RunRecords, split at bad glyphs (D-05) and
    addressed per D-02: every fragment shares the SAME anchor (the logical run's own first
    glyph), disambiguated only by `subrange` -- and only when there IS more than one
    fragment; a logical run untouched by D-05 gets `subrange=None`."""
    first_record, _first_attrs = logical[0]

    verdicts = [glyph_verdict_fn(record) for record, _attrs in logical]
    fragments = _fragment_by_editability(verdicts)
    single_fragment = len(fragments) == 1

    out: list[RunRecord] = []
    for start, end in fragments:
        frag = logical[start:end]
        frag_gaps = gaps[start:end]
        subrange = None if single_fragment else (start, end)
        run_id = encode_run_id(
            source_hash,
            page_index,
            first_record.stream_id,
            xobj_path=path.xobj_path,
            annot=path.annot,
            pattern=path.pattern,
            charproc=path.charproc,
            byte_offset=first_record.operator_byte_offset,
            subrange=subrange,
        )
        out.append(
            RunRecord(
                run_id=run_id,
                glyphs=[record for record, _attrs in frag],
                display_text=_display_text(frag, frag_gaps),
                page=page_index,
            )
        )
    return out


def cluster_page(
    page_index: int,
    located: Iterable[tuple[StreamPath, GlyphRecord, ClusterAttrs]],
    source_hash: str,
    glyph_verdict_fn: Callable[[GlyphRecord], GlyphVerdict],
) -> list[RunRecord]:
    """Bands, sorts, breaks and addresses one page's glyphs into `RunRecord`s.

    `located` is exactly `located_cluster_records(page, page_index, doc)`'s own output --
    passed straight through, never re-materialised into a different shape first.
    `glyph_verdict_fn` is a callable rather than a precomputed mapping because this module
    does not know which font a glyph resolved to; the caller closes over the FontVerdict
    table it built in 02-06 (see the controller-resolved interface in this task's brief).
    """
    groups: dict[StreamPath, list[_GlyphItem]] = {}
    for path, record, attrs in located:
        groups.setdefault(path, []).append((record, attrs))

    runs: list[RunRecord] = []
    for path, items in groups.items():
        # Rotated text bands independently by quantized angle (Section 3), so 0/45/90-degree
        # text on the same page never gets banded together.
        buckets: dict[int, list[_GlyphItem]] = {}
        for record, attrs in items:
            buckets.setdefault(_angle_bucket(attrs.direction), []).append((record, attrs))

        for bucket in buckets.values():
            for band in _band_by_baseline(bucket):
                # Pitfall 3: sort by reading-direction position BEFORE computing gaps.
                ordered = sorted(
                    band, key=lambda item: _project_along((item[0].x, item[0].y), _unit(item[1].direction))
                )
                gaps = _gaps_em(ordered)
                for start, end in _split_logical_runs(ordered, gaps):
                    logical = ordered[start:end]
                    logical_gaps = gaps[start:end]
                    runs.extend(
                        _emit_logical_run(
                            page_index, path, logical, logical_gaps, source_hash, glyph_verdict_fn
                        )
                    )
    return runs


__all__ = ["BAND_TOLERANCE_EM", "REVERSAL_TOLERANCE_EM", "SIZE_CHANGE_TOLERANCE", "cluster_page"]
