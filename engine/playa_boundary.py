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
from typing import Iterator

from playa.content import TextObject
from playa.document import Document
from playa.interp import LazyInterpreter
from playa.page import Page
from playa.parser import ObjectParser
from playa.pdftypes import ContentStream, PSKeyword

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


def walk_page(
    page: Page, doc: Document
) -> Iterator[tuple[int, int, list[object], TextObject]]:
    """Zip Pass A (`operator_table`) against Pass B (`LazyInterpreter`) over a page's whole
    /Contents, coalesced per the module docstring's ruling.

    Yields (byte_offset_within_part, part_index, operands, text_obj) per text-showing
    operator that produces a TextObject. Asserts interp._curpos equals the operator's
    offset in the joined buffer on every yield, and that Pass A and Pass B produced the
    same total count once the loop ends -- the free, always-on drift tripwire (module
    docstring: "Alignment tripwire has two ends"). Part-relative addressing of the
    keyword is a pure post-processing step over that already-verified offset, via
    `_locate_part`.
    """
    parts = list(page.streams)
    joined, part_ranges = _coalesce_parts(parts)
    table = operator_table(joined, doc)
    # A single fake ContentStream wrapping the joined buffer: attrs={} means get_filters()
    # finds no /Filter, so .buffer (== .decode()) returns rawdata unchanged. This is what
    # makes Pass B parse the SAME joined buffer as Pass A, as one continuous stream.
    coalesced_stream = ContentStream(attrs={}, rawdata=joined)
    interp = LazyInterpreter(page, [coalesced_stream], filter_classes=[TextObject])
    k = -1
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
        part_index, part_offset = _locate_part(kw_off, part_ranges)
        yield part_offset, part_index, operands, text_obj
    # The other end of the tripwire: if Pass A has an unconsumed tail (its LAST entries
    # never matched by a Pass-B yield), the loop above ends silently with no IndexError
    # and no per-yield assertion ever sees it. Catch that here.
    assert k + 1 == len(table), (
        f"playa iteration desync: Pass B yielded {k + 1} operator(s) but Pass A recorded "
        f"{len(table)} -- Pass A has an unconsumed tail Pass B never produced. "
        f"playa-pdf version changed iteration semantics -- do not proceed."
    )
