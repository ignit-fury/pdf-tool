"""The playa boundary -- the two-pass ObjectParser/LazyInterpreter zip.

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
and `walk_part` asserts it equals the keyword offset Pass A recorded for the
same ordinal. This is a private attribute (verified present on
`playa.page.LazyInterpreter` in the installed playa 1.1.0) -- a playa upgrade
must re-verify it exists and still means the same thing before this module is
trusted again.

Transcribed from 02-RESEARCH.md's "Pattern 1: The two-pass zip with a free
alignment assertion" (verified against playa 1.1.0, playa/parser.py:898,
playa/interp.py:308) -- a design already executed against real corpus
documents, not something to redesign here.
"""

from __future__ import annotations

from typing import Iterator

from playa.content import TextObject
from playa.document import Document
from playa.interp import LazyInterpreter
from playa.page import Page
from playa.parser import ObjectParser
from playa.pdftypes import ContentStream, PSKeyword

TEXT_OPS = {b"Tj", b"TJ", b"'", b'"'}


def operator_table(
    buffer: bytes, doc: Document
) -> list[tuple[int, bytes, list[tuple[int, object]]]]:
    """Pass A: (keyword_byte_offset, keyword, [(operand_byte_offset, operand)])."""
    stack: list[tuple[int, object]] = []
    out: list[tuple[int, bytes, list[tuple[int, object]]]] = []
    for pos, obj in ObjectParser(buffer, doc):
        if isinstance(obj, PSKeyword):
            if obj.name in TEXT_OPS:
                out.append((pos, obj.name, list(stack)))
            stack.clear()
        else:
            stack.append((pos, obj))
    return out


def walk_part(
    page: Page, part_stream: ContentStream, doc: Document
) -> Iterator[tuple[int, int | None, list[tuple[int, object]], TextObject]]:
    """Zip Pass A (`operator_table`) against Pass B (`LazyInterpreter`) by ordinal.

    Yields (keyword_byte_offset, stream_id, operands, text_obj) per
    text-showing operator in `part_stream`. Asserts interp._curpos == kw_off
    on every yield -- the free, always-on drift tripwire described in the
    module docstring.
    """
    table = operator_table(part_stream.buffer, doc)
    interp = LazyInterpreter(page, [part_stream], filter_classes=[TextObject])
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
        yield kw_off, interp.parser.streamid, operands, text_obj
