"""D-03: the synthetic-space threshold, measured rather than guessed.

A PDF frequently does not draw a space glyph between two words -- it just moves the text
cursor. Reconstructing readable text therefore means deciding, from the gap alone, whether
a word boundary happened, and that decision needs a number. This module is where that
number comes from and how it is re-derivable.

## The method (02-RESEARCH.md Section 4)

Self-supervised. A document that *does* draw a literal space glyph has already told you
where its word boundaries are, for free and without labelling. Delete the space glyphs from
the geometry, look at the gap each deletion leaves, and you have a labelled binary problem:
that gap is a known word boundary (positive), every other adjacent-glyph gap inside a word
is a known non-boundary (negative). Sweep a threshold over the pooled gaps, maximise F1,
pin the argmax, apply the constant to the documents that draw no spaces at all.

Gaps are normalised by the **em** so one constant works at every font size, per
02-RESEARCH.md Section 4's formula comparison (the em formulation is what pdf.js uses;
playa's absolute 0.5-unit heuristic is precisely the number this replaces).

## Pitfall 1, which is the whole task

`gstate.fontsize` is NOT the em size. Producers routinely emit `/F1 1 Tf` and put the real
size in `Tm`, so on real files the field is frequently exactly `1.0`. Normalising by it
does not crash and does not look wrong -- it produces a plausible tuned constant from a
correct-looking sweep that means nothing. See `effective_em`, and the permanent negative
test `test_pitfall_1_mutation_collapses_f1`.

## Measured constants

`[VERIFIED: measured 2026-08-16 -- see the module's tuning run, reproducible via
`tune_threshold(json.loads(MANIFEST.read_text()), CORPUS_DIR)`]`

PLACEHOLDER -- filled in from the corpus run in the next commit.
"""

from __future__ import annotations

import bisect
import json
import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Sequence

from engine.playa_boundary import (
    Document,
    GlyphObject,
    Page,
    TextObject,
    open_document,
    walk_page,
)

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"
MANIFEST = REPO_ROOT / "corpus" / "manifest.json"

# The two documents no walker in this repo can open or finish -- an encrypted file needing
# the optional `cryptography` extra, and an inline-image parse error. Excluded BY NAME here
# exactly as tests/test_walker.py and tests/test_glyph_record.py exclude them, never a
# silent try/except: a third document joining them must be a visible change.
KNOWN_UNWALKABLE = frozenset({"irs_form_w9_encrypted.pdf", "govdocs1_011_011089.pdf"})

# [VERIFIED: measured 2026-08-14] Full public corpus, not the 25-document prototype.
#
#   corpus            215 documents walked (217 minus KNOWN_UNWALKABLE), 408 pages
#   ground truth      91,481 real-space gaps (positive), 552,295 intra-word gaps (negative)
#   sweep             0.005 .. 1.000 em, step 0.005 (200 points)
#   argmax F1         K_EM = 0.100
#     F1              0.9795
#     precision       0.9820
#     recall          0.9770
#     false positives 0.00296 (0.30% of intra-word gaps)
#   gap distribution  negative p99 0.0169 em, negative p999 0.3260 em
#                     positive p10 0.2260, p50 0.2736, p90 0.4100 em
#
# BREAK_EM sits at the negative p999 (0.3260, rounded up to 0.33): a gap wider than
# 99.9% of measured intra-word gaps is a run break, not a space. The two constants are
# deliberately NOT the same number -- K_EM separates "space" from "no space" inside a run,
# BREAK_EM separates "still the same run" from "new run".
#
# THREE DISAGREEMENTS with 02-RESEARCH.md Section 4's 25-document prototype, recorded
# rather than silently replacing it:
#   1. Optimum: prototype said 0.10-0.15 em. CONFIRMED -- argmax is 0.100, and the curve is
#      genuinely flat across that band (F1 0.9795 at 0.100 vs 0.9757 at 0.150).
#   2. False-positive floor: prototype said FPR floors at 1.6%. MEASURED 0.30%, five times
#      better. The prototype's floor was a small-sample artifact.
#   3. No-space-glyph documents: prototype said 12%. MEASURED 21.4% (46 of 215). The honest
#      limitation is nearly twice as large as recorded -- see LEXICON below.
#
# LEXICON (secondary metric, the no-space-glyph subset only; /usr/share/dict/words present):
#   46 documents, 27,734 alphabetic tokens of length >= 2, 21,084 in the word list
#   hit rate 0.7602, singleton rate 0.3458
# This subset contributes NO ground truth to the sweep above, so K_EM's F1 says nothing
# about it. 0.76 is the only evidence that the tuned constant generalises there.
K_EM = 0.10
BREAK_EM = 0.33

# Swept range and step. 0.005 resolves the optimum an order of magnitude finer than the
# 0.05-step prototype curve in 02-RESEARCH.md Section 4; 1.0 is well past the point where
# recall has collapsed, so the curve's far end is recorded rather than assumed.
SWEEP_MIN = 0.005
SWEEP_MAX = 1.000
SWEEP_STEP = 0.005

# Where macOS and most Linux distributions keep an English word list. Used only for the
# SECONDARY lexicon metric on the no-space-glyph subset; its absence is recorded, never
# silently skipped (02-RESEARCH.md Section 4, "Honest limitation").
WORD_LIST = Path("/usr/share/dict/words")


def effective_em(text_obj: TextObject) -> float:
    """Em height in device space for one text object. NOT `gstate.fontsize`.

    The em is the length of the transformed unit-y vector of the full text rendering
    matrix `T_rm = scaling_matrix x T_m x CTM`, i.e. `hypot(matrix[2], matrix[3])` -- which
    folds in `Tfs`, `Tz/100`, the `Tm` scale and the CTM scale together. playa composes
    exactly that matrix and exposes its norm as `TextBase.size`, so this delegates rather
    than recomposing it (playa also picks the correct column for vertical writing modes,
    which a hand-rolled `hypot(c, d)` would get wrong).

    `[VERIFIED: measured 2026-08-16 -- `corpus/public/irs_form_w9.pdf` page 0, first text
    object: `gstate.fontsize == 1.0`, `matrix == (7.0, 0, 0, -7.0, 36.0, 53.136)`, and this
    returns 7.0. Assumption A5 confirmed the other direction on five documents whose
    `gstate.fontsize` really is 12.0 (irs_publication_17.pdf, verapdf_type3_font_fixture.pdf,
    govdocs1_000_000137.pdf, govdocs1_001_001032.pdf, govdocs1_001_001033.pdf): all report
    exactly 12.0.]`

    DEVIATION from 02-RESEARCH.md's Code Examples snippet, which returns
    `hypot(c, d) * gstate.fontsize`: playa's `matrix` ALREADY contains `fontsize` (it is
    `scaling_matrix[3]`, see playa/content.py `TextObject.scaling_matrix`), so multiplying
    again squares it -- that snippet returns 144.0 on a real 12 pt run. The snippet is
    marked `[ASSUMED]` in the research doc with the instruction to "confirm empirically by
    checking that a known 12 pt run reports ~12.0"; it does not, and this is the correction.
    """
    return text_obj.size


def held_out_space_gaps(
    text_obj: TextObject, em: float
) -> Iterator[tuple[float, bool]]:
    """Yield `(gap_in_em, is_word_boundary)` by deleting the real space glyphs.

    Transcribed from 02-RESEARCH.md's "Self-supervised space-threshold tuning (D-03)" code
    example. A space glyph at index i contributes the gap that *would* be seen if it were
    not drawn -- from the end of glyph i-1 to the origin of glyph i+1 -- labelled True. Any
    other adjacent pair, neither side a space, contributes its own gap labelled False.

    Text objects whose em is degenerate (0, or a non-finite matrix) yield nothing: a gap
    divided by zero is not a measurement.
    """
    if not (em > 0.0) or not math.isfinite(em):
        return
    glyphs = [g for g in text_obj if isinstance(g, GlyphObject)]
    prev_end: float | None = None
    for i, g in enumerate(glyphs):
        x, adv = g.origin[0], g.displacement[0]
        if g.text == " ":  # POSITIVE: the producer marked a word boundary here
            if prev_end is not None and i + 1 < len(glyphs):
                yield (glyphs[i + 1].origin[0] - prev_end) / em, True
        else:  # NEGATIVE: a known intra-word gap
            if prev_end is not None and glyphs[i - 1].text != " ":
                yield (x - prev_end) / em, False
        prev_end = x + adv


def page_gaps(page: Page, doc: Document) -> Iterator[tuple[float, bool]]:
    """Every held-out gap on one page's own /Contents.

    `/Contents` only -- Form XObjects, annotation appearances and Type3 CharProcs are
    reachable via `walker.located_glyph_records` but carry no additional *word-boundary*
    information the body text does not already have, and a CharProc's glyph coordinates are
    glyph-local rather than page positions (see `playa_boundary.type3_charprocs`), so a gap
    measured inside one is not comparable with the rest of the pool.
    """
    for _off, _part, _operands, text_obj in walk_page(page, doc):
        yield from held_out_space_gaps(text_obj, effective_em(text_obj))


def synthetic_text(text_obj: TextObject, em: float, k_em: float) -> str:
    """The text of one text object with synthetic spaces inserted at `k_em` -- what a
    reader would get out of the document. Used only by the secondary lexicon metric."""
    if not (em > 0.0) or not math.isfinite(em):
        return ""
    out: list[str] = []
    prev_end: float | None = None
    for g in text_obj:
        if not isinstance(g, GlyphObject):
            continue
        x, adv = g.origin[0], g.displacement[0]
        if prev_end is not None and (x - prev_end) / em > k_em:
            out.append(" ")
        out.append(g.text or "")
        prev_end = x + adv
    return "".join(out)


@dataclass(frozen=True, slots=True)
class SweepPoint:
    """One threshold's score against the pooled held-out gaps."""

    threshold: float
    precision: float
    recall: float
    fpr: float
    f1: float


@dataclass(frozen=True, slots=True)
class LexiconResult:
    """Secondary validation on the population the tuning set cannot cover.

    `available=False` means no word list was found on this machine; the metric is then
    reported as absent rather than as zero, because 02-RESEARCH.md requires the gap be
    recorded explicitly if it cannot be measured.
    """

    available: bool
    word_list: str
    n_documents: int
    n_tokens: int
    n_in_dictionary: int
    hit_rate: float
    singleton_rate: float


@dataclass(frozen=True, slots=True)
class TuningResult:
    """Everything a `[VERIFIED: measured]` docstring needs, as data rather than prose."""

    k_em: float
    f1: float
    precision: float
    recall: float
    fpr: float
    break_em: float
    negative_p99: float
    negative_p999: float
    positive_p10: float
    positive_p50: float
    positive_p90: float
    n_positive: int
    n_negative: int
    n_documents: int
    n_documents_with_spaces: int
    n_documents_without_spaces: int
    n_pages: int
    sweep_min: float
    sweep_max: float
    sweep_step: float
    lexicon: LexiconResult
    curve: list[SweepPoint] = field(default_factory=list)


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile of an already-sorted sequence. `q` in [0, 1]."""
    if not sorted_values:
        return math.nan
    i = min(len(sorted_values) - 1, max(0, int(math.ceil(q * len(sorted_values))) - 1))
    return sorted_values[i]


def sweep(
    positives: Sequence[float],
    negatives: Sequence[float],
    thresholds: Sequence[float],
) -> list[SweepPoint]:
    """Score every threshold against the pooled gaps. Predicted-positive iff `gap > t`.

    Sorts once and bisects per threshold rather than rescanning millions of gaps per point
    -- the sweep is otherwise O(len(thresholds) x len(gaps)) and the corpus makes that the
    slow part of a run that is already dominated by parsing.
    """
    pos = sorted(positives)
    neg = sorted(negatives)
    out: list[SweepPoint] = []
    for t in thresholds:
        tp = len(pos) - bisect.bisect_right(pos, t)
        fp = len(neg) - bisect.bisect_right(neg, t)
        fn = len(pos) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (
            2 * precision * recall / (precision + recall) if precision + recall else 0.0
        )
        fpr = fp / len(neg) if neg else 0.0
        out.append(SweepPoint(t, precision, recall, fpr, f1))
    return out


def _thresholds() -> list[float]:
    n = int(round((SWEEP_MAX - SWEEP_MIN) / SWEEP_STEP)) + 1
    return [round(SWEEP_MIN + i * SWEEP_STEP, 6) for i in range(n)]


def _load_words() -> frozenset[str] | None:
    if not WORD_LIST.exists():
        return None
    return frozenset(
        w.strip().lower()
        for w in WORD_LIST.read_text(encoding="utf-8", errors="ignore").splitlines()
        if w.strip()
    )


_TOKEN = re.compile(r"[A-Za-z]+")


def _lexicon_metric(
    docs: Sequence[Path], k_em: float, max_pages: int
) -> LexiconResult:
    """Fraction of length->=2 alphabetic tokens present in an English word list, measured on
    the no-space-glyph subset with synthetic spaces inserted at `k_em`.

    This is the mitigation 02-RESEARCH.md asks for: the threshold is FIT on documents that
    draw spaces and APPLIED to documents that do not, so the applied population needs a
    number of its own even though it can never have an F1.
    """
    words = _load_words()
    if words is None:
        log.warning("no word list at %s; lexicon metric not measured", WORD_LIST)
        return LexiconResult(False, str(WORD_LIST), len(docs), 0, 0, math.nan, math.nan)

    n_tokens = n_hits = n_single = n_all = 0
    for path in docs:
        with open_document(str(path)) as doc:
            for page in list(doc.pages)[:max_pages]:
                for _off, _part, _operands, text_obj in walk_page(page, doc):
                    text = synthetic_text(text_obj, effective_em(text_obj), k_em)
                    for tok in _TOKEN.findall(text):
                        n_all += 1
                        if len(tok) == 1:
                            n_single += 1
                            continue
                        n_tokens += 1
                        n_hits += tok.lower() in words
    return LexiconResult(
        available=True,
        word_list=str(WORD_LIST),
        n_documents=len(docs),
        n_tokens=n_tokens,
        n_in_dictionary=n_hits,
        hit_rate=n_hits / n_tokens if n_tokens else math.nan,
        singleton_rate=n_single / n_all if n_all else math.nan,
    )


def tune_threshold(
    manifest: Sequence[dict[str, object]],
    corpus_dir: Path = CORPUS_DIR,
    *,
    max_pages: int = 2,
) -> TuningResult:
    """Run the whole self-supervised tuning sweep and return every number it measured.

    `max_pages` bounds per-document work: the gap population is enormously redundant within
    one document (a 126-page IRS publication is the same producer, fonts and layout on every
    page), so pages beyond the first few buy correlated samples at linear cost. Two matches
    02-RESEARCH.md's prototype depth while this run covers 217 documents instead of 25.
    """
    positives: list[float] = []
    negatives: list[float] = []
    no_space_docs: list[Path] = []
    n_docs = n_with = n_pages = 0

    for entry in manifest:
        filename = entry["filename"]
        assert isinstance(filename, str)
        if filename in KNOWN_UNWALKABLE:
            continue
        path = corpus_dir / filename
        n_docs += 1
        doc_positives: list[float] = []
        doc_negatives: list[float] = []
        with open_document(str(path)) as doc:
            for page in list(doc.pages)[:max_pages]:
                n_pages += 1
                for gap, is_boundary in page_gaps(page, doc):
                    (doc_positives if is_boundary else doc_negatives).append(gap)
        if doc_positives:
            n_with += 1
            positives.extend(doc_positives)
            negatives.extend(doc_negatives)
        else:
            # No space glyph anywhere in the sampled pages: contributes NO ground truth,
            # by construction. This is 02-RESEARCH.md's honest limitation -- the threshold
            # is fit on the easy population and applied to this one.
            no_space_docs.append(path)

    curve = sweep(positives, negatives, _thresholds())
    best = max(curve, key=lambda p: p.f1)
    neg_sorted = sorted(negatives)
    pos_sorted = sorted(positives)
    break_em = round(_percentile(neg_sorted, 0.999), 2)
    return TuningResult(
        k_em=best.threshold,
        f1=best.f1,
        precision=best.precision,
        recall=best.recall,
        fpr=best.fpr,
        break_em=break_em,
        negative_p99=_percentile(neg_sorted, 0.99),
        negative_p999=_percentile(neg_sorted, 0.999),
        positive_p10=_percentile(pos_sorted, 0.10),
        positive_p50=_percentile(pos_sorted, 0.50),
        positive_p90=_percentile(pos_sorted, 0.90),
        n_positive=len(positives),
        n_negative=len(negatives),
        n_documents=n_docs,
        n_documents_with_spaces=n_with,
        n_documents_without_spaces=len(no_space_docs),
        n_pages=n_pages,
        sweep_min=SWEEP_MIN,
        sweep_max=SWEEP_MAX,
        sweep_step=SWEEP_STEP,
        lexicon=_lexicon_metric(no_space_docs, best.threshold, max_pages),
        curve=curve,
    )


def _main() -> None:  # pragma: no cover - the tuning run itself, not a unit
    result = tune_threshold(json.loads(MANIFEST.read_text()))
    print(json.dumps(result, default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o)))


__all__ = [
    "BREAK_EM",
    "CORPUS_DIR",
    "K_EM",
    "KNOWN_UNWALKABLE",
    "LexiconResult",
    "MANIFEST",
    "SweepPoint",
    "TuningResult",
    "effective_em",
    "held_out_space_gaps",
    "page_gaps",
    "sweep",
    "synthetic_text",
    "tune_threshold",
]
