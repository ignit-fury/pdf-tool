"""TEXT-01 / TEXT-02: glyph_records emits fully-provenanced records over the whole corpus.

Exclusion sets are duplicated from tests/test_walker.py rather than imported: they are
assertions about what is currently known-broken, and each test must fail independently if
its own set grows. Sharing them would let one test's newly-diagnosed failure silently
widen the other's allowance.
"""

import json
from pathlib import Path

import playa
import pytest
from playa.exceptions import PDFEncryptionError

from engine.walker import glyph_records

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"

# Same two documented, diagnosed non-alignment failures Task 1 established (see
# tests/test_walker.py's module docstring). Named exclusions, never a silent try/except.
KNOWN_UNOPENABLE_FILES = frozenset({"irs_form_w9_encrypted.pdf"})
KNOWN_OTHER_ERROR_FILES = frozenset({"govdocs1_011_011089.pdf"})

# Fields that must never be None on any glyph. glyph, unicode and item_index_within_tj are
# deliberately absent: glyph is 02-06's encoding table, unicode is absent for glyphs with no
# ToUnicode mapping, item_index_within_tj is None for every non-TJ operator.
ALWAYS_POPULATED = (
    "code",
    "x",
    "y",
    "advance",
    "font_id",
    "render_mode",
    "visible",
    "stream_id",
    "operator_byte_offset",
    "byte_offset_within_string",
)


def test_all_provenance_fields_populated() -> None:
    """TEXT-02: every field that must be populated is, on a real page.

    Goes red if: any ALWAYS_POPULATED name is dropped from GlyphRecord's construction in
    walker.py and defaulted to None -- verified by temporarily passing `x=None`, which
    fails this test (and mypy) rather than passing quietly. Also goes red if
    ALWAYS_POPULATED names a field GlyphRecord does not have, via the getattr below.
    """
    with playa.open(str(CORPUS_DIR / "irs_form_w9.pdf")) as doc:
        records = glyph_records(doc.pages[0], doc)

    assert records, "expected a non-empty glyph stream on irs_form_w9.pdf page 0"

    for rec in records:
        for field in ALWAYS_POPULATED:
            assert getattr(rec, field) is not None, (
                f"{field} was None on a glyph at part {rec.stream_id} "
                f"operator offset {rec.operator_byte_offset}"
            )
        assert isinstance(rec.advance, tuple) and len(rec.advance) == 2
        assert rec.byte_offset_within_string >= 0


def test_byte_offset_within_string_indexes_the_real_string() -> None:
    """The provenance field with actual teeth: byte_offset_within_string must address the
    glyph's own byte inside its own string operand, not a buffer position and not an
    ordinal.

    irs_form_w9.pdf page 0's first text-showing operator is `(Form  )Tj` at keyword offset
    204 (Task 1's test_walk_page_first_kw_off_irs_form_w9 pins the offset). Its font is a
    simple font, so code N sits at byte N of the string: the first four glyphs must report
    offsets 0,1,2,3 with codes spelling "Form".

    Goes red if: walker.py counts a running ordinal across the operator instead of
    restarting per string, or reports a joined-buffer offset (which would be ~204+, not
    0..3) -- both of which are the exact mistakes the operand-offset removal was about.
    """
    with playa.open(str(CORPUS_DIR / "irs_form_w9.pdf")) as doc:
        records = glyph_records(doc.pages[0], doc)

    first_op = [r for r in records if r.operator_byte_offset == 204]
    assert len(first_op) >= 4

    assert [r.byte_offset_within_string for r in first_op[:4]] == [0, 1, 2, 3]
    assert "".join(r.unicode or "" for r in first_op[:4]) == "Form"
    # A Tj carries one string and no array, so no glyph of it has a TJ item index.
    assert all(r.item_index_within_tj is None for r in first_op)


@pytest.mark.corpus
def test_walks_full_corpus_without_exception() -> None:
    """TEXT-01: glyph_records walks every page of every corpus document without exception.

    Covers strictly more than Task 1's operator-level tripwire: this also exercises
    walker's own _assert_glyph_alignment, which catches a font whose decoder and CMap
    disagree on byte consumption -- a desync invisible at the operator level.

    Goes red if: _assert_glyph_alignment starts firing (a playa upgrade changing decode
    semantics), or either known-failure set grows or shrinks.
    """
    manifest = json.loads((REPO_ROOT / "corpus" / "manifest.json").read_text())

    unopenable: set[str] = set()
    desynced: set[str] = set()
    other_errors: dict[str, str] = {}
    total_glyphs = 0

    for entry in manifest:
        filename = entry["filename"]
        try:
            doc = playa.open(str(CORPUS_DIR / filename))
        except PDFEncryptionError:
            unopenable.add(filename)
            continue

        try:
            for page in doc.pages:
                total_glyphs += len(glyph_records(page, doc))
        except AssertionError:
            desynced.add(filename)
        except Exception as exc:  # noqa: BLE001 - classified below, not swallowed
            other_errors[filename] = f"{type(exc).__name__}: {exc}"

    assert desynced == set(), f"glyph/operand desync on: {sorted(desynced)}"
    assert unopenable == KNOWN_UNOPENABLE_FILES, (
        f"unopenable-file set changed: new={unopenable - KNOWN_UNOPENABLE_FILES} "
        f"missing={KNOWN_UNOPENABLE_FILES - unopenable}"
    )
    assert set(other_errors) == KNOWN_OTHER_ERROR_FILES, (
        f"other-error set changed: new={set(other_errors) - KNOWN_OTHER_ERROR_FILES} "
        f"missing={KNOWN_OTHER_ERROR_FILES - set(other_errors)}; details={other_errors}"
    )
    # Pinned lower bound, not >= 0: a walker that silently emitted nothing would otherwise
    # pass every assertion above. Measured 21,312,545 across 215 documents.
    assert total_glyphs > 21_000_000, f"corpus glyph count collapsed to {total_glyphs}"
