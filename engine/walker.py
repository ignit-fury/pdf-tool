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

This runs on untrusted uploads, so descent is bounded three ways -- T-02-02 and T-02-03
from the plan's threat register, plus a third shape that register does not name and review
found:

- a **visited set built per branch** -- `parents | {stream_key}`, never a global set. The
  same Form XObject legitimately appears on many pages and often several times within one
  page (that is what `shared_xobjects` counts); a global set would silently drop all but
  the first occurrence, which is real text vanishing rather than a cycle being cut.
- an **explicit depth cap**, `MAX_RECURSION_DEPTH`, for the chain that is deep but not
  cyclic -- a 500-deep XObject chain is a Python recursion blow-up and no visited set
  stops it.
- a **per-page stream budget**, `MAX_STREAMS_PER_PAGE`, for total work. See below.

Hitting any of them aborts that ONE branch, logs objids/depths/counts only (never glyph
text -- T-02-04), and returns normally. Nothing propagates to the caller: a malicious
XObject graph must not be able to fail a document that is otherwise fine.

## The third shape: exponential fan-out, which neither of the plan's two bounds catches

`[MEASURED by review, on fixtures it built: each level `Do`-invoking the next TWICE.
16 levels -> 65,535 records in 4.7s; 20 -> 1,048,575 in 85s; 22 -> 4,194,303 in 383s. A
~7 KB file with 30 such objects is ~10^9 walks.]`

Every branch of that graph is **acyclic**, so the per-branch visited set never fires -- no
stream is ever its own ancestor. Every branch is **shallow**, so the depth cap never fires
either. The work is nonetheless 2^levels, and `list(walk_document(doc))` -- which any run-map
builder does -- OOMs. Two correct bounds, both looking at the shape of one path, and neither
can see the size of the tree.

So the third bound counts what the other two do not: `MAX_STREAMS_PER_PAGE`, spent by every
level from one allowance shared across the whole page walk. This is a hosted service taking
arbitrary uploads; a known DoS deferred is a known DoS shipped.

## Declared streams are siblings, walked once per page -- the bound the plan did not
## anticipate

Tiling patterns and Type3 CharProcs are not reached by an operator; they are *declared* in
a /Resources dictionary. A CharProc that has no /Resources of its own inherits the level's
-- routinely the page's -- and so re-declares every sibling CharProc. That one fact broke
two separate assumptions, and both fixes are load-bearing.

**1. `declared_seen`, a per-PAGE-WALK visited set.** The per-branch `parents` set stops a
CharProc re-entering ITSELF and stops nothing else, so 512 siblings enumerate
512 x 511 x 510 ... paths and the depth cap only decides how many years that takes.
`[MEASURED: corpus/public/govdocs1_004_004050.pdf page 0 -- 512 CharProcs, no cycle, no
adversary; the walk did not finish in 5 minutes with only the per-branch guard.]`
Per-page is the right shape and not merely the cheap one: the run-ID grammar addresses a
CharProc as `y{name}` and a pattern as `t{objid}`, neither of which records which level
declared it, so walking one twice on a page yields two IDs for one span of bytes -- a
double-edit hazard for Phase 3, not just wasted work. Form XObjects keep the per-branch set
instead, because they genuinely recur: the same header XObject drawn at two positions is
two addressable placements under two distinct `x{objid}` paths.

**2. They are QUEUED, not recursed into.** `declared_seen` alone converts the
combinatorial explosion into a CHAIN: CharProc 1 re-enumerates the page's fonts, finds
CharProc 2 unseen, descends into it; 2 finds 3; and so on. Charging each of those a level
of depth made `MAX_RECURSION_DEPTH` fire on that same ordinary document and silently drop
most of its CharProcs, falsifying TEXT-06's claim to find text in every location outside
/Contents. Raising the cap is the wrong fix twice over: it treats the symptom, and a
5,000-CharProc font truncates anyway.

`[MEASURED on the same page, recursive vs queued: 512 declared CharProc NAMES over 424
distinct streams (88 streams carry two names each -- that collapse is `declared_seen`
working, not a loss). Recursive: 424 reached, 64 actually walked, 360 aborted at the depth
cap, max depth 65. Queued: 424 walked, 0 aborted, max depth 0.]`

A CharProc is a SIBLING of the 511 declared beside it, not a descendant. So `_walk_level`
appends declared streams to a `pending` queue which `located_glyph_records` drains at its
own top level, each keeping the depth of the level that declared it. Depth then measures
only real nesting (`Do` inside `Do`), and N CharProcs cost one Python frame instead of N.

Relabelling the depth counter alone would NOT have been enough, because nested generators
consume the interpreter stack whatever number they are labelled with -- it only moves the
cliff. `[MEASURED by review, relabel-only variant vs the shipped queue: 300 / 424 (the real
document) / 500 / 700 CharProcs all complete either way; at 1,000 the relabel-only variant
raises RecursionError while the queue completes, and the queue still completes at 3,000.]`
A large CJK Type3 font is squarely in that range.

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
from collections import deque
from dataclasses import dataclass
from typing import Iterator, NamedTuple

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
from engine.records import ClusterAttrs, GlyphRecord
from engine.space_threshold import effective_em
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

# Bounds TOTAL WORK on one page, which neither of the other two bounds can (see the module
# docstring's "The third shape: exponential fan-out").
#
# `[MEASURED: the worst page in the whole 217-document corpus walks 523 streams
# (govdocs1_004_004050.pdf page 2, a 512-CharProc Type3 font); the runner-up is
# govdocs1_009_009097.pdf page 13 at 478. Sampled over all 8,247 corpus pages.]`
#
# 8192 is ~15x the measured worst case -- comfortably above any real document while still
# turning a 2^n fan-out from "OOM" into "returns immediately".
MAX_STREAMS_PER_PAGE = 8192


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


class _Budget:
    """One page walk's remaining stream allowance, and whether exhaustion was logged yet.

    Mutable and shared down the whole page walk, exactly like `declared_seen`: the bound is
    on the page's TOTAL work, so every level spends from the same allowance regardless of
    which branch it sits on.

    Exhaustion is logged ONCE. Every abandoned branch logging its own line would be
    thousands of records on precisely the hostile document the budget exists to survive --
    a log-flood built out of the DoS mitigation.
    """

    def __init__(self, limit: int) -> None:
        self.left = limit
        self.reported = False

    def spend(self) -> bool:
        self.left -= 1
        return self.left >= 0


class _Declared(NamedTuple):
    """A tiling pattern or Type3 CharProc found in some level's /Resources, queued to be
    walked as a SIBLING of that level rather than descended into as its child.

    It carries the declaring level's `depth` and `parents` unchanged: a CharProc is not
    nested inside the one declared before it, and descending per sibling is what walked
    only 64 of govdocs1_004_004050.pdf's 424 CharProcs (see the module docstring).
    """

    stream: ContentStream
    path: StreamPath
    resources: Resources
    ctm: Matrix
    type3: bool
    parents: frozenset[tuple[int, int]]
    depth: int


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


def _op_records(
    op: TextOp, fonts: _FontIds
) -> Iterator[tuple[GlyphRecord, ClusterAttrs]]:
    """One fully-populated (GlyphRecord, ClusterAttrs) pair per glyph of one
    text-showing operator, built in a single pass so the two can never drift out of
    alignment with each other -- unlike a second parallel walk, there is no ordinal to
    keep in sync."""
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

    # Constant across every glyph of one text-showing operator (Tf/Tm/Tz are their own
    # operators), so computed once rather than per glyph. This IS the em D-03 tuned
    # K_EM/BREAK_EM against -- never gstate.fontsize (Pitfall 1).
    em = effective_em(text_obj)

    for glyph, (item_index, byte_off) in zip(glyphs, positions):
        gs = glyph.gstate
        matrix = glyph.matrix
        record = GlyphRecord(
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
        attrs = ClusterAttrs(
            # Non-stroking colour is fill colour (D-01). A plain tuple, never playa's
            # Color type, so no playa import is needed outside playa_boundary.py.
            fill_color=(tuple(gs.ncolor.values), gs.ncolor.pattern),
            rise=gs.rise,
            effective_em=em,
            direction=(matrix[0], matrix[1]),
        )
        yield record, attrs


def glyph_records(page: Page, doc: Document) -> list[GlyphRecord]:
    """One fully-populated GlyphRecord per glyph on a page's own coalesced /Contents.

    Text outside /Contents -- Form XObjects, annotation appearances, tiling patterns,
    Type3 CharProcs -- is deliberately NOT here: those records need a `StreamPath` to be
    addressable at all. See `located_glyph_records`.
    """
    fonts = _FontIds()
    return [rec for op in walk_page(page, doc) for rec, _attrs in _op_records(op, fonts)]


def cluster_records(page: Page, doc: Document) -> list[tuple[GlyphRecord, ClusterAttrs]]:
    """`glyph_records`, paired with the clustering attributes (02-07) GlyphRecord's fixed
    13 fields do not carry -- fill colour, rise, effective em, line direction. Page's own
    /Contents only, matching `glyph_records`' scope exactly."""
    fonts = _FontIds()
    return [pair for op in walk_page(page, doc) for pair in _op_records(op, fonts)]


def _skip_direct_declared(kind: str, page_index: int) -> None:
    """A declared stream with no objid cannot be walked, and must not be given one.

    `stream_key`'s (-1, 0) floor is inert for `Do` targets -- those are indirect by
    construction -- but declared streams are resolved out of a /Resources dictionary, so a
    malformed document can present two direct streams there. Folding both onto (-1, 0)
    would have `declared_seen` silently eat the second, and the resulting `/t-1` path
    segment does not match `_RUN_ID_RE`'s `\\d+` anyway: the record would be unaddressable
    even if it were produced. Skipping loudly beats minting a broken address.
    """
    log.warning(
        "declared %s stream has no objid (page %d); unaddressable, skipped",
        kind,
        page_index,
    )


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
    pending: deque[_Declared],
    budget: _Budget,
    depth: int,
    fonts: _FontIds,
) -> Iterator[tuple[StreamPath, GlyphRecord]]:
    """One content-stream level: its own text, the Form XObjects it invokes, and the
    declared streams it contributes to `pending` for the page walk to drain.

    `key` is the level's (objid, genno) cycle-guard identity, or None for a page's own
    /Contents (which is entered exactly once and has no objid of its own). Both bounds are
    enforced here, in one place, so no caller can descend without them.
    """
    if not budget.spend():
        # The fan-out bound. Counts and a page index only -- never glyph text (T-02-04).
        if not budget.reported:
            budget.reported = True
            log.warning(
                "stream budget: page %d exceeded MAX_STREAMS_PER_PAGE=%d; every branch "
                "still outstanding is abandoned (logged once)",
                path.page,
                MAX_STREAMS_PER_PAGE,
            )
        return
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
                pending=pending,
                budget=budget,
                depth=depth + 1,
                fonts=fonts,
            )
        else:
            for record, _attrs in _op_records(item, fonts):
                yield path, record

    # Streams reached through this level's /Resources rather than through an operator are
    # QUEUED, not descended into -- see the module docstring's "declared streams are
    # siblings". They keep this level's `depth` and this branch's `parents`, and the page
    # walk drains them at its own top level, so 512 CharProcs cost one frame, not 512.
    for pattern, sub_resources, pattern_ctm in tiling_patterns(resources, ctm):
        if pattern.objid is None:
            _skip_direct_declared("pattern", path.page)
            continue
        pattern_key = stream_key(pattern)
        if pattern_key in declared_seen:
            continue
        declared_seen.add(pattern_key)
        pending.append(
            _Declared(
                stream=pattern,
                path=dataclasses.replace(path, pattern=pattern_key[0]),
                resources=resources if sub_resources is None else sub_resources,
                ctm=pattern_ctm,
                type3=False,
                parents=parents,
                depth=depth,
            )
        )
    for name, proc, sub_resources, proc_ctm in type3_charprocs(resources, ctm):
        if proc.objid is None:
            _skip_direct_declared("charproc", path.page)
            continue
        proc_key = stream_key(proc)
        if proc_key in declared_seen:
            continue
        declared_seen.add(proc_key)
        pending.append(
            _Declared(
                stream=proc,
                path=dataclasses.replace(path, charproc=name),
                resources=resources if sub_resources is None else sub_resources,
                ctm=proc_ctm,
                type3=True,
                parents=parents,
                depth=depth,
            )
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
    pending: deque[_Declared] = deque()
    budget = _Budget(MAX_STREAMS_PER_PAGE)
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
        pending=pending,
        budget=budget,
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
            pending=pending,
            budget=budget,
            depth=1,
            fonts=fonts,
        )
    # Drain flat, in declaration order. Walking a queued stream can queue more (a pattern
    # whose own /Resources declare another), which is why this is a while over a deque and
    # not a for over a snapshot; `declared_seen` is what makes it finite.
    while pending:
        item = pending.popleft()
        yield from _walk_level(
            page,
            doc,
            [item.stream],
            item.path,
            key=stream_key(item.stream),
            resources=item.resources,
            ctm=item.ctm,
            type3=item.type3,
            parents=item.parents,
            declared_seen=declared_seen,
            pending=pending,
            budget=budget,
            depth=item.depth,
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
    "MAX_STREAMS_PER_PAGE",
    "StreamPath",
    "cluster_records",
    "glyph_records",
    "located_glyph_records",
    "walk_document",
]
