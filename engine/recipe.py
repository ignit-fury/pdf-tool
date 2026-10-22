"""Recipe contract -- the JSON edit format this project replays against a document.

D-09: an edit is a JSON recipe, a list of `{run_id, new_text}` ops --
`pdftool edit doc.pdf --recipe r.json -o out.pdf` replays them. This format IS
Phase 4's wire format unchanged (CLAUDE.md: the client sends the operation log,
not the mutated file), so this module's shape is load-bearing beyond this CLI
phase. D-10: every op's `run_id` embeds a source hash checked against the
document actually opened, hard-refusing the whole recipe on mismatch -- no
override flag, because a mismatched hash means a byte offset that may land
mid-token, not a genuine edit. D-11: recipe application is all-or-nothing --
any refusal means nothing is written. D-13: substituted runs across the whole
recipe are collected into one subset per bundled family, emitted once at save,
which requires seeing the complete, validated edit set up front. EDIT-04:
every refusal this module produces is a small fixed named reason, or an
unmodified pass-through of an existing module's own named verdict -- never
invented prose, never `new_text` or decoded document content.

This module has three layers, built across this plan's tasks:

- `parse_recipe` (this task): untrusted bytes -> `tuple[RecipeOp, ...]`. Stdlib
  `json.loads` only, never `eval` -- the same posture `engine/run_id.py` takes
  for untrusted string parsing (strict regex, never `eval`/unchecked
  `str.split`). Also the recipe-size DoS guard named in 03-RESEARCH.md's
  Security Domain ("Recipe JSON with an implausibly large op count / string
  length" -- Known Threat Patterns table): bounded before any per-op work.
- `plan_recipe` (Task 2): resolves each `RecipeOp.run_id` against an opened
  document via `decode_run_id` plus that document's own current run map
  (`classify_document`), enforcing D-10's source-hash refusal, D-05/D-06's
  substitution routing, and the fit ladder -- writing nothing.
- `apply_recipe` (Task 3): D-11's all-or-nothing write, D-13's once-per-save
  font subsetting.
"""

from __future__ import annotations

import hashlib
from bisect import bisect_right
from functools import lru_cache
import json
import math
import re
import tempfile
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TypedDict, cast

import pikepdf

from engine.classify_run import RunVerdict, stream_bytes_and_resources
from engine.encoding_table import embedded_font_bytes, resolve_font
from engine.fit import FitResult, advance_pt_for_codes, fit_run, load_font
from engine.fonts import (
    BundledFamily,
    BundledVariant,
    SubsetFont,
    embed_type0_font,
    has_unmapped_glyph,
    liberation_font_path,
    lookup_bundled_font,
    run_needs_substitution,
    shape_cids,
    shape_glyph_names,
    subset_cid_widths,
    subset_font_for_family,
    substitution_unicode_reason,
)
from engine.index import RunIndex
from engine.records import RunRecord
from engine.rewrite import RewriteOutcome, rewrite_run, rewrite_preflight_refusal
from engine.run_id import decode_run_id

# 03-RESEARCH.md Security Domain, Known Threat Patterns table: "Recipe JSON with an
# implausibly large op count ... used to exhaust memory or CPU in a single `pdftool
# edit` invocation" -- "low priority for a CLI-only phase with a human operator, but
# worth naming now". engine/index.py's own module docstring measures ~50 runs/page;
# a 1000-page document is ~50,000 runs, so this is generous headroom for a single
# edit session, a reasoned ceiling rather than a corpus measurement.
MAX_RECIPE_OPS = 50_000

# A recipe op replaces ONE content-stream run (a line/fragment), never a document
# body -- this is generously above any plausible single run's text while still
# bounding one op's shaping cost.
MAX_NEW_TEXT_CHARS = 10_000


class RecipeStyle(TypedDict, total=False):
    font_family: BundledFamily
    color: list[float]
    bold: bool
    italic: bool
    font_size: float


def _validated_style(value: object) -> RecipeStyle:
    if not isinstance(value, dict) or set(value) - {"color", "bold", "italic", "font_size", "font_family"}:
        raise ValueError("invalid recipe style object")
    if "font_family" in value and (not isinstance(value["font_family"], str) or value["font_family"] not in ("Sans", "Serif", "Mono")):
        raise ValueError("style font_family must be Sans, Serif or Mono")
    for key in ("bold", "italic"):
        if key in value and type(value[key]) is not bool:
            raise ValueError("style weight and italic must be booleans")
    if "color" in value:
        color = value["color"]
        if not isinstance(color, list) or len(color) != 3 or any(
            type(c) not in (int, float) or not math.isfinite(c) or not 0 <= c <= 1
            for c in color
        ):
            raise ValueError("style color must be three finite RGB components in 0..1")
    if "font_size" in value:
        size = value["font_size"]
        if type(size) not in (int, float) or not math.isfinite(size) or size <= 0:
            raise ValueError("style font_size must be finite and positive")
    return cast(RecipeStyle, value.copy())


@dataclass(frozen=True, slots=True)
class RecipeOp:
    """One `{run_id, new_text}` edit op (D-09)."""

    run_id: str
    new_text: str
    style: RecipeStyle | None = None


class RecipeTooLargeError(Exception):
    """Raised by `parse_recipe` when a recipe exceeds `MAX_RECIPE_OPS` or any op's
    `new_text` exceeds `MAX_NEW_TEXT_CHARS`. Counts only in the message, never
    document content -- mirrors `engine.index.DocumentTooLargeError`."""


def parse_recipe(data: bytes) -> tuple[RecipeOp, ...]:
    """Parse untrusted recipe JSON bytes into `RecipeOp`s.

    D-09/D-10: this is the untrusted-input boundary for the recipe wire format
    (Phase 4's client-supplied operation log unchanged). Stdlib `json.loads`
    only, never `eval`. Raises `ValueError` on any structural or type mismatch
    (including `json.JSONDecodeError`, already a `ValueError` subclass, left
    to propagate uncaught) and `RecipeTooLargeError` on either size ceiling,
    checked before any per-op `RecipeOp` is constructed.
    """
    parsed = json.loads(data)

    if not isinstance(parsed, list):
        raise ValueError(f"recipe must be a JSON array, got {type(parsed).__name__}")

    if len(parsed) > MAX_RECIPE_OPS:
        raise RecipeTooLargeError(
            f"recipe has {len(parsed)} ops, exceeds MAX_RECIPE_OPS={MAX_RECIPE_OPS}"
        )

    ops: list[RecipeOp] = []
    for i, item in enumerate(parsed):
        if not isinstance(item, dict) or not {"run_id", "new_text"} <= set(item) or set(item) - {"run_id", "new_text", "style"}:
            raise ValueError(
                f"recipe op {i} must be an object with exactly run_id and new_text keys"
            )
        if not isinstance(item["run_id"], str) or not isinstance(item["new_text"], str):
            raise ValueError(f"recipe op {i}: run_id and new_text must both be strings")
        if len(item["new_text"]) > MAX_NEW_TEXT_CHARS:
            raise RecipeTooLargeError(
                f"recipe op {i}: new_text length exceeds MAX_NEW_TEXT_CHARS={MAX_NEW_TEXT_CHARS}"
            )
        style = _validated_style(item["style"]) if "style" in item else None
        ops.append(RecipeOp(run_id=item["run_id"], new_text=item["new_text"], style=style))

    return tuple(ops)


@dataclass(frozen=True, slots=True)
class ResolvedOp:
    """One op's resolution outcome -- everything `apply_recipe` needs to rewrite it, or
    the single named reason it will not be rewritten at all.

    EDIT-04: `reason` is either one of this module's small fixed strings
    (`"malformed_run_id"`, `"source_hash_mismatch"`, `"run_id_not_found"`,
    `"resolution_failed"`, `"character_has_no_glyph_in_bundled_font"`, and
    `"fit_refused"` -- the last a backstop for a `FitResult`
    that refuses without setting its own reason, which `engine.fit` does not currently
    construct but which must never surface as an unnamed refusal) or an UNMODIFIED
    pass-through of another module's own named verdict (`RunVerdict.reason`,
    `MappingVerdict.reason`, `FitResult.refusal_reason`). Never invented prose, and never
    `new_text` or any decoded document content.

    Every field after `reason` is best-effort context: populated only as far as this op's
    resolution actually got before succeeding or refusing, which is why an early refusal
    leaves them `None` rather than half-filled.
    """

    op: RecipeOp
    ok: bool
    reason: str | None = None
    strategy: str | None = None
    delta_pt: float | None = None
    run: RunRecord | None = None
    verdict: RunVerdict | None = None
    all_page_runs: tuple[RunRecord, ...] | None = None
    fit_result: FitResult | None = None
    substitution_key: tuple[BundledFamily, BundledVariant] | None = None


@dataclass(frozen=True, slots=True)
class RecipeReport:
    """D-03's dry run, as data. `ok` is the D-11 all-or-nothing gate: `apply_recipe`
    writes nothing unless every op resolved."""

    ok: bool
    resolved: tuple[ResolvedOp, ...]


# `engine.rewrite._POSITION_EPSILON`'s value and rationale, re-stated here rather than
# imported (it is private to that module, the same precedent the `Tf` scan below follows):
# a re-derived glyph origin measures a delta of exactly 0.0 on unedited content -- pikepdf
# round-trips content-stream numbers as arbitrary-precision Decimal -- so this sits many
# orders of magnitude above observed noise while still catching a real move.
_POSITION_EPSILON = 1e-6

# ISO 32000-1 Table 105/9.3: `/Name size Tf`. Re-implemented locally rather than imported
# from `engine.classify_run._find_active_font_name` / `engine.rewrite._active_font_operands`
# -- both are private to their own modules, and 03-06 already set the precedent that each
# module re-implements this small scan against the same fixed operator syntax instead of
# reaching across a module boundary for a private helper. Same known, deliberately
# inherited exposure as both of those: a raw byte scan cannot tell an operator from the
# same text inside a literal string.
_TF_NAME_SIZE_RE = re.compile(rb"/([^\s/\[\](){}<>%]+)\s+([+-]?[0-9.]+)\s+Tf\b")


@lru_cache(maxsize=1)
def _font_size_history(stream_bytes: bytes) -> tuple[tuple[int, ...], tuple[tuple[bytes, float] | None, ...]]:
    positions: list[int] = []
    values: list[tuple[bytes, float] | None] = []
    for match in _TF_NAME_SIZE_RE.finditer(stream_bytes):
        positions.append(match.start())
        try:
            values.append((match.group(1), float(match.group(2))))
        except ValueError:
            values.append(None)  # Invalid latest Tf must not fall back to an older font.
    return tuple(positions), tuple(values)


def active_font_name_and_size(
    stream_bytes: bytes, byte_offset: int
) -> tuple[bytes, float] | None:
    """The `(resource name, size)` operands of the LAST `Tf` at or before `byte_offset`.

    `None` when no `Tf` precedes the offset, or when the one that does carries a
    `[0-9.]`-shaped operand that is not actually a number (`1.2.3`) -- never a fallback to
    an earlier, cleaner `Tf`, which would silently resolve the wrong font. Classify-never-
    crash: the whole body is guarded, matching `engine.rewrite._correlate`'s pattern.
    """
    try:
        positions, values = _font_size_history(stream_bytes)
        index = bisect_right(positions, byte_offset) - 1
        return values[index] if index >= 0 else None
    except Exception:  # noqa: BLE001 - classify-never-crash, see docstring
        return None


# Compatibility for the Phase 3 gate, whose pinned import predates promotion.
_active_font_name_and_size = active_font_name_and_size


def _base_font_name(font: pikepdf.Object) -> str:
    """`/BaseFont` as a plain mapping-table key: leading `/` removed, and any six-
    uppercase-letter subset tag (`ABCDEF+`, ISO 32000-1 9.6.4) stripped.

    Both strips are load-bearing rather than cosmetic. `str(pikepdf.Name("/Helvetica"))`
    is `"/Helvetica"`, and `BASE_FONT_MAPPING`'s keys carry no slash, so passing the raw
    `str()` to `lookup_bundled_font` would refuse EVERY font in the table -- D-06's
    "refuse by name" turned into "refuse everything". Re-implemented locally, mirroring
    `engine.encoding_table._base_font_name` (private to that module, same precedent as
    the `Tf` scan above); D-06 is untouched -- what reaches the table is still one exact
    dict lookup with no lowercasing, trimming or substring matching.
    """
    base = font.get("/BaseFont")
    if base is None:
        return ""
    name = str(base).lstrip("/")
    if len(name) > 7 and name[6] == "+" and name[:6].isalpha() and name[:6].isupper():
        return name[7:]
    return name


def source_font_info(
    stream_bytes: bytes, resources: pikepdf.Object | None, operator_offset: int
) -> tuple[str | None, BundledFamily | None]:
    """Source identity and a known substitute; never guess an unknown font family."""
    active = active_font_name_and_size(stream_bytes, operator_offset)
    if active is None or resources is None:
        return None, None
    fonts = resources.get("/Font")
    font = fonts.get("/" + active[0].decode("latin-1")) if fonts is not None else None
    if font is None:
        return None, None
    name = font.get("/BaseFont")
    if name is None:
        descriptor = font.get("/FontDescriptor")
        name = descriptor.get("/FontName") if descriptor is not None else None
    return (str(name).lstrip("/") if name is not None else None,
            lookup_bundled_font(_base_font_name(font)).family)


def _part_key(run: RunRecord) -> tuple[int, int, tuple[int, ...]]:
    """The identity of the ONE content-stream part this run lives in: `(page, part,
    xobj_path)`. Every byte offset in a run ID is meaningful only within this scope
    (`engine/run_id.py`), and it is also the unit `apply_recipe`'s staleness tracking works
    in -- `rewrite_instructions` re-serialises a whole part, so an edit invalidates every
    offset in that part and none outside it."""
    parts = decode_run_id(run.run_id)
    return run.page, parts["part"], parts["xobj_path"]


def _resolve_op(
    pdf: pikepdf.Pdf,
    op: RecipeOp,
    run: RunRecord,
    verdict: RunVerdict,
    all_page_runs: tuple[RunRecord, ...],
) -> ResolvedOp:
    """Everything `apply_recipe` needs to rewrite ONE already-located run, or the single
    named reason it will not be rewritten -- see `plan_recipe`'s docstring for the ordered
    rules this implements.

    Split out of `plan_recipe`'s own loop so `apply_recipe` can run the IDENTICAL resolution
    a second time against a part an earlier op already mutated, instead of reusing records
    whose byte offsets that edit invalidated. Every input is read from `pdf`'s CURRENT state
    (the `/Tf` scan, the `/Resources /Font` lookup, the embedded program, the `/Widths`
    measurement), so this is correct against a mutated handle exactly as it is against a
    pristine one -- which is the whole reason it is a function rather than an inlined block.
    """
    if op.style is not None and "font_size" in op.style:
        return ResolvedOp(op, ok=False, reason="font_size_change_unsupported", run=run, verdict=verdict)
    if verdict.state == "not_editable":
        return ResolvedOp(op, ok=False, reason=verdict.reason, run=run, verdict=verdict)

    stateful_reason = rewrite_preflight_refusal(pdf, run.page, run, list(all_page_runs))
    if stateful_reason is not None:
        return ResolvedOp(op, ok=False, reason=stateful_reason, run=run, verdict=verdict)

    _page, part, xobj_path = _part_key(run)
    try:
        stream_bytes, resources = stream_bytes_and_resources(pdf, run.page, part, xobj_path)
        active = active_font_name_and_size(
            stream_bytes, run.glyphs[0].operator_byte_offset
        )
        if active is None:
            raise ValueError("no usable /Tf precedes this run")
        resource_name, font_size = active

        font_key = "/" + resource_name.decode("latin-1")
        fonts = resources.get("/Font") if resources is not None else None
        font_obj = fonts.get(font_key) if fonts is not None else None
        if font_obj is None:
            raise ValueError("active font resource not found in /Resources /Font")

        font_verdict = resolve_font(font_obj)
        program = embedded_font_bytes(font_obj.get("/FontDescriptor"))
        trigger = run_needs_substitution(font_obj, font_verdict, program, op.new_text)
        # Glyph inspection can read raw Type 1/CFF programs, but load_font's
        # replacement shaper requires an sfnt container. Use a bundled face for
        # these originals, with the usual explicit-choice path for unknown names.
        shaping_substitution = program is not None and program.data[:4] not in (
            b"OTTO", b"\x00\x01\x00\x00", b"true", b"typ1"
        )

        substitution_key: tuple[BundledFamily, BundledVariant] | None = None
        change_face = op.style is not None and bool({"bold", "italic", "font_family"}.intersection(op.style))
        chosen_family = op.style.get("font_family") if op.style is not None else None
        if verdict.state == "editable_substitution" or trigger.substitute or shaping_substitution or change_face:
            mapping = lookup_bundled_font(_base_font_name(font_obj))
            # The `family`/`variant` halves are tested alongside `mapped` rather than
            # asserted after it: `MappingVerdict`'s own construction ties them together (a
            # miss sets all three), so this is the same single D-06 refusal either way --
            # but an `assert` here would be control flow that `python -O` strips, turning a
            # broken invariant into a `TypeError` swallowed by the catch-all below as a
            # misleading `"resolution_failed"`. `mapping.reason` is set whenever `mapped` is
            # False, so the refusal is still named by the table, not by this module.
            if chosen_family is None and (not mapping.mapped or mapping.family is None or mapping.variant is None):
                return ResolvedOp(
                    op, ok=False, reason=mapping.reason, run=run, verdict=verdict
                )
            family = chosen_family if chosen_family is not None else mapping.family
            if family is None:
                raise ValueError("no replacement family")
            variant: BundledVariant = mapping.variant or "Regular"
            if change_face and op.style is not None:
                bold = op.style.get("bold", variant in ("Bold", "BoldItalic"))
                italic = op.style.get("italic", variant in ("Italic", "BoldItalic"))
                variant = "BoldItalic" if bold and italic else "Bold" if bold else "Italic" if italic else "Regular"
            substitution_key = (family, variant)
            # D-06 one rung lower, at the CHARACTER level. The mapping table above answers
            # "which bundled face"; this answers "does that face actually have a glyph for
            # every character of `new_text`". Both must hold, and a miss here is the same
            # kind of refusal: Liberation covers Latin/Greek/Cyrillic and little else, so
            # an emoji or any uncovered script shapes to `.notdef`, which `shape_cids`
            # would emit as CID 0 -- a glyph the `/W` array does not cover (it starts at
            # CID 1), silently taking `/DW` and drawing a box. FONT-04 forbids exactly that
            # silent width fallback and EDIT-04 requires the named refusal instead. Checked
            # HERE, in `_resolve_op`, because this is the single funnel every substituting
            # op passes through: `apply_recipe` only ever subsets and shapes for ops whose
            # `substitution_key` this function set on a report where every op resolved
            # (D-11), and `_rederive_op` re-enters this same function for a re-derived op.
            # Checked at PLAN time so the refusal is disclosed before commit (D-03).
            if has_unmapped_glyph(*substitution_key, op.new_text):
                return ResolvedOp(
                    op,
                    ok=False,
                    reason="character_has_no_glyph_in_bundled_font",
                    run=run,
                    verdict=verdict,
                )
            unicode_reason = substitution_unicode_reason(*substitution_key, (op.new_text,))
            if unicode_reason is not None:
                return ResolvedOp(op, ok=False, reason=unicode_reason, run=run, verdict=verdict)
            font_bytes = liberation_font_path(*substitution_key).read_bytes()
        elif program is None:
            raise ValueError("no embedded program to shape the replacement with")
        else:
            font_bytes = program.data

        # BOTH SIDES OF THE COMPARISON MUST LIVE IN THE SAME SPACE. `fit_run` measures the
        # replacement purely in text space scaled by the `Tf` size, so the original must be
        # measured the same way -- from the font DICTIONARY's own `/Widths`//`W`, which is
        # what the viewer actually advances by (Pitfall 5: "the dictionary is what the
        # viewer uses").
        #
        # `sum(glyph.advance[0] for glyph in run.glyphs)` was used here first and is WRONG
        # for this purpose: playa's advances are DEVICE space, with `Tm` already applied. On
        # the very common producer idiom of `1 Tf` plus a scaling `Tm`, the two differ by the
        # whole `Tm` scale -- measured 437.26 vs 36.44 on `govdocs1_012_012156.pdf`, a 12x
        # gap that refused every run on the page, including a no-op replacement of a run's
        # own text with itself. On rotated text the x-component collapses toward 0 instead.
        # Neither is a rounding error, and a `Tm`-free document hid it because there the two
        # agree.
        #
        # Measured with each glyph's own `.code` -- the PDF CHARACTER CODE, which is what
        # `/Widths` is indexed by -- never its decoded `.unicode`. That was the second bug
        # here, and `engine/types.py` exists to name it: `/ToUnicode` "decides nothing".
        # Under `/WinAnsiEncoding` the byte range 0x80-0x9F is smart quotes, en/em dashes and
        # bullets, whose `ord()` values (U+2018, U+2014, ...) fall far outside any real
        # `FirstChar..LastChar` -- so every run of ordinary typographic prose was
        # bounds-checked against the wrong number and refused as `resolution_failed`.
        # Measured on the same document: exactly the 5 runs carrying a codepoint above 255
        # failed, 182 passed.
        #
        # Codes come from `run.glyphs`, never from `run.display_text`, whose synthetic
        # clusterer-inserted spaces (D-03) are not glyphs the original run ever advanced by.
        original_advance_pt = advance_pt_for_codes(
            font_obj, [glyph.code for glyph in run.glyphs], font_size
        )

        fit_result = fit_run(
            original_advance_pt, op.new_text, load_font(font_bytes), font_size
        )
    except Exception:  # noqa: BLE001 - classify-never-crash, see plan_recipe's docstring
        return ResolvedOp(op, ok=False, reason="resolution_failed")

    # `engine.fit.fit_run` spells the refusing rung `"refused"`; `engine.rewrite` accepts
    # both spellings rather than betting on one, and so does this. The `or "fit_refused"`
    # covers a FitResult carrying `refused=True` with no reason set -- an unnamed refusal is
    # exactly what EDIT-04 forbids.
    if fit_result.refused or fit_result.strategy in ("refuse", "refused"):
        return ResolvedOp(
            op,
            ok=False,
            reason=fit_result.refusal_reason or "fit_refused",
            run=run,
            verdict=verdict,
            fit_result=fit_result,
        )

    return ResolvedOp(
        op,
        ok=True,
        strategy=fit_result.strategy,
        delta_pt=fit_result.delta_pt,
        run=run,
        verdict=verdict,
        all_page_runs=all_page_runs,
        fit_result=fit_result,
        substitution_key=substitution_key,
    )


def plan_recipe(pdf_path: str | Path, recipe: tuple[RecipeOp, ...], password: str = "") -> RecipeReport:
    """Resolve every op in `recipe` against `pdf_path`, and report -- writing NOTHING.

    D-03's dry-run computation: opens its own handles, closes them before returning, and
    never calls `save()`, so the file on disk is byte-identical afterwards.

    Per op, in this order:

    * D-10 -- the op's `run_id` must decode, and its embedded `source_hash` must equal the
      SHA-256 of the bytes actually opened. A mismatched hash means a byte offset that may
      land mid-token, so it refuses with no override.
    * The run must still exist in this document's own current run map.
    * A run Phase 2 already refused passes that refusal through unmodified (EDIT-04).
    * D-05 / 03-RESEARCH.md Pattern 4 -- the edit-time substitution trigger is consulted
      independently of Phase 2's own state, because a run can be `editable_original` and
      still need the bundled substitute the moment `new_text` contains a character the
      embedded program has no glyph for.
    * D-06 -- automatic substitution whose `/BaseFont` has no mapping-table entry refuses BY
      NAME, with `MappingVerdict`'s own reason. No fallback face is guessed.
    * D-06 again, one rung lower: a substituting run whose `new_text` contains a character
      the CHOSEN bundled face has no glyph for refuses as
      `"character_has_no_glyph_in_bundled_font"`. No fallback glyph is substituted and the
      character is not dropped -- Liberation covers Latin/Greek/Cyrillic and little else,
      and the alternative is a `.notdef` box shaped into the content stream as CID 0, with
      no `/W` entry and a silent `/DW` width (FONT-04's forbidden fallback in its Type0
      form). Fires here, in the dry run, so it is disclosed before commit (D-03).
    * The fit ladder (03-03) decides whether the replacement can occupy the original run's
      width at all; a refusal there is passed through with `fit_run`'s own reason. The
      width it fits against comes from `advance_pt_for_codes`, measured over the run's own
      PDF character codes -- see the comment at that call for why neither the run's glyph
      advances nor its decoded Unicode is the right input.

    One thing narrows against summing glyph advances, and it refuses rather than guessing:
    a `/Widths` array that does not actually declare a width for a code the run uses (the
    code falls outside `FirstChar..LastChar`, or the array is shorter than the range it
    declares) resolves as `"resolution_failed"` instead of silently taking `/MissingWidth`'s
    spec default of 0. That is a genuinely malformed or under-declared font, not ordinary
    text: smart quotes and em dashes are ordinary `/WinAnsiEncoding` codes in the 0x80-0x9F
    byte range and measure normally.

    The three named checks above the substitution/fit work stay OUTSIDE the broad
    `except Exception` guard deliberately (they live here; the rest is `_resolve_op`): a
    real bug in font resolution must never masquerade as `"source_hash_mismatch"` or
    `"run_id_not_found"`, which are specific, meaningful, user-facing statements about the
    recipe rather than about this engine.

    ## A repeated `run_id` refuses the WHOLE recipe, before any resolution work

    Two ops naming the same run are not two edits -- the second overwrites the first, and
    only its text survives. Resolving them independently would report two successful edits
    where the output can only carry one, which is a lie about what was applied and exactly
    the class of confident-wrong result this engine exists to avoid. There is no sane
    merge (the ops disagree about what the run should say), so this is a malformed recipe,
    refused whole like `MAX_RECIPE_OPS`: EVERY op gets `"duplicate_run_id_in_recipe"`,
    including the non-duplicated ones, because no per-op resolution ran and claiming
    anything more specific about them would be inventing a result.
    """
    if len({op.run_id for op in recipe}) != len(recipe):
        return RecipeReport(
            ok=False,
            resolved=tuple(
                ResolvedOp(op, ok=False, reason="duplicate_run_id_in_recipe")
                for op in recipe
            ),
        )

    path = Path(pdf_path)
    actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    by_run_id: dict[str, tuple[RunRecord, RunVerdict]] = {}
    page_runs_by_page: dict[int, list[RunRecord]] = {}
    requested_pages: set[int] = set()
    for op in recipe:
        try:
            parts = decode_run_id(op.run_id)
        except ValueError:
            continue  # Preserve the per-operation named refusal below.
        if parts["source_hash"] == actual_hash:
            requested_pages.add(parts["page"])
    # Classifying unrelated pages made one edit exceed worker limits on long PDFs.
    # Keep all runs on each requested page for correlation/geometry checks, but no
    # document-wide eager pass. Addresses still resolve against immutable source bytes.
    with RunIndex(path, password=password) as index:
        for page_number in sorted(requested_pages):
            if not 0 <= page_number < index.page_count:
                continue
            for run, verdict in index.page(page_number).runs:
                by_run_id[run.run_id] = (run, verdict)
                page_runs_by_page.setdefault(run.page, []).append(run)

    resolved: list[ResolvedOp] = []
    # A SECOND, independent open of the same bytes: RunIndex opens and closes
    # its own handles internally, and threading a shared one through its signature would
    # change a Phase 2 public API for this module's convenience. Read-only, and closed in
    # the `finally` below.
    pdf = pikepdf.open(path, password=password)
    try:
        for op in recipe:
            try:
                parts = decode_run_id(op.run_id)
            except ValueError:
                resolved.append(ResolvedOp(op, ok=False, reason="malformed_run_id"))
                continue

            if parts["source_hash"] != actual_hash:
                resolved.append(ResolvedOp(op, ok=False, reason="source_hash_mismatch"))
                continue

            found = by_run_id.get(op.run_id)
            if found is None:
                resolved.append(ResolvedOp(op, ok=False, reason="run_id_not_found"))
                continue

            run, verdict = found
            resolved.append(
                _resolve_op(pdf, op, run, verdict, tuple(page_runs_by_page[run.page]))
            )
    finally:
        pdf.close()

    # A shared subset has one ToUnicode entry per CID. Even individually safe edits
    # cannot assign different source characters to the same glyph across operations.
    keys = {r.substitution_key for r in resolved if r.ok and r.substitution_key is not None}
    for key in keys:
        texts = tuple(r.op.new_text for r in resolved if r.ok and r.substitution_key == key)
        unicode_reason = substitution_unicode_reason(*key, texts)
        if unicode_reason is not None:
            resolved = [replace(r, ok=False, reason=unicode_reason)
                        if r.ok and r.substitution_key == key else r for r in resolved]

    return RecipeReport(ok=all(r.ok for r in resolved), resolved=tuple(resolved))


def _refuse_at(
    report: RecipeReport, index: int, original: ResolvedOp, reason: str | None
) -> RecipeReport:
    """`report` with op `index` replaced by its refusing form -- D-11's whole-recipe
    refusal, minted at save time. The refused op keeps `plan_recipe`'s own record (context
    the caller can act on) and gains only the reason; every other op is untouched."""
    resolved = list(report.resolved)
    resolved[index] = replace(original, ok=False, reason=reason)
    return RecipeReport(ok=False, resolved=tuple(resolved))


def _match_run(
    target: RunRecord, current: list[tuple[RunRecord, RunVerdict]]
) -> tuple[RunRecord, RunVerdict] | None:
    """`target` located again in a run map re-derived AFTER some edit, or `None` when the
    match is not unambiguous.

    Neither of the two obvious identities survives the re-derivation:

    * the `run_id` does not -- it embeds both the document's source hash (now different
      bytes) and a byte offset (now shifted by the re-serialised part);
    * an ordinal position among the part's runs does not -- the clusterer is spatial, so an
      edit that changes a neighbouring run's text can legitimately change how many runs the
      part yields.

    What DOES survive, for a run no edit touched, is what the run physically is: its part,
    the origin of its first glyph, and its decoded text. `rewrite_run`'s D-04 guard already
    refuses any edit that moves following text, so a surviving edit leaves both unchanged.
    `_POSITION_EPSILON` is `engine.rewrite`'s own value and rationale (re-derived
    floating-point positions measure a delta of exactly 0.0 in practice, so this sits many
    orders of magnitude above observed noise).

    Ambiguity -- zero matches, or more than one -- returns `None` so the caller refuses by
    name. Picking one would be a guess, and guessing which run to overwrite is precisely the
    failure this function exists to prevent.
    """
    part_key = _part_key(target)
    first = target.glyphs[0]
    matches = [
        (run, verdict)
        for run, verdict in current
        if run.glyphs
        and _part_key(run) == part_key
        and run.display_text == target.display_text
        and abs(run.glyphs[0].x - first.x) < _POSITION_EPSILON
        and abs(run.glyphs[0].y - first.y) < _POSITION_EPSILON
    ]
    return matches[0] if len(matches) == 1 else None


def _rederive_op(pdf: pikepdf.Pdf, planned: ResolvedOp) -> ResolvedOp | str:
    """`planned` re-resolved against `pdf`'s CURRENT bytes, or the named reason it cannot
    be -- see `apply_recipe`'s "Two ops on ONE part" section for why this exists.

    The page is re-classified through `engine.index.RunIndex` over a scratch save of the
    handle as it now stands, which is the same mechanism `engine.rewrite._current_page_runs`
    already uses for D-04's guard; it is called here for the FULL classification (records
    AND verdicts), which that helper discards. A run whose fresh verdict is `not_editable`,
    or whose re-resolution refuses for any other reason, comes back as that resolution's own
    named reason rather than as a fallback to the stale plan.
    """
    if planned.run is None:
        return "resolution_failed"
    page_index = planned.run.page
    try:
        with tempfile.TemporaryDirectory() as scratch:
            scratch_path = Path(scratch) / "rederive.pdf"
            pdf.save(scratch_path)
            with RunIndex(scratch_path) as index:
                current = list(index.page(page_index).runs)
    except Exception:  # noqa: BLE001 - classify-never-crash, a named refusal instead
        return "resolution_failed"

    found = _match_run(planned.run, current)
    if found is None:
        return "run_lost_after_earlier_edit"

    run, verdict = found
    redone = _resolve_op(
        pdf, planned.op, run, verdict, tuple(r for r, _v in current if r.page == page_index)
    )
    if not redone.ok:
        return redone.reason or "resolution_failed"
    if redone.substitution_key != planned.substitution_key:
        # The document-wide glyph union (D-13) was already built and embedded from the
        # PLANNED keys. Honouring a changed one would point the replacement at a subset that
        # was never asked to cover its glyphs.
        return "substitution_key_changed_after_earlier_edit"
    return redone


def apply_recipe(
    pdf_path: str | Path, recipe: tuple[RecipeOp, ...], output_path: str | Path, password: str = ""
) -> RecipeReport:
    """D-11 + D-13: resolve the whole recipe, subset once per family, rewrite every op, and
    write `output_path` ONLY if all of that succeeded.

    ## D-11, all-or-nothing, in three ordered gates

    1. `plan_recipe` runs first and its report is the gate: if ANY op refused, this returns
       that exact report and nothing is opened for writing, so no output file exists at all.
    2. Font subsetting runs next, over the now-known complete edit set (that ordering IS
       D-13's stated dependency on D-11).
    3. Every `rewrite_run` runs in recipe order, and the FIRST failure returns without
       saving. `engine/rewrite.py`'s module docstring is explicit that a
       `RewriteOutcome(ok=False)` does **not** undo the mutation already applied for that
       attempt -- its D-04 guard cannot run before the splice, because the thing it measures
       is where the following glyph lands once the new bytes are in place. So the only
       correct response is to discard the whole `pikepdf.Pdf` handle unsaved, which the
       `finally` below does: no `save()` is ever reached on a partially-mutated document.
       No `--partial` mode (D-11: deliberately not added).

    On success the report returned is `plan_recipe`'s own object, unchanged and unrebuilt,
    so a dry run and a commit of the same recipe are the same report by construction.

    ## D-13, one subset per bundled family per document

    Glyph names are unioned across every substituting op FIRST, keyed by
    `(family, variant)`, and `subset_font_for_family` / `subset_cid_widths` /
    `shape_cids` / `embed_type0_font` then run exactly ONCE per distinct key -- never once
    per op -- in 03-05's own construction order. `/ToUnicode` is likewise built over the
    union of every op sharing that key, so one font object serves them all and FONT-05 has
    one fresh subset tag per family to keep distinct rather than one per edited run.

    ## Two ops on ONE part: the later one is RE-DERIVED, never applied from stale records

    `rewrite_instructions`' CALLER INVARIANT asks for run records describing the part's
    CURRENT bytes. `plan_recipe`'s records describe its bytes before any op ran, and
    `rewrite_instructions` re-serialises the WHOLE part it edits, so a single edit
    invalidates every byte offset in that part -- including offsets BEFORE the edit point,
    since `unparse_content_stream` re-emits the entire instruction list.

    An earlier version of this docstring claimed `_correlate`'s `"stale_run_index"` check
    contained that hazard. **It does not, and this is a corrected claim, not a restated
    one.** That check compares ORDINAL counts of text-showing operators, which routinely
    coincide before and after an edit (a replacement emits one showing operator just as the
    original did). Everything `rewrite_run` resolves by RAW BYTE OFFSET is left uncovered --
    above all the backward scan for the nearest preceding `Tf`, which decides the run's font
    and therefore its ENCODING. Both halves of that were reproduced against real code on a
    two-run part: op 2's `Tf`-restore emitted op 1's freshly-embedded Identity-H CID font
    instead of its own resource (leaving a CID font in force past `ET`, the exact D-02
    hazard the restore bracket exists to prevent), and, with a `/Differences` encoding on
    the second font, op 2's replacement was encoded through op 1's font's `/Encoding` --
    writing `(AB)` where that run's own font renders those codes as "BA". Both returned
    `ok=True`. This is not an exotic recipe shape: "replace this phrase everywhere" hits one
    page, and one part, repeatedly.

    So: `_part_key` identifies the ONE part each op edits, and once an op has mutated a
    part, any LATER op targeting that same part is re-derived before it is applied --
    the page is re-classified from the handle's CURRENT bytes (`_current_page_runs`, the
    same scratch-save + `RunIndex` re-walk `rewrite_run`'s own D-04 guard already performs),
    the op's run is re-located in that fresh map by `_match_run`, and `_resolve_op` runs
    again against the mutated document. Bounded cost: one re-walk per edit that is actually
    followed by another op on the same part, not one per op.

    Re-derivation refuses by NAME rather than falling back to the stale records:
    `"run_lost_after_earlier_edit"` when the fresh map has no unambiguous match, and
    `"substitution_key_changed_after_earlier_edit"` when it does but the re-resolved
    bundled face is not the one this save already subset for (the glyph union was built
    from the planned keys, so honouring a changed one would reference glyphs no embedded
    subset contains). D-11 still applies to both: nothing is written.
    """
    report = plan_recipe(pdf_path, recipe, password=password)
    if not report.ok:
        return report

    glyph_names_by_key: defaultdict[tuple[BundledFamily, BundledVariant], set[str]] = (
        defaultdict(set)
    )
    for r in report.resolved:
        if r.substitution_key is not None:
            glyph_names_by_key[r.substitution_key].update(
                shape_glyph_names(*r.substitution_key, r.op.new_text)
            )

    pdf = pikepdf.open(pdf_path, password=password)
    try:
        font_map: dict[
            tuple[BundledFamily, BundledVariant], tuple[SubsetFont, pikepdf.Object]
        ] = {}
        for key, names in glyph_names_by_key.items():
            matching = [(i, r) for i, r in enumerate(report.resolved) if r.substitution_key == key]
            unicode_reason = substitution_unicode_reason(*key, tuple(r.op.new_text for _, r in matching))
            if unicode_reason is not None:
                i, refused = matching[0]
                return _refuse_at(report, i, refused, unicode_reason)
            subset = subset_font_for_family(key[0], key[1], frozenset(names))
            cid_widths = subset_cid_widths(subset)
            cid_to_unicode: dict[int, str] = {}
            for r in report.resolved:
                if r.substitution_key == key:
                    cid_to_unicode.update(dict(shape_cids(subset, r.op.new_text)))
            font_map[key] = (subset, embed_type0_font(pdf, subset, cid_widths, cid_to_unicode))

        # Parts this call has already mutated, and therefore whose byte offsets every
        # not-yet-applied op's records are now stale against.
        edited_parts: set[tuple[int, int, tuple[int, ...]]] = set()
        for index, r in enumerate(report.resolved):
            if (
                r.run is None
                or r.verdict is None
                or r.all_page_runs is None
                or r.fit_result is None
            ):
                # Structurally unreachable for an `ok=True` op -- `plan_recipe` sets all
                # four together on its success path. Written as a named refusal rather than
                # an `assert` for the same reason `plan_recipe`'s own D-06 branch is: an
                # assert is control flow `python -O` strips, and the alternative here would
                # be an `AttributeError` escaping as an unnamed crash (EDIT-04).
                return _refuse_at(report, index, r, "resolution_failed")

            applied = r
            if _part_key(r.run) in edited_parts:
                redone = _rederive_op(pdf, r)
                if isinstance(redone, str):
                    return _refuse_at(report, index, r, redone)
                applied = redone

            substitution_target = (
                font_map.get(applied.substitution_key)
                if applied.substitution_key
                else None
            )
            if (
                applied.run is None
                or applied.verdict is None
                or applied.all_page_runs is None
                or applied.fit_result is None
            ):
                return _refuse_at(report, index, r, "resolution_failed")

            outcome = rewrite_run(
                pdf,
                applied.run.page,
                applied.run,
                applied.verdict,
                list(applied.all_page_runs),
                applied.op.new_text,
                applied.fit_result,
                substitution_target=substitution_target,
                color=tuple(applied.op.style["color"]) if applied.op.style is not None and "color" in applied.op.style else None,
                force_substitution=applied.substitution_key is not None,
            )
            if not outcome.ok:
                # Return WITHOUT saving; the `finally` closes the mutated handle and it is
                # discarded. See this function's docstring and `engine/rewrite.py`'s own
                # "Refusal does NOT roll back (D-11)" section.
                return _refuse_at(report, index, r, outcome.reason)
            edited_parts.add(_part_key(applied.run))

        pdf.save(Path(output_path))
    finally:
        pdf.close()

    return report


__all__ = [
    "RecipeOp",
    "RecipeStyle",
    "active_font_name_and_size",
    "MAX_RECIPE_OPS",
    "MAX_NEW_TEXT_CHARS",
    "RecipeReport",
    "RecipeTooLargeError",
    "ResolvedOp",
    "apply_recipe",
    "parse_recipe",
    "plan_recipe",
]
