"""Renderer-independent, conservative layout over the one existing RunIndex.

Coordinates are glyph device coordinates. Horizontal lines are supported; rotated
text retains its source text with an explicit warning. Complete rectangular grids
are tables; partial/merged/unruled tables remain paragraphs. No OCR is performed.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from engine.index import PageIndex, RunIndex
from engine.records import RunRecord

HEADING_RATIO = 1.35
LARGE_HEADING_RATIO = 1.8
BASELINE_TOLERANCE_EM = .35
LINE_GAP_EM = 2.0
PARAGRAPH_LEADING_EM = 1.65
RULE_TOLERANCE = .5
MAX_BLOCK_PAGES = 2000
MAX_BLOCK_RUNS = 100_000
MAX_GRID_AXES = 64
MAX_GRID_COMPARISONS = 1_000_000
LIST_MARKER = re.compile(r'^(?:[-*•]|\d+[.)])\s+')


class ExportLimitError(ValueError):
    """A named layout/serialization work bound, not malformed PDF content."""


@dataclass(frozen=True, slots=True)
class Span:
    text: str
    bold: bool | None = None
    italic: bool | None = None
    source_runs: tuple[RunRecord, ...] = ()


@dataclass(frozen=True, slots=True)
class Block:
    kind: Literal['paragraph', 'heading', 'list', 'table']
    source_runs: tuple[RunRecord, ...]
    spans: tuple[Span, ...]
    heading_level: int | None = None
    rows: tuple[tuple[tuple[Span, ...], ...], ...] = ()


@dataclass(frozen=True, slots=True)
class PageBlocks:
    page_index: int
    blocks: tuple[Block, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DocumentBlocks:
    pages: tuple[PageBlocks, ...]


@dataclass(frozen=True, slots=True)
class _Line:
    runs: tuple[RunRecord, ...]
    x: float
    end: float
    y: float
    size: float


def _bounds(run: RunRecord) -> tuple[float, float, float, float]:
    points = [(g.x, g.y) for g in run.glyphs] + [(g.x+g.advance[0], g.y+g.advance[1]) for g in run.glyphs]
    if not points or not all(math.isfinite(c) for p in points for c in p):
        return (0, 0, 0, 0)
    return min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)


def _size(run: RunRecord) -> float:
    return run.effective_em if run.effective_em is not None and math.isfinite(run.effective_em) and run.effective_em > 0 else 12.0


def _spans(runs: tuple[RunRecord, ...]) -> tuple[Span, ...]:
    out: list[Span] = []
    previous: RunRecord | None = None
    for run in runs:
        if previous is not None and not previous.display_text.endswith((' ', '\n')) and not run.display_text.startswith((' ', '\n')):
            gap = _bounds(run)[0] - _bounds(previous)[2]
            if gap > .15 * min(_size(run), _size(previous)):
                out.append(Span(' '))
        out.append(Span(run.display_text, run.bold, run.italic, (run,)))
        previous = run
    return tuple(out)


def _lines(runs: list[RunRecord]) -> list[_Line]:
    # Sorted sweep only checks the current baseline, avoiding pairwise run work.
    ordered = sorted(runs, key=lambda r: (_bounds(r)[1], _bounds(r)[0], r.run_id))
    bands: list[list[RunRecord]] = []
    for run in ordered:
        if bands and abs(_bounds(run)[1] - _bounds(bands[-1][0])[1]) <= BASELINE_TOLERANCE_EM * min(_size(run), _size(bands[-1][0])):
            bands[-1].append(run)
        else:
            bands.append([run])
    lines: list[_Line] = []
    for band in bands:
        groups: list[list[RunRecord]] = []
        for run in sorted(band, key=lambda r: (_bounds(r)[0], r.run_id)):
            if groups and _bounds(run)[0] - _bounds(groups[-1][-1])[2] <= LINE_GAP_EM * min(_size(run), _size(groups[-1][-1])):
                groups[-1].append(run)
            else:
                groups.append([run])
        for group in groups:
            lines.append(_Line(tuple(group), min(_bounds(r)[0] for r in group), max(_bounds(r)[2] for r in group),
                               min(_bounds(r)[1] for r in group), max(_size(r) for r in group)))
    return lines


def _table(page: PageIndex, runs: list[RunRecord]) -> tuple[Block | None, set[str], str | None]:
    if not page.rulings:
        return None, set(), None
    horizontals = [(min(x,u), max(x,u), (y+v)/2) for x,y,u,v in page.rulings if abs(y-v) <= RULE_TOLERANCE]
    verticals = [(min(y,v), max(y,v), (x+u)/2) for x,y,u,v in page.rulings if abs(x-u) <= RULE_TOLERANCE]

    def axes(values: list[float]) -> list[float]:
        out: list[float] = []
        for value in sorted(values):
            if not out or value-out[-1] > RULE_TOLERANCE:
                out.append(value)
        return out

    xs, ys = axes([v[2] for v in verticals]), axes([h[2] for h in horizontals])
    if len(xs) < 2 or len(ys) < 2:
        return None, set(), 'unsupported-table-rulings'
    if max(len(xs),len(ys)) > MAX_GRID_AXES or len(xs)*len(ys)*max(1,len(runs)) > MAX_GRID_COMPARISONS:
        return None, set(), 'table-work-limit'

    def covered(segments: list[tuple[float,float,float]], axis: float, lo: float, hi: float) -> bool:
        end = lo
        for a,b,c in sorted(segments):
            if abs(c-axis) <= RULE_TOLERANCE and a <= end+RULE_TOLERANCE and b >= end:
                end = max(end,b)
        return end >= hi-RULE_TOLERANCE

    if not all(covered(horizontals,y,xs[0],xs[-1]) for y in ys) or not all(covered(verticals,x,ys[0],ys[-1]) for x in xs):
        return None, set(), 'ambiguous-table-grid'
    cells: list[list[list[RunRecord]]] = [[[] for _ in xs[1:]] for _ in ys[1:]]
    used: set[str] = set()
    for run in runs:
        x,y,end,bottom = _bounds(run)
        if not (xs[0] <= x <= xs[-1] and ys[0] <= y <= ys[-1]):
            continue
        matches = [(r,c) for r in range(len(ys)-1) for c in range(len(xs)-1)
                   if xs[c]+RULE_TOLERANCE < x and end < xs[c+1]-RULE_TOLERANCE
                   and ys[r]+RULE_TOLERANCE < y and bottom < ys[r+1]-RULE_TOLERANCE]
        if len(matches) != 1:
            return None, set(), 'ambiguous-table-content'
        r,c = matches[0]
        cells[r][c].append(run)
        used.add(run.run_id)
    if not used:
        return None, set(), 'empty-table-grid'
    rows = tuple(tuple(_line_spans(_lines(cell)) for cell in row) for row in cells)
    source = tuple(r for row in cells for cell in row for r in cell)
    return Block('table', source, (), rows=rows), used, None


def _line_spans(lines: list[_Line]) -> tuple[Span, ...]:
    result: list[Span] = []
    for line in sorted(lines, key=lambda line: (line.y,line.x)):
        if result:
            result.append(Span('\n'))
        result.extend(_spans(line.runs))
    return tuple(result)


def _ordered(lines: list[_Line], body: float, warnings: list[str]) -> list[_Line]:
    """Split vertical bands at headings/large gaps; disjoint x intervals form columns."""
    bands: list[list[_Line]] = []
    for line in sorted(lines,key=lambda l: (l.y,l.x)):
        heading = line.size >= body*HEADING_RATIO
        if not bands or heading or bands[-1][-1].size >= body*HEADING_RATIO or line.y-bands[-1][-1].y > 3*body:
            bands.append([line])
        else:
            bands[-1].append(line)
    result: list[_Line] = []
    for band in bands:
        columns: list[list[_Line]] = []
        right = -math.inf
        for line in sorted(band, key=lambda l: (l.x,l.end)):
            if not columns or line.x > right + LINE_GAP_EM*body:
                columns.append([line])
            else:
                columns[-1].append(line)
            right = max(right,line.end)
        if len(columns) > 1:
            warnings.append('columns-inferred-unruled-tables-unsupported')
        result.extend(line for column in columns for line in sorted(column,key=lambda l: (l.y,l.x)))
    return result


def _page(index: int, page: PageIndex) -> PageBlocks:
    runs = [run for run,_ in page.runs if run.display_text]
    warnings: list[str] = []
    if not runs:
        return PageBlocks(index, (), ('no-indexed-text',))
    if any(r.direction is not None and (abs(r.direction[1]) > .01 or r.direction[0] <= 0) for r in runs):
        warnings.append('unsupported-text-direction')
    sizes: dict[float,int] = defaultdict(int)
    for run in runs:
        sizes[round(_size(run)*2)/2] += max(1,len(run.display_text))
    body = max(sizes,key=lambda size: (sizes[size],-size))
    table, used, warning = _table(page,runs)
    if warning:
        warnings.append(warning)
    lines = _ordered(_lines([r for r in runs if r.run_id not in used]),body,warnings)
    blocks: list[Block] = []
    previous: _Line | None = None
    for line in lines:
        spans = _spans(line.runs)
        text = ''.join(s.text for s in spans)
        kind: Literal['paragraph','heading','list','table'] = 'heading' if line.size >= body*HEADING_RATIO else 'list' if LIST_MARKER.match(text) else 'paragraph'
        level = (1 if line.size >= body*LARGE_HEADING_RATIO else 2) if kind == 'heading' else None
        if kind == 'paragraph' and blocks and blocks[-1].kind == 'paragraph' and previous is not None and 0 < line.y-previous.y <= body*PARAGRAPH_LEADING_EM and abs(line.x-previous.x) < body*.75:
            old = blocks[-1]
            blocks[-1] = Block('paragraph', old.source_runs+line.runs, old.spans+(Span('\n'),)+spans)
        else:
            blocks.append(Block(kind,line.runs,spans,level))
        previous = line
    if table is not None:
        table_y = min(_bounds(r)[1] for r in table.source_runs)
        position = next((n for n,b in enumerate(blocks) if min(_bounds(r)[1] for r in b.source_runs) > table_y),len(blocks))
        blocks.insert(position,table)
    return PageBlocks(index,tuple(blocks),tuple(dict.fromkeys(warnings)))


def build_document(index: RunIndex) -> DocumentBlocks:
    if index.page_count > MAX_BLOCK_PAGES:
        raise ExportLimitError('export-page-limit')
    pages: list[PageBlocks] = []
    count = 0
    for number in range(index.page_count):
        page = index.page(number)
        count += len(page.runs)
        if count > MAX_BLOCK_RUNS:
            raise ExportLimitError('export-run-limit')
        pages.append(_page(number,page))
    return DocumentBlocks(tuple(pages))
