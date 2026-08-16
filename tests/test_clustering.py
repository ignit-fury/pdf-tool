"""02-07 Task 2: engine/clusterer.py -- bands, sort, break rules, synthetic spaces, sub-runs.

Two families of fixtures:
- Directly-constructed GlyphRecord/ClusterAttrs/StreamPath triples for the D-01/D-02/D-03/
  D-05 break-rule unit tests. `cluster_page`'s real input shape IS these three plain
  dataclasses, not a pikepdf/playa object, so building them by hand exercises the same code
  path a real walk would, without needing a font program or a Type3 CharProc just to
  synthesize one bad-glyph signal.
- Inline pikepdf fixtures, parsed through playa and the real walker, for the two cases the
  acceptance criteria name explicitly: the corpus's own glyph-at-a-time Form XObject, and a
  synthetic two-column page ("constructed inline in the test via pikepdf" per the
  acceptance criteria's own wording).
"""

import hashlib
import io
import json
import unicodedata
from pathlib import Path

import pikepdf
import playa
import pytest
from playa.exceptions import PDFEncryptionError

from engine.clusterer import _gaps_em, cluster_page
from engine.encoding_table import FontVerdict, GlyphVerdict, glyph_verdict
from engine.records import ClusterAttrs, GlyphRecord
from engine.run_id import decode_run_id
from engine.space_threshold import BREAK_EM
from engine.types import CharCode, Unicode
from engine.walker import StreamPath, located_cluster_records

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"

# Any 64 hex chars: these tests exercise clustering, not the source-hash half of a run ID
# (tests/test_run_id.py already covers that half).
FAKE_HASH = "0" * 64

PATH0 = StreamPath(page=0)


def _record(
    *,
    x: float,
    y: float,
    code: int = 1,
    unicode: str | None = "A",
    advance: tuple[float, float] = (10.0, 0.0),
    font_id: int = 0,
    render_mode: int = 0,
    stream_id: int = 0,
    byte_offset: int = 0,
) -> GlyphRecord:
    return GlyphRecord(
        code=CharCode(code),
        glyph=None,
        unicode=Unicode(unicode) if unicode is not None else None,
        x=x,
        y=y,
        advance=advance,
        font_id=font_id,
        render_mode=render_mode,
        visible=render_mode not in (3, 7),
        stream_id=stream_id,
        operator_byte_offset=byte_offset,
        item_index_within_tj=None,
        byte_offset_within_string=0,
    )


def _attrs(
    *,
    fill_color: tuple[tuple[float, ...], str | None] = ((0.0, 0.0, 0.0), None),
    rise: float = 0.0,
    effective_em: float = 12.0,
    direction: tuple[float, float] = (12.0, 0.0),
) -> ClusterAttrs:
    return ClusterAttrs(
        fill_color=fill_color, rise=rise, effective_em=effective_em, direction=direction
    )


def _accept_all(record: GlyphRecord) -> GlyphVerdict:
    return GlyphVerdict(True, None)


# ---------------------------------------------------------------------------
# D-01: font / size / rise / visibility / colour break conditions
# ---------------------------------------------------------------------------


def test_font_change_breaks_run() -> None:
    located = [
        (PATH0, _record(x=0.0, y=100.0, unicode="A", font_id=0, byte_offset=10), _attrs()),
        (PATH0, _record(x=10.0, y=100.0, unicode="B", font_id=1, byte_offset=16), _attrs()),
    ]
    runs = cluster_page(0, located, FAKE_HASH, _accept_all)
    assert [r.display_text for r in runs] == ["A", "B"]


def test_size_change_over_one_percent_breaks_run() -> None:
    located = [
        (PATH0, _record(x=0.0, y=100.0, unicode="A", byte_offset=10), _attrs(effective_em=12.0)),
        (PATH0, _record(x=10.0, y=100.0, unicode="B", byte_offset=16), _attrs(effective_em=13.0)),
    ]
    runs = cluster_page(0, located, FAKE_HASH, _accept_all)
    assert [r.display_text for r in runs] == ["A", "B"]


def test_size_change_under_one_percent_does_not_break_run() -> None:
    located = [
        (PATH0, _record(x=0.0, y=100.0, unicode="A", byte_offset=10), _attrs(effective_em=12.0)),
        (PATH0, _record(x=10.0, y=100.0, unicode="B", byte_offset=16), _attrs(effective_em=12.05)),
    ]
    runs = cluster_page(0, located, FAKE_HASH, _accept_all)
    assert len(runs) == 1
    assert runs[0].display_text == "AB"


def test_large_rise_change_breaks_run() -> None:
    """CONTROLLER CORRECTION 2026-08-14 (pre-Task-3, .superpowers/sdd/02-01-PLAN/progress.md):
    this test originally asserted that a 3.0 rise delta on a 12.0 em (a fraction of 0.25 em,
    well UNDER the 0.5em line-break threshold, with forward advance intact) broke the run --
    that is a textbook SUPERSCRIPT per Section 3, and should NOT break. The docstring even
    named "no horizontal reset" as the condition while asserting a break, which is the
    superscript rule's own negation. Renamed and re-fixtured to an unambiguous line-break
    case: a rise delta of 7.0 on a 12.0 em is 0.583 em, past the 0.5em threshold -- a real
    baseline shift, not a superscript, and must break regardless of forward advance.
    `y` differs only slightly (well inside the 0.2em band tolerance, so the two glyphs land
    in the SAME baseline band) so this isolates the explicit rise/superscript check as the
    mechanism, rather than incidental band separation. See
    test_small_rise_change_with_forward_advance_does_not_break_run for the superscript
    positive case this correction made possible.
    """
    located = [
        (PATH0, _record(x=0.0, y=100.0, unicode="A", byte_offset=10), _attrs(rise=0.0)),
        (PATH0, _record(x=10.0, y=101.0, unicode="2", byte_offset=16), _attrs(rise=7.0)),
    ]
    runs = cluster_page(0, located, FAKE_HASH, _accept_all)
    assert [r.display_text for r in runs] == ["A", "2"]


def test_small_rise_change_with_forward_advance_does_not_break_run() -> None:
    """The superscript case Section 3 names explicitly: `Ts` becomes nonzero (rise 0.0 ->
    3.0, a fraction of 0.25 em on a 12.0 em -- under the 0.5em threshold) WITH forward
    advance intact (x continues 0.0 -> 10.0, no horizontal reset). D-01/D-02: this must
    stay ONE run, not split into a base run and a superscript run.

    MUTATION: reverting `_is_line_break_not_superscript` to `attrs.rise !=
    prev_attrs.rise` (unconditional) turns this red -- confirmed by running it against the
    pre-correction predicate before restoring the fix.
    """
    located = [
        (PATH0, _record(x=0.0, y=100.0, unicode="x", byte_offset=10), _attrs(rise=0.0)),
        (PATH0, _record(x=10.0, y=100.0, unicode="2", byte_offset=16), _attrs(rise=3.0)),
    ]
    runs = cluster_page(0, located, FAKE_HASH, _accept_all)
    assert len(runs) == 1
    assert runs[0].display_text == "x2"


def test_visibility_transition_breaks_run() -> None:
    """Tr 0 (fill, visible) -> Tr 3 (neither fill nor stroke, invisible) crosses the
    visible/invisible boundary and must break."""
    located = [
        (PATH0, _record(x=0.0, y=100.0, unicode="A", render_mode=0, byte_offset=10), _attrs()),
        (PATH0, _record(x=10.0, y=100.0, unicode="B", render_mode=3, byte_offset=16), _attrs()),
    ]
    runs = cluster_page(0, located, FAKE_HASH, _accept_all)
    assert [r.display_text for r in runs] == ["A", "B"]


def test_stroke_mode_change_does_not_break_run() -> None:
    """D-01's negative case, and the trap this task exists to catch: Tr 0 (fill) -> Tr 1
    (stroke) are BOTH visible and must cluster together. Only a visible<->invisible
    TRANSITION breaks a run -- never a raw render_mode value change."""
    located = [
        (PATH0, _record(x=0.0, y=100.0, unicode="A", render_mode=0, byte_offset=10), _attrs()),
        (PATH0, _record(x=10.0, y=100.0, unicode="B", render_mode=1, byte_offset=16), _attrs()),
    ]
    runs = cluster_page(0, located, FAKE_HASH, _accept_all)
    assert len(runs) == 1, "Tr 0 -> Tr 1 are both visible and must not split the run"
    assert runs[0].display_text == "AB"


def test_fill_colour_change_breaks_run() -> None:
    """D-01's extension: only FILL colour breaks a run."""
    located = [
        (
            PATH0,
            _record(x=0.0, y=100.0, unicode="A", byte_offset=10),
            _attrs(fill_color=((0.0, 0.0, 0.0), None)),
        ),
        (
            PATH0,
            _record(x=10.0, y=100.0, unicode="B", byte_offset=16),
            _attrs(fill_color=((1.0, 0.0, 0.0), None)),
        ),
    ]
    runs = cluster_page(0, located, FAKE_HASH, _accept_all)
    assert [r.display_text for r in runs] == ["A", "B"]


# ---------------------------------------------------------------------------
# D-03: gap-driven synthetic spaces and run breaks
# ---------------------------------------------------------------------------


def test_gap_between_k_em_and_break_em_inserts_synthetic_space() -> None:
    # em=12, gap_em=0.2 -> gap of 2.4 units after glyph A's advance-10 end.
    located = [
        (PATH0, _record(x=0.0, y=100.0, unicode="A", byte_offset=10), _attrs()),
        (PATH0, _record(x=12.4, y=100.0, unicode="B", byte_offset=16), _attrs()),
    ]
    runs = cluster_page(0, located, FAKE_HASH, _accept_all)
    assert len(runs) == 1
    assert runs[0].display_text == "A B"


def test_gap_at_or_below_k_em_does_not_insert_space() -> None:
    # gap_em=0.05 -> gap of 0.6 units.
    located = [
        (PATH0, _record(x=0.0, y=100.0, unicode="A", byte_offset=10), _attrs()),
        (PATH0, _record(x=10.6, y=100.0, unicode="B", byte_offset=16), _attrs()),
    ]
    runs = cluster_page(0, located, FAKE_HASH, _accept_all)
    assert len(runs) == 1
    assert runs[0].display_text == "AB"


def test_gap_over_break_em_breaks_run() -> None:
    # gap_em=0.5 -> gap of 6 units, over BREAK_EM (0.33).
    located = [
        (PATH0, _record(x=0.0, y=100.0, unicode="A", byte_offset=10), _attrs()),
        (PATH0, _record(x=16.0, y=100.0, unicode="B", byte_offset=16), _attrs()),
    ]
    runs = cluster_page(0, located, FAKE_HASH, _accept_all)
    assert [r.display_text for r in runs] == ["A", "B"]


def test_direction_reversal_breaks_run() -> None:
    """After Step 1's sort, a large NEGATIVE gap means overlap -- the sorted glyph's origin
    sits well inside the previous glyph's own advance -- which is the pdf.js
    negativeSpaceMax rule applied to the sorted (not stream) sequence."""
    located = [
        (PATH0, _record(x=0.0, y=100.0, unicode="A", byte_offset=10), _attrs()),
        (PATH0, _record(x=4.0, y=100.0, unicode="B", byte_offset=16), _attrs()),
    ]
    runs = cluster_page(0, located, FAKE_HASH, _accept_all)
    assert [r.display_text for r in runs] == ["A", "B"]


# ---------------------------------------------------------------------------
# D-02 / D-05: bad-glyph sub-run splitting and addressing
# ---------------------------------------------------------------------------


def test_bad_glyph_splits_run_into_locked_and_editable_subruns() -> None:
    """D-05: a glyph with no /ToUnicode mapping (unicode falsy) locks only itself; the
    surrounding editable text stays editable as two separate sub-runs. D-02: all three
    fragments share ONE anchor -- the logical run's first glyph (part 0, byte offset 10) --
    disambiguated only by `subrange`, a half-open index range into the original unsplit
    run's own glyph list.
    """
    located = [
        (PATH0, _record(x=0.0, y=100.0, code=1, unicode="A", byte_offset=10), _attrs()),
        (PATH0, _record(x=10.0, y=100.0, code=2, unicode=None, byte_offset=16), _attrs()),
        (PATH0, _record(x=20.0, y=100.0, code=3, unicode="B", byte_offset=22), _attrs()),
    ]
    font_verdict = FontVerdict("T1-a", True, False)
    runs = cluster_page(0, located, FAKE_HASH, lambda r: glyph_verdict(font_verdict, r))

    assert [r.display_text for r in runs] == ["A", "", "B"]
    decoded = [decode_run_id(r.run_id) for r in runs]
    assert all(d["part"] == 0 and d["byte_offset"] == 10 for d in decoded), (
        "every fragment of one logical run must share the SAME anchor"
    )
    assert [d["subrange"] for d in decoded] == [(0, 1), (1, 2), (2, 3)]


def test_editable_run_with_no_bad_glyph_has_no_subrange() -> None:
    """A run untouched by D-05 gets subrange=None -- only a SPLIT run's fragments use it."""
    located = [
        (PATH0, _record(x=0.0, y=100.0, unicode="A", byte_offset=10), _attrs()),
        (PATH0, _record(x=10.0, y=100.0, unicode="B", byte_offset=16), _attrs()),
    ]
    runs = cluster_page(0, located, FAKE_HASH, _accept_all)
    assert len(runs) == 1
    assert decode_run_id(runs[0].run_id)["subrange"] is None


# ---------------------------------------------------------------------------
# StreamPath grouping -- a run must never span two different streams
# ---------------------------------------------------------------------------


def test_run_never_spans_two_stream_paths() -> None:
    """Two glyphs that would otherwise cluster (adjacent, same style) but come from
    different StreamPaths (here: page /Contents vs. inside Form XObject 5) must never merge
    -- they are different physical byte ranges and encode_run_id has room for only one
    `:c{part}` anchor."""
    path_a = StreamPath(page=0)
    path_b = StreamPath(page=0, xobj_path=(5,))
    located = [
        (path_a, _record(x=0.0, y=100.0, unicode="A", byte_offset=10), _attrs()),
        (path_b, _record(x=10.0, y=100.0, unicode="B", byte_offset=10), _attrs()),
    ]
    runs = cluster_page(0, located, FAKE_HASH, _accept_all)
    assert len(runs) == 2
    assert {r.display_text for r in runs} == {"A", "B"}


# ---------------------------------------------------------------------------
# Rotated text (02-RESEARCH.md Section 3, "Rotated text")
# ---------------------------------------------------------------------------


def test_rotated_text_bands_independently_by_angle() -> None:
    """A horizontal run and a 90-degree-rotated (vertical) run must band and cluster
    independently -- each along its own reading direction, never projected onto raw device
    x/y."""
    horiz = _attrs(direction=(12.0, 0.0))
    vert = _attrs(direction=(0.0, 12.0))
    located = [
        (PATH0, _record(x=0.0, y=100.0, unicode="A", byte_offset=10), horiz),
        (PATH0, _record(x=10.0, y=100.0, unicode="B", byte_offset=16), horiz),
        (PATH0, _record(x=200.0, y=200.0, unicode="C", advance=(0.0, 10.0), byte_offset=22), vert),
        (PATH0, _record(x=200.0, y=210.0, unicode="D", advance=(0.0, 10.0), byte_offset=28), vert),
    ]
    runs = cluster_page(0, located, FAKE_HASH, _accept_all)
    assert {r.display_text for r in runs} == {"AB", "CD"}


# ---------------------------------------------------------------------------
# Acceptance criteria: the real corpus glyph-at-a-time fixture, and a synthetic two-column
# page proving Pitfall 3's sort-before-break requirement.
# ---------------------------------------------------------------------------


def test_irs_1040_glyph_at_a_time_clusters_into_one_run() -> None:
    """irs_1040_instructions.pdf's Form XObject /I1 draws its cover headline "Futu" then
    "r" as consecutive Tj operators at byte offsets 673/679 -- glyph-at-a-time, the other
    Gate G1 case. D-01 handles it for free: nothing here assumes one text-showing operator
    produces one run."""
    path = CORPUS_DIR / "irs_1040_instructions.pdf"
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    with playa.open(str(path)) as doc:
        page = doc.pages[0]
        located = list(located_cluster_records(page, 0, doc))

    runs = cluster_page(0, located, source_hash, _accept_all)
    matches = [r for r in runs if r.display_text.startswith("Futur")]
    assert len(matches) == 1, (
        f"expected exactly one run starting 'Futur...' among {len(runs)} runs, got "
        f"{len(matches)} matches"
    )


def _helvetica() -> pikepdf.Dictionary:
    return pikepdf.Dictionary(
        Type=pikepdf.Name.Font,
        Subtype=pikepdf.Name.Type1,
        BaseFont=pikepdf.Name.Helvetica,
    )


def _parse(pdf: pikepdf.Pdf) -> playa.Document:
    buf = io.BytesIO()
    pdf.save(buf)
    return playa.parse(buf.getvalue())


def _two_column_fixture() -> tuple[playa.Document, playa.Page]:
    """Two independent columns at the SAME baseline, glyphs emitted INTERLEAVED in stream
    order (A, B, A, B, ...) -- exactly 02-RESEARCH.md Section 3's "Two-column layout"
    shape: producers commonly emit both columns interleaved, so gaps computed in stream
    order alternate between huge positive and huge negative values."""
    # 8.0 units/glyph deliberately tracks Helvetica 12pt's real "A"/"B" advance (667/1000 *
    # 12 = 8.004) closely enough that the measured intra-column gap stays under K_EM -- this
    # fixture is about the two-column break, not the synthetic-space threshold.
    pdf = pikepdf.Pdf.new()
    ops = [b"BT /Helv 12 Tf\n"]
    for i in range(4):
        ops.append(f"1 0 0 1 {i * 8.0} 700 Tm (A) Tj\n".encode())
        ops.append(f"1 0 0 1 {300 + i * 8.0} 700 Tm (B) Tj\n".encode())
    ops.append(b"ET\n")
    page = pdf.add_blank_page(page_size=(500, 800))
    page.Contents = pdf.make_stream(b"".join(ops))
    page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(Helv=_helvetica()))
    doc = _parse(pdf)
    return doc, doc.pages[0]


def test_two_column_page_reconstructs_into_two_column_runs() -> None:
    doc, page = _two_column_fixture()
    located = list(located_cluster_records(page, 0, doc))
    runs = cluster_page(0, located, FAKE_HASH, _accept_all)
    texts = sorted(r.display_text for r in runs)
    assert texts == ["AAAA", "BBBB"], f"expected two clean per-column runs, got {texts}"


def test_pitfall_3_skipping_the_sort_interleaves_two_columns() -> None:
    """The permanent negative case (Pitfall 3): computing gaps in STREAM order (A, B, A, B,
    ...) instead of sorting by projected position first produces gaps that alternate
    between huge positive and huge negative values, every one of which exceeds BREAK_EM --
    reproduced here with the module's own `_gaps_em` helper against the UNSORTED band, so
    this is the real failure mode the sort prevents, not a hand-written approximation of it.
    The real `cluster_page` (which DOES sort first) recovers the same two clean columns from
    the identical input, in the assertion below.
    """
    doc, page = _two_column_fixture()
    located = list(located_cluster_records(page, 0, doc))
    stream_order = [(record, attrs) for _path, record, attrs in located]  # NOT sorted

    unsorted_gaps = _gaps_em(stream_order)[1:]  # index 0 has no predecessor
    assert len(unsorted_gaps) == 7
    assert all(abs(g) > BREAK_EM for g in unsorted_gaps), (
        "expected every stream-order (unsorted) gap to exceed BREAK_EM in magnitude -- the "
        "interleaved-gibberish failure Pitfall 3 exists to prevent"
    )

    runs = cluster_page(0, located, FAKE_HASH, _accept_all)
    texts = sorted(r.display_text for r in runs)
    assert texts == ["AAAA", "BBBB"], "the real (sorting) clusterer must still recover two clean columns"


# ---------------------------------------------------------------------------
# Corpus-wide sweep (02-07 Task 3): zero exceptions, not editability correctness -- that
# is already unit-tested above and in test_bad_glyph_splits_run_into_locked_and_editable_
# subruns. Same two-exclusion convention as tests/test_glyph_record.py and
# tests/test_walker.py: exclusions are DUPLICATED, not imported, so a newly-diagnosed
# failure in one file can't silently widen another file's allowance.
# ---------------------------------------------------------------------------

# playa-pdf 1.1.0 cannot open this file without the optional `cryptography` extra
# (`pip install playa-pdf[crypto]`), not installed as a runtime dependency here.
KNOWN_UNOPENABLE_FILES = frozenset({"irs_form_w9_encrypted.pdf"})

# Raises a PDFSyntaxError from ObjectParser's inline-image (BI...ID...EI) handling,
# unrelated to text operators or clustering -- see tests/test_walker.py's module docstring.
KNOWN_OTHER_ERROR_FILES = frozenset({"govdocs1_011_011089.pdf"})


@pytest.mark.corpus
def test_cluster_page_walks_full_corpus_without_exception() -> None:
    """TEXT-08: cluster_page runs across every page of every public-corpus document without
    raising -- proving the four-stage pipeline (band, sort, break, address) survives real
    documents' superscript, rotated-text and glyph-at-a-time shapes, not just the
    hand-constructed unit fixtures above. `_accept_all` (defined earlier in this file) is
    used deliberately: whether a glyph SHOULD be editable is 02-06/D-05's concern and is
    already covered by test_bad_glyph_splits_run_into_locked_and_editable_subruns; this
    sweep only proves clustering itself never throws.

    `source_hash` is one fixed literal (FAKE_HASH) for the whole sweep -- this test never
    decodes a run ID back to bytes, so a real per-document hash buys nothing.

    Goes red if: cluster_page raises on any corpus document not already in one of the two
    known-failure sets below, or if either set changes size (grows -- a new failure; or
    shrinks -- a fix that should also shrink the allowlist).
    """
    manifest = json.loads((REPO_ROOT / "corpus" / "manifest.json").read_text())

    unopenable: set[str] = set()
    other_errors: dict[str, str] = {}

    for entry in manifest:
        filename = entry["filename"]
        try:
            doc = playa.open(str(CORPUS_DIR / filename))
        except PDFEncryptionError:
            unopenable.add(filename)
            continue

        try:
            for page_index, page in enumerate(doc.pages):
                located = list(located_cluster_records(page, page_index, doc))
                cluster_page(page_index, located, FAKE_HASH, _accept_all)
        except Exception as exc:  # noqa: BLE001 - classified below, not swallowed
            other_errors[filename] = f"{type(exc).__name__}: {exc}"

    assert unopenable == KNOWN_UNOPENABLE_FILES, (
        f"unopenable-file set changed: new={unopenable - KNOWN_UNOPENABLE_FILES} "
        f"missing={KNOWN_UNOPENABLE_FILES - unopenable}"
    )
    assert set(other_errors) == KNOWN_OTHER_ERROR_FILES, (
        f"other-error set changed: new={set(other_errors) - KNOWN_OTHER_ERROR_FILES} "
        f"missing={KNOWN_OTHER_ERROR_FILES - set(other_errors)}; details={other_errors}"
    )


# ---------------------------------------------------------------------------
# RTL detectability (02-07 Task 3; 02-RESEARCH.md Section 3 "RTL and vertical writing",
# Assumption A6). No real corpus RTL example exists -- this is a constructed-fixture-only
# guarantee, not a corpus-proven one. cluster_page does nothing RTL-specific (there is no
# bidi/RTL logic anywhere in this module); the point of this test is that a run's
# display_text reaches downstream classification intact enough for 02-08's classify_run to
# make its own RTL determination -- classify_run, not cluster_page, is what will assign
# editable=False/reason="right-to-left text". That verdict is explicitly OUT of scope here.
# ---------------------------------------------------------------------------


def test_rtl_run_display_text_is_detectable_as_rtl() -> None:
    """Constructs a run out of Arabic glyphs ("مرحبا", "hello") the same way every D-01/D-03
    unit test above does -- one GlyphRecord per glyph via `_record`, advancing along x like
    any other run -- and checks the resulting RunRecord.display_text's leading
    strong-directionality character is unicodedata.bidirectional() AL or R. cluster_page
    has no RTL-specific code path; this proves the glyphs' own Unicode text (already decoded
    by playa/02-06 before reaching this module) survives banding/sorting/breaking/addressing
    unmangled, which is all this module's architectural job covers.

    Sanity check (02-VALIDATION.md: a check is not trusted until demonstrated failing): the
    same assertion is run against an ordinary LTR run built the identical way, and must NOT
    hold for it -- proving the assertion actually discriminates RTL from LTR text rather than
    being trivially true for any display_text. No production RTL-handling code exists in
    cluster_page to mutate (that is exactly the point being proven -- it does nothing
    RTL-specific), so this inline LTR counter-fixture stands in for a mutation test.
    """
    rtl_text = "مرحبا"
    rtl_located = [
        (PATH0, _record(x=i * 10.0, y=100.0, unicode=ch, byte_offset=10 + i * 6), _attrs())
        for i, ch in enumerate(rtl_text)
    ]
    rtl_runs = cluster_page(0, rtl_located, FAKE_HASH, _accept_all)
    assert len(rtl_runs) == 1
    rtl_display_text = rtl_runs[0].display_text
    assert rtl_display_text == rtl_text

    rtl_leading = next(
        ch for ch in rtl_display_text if unicodedata.bidirectional(ch) in ("AL", "R", "L")
    )
    assert unicodedata.bidirectional(rtl_leading) in ("AL", "R"), (
        "expected the RTL fixture's leading strong-directionality character to be AL/R, "
        f"got bidirectional class {unicodedata.bidirectional(rtl_leading)!r}"
    )

    # Sanity check: the identical assertion, against an ordinary LTR run, must fail --
    # not trivially satisfied by any text cluster_page happens to pass through unmangled.
    ltr_text = "hello"
    ltr_located = [
        (PATH0, _record(x=i * 10.0, y=100.0, unicode=ch, byte_offset=10 + i * 6), _attrs())
        for i, ch in enumerate(ltr_text)
    ]
    ltr_runs = cluster_page(0, ltr_located, FAKE_HASH, _accept_all)
    assert len(ltr_runs) == 1
    ltr_display_text = ltr_runs[0].display_text
    ltr_leading = next(
        ch for ch in ltr_display_text if unicodedata.bidirectional(ch) in ("AL", "R", "L")
    )
    assert unicodedata.bidirectional(ltr_leading) not in ("AL", "R"), (
        "the RTL-detectability assertion must NOT hold for an ordinary LTR fixture -- "
        "otherwise it proves nothing"
    )
