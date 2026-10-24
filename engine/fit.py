"""TJ-refit width-fitting: fits replacement text into an original text run's advance width.

Ported from `spike/tj_refit_prototype.py` (Phase 1's spike). See
`.planning/phases/01-conformance-harness-engine-spike/TJ-REFIT-RESULTS.md` for the measured
proof this port reproduces: Δwidth = 0.0000pt in both the shorter- and longer-replacement
directions, on the same real IRS Form W-9 fixture used by `tests/test_fit.py`.

Algorithm, priority-ordered (research/PITFALLS.md, Pitfall 5 "Naive replacement wrecks advance
widths"):
  1. Shape the replacement text with uharfbuzz's `hb.shape()` to learn the correct GLYPH
     SEQUENCE, then sum each shaped glyph's own *unkerned* `hmtx` advance -- NOT harfbuzz's
     `pos.x_advance`, which folds in the font's GPOS kerning. See `shape_advance_pt` for why
     the kerned number is the wrong basis for a PDF text-showing operator.
  2. Compute delta_pt = shaped_advance_pt - original_advance_pt.
  3. If |delta_pt| fits within roughly one space-glyph width, absorb it entirely in a single
     trailing TJ kern number. Cheapest, invisible, and exactly correct for what follows on the
     line.
  4. Otherwise, distribute the delta evenly across the inter-word kerns already present in the
     run (bounded absorption range -- see `_INTER_WORD_ABSORB_MULTIPLIER` below).
     If a shorter replacement exceeds that range, leave the unused space after its last
     glyph with a trailing TJ kern. This preserves the following text's position without
     stretching the replacement's glyphs or word spaces.
  5. Otherwise, if the replacement is longer than the original (delta > 0), try condensing it
     with `Tz` horizontal scaling down to `TZ_FLOOR_PERCENT`. This is priority 3 of the ladder:
     `trailing_kern` -> `inter_word_kern` -> `tz` -> refuse.
  6. Otherwise, refuse longer replacements. Refusing honestly is the point: a confident wrong
     fit is the failure mode this ladder guards against, not an acceptable shortcut.

TJ sign convention (load-bearing -- get this backwards and the fix doubles the error instead of
cancelling it): a TJ array number K is expressed in thousandths of text space and is SUBTRACTED
from the advance, scaled by font size:

    displacement_pt = -(K / 1000) * font_size_pt

So a POSITIVE K tightens (reduces total advance, moves the next glyph left); a NEGATIVE K widens
it. `kern_to_displacement_pt` and `test_sign_convention_positive_kern_tightens_advance` exist
specifically to pin this down.
"""

from __future__ import annotations

import dataclasses
import functools
import io
from collections.abc import Sequence
from pathlib import Path

import pikepdf
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.agl import toUnicode

from engine.encoding_table import STANDARD_14, cid_width, encoding_map
from engine.playa_boundary import core_font_widths

# "Roughly one space width" per Pitfall 5's priority-ordered absorption strategy -- the natural
# threshold below which a single trailing TJ kern looks invisible rather than like a gap.
_INTER_WORD_ABSORB_MULTIPLIER = 2.0
# Tightening must leave a visible, positive word space. The former symmetric
# 2-space budget let positive kerns reverse a gap and reorder decoded words.
# Larger compression goes through bounded Tz or is refused instead.
_INTER_WORD_TIGHTEN_MULTIPLIER = 0.5

# 03-RESEARCH.md Pattern 3: wide end of EDIT-03's 90-95% band, maximizes usable range and
# reduces D-06/D-08's refusal rate -- Claude's Discretion per 03-CONTEXT.md, not corpus-measured.
TZ_FLOOR_PERCENT = 90.0


@dataclasses.dataclass(frozen=True, slots=True)
class FitResult:
    """The outcome of one `fit_run` call. Frozen/slots (deviation from the spike's plain
    `@dataclasses.dataclass`) -- matches every other verdict/record type in `engine/`
    (`engine/encoding_table.py`'s `FontVerdict`/`GlyphVerdict`) so a construction call missing
    a field raises `TypeError` before a half-built record exists, rather than silently
    defaulting."""

    original_advance_pt: float
    replacement_shaped_advance_pt: float  # unfit, before any kern is applied
    delta_pt: float  # residual after fitting (== shaped - original, unfit if refused)
    strategy: str  # "trailing_kern" | "inter_word_kern" | "tz" | "refused"
    kerns: list[float]  # TJ kern numbers applied, in thousandths of text space
    refused: bool = False
    refusal_reason: str | None = None
    # `tz` strategy only -- 03-RESEARCH.md Pattern 3: this module computes the required scale,
    # it does not emit any PDF operators. `engine/rewrite.py` (03-06) owns finding/restoring any
    # actual preceding `Tz` and building the save/restore pair around the replacement text-showing
    # operator; `original_scale_to_restore` is always the spec default (100.0) here because this
    # module has no content-stream context to look one up.
    condensed_scale: float | None = None
    original_scale_to_restore: float | None = None


# Every shaping entry point below accepts EITHER a bundled font's own path OR an
# ALREADY-LOADED `(hb.Font, TTFont)` pair from `load_font`.
#
# DEVIATION from 03-07-PLAN.md's `<interfaces>` block, which transcribed `fit_run`'s font
# parameter as `tuple[hb.Font, int]`. The real, committed signature is a PATH, and
# `_load_font` returns `tuple[hb.Font, TTFont]`, not `tuple[hb.Font, int]` -- the plan's own
# instruction is to read the real file for field-level precision, so the union widens rather
# than either half being rewritten: `engine/recipe.py` needs to shape against raw BYTES (a
# run's own embedded program, or a bundled Liberation TTF read into memory) with no file to
# point at, while every existing caller (tests/test_fit.py, tests/test_tj_refit_prototype.py)
# passes a path and keeps working unchanged.


@functools.lru_cache(maxsize=None)
def load_font(data: bytes) -> tuple[hb.Font, TTFont]:
    """`_load_font`'s public, BYTES-accepting form (03-07 Task 2's promotion).

    Same two-loads-are-not-redundant rationale as `_load_font` below; the only difference is
    where the bytes come from. `hb.Blob(data)` rather than `hb.Blob.from_file_path(...)`
    follows `engine.fonts.shape_cids`'s own already-established in-memory precedent, and
    `TTFont(io.BytesIO(data))` follows `engine.fonts.subset_cid_widths`'s.

    Raises whatever fontTools/harfbuzz raise for a program neither can parse (a Type1
    `/FontFile`, a bare CFF `/FontFile3`) -- callers that must not crash catch it. This is
    deliberately not swallowed here: a silent `None` would let a caller fit against nothing.
    """
    return hb.Font(hb.Face(hb.Blob(data))), TTFont(io.BytesIO(data))


def _as_font(font: str | Path | tuple[hb.Font, TTFont]) -> tuple[hb.Font, TTFont]:
    """Normalise either accepted font form to the `(hb.Font, TTFont)` pair the shaping code
    actually uses. A tuple passes straight through -- already loaded, already cached by
    whoever called `load_font`."""
    if isinstance(font, tuple):
        return font
    return _load_font(font)


@functools.lru_cache(maxsize=None)
def _load_font(font_path: str | Path) -> tuple[hb.Font, TTFont]:
    # Return-type annotation fix (deviation from the spike): the body returns a tuple, but
    # the spike declared `-> hb.Font`. `spike/` sits outside mypy's `files = ["engine"]`
    # scope, so that mismatch was never caught there.
    #
    # Both loads are needed and they are not redundant: harfbuzz shapes (glyph SEQUENCE),
    # fontTools supplies each glyph's own unkerned `hmtx` advance (glyph WIDTH). Only
    # fontTools exposes the raw `hmtx` value un-adjusted by GPOS.
    #
    # `functools.lru_cache` (stdlib, no new dependency) -- same precedent as
    # `engine.fonts._liberation_ttfont`: this is called twice per `fit_run` (directly, and
    # again via `space_width_pt`) against a small, fixed set of bundled font files, and the
    # `TTFont(str(font_path))` load alone cost ~1.1ms per call before caching -- real
    # overhead on a synchronous per-page rewrite path. Two caveats, both already accepted
    # by the `_liberation_ttfont` precedent:
    #   1. `str` and `Path` for the same file cache as separate entries -- harmless, just a
    #      marginally less-effective cache, not a correctness issue.
    #   2. Callers now share the same mutable `hb.Font`/`TTFont` objects across calls.
    #      Safe here: `shape_advance_pt` (the sole caller) only reads from them --
    #      `hb.shape(hb_font, buf)` shapes into the caller's own `buf`, and
    #      `ttfont["hmtx"]` / `ttfont["head"].unitsPerEm` / `ttfont.getGlyphName(...)` are
    #      all read accesses. Neither object is mutated by this module.
    blob = hb.Blob.from_file_path(str(font_path))
    face = hb.Face(blob)
    return hb.Font(face), TTFont(str(font_path))


def shape_advance_pt(
    text: str, font: str | Path | tuple[hb.Font, TTFont], font_size_pt: float
) -> float:
    """Shape `text` with uharfbuzz and return the total *UNKERNED* advance of the resulting
    glyph sequence, in points.

    Load-bearing, and deliberately not what harfbuzz reports (this was a real bug, fixed):
    `hb.shape()`'s `pos.x_advance` includes the font program's GPOS pairwise kerning, but a
    PDF text-showing operator (`Tj`/`TJ`) NEVER applies the embedded font's own GPOS/kern
    tables. Per the PDF spec, glyph displacement during Tj/TJ is governed entirely by the
    font DICTIONARY's `/Widths` (simple fonts) or `/W` (Type0/CID) array, summed per glyph.
    So the kerned total is a number no viewer will ever render, and fitting against it puts
    the replacement text off by that kerning -- measured at up to ~6pt on real corpus text
    at 14pt, visible-scale error, not rounding noise.

    This is the same basis `read_original_advance_pt` reads the ORIGINAL run's advance from
    (`/Widths`//`W`, never the font program) and the same basis `engine.fonts
    .subset_cid_widths` writes the replacement's `/W` array from (unkerned `hmtx`), so all
    three now measure in one consistent space.

    Shaping is still done with harfbuzz, and must be: shaping decides the glyph sequence,
    including ligature substitution (GSUB), which legitimately changes the glyph set and
    therefore the unkerned total too. Only the per-glyph WIDTH comes from `hmtx`.
    """
    hb_font, ttfont = _as_font(font)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hb_font, buf)

    hmtx = ttfont["hmtx"]
    units_per_em: int = ttfont["head"].unitsPerEm
    # `* 1000 / unitsPerEm` -> the 1000-unit space a PDF `/Widths`//`W` entry always lives
    # in (matching `engine.fonts.subset_cid_widths` / `liberation_advance_1000u`), then
    # `* font_size_pt / 1000` -> points (matching `read_original_advance_pt`).
    total_thousandths = 0.0
    for info in buf.glyph_infos:
        # Resolve the shaped GID to a glyph NAME before the hmtx lookup -- same pattern as
        # `engine.fonts.shape_glyph_names`. uharfbuzz ships no py.typed marker
        # (pyproject.toml's mypy override), so `info.codepoint` types as Any.
        glyph_name = ttfont.getGlyphName(info.codepoint)
        total_thousandths += hmtx[glyph_name][0] * 1000.0 / units_per_em
    return total_thousandths / 1000.0 * font_size_pt


def space_width_pt(
    font: str | Path | tuple[hb.Font, TTFont], font_size_pt: float
) -> float:
    return shape_advance_pt(" ", font, font_size_pt)


def kern_to_displacement_pt(kern: float, font_size_pt: float) -> float:
    """TJ sign convention: the kern number is SUBTRACTED, in thousandths of text space."""
    return -(kern / 1000.0) * font_size_pt


def total_advance_with_kerns(
    shaped_advance_pt: float, kerns: list[float], font_size_pt: float
) -> float:
    return shaped_advance_pt + sum(
        kern_to_displacement_pt(k, font_size_pt) for k in kerns
    )


def advance_pt_for_codes(
    font: pikepdf.Object, codes: Sequence[int], font_size_pt: float
) -> float:
    """The advance of `codes` in `font`, read from the PDF font DICTIONARY's `/Widths`
    (simple fonts) or `/W` array (Type0/CID composite fonts), never the embedded font
    program.

    `codes` are the ORIGINAL PDF CHARACTER CODES as they appear in the content stream --
    `engine.types.CharCode`, which is what `/Widths` is indexed by. NOT decoded Unicode:
    `engine/types.py` exists to keep exactly these two apart ("/ToUnicode ... Decides
    nothing"), and under `/WinAnsiEncoding` the byte range 0x80-0x9F carries smart quotes
    and dashes whose `ord()` values (U+2018, U+2014, ...) are nowhere near any real
    font's `FirstChar..LastChar`.

    Deliberately does not read the embedded font program (Pitfall 5: the two may disagree,
    and the dictionary is what the viewer actually uses). Bounds-checks every code against
    FirstChar..LastChar explicitly -- an out-of-range code falling through to /MissingWidth
    (spec default 0) is "the single most spectacular naive-replacement failure" per Pitfall 5,
    and it is one missing bounds check away from happening silently.

    Takes an already-resolved font OBJECT rather than a path plus a resource name, so a
    caller that has resolved the font itself -- including from a Form XObject's own
    `/Resources`, which a page-level lookup cannot reach -- can measure without a second
    `pikepdf.open`. `read_original_advance_pt` below is the path-taking form.
    """
    if font.get("/Subtype") == pikepdf.Name("/Type0"):
        # D-14: Type0/CID width lookup via /W, reusing `engine.encoding_table.cid_width`
        # rather than reimplementing /W's run-length parsing (it already handles the
        # /DW default and malformed-array defensiveness). Identity-H is the only CMap
        # this reads through: code space IS CID space, so the code IS the CID.
        descendants = font.get("/DescendantFonts")
        if not descendants or len(descendants) == 0:
            raise ValueError("Type0 font has no usable /DescendantFonts entry")
        descendant_font = descendants[0]
        # /W and /DW cannot change within this measurement. Repeated characters
        # need one lookup each, rather than rescanning the same nested PDF arrays
        # for every glyph. Keep the sum in source-code order and discard the
        # cache at return, so later measurements observe any dictionary change.
        cid_widths = {code: cid_width(descendant_font, code) for code in set(codes)}
        return (
            sum(cid_widths[code] for code in codes)
            / 1000.0
            * font_size_pt
        )

    base_name = str(font.get("/BaseFont", "")).lstrip("/")
    if (font.get("/Widths") is None and font.get("/Subtype") == pikepdf.Name.Type1
            and base_name in STANDARD_14 - {"Symbol", "ZapfDingbats"}):
        # Standard Type1 fonts may omit /Widths; use the same Adobe AFM metrics
        # as the read engine, with the font's actual Encoding/Differences applied.
        metrics = core_font_widths(base_name)
        mapping = encoding_map(font)
        total = 0
        for code in codes:
            glyph_name = mapping.get(code)
            width = metrics.get(toUnicode(glyph_name)) if metrics is not None and glyph_name else None
            if width is None:
                raise ValueError("standard_font_code_has_no_metric")
            total += width
        return total / 1000.0 * font_size_pt

    first_char = int(font["/FirstChar"])
    last_char = int(font["/LastChar"])
    widths = font["/Widths"]
    total_thousandths = 0.0
    for code in codes:
        if not (first_char <= code <= last_char):
            # Content-free deviation from the spike: the numeric code and bounds only, no
            # character -- "no document content in exception text" (PROJECT.md's privacy
            # constraint), which the throwaway spike wasn't held to.
            raise ValueError(
                f"code {code} outside FirstChar..LastChar "
                f"({first_char}..{last_char}) -- refusing to fall through to "
                "/MissingWidth (spec default 0), see Pitfall 5"
            )
        index = code - first_char
        if index >= len(widths):
            # Hardening deviation from the spike: a /Widths array shorter than its own
            # declared FirstChar..LastChar range must refuse, not raise IndexError, for
            # an otherwise in-range code. Same content-free style as above.
            raise ValueError(
                f"code {code} is within FirstChar..LastChar ({first_char}..{last_char}) "
                f"but /Widths has only {len(widths)} entries -- refusing rather than "
                "indexing past the end of a malformed array"
            )
        total_thousandths += float(widths[index])
    return total_thousandths / 1000.0 * font_size_pt


def read_original_advance_pt(
    pdf_path: str | Path,
    page_index: int,
    font_resource_name: str,
    text: str,
    font_size_pt: float,
) -> float:
    """`advance_pt_for_codes` for a font named in a PAGE's own `/Resources /Font`, keyed by
    text rather than by codes.

    `ord(ch)` as the character code is a real simplification, correct only where the
    font's encoding agrees with Unicode over the text in question (plain ASCII under the
    usual Latin encodings). It is fine for a REPLACEMENT string a caller chose, and wrong
    for an ORIGINAL run's own text -- see `advance_pt_for_codes`'s note, and use it
    directly with `GlyphRecord.code` for that case.
    """
    with pikepdf.open(str(pdf_path)) as pdf:
        page = pdf.pages[page_index]
        font = page["/Resources"]["/Font"][font_resource_name]
        return advance_pt_for_codes(font, [ord(ch) for ch in text], font_size_pt)


def fit_run(
    original_advance_pt: float,
    replacement_text: str,
    font: str | Path | tuple[hb.Font, TTFont],
    font_size_pt: float,
) -> FitResult:
    # Normalised ONCE here rather than twice below: an already-loaded pair passes through
    # untouched, and a path is resolved through `_load_font`'s cache exactly as before.
    resolved_font = _as_font(font)
    shaped = shape_advance_pt(replacement_text, resolved_font, font_size_pt)
    delta = shaped - original_advance_pt
    space_w = space_width_pt(resolved_font, font_size_pt)

    # Priority 1: a single trailing TJ kern absorbs everything within ~1 space width.
    if abs(delta) <= space_w:
        kern = delta / font_size_pt * 1000.0
        kerns = [kern]
        final_advance = total_advance_with_kerns(shaped, kerns, font_size_pt)
        return FitResult(
            original_advance_pt,
            shaped,
            final_advance - original_advance_pt,
            "trailing_kern",
            kerns,
        )

    # Priority 2: distribute across inter-word kerns already present in the run.
    gap_count = replacement_text.count(" ")
    multiplier = _INTER_WORD_TIGHTEN_MULTIPLIER if delta > 0 else _INTER_WORD_ABSORB_MULTIPLIER
    max_inter_word_absorb = gap_count * space_w * multiplier
    if gap_count > 0 and abs(delta) <= max_inter_word_absorb:
        per_gap_kern = (delta / gap_count) / font_size_pt * 1000.0
        kerns = [per_gap_kern] * gap_count
        final_advance = total_advance_with_kerns(shaped, kerns, font_size_pt)
        return FitResult(
            original_advance_pt,
            shaped,
            final_advance - original_advance_pt,
            "inter_word_kern",
            kerns,
        )

    # Large underflow leaves blank space AFTER the replacement. A terminal negative
    # TJ adjustment advances the next text operator to the original endpoint; unlike
    # inter-word widening, it cannot deform the replacement's visible spacing.
    if delta < 0:
        kerns = [delta / font_size_pt * 1000.0]
        final_advance = total_advance_with_kerns(shaped, kerns, font_size_pt)
        return FitResult(
            original_advance_pt,
            shaped,
            final_advance - original_advance_pt,
            "trailing_kern",
            kerns,
        )

    # Priority 3: Tz horizontal-scale condensing -- only when the replacement is longer than the
    # original (delta > 0, condensing only, never widening per D-02) and never stacked with
    # inter-word kern distribution (D-01: first rung that fits wins, tried against the FULL
    # original delta, not a residual left over from a failed inter-word attempt).
    required_scale_percent = None
    if delta > 0:
        required_scale_percent = (original_advance_pt / shaped) * 100.0
        if required_scale_percent >= TZ_FLOOR_PERCENT:
            condensed_advance = shaped * (required_scale_percent / 100.0)
            return FitResult(
                original_advance_pt,
                shaped,
                condensed_advance - original_advance_pt,
                "tz",
                [],
                condensed_scale=required_scale_percent,
                original_scale_to_restore=100.0,
            )

    # Priority 4: refuse honestly instead of guessing.
    reason = (
        f"delta {delta:.2f}pt exceeds trailing-kern (+/-{space_w:.2f}pt) and inter-word-kern "
        f"(+/-{max_inter_word_absorb:.2f}pt over {gap_count} gaps) absorption range"
    )
    if required_scale_percent is not None:
        reason += (
            f"; Tz condensing would require {required_scale_percent:.2f}%, below the "
            f"{TZ_FLOOR_PERCENT:.1f}% floor"
        )
    return FitResult(
        original_advance_pt, shaped, delta, "refused", [], refused=True, refusal_reason=reason
    )


__all__ = [
    "FitResult",
    "TZ_FLOOR_PERCENT",
    "advance_pt_for_codes",
    "fit_run",
    "kern_to_displacement_pt",
    "load_font",
    "read_original_advance_pt",
    "shape_advance_pt",
    "space_width_pt",
    "total_advance_with_kerns",
]
