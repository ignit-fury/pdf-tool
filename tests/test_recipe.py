"""Tests for engine.recipe -- the JSON recipe contract (D-09, EDIT-04).

Relies on [tool.pytest.ini_options] pythonpath = ["."] in pyproject.toml for a bare
`import engine`, matching tests/test_run_id.py's own convention.
"""

import dataclasses
import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path

import pikepdf
import pytest
from fontTools.ttLib import TTFont

import engine.recipe as recipe_module
from engine.classify_run import RunVerdict, classify_document
from engine.records import RunRecord
from engine.fit import FitResult, advance_pt_for_codes, fit_run, load_font, read_original_advance_pt
from engine.fonts import (
    BundledFamily,
    BundledVariant,
    SubsetFont,
    liberation_font_path,
    lookup_bundled_font,
)
from engine.recipe import (
    MAX_NEW_TEXT_CHARS,
    MAX_RECIPE_OPS,
    RecipeOp,
    RecipeReport,
    RecipeTooLargeError,
    apply_recipe,
    parse_recipe,
    plan_recipe,
)
from engine.rewrite import rewrite_run
from engine.run_id import decode_run_id

# The synthetic fixture's embedded-TrueType font covers printable ASCII only -- the same
# FirstChar/LastChar span the /Widths array below is built over.
FIRST_CHAR = 32
LAST_CHAR = 126


def test_parse_recipe_builds_ops_from_valid_json() -> None:
    data = json.dumps(
        [
            {"run_id": "a" * 64 + ":p0:c0:o5", "new_text": "hello"},
            {"run_id": "b" * 64 + ":p1:c0:o9", "new_text": "world"},
        ]
    ).encode()
    ops = parse_recipe(data)
    assert ops == (
        RecipeOp(run_id="a" * 64 + ":p0:c0:o5", new_text="hello"),
        RecipeOp(run_id="b" * 64 + ":p1:c0:o9", new_text="world"),
    )


def test_parse_recipe_rejects_non_list_json() -> None:
    data = json.dumps({"run_id": "x", "new_text": "y"}).encode()
    with pytest.raises(ValueError):
        parse_recipe(data)


def test_parse_recipe_rejects_op_missing_required_key() -> None:
    data = json.dumps([{"run_id": "x"}]).encode()
    with pytest.raises(ValueError):
        parse_recipe(data)


def test_parse_recipe_rejects_op_with_extra_key() -> None:
    data = json.dumps([{"run_id": "x", "new_text": "y", "extra": "z"}]).encode()
    with pytest.raises(ValueError):
        parse_recipe(data)


def test_parse_recipe_rejects_non_string_field() -> None:
    data = json.dumps([{"run_id": "x", "new_text": 5}]).encode()
    with pytest.raises(ValueError):
        parse_recipe(data)


def test_parse_recipe_rejects_op_count_above_max() -> None:
    ops = [{"run_id": "x", "new_text": "y"} for _ in range(MAX_RECIPE_OPS + 1)]
    data = json.dumps(ops).encode()
    with pytest.raises(RecipeTooLargeError):
        parse_recipe(data)


def test_parse_recipe_rejects_new_text_above_max_chars() -> None:
    data = json.dumps([{"run_id": "x", "new_text": "a" * (MAX_NEW_TEXT_CHARS + 1)}]).encode()
    with pytest.raises(RecipeTooLargeError):
        parse_recipe(data)


def test_parse_recipe_rejects_malformed_json_bytes() -> None:
    with pytest.raises(ValueError):
        parse_recipe(b"{not valid json")


def test_recipe_op_is_frozen_slots() -> None:
    with pytest.raises(TypeError):
        RecipeOp(run_id="x")  # type: ignore[call-arg]

    op = RecipeOp(run_id="x", new_text="y")
    with pytest.raises(FrozenInstanceError):
        op.new_text = "z"  # type: ignore[misc]


def test_no_eval_or_exec_in_recipe_module() -> None:
    source = Path(recipe_module.__file__).read_text()
    assert "eval(" not in source
    assert "exec(" not in source


# --------------------------------------------------------------------------------------
# 03-07 Task 2: plan_recipe -- D-10's hash check, D-05/D-06's substitution routing,
# EDIT-04's pass-through-or-named refusal vocabulary.
# --------------------------------------------------------------------------------------


def _liberation_widths(family: BundledFamily, variant: BundledVariant) -> list[int]:
    """A `/Widths` array over FIRST_CHAR..LAST_CHAR taken from a bundled Liberation face,
    in the 1000-unit space `/Widths` is always expressed in.

    Shared by both fixtures below: an unembedded font still needs a real `/Widths`, because
    `advance_pt_for_codes` measures the original run from the font DICTIONARY and refuses
    (rather than falling through to `/MissingWidth`) when the array cannot answer.
    """
    ttf = TTFont(str(liberation_font_path(family, variant)))
    units_per_em = ttf["head"].unitsPerEm
    cmap = ttf.getBestCmap()
    hmtx = ttf["hmtx"]
    return [
        round(hmtx[cmap[code]][0] * 1000 / units_per_em) if code in cmap else 0
        for code in range(FIRST_CHAR, LAST_CHAR + 1)
    ]


def _build_plan_fixture(path: Path) -> None:
    """A four-run single-page document, built inline (the same synthetic-fixture
    convention `tests/test_classify.py::test_low_path_count_classifies_empty` established)
    because no corpus document carries all four of `plan_recipe`'s routing outcomes at
    once, and hunting one that happens to would pin the test to that document's
    incidental font choices rather than to the routing rules themselves.

    The four runs, in stream order:

    * `/F1` -- BaseFont `/Arial`, but the embedded `/FontFile2` program is the bundled
      LiberationSans-Regular (D-07: metric-compatible, which is exactly why substituting
      one for the other is seamless). `/Widths` is derived from that same program, so a
      run's summed glyph advance and a Liberation-shaped replacement's advance are
      directly comparable and the fit ladder produces real, non-refused results.
      Classifies `editable_original` (embedded, so Phase 2 sees no substitution need) --
      which makes it the ONE run that can prove BOTH the non-substituting path AND
      Pattern 4's edit-time trigger firing independently of Phase 2's own state.
    * `/F2` -- non-embedded `/Helvetica`: `editable_substitution` already at
      classification time, and mapped by the table.
    * `/F3` -- non-embedded `/NoSuchFontFamily`: substituting, and deliberately absent
      from `BASE_FONT_MAPPING`, so D-06 refuses it BY NAME.
    * `/F4` -- a Type3 font: `not_editable`, whose reason `plan_recipe` must pass through
      unmodified rather than renaming.
    """
    program = liberation_font_path("Sans", "Regular").read_bytes()
    widths = _liberation_widths("Sans", "Regular")

    pdf = pikepdf.Pdf.new()
    page = pdf.add_blank_page(page_size=(612, 792))

    descriptor = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/FontDescriptor"),
                "/FontName": pikepdf.Name("/Arial"),
                "/Flags": 32,  # non-symbolic
                "/FontBBox": pikepdf.Array([-203, -303, 1050, 910]),
                "/ItalicAngle": 0,
                "/Ascent": 905,
                "/Descent": -212,
                "/CapHeight": 715,
                "/StemV": 80,
                "/FontFile2": pdf.make_stream(program),
            }
        )
    )
    embedded_truetype = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/Font"),
                "/Subtype": pikepdf.Name("/TrueType"),
                "/BaseFont": pikepdf.Name("/Arial"),
                "/FirstChar": FIRST_CHAR,
                "/LastChar": LAST_CHAR,
                "/Widths": pikepdf.Array(widths),
                "/Encoding": pikepdf.Name("/WinAnsiEncoding"),
                "/FontDescriptor": descriptor,
            }
        )
    )

    def _simple_unembedded(base_font: str) -> pikepdf.Object:
        return pdf.make_indirect(
            pikepdf.Dictionary(
                {
                    "/Type": pikepdf.Name("/Font"),
                    "/Subtype": pikepdf.Name("/Type1"),
                    "/BaseFont": pikepdf.Name(base_font),
                    "/Encoding": pikepdf.Name("/WinAnsiEncoding"),
                }
            )
        )

    type3 = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/Font"),
                "/Subtype": pikepdf.Name("/Type3"),
                "/FontBBox": pikepdf.Array([0, 0, 10, 10]),
                "/FontMatrix": pikepdf.Array([0.001, 0, 0, 0.001, 0, 0]),
                "/CharProcs": pikepdf.Dictionary(
                    {"/square": pdf.make_stream(b"10 0 0 0 10 10 d1\n0 0 10 10 re f\n")}
                ),
                "/Encoding": pikepdf.Dictionary(
                    {
                        "/Type": pikepdf.Name("/Encoding"),
                        "/Differences": pikepdf.Array([97, pikepdf.Name("/square")]),
                    }
                ),
                "/FirstChar": 97,
                "/LastChar": 97,
                "/Widths": pikepdf.Array([1000]),
            }
        )
    )

    page.Resources = pikepdf.Dictionary(
        {
            "/Font": pikepdf.Dictionary(
                {
                    "/F1": embedded_truetype,
                    "/F2": _simple_unembedded("/Helvetica"),
                    "/F3": _simple_unembedded("/NoSuchFontFamily"),
                    "/F4": type3,
                }
            )
        }
    )
    page.Contents = pdf.make_stream(
        b"BT /F1 12 Tf 72 700 Td (Hello world) Tj ET\n"
        b"BT /F2 12 Tf 72 660 Td (Second line) Tj ET\n"
        b"BT /F3 12 Tf 72 620 Td (Third line) Tj ET\n"
        b"BT /F4 12 Tf 72 580 Td (aaa) Tj ET\n"
    )
    pdf.save(str(path))
    pdf.close()


@pytest.fixture(scope="module")
def plan_fixture(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("plan_recipe") / "plan_fixture.pdf"
    _build_plan_fixture(path)
    return path


def _run_ids_by_font(path: Path) -> dict[str, tuple[str, RunVerdict]]:
    """`{"F1": (run_id, verdict), ...}` -- the fixture's four runs in stream order,
    labelled by the font resource each was written with. Resolved through
    `classify_document` itself rather than hardcoded, so the run IDs carry the real
    source hash the fix under test now embeds."""
    runs = classify_document(path).runs
    assert len(runs) == 4, "fixture must produce exactly four runs"
    return {
        f"F{i + 1}": (run.run_id, verdict) for i, (run, verdict) in enumerate(runs)
    }


def test_plan_recipe_refuses_on_source_hash_mismatch(plan_fixture: Path) -> None:
    """D-10, the whole point of the `source_hash` fix: a run ID minted against different
    bytes must refuse, and must do so BEFORE any other property of the op is resolved --
    a byte offset from another document may land mid-token."""
    run_id, _verdict = _run_ids_by_font(plan_fixture)["F1"]
    foreign = "0" * 64 + run_id[64:]

    report = plan_recipe(plan_fixture, (RecipeOp(run_id=foreign, new_text="Hallo world"),))

    assert report.ok is False
    (resolved,) = report.resolved
    assert resolved.ok is False
    assert resolved.reason == "source_hash_mismatch"
    # Nothing else resolved: the check fires before any run/verdict/fit lookup.
    assert resolved.run is None
    assert resolved.verdict is None
    assert resolved.fit_result is None
    assert resolved.substitution_key is None


def test_plan_recipe_refuses_on_malformed_run_id(plan_fixture: Path) -> None:
    """`decode_run_id` raises `ValueError` on anything off-grammar; `plan_recipe` is the
    untrusted-input boundary Phase 4 will hand client-echoed IDs to, so that must become a
    named refusal, never an uncaught exception."""
    report = plan_recipe(plan_fixture, (RecipeOp(run_id="not-a-run-id", new_text="x"),))

    assert report.ok is False
    (resolved,) = report.resolved
    assert resolved.reason == "malformed_run_id"


def test_plan_recipe_refuses_on_unknown_run_id(plan_fixture: Path) -> None:
    """Right document, right hash, no such run: distinct from both a hash mismatch and a
    malformed ID, because it means the ID is well-formed and current but addresses bytes
    no run was clustered from."""
    run_id, _verdict = _run_ids_by_font(plan_fixture)["F1"]
    source_hash = decode_run_id(run_id)["source_hash"]
    unknown = f"{source_hash}:p0:c0:o999999"

    report = plan_recipe(plan_fixture, (RecipeOp(run_id=unknown, new_text="x"),))

    assert report.ok is False
    (resolved,) = report.resolved
    assert resolved.reason == "run_id_not_found"


def test_plan_recipe_passes_through_not_editable_reason(plan_fixture: Path) -> None:
    """EDIT-04: a refusal Phase 2 already named is passed through UNMODIFIED, never
    re-worded into a `plan_recipe`-specific string. The fixture's Type3 run refuses with
    `classify_run`'s own `"Type3"`."""
    run_id, verdict = _run_ids_by_font(plan_fixture)["F4"]
    assert verdict.state == "not_editable"
    assert verdict.reason == "Type3"

    report = plan_recipe(plan_fixture, (RecipeOp(run_id=run_id, new_text="x"),))

    (resolved,) = report.resolved
    assert resolved.ok is False
    assert resolved.reason == verdict.reason
    assert resolved.verdict is verdict or resolved.verdict == verdict


def test_plan_recipe_resolves_editable_original_run_successfully(
    plan_fixture: Path,
) -> None:
    """The happy path: the run's own embedded program covers every character of
    `new_text`, so no substitution is needed and the fit ladder runs against that same
    embedded program."""
    run_id, verdict = _run_ids_by_font(plan_fixture)["F1"]
    assert verdict.state == "editable_original"

    report = plan_recipe(
        plan_fixture, (RecipeOp(run_id=run_id, new_text="Hallo world"),)
    )

    assert report.ok is True
    (resolved,) = report.resolved
    assert resolved.ok is True
    assert resolved.reason is None
    assert resolved.substitution_key is None
    assert resolved.fit_result is not None
    assert resolved.fit_result.refused is False
    assert resolved.strategy == resolved.fit_result.strategy
    assert resolved.delta_pt == resolved.fit_result.delta_pt
    assert resolved.strategy in ("trailing_kern", "inter_word_kern", "tz")
    assert resolved.run is not None
    assert resolved.all_page_runs is not None
    # `rewrite_run`'s `all_page_runs` argument: every run on the page, not just this one.
    assert len(resolved.all_page_runs) == 4


def test_plan_recipe_substitution_key_set_when_trigger_fires_on_editable_original(
    plan_fixture: Path,
) -> None:
    """D-05 / 03-RESEARCH.md Pattern 4, the genuinely new question Phase 2 cannot answer:
    this run is `editable_original` -- its font is embedded and fully usable for the text
    already on the page -- yet `new_text` contains U+0101, which `/WinAnsiEncoding` has no
    code for. The trigger must be consulted INDEPENDENTLY of the Phase 2 state, and the
    resolved substitute must come from the mapping table keyed on this run's own
    `/BaseFont`.
    """
    run_id, verdict = _run_ids_by_font(plan_fixture)["F1"]
    assert verdict.state == "editable_original", (
        "this test is only meaningful while Phase 2 itself sees no substitution need -- "
        "if this run were already editable_substitution it would prove nothing about the "
        "edit-time trigger"
    )

    report = plan_recipe(
        plan_fixture, (RecipeOp(run_id=run_id, new_text="Hello worlā"),)
    )

    assert report.ok is True
    (resolved,) = report.resolved
    assert resolved.ok is True
    assert resolved.substitution_key == ("Sans", "Regular")


def test_plan_recipe_refuses_when_basefont_not_in_mapping_table(
    plan_fixture: Path,
) -> None:
    """D-06: a BaseFont with no table entry refuses BY NAME, and the reason is
    `MappingVerdict`'s own string passed through unmodified -- no serif/sans fallback
    guessed from `/FontDescriptor` flags."""
    run_id, verdict = _run_ids_by_font(plan_fixture)["F3"]
    assert verdict.state == "editable_substitution"

    report = plan_recipe(plan_fixture, (RecipeOp(run_id=run_id, new_text="x"),))

    assert report.ok is False
    (resolved,) = report.resolved
    assert resolved.ok is False
    assert resolved.reason == lookup_bundled_font("NoSuchFontFamily").reason
    assert resolved.substitution_key is None


def test_plan_recipe_never_mutates_source_file(plan_fixture: Path) -> None:
    """`plan_recipe` is D-03's dry run: it opens its own handles and closes them without
    saving, so the file on disk is byte-identical afterwards. Asserted over a recipe that
    mixes a resolving op with a refusing one, so both code paths run."""
    ids = _run_ids_by_font(plan_fixture)
    before = hashlib.sha256(plan_fixture.read_bytes()).hexdigest()

    plan_recipe(
        plan_fixture,
        (
            RecipeOp(run_id=ids["F1"][0], new_text="Hallo world"),
            RecipeOp(run_id=ids["F3"][0], new_text="x"),
            RecipeOp(run_id=ids["F4"][0], new_text="x"),
        ),
    )

    assert hashlib.sha256(plan_fixture.read_bytes()).hexdigest() == before


def test_plan_recipe_resolution_failure_produces_named_reason_not_crash(
    plan_fixture: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The classify-never-crash catch-all, proven by making a real call inside it blow up
    rather than by its absence from the happy-path tests.

    MUTATION: `engine.recipe.resolve_font` -- a call that only happens INSIDE the broad
    try block, after every named check above it -- raises. The op must come back
    `"resolution_failed"`, and the named checks must keep their own reasons, proving the
    catch-all sits after them and cannot masquerade as one of them.
    """
    ids = _run_ids_by_font(plan_fixture)

    def _boom(_font: object) -> object:
        raise RuntimeError("font resolution exploded")

    monkeypatch.setattr(recipe_module, "resolve_font", _boom)

    report = plan_recipe(
        plan_fixture,
        (
            RecipeOp(run_id=ids["F1"][0], new_text="Hallo world"),
            RecipeOp(run_id="not-a-run-id", new_text="x"),
            RecipeOp(run_id=ids["F4"][0], new_text="x"),
        ),
    )

    assert report.ok is False
    failed, malformed, type3 = report.resolved
    assert failed.reason == "resolution_failed"
    # The named checks are OUTSIDE the catch-all and keep their own, more specific reasons.
    assert malformed.reason == "malformed_run_id"
    assert type3.reason == "Type3"


# The Tf-1/Tm-scaled regression case: this document sets `1 Tf` and carries the real
# scale in `Tm`, so a run's DEVICE-space glyph advances and its text-space `/Widths`
# advance differ by that whole scale factor. Measured on the run below: 437.26 vs 36.44.
TM_SCALED_DOC = Path(__file__).parent.parent / "corpus" / "public" / "govdocs1_012_012156.pdf"
TM_SCALED_RUN_SUFFIX = ":p0:c0:o481"
# The `Tf` resource name and size in force at that run's own operator, read off the
# content stream once (`/TT4 1 Tf`) rather than re-scanning for it here -- resolving it
# would mean duplicating `plan_recipe`'s own private Tf scan inside the test.
TM_SCALED_RUN_FONT = "/TT4"
TM_SCALED_RUN_FONT_SIZE = 1.0

# A run on the SAME document whose text-showing operator backs TWO clustered runs -- the
# `run_id` is therefore not unique, and `rewrite_run` refuses it by name
# (`"operator_shared_by_multiple_runs"`) only AFTER `apply_recipe` has already subset and
# embedded a font for it. The one real save-time refusal available without a synthetic
# malformed document; `new_text` is that run's own text, so nothing but the sharing refuses.
SHARED_OPERATOR_RUN_SUFFIX = ":p1:c0:o4257"
SHARED_OPERATOR_TEXT = " " * 20


def test_plan_recipe_fits_against_widths_not_device_space_glyph_advances() -> None:
    """REGRESSION: `plan_recipe` first measured the original run with
    `sum(g.advance[0] for g in run.glyphs)` -- playa's DEVICE-space advances, `Tm` already
    applied -- and compared it against `fit_run`'s purely text-space shaped width. On the
    very common `1 Tf` + scaling `Tm` idiom the two live in different spaces entirely, and
    the ladder refused everything on the page.

    This asserts both halves, so it cannot pass vacuously:

    1. the OLD device-space measurement differs substantially from the font dictionary;
    2. the NEW measurement, through the real `plan_recipe`, uses the dictionary width
       and fits that same no-op edit. Large underflow is now allowed, so an accidental
       device-space measurement must be detected by its width, not by a refusal.

    Any residual delta is pure Liberation-vs-original metric divergence, not a space
    mismatch -- D-07 picked Liberation to make that near-zero.
    """
    source_hash = hashlib.sha256(TM_SCALED_DOC.read_bytes()).hexdigest()
    run_id = source_hash + TM_SCALED_RUN_SUFFIX

    runs = {run.run_id: run for run, _verdict in classify_document(TM_SCALED_DOC).runs}
    run = runs[run_id]
    # Rebuilt exactly as plan_recipe rebuilds it: per-glyph decoded unicode, in glyph
    # order, never display_text (whose synthetic spaces D-03 inserts are not real advance).
    original_text = "".join(glyph.unicode or "" for glyph in run.glyphs)
    assert original_text, "run must decode to real text for this test to mean anything"

    device_space_advance = sum(glyph.advance[0] for glyph in run.glyphs)
    widths_advance = read_original_advance_pt(
        TM_SCALED_DOC, run.page, TM_SCALED_RUN_FONT, original_text, TM_SCALED_RUN_FONT_SIZE
    )
    assert device_space_advance > widths_advance * 5, (
        "this fixture is only a regression case while the two measurements diverge by "
        "the Tm scale -- if they have converged, this test no longer exercises the bug"
    )

    # THE REAL PATH, same run, same text: pin the actual width supplied to fitting.
    report = plan_recipe(
        TM_SCALED_DOC, (RecipeOp(run_id=run_id, new_text=original_text),)
    )
    assert report.ok is True
    (resolved,) = report.resolved
    assert resolved.ok is True
    assert resolved.fit_result is not None
    assert resolved.fit_result.original_advance_pt == pytest.approx(widths_advance)
    assert resolved.fit_result.refused is False
    assert resolved.delta_pt == pytest.approx(0.0, abs=0.01)


def test_plan_recipe_measures_original_by_character_code_not_decoded_unicode() -> None:
    """REGRESSION: the original run's advance was measured from `glyph.unicode` (the
    DECODED character) against the font's `/Widths`, which is indexed by the PDF CHARACTER
    CODE. The identity `ord(decoded) == code` holds for plain ASCII and nowhere else --
    `engine/types.py` exists to keep these apart ("/ToUnicode ... Decides nothing").

    Under `/WinAnsiEncoding` the byte range 0x80-0x9F carries smart quotes, en/em dashes
    and bullets. A run containing one was bounds-checked as U+2018/U+2014/... -- far
    outside any real `FirstChar..LastChar` -- and refused under the generic
    `"resolution_failed"`, which reads like a malformed-font edge case rather than "this
    paragraph uses a curly apostrophe". That is most real typographic prose.

    Replays every editable run of the fixture as a no-op self-replacement, the same
    measurement the review made: 5 of the 188 runs carry a codepoint above 255, and before
    the fix exactly those 5 refused. Asserted at both granularities so a future regression
    cannot hide in the aggregate.
    """
    # Deduplicated by run_id, and that is not defensive tidying: on THIS document two
    # distinct runs on p1 share the operator byte offset `:o4257` (one `TJ` backing two
    # runs -- `rewrite_run`'s own `"operator_shared_by_multiple_runs"` case), so a run ID is
    # not unique here. `plan_recipe` now refuses a recipe carrying a repeated run_id whole,
    # which would make this measurement test report that one reason for all 188 ops instead
    # of the per-run resolution it exists to measure.
    by_id: dict[str, RunRecord] = {}
    for run, verdict in classify_document(TM_SCALED_DOC).runs:
        if verdict.state != "not_editable":
            by_id.setdefault(run.run_id, run)
    runs = list(by_id.values())
    original_texts = {
        run.run_id: "".join(glyph.unicode or "" for glyph in run.glyphs) for run in runs
    }
    non_ascii_ids = {
        run_id
        for run_id, text in original_texts.items()
        if any(ord(ch) > 255 for ch in text)
    }
    assert non_ascii_ids, (
        "fixture must contain runs with codepoints above 255 for this to be non-vacuous "
        "-- these are the runs the bug refused"
    )

    report = plan_recipe(
        TM_SCALED_DOC,
        tuple(
            RecipeOp(run_id=run.run_id, new_text=original_texts[run.run_id])
            for run in runs
        ),
    )

    # (1) The failure class is gone entirely, not merely reduced.
    assert not [r for r in report.resolved if r.reason == "resolution_failed"]

    # (2) Specifically, every run that carries a non-ASCII codepoint now resolves. Before
    #     the fix these were exactly the failures, one for one.
    resolved_by_id = {r.op.run_id: r for r in report.resolved}
    assert all(resolved_by_id[run_id].ok for run_id in non_ascii_ids)

    # (3) Preview also discloses the shared-operator refusal that used to appear
    #     only at apply time. Neither refusal is a character-width lookup failure.
    refusals = [r for r in report.resolved if not r.ok]
    assert all(
        r.reason is not None and (r.reason.startswith("no mapping table entry")
                                 or r.reason == "operator_shared_by_multiple_runs")
        for r in refusals
    )


# --------------------------------------------------------------------------------------
# 03-07 Task 3: apply_recipe -- D-11's all-or-nothing write, D-13's one-subset-per-family
# save-time orchestration, EDIT-04's named-or-passed-through refusal vocabulary.
# --------------------------------------------------------------------------------------


def _build_apply_fixture(path: Path) -> None:
    """A three-run single-page document covering every routing outcome `apply_recipe`
    must ORCHESTRATE (as opposed to merely resolve, which `plan_fixture` already covers).

    * `/F1` -- BaseFont `/Arial` with the bundled LiberationSans-Regular embedded as
      `/FontFile2`: `editable_original`, so it drives the NON-substituting rewrite path,
      and (per D-05/Pattern 4) the SUBSTITUTING one too the moment `new_text` carries a
      character `/WinAnsiEncoding` has no code for -- mapping to `("Sans", "Regular")`.
    * `/F2` -- unembedded `/Helvetica`: `editable_substitution`, also `("Sans", "Regular")`.
      Together with `/F1`'s substituting form this is the D-13 same-key pair.
    * `/F3` -- unembedded `/Times-Roman`: `editable_substitution`, `("Serif", "Regular")` --
      a SECOND distinct key, which `plan_fixture` has no font for.

    Both unembedded fonts carry a real `/Widths` (see `_liberation_widths`); `plan_fixture`'s
    own unembedded fonts deliberately do not, because its tests refuse before that is read.
    """
    pdf = pikepdf.Pdf.new()
    page = pdf.add_blank_page(page_size=(612, 792))

    descriptor = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/FontDescriptor"),
                "/FontName": pikepdf.Name("/Arial"),
                "/Flags": 32,
                "/FontBBox": pikepdf.Array([-203, -303, 1050, 910]),
                "/ItalicAngle": 0,
                "/Ascent": 905,
                "/Descent": -212,
                "/CapHeight": 715,
                "/StemV": 80,
                "/FontFile2": pdf.make_stream(
                    liberation_font_path("Sans", "Regular").read_bytes()
                ),
            }
        )
    )

    def _font(
        subtype: str, base_font: str, family: BundledFamily, descriptor_obj: object = None
    ) -> pikepdf.Object:
        entries = {
            "/Type": pikepdf.Name("/Font"),
            "/Subtype": pikepdf.Name(subtype),
            "/BaseFont": pikepdf.Name(base_font),
            "/FirstChar": FIRST_CHAR,
            "/LastChar": LAST_CHAR,
            "/Widths": pikepdf.Array(_liberation_widths(family, "Regular")),
            "/Encoding": pikepdf.Name("/WinAnsiEncoding"),
        }
        if descriptor_obj is not None:
            entries["/FontDescriptor"] = descriptor_obj
        return pdf.make_indirect(pikepdf.Dictionary(entries))

    fonts = pikepdf.Dictionary(
        {
            "/F1": _font("/TrueType", "/Arial", "Sans", descriptor),
            "/F2": _font("/Type1", "/Helvetica", "Sans"),
            "/F3": _font("/Type1", "/Times-Roman", "Serif"),
        }
    )
    page.Resources = pikepdf.Dictionary({"/Font": fonts})
    page.Contents = pdf.make_stream(
        b"BT /F1 12 Tf 72 700 Td (Hello world) Tj ET\n"
        b"BT /F2 12 Tf 72 660 Td (Second line) Tj ET\n"
        b"BT /F3 12 Tf 72 620 Td (Third line) Tj ET\n"
    )

    # A SECOND PAGE carrying one `/F1` run. Its only job is to be on a DIFFERENT
    # `(page, part, xobj_path)` from every page-0 run, so a recipe can pair a page-0 op with
    # a page-1 op and reach `rewrite_run` with the records `plan_recipe` produced -- no
    # re-derivation, because nothing this recipe edits shares a part.
    page2 = pdf.add_blank_page(page_size=(612, 792))
    page2.Resources = pikepdf.Dictionary({"/Font": fonts})
    page2.Contents = pdf.make_stream(b"BT /F1 12 Tf 72 700 Td (Fourth line) Tj ET\n")

    pdf.save(str(path))
    pdf.close()


@pytest.fixture(scope="module")
def apply_fixture(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("apply_recipe") / "apply_fixture.pdf"
    _build_apply_fixture(path)
    return path


def _apply_run_ids(path: Path) -> dict[str, str]:
    """`{"F1": run_id, ...}` for the apply fixture's four runs, in stream order --
    `F1`/`F2`/`F3` on page 0's single part, `P2` alone on page 1's."""
    runs = classify_document(path).runs
    assert len(runs) == 4, "apply fixture must produce exactly four runs"
    ids = {f"F{i + 1}": run.run_id for i, (run, _verdict) in enumerate(runs)}
    ids["P2"] = ids.pop("F4")
    return ids


def _page_fonts(path: Path) -> dict[str, str]:
    """`{resource key: /Subtype}` for page 0's `/Resources /Font` -- the observable
    surface D-13 is counted on."""
    with pikepdf.open(path) as pdf:
        fonts = pdf.pages[0].Resources.Font
        return {str(key): str(value.get("/Subtype")) for key, value in fonts.items()}


def test_apply_recipe_writes_nothing_when_any_op_refuses(
    apply_fixture: Path, tmp_path: Path
) -> None:
    """D-11: one refusal anywhere means NO output file at all -- not a partial one, not an
    empty one -- and the report handed back is `plan_recipe`'s own, unchanged."""
    ids = _apply_run_ids(apply_fixture)
    out = tmp_path / "never_written.pdf"

    recipe = (
        RecipeOp(run_id=ids["F1"], new_text="Hallo world"),
        RecipeOp(run_id="not-a-run-id", new_text="x"),
    )
    report = apply_recipe(apply_fixture, recipe, out)

    assert report.ok is False
    assert [r.reason for r in report.resolved] == [None, "malformed_run_id"]
    assert not out.exists()


def test_apply_recipe_writes_valid_output_for_non_substituting_recipe(
    apply_fixture: Path, tmp_path: Path
) -> None:
    """EDIT-04's happy path end to end: a resolving, non-substituting op produces a file
    that opens cleanly, survives `qpdf --check`, and actually carries the new text."""
    ids = _apply_run_ids(apply_fixture)
    out = tmp_path / "non_substituting.pdf"

    report = apply_recipe(
        apply_fixture, (RecipeOp(run_id=ids["F1"], new_text="Hallo world"),), out
    )

    assert report.ok is True
    assert out.exists()
    with pikepdf.open(out) as pdf:
        assert b"Hallo world" in pdf.pages[0].Contents.read_bytes()
    # No new font object at all: the non-substituting path embeds nothing (D-12/D-13).
    assert _page_fonts(out) == _page_fonts(apply_fixture)

    if shutil.which("qpdf") is not None:
        result = subprocess.run(
            ["qpdf", "--check", str(out)], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stdout or result.stderr


def test_apply_recipe_embeds_one_subset_per_family_across_multiple_substituting_ops(
    apply_fixture: Path, tmp_path: Path
) -> None:
    """D-13, at this plan's own orchestration level: TWO substituting ops that both map to
    `("Sans", "Regular")` must add exactly ONE new Type0 font object covering the union of
    both ops' glyphs -- not one per op.

    The union half is asserted directly against the embedded `/ToUnicode`: every character
    of BOTH replacements must be reachable through the single subset, which is only true if
    the subset was built over the union rather than over either op alone.
    """
    ids = _apply_run_ids(apply_fixture)
    out = tmp_path / "one_subset.pdf"

    # "worlā" forces D-05's edit-time trigger on the EMBEDDED /F1 (U+0101 has no WinAnsi
    # code), which is what makes this op substitute at all; /F2 substitutes by verdict.
    texts = ["Hello worlā", "Second line"]
    report = apply_recipe(
        apply_fixture,
        (
            RecipeOp(run_id=ids["F1"], new_text=texts[0]),
            RecipeOp(run_id=ids["F2"], new_text=texts[1]),
        ),
        out,
    )

    assert report.ok is True
    assert {r.substitution_key for r in report.resolved} == {("Sans", "Regular")}

    before, after = _page_fonts(apply_fixture), _page_fonts(out)
    added = set(after) - set(before)
    assert len(added) == 1, f"expected exactly one new font resource, got {sorted(added)}"
    assert [after[k] for k in added] == ["/Type0"]

    with pikepdf.open(out) as pdf:
        (key,) = added
        to_unicode = pdf.pages[0].Resources.Font[key].ToUnicode.read_bytes().decode("latin-1")
    for char in set("".join(texts)):
        assert char.encode("utf-16-be").hex().upper() in to_unicode.upper(), (
            "the single subset must cover the UNION of both ops' glyphs"
        )


def test_apply_recipe_embeds_one_subset_per_distinct_family_variant_pair(
    apply_fixture: Path, tmp_path: Path
) -> None:
    """The other half of D-13: two ops mapping to two DIFFERENT keys embed two subsets,
    one per key -- the collapse is per `(family, variant)`, never document-wide."""
    ids = _apply_run_ids(apply_fixture)
    out = tmp_path / "two_subsets.pdf"

    report = apply_recipe(
        apply_fixture,
        (
            RecipeOp(run_id=ids["F2"], new_text="Second line"),
            RecipeOp(run_id=ids["F3"], new_text="Third line"),
        ),
        out,
    )

    assert report.ok is True
    assert {r.substitution_key for r in report.resolved} == {
        ("Sans", "Regular"),
        ("Serif", "Regular"),
    }

    before, after = _page_fonts(apply_fixture), _page_fonts(out)
    added = set(after) - set(before)
    assert len(added) == 2, f"expected exactly two new font resources, got {sorted(added)}"
    assert sorted(after[k] for k in added) == ["/Type0", "/Type0"]


def test_apply_recipe_calls_subset_font_for_family_once_per_key(
    apply_fixture: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The D-13 proof at the call level rather than the artifact level: THREE substituting
    ops across TWO distinct keys must produce exactly TWO `subset_font_for_family` calls.
    Counting the saved output's font objects alone could not tell "subset once" from
    "subset three times and embed the last one"."""
    ids = _apply_run_ids(apply_fixture)
    out = tmp_path / "spied.pdf"

    real = recipe_module.subset_font_for_family
    calls: list[tuple[BundledFamily, BundledVariant]] = []

    def _spy(
        family: BundledFamily, variant: BundledVariant, glyph_names: frozenset[str]
    ) -> SubsetFont:
        calls.append((family, variant))
        return real(family, variant, glyph_names)

    monkeypatch.setattr(recipe_module, "subset_font_for_family", _spy)

    report = apply_recipe(
        apply_fixture,
        (
            RecipeOp(run_id=ids["F1"], new_text="Hello worlā"),
            RecipeOp(run_id=ids["F2"], new_text="Second line"),
            RecipeOp(run_id=ids["F3"], new_text="Third line"),
        ),
        out,
    )

    assert report.ok is True
    assert sorted(calls) == [("Sans", "Regular"), ("Serif", "Regular")]


def test_apply_recipe_discards_mutation_and_writes_nothing_on_rewrite_failure(
    apply_fixture: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-11's SAVE-TIME half, which the refusal test above cannot reach: `plan_recipe`
    says every op is fine, the first `rewrite_run` genuinely mutates the in-memory pdf,
    and only then does the second one fail.

    `engine/rewrite.py`'s module docstring is explicit that a `RewriteOutcome(ok=False)`
    does NOT undo the mutation already applied, so the only correct response is to discard
    the whole handle. Proven by the output path not existing afterwards, and by the
    returned report carrying that call's OWN `RewriteOutcome.reason` -- not `plan_recipe`'s
    report, which said `ok=True`.

    The failure is injected by handing the second op a deliberately-wrong `FitResult`
    AFTER `plan_recipe` has validated it, which is the one failure `rewrite_run` reports
    without needing a malformed document to produce it.

    The two ops sit on DIFFERENT PAGES on purpose. Two ops on one part now go through
    `_rederive_op`, which recomputes the `FitResult` from the document and would simply
    discard the injection -- correct behaviour, and it would make this test vacuous.
    """
    ids = _apply_run_ids(apply_fixture)
    out = tmp_path / "never_saved.pdf"
    injected_reason = "synthetic_wrong_fit_result"

    real_plan = recipe_module.plan_recipe
    planned: list[RecipeReport] = []

    def _plan_then_break_second_op(
        pdf_path: str | Path, recipe: tuple[RecipeOp, ...], password: str = ""
    ) -> RecipeReport:
        report = real_plan(pdf_path, recipe, password=password)
        planned.append(report)
        second = report.resolved[1]
        assert second.fit_result is not None
        broken = dataclasses.replace(
            second, fit_result=dataclasses.replace(
                second.fit_result, refused=True, refusal_reason=injected_reason
            )
        )
        return RecipeReport(
            ok=report.ok, resolved=(report.resolved[0], broken, *report.resolved[2:])
        )

    monkeypatch.setattr(recipe_module, "plan_recipe", _plan_then_break_second_op)

    report = apply_recipe(
        apply_fixture,
        (
            RecipeOp(run_id=ids["F1"], new_text="Hallo world"),
            RecipeOp(run_id=ids["P2"], new_text="Fourth line"),
        ),
        out,
    )

    # Not a pass-through: planning itself succeeded, so this refusal was minted at save.
    assert planned[0].ok is True
    assert report.ok is False
    assert report.resolved[0].ok is True
    assert report.resolved[1].ok is False
    assert report.resolved[1].reason == injected_reason
    assert not out.exists()


# --------------------------------------------------------------------------------------
# 03-07 Task 3 review fixes: two ops on ONE content-stream part, and duplicate run_ids.
# --------------------------------------------------------------------------------------


def test_apply_recipe_second_op_on_same_part_restores_its_own_font(
    apply_fixture: Path, tmp_path: Path
) -> None:
    """REGRESSION (review, Critical, scenario 1): op 2's `Tf` restore emitted op 1's
    freshly-embedded Identity-H CID font instead of its own resource.

    Both ops live on page 0's single content-stream part. `rewrite_instructions`
    re-serialises that whole part for op 1, so every byte offset in it shifts -- and
    `rewrite_run` resolves the run's font by scanning BACKWARDS from the run's raw byte
    offset for the nearest preceding `Tf`. Op 2's stale offset landed inside op 1's
    rewritten region, so `/F2`'s restore was written as `/FHEQFEO` (op 1's CID subset),
    leaving a CID font in force past `ET` -- the exact D-02 hazard the restore exists to
    prevent -- and `apply_recipe` returned `ok=True`. `_correlate`'s `"stale_run_index"`
    check never fired: it compares ORDINAL counts of text-showing operators, which are
    identical before and after.

    Each edited block must open AND close with its own font: two `/Fn 12 Tf` occurrences.
    """
    ids = _apply_run_ids(apply_fixture)
    out = tmp_path / "same_part_fonts.pdf"

    report = apply_recipe(
        apply_fixture,
        (
            RecipeOp(run_id=ids["F1"], new_text="Hello worlā"),
            RecipeOp(run_id=ids["F2"], new_text="Second line"),
        ),
        out,
    )

    assert report.ok is True, [r.reason for r in report.resolved]
    with pikepdf.open(out) as pdf:
        content = pdf.pages[0].Contents.read_bytes()
    assert content.count(b"/F1 12 Tf") == 2, content.decode("latin-1")
    assert content.count(b"/F2 12 Tf") == 2, content.decode("latin-1")


def _build_differences_fixture(path: Path) -> None:
    """Three runs on ONE content-stream part, the second font carrying a `/Differences`
    encoding that SWAPS the codes for `A` and `B`.

    Under `/FB`, code 65 draws `B` and code 66 draws `A`. So the run written `(AB)` reads
    "BA", and a replacement of `"AB"` must be encoded as the bytes `BA`. Encoding it
    through `/FA`'s plain `/WinAnsiEncoding` instead produces `AB` -- which renders as
    "BA", the reverse of what was asked for, with no error anywhere.

    The middle `(filler)` run exists purely to put a SECOND `/FA ... Tf` between the two
    edited runs, so that op 3's stale byte offset lands after a valid simple-font `Tf` and
    the wrong encoding is used SILENTLY, rather than landing on the CID subset font (which
    refuses instead). Op 1 substitutes (`ā` has no WinAnsi code), and a substituted run
    serialises far longer than its original, which is what pushes the later offsets out of
    position in the first place.
    """
    pdf = pikepdf.Pdf.new()
    page = pdf.add_blank_page(page_size=(612, 792))
    program = pdf.make_stream(liberation_font_path("Sans", "Regular").read_bytes())
    widths = _liberation_widths("Sans", "Regular")

    def _font(encoding: pikepdf.Object) -> pikepdf.Object:
        descriptor = pdf.make_indirect(
            pikepdf.Dictionary(
                {
                    "/Type": pikepdf.Name("/FontDescriptor"),
                    "/FontName": pikepdf.Name("/Arial"),
                    "/Flags": 32,
                    "/FontBBox": pikepdf.Array([-203, -303, 1050, 910]),
                    "/ItalicAngle": 0,
                    "/Ascent": 905,
                    "/Descent": -212,
                    "/CapHeight": 715,
                    "/StemV": 80,
                    "/FontFile2": program,
                }
            )
        )
        return pdf.make_indirect(
            pikepdf.Dictionary(
                {
                    "/Type": pikepdf.Name("/Font"),
                    "/Subtype": pikepdf.Name("/TrueType"),
                    "/BaseFont": pikepdf.Name("/Arial"),
                    "/FirstChar": FIRST_CHAR,
                    "/LastChar": LAST_CHAR,
                    "/Widths": pikepdf.Array(widths),
                    "/Encoding": encoding,
                    "/FontDescriptor": descriptor,
                }
            )
        )

    swapped = pikepdf.Dictionary(
        {
            "/Type": pikepdf.Name("/Encoding"),
            "/BaseEncoding": pikepdf.Name("/WinAnsiEncoding"),
            "/Differences": pikepdf.Array([65, pikepdf.Name("/B"), pikepdf.Name("/A")]),
        }
    )
    page.Resources = pikepdf.Dictionary(
        {
            "/Font": pikepdf.Dictionary(
                {"/FA": _font(pikepdf.Name("/WinAnsiEncoding")), "/FB": _font(swapped)}
            )
        }
    )
    page.Contents = pdf.make_stream(
        b"BT /FA 12 Tf 72 700 Td (a a a a a a) Tj ET\n"
        b"BT /FA 12 Tf 72 680 Td (filler) Tj ET\n"
        b"BT /FB 12 Tf 72 660 Td (AB) Tj ET\n"
    )
    pdf.save(str(path))
    pdf.close()


def test_apply_recipe_second_op_on_same_part_uses_its_own_encoding(
    tmp_path: Path,
) -> None:
    """REGRESSION (review, Critical, scenario 2): op 2's replacement was encoded through a
    DIFFERENT run's font `/Encoding`, producing visibly reversed text with `ok=True`.

    Same mechanism as the `Tf`-restore case above -- a stale byte offset resolving the
    wrong font -- but the consequence here is the one a reader actually sees. Measured
    before the fix: the output carried `(AB)`, which `/FB`'s `/Differences` renders as
    "BA", the reverse of the requested "AB". No refusal, no warning.
    """
    src = tmp_path / "differences.pdf"
    _build_differences_fixture(src)
    run_ids = [run.run_id for run, _verdict in classify_document(src).runs]
    assert len(run_ids) == 3
    out = tmp_path / "differences_out.pdf"

    report = apply_recipe(
        src,
        (
            RecipeOp(run_id=run_ids[0], new_text="b b b b b ā"),
            RecipeOp(run_id=run_ids[2], new_text="AB"),
        ),
        out,
    )

    assert report.ok is True, [r.reason for r in report.resolved]
    with pikepdf.open(out) as pdf:
        content = pdf.pages[0].Contents.read_bytes()
    # `/FB` swaps the two codes, so "AB" must be written as the bytes `BA`.
    assert b"(BA)" in content, content.decode("latin-1")
    assert b"(AB)" not in content, content.decode("latin-1")


def test_apply_recipe_refuses_by_name_when_a_re_derived_run_cannot_be_matched(
    apply_fixture: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The re-derivation guard's own refusal path: when the freshly classified page offers
    no unambiguous match for a later op's run, that op refuses BY NAME and D-11 still
    holds -- never a fall back to the stale records the whole fix exists to stop using."""
    ids = _apply_run_ids(apply_fixture)
    out = tmp_path / "unmatched.pdf"
    monkeypatch.setattr(recipe_module, "_match_run", lambda *_args: None)

    report = apply_recipe(
        apply_fixture,
        (
            RecipeOp(run_id=ids["F1"], new_text="Hello worlā"),
            RecipeOp(run_id=ids["F2"], new_text="Second line"),
        ),
        out,
    )

    assert report.ok is False
    assert report.resolved[1].reason == "run_lost_after_earlier_edit"
    assert not out.exists()


def test_apply_recipe_refuses_when_re_derivation_changes_the_substitution_key(
    apply_fixture: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-13's glyph union is built from the PLANNED keys and embedded before any rewrite,
    so a re-derived op that now wants a different bundled face must refuse rather than
    reference a subset that was never asked to cover its glyphs."""
    ids = _apply_run_ids(apply_fixture)
    out = tmp_path / "key_changed.pdf"

    real_resolve = recipe_module._resolve_op
    calls: list[int] = []

    def _resolve_then_switch_key(*args: object, **kwargs: object) -> object:
        result = real_resolve(*args, **kwargs)  # type: ignore[arg-type]
        calls.append(1)
        # Only the RE-DERIVE call (after plan_recipe's own two) gets the switched key.
        if len(calls) > 2 and result.ok:
            return dataclasses.replace(result, substitution_key=("Serif", "Regular"))
        return result

    monkeypatch.setattr(recipe_module, "_resolve_op", _resolve_then_switch_key)

    report = apply_recipe(
        apply_fixture,
        (
            RecipeOp(run_id=ids["F1"], new_text="Hello worlā"),
            RecipeOp(run_id=ids["F2"], new_text="Second line"),
        ),
        out,
    )

    assert report.ok is False
    assert report.resolved[1].reason == "substitution_key_changed_after_earlier_edit"
    assert not out.exists()


def test_plan_recipe_refuses_a_recipe_carrying_a_duplicate_run_id(
    apply_fixture: Path, tmp_path: Path
) -> None:
    """REGRESSION (review, Important): two ops naming the SAME run both reported `ok=True`
    while only the second op's text survived in the output -- a report claiming two edits
    landed when the document can only carry one.

    Refused whole at `plan_recipe`, before any resolution work, so `apply_recipe` writes
    nothing and no op is credited with an edit that did not happen.
    """
    ids = _apply_run_ids(apply_fixture)
    duplicated = (
        RecipeOp(run_id=ids["F1"], new_text="Hallo world"),
        RecipeOp(run_id=ids["F1"], new_text="Hullo world"),
    )

    report = plan_recipe(apply_fixture, duplicated)
    assert report.ok is False
    assert [r.reason for r in report.resolved] == ["duplicate_run_id_in_recipe"] * 2

    out = tmp_path / "duplicate.pdf"
    assert apply_recipe(apply_fixture, duplicated, out).ok is False
    assert not out.exists()


# `engine/recipe.py`'s OWN refusal vocabulary -- the complete fixed set this module invents
# rather than passes through. Anything outside it must be byte-identical to a string another
# module already produced. Kept honest by `test_module_own_reasons_matches_the_source`
# below, which reads the literals back out of the module rather than trusting this list.
MODULE_OWN_REASONS = frozenset(
    {
        "malformed_run_id",
        "source_hash_mismatch",
        "run_id_not_found",
        "resolution_failed",
        "fit_refused",
        "duplicate_run_id_in_recipe",
        "run_lost_after_earlier_edit",
        "substitution_key_changed_after_earlier_edit",
        "character_has_no_glyph_in_bundled_font",
        "font_size_change_unsupported",
    }
)


def test_module_own_reasons_matches_the_source() -> None:
    """`MODULE_OWN_REASONS` is the fixed set the EDIT-04 test measures against, so it must
    not drift from the module. Every name here has to appear verbatim in `engine/recipe.py`,
    and every bare-string reason the module assigns has to appear here -- otherwise a newly
    invented reason would be waved through as "already in the allowed set"."""
    source = Path(recipe_module.__file__).read_text()
    for reason in MODULE_OWN_REASONS:
        assert f'"{reason}"' in source, f"{reason!r} is no longer in engine/recipe.py"

    # Every `reason="..."` / `reason=(...)`-shaped literal the module assigns to a refusal.
    assigned = set(re.findall(r'reason=\s*"([a-z_]+)"', source))
    assigned |= set(re.findall(r'or\s+"([a-z_]+)"', source))
    assigned |= set(re.findall(r'return\s+"([a-z_]+)"', source))
    assert assigned <= MODULE_OWN_REASONS, (
        f"engine/recipe.py mints reasons this test does not know about: "
        f"{sorted(assigned - MODULE_OWN_REASONS)}"
    )


def _raise_for_resolution_failure(_font: object) -> object:
    """Stand-in for `engine.recipe.resolve_font`, which is only ever called INSIDE
    `_resolve_op`'s classify-never-crash guard -- so raising here is the one honest way to
    make a real `"resolution_failed"` happen."""
    raise RuntimeError("font resolution exploded")


def test_refusal_reasons_are_named_not_generic(
    apply_fixture: Path, plan_fixture: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VALIDATION.md's pinned EDIT-04 check, over every refusal path Tasks 1-3 can reach.

    Each collected reason must be either one of this module's own fixed strings
    (`MODULE_OWN_REASONS`, itself checked against the source by the test above) or
    BYTE-IDENTICAL to a string obtained by calling the underlying producer
    (`RunVerdict` / `MappingVerdict` / `FitResult` / `RewriteOutcome`) directly for the same
    input -- and no reason may contain any op's `new_text`, which is document content.

    Sampled paths, named rather than counted (the earlier version of this test asserted a
    bare `len(collected) == 7` under a comment claiming exhaustiveness, which pinned a
    hand-curated subset and quietly missed both `"resolution_failed"` and every reason
    `apply_recipe`'s own save-time substitution mints):

    * `plan_recipe`'s four early named checks, plus its two pass-throughs
      (`RunVerdict` / `MappingVerdict`) and the fit ladder's own reason;
    * a genuine `"resolution_failed"`, driven by making a call inside the catch-all raise;
    * a genuine `"duplicate_run_id_in_recipe"`;
    * a genuine SAVE-TIME `RewriteOutcome` reason -- a real corpus run whose text-showing
      operator backs two runs, refused by `rewrite_run` as
      `"operator_shared_by_multiple_runs"` only after `apply_recipe` has already subset and
      embedded a font for it. That is the path `_refuse_at` substitutes through, and it was
      previously unsampled, so EDIT-04's "no document content in the reason" guarantee was
      unverified for exactly the reasons this task mints.

    The two re-derivation reasons are driven by their own dedicated tests above
    (`..._cannot_be_matched`, `..._changes_the_substitution_key`) and are content-free
    literals checked by `test_module_own_reasons_matches_the_source`.
    """
    plan_ids = _run_ids_by_font(plan_fixture)
    apply_ids = _apply_run_ids(apply_fixture)

    # --- the independently-obtained side, computed WITHOUT going through engine.recipe ---
    type3_reason = plan_ids["F4"][1].reason
    mapping_reason = lookup_bundled_font("NoSuchFontFamily").reason

    # A replacement far too long for its run refuses at the fit ladder. Reconstructed here
    # from the same three inputs plan_recipe feeds it: the run's own /Widths advance over
    # its own character codes, the bundled program (which IS /F1's embedded FontFile2), and
    # the /Tf size in force.
    overlong = "Hello world, and then a great deal more text than ever fitted here"
    run = {r.run_id: r for r, _v in classify_document(apply_fixture).runs}[apply_ids["F1"]]
    with pikepdf.open(apply_fixture) as pdf:
        original_advance_pt = advance_pt_for_codes(
            pdf.pages[0].Resources.Font["/F1"], [g.code for g in run.glyphs], 12.0
        )
    direct_fit = fit_run(
        original_advance_pt,
        overlong,
        load_font(liberation_font_path("Sans", "Regular").read_bytes()),
        12.0,
    )
    assert direct_fit.refused is True, "this op must actually refuse for the check to bind"

    # A rewrite refusal that preview now discloses, independently obtained from
    # rewrite_run on the genuine indexed run and its sibling operators.
    shared_run_id = (
        hashlib.sha256(TM_SCALED_DOC.read_bytes()).hexdigest() + SHARED_OPERATOR_RUN_SUFFIX
    )
    shared_op = RecipeOp(run_id=shared_run_id, new_text=SHARED_OPERATOR_TEXT)
    shared_plan = plan_recipe(TM_SCALED_DOC, (shared_op,))
    assert not shared_plan.ok
    shared_runs = classify_document(TM_SCALED_DOC).runs
    shared_run, shared_verdict = next((run, verdict) for run, verdict in shared_runs
                                     if run.run_id == shared_run_id)
    with pikepdf.open(TM_SCALED_DOC) as shared_pdf:
        direct_outcome = rewrite_run(
            shared_pdf,
            shared_run.page,
            shared_run,
            shared_verdict,
            [run for run, _verdict in shared_runs if run.page == shared_run.page],
            shared_op.new_text,
            FitResult(0.0, 0.0, 0.0, "trailing_kern", []),
        )
    assert direct_outcome.ok is False, "this run must actually refuse at rewrite time"
    assert shared_plan.resolved[0].reason == direct_outcome.reason

    known_foreign = {
        type3_reason,
        mapping_reason,
        direct_fit.refusal_reason,
        direct_outcome.reason,
    }

    # --- every reason engine.recipe itself produces, across all three layers ---
    # Distinctive multi-character sentinels, deliberately not single letters: a one-letter
    # `new_text` would be "found" inside ordinary English words in fit.py's measured-value
    # prose ("exceeds" contains an "x") and the leak check would fail vacuously without any
    # content actually having leaked.
    new_texts = {
        "malformed": "Zarquon",
        "hash": "Hallo world",
        "unknown": "Bellerophon",
        "type3": "Quuxwhistle",
        "mapping": "Vorpalblade",
        "fit": overlong,
    }
    source_hash = decode_run_id(plan_ids["F1"][0])["source_hash"]
    plan_report = plan_recipe(
        plan_fixture,
        (
            RecipeOp(run_id="not-a-run-id", new_text=new_texts["malformed"]),
            RecipeOp(run_id="0" * 64 + plan_ids["F1"][0][64:], new_text=new_texts["hash"]),
            RecipeOp(run_id=f"{source_hash}:p0:c0:o999999", new_text=new_texts["unknown"]),
            RecipeOp(run_id=plan_ids["F4"][0], new_text=new_texts["type3"]),
            RecipeOp(run_id=plan_ids["F3"][0], new_text=new_texts["mapping"]),
        ),
    )
    fit_report = plan_recipe(
        apply_fixture, (RecipeOp(run_id=apply_ids["F1"], new_text=new_texts["fit"]),)
    )
    # apply_recipe's own layer: the refusing recipe returns its report and writes nothing.
    out = tmp_path / "not_written.pdf"
    apply_report = apply_recipe(apply_fixture, (fit_report.resolved[0].op,), out)
    assert not out.exists()

    # apply_recipe's SAVE-TIME reason substitution (`_refuse_at`), on a real corpus run.
    shared_out = tmp_path / "shared_operator.pdf"
    shared_report = apply_recipe(TM_SCALED_DOC, (shared_op,), shared_out)
    assert shared_report.ok is False
    assert not shared_out.exists()

    # A genuine "resolution_failed": a call that only happens INSIDE plan_recipe's
    # classify-never-crash guard is made to raise.
    monkeypatch.setattr(recipe_module, "resolve_font", _raise_for_resolution_failure)
    failed_report = plan_recipe(
        apply_fixture, (RecipeOp(run_id=apply_ids["F1"], new_text=new_texts["hash"]),)
    )
    monkeypatch.undo()

    # A genuine "duplicate_run_id_in_recipe".
    duplicate_report = plan_recipe(
        apply_fixture,
        (
            RecipeOp(run_id=apply_ids["F1"], new_text=new_texts["hash"]),
            RecipeOp(run_id=apply_ids["F1"], new_text=new_texts["unknown"]),
        ),
    )

    collected = [
        r.reason
        for report in (
            plan_report,
            fit_report,
            apply_report,
            shared_report,
            failed_report,
            duplicate_report,
        )
        for r in report.resolved
        if r.reason is not None
    ]
    # Named, not counted: every path this test claims to sample must actually have fired.
    assert set(collected) == {
        "malformed_run_id",
        "source_hash_mismatch",
        "run_id_not_found",
        "resolution_failed",
        "duplicate_run_id_in_recipe",
        type3_reason,
        mapping_reason,
        direct_fit.refusal_reason,
        direct_outcome.reason,
    }, sorted(set(collected))

    for reason in collected:
        assert reason in MODULE_OWN_REASONS or reason in known_foreign, (
            f"unnamed/invented refusal reason: {reason!r}"
        )
        for text in new_texts.values():
            assert text not in reason, f"reason leaks document content: {reason!r}"
