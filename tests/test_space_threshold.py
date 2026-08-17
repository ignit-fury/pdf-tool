"""D-03: the synthetic-space threshold is measured, not guessed.

Pitfall 1 is the whole point of this file. `gstate.fontsize` is frequently 1.0 on real
documents, with the true size living in the text matrix. Using it does not crash and does
not look wrong -- it produces a plausible tuned threshold from a correct-looking sweep that
happens to be meaningless. 02-RESEARCH.md calls that "the single easiest way to produce a
green-but-wrong tuning run", so the mutation test below is the deliverable, not a
formality.
"""

import json
import math
from pathlib import Path

import playa
import pytest

from engine.playa_boundary import GlyphObject, TextObject
from engine.space_threshold import (
    BREAK_EM,
    K_EM,
    KNOWN_UNWALKABLE,
    effective_em,
    held_out_space_gaps,
    page_gaps,
    sweep,
    tune_threshold,
)

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"
MANIFEST = REPO_ROOT / "corpus" / "manifest.json"

# [VERIFIED: measured 2026-08-14] the full-corpus tuning run recorded in
# engine/space_threshold.py's constants block. Reproduced by the determinism test below.
MEASURED_F1 = 0.9795
MEASURED_PRECISION = 0.9820
MEASURED_RECALL = 0.9770
MEASURED_ARGMAX = 0.100


def _first_text_object(page: object) -> TextObject:
    for item in page:  # type: ignore[attr-defined]
        if isinstance(item, TextObject):
            return item
    raise AssertionError("page has no TextObject")


# --------------------------------------------------------------------------------------
# Pitfall 1 -- effective_em is not gstate.fontsize
# --------------------------------------------------------------------------------------


def test_effective_em_is_not_gstate_fontsize() -> None:
    """The named example. `irs_form_w9.pdf` page 0's first text object reports
    gstate.fontsize == 1.0 while its real em is 7.0 -- a factor of 7.

    MUTATION: `return text_obj.size` -> `return text_obj.gstate.fontsize` collapses this
    to 1.0. Run and confirmed red. The F1 half of that mutation is the corpus test below;
    both halves matter, because a wrong em that happened to preserve F1 would not be a bug.
    """
    with playa.open(str(CORPUS_DIR / "irs_form_w9.pdf")) as doc:
        text_obj = _first_text_object(doc.pages[0])
        assert text_obj.gstate.fontsize == pytest.approx(1.0)
        assert effective_em(text_obj) == pytest.approx(7.0, abs=0.01)


def test_effective_em_reports_true_size_on_known_12pt() -> None:
    """Assumption A5, the other direction: where gstate.fontsize genuinely IS the size,
    effective_em must agree with it rather than diverge.

    Guards against "fix" the mutation by scaling the matrix -- a formulation that reports
    7.0 on the w9 but 144.0 on a real 12pt run would pass the test above and fail here.
    That is not hypothetical: 02-RESEARCH.md's own code snippet multiplies the matrix norm
    by gstate.fontsize, but playa's matrix ALREADY contains fontsize, so the snippet
    returns 144.0 on a 12pt run. See effective_em's DEVIATION note.
    """
    with playa.open(str(CORPUS_DIR / "irs_publication_17.pdf")) as doc:
        sizes = set()
        for page in list(doc.pages)[:3]:
            for item in page:
                if isinstance(item, TextObject) and item.gstate.fontsize == 12.0:
                    sizes.add(round(effective_em(item), 3))
        assert sizes, "expected at least one text object with gstate.fontsize == 12.0"
        assert sizes == {12.0}, f"a known 12pt run reported {sorted(sizes)}, not 12.0"


def test_held_out_gaps_label_real_spaces_positive() -> None:
    """The self-supervision itself: a drawn space glyph yields a True-labelled gap, and
    adjacent non-space pairs yield False-labelled ones.

    MUTATION: dropping the `glyphs[i - 1].text != " "` guard on the negative branch labels
    the gap *after* a space as intra-word, poisoning the negative population with real
    word gaps and dragging the argmax upward.
    """
    with playa.open(str(CORPUS_DIR / "irs_form_w9.pdf")) as doc:
        pairs = list(page_gaps(doc.pages[0], doc))

    assert pairs, "expected held-out gaps on w9 page 0"
    positives = [g for g, is_boundary in pairs if is_boundary]
    negatives = [g for g, is_boundary in pairs if not is_boundary]
    assert positives and negatives
    # The separation the whole method rests on: real word gaps are wider than intra-word.
    assert sum(positives) / len(positives) > sum(negatives) / len(negatives)


# --------------------------------------------------------------------------------------
# The pinned constants
# --------------------------------------------------------------------------------------


def test_pinned_constants_are_the_recorded_values() -> None:
    """K_EM and BREAK_EM are measurements, and this project treats recorded measurements as
    deliverables. Changing either without re-running the sweep must break a test."""
    assert K_EM == pytest.approx(MEASURED_ARGMAX)
    assert BREAK_EM == pytest.approx(0.33)
    # BREAK_EM separates runs, K_EM separates words: they must not collapse together.
    assert BREAK_EM > K_EM


@pytest.mark.corpus
def test_pinned_threshold_reproduces_measured_f1() -> None:
    """Determinism: re-running the sweep reproduces its own recorded numbers.

    This is the check that makes the constants block trustworthy rather than decorative --
    a docstring citing an F1 nobody can reproduce is exactly the "recorded measurement that
    disagrees with what the code computes" defect this phase already caught once.

    MUTATION: any change to effective_em, held_out_space_gaps' labelling, or the sweep
    arithmetic moves these numbers outside tolerance.
    """
    result = tune_threshold(json.loads(MANIFEST.read_text()))

    assert result.k_em == pytest.approx(MEASURED_ARGMAX)
    assert result.f1 == pytest.approx(MEASURED_F1, abs=0.001)
    assert result.precision == pytest.approx(MEASURED_PRECISION, abs=0.001)
    assert result.recall == pytest.approx(MEASURED_RECALL, abs=0.001)
    # BREAK_EM is the negative p999 rounded up; pin the relationship, not just the value.
    assert result.negative_p999 <= BREAK_EM
    assert result.break_em == pytest.approx(BREAK_EM, abs=0.005)
    # Populations, so a corpus that silently shrank cannot pass on a handful of gaps.
    assert result.n_positive > 90_000
    assert result.n_negative > 550_000
    assert result.n_documents >= 215


@pytest.mark.corpus
def test_pitfall_1_fontsize_em_displaces_the_argmax() -> None:
    """The other half of the Pitfall-1 mutation, asserted as it actually behaves.

    THE PLAN'S ACCEPTANCE CRITERION IS WRONG HERE, and this is the corrected form.
    02-07-PLAN.md says the fontsize mutation "pushes F1 below the pinned bound". Measured
    over the full corpus, it does not: real-em peaks at F1 0.8734 and fontsize-em at
    0.8623, a difference of 0.011. An F1 assertion would have been a coin-flip guard.

    What the mutation actually does is DISPLACE THE ARGMAX, 0.10 -> 0.23. That is the real
    damage and it is worse than a slightly-worse curve: tuning with a fontsize em pins
    K_EM at 0.23, and 0.23 then gets applied to correctly-computed em gaps in production,
    where it under-detects word boundaries badly (from the recorded full-corpus curve:
    recall 0.977 at 0.10 versus 0.884 at 0.23).

    Why F1 survives: dividing every gap in ONE text object by a constant preserves that
    object's separability, so the curve only degrades where the em/fontsize ratio VARIES
    between objects. It varies plenty -- 408 distinct ratios across the corpus, from 0.06
    to 2.12 -- but pooled F1 absorbs it while the optimum shifts.

    MUTATION: `return text_obj.size` -> `return text_obj.gstate.fontsize` in effective_em.
    Run and confirmed: argmax moves 0.10 -> 0.23.
    """
    manifest = json.loads(MANIFEST.read_text())
    thresholds = [round(0.005 * i, 4) for i in range(1, 201)]

    real_pos: list[float] = []
    real_neg: list[float] = []
    fs_pos: list[float] = []
    fs_neg: list[float] = []

    for entry in manifest:
        name = entry["filename"]
        if name in KNOWN_UNWALKABLE:
            continue
        path = CORPUS_DIR / name
        if not path.exists():
            continue
        with playa.open(str(path)) as doc:
            for page in list(doc.pages)[:2]:
                for item in page:
                    if not isinstance(item, TextObject):
                        continue
                    em = effective_em(item)
                    if em > 0.0 and math.isfinite(em):
                        for gap, is_boundary in held_out_space_gaps(item, em):
                            (real_pos if is_boundary else real_neg).append(gap)
                    # THE MUTATION, applied to data rather than to source.
                    fontsize_em = item.gstate.fontsize
                    if fontsize_em > 0.0 and math.isfinite(fontsize_em):
                        for gap, is_boundary in held_out_space_gaps(item, fontsize_em):
                            (fs_pos if is_boundary else fs_neg).append(gap)

    assert real_pos and real_neg and fs_pos and fs_neg

    best_real = max(sweep(real_pos, real_neg, thresholds), key=lambda p: p.f1)
    best_fs = max(sweep(fs_pos, fs_neg, thresholds), key=lambda p: p.f1)

    # The real em's optimum agrees with the pinned constant. If this drifts, K_EM is stale.
    assert best_real.threshold == pytest.approx(K_EM, abs=0.005)
    # The mutation's optimum does not. This is the guard.
    assert best_fs.threshold > K_EM * 1.5, (
        f"fontsize-em argmax {best_fs.threshold} did not displace from K_EM {K_EM} -- the "
        f"Pitfall-1 mutation is no longer reproducing, so this guard is vacuous"
    )
    # And the displacement is expensive when applied to correct data: score BOTH constants
    # against the REAL gap population, which is what production would do.
    scored = {p.threshold: p for p in sweep(real_pos, real_neg, [K_EM, best_fs.threshold])}
    assert scored[best_fs.threshold].recall < scored[K_EM].recall - 0.05, (
        f"the displaced constant {best_fs.threshold} cost only "
        f"{scored[K_EM].recall - scored[best_fs.threshold].recall:.4f} recall on real gaps"
    )
