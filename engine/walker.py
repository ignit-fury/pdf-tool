"""Page-level glyph record assembly over the coalesced playa boundary (TEXT-01, TEXT-02).

`engine.playa_boundary.walk_page` yields one `(part_offset, part_index, operands,
text_obj)` per text-showing operator, with the two-pass alignment already asserted.
This module turns each of those into one `GlyphRecord` per glyph, filling the four
provenance fields playa does not expose.

NOTE ON NAMING: the boundary's `walk_page` and this module's `glyph_records` are
different things and deliberately named differently. `walk_page` is the operator-level
zip and returns tuples; `glyph_records` is the glyph-level product and returns
`GlyphRecord`s. An earlier revision of the plan had both called `walk_page`.

## Two entry points, deliberately (TEXT-06)

- `glyph_records(page, doc) -> list[GlyphRecord]` -- the page's OWN coalesced /Contents,
  unchanged. Every record it returns is addressed by `(part, byte offset)` alone, which is
  exactly what a page-local consumer (02-07's clusterer, 02-08's classifier) wants.
- `located_glyph_records(page, page_index, doc)` / `walk_document(doc)` -- the same records
  plus everything reachable outside /Contents, each paired with the `StreamPath` that says
  WHERE it came from. A record from inside a Form XObject is meaningless without that
  path: its byte offset is an offset into the XObject's stream, and Phase 3 rewriting it
  as if it were a page offset is the exact corruption 02-RESEARCH.md Pitfall 4 names.

The split exists because `GlyphRecord` has 13 fields fixed by 02-02 and none of them can
hold a path, so the path travels beside the record rather than inside it.

## Owning the recursion, and bounding it

`Page.flatten()` recurses for you and would make this file shorter -- and every glyph
below the top level would carry an address pointing into the page's content stream instead
of its own (Pitfall 4: "the inner LazyInterpreter -- and therefore _curpos and streamid --
is not reachable"). So the recursion is ours: `playa_boundary.walk_stream` yields the
`Do`-invoked Form XObjects and constructs a fresh interpreter for whichever ones we hand
back to it.

This runs on untrusted uploads, so descent is bounded twice over (T-02-02, T-02-03):

- a **visited set built per branch** -- `parents | {stream_key}`, never a global set. The
  same Form XObject legitimately appears on many pages and often several times within one
  page (that is what `shared_xobjects` counts); a global set would silently drop all but
  the first occurrence, which is real text vanishing rather than a cycle being cut.
- an **explicit depth cap**, `MAX_RECURSION_DEPTH`, for the chain that is deep but not
  cyclic -- a 500-deep XObject chain is a Python recursion blow-up and no visited set
  stops it.

Hitting either aborts that ONE branch, logs objids/depths/counts only (never glyph text --
T-02-04), and returns normally. Nothing propagates to the caller: a malicious XObject
graph must not be able to fail a document that is otherwise fine.

## Declared streams are walked once per page -- the bound the plan did not anticipate

Tiling patterns and Type3 CharProcs are not reached by an operator; they are *declared* in
a /Resources dictionary. A CharProc that has no /Resources of its own inherits the level's
-- routinely the page's -- and re-declares every sibling CharProc. The per-branch visited
set stops a CharProc re-entering ITSELF and stops nothing else, so 512 siblings enumerate
512 x 511 x 510 ... paths, and the depth cap only decides how many years that takes.

`[MEASURED: corpus/public/govdocs1_004_004050.pdf page 0 -- 512 CharProcs, no cycle, no
adversary; the walk did not finish in 5 minutes with only the per-branch guard.]`

So resource-DECLARED streams carry a third bound, `declared_seen`, which is per PAGE WALK
and deliberately not per branch. That is the right shape and not merely the cheap one: the
run-ID grammar addresses a CharProc as `y{name}` and a pattern as `t{objid}`, neither of
which records which level declared it, so walking one twice on a page yields two IDs for
one span of bytes -- a double-edit hazard for Phase 3, not just wasted work. Form XObjects
keep the per-branch set instead, because they genuinely recur: the same header XObject
drawn at two positions is two addressable placements under two distinct `x{objid}` paths.

## Where the two "local, not buffer" provenance fields come from

`item_index_within_tj` and `byte_offset_within_string` are LOCAL coordinates -- an index
into a TJ array, and an offset from a string's own first byte. They are deliberately not
buffer addresses: an operand can be parsed from a different /Contents part than the
keyword that consumes it, so no single (part, offset) pair addresses both, and a run ID
addresses the keyword only (see playa_boundary's module docstring, "A run ID addresses
the operator keyword, not its operands").

So this module recomputes them by walking each operator's operand VALUES in lockstep
with playa's glyph stream, using `playa_boundary.glyph_byte_offsets` (playa's own
decoder) for the byte spans. `_assert_glyph_alignment` then checks the two streams had
the same length -- the same always-on tripwire discipline the boundary uses one level up.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass
from typing import Iterator

from engine.playa_boundary import (
    ContentStream,
    Document,
    GlyphObject,
    GraphicState,
    Matrix,
    Page,
    Resources,
    TextOp,
    XObjectObject,
    annotation_appearances,
    glyph_byte_offsets,
    stream_key,
    tiling_patterns,
    type3_charprocs,
    walk_page,
    walk_stream,
)
from engine.records import GlyphRecord
from engine.types import CharCode, Unicode

log = logging.getLogger(__name__)

# Text render modes that paint nothing: 3 = neither fill nor stroke (the classic
# scanned-page OCR layer), 7 = add to clipping path only. Every other mode marks ink.
INVISIBLE_RENDER_MODES = frozenset({3, 7})

# Bounds a deep-but-acyclic descent chain, which no visited set can stop (T-02-03). The
# corpus has never shown a Form XObject nested past depth 2; 64 matches
# shared_xobjects._MAX_XOBJECT_DEPTH so the detector and the walker agree on what "too
# deep" means, and sits far under Python's recursion limit even with a generator frame or
# three per level.
MAX_RECURSION_DEPTH = 64


@dataclass(frozen=True, slots=True)
class StreamPath:
    """WHERE a glyph record's byte offset is an offset INTO -- the run-ID path prefix.

    Field names and types are `run_id.encode_run_id`'s parameters exactly, so assembling
    an ID is a splat and not a translation step: `encode_run_id(source_hash, path.page,
    record.stream_id, **rest_of_path, byte_offset=record.operator_byte_offset)`.

    `page` is 0-based, matching `doc.pages` and `GlyphRecord.stream_id`'s part index. An
    empty path (all defaults) means the page's own /Contents.
    """

    page: int
    xobj_path: tuple[int, ...] = ()
    annot: tuple[int, str] | None = None
    pattern: int | None = None
    charproc: str | None = None


def _string_items(operands: list[object]) -> list[tuple[int | None, bytes]]:
    """Split one text-showing operator's operands into its (item_index, string) pairs.

    TJ carries a single array operand; each bytes element is a separate string and its
    array index is `item_index_within_tj`. Tj / ' / " each carry exactly one string, as
    the LAST operand (' and " prepend aw/ac numbers), and have no array index at all --
    hence None, which is why GlyphRecord types that field as `int | None`.

    The keyword itself is not yielded by walk_page, so TJ is discriminated by its operand
    shape: only TJ takes a list, and `_has_visible_text` has already rejected any operator
    whose strings are all empty. Numbers inside a TJ array are kerning adjustments and
    produce no glyphs, so they are skipped rather than indexed.
    """
    if operands and isinstance(operands[0], list):
        return [
            (i, el) for i, el in enumerate(operands[0]) if isinstance(el, bytes) and el
        ]
    tail = operands[-1] if operands else None
    return [(None, tail)] if isinstance(tail, bytes) and tail else []


def _assert_glyph_alignment(n_glyphs: int, n_positions: int, part_index: int) -> None:
    """Third end of the project's alignment tripwire, one level below the boundary's.

    The boundary proves Pass A and Pass B agree on the OPERATOR count. This proves the
    operand walk and playa's glyph stream agree on the GLYPH count within an operator --
    a distinct failure mode: a font whose decoder consumes bytes differently than its
    CMap reports would slip past the operator-level check while silently misassigning
    every byte_offset_within_string.

    Prints counts and a part index only -- never glyph text or buffer contents (T-02-04).
    """
    assert n_glyphs == n_positions, (
        f"glyph/operand desync in part {part_index}: playa yielded {n_glyphs} glyph(s) "
        f"but the operand walk produced {n_positions} position(s). A font's decoder and "
        f"its CMap disagree on byte consumption -- do not trust byte_offset_within_string."
    )


class _FontIds:
    """Interns font objects to small ints for `GlyphRecord.font_id`.

    What consumers need is "did the font change between these two glyphs" (D-01 breaks
    runs on font change), and an objid is both unstable across qpdf's repair-on-open and
    absent from playa's Font. The `_seen` list holds a reference to each font so its id()
    cannot be recycled by the garbage collector into a false match.

    One instance per page walk, so ids are comparable across every stream on that page --
    a running header in a Form XObject and the body text on the page that invokes it get
    the same id when they really are the same font object.
    """

    def __init__(self) -> None:
        self._ids: dict[int, int] = {}
        self._seen: list[object] = []

    def intern(self, font: object) -> int:
        key = id(font)
        if key not in self._ids:
            self._ids[key] = len(self._ids)
            self._seen.append(font)
        return self._ids[key]


def _op_records(op: TextOp, fonts: _FontIds) -> Iterator[GlyphRecord]:
    """One fully-populated GlyphRecord per glyph of one text-showing operator."""
    part_offset, part_index, operands, text_obj = op
    # A TextObject iterates GlyphObjects at runtime; playa types __iter__ generically
    # as ContentObject, so narrow explicitly rather than reaching through Any.
    glyphs = [g for g in text_obj if isinstance(g, GlyphObject)]
    if not glyphs:
        return

    # The font cannot change inside one text-showing operator -- Tf is its own
    # operator -- so one lookup per operator, off the first glyph, is exact.
    font = glyphs[0].gstate.font
    if font is None:
        # playa produced glyphs with no font resource. Nothing to decode byte spans
        # against, and a guessed offset is worse than a loud skip; 02-08's classifier
        # is where "this page is not editable text" gets its refusal UX.
        return
    positions: list[tuple[int | None, int]] = []
    for item_index, data in _string_items(operands):
        for off in glyph_byte_offsets(font, data):
            positions.append((item_index, off))

    _assert_glyph_alignment(len(glyphs), len(positions), part_index)

    for glyph, (item_index, byte_off) in zip(glyphs, positions):
        gs = glyph.gstate
        matrix = glyph.matrix
        yield GlyphRecord(
            code=CharCode(glyph.cid),
            # playa exposes no glyph index; the code->glyph forward map is
            # 02-06's encoding table. None here is the documented legitimate
            # absence, not a sentinel for failure.
            glyph=None,
            unicode=Unicode(glyph.text) if glyph.text is not None else None,
            x=matrix[4],
            y=matrix[5],
            advance=glyph.displacement,
            font_id=fonts.intern(gs.font),
            render_mode=gs.render_mode,
            visible=gs.render_mode not in INVISIBLE_RENDER_MODES,
            stream_id=part_index,
            operator_byte_offset=part_offset,
            item_index_within_tj=item_index,
            byte_offset_within_string=byte_off,
        )


def glyph_records(page: Page, doc: Document) -> list[GlyphRecord]:
    """One fully-populated GlyphRecord per glyph on a page's own coalesced /Contents.

    Text outside /Contents -- Form XObjects, annotation appearances, tiling patterns,
    Type3 CharProcs -- is deliberately NOT here: those records need a `StreamPath` to be
    addressable at all. See `located_glyph_records`.
    """
    fonts = _FontIds()
    return [rec for op in walk_page(page, doc) for rec in _op_records(op, fonts)]


def _walk_level(
    page: Page,
    doc: Document,
    parts: list[ContentStream],
    path: StreamPath,
    *,
    key: tuple[int, int] | None,
    resources: Resources,
    ctm: Matrix,
    gstate: GraphicState | None = None,
    type3: bool = False,
    parents: frozenset[tuple[int, int]],
    declared_seen: set[tuple[int, int]],
    depth: int,
    fonts: _FontIds,
) -> Iterator[tuple[StreamPath, GlyphRecord]]:
    """One content-stream level: its own text, then everything it reaches.

    `key` is the level's (objid, genno) cycle-guard identity, or None for a page's own
    /Contents (which is entered exactly once and has no objid of its own). Both bounds are
    enforced here, in one place, so no caller can descend without them.
    """
    if key is not None:
        if key in parents:
            # T-02-02. objid, depth and the branch kind only -- never glyph text (T-02-04).
            log.warning(
                "cycle guard: stream %d re-entered on its own branch at depth %d "
                "(page %d); branch aborted",
                key[0],
                depth,
                path.page,
            )
            return
        if depth > MAX_RECURSION_DEPTH:
            # T-02-03.
            log.warning(
                "depth cap: stream %d at depth %d exceeds MAX_RECURSION_DEPTH=%d "
                "(page %d); branch aborted",
                key[0],
                depth,
                MAX_RECURSION_DEPTH,
                path.page,
            )
            return
        parents = parents | {key}

    for item in walk_stream(
        page, doc, parts, resources=resources, ctm=ctm, gstate=gstate, type3=type3
    ):
        if isinstance(item, XObjectObject):
            # Recurse HERE, while the parent interpreter is suspended at this exact Do:
            # the graphics state playa handed us is the live one, and it keeps mutating
            # as the parent's operators run on. Collecting invocations and descending
            # afterwards would apply the wrong (later) gstate to every one of them.
            child_key = stream_key(item.stream)
            yield from _walk_level(
                page,
                doc,
                [item.stream],
                dataclasses.replace(path, xobj_path=path.xobj_path + (child_key[0],)),
                key=child_key,
                # None means "no /Resources of my own" -- a pre-1.2 XObject inheriting
                # the page's, which is also what playa's own interp falls back to.
                resources=page.resources if item.resources is None else item.resources,
                ctm=item.ctm,
                gstate=item.gstate,
                parents=parents,
                declared_seen=declared_seen,
                depth=depth + 1,
                fonts=fonts,
            )
        else:
            for record in _op_records(item, fonts):
                yield path, record

    # Streams reached through this level's /Resources rather than through an operator.
    # `declared_seen` is per PAGE WALK, not per branch -- see the module docstring's
    # "declared streams are walked once per page".
    for pattern, sub_resources, pattern_ctm in tiling_patterns(resources, ctm):
        pattern_key = stream_key(pattern)
        if pattern_key in declared_seen:
            continue
        declared_seen.add(pattern_key)
        yield from _walk_level(
            page,
            doc,
            [pattern],
            dataclasses.replace(path, pattern=pattern_key[0]),
            key=pattern_key,
            resources=resources if sub_resources is None else sub_resources,
            ctm=pattern_ctm,
            parents=parents,
            declared_seen=declared_seen,
            depth=depth + 1,
            fonts=fonts,
        )
    for name, proc, sub_resources, proc_ctm in type3_charprocs(resources, ctm):
        proc_key = stream_key(proc)
        if proc_key in declared_seen:
            continue
        declared_seen.add(proc_key)
        yield from _walk_level(
            page,
            doc,
            [proc],
            dataclasses.replace(path, charproc=name),
            key=proc_key,
            resources=resources if sub_resources is None else sub_resources,
            ctm=proc_ctm,
            type3=True,
            parents=parents,
            declared_seen=declared_seen,
            depth=depth + 1,
            fonts=fonts,
        )


def located_glyph_records(
    page: Page, page_index: int, doc: Document
) -> Iterator[tuple[StreamPath, GlyphRecord]]:
    """Every glyph on one page, wherever it lives, paired with the path that addresses it.

    The page's own /Contents first, then -- per 02-RESEARCH.md Section 5's four locations
    -- Form XObjects invoked by `Do` (recursively), tiling patterns and Type3 CharProcs
    declared in each level's /Resources, and finally each annotation's /AP /N appearance
    stream, which is a sibling of /Contents rather than something reachable from it.

    Lazy by page (Pitfall 8: never build the whole document's run map eagerly), and
    `font_id` is interned per page, exactly as `glyph_records` does -- the question it
    answers ("did the font change between these two glyphs?") is only ever asked within a
    page, and a document-wide interner would make every page's ids depend on how many
    pages were walked before it.
    """
    fonts = _FontIds()
    declared_seen: set[tuple[int, int]] = set()
    path = StreamPath(page=page_index)
    yield from _walk_level(
        page,
        doc,
        list(page.streams),
        path,
        key=None,
        resources=page.resources,
        ctm=page.ctm,
        parents=frozenset(),
        declared_seen=declared_seen,
        depth=0,
        fonts=fonts,
    )
    for annot_index, state, stream, resources, ctm in annotation_appearances(page):
        yield from _walk_level(
            page,
            doc,
            [stream],
            dataclasses.replace(path, annot=(annot_index, state)),
            key=stream_key(stream),
            resources=page.resources if resources is None else resources,
            ctm=ctm,
            parents=frozenset(),
            declared_seen=declared_seen,
            depth=1,
            fonts=fonts,
        )


def walk_document(doc: Document) -> Iterator[tuple[StreamPath, GlyphRecord]]:
    """Every glyph in the document, wherever it lives, paired with its `StreamPath`.

    Takes only the playa `Document`: the plan's original `walk_document(pdf, doc)` was
    written against a design where recursion needed pikepdf's object graph, but every
    location this walks -- Form XObjects, annotation /AP, tiling patterns, Type3 CharProcs
    -- is reachable through playa alone, and `stream.objid` gives the same identity
    pikepdf's `objgen` would. A second handle to the same bytes, unused, would be a
    liability rather than a parameter.
    """
    for page_index, page in enumerate(doc.pages):
        yield from located_glyph_records(page, page_index, doc)


__all__ = [
    "MAX_RECURSION_DEPTH",
    "StreamPath",
    "glyph_records",
    "located_glyph_records",
    "walk_document",
]
