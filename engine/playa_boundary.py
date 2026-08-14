"""The playa boundary -- the two-pass ObjectParser/LazyInterpreter zip over a page's
coalesced /Contents.

THIS IS THE ONLY MODULE in the repository that imports `playa` (successor to
spike/playa_decode_probe.py, which held that role for the Phase 1 spike and is
now out of scope -- see its own docstring). No Protocol, ABC, adapter, or
factory is built around it: the file boundary itself is the swap mechanism.

Why two passes over the same bytes, per 02-RESEARCH.md Section 8: playa gives
every semantic glyph field (code, unicode, position, advance, font) and none
of the provenance fields (stream_id, operator byte offset, TJ item index,
byte offset within string). `playa.parser.ObjectParser` gives the inverse --
every byte offset and no resolved semantics. Matching the two afterwards by
string or geometry would be a fuzzy join on the critical path. Instead: both
passes walk the identical buffer in the identical order, so the k-th
text-showing operator in Pass A (`operator_table`, via `ObjectParser`) *is*
the k-th `TextObject` yielded by Pass B (`LazyInterpreter`), by construction.
No matching, no heuristics.

`LazyInterpreter._curpos` is the tripwire that proves the zip stayed aligned:
after each Pass B yield it holds the byte offset the interpreter has reached,
and `walk_page` asserts it equals the keyword offset Pass A recorded for the
same ordinal -- on EVERY yield, and once more after the loop ends (see
"Alignment tripwire has two ends" below). This is a private attribute
(verified present on `playa.page.LazyInterpreter` in the installed playa
1.1.0) -- a playa upgrade must re-verify it exists and still means the same
thing before this module is trusted again.

## Coalescing ruling (2026-08-13, .planning/phases/02-text-model/02-04-PLAN.md)

A page's `/Contents` can be an array of parts. Two naive approaches both fail:
- Per-part isolation (parsing each part with its own fresh ObjectParser/LazyInterpreter)
  splits a text-showing operator's keyword from its operand array when the split falls
  between them -- legal per ISO 32000-1 7.8.2, measured on 46/217 corpus documents.
- Naive byte concatenation (`b"".join`) fuses the last token of one part with the first
  of the next -- a part ending "Q" followed by a part starting "BT" lexes as the single
  keyword "QBT" (qpdf #444; see tests/test_walker.py's fusion tests).

The fix: join parts with a `b"\n"` separator into ONE buffer before running either pass.
The separator is load-bearing, not cosmetic -- it is what a bare token-adjacent join is
missing, and it is what prevents the QBT fusion (newline is PDF whitespace, so it always
lexes as a token boundary). A single continuous parse over that one buffer sees every
operator whole, so there is nothing left to split.

## A run ID addresses the operator keyword, not its operands

`_locate_part` maps a byte offset in the joined buffer back to
`(part_index, offset_within_that_part)`. **It is only ever called on `kw_off` -- the
text-showing operator's own keyword position.** That is deliberate and it is the whole
of what a run ID needs: `run_id.py`'s `resolve_run_id_offset` confirms an operator
keyword token starts at the decoded offset; a run ID is `(part, byte_offset_within_part)`
of that keyword, nothing else.

An operand can live in a **different part** than the keyword that consumes it -- the same
`/Contents`-splits-mid-structure fact that motivated coalescing in the first place, just
one level up. Confirmed on `corpus/public/govdocs1_000_000010.pdf` page 0, operator #24
(a `TJ`): `part_ranges = [(0, 1386), (1387, 2841), ...]` (0-indexed, `[start, end)` in the
joined buffer); the `TJ` keyword sits at joined-buffer offset 1387 -> part 1, offset 0 --
but its operand array was parsed starting at joined-buffer offset 1349 -> part 0. One
`(part, offset)` pair cannot address both; the grammar in `run_id.py` only has room for
one `:c{part}` per ID, and it was never meant to address anything but the keyword.

This is why `operator_table`'s operands carry **no byte offset at all** -- earlier
versions of this module yielded `(operand_byte_offset, operand_value)` pairs, an
artifact of transcribing 02-RESEARCH.md's Pattern 1 literally. That offset was always a
position in the *joined* buffer, which the operator #24 case above proves cannot be
translated into a single `(part, offset)` pair the way the keyword's can, and no
consumer needs it to: `byte_offset_within_string` (a glyph's position inside a `Tj`/`'`/
`"` string, e.g. 3 for the 4th byte of `(Hello)`) is counted from the *string's own*
first byte, and `item_index_within_tj` is an index into the *array already yielded
whole* -- both are local to the operand's own value, not a buffer address, and both are
fully computable from what `operands` already carries. So `operands` is just
`list[object]` (each element is the operand's *value* -- `bytes`, `int`, `float`, or for
`TJ` a `list` of those -- never its position).

## Text outside /Contents (02-05): one interpreter per level, constructed here

`walk_stream` generalises `walk_page` to any single content-stream level -- a page's
coalesced /Contents, a Form XObject, an annotation appearance stream, a tiling pattern, a
Type3 CharProc -- because `_curpos` and the two-pass zip are only correct for the buffer
the interpreter was constructed over. `Page.flatten()` recurses for you but hands back
objects whose inner interpreter is unreachable, so every glyph below the top level would
be addressed as an offset into the *page's* stream (02-RESEARCH.md Pitfall 4). Hence: a
fresh `LazyInterpreter` per level, and `walk_stream` yields the `Do`-invoked
`XObjectObject`s rather than following them, leaving the recursion (and its cycle guard,
depth cap and run-ID path) to `engine.walker`.

The other three locations have no playa object at all -- `Annotation.props` is a raw dict
and playa never interprets /AP, and there is no PatternObject -- so
`annotation_appearances`, `tiling_patterns` and `type3_charprocs` resolve them from the
raw object graph here, where the playa resolvers live. Each returns plain
`(stream, resources, ctm)` triples that go straight back into `walk_stream`.

## Alignment tripwire has two ends

The per-yield `assert interp._curpos == kw_off` only fires while there is a Pass-B value
to compare against a Pass-A entry. If Pass A has strictly more entries than Pass B *and
the extra entry is the last one*, `enumerate(interp)` simply runs out first and the loop
ends silently -- `table`'s unconsumed tail is never compared, no assertion, no
`IndexError` (the opposite direction, Pass A short, *is* caught loudly via `IndexError`
on `table[k]`). `walk_page` therefore also asserts `k + 1 == len(table)` once the loop
ends, naming both counts, closing that blind spot.

Transcribed from 02-RESEARCH.md's "Pattern 1: The two-pass zip with a free alignment
assertion" (verified against playa 1.1.0, playa/parser.py:898, playa/interp.py:308), with
corrections forced by verification against the real corpus and by review rather than a
redesign of Pattern 1's shape: the coalescing above, `_has_visible_text` below (playa's
own `do_TJ` silently produces no TextObject for a text-showing operator whose string
operand is entirely empty -- e.g. `() Tj` -- so Pass A must not count it as text-showing
either, or Pass A and Pass B disagree on the ordinal count independent of any
part-boundary issue), the operand-offset removal above, and the trailing-entry assertion
above. See task-1-report.md for the corpus evidence behind each.
"""

from __future__ import annotations

import bisect
import logging
from typing import Iterator

from playa.content import GlyphObject, GraphicState, TextObject, XObjectObject
from playa.document import Document
from playa.font import Font
from playa.interp import LazyInterpreter, Type3Interpreter
from playa.page import Page
from playa.parser import ObjectParser
from playa.pdftypes import (
    MATRIX_IDENTITY,
    ContentStream,
    Matrix,
    PDFObject,
    PSKeyword,
    Rect,
    dict_value,
    int_value,
    literal_name,
    matrix_value,
    rect_value,
    resolve1,
    stream_value,
)
from playa.utils import mult_matrix, transform_bbox

# Re-exported so consumers get real types without a second `import playa` anywhere in the
# repo (there is a test asserting exactly one file imports playa). The file boundary is
# the swap mechanism, so the types cross it too -- an alias layer would defeat the point.
__all__ = [
    "ContentStream",
    "Document",
    "Font",
    "GlyphObject",
    "Matrix",
    "Page",
    "Resources",
    "TextOp",
    "TextObject",
    "XObjectObject",
    "annotation_appearances",
    "glyph_byte_offsets",
    "operator_table",
    "stream_key",
    "tiling_patterns",
    "type3_charprocs",
    "walk_page",
    "walk_stream",
]

log = logging.getLogger(__name__)

# A resolved /Resources dictionary. playa types it as Dict[str, PDFObject] on Page and as
# the same shape (or None, meaning "inherit the page's") on XObjectObject.
Resources = dict[str, PDFObject]

# What `walk_stream` yields for one text-showing operator: exactly `walk_page`'s tuple.
TextOp = tuple[int, int, list[object], TextObject]

TEXT_OPS = {b"Tj", b"TJ", b"'", b'"'}


def _has_visible_text(kw: bytes, operands: list[object]) -> bool:
    """Mirror playa's interp.py do_TJ 'has_text' gate exactly: a Tj/TJ/'/" whose string
    operand(s) are entirely empty makes do_TJ return None, so LazyInterpreter emits no
    TextObject for it at all. Pass A must apply the identical rule or it counts operators
    Pass B will never produce.

    Tj/'/": the operand list's last entry is the string (' and " prepend aw/ac operands
    that "  also carries, so the string is always last). TJ: the sole operand is an array;
    at least one bytes element must be non-empty.
    """
    if not operands:
        return False
    if kw in (b"Tj", b"'", b'"'):
        s = operands[-1]
        return isinstance(s, bytes) and len(s) > 0
    if kw == b"TJ":
        arr = operands[0]
        if not isinstance(arr, list):
            return False
        return any(isinstance(el, bytes) and len(el) > 0 for el in arr)
    return False


def operator_table(buffer: bytes, doc: Document) -> list[tuple[int, bytes, list[object]]]:
    """Pass A: (keyword_byte_offset, keyword, [operand_value, ...]) for every text-showing
    operator that will actually produce a TextObject in Pass B. Operand values only, no
    positions -- see module docstring's "A run ID addresses the operator keyword" for why
    an operand's byte offset is neither addressable nor needed."""
    stack: list[object] = []
    out: list[tuple[int, bytes, list[object]]] = []
    for pos, obj in ObjectParser(buffer, doc):
        if isinstance(obj, PSKeyword):
            if obj.name in TEXT_OPS and _has_visible_text(obj.name, stack):
                out.append((pos, obj.name, list(stack)))
            stack.clear()
        else:
            stack.append(obj)
    return out


def glyph_byte_offsets(font: Font, data: bytes) -> list[int]:
    """Byte offset of each glyph within its OWN string operand, using the font's own
    decoder rather than a reimplementation of it.

    This is a playa *decode* call, which is why it lives here and not in walker.py: the
    project constraint is that playa decoding stays in this one module. walker.py consumes
    the returned offsets, which are plain ints.

    Two cases, both taken from playa 1.1.0's own `Font.decode` implementations:
    - Simple fonts (Type1/TrueType/Type3) decode `data` byte-by-byte -- both branches of
      `SimpleFont.decode` iterate the raw bytes -- so glyph i sits at byte i. The
      ToUnicode branch is a `zip`, which truncates to the shorter side, so the caller
      must not assume len(data) glyphs; it gets exactly as many offsets as playa yields.
    - CID fonts consume a variable number of bytes per code via the CMap.
      `CIDFont.cmap.decode` yields `(substr, cid)` where `substr` is the raw bytes
      consumed, so the spans are read off playa's decoder directly.

    Duck-typed on the presence of `cmap` rather than `isinstance(font, CIDFont)` -- an
    isinstance check would be a second playa import surface for no gain.
    """
    cmap = getattr(font, "cmap", None)
    if cmap is None:
        return [i for i, _ in enumerate(font.decode(data))]
    offsets: list[int] = []
    pos = 0
    for substr, _cid in cmap.decode(data):
        offsets.append(pos)
        pos += len(substr)
    return offsets


def _coalesce_parts(parts: list[ContentStream]) -> tuple[bytes, list[tuple[int, int]]]:
    """Join a page's /Contents parts with b"\\n" -- never bare b"".join (see module
    docstring). Returns (joined_buffer, part_ranges); part_ranges[i] = (start, end) is
    part i's byte range [start, end) within joined_buffer -- part i's own index (0, 1, 2,
    ...) is what run IDs address, deliberately not the stream objid: qpdf's repair-on-open
    can renumber objects, and part index is stable across that (02-RESEARCH.md Open
    Question 4)."""
    pieces: list[bytes] = []
    part_ranges: list[tuple[int, int]] = []
    pos = 0
    for part in parts:
        data = bytes(part.buffer)
        start = pos
        end = start + len(data)
        part_ranges.append((start, end))
        pieces.append(data)
        pos = end + 1  # +1 for the b"\n" separator
    return b"\n".join(pieces), part_ranges


def _locate_part(offset: int, part_ranges: list[tuple[int, int]]) -> tuple[int, int]:
    """Map a byte offset in the joined buffer back to (part_index, offset_within_that_part)
    -- what run IDs address (TEXT-03). Only ever called on an operator keyword's own
    offset (see module docstring); an operand's offset is not addressable this way and
    `operator_table` does not yield one."""
    starts = [r[0] for r in part_ranges]
    i = bisect.bisect_right(starts, offset) - 1
    start, _end = part_ranges[i]
    return i, offset - start


def walk_stream(
    page: Page,
    doc: Document,
    parts: list[ContentStream],
    *,
    resources: Resources | None = None,
    ctm: Matrix | None = None,
    gstate: GraphicState | None = None,
    type3: bool = False,
) -> Iterator[TextOp | XObjectObject]:
    """Zip Pass A (`operator_table`) against Pass B (a FRESH `LazyInterpreter`) over ONE
    content stream level -- a page's coalesced /Contents, a Form XObject, an annotation
    appearance stream, a tiling pattern, or a Type3 CharProc.

    Yields, in content-stream order, either:
    - a `TextOp` -- `(byte_offset_within_part, part_index, operands, text_obj)`, the same
      tuple `walk_page` has always yielded, with `_curpos` asserted against Pass A; or
    - an `XObjectObject` -- a Form XObject invoked by `Do` at this level, carrying its own
      stream, resources, composed CTM (/Matrix x this level's CTM) and inherited graphics
      state. The CALLER decides whether to recurse into it, which is the whole point:
      `Page.flatten()` would recurse for us but hand back objects whose provenance points
      into this stream rather than the XObject's own (02-RESEARCH.md Pitfall 4). Every
      level therefore gets a fresh interpreter, constructed here.

    Only TextOps advance the Pass A ordinal `k`, so the alignment tripwire is unchanged by
    the added XObjectObject yields -- an `XObjectObject` is not in Pass A's table and does
    not consume an entry.

    `resources`/`ctm`/`gstate` are None only for a page's own /Contents, where
    LazyInterpreter's own defaults (page.resources, page.ctm, a fresh state) are exactly
    right. `type3=True` swaps in playa's `Type3Interpreter`, which is `LazyInterpreter`
    plus the `d0`/`d1` glyph-metric operators a CharProc is required to open with.
    """
    joined, part_ranges = _coalesce_parts(parts)
    table = operator_table(joined, doc)
    # A single fake ContentStream wrapping the joined buffer: attrs={} means get_filters()
    # finds no /Filter, so .buffer (== .decode()) returns rawdata unchanged. This is what
    # makes Pass B parse the SAME joined buffer as Pass A, as one continuous stream.
    coalesced_stream = ContentStream(attrs={}, rawdata=joined)
    interp_class: type[LazyInterpreter] = Type3Interpreter if type3 else LazyInterpreter
    # Positional, because playa 1.1.0's Type3Interpreter.__init__ accepts neither
    # `filter_classes` nor `restrict_ops` -- the attribute assignment below is the one
    # construction path that works for both classes.
    interp = interp_class(page, [coalesced_stream], resources, ctm, gstate)
    interp.filter_classes = [TextObject, XObjectObject]
    k = -1
    for obj in interp:
        if isinstance(obj, XObjectObject):
            yield obj
            continue
        # filter_classes guarantees this at runtime; LazyInterpreter's __next__ is typed
        # generically as ContentObject, so narrow explicitly for mypy.
        assert isinstance(obj, TextObject)
        k += 1
        kw_off, _kw, operands = table[k]
        # Free, always-on drift tripwire. Costs one integer compare.
        assert interp._curpos == kw_off, (
            f"playa iteration desync at op {k}: _curpos={interp._curpos} != {kw_off}. "
            f"playa-pdf version changed iteration semantics -- do not proceed."
        )
        part_index, part_offset = _locate_part(kw_off, part_ranges)
        yield part_offset, part_index, operands, obj
    # The other end of the tripwire: if Pass A has an unconsumed tail (its LAST entries
    # never matched by a Pass-B yield), the loop above ends silently with no IndexError
    # and no per-yield assertion ever sees it. Catch that here.
    assert k + 1 == len(table), (
        f"playa iteration desync: Pass B yielded {k + 1} operator(s) but Pass A recorded "
        f"{len(table)} -- Pass A has an unconsumed tail Pass B never produced. "
        f"playa-pdf version changed iteration semantics -- do not proceed."
    )


def walk_page(page: Page, doc: Document) -> Iterator[TextOp]:
    """A page's own coalesced /Contents, text-showing operators only.

    `walk_stream` over `page.streams` with the Form XObject invocations dropped: this is
    the page-local view `glyph_records` has always had, unchanged. Recursion into what the
    dropped `Do`s reference is `walker.walk_document`'s job, because only the walker can
    carry the run-ID path that addresses the deeper level.
    """
    for item in walk_stream(page, doc, list(page.streams)):
        if not isinstance(item, XObjectObject):
            yield item


def _child_ctm(stream: ContentStream, base: Matrix) -> Matrix:
    """Compose a child stream's own /Matrix onto the CTM in force where it is invoked --
    the same composition playa does in `XObjectObject.from_stream` (`mult_matrix(/Matrix,
    ctm)`), applied here to the two child stream kinds playa has no object for."""
    matrix = matrix_value(stream["Matrix"]) if "Matrix" in stream else MATRIX_IDENTITY
    return mult_matrix(matrix, base)


def annotation_appearances(
    page: Page,
) -> list[tuple[int, str, ContentStream, Resources | None, Matrix]]:
    """Every annotation's normal appearance stream: (annot_index, ap_state, stream,
    resources, ctm).

    playa yields `Annotation.props` -- the raw dictionary -- and stops there; it does not
    interpret /AP at all (02-RESEARCH.md Section 5). So both halves are done here:

    - **/AP /N may be a stream OR a dictionary of streams keyed by appearance state**,
      selected by the annotation's /AS (ISO 32000-1 12.5.5). A stream directly under /N
      has no state name, and reports "N" -- the run-ID grammar's `a{idx}:{state}` segment
      has no empty-state form. When /N is a dict, /AS is required; a single-entry dict with
      /AS missing is unambiguous anyway and is accepted, anything else is skipped.
    - **Positioning is the /Rect fit, not the page CTM.** Transform /BBox by /Matrix, take
      the bounding box of the result, and compute the matrix A that maps that box onto
      /Rect; the appearance runs under `/Matrix x A x page.ctm`. Handing the interpreter a
      bare `page.ctm` instead would put every annotation glyph at coordinates in form
      space -- plausible numbers, wrong page positions, and the run clusterer downstream
      cannot tell the difference.

    Malformed entries are logged (index and reason only, never annotation content) and
    skipped: this walks untrusted uploads, and one broken /AP must not lose the other
    annotations on the page.
    """
    out: list[tuple[int, str, ContentStream, Resources | None, Matrix]] = []
    for index, annot in enumerate(page.annotations):
        try:
            ap = resolve1(annot.props.get("AP"))
            if not isinstance(ap, dict):
                continue
            normal = resolve1(ap.get("N"))
            state = "N"
            # ContentStream is a Mapping, not a dict, so this branch is the state-dict
            # case only -- a stream directly under /N falls straight through.
            if isinstance(normal, dict):
                as_name = resolve1(annot.props.get("AS"))
                if as_name is not None:
                    state = literal_name(as_name)
                elif len(normal) == 1:
                    state = next(iter(normal))
                else:
                    log.debug(
                        "annotation %d: /AP /N is a %d-state dict with no /AS; skipped",
                        index,
                        len(normal),
                    )
                    continue
                if state not in normal:
                    log.debug("annotation %d: /AS names an absent state; skipped", index)
                    continue
                normal = resolve1(normal[state])
            if not isinstance(normal, ContentStream):
                continue
            resources = normal.get("Resources")
            out.append(
                (
                    index,
                    state,
                    normal,
                    None if resources is None else dict_value(resources),
                    _appearance_ctm(normal, annot.rect, page.ctm),
                )
            )
        except (TypeError, ValueError) as exc:
            log.debug("annotation %d: unusable /AP (%s); skipped", index, type(exc).__name__)
    return out


def _appearance_ctm(stream: ContentStream, rect: Rect, page_ctm: Matrix) -> Matrix:
    """ISO 32000-1 12.5.5's appearance-to-/Rect fit, composed onto the page CTM."""
    matrix = matrix_value(stream["Matrix"]) if "Matrix" in stream else MATRIX_IDENTITY
    if "BBox" not in stream:
        # No /BBox means no box to fit; the appearance is degenerate. Page CTM is the
        # only defensible fallback and keeps the glyphs on the page.
        return mult_matrix(matrix, page_ctm)
    tx0, ty0, tx1, ty1 = transform_bbox(matrix, rect_value(stream["BBox"]))
    rx0, ry0, rx1, ry1 = rect
    rx0, rx1 = min(rx0, rx1), max(rx0, rx1)
    ry0, ry1 = min(ry0, ry1), max(ry0, ry1)
    # A degenerate (zero-width or zero-height) transformed BBox has no scale factor; 1.0
    # keeps the appearance at its natural size rather than collapsing it to a point.
    sx = (rx1 - rx0) / (tx1 - tx0) if tx1 != tx0 else 1.0
    sy = (ry1 - ry0) / (ty1 - ty0) if ty1 != ty0 else 1.0
    fit: Matrix = (sx, 0.0, 0.0, sy, rx0 - sx * tx0, ry0 - sy * ty0)
    return mult_matrix(matrix, mult_matrix(fit, page_ctm))


def tiling_patterns(
    resources: Resources, ctm: Matrix
) -> list[tuple[ContentStream, Resources | None, Matrix]]:
    """Every /PatternType 1 (tiling) pattern declared in one level's /Resources /Pattern:
    (stream, resources, ctm). A tiling pattern object *is* a content stream and can show
    text; playa has no PatternObject and its `do_scn` only sets colour, so this is read off
    the resource dictionary directly.

    ponytail: declared, not invocation-tracked. A pattern named in /Resources but never
    selected by an `scn`/`SCN` with a pattern colour space is still walked, so its text
    becomes addressable even though nothing painted it. Over-inclusion is the safe
    direction for a walker that never decides editability, and the alternative -- tracking
    the pattern colour space through `cs`/`CS` and matching name operands on `scn`/`SCN` --
    is a graphics-state machine this module exists to *not* reimplement. Upgrade path if
    the false-positive rate ever matters: record `scn`/`SCN` name operands in Pass A
    (`operator_table` already sees every token) and intersect with this list.
    """
    out: list[tuple[ContentStream, Resources | None, Matrix]] = []
    patterns = resolve1(resources.get("Pattern"))
    if not isinstance(patterns, dict):
        return out
    for name, ref in patterns.items():
        try:
            pattern = stream_value(resolve1(ref))
            if int_value(pattern.get("PatternType")) != 1:
                continue
            sub = pattern.get("Resources")
            out.append(
                (
                    pattern,
                    None if sub is None else dict_value(sub),
                    _child_ctm(pattern, ctm),
                )
            )
        except (TypeError, ValueError) as exc:
            log.debug("pattern %r: unusable (%s); skipped", name, type(exc).__name__)
    return out


def type3_charprocs(
    resources: Resources, ctm: Matrix
) -> list[tuple[str, ContentStream, Resources | None, Matrix]]:
    """Every Type3 /CharProcs content stream declared in one level's /Resources /Font:
    (charproc_name, stream, resources, ctm).

    ponytail: enumerated per stream level, once, rather than once per invoking glyph. A
    CharProc is really invoked once per glyph drawn, under `/FontMatrix x Tm x Tfs x CTM`
    -- so the CTM here (`/FontMatrix x` this level's CTM) is the right *shape* but is
    missing the invoking text object's own matrix, and glyph coordinates inside a CharProc
    are therefore glyph-local, not page positions. The addressing -- which is what a run ID
    needs, and what Phase 3 rewrites -- is exact either way: the `y{charProcName}` segment
    plus a byte offset into the CharProc's own stream. Upgrade path if a consumer ever
    needs page positions for Type3 glyph internals: recurse from each GlyphObject instead
    of from the resource dictionary, composing its text rendering matrix.
    """
    out: list[tuple[str, ContentStream, Resources | None, Matrix]] = []
    fonts = resolve1(resources.get("Font"))
    if not isinstance(fonts, dict):
        return out
    for name, ref in fonts.items():
        try:
            font = resolve1(ref)
            if not isinstance(font, dict) or font.get("Subtype") is None:
                continue
            if literal_name(font["Subtype"]) != "Type3":
                continue
            charprocs = resolve1(font.get("CharProcs"))
            if not isinstance(charprocs, dict):
                continue
            sub = font.get("Resources")
            sub_resources = None if sub is None else dict_value(sub)
            font_matrix = (
                matrix_value(font["FontMatrix"])
                if "FontMatrix" in font
                else (0.001, 0.0, 0.0, 0.001, 0.0, 0.0)
            )
            child = mult_matrix(font_matrix, ctm)
            for proc_name, proc_ref in charprocs.items():
                out.append((proc_name, stream_value(resolve1(proc_ref)), sub_resources, child))
        except (TypeError, ValueError) as exc:
            log.debug("font %r: unusable /CharProcs (%s); skipped", name, type(exc).__name__)
    return out


def stream_key(stream: ContentStream) -> tuple[int, int]:
    """Cycle-guard identity for a content stream: its full (objid, genno).

    Matches `shared_xobjects._walk`'s `objgen` convention rather than playa's own
    `flatten()` (which uses `objid` alone and folds every direct stream onto 0). A direct
    (non-indirect) stream cannot be the target of a `Do`, so the None branch is a
    defensive floor, not a live path.
    """
    return (-1 if stream.objid is None else stream.objid, stream.genno or 0)
