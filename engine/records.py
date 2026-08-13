"""Provenance shapes every Phase 2 consumer builds against (TEXT-02).

GlyphRecord carries exactly the 13 fields 02-RESEARCH.md Section 8 identified
as required, and where each comes from. playa gives every semantic field
directly (code, glyph, unicode, x, y, advance, font_id, render_mode, visible)
but none of the provenance fields -- stream_id, operator_byte_offset,
item_index_within_tj, byte_offset_within_string are not exposed on any playa
object and must be tracked by the walker (02-04) off its own two-pass parse.

frozen=True, slots=True means a construction call missing any of the 13
fields raises TypeError before a half-built record can exist.
"""

from dataclasses import dataclass

from engine.types import CharCode, GlyphId, Unicode


@dataclass(frozen=True, slots=True)
class GlyphRecord:
    code: CharCode
    glyph: GlyphId | None
    unicode: Unicode | None
    x: float
    y: float
    advance: tuple[float, float]
    font_id: int
    render_mode: int
    visible: bool
    stream_id: int
    operator_byte_offset: int
    item_index_within_tj: int | None
    byte_offset_within_string: int


@dataclass
class RunRecord:
    run_id: str
    glyphs: list[GlyphRecord]
    display_text: str  # synthetic spaces inserted by the clusterer (D-03)
    page: int
