"""02-10 Task 1/2/3: engine/identity_rewrite.py -- Gate G1 criterion 1's provenance
round-trip, the last requirement of Phase 2.

Three layers, matching the plan's own three tasks:

1. `test_identity_rewrite_preserves_run_ids` (Task 1's pinned name) and its
   companions prove the mechanism on a real corpus document: identity_rewrite/
   null_edit_rewrite followed by verify_roundtrip, plus the permanent negative case
   that proves verify_roundtrip actually discriminates a real content change.
2. `test_malformed_corpus_roundtrip` (Task 2) sweeps all 17 malformed-category
   documents and closes 02-RESEARCH.md's Open Question 4 (does qpdf's repair-on-open
   shift the run ID scheme's part-index addressing?) with measured evidence, not
   left open into Phase 3.
3. `test_*_harness_zero_diff` (Task 3) reuses harness/render_diff.render_all +
   harness/masked_diff.masked_pixel_diff -- Phase 1's own same-engine zero-tolerance
   primitive -- rather than inventing a second verification mechanism.

No document content (glyph text) appears in any assertion message, per this
project's standing convention (T-02-04) -- only counts, filenames and booleans.

Scratch-only writes throughout (threat register T-02-01/T-02-06): every rewrite
output goes to pytest's own `tmp_path` fixture, never the corpus file itself.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pikepdf
import pytest

from engine.identity_rewrite import identity_rewrite, null_edit_rewrite, verify_roundtrip
from engine.index import RunIndex

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"
MANIFEST_PATH = REPO_ROOT / "corpus" / "manifest.json"

# harness/ has no __init__.py -- sibling-module import, matching
# tests/test_masked_diff.py's own established convention (and
# harness/run_corpus_harness.py's own module docstring, which explains why: these
# scripts are meant to be runnable directly with harness/ as sys.path[0]).
sys.path.insert(0, str(REPO_ROOT / "harness"))
from masked_diff import masked_pixel_diff  # noqa: E402
from render_diff import render_all  # noqa: E402

# wikipedia_zh_monthly_magazine.pdf: 14 pages, subset_fonts/type0_identity_h/
# cid_keyed_cff, page 0 alone carries 11 real `Tj` instructions (not just `TJ`
# arrays) directly in the page's own /Contents -- verified directly before writing
# this test, and does NOT reproduce the multi-part-Tf-scope finding named in
# engine/identity_rewrite.py's own module docstring (unlike every irs_form_*.pdf and
# govdocs1_003_003074.pdf, which do).
WIKIPEDIA_ZH = CORPUS_DIR / "wikipedia_zh_monthly_magazine.pdf"

# irs_1040_instructions.pdf: contents_array + form_xobjects + type0_identity_h in
# ONE document (its own manifest categories) -- three of Task 3's four named
# structural categories from a single file.
IRS_1040_INSTRUCTIONS = CORPUS_DIR / "irs_1040_instructions.pdf"

# The corpus's only pure-type3 fixture.
TYPE3_FIXTURE = CORPUS_DIR / "verapdf_type3_font_fixture.pdf"


def _manifest() -> list[dict]:
    return json.loads(MANIFEST_PATH.read_text())


# --------------------------------------------------------------------------------------
# Task 1: identity_rewrite / null_edit_rewrite / verify_roundtrip, proven on a real
# corpus document, plus the permanent negative case.
# --------------------------------------------------------------------------------------


def test_identity_rewrite_preserves_run_ids(tmp_path: Path) -> None:
    """Task 1's pinned acceptance criterion, verbatim: on a real corpus document,
    identity_rewrite followed by verify_roundtrip returns True."""
    idx = RunIndex(WIKIPEDIA_ZH)
    try:
        total_runs = sum(len(idx.page(i).runs) for i in range(idx.page_count))
        assert total_runs > 0, (
            "expected at least one run on this document -- otherwise a True "
            "verify_roundtrip result would be vacuous"
        )

        out = tmp_path / "identity.pdf"
        identity_rewrite(WIKIPEDIA_ZH, str(out))
        assert verify_roundtrip(WIKIPEDIA_ZH, idx, str(out)) is True
    finally:
        idx.close()


def test_null_edit_rewrite_produces_hex_literal_and_preserves_run_ids(
    tmp_path: Path,
) -> None:
    """The null-edit extension's own acceptance criterion: the output contains a hex
    string literal (proof the Tj-operand transformation actually ran, not just that
    verify_roundtrip still passes), and verify_roundtrip is still True."""
    idx = RunIndex(WIKIPEDIA_ZH)
    try:
        out = tmp_path / "null_edit.pdf"
        null_edit_rewrite(WIKIPEDIA_ZH, str(out))

        rewritten_pdf = pikepdf.open(out)
        try:
            found_hex_tj = any(
                b"> Tj" in page.obj.get("/Contents").read_bytes()
                for page in rewritten_pdf.pages
                if page.obj.get("/Contents") is not None
            )
        finally:
            rewritten_pdf.close()
        assert found_hex_tj, "expected at least one hex-string-serialised Tj in the output"

        assert verify_roundtrip(WIKIPEDIA_ZH, idx, str(out)) is True
    finally:
        idx.close()


def _mutated_rewrite_changes_one_tj_text(pdf_path: Path, output_path: Path) -> None:
    """THE MUTATION for the negative-case test below -- a standalone COPY of
    identity_rewrite's own parse/unparse loop that changes ONE Tj operand's actual
    text content, never a change to identity_rewrite itself (task-1-brief.md's own
    instruction). Proves verify_roundtrip actually discriminates a real content
    change rather than accepting everything -- this project's standing "a check is
    not trusted until demonstrated failing" discipline."""
    pdf = pikepdf.open(pdf_path)
    try:
        mutated = False
        for page in pdf.pages:
            ops = pikepdf.parse_content_stream(page)
            new_ops = []
            for instr in ops:
                operands = instr.operands
                if (
                    not mutated
                    and str(instr.operator) == "Tj"
                    and len(operands) == 1
                    and isinstance(operands[0], pikepdf.String)
                ):
                    new_ops.append(
                        pikepdf.ContentStreamInstruction(
                            [pikepdf.String(b"MUTATED TEXT")], instr.operator
                        )
                    )
                    mutated = True
                else:
                    new_ops.append(instr)
            new_bytes = pikepdf.unparse_content_stream(new_ops)
            page.Contents = pdf.make_stream(new_bytes)
        assert mutated, (
            "expected at least one Tj instruction on this fixture to mutate -- "
            "otherwise this negative case is vacuous"
        )
        pdf.save(output_path)
    finally:
        pdf.close()


def test_verify_roundtrip_detects_mutated_tj_text(tmp_path: Path) -> None:
    """The permanent negative case (Task 1 acceptance criterion 3): a rewrite that
    changes one Tj operand's actual text, applied to the SAME fixture the positive
    tests above prove True on, must make verify_roundtrip return False."""
    idx = RunIndex(WIKIPEDIA_ZH)
    try:
        out = tmp_path / "mutated.pdf"
        _mutated_rewrite_changes_one_tj_text(WIKIPEDIA_ZH, out)
        assert verify_roundtrip(WIKIPEDIA_ZH, idx, str(out)) is False
    finally:
        idx.close()


# --------------------------------------------------------------------------------------
# Task 2: the 17 malformed-category documents -- 02-RESEARCH.md Open Question 4.
# --------------------------------------------------------------------------------------

# Measured directly, 2026-08-17, running identity_rewrite+verify_roundtrip against all
# 17 corpus/manifest.json "malformed"-category documents: 16/17 round-trip cleanly
# (verify_roundtrip returns True -- qpdf's repair-on-open does NOT shift this run ID
# scheme's part-index addressing on any of them, closing Open Question 4 with
# evidence). The 17th, govdocs1_011_011089.pdf, is NOT a new finding: `RunIndex`
# construction itself SUCCEEDS (it is lazy, D-06 -- opening a document never walks a
# page), but walking page 0 (inside `identity_rewrite`/`verify_roundtrip`, exactly as
# inside `RunIndex.page()`) raises the exact `PDFSyntaxError` from `ObjectParser`'s
# inline-image handling that tests/test_walker.py's own `KNOWN_OTHER_ERROR_FILES`
# already names for this same file -- a WALK failure, not a construction failure, and
# not a round-trip failure: the rewrite/verify machinery never got a chance to run.
KNOWN_MALFORMED_WALK_FAILURES = frozenset({"govdocs1_011_011089.pdf"})


@pytest.mark.corpus
def test_malformed_corpus_roundtrip() -> None:
    """Task 2: round-trip every one of the 17 malformed-category documents, recording
    a per-document pass/fail outcome. Any failure beyond the one already-known,
    already-diagnosed walk failure above is a NEW finding this test must surface,
    never silently absorbed into a loosened assertion."""
    malformed_filenames = sorted(
        e["filename"] for e in _manifest() if "malformed" in e.get("categories", [])
    )
    assert len(malformed_filenames) == 17, (
        f"malformed-category document count changed: now {len(malformed_filenames)}"
    )

    construction_failures: dict[str, str] = {}
    walk_failures: dict[str, str] = {}
    roundtrip_results: dict[str, bool] = {}

    for filename in malformed_filenames:
        path = CORPUS_DIR / filename
        try:
            idx = RunIndex(path)
        except Exception as exc:  # noqa: BLE001 - classified below, not swallowed
            construction_failures[filename] = type(exc).__name__
            continue

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                out = Path(tmp_dir) / "rewritten.pdf"
                identity_rewrite(path, out)
                roundtrip_results[filename] = verify_roundtrip(path, idx, str(out))
        except Exception as exc:  # noqa: BLE001 - classified below, not swallowed
            walk_failures[filename] = type(exc).__name__
        finally:
            idx.close()

    assert construction_failures == {}, (
        f"unexpected RunIndex construction failure(s): {construction_failures}"
    )
    assert set(walk_failures) == KNOWN_MALFORMED_WALK_FAILURES, (
        f"walk-failure set changed: "
        f"new={set(walk_failures) - KNOWN_MALFORMED_WALK_FAILURES} "
        f"missing={KNOWN_MALFORMED_WALK_FAILURES - set(walk_failures)}; "
        f"details={walk_failures}"
    )
    failed = {fn for fn, ok in roundtrip_results.items() if ok is not True}
    assert failed == set(), f"round-trip failed (not walk/construction) on: {sorted(failed)}"
    # Every non-walk-failure document was actually exercised, not skipped.
    assert len(roundtrip_results) == 16


# --------------------------------------------------------------------------------------
# Task 3: same-engine zero-diff verification via the existing harness -- reused, not
# reinvented (harness/render_diff.render_all, harness/masked_diff.masked_pixel_diff).
# --------------------------------------------------------------------------------------

# One representative document per Task 3's four named structural categories.
# irs_1040_instructions.pdf's own manifest categories cover three at once
# (contents_array, form_xobjects, type0_identity_h); TYPE3_FIXTURE covers the fourth.
_HARNESS_DOCS = [IRS_1040_INSTRUCTIONS, TYPE3_FIXTURE]
_HARNESS_PAGE_INDEX = 0
_ENGINE_LABELS = ("pdfium", "poppler", "mupdf")


@pytest.mark.parametrize("doc_path", _HARNESS_DOCS, ids=lambda p: p.name)
@pytest.mark.parametrize(
    "rewrite_fn", [identity_rewrite, null_edit_rewrite], ids=lambda f: f.__name__
)
def test_rewrite_harness_zero_diff(doc_path: Path, rewrite_fn, tmp_path: Path) -> None:
    """Task 3: render the original page and the rewritten page with all three
    engines, and assert masked_pixel_diff() == 0 (zero tolerance, no blur, no
    channel-tolerance -- the SAME rasterizer rendering the same unedited pixels
    twice, per harness/run_corpus_harness.py's own module docstring)."""
    rewritten = tmp_path / "rewritten.pdf"
    rewrite_fn(doc_path, str(rewritten))

    orig_pngs = render_all(doc_path, _HARNESS_PAGE_INDEX, tmp_path / "orig")
    new_pngs = render_all(rewritten, _HARNESS_PAGE_INDEX, tmp_path / "new")

    for label, orig_png, new_png in zip(_ENGINE_LABELS, orig_pngs, new_pngs):
        diff = masked_pixel_diff(orig_png, new_png)
        assert diff == 0, (
            f"{doc_path.name} page {_HARNESS_PAGE_INDEX} ({rewrite_fn.__name__}, "
            f"{label}): expected zero pixel diff, got {diff}"
        )
