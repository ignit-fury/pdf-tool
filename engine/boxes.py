"""Selection geometry in unrotated PDF user space (bottom-left origin).

These are hit boxes, not outline bounds. Glyph provenance remains unchanged; the
page transform and effective em captured during classification provide the device
to user-space conversion without making the browser guess at PDF text addresses.
"""
from __future__ import annotations

import math

import pikepdf

from engine.recipe import active_font_name_and_size
from engine.records import RunRecord


def run_box(
    run: RunRecord, raw_bytes: bytes, resources: pikepdf.Object | None
) -> tuple[float, float, float, float]:
    """Bound all glyph advances and approximate ascent/descent around the baseline.

    # ponytail: 0.8em ascent / 0.2em descent are selection padding, not measured
    font outlines. Upgrade to descriptor /Ascent and /Descent when exact outline
    bounds become a requirement. Effective em includes Tm and CTM scaling. Inverse
    page CTM handles screen inversion, MediaBox offsets, and /Rotate; glyph origins
    already include text transforms and nested Form matrices.
    """
    if not run.glyphs:
        raise ValueError("run_box_requires_glyphs")
    active = active_font_name_and_size(raw_bytes, run.glyphs[0].operator_byte_offset)
    em = abs(run.effective_em or (active[1] if active is not None else 1.0))
    em = max(em, 0.01)
    direction = run.direction or run.glyphs[0].advance
    length = math.hypot(*direction)
    ux, uy = (direction[0] / length, direction[1] / length) if length else (1.0, 0.0)
    # screen space has a reflected y axis; text's vertical em points opposite
    # the mathematical left normal there. Invert that sign before inverting CTM.
    ctm = run.page_ctm or (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    a, b, c, d, e, f = ctm
    determinant = a * d - b * c
    if abs(determinant) < 1e-12:
        raise ValueError("run_box_singular_page_transform")
    sign = 1.0 if determinant > 0 else -1.0
    nx, ny = -uy * sign, ux * sign
    points: list[tuple[float, float]] = []
    for glyph in run.glyphs:
        for x, y in ((glyph.x, glyph.y), (glyph.x + glyph.advance[0], glyph.y + glyph.advance[1])):
            for pad in (-0.2 * em, 0.8 * em):
                dx, dy = x + nx * pad - e, y + ny * pad - f
                points.append(((d * dx - c * dy) / determinant, (-b * dx + a * dy) / determinant))
    xs, ys = zip(*points)
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    # A zero-width space or vertically stacked mark is still selectable.
    return x0, y0, max(x1, x0 + 0.01), max(y1, y0 + 0.01)
