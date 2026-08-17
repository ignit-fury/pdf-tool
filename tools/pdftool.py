"""02-09 Task 2: the CLI over the Phase 2 pipeline (`engine.index.RunIndex`).

One subcommand, `index <pdf_path> [--page N]`:
  - no `--page`: a per-page summary table (page number, run count, editable/substitution/
    not-editable counts, page bucket), iterating every page of the document so `RunIndex`'s
    own cache/evict machinery (D-06) runs exactly as intended -- no eager whole-document
    alternative exists here (see `engine.index`'s own docstring on Pitfall 8).
  - with `--page N`: that page's run list (run ID, display text with its synthetic spaces,
    verdict state, and `reason` only when the state is `not_editable` -- `RunVerdict.reason`
    is `None` for editable runs, so printing it unconditionally would just be noise).

Implemented as a real `add_subparsers` subcommand (not a bare positional-arg parser) even
though only one exists today, per the plan's own phrasing ("one subcommand") -- this keeps a
natural home for future subcommands without a breaking CLI change later.

Local, filesystem-only CLI. Phase 2 is still CLI-only (no web tier before Gate G2b in
Phase 3) -- this file must never import anything that opens a network surface (T-02 threat
register's disposition for this exact file: "CLI, no network, no served endpoint").
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

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
