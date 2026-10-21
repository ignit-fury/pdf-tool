"""02-09 Task 2 / 03-07 Task 4: the CLI over the Phase 2 pipeline (`engine.index.RunIndex`)
and the Phase 3 recipe engine (`engine.recipe`).

Two subcommands:

`index <pdf_path> [--page N]`:
  - no `--page`: a per-page summary table (page number, run count, editable/substitution/
    not-editable counts, page bucket), iterating every page of the document so `RunIndex`'s
    own cache/evict machinery (D-06) runs exactly as intended -- no eager whole-document
    alternative exists here (see `engine.index`'s own docstring on Pitfall 8).
  - with `--page N`: that page's run list (run ID, display text with its synthetic spaces,
    verdict state, and `reason` only when the state is `not_editable` -- `RunVerdict.reason`
    is `None` for editable runs, so printing it unconditionally would just be noise).

`edit <pdf_path> --recipe r.json -o out.pdf [--commit]`:
  - D-03: dry run is the default. Without `--commit` this computes and prints the per-op
    fit/refusal report (`plan_recipe`) and writes nothing. With `--commit` it applies the
    recipe (`apply_recipe`) and writes `out.pdf` only when every op resolved (D-11).
  - The printed report is a direct, structured-data-first rendering of the SAME
    `RecipeReport` object `plan_recipe`/`apply_recipe` return -- never a separately
    recomputed summary (D-03's "Phase 4's UI later renders this same structured data
    rather than recomputing it").

Implemented as a real `add_subparsers` subcommand structure (not a bare positional-arg
parser) even when only one subcommand existed, per the plan's own phrasing ("one
subcommand") -- this keeps a natural home for future subcommands without a breaking CLI
change later, which is exactly what `edit` now is.

Local, filesystem-only CLI. Phase 2 is still CLI-only (no web tier before Gate G2b in
Phase 3) -- this file must never import anything that opens a network surface (T-02 threat
register's disposition for this exact file: "CLI, no network, no served endpoint" --
still true for `edit`: `engine.recipe` itself opens no network surface either).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# `python tools/pdftool.py ...` (the plan's own literal invocation, no `uv run -m` / no
# PYTHONPATH) puts `tools/`, not the repo root, on sys.path[0] -- `engine` would otherwise
# not be importable. Mirrors `tools/harvest_public_corpus.py`'s own precedent of inserting
# a path relative to `__file__` for exactly this reason.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.index import RunIndex  # noqa: E402
from engine.recipe import (  # noqa: E402
    RecipeReport,
    RecipeTooLargeError,
    apply_recipe,
    parse_recipe,
    plan_recipe,
)


def _print_summary(idx: RunIndex) -> None:
    header = f"{'page':>5}  {'runs':>5}  {'editable':>8}  {'subst':>5}  {'not_editable':>12}  bucket"
    print(header)
    for page_number in range(idx.page_count):
        page = idx.page(page_number)
        editable = substitution = not_editable = 0
        for _run, verdict in page.runs:
            if verdict.state == "editable_original":
                editable += 1
            elif verdict.state == "editable_substitution":
                substitution += 1
            else:
                not_editable += 1
        print(
            f"{page_number:>5}  {len(page.runs):>5}  {editable:>8}  {substitution:>5}  "
            f"{not_editable:>12}  {page.bucket}"
        )


def _print_page_runs(idx: RunIndex, page_number: int) -> None:
    page = idx.page(page_number)
    for run, verdict in page.runs:
        line = f"{run.run_id}  {run.display_text!r}  {verdict.state}"
        if verdict.state == "not_editable" and verdict.reason is not None:
            line += f"  reason={verdict.reason}"
        print(line)


def _cmd_index(args: argparse.Namespace) -> int:
    with RunIndex(args.pdf_path) as idx:
        if args.page is None:
            _print_summary(idx)
        else:
            _print_page_runs(idx, args.page)
    return 0


def _print_report(report: "RecipeReport") -> None:
    """D-03's report, printed. Structured data FIRST: one line per op, built entirely
    from that op's OWN `ResolvedOp` fields -- a direct rendering, no recomputation. Human
    text SECOND: a short summary line. This ordering is D-03's explicit requirement, not
    cosmetic -- Phase 4 consumes the same per-run records this loop reads to drive its UI.
    """
    for resolved in report.resolved:
        line = f"{resolved.op.run_id}  ok={resolved.ok}"
        if resolved.reason is not None:
            line += f"  reason={resolved.reason}"
        if resolved.strategy is not None:
            line += f"  strategy={resolved.strategy}"
        if resolved.delta_pt is not None:
            line += f"  delta_pt={resolved.delta_pt}"
        print(line)

    refused = sum(1 for r in report.resolved if not r.ok)
    print(f"{len(report.resolved)} op(s), {refused} refused")


def _cmd_edit(args: argparse.Namespace) -> int:
    data = Path(args.recipe).read_bytes()
    try:
        recipe = parse_recipe(data)
    except (ValueError, RecipeTooLargeError) as exc:
        print(f"recipe rejected: {exc}")
        return 1

    if args.commit:
        report = apply_recipe(args.pdf_path, recipe, args.output)
    else:
        report = plan_recipe(args.pdf_path, recipe)

    _print_report(report)

    if not args.commit:
        print("dry run -- pass --commit to write output")
    elif report.ok:
        print(f"written to {args.output}")
    # else: the per-op reasons already printed above are the explanation (D-11).

    return 0 if report.ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser(
        "index", help="Walk a PDF through the Phase 2 pipeline and print its run index"
    )
    index_parser.add_argument("pdf_path", help="Path to the PDF file")
    index_parser.add_argument(
        "--page",
        type=int,
        default=None,
        help="Print only this page's run list (0-indexed) instead of the whole-document summary",
    )
    index_parser.set_defaults(func=_cmd_index)

    edit_parser = subparsers.add_parser(
        "edit", help="Apply a JSON recipe of text edits to a PDF (dry run by default)"
    )
    edit_parser.add_argument("pdf_path", help="Path to the PDF file")
    edit_parser.add_argument("--recipe", required=True, help="Path to the JSON recipe file")
    edit_parser.add_argument(
        "-o", "--output", required=True, help="Path to write the edited PDF"
    )
    edit_parser.add_argument(
        "--commit",
        action="store_true",
        help="Write output; without this flag, only the fit/refusal report is printed "
        "and nothing is written (D-03)",
    )
    edit_parser.set_defaults(func=_cmd_edit)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
