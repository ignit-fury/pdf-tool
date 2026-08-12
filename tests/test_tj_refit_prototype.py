"""Tests for the TJ-refit width-fitting prototype (spike/tj_refit_prototype.py).

NOT throwaway: these test cases and their measured numbers are Phase 3's seed acceptance
fixtures. See `.planning/phases/01-conformance-harness-engine-spike/TJ-REFIT-RESULTS.md`.

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

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from spike.tj_refit_prototype import (  # noqa: E402
    fit_run,
    kern_to_displacement_pt,
    read_original_advance_pt,
    total_advance_with_kerns,
)

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


def test_inter_word_kern_distribution_for_larger_delta(original_advance_pt: float) -> None:
    # Delta here (~26pt) exceeds one space width but is within the inter-word absorption
    # range -- exercises priority-2 of the absorption strategy, not just the trailing kern.
    result = fit_run(original_advance_pt, "Request for Taxpayer Info ", FONT, FONT_SIZE_PT)
    assert not result.refused
    assert result.strategy == "inter_word_kern"
    assert len(result.kerns) > 1
    assert abs(result.delta_pt) < 0.5


def test_refuses_rather_than_guesses_when_delta_is_too_large(
    original_advance_pt: float,
) -> None:
    # "X" is drastically shorter than the original run -- no honest kern-only fit exists.
    result = fit_run(original_advance_pt, "X", FONT, FONT_SIZE_PT)
    assert result.refused
    assert result.refusal_reason is not None
    assert result.strategy == "refused"


def test_out_of_range_code_refuses_instead_of_falling_through_to_missing_width() -> None:
    # Pitfall 5's "single most spectacular naive-replacement failure": a code outside
    # FirstChar..LastChar silently falls through to /MissingWidth (spec default 0) in a naive
    # implementation, stacking every subsequent glyph at the same x. This must raise, not
    # silently return 0. "—" (U+2014) is far outside this font's 0..255 range.
    with pytest.raises(ValueError):
        read_original_advance_pt(
            SAMPLE_PDF, 0, ORIGINAL_FONT_RESOURCE, "—", FONT_SIZE_PT
        )
