"""Gate G2b: the substitution proof, end to end on one real substituting edit.

This test IS the project gate. Where `tests/test_gate_g2a.py` proves the CONFINED-diff
story on an edit that deliberately needs no new glyph, this one proves the other half:
an edit whose replacement text contains a character the embedded program has no glyph
for, routed through `engine.fonts`'s substitution trigger into a freshly subset, freshly
embedded bundled Liberation Type0/CIDFontType2 face -- and still lands clean.

D-15's full CI-automatable clause set, all against that single edit:

1. OTS: the newly-embedded Type0 font's own `/FontDescriptor`, read back out of the
   REWRITTEN output (never the in-memory `SubsetFont` that produced it), yields a font
   program that `ots-sanitize` accepts with exit 0;
2. `qpdf --check --warning-exit-0` is clean on the output;
3. per engine, the rendered page is pixel-identical outside the substituted run's own
   box (D-05: the WHOLE visual run is re-encoded, never a sub-span, so the mask is the
   whole run's box);
4. the three engines still agree with each other on the rewritten output;
5. ToUnicode: re-classifying the output through the real read pipeline recovers the
   recipe's own `new_text` at the substituted run's list position -- the programmatic
   proxy for a correct Acrobat copy-paste, rather than a hand-rolled CMap parser.

A second test in this file, `test_shared_family_resubset_serves_both_edited_runs`, closes
03-VALIDATION.md's FONT-02 criterion 3 ("untouched text elsewhere in the document that uses
the same font still renders correctly after a re-subset"). It lives here rather than at that
row's pre-planning guess of `tests/test_rewrite.py`, because the criterion is about
`apply_recipe`'s D-13 union-subsetting across a WHOLE recipe -- `engine/rewrite.py` sees one
run at a time and has no view of which other runs share a bundled family -- and because the
proof it asks for is a corpus + pixel-diff one, which is this file's own technique set. See
that test's own docstring for what it adds over 03-07's call-count unit test.

Scope note -- this is G2b, NOT G2a: `resolved_op.substitution_key is not None` is asserted
as a PRECONDITION (03-08's own precondition, inverted). A fixture/op pair that does not
actually substitute fails this gate rather than being accommodated; `harness.g2b_fixture`
finds the pair by ASKING `plan_recipe`, so "it substituted" is proven, never constructed.

No assertion message here embeds `new_text`, `run.display_text`, or raw content-stream /
font bytes -- only counts, booleans, lengths, paths, and engine/pair labels (the standing
convention T-02-04, as in tests/test_gate_g2a.py and tests/test_roundtrip.py).
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pikepdf
import pytest
from PIL import Image

from engine.classify_run import classify_document, stream_bytes_and_resources
from engine.encoding_table import embedded_font_bytes
from engine.fonts import BundledFamily, BundledVariant

# `_active_font_name_and_size` is private to `engine.recipe`, and imported here rather than
# re-implemented (the precedent this file's own `_cross_engine_pair_ok` import already sets)
# deliberately: the question the shared-subset test asks is "which font object does the
# rewritten run actually show its text through", and the honest answer is whatever the
# ENGINE's own `Tf` scan resolves. A second, local copy of that scan would prove the copy.
from engine.recipe import RecipeOp, _active_font_name_and_size, apply_recipe, plan_recipe
from engine.records import RunRecord
from engine.run_id import decode_run_id
from harness.g2b_fixture import (
    MAX_CANDIDATE_RUNS_PER_DOCUMENT,
    _candidate_new_texts,
    default_g2b_candidates,
    select_g2b_fixture,
)

REPO_ROOT = Path(__file__).parent.parent

# harness/ has no __init__.py -- sibling-module import, matching tests/test_gate_g2a.py's
# and tests/test_roundtrip.py's own established convention. (`harness.g2b_fixture` above
# is imported by package path instead, exactly as that module imports its own
# `harness.render_diff`.)
sys.path.insert(0, str(REPO_ROOT / "harness"))
from masked_diff import masked_pixel_diff  # noqa: E402
from render_diff import RENDER_DPI, render_all  # noqa: E402
from run_corpus_harness import _cross_engine_pair_ok  # noqa: E402

# Matches harness/render_diff.py's SUBPROCESS_TIMEOUT_SECONDS and tests/test_gate_g2a.py's
# own QPDF_CHECK_TIMEOUT_SECONDS precedent exactly.
OTS_SANITIZE_TIMEOUT_SECONDS = 30
QPDF_CHECK_TIMEOUT_SECONDS = 30

# Generous fixed padding standing in for real font ascent/descent. ponytail: fixed padding,
# upgrade to real font-program ascent/descent if a corpus run ever produces a false pass (a
# mask so large it hides a genuine regression). Same value and same tagged simplification as
# tests/test_gate_g2a.py's own constant.
MASK_VERTICAL_PAD_PT = 14.0
# Same spirit, one axis over -- carried over with `_edited_run_pixel_mask` itself, since
# G2a MEASURED the three engines' real differing pixel columns landing exactly ON both
# boundary columns without it.
MASK_HORIZONTAL_PAD_PT = 3.0

# `engine.fonts._tagged_base_font_name` builds the emitted BaseFont as
# `{6-letter subset tag}+Liberation{family}` -- so the family half is what identifies the
# newly-embedded face inside a page's `/Resources /Font`, keyed here by the
# `BundledFamily` literal `ResolvedOp.substitution_key` actually carries.
LIBERATION_BASEFONT_SUBSTRINGS = {
    "Sans": "LiberationSans",
    "Serif": "LiberationSerif",
    "Mono": "LiberationMono",
}

_ENGINE_LABELS = ("pdfium", "poppler", "mupdf")


def _edited_run_pixel_mask(run: RunRecord, cropbox_height_pt: float) -> tuple[int, int, int, int]:
    """The edited run's own bounding box in PNG pixel coordinates, for `masked_pixel_diff`.

    Intentionally a VERBATIM duplicate of `tests/test_gate_g2a.py`'s own private helper
    rather than an import from it, so each gate test file stays independently runnable --
    this task's brief asks for exactly that. Its docstring is reproduced with it because the
    measurement it records is the reason the formula has the shape it does:

    Glyph `x`/`y`/`advance` are DEVICE space (playa's, `Tm` already applied -- see
    `engine/records.py`: they are `matrix[4]`/`matrix[5]` of the glyph's own text-rendering
    matrix), and playa's device space is already y-DOWN from the top-left corner, the same
    orientation the PNG has. So this scales straight through with no y flip.

    MEASURED, because both G2a's and this plan's briefs prescribe a `cropbox_height_pt - y`
    flip and that is wrong for playa's coordinates. Re-measured for G2b on its OWN selected
    fixture (`corpus/public/govdocs1_000_000019.pdf` page 0), not assumed from G2a: the
    substituted run's glyphs sit at y=78.06pt, this formula produces mask rows 133-192
    (78.06 * 150/72 = 162.6, the baseline, inside it), and the three engines' real
    before/after pixel differences -- 592 (pdfium), 440 (poppler), 460 (mupdf) unmasked --
    all fall inside it, leaving 0 outside. The flipped formula was measured too, on these
    same renders: it produces rows 1458-1517 on this 1651px-tall page, a mask covering no
    changed pixel at all, and the clause then reports the full 440/460/592 -- here a false
    FAILURE rather than G2a's own vacuous pass, but wrong for the same reason either way.
    Only the unflipped formula puts the mask where the edit is. `cropbox_height_pt` is kept
    in the signature
    since a future page whose CropBox origin is not (0, 0) will need it; it is deliberately
    unused for the y axis today.

    Every edge rounds OUTWARD -- `floor` on left/top, `ceil` on right/bottom -- so the mask
    always fully contains the box it is built from. `int()` truncates toward zero, which is
    the wrong direction for the right/bottom edges (it shrinks the mask inward) and only
    happens to be right for left/top while the coordinates are positive.

    `scale` is recomputed locally rather than importing `render_diff._SCALE` (private to that
    module -- 03-07's established reimplement-small-cross-module-logic-locally precedent).
    """
    left_pt = min(g.x for g in run.glyphs) - MASK_HORIZONTAL_PAD_PT
    right_pt = max(g.x + g.advance[0] for g in run.glyphs) + MASK_HORIZONTAL_PAD_PT
    top_pt = min(g.y for g in run.glyphs) - MASK_VERTICAL_PAD_PT
    bottom_pt = max(g.y for g in run.glyphs) + MASK_VERTICAL_PAD_PT

    scale = RENDER_DPI / 72
    return (
        math.floor(left_pt * scale),
        math.floor(top_pt * scale),
        math.ceil(right_pt * scale),
        math.ceil(bottom_pt * scale),
    )


@pytest.mark.corpus
def test_g2b_full_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Gate G2b, D-15's full automatable clause set, on one real substituting edit."""
    # `default_g2b_candidates` builds RELATIVE corpus paths (`corpus/public/...`) and filters
    # them by `Path.exists()`, so it only finds anything from the repo root. The pinned
    # command is run from there; this pins it for every other invocation too, without
    # touching the harness's own signature.
    monkeypatch.chdir(REPO_ROOT)

    fixture_path, op = select_g2b_fixture(default_g2b_candidates())
    output_path = tmp_path / "g2b_output.pdf"
    report = apply_recipe(fixture_path, (op,), output_path)

    assert report.ok is True, f"{fixture_path}: recipe refused ({report.resolved[0].reason})"
    assert len(report.resolved) == 1
    resolved_op = report.resolved[0]
    # G2b's scope precondition: this edit genuinely needed a bundled substitute. Never
    # weakened -- a non-substituting run belongs to G2a, and a gate that passed on one
    # would be measuring nothing this plan exists to prove.
    assert resolved_op.substitution_key is not None
    assert resolved_op.run is not None
    assert resolved_op.all_page_runs is not None
    run = resolved_op.run

    orig_pdf = pikepdf.open(fixture_path)
    new_pdf = pikepdf.open(output_path)
    try:
        # Clause 1: the font this edit newly embedded, read back out of the OUTPUT, is
        # OTS-clean.
        family, _variant = resolved_op.substitution_key
        target_substr = LIBERATION_BASEFONT_SUBSTRINGS[family]
        embedded = [
            font
            for font in new_pdf.pages[run.page].Resources.Font.values()
            if font.get("/Subtype") == pikepdf.Name("/Type0")
            and target_substr in str(font.BaseFont)
        ]
        assert len(embedded) == 1, (
            f"{output_path.name} page {run.page}: found {len(embedded)} newly-embedded "
            f"Type0 font(s) for this substitution, expected exactly 1"
        )
        descriptor = embedded[0].DescendantFonts[0].FontDescriptor
        program = embedded_font_bytes(descriptor)
        assert program is not None, (
            f"{output_path.name} page {run.page}: embedded Type0 font carries no readable "
            f"font program"
        )

        font_path = tmp_path / "g2b_subset_font.ttf"
        font_path.write_bytes(program.data)
        result = subprocess.run(
            ["ots-sanitize", str(font_path)],
            capture_output=True,
            timeout=OTS_SANITIZE_TIMEOUT_SECONDS,
        )
        assert result.returncode == 0, (
            f"ots-sanitize exited {result.returncode} ({len(result.stderr)} stderr byte(s))"
        )

        # Clause 2: the output is structurally clean (identical technique to
        # tests/test_gate_g2a.py's own qpdf clause).
        result = subprocess.run(
            ["qpdf", "--check", "--warning-exit-0", str(output_path)],
            capture_output=True,
            timeout=QPDF_CHECK_TIMEOUT_SECONDS,
        )
        assert result.returncode == 0, f"qpdf --check exited {result.returncode}"

        cropbox = orig_pdf.pages[run.page].cropbox
        cropbox_height_pt = float(cropbox[3]) - float(cropbox[1])
    finally:
        orig_pdf.close()
        new_pdf.close()

    # Clause 3: same-engine, zero-tolerance pixel identity everywhere outside the
    # substituted run's own box. D-05 -- the whole visual run is re-encoded through the new
    # face, never a sub-span, so the whole run's box is the correct mask.
    mask = _edited_run_pixel_mask(run, cropbox_height_pt)
    orig_pngs = render_all(fixture_path, run.page, tmp_path / "orig")
    new_pngs = render_all(output_path, run.page, tmp_path / "new")

    for label, orig_png, new_png in zip(_ENGINE_LABELS, orig_pngs, new_pngs):
        diff = masked_pixel_diff(orig_png, new_png, mask=mask)
        assert diff == 0, (
            f"{label}: expected zero pixel diff outside the substituted run's box, got {diff}"
        )

    # Clause 4: the three engines still agree with each other on the REWRITTEN output --
    # reusing clause 3's renders, not re-rendering.
    pdfium_png, poppler_png, mupdf_png = new_pngs
    for pair_label, png_a, png_b in (
        ("pdfium-vs-poppler", pdfium_png, poppler_png),
        ("pdfium-vs-mupdf", pdfium_png, mupdf_png),
        ("poppler-vs-mupdf", poppler_png, mupdf_png),
    ):
        ok, detail = _cross_engine_pair_ok(pair_label, png_a, png_b)
        assert ok, detail

    # Clause 5: the /ToUnicode CMap this substitution emitted round-trips through the REAL
    # read pipeline -- `classify_document`, the same path the UI reads with -- so the
    # substituted run's text comes back out of a CID-keyed font exactly as written.
    #
    # The index-based comparison assumes the PRE-edit `all_page_runs` position is still the
    # same run's position in the POST-edit, re-classified page list. That is a real
    # assumption, not a given: a substitution re-encodes the ENTIRE run through a different
    # font and a different (CID) encoding, which could in principle change how many runs the
    # clusterer produces or their order. MEASURED on the selected fixture rather than
    # assumed: page 0 yields 45 runs before and 45 after, and every one of the 45 positions
    # carries the same first-glyph (x, y) and the same display_text LENGTH pre and post --
    # the list is aligned end to end, not merely long enough. Re-measure this if the fixture
    # selection ever moves to a different document.
    edited_index = next(
        i for i, r in enumerate(resolved_op.all_page_runs) if r.run_id == run.run_id
    )
    new_classification = classify_document(output_path)
    new_page_runs = [r for r, _verdict in new_classification.runs if r.page == run.page]
    assert edited_index < len(new_page_runs), (
        f"{output_path.name} page {run.page}: rewritten page has {len(new_page_runs)} run(s), "
        f"expected more than {edited_index}"
    )
    extracted_run = new_page_runs[edited_index]

    matches = extracted_run.display_text == op.new_text
    assert matches, (
        f"ToUnicode round-trip mismatch at page-run position {edited_index}: recovered "
        f"{len(extracted_run.display_text)} char(s), recipe wrote {len(op.new_text)}"
    )


def _find_same_family_op_pair(
    pdf_path: Path,
) -> tuple[RecipeOp, RecipeOp, tuple[BundledFamily, BundledVariant]]:
    """Two DISTINCT runs on one page of `pdf_path`, each with a replacement a LIVE
    `plan_recipe` call proves substitutes, both landing on the SAME `(family, variant)`.

    `harness.g2b_fixture.find_substitution_forcing_op` returns exactly one op and stops, so
    it cannot answer "and now a second one sharing its family" -- this walks the same
    candidates with the same three ingredients that function is built from
    (`classify_document`'s `editable_original` runs, `_candidate_new_texts`'s forcing
    replacements, and a live `plan_recipe` whose `substitution_key` came back set), so the
    live-proof discipline is preserved exactly: nothing here asserts a substitution by
    construction, and the family match is READ off the resolver rather than inferred from
    `/BaseFont` by this test.

    Two guards that were MEASURED, not anticipated. The pair must sit on one PAGE, because
    the mask/render/re-classification clauses below are all per-page. And the two runs must
    carry DISTINCT `run_id`s: `corpus/public/govdocs1_000_000019.pdf` page 0 really does
    yield several distinct `RunRecord`s sharing one run ID (same part, same operator byte
    offset, no `:g` subrange), and a recipe naming the same ID twice is refused whole as
    `"duplicate_run_id_in_recipe"` -- correctly, but it would be measuring that refusal
    rather than D-13.

    Raises `RuntimeError` -- file name and counts only, never `display_text` or a candidate
    string (T-02-04, the same posture `find_substitution_forcing_op` itself takes).
    """
    classification = classify_document(pdf_path)
    candidate_runs = [
        (run, verdict)
        for run, verdict in classification.runs
        if verdict.state == "editable_original"
    ][:MAX_CANDIDATE_RUNS_PER_DOCUMENT]

    first_by_key: dict[tuple[BundledFamily, BundledVariant], tuple[RunRecord, RecipeOp]] = {}
    for run, _verdict in candidate_runs:
        for candidate in _candidate_new_texts(run.display_text):
            op = RecipeOp(run.run_id, candidate)
            report = plan_recipe(pdf_path, (op,))
            if not report.ok:
                continue
            key = report.resolved[0].substitution_key
            if key is None:
                continue
            earlier = first_by_key.get(key)
            if (
                earlier is not None
                and earlier[0].page == run.page
                and earlier[0].run_id != run.run_id
            ):
                return earlier[1], op, key
            first_by_key.setdefault(key, (run, op))
            # This run has had its forcing replacement found; move to the next run rather
            # than trying its remaining candidates, exactly as `find_substitution_forcing_op`
            # does.
            break

    raise RuntimeError(
        f"no same-family substitution-forcing op pair in {pdf_path.name}: "
        f"{len(candidate_runs)} run(s) searched, {len(first_by_key)} distinct family/variant "
        f"key(s) forced"
    )


def _serving_font(pdf: pikepdf.Pdf, run: RunRecord) -> pikepdf.Object:
    """The `/Resources /Font` object `run` actually shows its text through, in `pdf`.

    Resolved the way the engine itself resolves a run's font -- the last `Tf` at or before
    the run's first glyph's operator byte offset, looked up in that PART's own resources
    (`run.run_id` names the part, including any Form XObject path). Reading it back out of
    the REWRITTEN document, from the rewritten run's own re-derived offsets, is what makes
    the objgen comparison below evidence about the OUTPUT rather than about the plan.
    """
    parts = decode_run_id(run.run_id)
    stream_bytes, resources = stream_bytes_and_resources(
        pdf, run.page, parts["part"], parts["xobj_path"]
    )
    active = _active_font_name_and_size(stream_bytes, run.glyphs[0].operator_byte_offset)
    assert active is not None, f"page {run.page}: no usable /Tf precedes the rewritten run"
    resource_name, _size = active
    assert resources is not None, f"page {run.page}: rewritten part carries no /Resources"
    return resources["/Font"]["/" + resource_name.decode("latin-1")]


def _two_region_masked_diff(
    png_a: Path,
    png_b: Path,
    mask_a: tuple[int, int, int, int],
    mask_b: tuple[int, int, int, int],
    scratch_dir: Path,
) -> int:
    """`masked_pixel_diff` with TWO regions excluded instead of one.

    `masked_pixel_diff` takes a single bounding box, and this test has two edited runs. The
    union of two boxes is not a box, so rather than widening the helper's signature for one
    caller, `mask_a` is painted the SAME flat colour onto a copy of each image -- which
    makes that region byte-identical between them, contributing exactly zero differing
    pixels -- and `mask_b` is then passed through as the helper's own mask. Equivalent to
    excluding both, with the counting still done by the one shared implementation.
    """
    scratch_dir.mkdir(parents=True, exist_ok=True)
    masked: list[Path] = []
    # Indexed names, never `source.name`: `render_all` names its output after the ENGINE, so
    # the before and after renders of one engine share a file name and differ only by
    # directory -- copying both here under their own names would clobber one with the other.
    for index, source in enumerate((png_a, png_b)):
        target = scratch_dir / f"{index}.png"
        with Image.open(source) as image:
            rgb = image.convert("RGB")
            rgb.paste((0, 0, 0), mask_a)
            rgb.save(target)
        masked.append(target)
    # `int(...)` only because `masked_diff` is imported as an untyped sibling module (see the
    # `sys.path` note above), so mypy sees `Any` coming back out of it.
    return int(masked_pixel_diff(masked[0], masked[1], mask=mask_b))


@pytest.mark.corpus
def test_shared_family_resubset_serves_both_edited_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FONT-02 criterion 3: one re-subset family serves EVERY edit that uses it.

    03-07's `test_apply_recipe_calls_subset_font_for_family_once_per_key` proves D-13's call
    COUNT -- `subset_font_for_family` runs once per distinct `(family, variant)` across the
    whole recipe. It cannot prove that the single subset that call produced actually SERVES
    both edits: a glyph union built for two ops' characters could still drop or corrupt one
    op's glyphs, and a per-op re-embed could quietly appear, and that unit test would pass
    either way. This is the other half, against real corpus bytes and real rendering:

    * both ops apply (`report.ok`), both through the same resolved `(family, variant)`;
    * both rewritten runs show their text through the IDENTICAL indirect font object --
      compared by `objgen`, the same stable indirect-object identity
      `engine.rewrite._substitution_resource_key` itself keys on, never by value-equality
      of two dictionaries that merely look alike;
    * BOTH edits' own `new_text` comes back out of the real read pipeline at their own
      positions (Task 2's ToUnicode round-trip, applied twice) -- the shared union covers
      both edits' glyphs, not just the one it was built for first;
    * the rendered page is pixel-identical outside the two edited boxes -- the literal
      "untouched text elsewhere in the document that uses the same font still renders
      correctly" claim, proven visually.

    MEASURED on `corpus/public/govdocs1_000_000019.pdf` (the first pinned candidate, the
    same document Task 2's gate selects): page 0's runs at pre-edit page-run positions 0 and
    8 both force `("Serif", "Regular")`, the pair search costs ~1.3s, page 0 yields 45 runs
    before and 45 after both edits, both recoveries match, and the two-region diff is 0 on
    all three engines (unmasked, the same edits move 2531/1934/1883 and 592/440/460 pixels).
    """
    monkeypatch.chdir(REPO_ROOT)

    # Exhaust the real corpus before constructing anything (the "measure the corpus,
    # construct only if it fails" discipline): every candidate document is searched, and the
    # first that yields a same-family pair wins. No constructed fixture is needed -- the
    # FIRST pinned candidate already carries one.
    for path in default_g2b_candidates():
        try:
            op_a, op_b, key = _find_same_family_op_pair(Path(path))
        except RuntimeError:
            continue
        fixture_path = Path(path)
        break
    else:
        raise AssertionError(
            f"no same-family substitution-forcing op pair in "
            f"{len(default_g2b_candidates())} candidate document(s)"
        )

    output_path = tmp_path / "shared_family_output.pdf"
    report = apply_recipe(fixture_path, (op_a, op_b), output_path)

    assert report.ok is True, (
        f"{fixture_path}: recipe refused "
        f"({[r.reason for r in report.resolved if not r.ok]})"
    )
    assert len(report.resolved) == 2
    resolved_a, resolved_b = report.resolved
    # Precondition, same posture as the gate above: both edits genuinely substituted, and
    # through the SAME bundled key -- otherwise there is no shared subset to prove anything
    # about. Read off the resolver, never asserted by construction.
    assert resolved_a.substitution_key == key
    assert resolved_b.substitution_key == key
    assert resolved_a.run is not None
    assert resolved_b.run is not None
    assert resolved_a.all_page_runs is not None
    assert resolved_b.all_page_runs is not None
    assert resolved_a.run.page == resolved_b.run.page
    page = resolved_a.run.page
    run_a, run_b = resolved_a.run, resolved_b.run

    # Both edited runs, located again in the REWRITTEN page's run list at their own pre-edit
    # positions -- Task 2's clause-5 technique and its measured assumption (the pre- and
    # post-edit page-run lists stay aligned), applied to two runs instead of one.
    indices = (
        next(i for i, r in enumerate(resolved_a.all_page_runs) if r.run_id == run_a.run_id),
        next(i for i, r in enumerate(resolved_b.all_page_runs) if r.run_id == run_b.run_id),
    )
    new_classification = classify_document(output_path)
    new_page_runs = [r for r, _verdict in new_classification.runs if r.page == page]
    assert max(indices) < len(new_page_runs), (
        f"{output_path.name} page {page}: rewritten page has {len(new_page_runs)} run(s), "
        f"expected more than {max(indices)}"
    )
    rewritten_runs = tuple(new_page_runs[i] for i in indices)

    new_pdf = pikepdf.open(output_path)
    try:
        # The one-subset-per-family claim, as object identity: both rewritten runs show
        # their text through one and the same indirect font object.
        font_a, font_b = (_serving_font(new_pdf, run) for run in rewritten_runs)
        assert font_a.objgen != (0, 0), (
            f"{output_path.name} page {page}: the first edited run's font is a DIRECT "
            f"object, so objgen identity would be meaningless"
        )
        assert font_a.objgen == font_b.objgen, (
            f"{output_path.name} page {page}: the two edited runs show through different "
            f"font objects {font_a.objgen} and {font_b.objgen}, expected one shared subset"
        )
        assert font_a.get("/Subtype") == pikepdf.Name("/Type0")
        target_substr = LIBERATION_BASEFONT_SUBSTRINGS[key[0]]
        assert target_substr in str(font_a.BaseFont)

        # And the same claim from the document's side: the page's resources carry exactly
        # ONE newly-embedded Type0 face for this family, not one per edit.
        embedded = [
            font
            for font in new_pdf.pages[page].Resources.Font.values()
            if font.get("/Subtype") == pikepdf.Name("/Type0")
            and target_substr in str(font.BaseFont)
        ]
        assert len(embedded) == 1, (
            f"{output_path.name} page {page}: found {len(embedded)} newly-embedded Type0 "
            f"font(s) for this family, expected exactly 1 for 2 edits"
        )

        cropbox = new_pdf.pages[page].cropbox
        cropbox_height_pt = float(cropbox[3]) - float(cropbox[1])
    finally:
        new_pdf.close()

    # BOTH edits round-trip: the shared glyph union did not drop or corrupt either one by
    # having been built for the other's characters too.
    for label, rewritten, op in zip(("first", "second"), rewritten_runs, (op_a, op_b)):
        assert rewritten.display_text == op.new_text, (
            f"{label} edit: ToUnicode round-trip mismatch, recovered "
            f"{len(rewritten.display_text)} char(s), recipe wrote {len(op.new_text)}"
        )

    # "Untouched text elsewhere still renders correctly", literally: zero same-engine pixel
    # difference outside the union of the two edited runs' own boxes.
    mask_a = _edited_run_pixel_mask(run_a, cropbox_height_pt)
    mask_b = _edited_run_pixel_mask(run_b, cropbox_height_pt)
    orig_pngs = render_all(fixture_path, page, tmp_path / "orig")
    new_pngs = render_all(output_path, page, tmp_path / "new")

    for label, orig_png, new_png in zip(_ENGINE_LABELS, orig_pngs, new_pngs):
        diff = _two_region_masked_diff(
            orig_png, new_png, mask_a, mask_b, tmp_path / f"masked_{label}"
        )
        assert diff == 0, (
            f"{label}: expected zero pixel diff outside both edited runs' boxes, got {diff}"
        )
