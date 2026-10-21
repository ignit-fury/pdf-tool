"""Gate G2b's substitution-forcing fixture finder, plus its manual-review contact sheet.

Gate G2b must demonstrate a REAL substitution: a run whose replacement text contains a
character the embedded program has no glyph for, routed through `engine.fonts`'s
substitution trigger into a bundled Liberation subset. This module finds that
run+replacement-text combination by ASKING THE LIVE PIPELINE -- one `plan_recipe` call per
candidate, keeping the first whose `ResolvedOp.substitution_key` actually came back set.
Never invented, never asserted by construction: a fixture that only *looks* like it forces
substitution would let the project gate pass on a document that never substituted at all.

Two consumers, one finder:

- the G2b gate test (`select_g2b_fixture` / `default_g2b_candidates`), which needs a real
  corpus document plus a proven-forcing op;
- the one-time manual-verification evidence (`generate_contact_sheet`), which needs a
  persistent before/after PNG a human can look at.

D-05 / 03-RESEARCH.md Pattern 4: the substitution trigger is consulted independently of
Phase 2's own per-run state, so an `editable_original` run STILL substitutes the moment
`new_text` carries a glyph the embedded subset lacks. That is why the candidate search
deliberately prefers `editable_original` runs over already-flagged
`editable_substitution` ones -- forcing the trigger on a run the classifier called
editable-as-is is the stronger evidence, and it is the path Pattern 4 exists to cover.

Runs standalone from the repo root: `python -m harness.g2b_fixture`. No pytest import,
no `tests/conftest.py` helpers -- sample discovery mirrors `harness/render_diff.py`'s own
glob-based `__main__` self-check instead. Module invocation puts the repo root on
`sys.path` automatically, so no `sys.path` shim is needed here (unlike
`harness/run_corpus_harness.py` and `tools/pdftool.py`, which are invoked as scripts).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from PIL import Image

from engine.classify_run import classify_document
from engine.recipe import RecipeOp, apply_recipe, plan_recipe
from harness.render_diff import render_all

# Common Latin letters mapped to an accented form almost certainly absent from an
# English-language document's embedded subset -- a subset carries the glyphs the document
# actually uses, and an English document uses none of these.
ACCENT_FORCING_MAP = {
    "e": "é",
    "a": "á",
    "o": "ó",
    "i": "í",
    "u": "ú",
    "c": "ç",
    "n": "ñ",
}

# A CJK ideograph as a guaranteed-exotic fallback, for a run whose `display_text` contains
# none of the mapped letters.
FALLBACK_FORCING_CHAR = "字"

# ponytail: a bounded search, not a full 217-document corpus sweep, to keep this inside the
# quick per-commit budget -- widen only if the bound is measured to ever fail.
MAX_CANDIDATE_RUNS_PER_DOCUMENT = 20
MAX_CANDIDATE_DOCUMENTS = 10

# Corpus documents MEASURED to yield a forcing op that also applies cleanly, fastest
# first -- see `default_g2b_candidates`'s docstring for the measurements and for why the
# alphabetical glob alone cannot reach one inside a per-commit budget. Pinned, not
# guessed: each was run end to end through `find_substitution_forcing_op` +
# `apply_recipe` on 2026-08-27. Not a hardcoded fixture list -- the glob discovery below
# them still runs if any of these is unavailable.
PINNED_G2B_DOCUMENTS = [
    Path("corpus/public/govdocs1_000_000019.pdf"),  # 0.5s
    Path("corpus/public/govdocs1_000_000016.pdf"),  # 1.6s
    Path("corpus/public/govdocs1_000_000018.pdf"),  # 1.7s
    Path("corpus/public/govdocs1_000_000028.pdf"),  # 3.4s
    Path("corpus/public/govdocs1_000_000015.pdf"),  # 55.5s
]


def _candidate_new_texts(display_text: str) -> list[str]:
    """Replacement strings to try against one run, most plausible first.

    One candidate per `ACCENT_FORCING_MAP` letter actually present in `display_text` (its
    first occurrence replaced, an uppercase input taking the uppercase accented form),
    then `display_text` plus `FALLBACK_FORCING_CHAR` as the last resort. The accented
    candidates come first because they keep the run's length and shape, which gives the
    fit ladder its best chance of accepting the replacement.
    """
    candidates: list[str] = []
    for letter, accented in ACCENT_FORCING_MAP.items():
        for i, char in enumerate(display_text):
            if char.lower() == letter:
                replacement = accented.upper() if char.isupper() else accented
                candidates.append(display_text[:i] + replacement + display_text[i + 1 :])
                break
    candidates.append(display_text + FALLBACK_FORCING_CHAR)
    return candidates


def find_substitution_forcing_op(pdf_path: str | Path) -> RecipeOp:
    """A `RecipeOp` against `pdf_path` that a LIVE `plan_recipe` call proves substitutes.

    Proof, not construction: the op is returned only when `plan_recipe` reports `ok` AND
    the resolved op carries a `substitution_key`, which `engine.recipe` sets only when
    `engine.fonts.run_needs_substitution` (or an `editable_substitution` verdict) actually
    routed the run to a bundled face.

    Raises `RuntimeError` -- naming only the file name and the counts tried, never
    `display_text` or any candidate string (EDIT-04's no-document-content posture applied
    to this harness) -- when every candidate is exhausted.
    """
    classification = classify_document(pdf_path)
    candidate_runs = [
        (run, verdict)
        for run, verdict in classification.runs
        if verdict.state == "editable_original"
    ][:MAX_CANDIDATE_RUNS_PER_DOCUMENT]

    candidates_tried = 0
    for run, _verdict in candidate_runs:
        for candidate in _candidate_new_texts(run.display_text):
            candidates_tried += 1
            op = RecipeOp(run.run_id, candidate)
            report = plan_recipe(pdf_path, (op,))
            if report.ok and report.resolved[0].substitution_key is not None:
                return op

    raise RuntimeError(
        f"no substitution-forcing op found in {Path(pdf_path).name}: "
        f"{len(candidate_runs)} run(s), {candidates_tried} candidate(s) tried"
    )


def select_g2b_fixture(candidate_paths: Sequence[str | Path]) -> tuple[Path, RecipeOp]:
    """The first `(path, op)` among `candidate_paths` that forces substitution.

    Iterating a list rather than pinning one document is what makes the gate test
    deterministic ENOUGH without being brittle: the corpus order is fixed, so the same
    fixture is selected run after run, but a document that stops qualifying does not
    break the gate.
    """
    for path in candidate_paths:
        try:
            op = find_substitution_forcing_op(path)
        except RuntimeError:
            continue
        return Path(path), op

    raise RuntimeError(
        f"no substitution-forcing fixture found in {len(candidate_paths)} candidate(s)"
    )


def default_g2b_candidates() -> list[Path]:
    """Candidate documents: the measured-good pins first, then the discovery fallback.

    The pins are MEASURED, not guessed -- the same "measure, then pin, never guess"
    posture every threshold in this codebase carries. Each of `PINNED_G2B_DOCUMENTS`
    was run through `find_substitution_forcing_op` + `apply_recipe` and produced a
    fully applied substituting edit in 0.5-3.4s (`_000015` at 55.5s is last for that
    reason).

    Why pinning is load-bearing rather than an optimisation: naive alphabetical
    discovery puts `far_federal_acquisition_regulation.pdf` (13 MB, 139,620 runs)
    first, whose `classify_document` alone measures 395s -- and `plan_recipe`
    re-classifies per candidate, so ONE such document's bounded search costs up to
    ~17 hours. The two next alphabetical documents yield no forcing op at all
    (`tj_refit_sample.pdf`: `ITCFranklinGothicStd-Demi`, `govdocs1_000_000009.pdf`:
    `LucidaSans-Bold` -- neither in the D-06 mapping table), so discovery order alone
    reaches nothing usable inside any per-commit budget.

    The original spike-fixture + glob discovery is kept BELOW the pins, unchanged, so
    the function still finds a fixture on its own if a pinned document is ever
    removed. Discovery mirrors `harness/render_diff.py`'s own glob-based `__main__`
    sample pick exactly -- never `tests/conftest.py`'s pytest-bound
    `docs_with_category`/`open_doc`, so this module stays importable and runnable
    outside pytest.
    """
    candidates = [p for p in PINNED_G2B_DOCUMENTS if p.exists()]
    fallback = [p for p in [Path("spike/fixtures/tj_refit_sample.pdf")] if p.exists()]
    fallback.extend(sorted(Path("corpus/public").glob("*.pdf"))[:MAX_CANDIDATE_DOCUMENTS])
    candidates.extend(p for p in fallback if p not in candidates)
    return candidates


def generate_contact_sheet(pdf_paths: Sequence[Path], output_dir: Path) -> list[Path]:
    """One side-by-side before/after PNG per usable document, written to `output_dir`.

    This is the persistent artifact G2b's one-time manual verification is signed off
    against -- a human looks at the pair, not at a metric. Documents with no forcing op,
    or whose recipe does not apply, are skipped out loud rather than failing the batch:
    the sheet is evidence, and one unusable corpus sample is not evidence of anything.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    sheets: list[Path] = []

    for pdf_path in pdf_paths:
        try:
            op = find_substitution_forcing_op(pdf_path)
        except RuntimeError:
            print(f"skip {pdf_path.name}: no forcing op found")
            continue

        output_pdf = output_dir / f"{pdf_path.stem}_g2b.pdf"
        report = apply_recipe(pdf_path, (op,), output_pdf)
        if not report.ok:
            print(f"skip {pdf_path.name}: recipe did not apply")
            continue

        run = report.resolved[0].run
        if run is None:
            # Structurally unreachable for an applied op -- `plan_recipe` sets `run` on
            # every success path. A named skip rather than an `AttributeError` crash.
            print(f"skip {pdf_path.name}: applied op carries no run record")
            continue

        orig_renders = render_all(pdf_path, run.page, output_dir / f"{pdf_path.stem}_orig")
        new_renders = render_all(output_pdf, run.page, output_dir / f"{pdf_path.stem}_new")

        # Index 0 is render_all's pdfium render -- the in-process engine, and the one
        # whose CropBox handling the other two are aligned to in render_diff.py.
        with Image.open(orig_renders[0]) as orig, Image.open(new_renders[0]) as new:
            sheet = Image.new(
                "RGB",
                (orig.width + new.width, max(orig.height, new.height)),
                "white",
            )
            sheet.paste(orig, (0, 0))
            sheet.paste(new, (orig.width, 0))
            sheet_path = output_dir / f"{pdf_path.stem}_g2b_before_after.png"
            sheet.save(sheet_path)

        sheets.append(sheet_path)

    return sheets


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="/tmp/g2b_manual_review")
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()

    candidates = default_g2b_candidates()[: args.samples]
    sheets = generate_contact_sheet(candidates, Path(args.output_dir))
    if sheets:
        for sheet in sheets:
            print(sheet)
        print(f"OK: {len(sheets)} contact sheet(s) in {args.output_dir}")
        sys.exit(0)

    print(f"FAIL: no contact sheet produced from {len(candidates)} candidate(s)")
    sys.exit(1)
