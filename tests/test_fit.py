"""Tests for the TJ-refit width-fitting engine (engine/fit.py).

Ported verbatim from `tests/test_tj_refit_prototype.py` (Phase 1 spike) -- same fixture PDF,
same fixture font, same expected numbers. See
`.planning/phases/01-conformance-harness-engine-spike/TJ-REFIT-RESULTS.md`.

Fixture: `spike/fixtures/tj_refit_sample.pdf` (IRS Form W-9, public domain, U.S. Government
Work). The hand-picked run is "Request for Taxpayer " on page 0, font resource `/T1_2`
(`MCXSQA+ITCFranklinGothicStd-Demi`, a Type1 subset) at 14pt, whose original advance is read
from the PDF's own `/Widths` dictionary array (137.76pt) -- per Pitfall 5, the dictionary is
what the viewer actually uses, not the embedded font program's own metrics. Replacement text is
shaped against `spike/fixtures/LiberationSans-Regular.ttf` (SIL OFL 1.1), the font family this
project has already committed to bundling (PROJECT.md), simulating the bundled-font-substitution
path (Pitfall 4's default case) rather than assuming glyph availability in the original subset.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pikepdf
import pytest
import uharfbuzz as hb
from fontTools.ttLib import TTFont

from engine.encoding_table import cid_width
from engine.fit import (
    _load_font,  # noqa: private -- cache-identity test below needs the raw function
    fit_run,
    kern_to_displacement_pt,
    read_original_advance_pt,
    shape_advance_pt,
    space_width_pt,
    total_advance_with_kerns,
)

REPO_ROOT = Path(__file__).parent.parent
FIXTURES = REPO_ROOT / "spike" / "fixtures"
SAMPLE_PDF = FIXTURES / "tj_refit_sample.pdf"
FONT = FIXTURES / "LiberationSans-Regular.ttf"
FONT_SIZE_PT = 14.0
ORIGINAL_TEXT = "Request for Taxpayer "
ORIGINAL_FONT_RESOURCE = "/T1_2"


@pytest.fixture(scope="module")
def original_advance_pt() -> float:
    return read_original_advance_pt(
        SAMPLE_PDF, 0, ORIGINAL_FONT_RESOURCE, ORIGINAL_TEXT, FONT_SIZE_PT
    )


def test_original_advance_matches_pdf_widths(original_advance_pt: float) -> None:
    # Sanity check on the fixture itself: 21 chars of ITCFranklinGothicStd-Demi /Widths at 14pt.
    assert original_advance_pt == pytest.approx(137.76, abs=0.01)


def test_shorter_replacement_fits_within_threshold(original_advance_pt: float) -> None:
    result = fit_run(original_advance_pt, "Request Payer Tax ID", FONT, FONT_SIZE_PT)
    assert not result.refused
    assert result.replacement_shaped_advance_pt < original_advance_pt
    assert abs(result.delta_pt) < 0.5


def test_longer_replacement_fits_within_threshold(original_advance_pt: float) -> None:
    result = fit_run(original_advance_pt, "Ask for Taxpayer Data ", FONT, FONT_SIZE_PT)
    assert not result.refused
    assert result.replacement_shaped_advance_pt > original_advance_pt
    assert abs(result.delta_pt) < 0.5


def test_sign_convention_positive_kern_tightens_advance() -> None:
    shaped = 100.0
    zero_kern_advance = total_advance_with_kerns(shaped, [0.0], FONT_SIZE_PT)
    positive_kern_advance = total_advance_with_kerns(shaped, [50.0], FONT_SIZE_PT)
    negative_kern_advance = total_advance_with_kerns(shaped, [-50.0], FONT_SIZE_PT)

    assert positive_kern_advance < zero_kern_advance, (
        "a positive TJ kern must tighten (reduce) the computed advance, never widen it"
    )
    assert negative_kern_advance > zero_kern_advance, (
        "a negative TJ kern must widen (increase) the computed advance"
    )
    # Direct formula check: kern is in thousandths of text space, scaled by font size.
    assert kern_to_displacement_pt(50.0, FONT_SIZE_PT) == pytest.approx(-0.7)
    assert kern_to_displacement_pt(-50.0, FONT_SIZE_PT) == pytest.approx(0.7)


def test_inter_word_kern_distribution_for_larger_delta() -> None:
    # Widening across several gaps is safe; it cannot consume a word space.
    text = 'Request for Taxpayer Info '
    original = shape_advance_pt(text, FONT, FONT_SIZE_PT) + 1.5 * space_width_pt(FONT, FONT_SIZE_PT)
    result = fit_run(original, text, FONT, FONT_SIZE_PT)
    assert not result.refused
    assert result.strategy == "inter_word_kern"
    assert len(result.kerns) > 1
    assert abs(result.delta_pt) < 0.5


def test_former_inter_word_fit_refuses_reversed_word_spaces(original_advance_pt: float) -> None:
    # The historical positive ~28pt delta consumed more than a whole space at
    # every gap. Its ~83% required scale is below the preservation floor.
    result = fit_run(original_advance_pt, 'Request for Taxpayer Info ', FONT, FONT_SIZE_PT)
    assert result.refused
    assert result.refusal_reason is not None


def test_tightening_never_consumes_or_reverses_the_word_space() -> None:
    font = Path(__file__).resolve().parents[1] / 'fonts/LiberationSans-Bold.ttf'
    text = 'Hallo world'
    shaped = shape_advance_pt(text, font, 12)
    result = fit_run(shaped * 0.93, text, font, 12)
    assert not result.refused
    assert result.strategy == 'tz'
    assert result.condensed_scale == pytest.approx(93)


def test_very_short_replacement_leaves_unused_space_after_text(
    original_advance_pt: float,
) -> None:
    # A terminal adjustment fills the unused advance without stretching the glyph.
    result = fit_run(original_advance_pt, "X", FONT, FONT_SIZE_PT)
    assert not result.refused
    assert result.strategy == "trailing_kern"
    assert len(result.kerns) == 1
    assert result.kerns[0] < 0
    assert result.condensed_scale is None
    assert total_advance_with_kerns(
        result.replacement_shaped_advance_pt, result.kerns, FONT_SIZE_PT
    ) == pytest.approx(original_advance_pt)


def test_tz_condensing_restores_scale_after_run() -> None:
    # Zero-space single word: gap_count == 0 makes inter_word_kern structurally unreachable
    # regardless of delta size, isolating priority 3 (Tz condensing) from priority 2. Original
    # advance is derived algebraically as 93% of the replacement's shaped advance -- comfortably
    # inside the 90-95% band and above TZ_FLOOR_PERCENT -- so the test is deterministic without
    # hardcoding the shaped advance's absolute value.
    replacement = "extraordinarily"
    shaped = shape_advance_pt(replacement, FONT, FONT_SIZE_PT)
    space_w = space_width_pt(FONT, FONT_SIZE_PT)
    assert shaped * 0.07 > space_w, "fixture word must exceed the trailing-kern absorption range"

    original = shaped * 0.93
    result = fit_run(original, replacement, FONT, FONT_SIZE_PT)

    assert not result.refused
    assert result.strategy == "tz"
    assert result.condensed_scale == pytest.approx(93.0)
    assert result.original_scale_to_restore == pytest.approx(100.0)
    assert abs(result.delta_pt) < 0.01


def test_tz_refuses_below_ninety_percent_floor() -> None:
    # Same zero-space fixture, but the original advance now requires ~80% condensing --
    # below TZ_FLOOR_PERCENT, so the ladder must refuse rather than deform glyphs past the floor.
    replacement = "extraordinarily"
    shaped = shape_advance_pt(replacement, FONT, FONT_SIZE_PT)
    space_w = space_width_pt(FONT, FONT_SIZE_PT)
    assert shaped * 0.20 > space_w, "fixture word must exceed the trailing-kern absorption range"

    original = shaped * 0.80
    result = fit_run(original, replacement, FONT, FONT_SIZE_PT)

    assert result.refused
    assert result.strategy == "refused"
    assert result.refusal_reason is not None


def test_shape_advance_pt_uses_unkerned_widths_not_gpos_kerning() -> None:
    # Regression: `shape_advance_pt` used to return harfbuzz's `pos.x_advance` sum, which
    # folds in the font's GPOS pairwise kerning. A PDF `Tj`/`TJ` never applies the embedded
    # font program's kerning -- glyph displacement comes entirely from the font dictionary's
    # /Widths (or /W) array, which is the unkerned per-glyph advance. Fitting against the
    # kerned number therefore mis-sized every replacement by exactly the kerning amount.
    #
    # "VAV To Wave Yes" is chosen for its density of real GPOS kern pairs in LiberationSans
    # (VA, AV, To, Wa, av, Ye) -- 5.94pt of kerning at 14pt, far above any rounding noise.
    text = "VAV To Wave Yes"

    face = hb.Face(hb.Blob.from_file_path(str(FONT)))
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hb.Font(face), buf)

    # Oracle 1 (what shape_advance_pt must now return): each shaped glyph's OWN hmtx advance.
    ttfont = TTFont(str(FONT))
    upem = ttfont["head"].unitsPerEm
    unkerned_pt = (
        sum(ttfont["hmtx"][ttfont.getGlyphName(i.codepoint)][0] for i in buf.glyph_infos)
        / upem
        * FONT_SIZE_PT
    )
    # Oracle 2 (what the old buggy implementation returned): harfbuzz's kerned positioning.
    kerned_pt = sum(p.x_advance for p in buf.glyph_positions) / upem * FONT_SIZE_PT

    assert kerned_pt < unkerned_pt - 1.0, (
        "fixture text must actually exercise GPOS kerning, or this test proves nothing"
    )
    result = shape_advance_pt(text, FONT, FONT_SIZE_PT)
    assert result == pytest.approx(unkerned_pt, abs=1e-6)
    assert result != pytest.approx(kerned_pt, abs=1.0)


def test_out_of_range_code_refuses_instead_of_falling_through_to_missing_width() -> None:
    # Pitfall 5's "single most spectacular naive-replacement failure": a code outside
    # FirstChar..LastChar silently falls through to /MissingWidth (spec default 0) in a naive
    # implementation, stacking every subsequent glyph at the same x. This must raise, not
    # silently return 0. "—" (U+2014) is far outside this font's 0..255 range.
    with pytest.raises(ValueError):
        read_original_advance_pt(
            SAMPLE_PDF, 0, ORIGINAL_FONT_RESOURCE, "—", FONT_SIZE_PT
        )


# --- New tests for this task: Type0/CID /W path, malformed /Widths, content-free messages ---


def _pdf_with_font(font_dict: dict[str, object], resource_name: str) -> pikepdf.Pdf:
    """A minimal one-page PDF whose page resources expose `font_dict` under `resource_name`.
    Built in-memory, no fixture file -- same shape as tests/test_encoding_table.py's synthetic
    font helpers."""
    pdf = pikepdf.Pdf.new()
    page = pdf.add_blank_page(page_size=(200, 200))
    page.Contents = pdf.make_stream(b"")
    page.Resources = pikepdf.Dictionary(
        {"/Font": pikepdf.Dictionary({resource_name: pdf.make_indirect(pikepdf.Dictionary(font_dict))})}
    )
    return pdf


def test_type0_original_advance_reads_w_array_via_cid_width() -> None:
    # A synthetic Type0/CIDFontType2 font with a /W array covering the CIDs this text maps
    # to under Identity-H's code-space-is-CID-space simplification (ord(ch) as CID).
    text = "AB"  # ord('A')=65, ord('B')=66
    w_array = pikepdf.Array([65, pikepdf.Array([600, 650]), 100, 120, 700])
    descendant_dict: dict[str, object] = {
        "/Type": pikepdf.Name("/Font"),
        "/Subtype": pikepdf.Name("/CIDFontType2"),
        "/CIDToGIDMap": pikepdf.Name("/Identity"),
        "/DW": 1000,
        "/W": w_array,
    }
    pdf = pikepdf.Pdf.new()
    page = pdf.add_blank_page(page_size=(200, 200))
    page.Contents = pdf.make_stream(b"")
    descendant = pdf.make_indirect(pikepdf.Dictionary(descendant_dict))
    font_dict = pikepdf.Dictionary(
        {
            "/Type": pikepdf.Name("/Font"),
            "/Subtype": pikepdf.Name("/Type0"),
            "/Encoding": pikepdf.Name("/Identity-H"),
            "/DescendantFonts": pikepdf.Array([descendant]),
        }
    )
    page.Resources = pikepdf.Dictionary(
        {"/Font": pikepdf.Dictionary({"/T0_1": pdf.make_indirect(font_dict)})}
    )

    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        pdf.save(tmp.name)
        pdf.close()

        result = read_original_advance_pt(tmp.name, 0, "/T0_1", text, FONT_SIZE_PT)

        # Independently reopen and sum cid_width() directly for the same CIDs -- must match.
        with pikepdf.open(tmp.name) as reopened:
            reopened_descendant = reopened.pages[0]["/Resources"]["/Font"]["/T0_1"][
                "/DescendantFonts"
            ][0]
            expected_thousandths = sum(cid_width(reopened_descendant, ord(ch)) for ch in text)
            expected_pt = expected_thousandths / 1000.0 * FONT_SIZE_PT

        assert result == pytest.approx(expected_pt)


def test_malformed_widths_array_shorter_than_declared_refuses() -> None:
    # /FirstChar..LastChar promises 3 widths (codes 65..67) but /Widths has only 2 entries --
    # code 67 is in-range per FirstChar/LastChar but out-of-range for the array itself. Must
    # raise ValueError (refuse), never IndexError.
    font_dict: dict[str, object] = {
        "/Type": pikepdf.Name("/Font"),
        "/Subtype": pikepdf.Name("/Type1"),
        "/FirstChar": 65,
        "/LastChar": 67,
        "/Widths": pikepdf.Array([600, 600]),
    }
    pdf = _pdf_with_font(font_dict, "/T1_1")
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        pdf.save(tmp.name)
        pdf.close()
        with pytest.raises(ValueError) as excinfo:
            read_original_advance_pt(tmp.name, 0, "/T1_1", "C", FONT_SIZE_PT)
        assert "IndexError" not in type(excinfo.value).__name__


def test_widths_refusal_messages_omit_decoded_character() -> None:
    # Both refusal paths must name the numeric code, never the literal decoded character
    # (project's "no document content in exception text" rule).
    out_of_range_font: dict[str, object] = {
        "/Type": pikepdf.Name("/Font"),
        "/Subtype": pikepdf.Name("/Type1"),
        "/FirstChar": 65,
        "/LastChar": 70,
        "/Widths": pikepdf.Array([600] * 6),
    }
    pdf1 = _pdf_with_font(out_of_range_font, "/T1_1")
    secret_char = "あ"  # far outside 65..70
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        pdf1.save(tmp.name)
        pdf1.close()
        with pytest.raises(ValueError) as excinfo:
            read_original_advance_pt(tmp.name, 0, "/T1_1", secret_char, FONT_SIZE_PT)
        message = str(excinfo.value)
        assert str(ord(secret_char)) in message
        assert secret_char not in message

    # "Ω" (U+03A9) chosen specifically so its glyph shares no substring with the message
    # wording below (unlike e.g. "C", which collides with "FirstChar"/"LastChar") -- a
    # clean test of "the character itself never appears," not an accident of spelling.
    malformed_char = "Ω"
    code = ord(malformed_char)
    malformed_font: dict[str, object] = {
        "/Type": pikepdf.Name("/Font"),
        "/Subtype": pikepdf.Name("/Type1"),
        "/FirstChar": code - 5,
        "/LastChar": code + 5,
        "/Widths": pikepdf.Array([600] * 3),  # promises 11 entries, has 3
    }
    pdf2 = _pdf_with_font(malformed_font, "/T1_1")
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        pdf2.save(tmp.name)
        pdf2.close()
        with pytest.raises(ValueError) as excinfo:
            read_original_advance_pt(tmp.name, 0, "/T1_1", malformed_char, FONT_SIZE_PT)
        message = str(excinfo.value)
        assert str(code) in message
        assert malformed_char not in message


def test_load_font_is_cached() -> None:
    # `_load_font` is decorated with `functools.lru_cache` (same precedent as
    # `engine.fonts._liberation_ttfont`) because it re-parses the font file from scratch on
    # every call and `fit_run` calls it twice per run (once directly, once via
    # `space_width_pt`). Prove the cache actually returns the SAME objects rather than
    # trusting the decorator is doing anything -- identity, not just equal values, since a
    # second parse of the same file would produce equal-but-distinct `hb.Font`/`TTFont`
    # instances.
    hb_font_1, ttfont_1 = _load_font(FONT)
    hb_font_2, ttfont_2 = _load_font(FONT)
    assert hb_font_1 is hb_font_2
    assert ttfont_1 is ttfont_2
