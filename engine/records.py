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


@dataclass(frozen=True, slots=True)
class ClusterAttrs:
    """Per-glyph state the clusterer (02-07) needs that GlyphRecord's fixed 13 fields do
    not carry -- GlyphRecord's shape is locked by TEXT-02, so this travels beside it
    rather than extending it, the same precedent as 02-05's StreamPath.

    fill_color is `(gs.ncolor.values, gs.ncolor.pattern)` -- playa's non-stroking colour,
    which is fill colour (D-01: "only fill colour breaks a run", never stroke). Captured
    as a plain tuple, never the playa Color type itself, so this stays a pure-builtin
    shape and no playa import leaks past engine/playa_boundary.py.

    effective_em is `space_threshold.effective_em(text_obj)` -- the SAME em D-03 tuned
    K_EM/BREAK_EM against. Constant across one text-showing operator's glyphs, but every
    glyph carries its own copy rather than the caller re-deriving it, since size-relative
    break thresholds (superscript rise, gap-width) are exactly Pitfall 1's failure mode if
    they use `gstate.fontsize` instead.

    direction is `(matrix[0], matrix[1])`, the glyph's full text-rendering matrix's
    rotation/scale row -- the same matrix GlyphRecord.x/y come from (matrix[4]/matrix[5]).
    Projecting onto this, not raw device (x, y), is what makes banding correct on rotated
    text (02-RESEARCH.md Section 3).
    """

    fill_color: tuple[tuple[float, ...], str | None]
    rise: float
    effective_em: float
    direction: tuple[float, float]


@dataclass
class RunRecord:
    run_id: str
    glyphs: list[GlyphRecord]
    display_text: str  # synthetic spaces inserted by the clusterer (D-03)
    page: int
