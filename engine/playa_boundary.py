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
same ordinal. This is a private attribute (verified present on
`playa.page.LazyInterpreter` in the installed playa 1.1.0) -- a playa upgrade
must re-verify it exists and still means the same thing before this module is
trusted again.

## Coalescing ruling (2026-08-13, .planning/phases/02-text-model/02-04-PLAN.md)

A page's `/Contents` can be an array of parts. Two naive approaches both fail:
- Per-part isolation (parsing each part with its own fresh ObjectParser/LazyInterpreter)
  splits a text-showing operator's keyword from its operand array when the split falls
  between them -- legal per ISO 32000-1 7.8.2, measured on 46/217 corpus documents.
- Naive byte concatenation (`b"".join`) fuses the last token of one part with the first
  of the next -- a part ending "Q" followed by a part starting "BT" lexes as the single
  keyword "QBT" (qpdf #444; see test_naive_join_fuses_qbt_govdocs1_002_002167).

The fix: join parts with a `b"\n"` separator into ONE buffer before running either pass.
The separator is load-bearing, not cosmetic -- it is what a bare token-adjacent join is
missing, and it is what prevents the QBT fusion (newline is PDF whitespace, so it always
lexes as a token boundary). A single continuous parse over that one buffer sees every
operator whole, so there is nothing left to split. Addressing by part is preserved
separately: `_locate_part` maps a byte offset in the joined buffer back to
(part_objid, offset_within_that_part) via each part's recorded byte range, which is what
run IDs need (Phase 3 must know which stream object to write an edit back into) --
addressing by part and parsing in isolation are separate concerns.

Transcribed from 02-RESEARCH.md's "Pattern 1: The two-pass zip with a free alignment
assertion" (verified against playa 1.1.0, playa/parser.py:898, playa/interp.py:308), with
two corrections forced by verification against the real corpus rather than a redesign of
Pattern 1's shape: the coalescing above, and `_has_visible_text` below (playa's own
`do_TJ` silently produces no TextObject for a text-showing operator whose string operand
is entirely empty -- e.g. `() Tj` -- so Pass A must not count it as text-showing either,
or Pass A and Pass B disagree on the ordinal count independent of any part-boundary
issue; see task-1-report.md for the corpus evidence, 5/217 documents before this fix).
"""

from __future__ import annotations

import bisect
from typing import Iterator

from playa.content import TextObject
from playa.document import Document
from playa.interp import LazyInterpreter
from playa.page import Page
from playa.parser import ObjectParser
from playa.pdftypes import ContentStream, PSKeyword

TEXT_OPS = {b"Tj", b"TJ", b"'", b'"'}


def _has_visible_text(kw: bytes, operands: list[tuple[int, object]]) -> bool:
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
        s = operands[-1][1]
        return isinstance(s, bytes) and len(s) > 0
    if kw == b"TJ":
        arr = operands[0][1]
        if not isinstance(arr, list):
            return False
        return any(isinstance(el, bytes) and len(el) > 0 for el in arr)
    return False


def operator_table(
    buffer: bytes, doc: Document
) -> list[tuple[int, bytes, list[tuple[int, object]]]]:
    """Pass A: (keyword_byte_offset, keyword, [(operand_byte_offset, operand)]) for every
    text-showing operator that will actually produce a TextObject in Pass B."""
    stack: list[tuple[int, object]] = []
    out: list[tuple[int, bytes, list[tuple[int, object]]]] = []
    for pos, obj in ObjectParser(buffer, doc):
        if isinstance(obj, PSKeyword):
            if obj.name in TEXT_OPS and _has_visible_text(obj.name, stack):
                out.append((pos, obj.name, list(stack)))
            stack.clear()
        else:
            stack.append((pos, obj))
    return out


def _coalesce_parts(parts: list[ContentStream]) -> tuple[bytes, list[tuple[int | None, int, int]]]:
    """Join a page's /Contents parts with b"\\n" -- never bare b"".join (see module
    docstring). Returns (joined_buffer, part_ranges); part_ranges[i] is
    (part_objid, start, end), part i's byte range [start, end) within joined_buffer."""
    pieces: list[bytes] = []
    part_ranges: list[tuple[int | None, int, int]] = []
    pos = 0
    for part in parts:
        data = bytes(part.buffer)
        start = pos
        end = start + len(data)
        part_ranges.append((part.objid, start, end))
        pieces.append(data)
        pos = end + 1  # +1 for the b"\n" separator
    return b"\n".join(pieces), part_ranges


def _locate_part(offset: int, part_ranges: list[tuple[int | None, int, int]]) -> tuple[int | None, int]:
    """Map a byte offset in the joined buffer back to (part_objid, offset_within_that_part)
    -- what run IDs address (TEXT-03), preserved separately from how parsing is done."""
    starts = [r[1] for r in part_ranges]
    i = bisect.bisect_right(starts, offset) - 1
    part_objid, start, _end = part_ranges[i]
    return part_objid, offset - start


def walk_page(
    page: Page, doc: Document
) -> Iterator[tuple[int, int | None, list[tuple[int, object]], TextObject]]:
    """Zip Pass A (`operator_table`) against Pass B (`LazyInterpreter`) over a page's whole
    /Contents, coalesced per the module docstring's ruling.

    Yields (byte_offset_within_part, part_objid, operands, text_obj) per text-showing
    operator that produces a TextObject. Asserts interp._curpos equals the operator's
    offset in the joined buffer on every yield -- the free, always-on drift tripwire;
    part-relative addressing is a pure post-processing step over that already-verified
    offset, via `_locate_part`.
    """
    parts = list(page.streams)
    joined, part_ranges = _coalesce_parts(parts)
    table = operator_table(joined, doc)
    # A single fake ContentStream wrapping the joined buffer: attrs={} means get_filters()
    # finds no /Filter, so .buffer (== .decode()) returns rawdata unchanged. This is what
    # makes Pass B parse the SAME joined buffer as Pass A, as one continuous stream.
    coalesced_stream = ContentStream(attrs={}, rawdata=joined)
    interp = LazyInterpreter(page, [coalesced_stream], filter_classes=[TextObject])
    for k, text_obj in enumerate(interp):
        kw_off, kw, operands = table[k]
        # filter_classes=[TextObject] guarantees this at runtime; LazyInterpreter's
        # __next__ is typed generically as ContentObject, so narrow explicitly for mypy.
        assert isinstance(text_obj, TextObject)
        # Free, always-on drift tripwire. Costs one integer compare.
        assert interp._curpos == kw_off, (
            f"playa iteration desync at op {k}: _curpos={interp._curpos} != {kw_off}. "
            f"playa-pdf version changed iteration semantics -- do not proceed."
        )
        part_objid, part_offset = _locate_part(kw_off, part_ranges)
        yield part_offset, part_objid, operands, text_obj
