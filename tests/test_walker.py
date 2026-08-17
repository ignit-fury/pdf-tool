"""Tests for engine.playa_boundary -- the two-pass ObjectParser/LazyInterpreter zip over a
page's coalesced /Contents.

This file imports `playa` and `pikepdf` directly (permitted outside `engine/` -- the
one-module boundary rule in engine/playa_boundary.py's docstring only restricts files under
engine/) to construct documents and drive `walk_page`.

## History (read before touching anything below)

The original per-part design (`walk_part`, one independent ObjectParser/LazyInterpreter per
`/Contents` part) desynced the alignment tripwire on 46/217 corpus documents: a text-showing
operator's operand array can close in one part while its keyword opens the next (legal per
ISO 32000-1 7.8.2). The 2026-08-13 ruling in `.planning/phases/02-text-model/02-04-PLAN.md`
replaced it with `walk_page`, which coalesces a page's parts with a `b"\\n"` separator into
one buffer before parsing either pass (see engine/playa_boundary.py's module docstring for
the full mechanism and why naive `b"".join` is not the fix -- it fuses tokens across the
boundary instead, qpdf #444).

Fixing the part-boundary issue exposed a second, orthogonal one on 5/217 documents: playa's
own `do_TJ` (interp.py) emits no TextObject for a text-showing operator whose string operand
is entirely empty (`() Tj`). `operator_table` now applies the identical gate.

With both fixes, the alignment tripwire fires on **zero** of the 217 public corpus documents.
No allowlist. `test_curpos_alignment_holds_across_corpus` asserts this directly.

Two *other* documents fail for reasons unrelated to alignment, each its own separate finding
(not folded into any allowlist): `irs_form_w9_encrypted.pdf` needs the optional `cryptography`
package (playa-pdf[crypto]) to open at all, and `govdocs1_011_011089.pdf` raises a
PDFSyntaxError from `ObjectParser`'s inline-image (BI...ID...EI) handling, unrelated to text
operators. See task-1-report.md.
"""

import json
from pathlib import Path

import pikepdf
import playa
import pytest
from playa.exceptions import PDFEncryptionError
from playa.parser import ObjectParser
from playa.pdftypes import PSKeyword

from engine.index import DocumentTooLargeError, RunIndex
from engine.playa_boundary import _coalesce_parts, walk_page

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"

# Not an alignment issue: playa-pdf 1.1.0 cannot open this file without the optional
# `cryptography` extra (`pip install playa-pdf[crypto]`), not installed as a runtime
# dependency here. Its own finding, not a workaround for the tripwire.
KNOWN_UNOPENABLE_FILES = frozenset({"irs_form_w9_encrypted.pdf"})

# Not an alignment issue: raises before ever reaching walk_page's assertion, from an
# inline-image tokenisation edge case inside ObjectParser itself. Its own finding.
KNOWN_OTHER_ERROR_FILES = frozenset({"govdocs1_011_011089.pdf"})


def test_walk_page_first_kw_off_irs_form_w9() -> None:
    """corpus/public/irs_form_w9.pdf page 0's first text-showing operator is a Tj whose
    keyword starts at byte 204 -- the number 02-RESEARCH.md Section 8 verified directly
    (buffer[174:210] == b'...Tm\\n(Form  )Tj\\n/T1', byte 204 is the 'T' of 'Tj'). Page 0 has
    a single /Contents part, so its offset-within-part equals the pre-coalescing value."""
    doc = playa.open(str(CORPUS_DIR / "irs_form_w9.pdf"))
    page = doc.pages[0]

    part_offset, part_index, operands, text_obj = next(walk_page(page, doc))

    assert part_offset == 204


@pytest.mark.corpus
def test_curpos_alignment_holds_across_corpus() -> None:
    """Walk every page of every public corpus document; the alignment tripwire must fire on
    NONE of them -- no allowlist. Two other, non-alignment failure categories are recorded
    separately (see module docstring) so they can't mask a real alignment regression, and
    their own sets must not grow beyond what's already been diagnosed and reported."""
    manifest = json.loads((REPO_ROOT / "corpus" / "manifest.json").read_text())

    unopenable: set[str] = set()
    desynced: set[str] = set()
    other_errors: dict[str, str] = {}

    for entry in manifest:
        filename = entry["filename"]
        try:
            doc = playa.open(str(CORPUS_DIR / filename))
        except PDFEncryptionError:
            unopenable.add(filename)
            continue

        try:
            for page in doc.pages:
                for _ in walk_page(page, doc):
                    pass
        except AssertionError:
            desynced.add(filename)
        except Exception as exc:  # noqa: BLE001 - classified below, not swallowed
            other_errors[filename] = f"{type(exc).__name__}: {exc}"

    assert desynced == set(), f"alignment tripwire fired on: {sorted(desynced)}"
    assert unopenable == KNOWN_UNOPENABLE_FILES, (
        f"unopenable-file set changed: new={unopenable - KNOWN_UNOPENABLE_FILES} "
        f"missing={KNOWN_UNOPENABLE_FILES - unopenable}"
    )
    assert set(other_errors) == KNOWN_OTHER_ERROR_FILES, (
        f"other-error set changed: new={set(other_errors) - KNOWN_OTHER_ERROR_FILES} "
        f"missing={KNOWN_OTHER_ERROR_FILES - set(other_errors)}; details={other_errors}"
    )



# 02-09-PLAN.md Task 3: the two failure sets below are for RunIndex -- the fully composed
# walker -> encoding-table -> clusterer -> classify_page/classify_run pipeline -- discovered
# by actually running the sweep (never assumed from KNOWN_UNOPENABLE_FILES/
# KNOWN_OTHER_ERROR_FILES above, which were measured against the raw walker only; RunIndex
# composes four more stages that could newly fail or newly succeed). Measured 2026-08-17:
# identical files, same underlying causes -- see the test's own docstring.
KNOWN_RUNINDEX_UNOPENABLE_FILES = frozenset({"irs_form_w9_encrypted.pdf"})
KNOWN_RUNINDEX_OTHER_ERROR_FILES = frozenset({"govdocs1_011_011089.pdf"})


@pytest.mark.corpus
def test_full_pipeline_walks_full_corpus_without_exception() -> None:
    """TEXT-01: `RunIndex` -- walker, encoding table, clusterer and classify_page/
    classify_run composed for the first time -- walks every page of every public corpus
    document without an unhandled exception. One layer up from
    `test_curpos_alignment_holds_across_corpus` above (raw walker only) and
    `test_cluster_page_walks_full_corpus_without_exception` in test_clustering.py (walker +
    clusterer only).

    Three separate failure categories (02-09-PLAN.md Task 3 / task-3-brief.md), never folded
    together: construction failures (`RunIndex.__init__` -- pikepdf.open/playa-open failing
    before any page is touched), per-page failures (an exception from `.page(n)` that is not
    `DocumentTooLargeError`), and `DocumentTooLargeError` itself (T-02-01's own pathological-
    document abort -- an intentional guard firing, not a bug, so it must never silently land
    in "other errors").

    Measured 2026-08-17 by actually running RunIndex over all 217 manifest documents (the
    plan text says 216; the manifest -- and this file's own module docstring for the raw-
    walker sweep -- says 217, so 217 is what's asserted below): RunIndex fully succeeds on
    215 documents (8,247 pages, 1,149,704 runs). The other two are IDENTICAL to
    KNOWN_UNOPENABLE_FILES/KNOWN_OTHER_ERROR_FILES above, for the same underlying reasons,
    not new failures introduced by encoding-table/clustering/classification:
    `irs_form_w9_encrypted.pdf` fails at construction (`RunIndex.__init__` opens playa eagerly,
    same PDFEncryptionError as the raw sweep -- missing optional `cryptography` extra) before
    any page-level stage ever runs; `govdocs1_011_011089.pdf` fails inside the walker's own
    ObjectParser (inline-image handling) before reaching a text operator, so it surfaces as a
    per-page failure here too. No `DocumentTooLargeError` fires on any current public-corpus
    document.

    Per-page failures store `type(exc).__name__` ONLY, deviating from this file's own
    `f"{type(exc).__name__}: {exc}"` convention used elsewhere (see module docstring):
    confirmed by inspection that `govdocs1_011_011089.pdf`'s PDFSyntaxError embeds a raw
    `[(offset, byte), ...]` dump of the surrounding content-stream bytes in its own message --
    the same embedding test_clustering.py's sweep already documented and worked around for
    this same file. Construction failures keep `str(exc)`: PDFEncryptionError's message is a
    fixed, generic string naming the missing package, no document content.

    Goes red if: RunIndex raises on any corpus document not already in one of the three known
    sets below, if a set changes size, or if total_runs collapses -- pinned as a lower bound
    (1,149,704 measured), mirroring test_cluster_page_walks_full_corpus_without_exception's
    own guard against a stub-return regression.
    """
    manifest = json.loads((REPO_ROOT / "corpus" / "manifest.json").read_text())
    assert len(manifest) == 217, f"manifest size changed: now {len(manifest)} documents"

    construction_failures: dict[str, str] = {}
    page_failures: dict[str, str] = {}
    pathological: set[str] = set()
    total_runs = 0

    for entry in manifest:
        filename = entry["filename"]
        try:
            index = RunIndex(CORPUS_DIR / filename)
        except Exception as exc:  # noqa: BLE001 - classified below, not swallowed
            construction_failures[filename] = f"{type(exc).__name__}: {exc}"
            continue

        with index:
            try:
                for page_index in range(index.page_count):
                    total_runs += len(index.page(page_index).runs)
            except DocumentTooLargeError:
                pathological.add(filename)
            except Exception as exc:  # noqa: BLE001 - classified below, not swallowed
                page_failures[filename] = type(exc).__name__

    assert set(construction_failures) == KNOWN_RUNINDEX_UNOPENABLE_FILES, (
        f"construction-failure set changed: "
        f"new={set(construction_failures) - KNOWN_RUNINDEX_UNOPENABLE_FILES} "
        f"missing={KNOWN_RUNINDEX_UNOPENABLE_FILES - set(construction_failures)}"
    )
    assert set(page_failures) == KNOWN_RUNINDEX_OTHER_ERROR_FILES, (
        f"page-failure set changed: new={set(page_failures) - KNOWN_RUNINDEX_OTHER_ERROR_FILES} "
        f"missing={KNOWN_RUNINDEX_OTHER_ERROR_FILES - set(page_failures)}; "
        f"details={page_failures}"
    )
    assert pathological == set(), f"unexpected DocumentTooLargeError on: {sorted(pathological)}"
    # [VERIFIED 2026-08-17] 215 documents fully walked, 8,247 pages, 1,149,704 total runs.
    # Pinned well under that as a lower bound, not an exact match -- a RunIndex.page() that
    # silently returned an empty run list would otherwise pass every assertion above.
    assert total_runs > 100_000, f"corpus run count collapsed to {total_runs}"


def test_naive_join_fuses_qbt_govdocs1_002_002167() -> None:
    """TEXT-07: proves the b"\\n" separator is load-bearing, not cosmetic, on the file
    02-RESEARCH.md Section 6 names for this exact bug. Page 0's /Contents array has a
    1-byte "Q" part immediately followed by a part starting "BT" -- confirmed at the raw
    byte level via pikepdf's read_bytes() (strict /Length: exactly b'Q', no trailing byte).
    Naive b"".join glues them into the single fused keyword "QBT" (qpdf #444); the
    b"\\n"-separated join (matching what walk_page's _coalesce_parts does) does not.

    Uses pikepdf's raw stream bytes rather than playa's `.buffer`: playa reads slightly past
    a stream's declared /Length up to the actual `endstream` marker, and for this file's two
    1-byte parts that incidentally captures a trailing whitespace byte already in the file --
    so via playa's own (generous) buffer reads, this specific file no longer reproduces the
    fusion. The underlying risk is still real through playa's buffers too (reproduced
    separately on govdocs1_008_008012.pdf, see task-1-report.md); this test reproduces the
    exact, named, spec-level bug against the file's true declared stream content.
    """
    pdf = pikepdf.open(CORPUS_DIR / "govdocs1_002_002167.pdf")
    contents = pdf.pages[0].obj["/Contents"]
    raw_parts = [s.read_bytes() for s in contents]

    naive = b"".join(raw_parts)
    separated = b"\n".join(raw_parts)

    doc = playa.open(str(CORPUS_DIR / "govdocs1_002_002167.pdf"))

    def keyword_names(buffer: bytes) -> list[bytes]:
        return [
            obj.name for _pos, obj in ObjectParser(buffer, doc) if isinstance(obj, PSKeyword)
        ]

    naive_tokens = keyword_names(naive)
    separated_tokens = keyword_names(separated)

    assert b"QBT" in naive_tokens
    assert b"QBT" not in separated_tokens
    assert naive_tokens != separated_tokens
    # The fusion also costs a token: "Q" + "BT" (2 tokens) become "QBT" (1 token).
    assert len(separated_tokens) == len(naive_tokens) + 1


def test_coalesce_parts_prevents_fusion_govdocs1_008_008012() -> None:
    """TEXT-07, driving the actual code under guard: the QBT test above proves the bug
    against pikepdf's raw bytes, but never calls `_coalesce_parts` or `walk_page` --  if the
    separator were silently dropped from `_coalesce_parts`, that test would never notice.
    This one calls `_coalesce_parts` directly and reproduces a token fusion that IS
    observable through playa's own `.buffer` (unlike the govdocs1_002_002167.pdf case,
    where playa's generous past-/Length reading happens to add protective whitespace --
    see that test's docstring): page 24 has a part ending "q" immediately followed by a
    part starting "1", which naive b"".join fuses into the single wrong keyword "q1",
    one token short of the correct count."""
    doc = playa.open(str(CORPUS_DIR / "govdocs1_008_008012.pdf"))
    page = list(doc.pages)[24]
    parts = list(page.streams)

    naive = b"".join(bytes(p.buffer) for p in parts)
    joined, _part_ranges = _coalesce_parts(parts)

    def keyword_names(buffer: bytes) -> list[bytes]:
        return [
            obj.name for _pos, obj in ObjectParser(buffer, doc) if isinstance(obj, PSKeyword)
        ]

    naive_tokens = keyword_names(naive)
    joined_tokens = keyword_names(joined)

    assert b"q1" in naive_tokens
    assert b"q1" not in joined_tokens
    assert len(joined_tokens) == len(naive_tokens) + 1
