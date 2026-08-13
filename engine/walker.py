"""Page-level glyph record assembly over the coalesced playa boundary (TEXT-01, TEXT-02).

`engine.playa_boundary.walk_page` yields one `(part_offset, part_index, operands,
text_obj)` per text-showing operator, with the two-pass alignment already asserted.
This module turns each of those into one `GlyphRecord` per glyph, filling the four
provenance fields playa does not expose.

NOTE ON NAMING: the boundary's `walk_page` and this module's `glyph_records` are
different things and deliberately named differently. `walk_page` is the operator-level
zip and returns tuples; `glyph_records` is the glyph-level product and returns
`GlyphRecord`s. An earlier revision of the plan had both called `walk_page`.

Scope: a page's own coalesced /Contents only. XObject / annotation / pattern / Type3
recursion is 02-05's extension of this same file (Pitfall 4 keeps it separate).

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

from engine.playa_boundary import (
    Document,
    GlyphObject,
    Page,
    glyph_byte_offsets,
    walk_page,
)
from engine.records import GlyphRecord
from engine.types import CharCode, Unicode

# Text render modes that paint nothing: 3 = neither fill nor stroke (the classic
# scanned-page OCR layer), 7 = add to clipping path only. Every other mode marks ink.
INVISIBLE_RENDER_MODES = frozenset({3, 7})


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


def glyph_records(page: Page, doc: Document) -> list[GlyphRecord]:
    """One fully-populated GlyphRecord per glyph on a page's own coalesced /Contents.

    `font_id` is an index interned per call, not a PDF object id: what consumers need is
    "did the font change between these two glyphs" (D-01 breaks runs on font change), and
    an objid is both unstable across qpdf's repair-on-open and absent from playa's Font.
    The `_fonts_seen` list holds a reference to each font so its id() cannot be recycled
    by the garbage collector into a false match.
    """
    records: list[GlyphRecord] = []
    font_ids: dict[int, int] = {}
    _fonts_seen: list[object] = []

    for part_offset, part_index, operands, text_obj in walk_page(page, doc):
        # A TextObject iterates GlyphObjects at runtime; playa types __iter__ generically
        # as ContentObject, so narrow explicitly rather than reaching through Any.
        glyphs = [g for g in text_obj if isinstance(g, GlyphObject)]
        if not glyphs:
            continue

        # The font cannot change inside one text-showing operator -- Tf is its own
        # operator -- so one lookup per operator, off the first glyph, is exact.
        font = glyphs[0].gstate.font
        if font is None:
            # playa produced glyphs with no font resource. Nothing to decode byte spans
            # against, and a guessed offset is worse than a loud skip; 02-08's classifier
            # is where "this page is not editable text" gets its refusal UX.
            continue
        positions: list[tuple[int | None, int]] = []
        for item_index, data in _string_items(operands):
            for off in glyph_byte_offsets(font, data):
                positions.append((item_index, off))

        _assert_glyph_alignment(len(glyphs), len(positions), part_index)

        for glyph, (item_index, byte_off) in zip(glyphs, positions):
            gs = glyph.gstate
            font_key = id(gs.font)
            if font_key not in font_ids:
                font_ids[font_key] = len(font_ids)
                _fonts_seen.append(gs.font)
            matrix = glyph.matrix
            records.append(
                GlyphRecord(
                    code=CharCode(glyph.cid),
                    # playa exposes no glyph index; the code->glyph forward map is
                    # 02-06's encoding table. None here is the documented legitimate
                    # absence, not a sentinel for failure.
                    glyph=None,
                    unicode=Unicode(glyph.text) if glyph.text is not None else None,
                    x=matrix[4],
                    y=matrix[5],
                    advance=glyph.displacement,
                    font_id=font_ids[font_key],
                    render_mode=gs.render_mode,
                    visible=gs.render_mode not in INVISIBLE_RENDER_MODES,
                    stream_id=part_index,
                    operator_byte_offset=part_offset,
                    item_index_within_tj=item_index,
                    byte_offset_within_string=byte_off,
                )
            )
    return records


__all__ = ["glyph_records"]
