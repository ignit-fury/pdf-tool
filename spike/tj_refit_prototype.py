"""TJ-refit width-fitting prototype.

THROWAWAY SPIKE CODE. Per `.planning/phases/01-conformance-harness-engine-spike/01-CONTEXT.md`
("Claude's Discretion" -> Spike code disposition), this module is judged only on whether it
answers one question: can replacement text be fitted into an original text run's advance width
within |delta_pt| < 0.5pt, using the TJ kern-absorption strategy, in both the "replacement is
shorter" and "replacement is longer" directions? The tests in
`tests/test_tj_refit_prototype.py` and the fixture PDF are NOT throwaway -- see
`TJ-REFIT-RESULTS.md` for why they carry forward into Phase 3.

Algorithm, priority-ordered (research/PITFALLS.md, Pitfall 5 "Naive replacement wrecks advance
widths"):
  1. Shape the replacement text with uharfbuzz's `hb.shape()` to get its *kerned* total advance
     (fontTools' `hmtx` table only gives unkerned advances -- the delta between kerned and
     unkerned advance is literally the number that goes in the TJ array).
  2. Compute delta_pt = shaped_advance_pt - original_advance_pt.
  3. If |delta_pt| fits within roughly one space-glyph width, absorb it entirely in a single
     trailing TJ kern number. Cheapest, invisible, and exactly correct for what follows on the
     line.
  4. Otherwise, distribute the delta evenly across the inter-word kerns already present in the
     run (bounded absorption range -- see `_INTER_WORD_ABSORB_MULTIPLIER` below).
  5. Otherwise, refuse. Tz (horizontal scale) and the "must grow with content immediately
     after it" refusal ladder are explicitly out of scope for this prototype (plan 01-06
     <behavior>) -- refusing honestly here is the point (phase_critical_constraint #5: a
     confident wrong fit is the failure mode being guarded against, not an acceptable shortcut).

TJ sign convention (load-bearing -- get this backwards and the fix doubles the error instead of
cancelling it): a TJ array number K is expressed in thousandths of text space and is SUBTRACTED
from the advance, scaled by font size:

    displacement_pt = -(K / 1000) * font_size_pt

So a POSITIVE K tightens (reduces total advance, moves the next glyph left); a NEGATIVE K widens
it. `kern_to_displacement_pt` and the sign-convention test in the test file exist specifically to
pin this down.

Deviation from the plan's literal action text: the plan's action item 1 says to read the
original run's `/Widths`/`/W` array "via fontTools". fontTools parses font *program* files
(glyf/CFF/Type1), not PDF dictionary objects -- it has no API for a PDF's `/Widths` array. Per
Pitfall 5, the width that actually governs rendering is the PDF font DICTIONARY's `/Widths`
entry, not the embedded font program's own metrics (the two are allowed to disagree). This
module therefore reads `/Widths` via `pikepdf` (already the project's PDF object-layer library),
and reserves fontTools/uharfbuzz for what they are actually for: shaping the replacement text.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pikepdf
import uharfbuzz as hb

# "Roughly one space width" per Pitfall 5's priority-ordered absorption strategy -- the natural
# threshold below which a single trailing TJ kern looks invisible rather than like a gap.
_INTER_WORD_ABSORB_MULTIPLIER = 2.0


@dataclasses.dataclass
class FitResult:
    original_advance_pt: float
    replacement_shaped_advance_pt: float  # unfit, before any kern is applied
    delta_pt: float  # residual after fitting (== shaped - original, unfit if refused)
    strategy: str  # "trailing_kern" | "inter_word_kern" | "refused"
    kerns: list[float]  # TJ kern numbers applied, in thousandths of text space
    refused: bool = False
    refusal_reason: str | None = None


def _load_font(font_path: str | Path) -> hb.Font:
    blob = hb.Blob.from_file_path(str(font_path))
    face = hb.Face(blob)
    return hb.Font(face), face.upem


def shape_advance_pt(text: str, font_path: str | Path, font_size_pt: float) -> float:
    """Shape `text` with uharfbuzz and return its total *kerned* advance, in points."""
    font, upem = _load_font(font_path)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf)
    total_units = sum(pos.x_advance for pos in buf.glyph_positions)
    return total_units / upem * font_size_pt


def space_width_pt(font_path: str | Path, font_size_pt: float) -> float:
    return shape_advance_pt(" ", font_path, font_size_pt)


def kern_to_displacement_pt(kern: float, font_size_pt: float) -> float:
    """TJ sign convention: the kern number is SUBTRACTED, in thousandths of text space."""
    return -(kern / 1000.0) * font_size_pt


def total_advance_with_kerns(
    shaped_advance_pt: float, kerns: list[float], font_size_pt: float
) -> float:
    return shaped_advance_pt + sum(
        kern_to_displacement_pt(k, font_size_pt) for k in kerns
    )


def read_original_advance_pt(
    pdf_path: str | Path,
    page_index: int,
    font_resource_name: str,
    text: str,
    font_size_pt: float,
) -> float:
    """Read the original run's advance from the PDF font DICTIONARY's /Widths array.

    Deliberately does not read the embedded font program (Pitfall 5: the two may disagree,
    and the dictionary is what the viewer actually uses). Bounds-checks every code against
    FirstChar..LastChar explicitly -- an out-of-range code falling through to /MissingWidth
    (spec default 0) is "the single most spectacular naive-replacement failure" per Pitfall 5,
    and it is one missing bounds check away from happening silently.
    """
    with pikepdf.open(str(pdf_path)) as pdf:
        page = pdf.pages[page_index]
        font = page["/Resources"]["/Font"][font_resource_name]
        if font.get("/Subtype") == pikepdf.Name("/Type0"):
            raise NotImplementedError(
                "Type0/CID width lookup (/W, /DW) is out of scope for this prototype -- "
                "route Type0 fonts through a separate width function per Pitfall 3, never "
                "this /Widths-based one."
            )
        first_char = int(font["/FirstChar"])
        last_char = int(font["/LastChar"])
        widths = font["/Widths"]
        total_thousandths = 0.0
        for ch in text:
            code = ord(ch)
            if not (first_char <= code <= last_char):
                raise ValueError(
                    f"code {code!r} ({ch!r}) outside FirstChar..LastChar "
                    f"({first_char}..{last_char}) -- refusing to fall through to "
                    "/MissingWidth (spec default 0), see Pitfall 5"
                )
            total_thousandths += float(widths[code - first_char])
        return total_thousandths / 1000.0 * font_size_pt


def fit_run(
    original_advance_pt: float,
    replacement_text: str,
    font_path: str | Path,
    font_size_pt: float,
) -> FitResult:
    shaped = shape_advance_pt(replacement_text, font_path, font_size_pt)
    delta = shaped - original_advance_pt
    space_w = space_width_pt(font_path, font_size_pt)

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
    max_inter_word_absorb = gap_count * space_w * _INTER_WORD_ABSORB_MULTIPLIER
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

    # Priority 3+ (Tz scale, refuse-if-content-follows) are out of scope for this prototype
    # (plan 01-06 <behavior>) -- refuse honestly instead of guessing.
    reason = (
        f"delta {delta:.2f}pt exceeds trailing-kern (+/-{space_w:.2f}pt) and inter-word-kern "
        f"(+/-{max_inter_word_absorb:.2f}pt over {gap_count} gaps) absorption range; "
        "Tz/refuse-ladder is out of scope for this prototype"
    )
    return FitResult(
        original_advance_pt, shaped, delta, "refused", [], refused=True, refusal_reason=reason
    )


if __name__ == "__main__":
    # ponytail: runnable demo, doubles as the source of the numbers in TJ-REFIT-RESULTS.md.
    fixtures = Path(__file__).parent / "fixtures"
    sample_pdf = fixtures / "tj_refit_sample.pdf"
    font = fixtures / "LiberationSans-Regular.ttf"

    original_text = "Request for Taxpayer "
    font_size = 14.0
    original_advance = read_original_advance_pt(sample_pdf, 0, "/T1_2", original_text, font_size)
    print(f"Original run: {original_text!r} @ {font_size}pt -> {original_advance:.3f}pt")

    for label, replacement in [
        ("shorter", "Request Payer Tax ID"),
        ("longer", "Ask for Taxpayer Data "),
    ]:
        result = fit_run(original_advance, replacement, font, font_size)
        print(
            f"{label}: {replacement!r} shaped={result.replacement_shaped_advance_pt:.3f}pt "
            f"strategy={result.strategy} kerns={result.kerns} "
            f"delta_pt={result.delta_pt:.4f} refused={result.refused}"
        )
