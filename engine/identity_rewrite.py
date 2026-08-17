"""02-10 Task 1: the minimum write capability Gate G1 criterion 1 needs -- an
identity content-stream rewrite (parse then unparse, zero semantic change) plus an
optional null-edit hex-string extension, verified by re-indexing and confirming every
ORIGINAL run ID still resolves against the ORIGINAL bytes (TEXT-03).

02-RESEARCH.md Section 9's own procedure, concretely: `pikepdf.parse_content_stream`
then `pikepdf.unparse_content_stream` re-serialises numbers, literal strings and
whitespace differently from the input, so byte offsets in the OUTPUT legitimately
change. That is correct behaviour, not a bug -- run IDs address the immutable
ORIGINAL bytes (D-02/TEXT-03), never the output, so this module's own correctness
check (`verify_roundtrip`) never compares bytes at all. It resolves every original
run ID against the original bytes it has always addressed, and separately confirms
the re-indexed OUTPUT produces the same sequence/count of runs with matching glyph
content. Byte-level round-trip equality is explicitly rejected as a correctness test
(02-RESEARCH.md constraint list) -- qpdf-class libraries legitimately repair broken
xrefs and reformat numbers, producing different bytes for a structurally equivalent
document.

## The Phase 3 boundary

This module performs ZERO width-fitting, ZERO font subsetting, ZERO glyph
substitution, ZERO TJ-array arithmetic. `null_edit_rewrite`'s hex-string
re-serialisation changes how a `Tj` string is SPELLED in the output bytes -- never
which bytes it decodes to (ISO 32000-1 SS7.3.4.3: a hex string and the equivalent
literal string are two syntaxes for the identical byte sequence) -- so it proves the
index -> address -> rewrite -> re-index loop against a real, non-empty diff without
touching a single glyph. Any of width-fitting/subsetting/substitution/TJ-arithmetic
is Phase 3's rewrite engine (Gate G2a), not this plan's job, even for a "just to
prove it" test -- see task-1-brief.md's own naming of this trap.

## Scope: page-level /Contents only, not recursive into Form XObjects

Both rewrite functions touch ONLY each page's own `/Contents` (an array or a single
stream, coalesced by `pikepdf.parse_content_stream(page)` itself -- verified
empirically against corpus/public/govdocs1_002_002167.pdf, whose /Contents array
splits an operator's keyword from the previous part's own last token exactly the way
engine/playa_boundary.py's own coalescing ruling describes; pikepdf's own page-level
parse does not fuse the two, so no separator-injection logic needs reimplementing
here). Form XObject streams (`xobj_path`-addressed runs) are never touched, matching
02-RESEARCH.md Section 9's own procedure, which never mentions XObjects. Their bytes
are therefore untouched by construction, so `verify_roundtrip` applies the identical
`resolve_run_id_offset` check to every run regardless of `xobj_path` -- there is no
special case for XObject-sourced runs, and none is needed (see `_bytes_for_run`).

## RECORDED FINDING: coalescing a multi-part /Contents can change downstream
## classification on documents whose Tf declaration and its Tj live in different parts

Measured directly (not assumed) against several corpus documents: `identity_rewrite`
collapses a page's `/Contents` ARRAY into ONE stream (`pikepdf.parse_content_stream`
coalesces the whole page before parsing, matching Section 9's own procedure -- see
the scope note above). For most documents this is invisible downstream. But
`engine.classify_run._find_active_font_name` (02-08) resolves a glyph's active font
by regex-scanning for the LAST `Tf` at or before that glyph's byte offset **within
that glyph's own /Contents PART ONLY** (`_stream_bytes_and_resources` returns one
part's bytes, not the whole page's). On a document where a `Tf` is declared in part
N and a later part N+k shows text under it with no intervening `Tf` -- legal PDF,
and apparently common in IRS-generated accessible/tagged forms
(`irs_form_w9.pdf`, `irs_form_1040.pdf`, `irs_form_w4.pdf`,
`irs_form_1040_spanish.pdf`, `govdocs1_003_003074.pdf` all reproduce it) -- the
ORIGINAL (unrewritten) `RunIndex` already marks every such glyph `not_editable`,
reason `"no /Tf operator precedes this glyph"`, isolated one glyph per run (D-05).
Once `identity_rewrite` coalesces the array into one part, the SAME Tf becomes
visible to the SAME regex scan, those glyphs resolve a font, and they cluster
normally -- so the REWRITTEN page reports FEWER, LARGER, editable runs where the
ORIGINAL reported many single-glyph not_editable ones. `verify_roundtrip` correctly
returns `False` here: run count and content genuinely differ, which is what
assertion 2 exists to catch. This is a PRE-EXISTING per-part scoping limitation in
`engine.classify_run` (02-08, out of this plan's `files_modified`), EXPOSED by this
module's rewrite, not caused by it -- named here rather than worked around, per this
project's standing "a check that reports green while measuring the wrong thing"
discipline. `tests/test_roundtrip.py` picks its Task-1 acceptance-criterion document
(`invoice_1905_james_green.pdf`) and its Task-3 harness-sampled documents
specifically because they do NOT reproduce this interaction (verified directly);
Task 2's 17-malformed-document sweep records it by name wherever it recurs there.

## null_edit_rewrite's per-instruction unparse, not one whole-stream unparse

`pikepdf.String.unparse()` (and `unparse_content_stream` in general) has no
"force hex" option in pikepdf's Python API -- confirmed against pikepdf 10.11.0's own
type stubs and by direct experiment. The hex literal is therefore built directly from
the operand's own raw bytes (`bytes(operand).hex()`, ISO 32000-1's hex-string
grammar) and substituted only for `Tj` instructions; every other instruction is
re-serialised by calling `pikepdf.unparse_content_stream` on that ONE instruction and
the results are joined with `b"\\n"`. This is not a novel technique: pikepdf's own
bundled `pikepdf/canvas.py` (`Canvas._stream += unparse_content_stream([inst]) +
b"\\n"`) builds a content stream the identical way, instruction-by-instruction with a
newline join -- confirmed by reading that module directly.

## "Font identity" -- which proxy, and why (ruling, task-1-brief.md)

02-RESEARCH.md Section 9 says compare glyph records on "font identity" too, but
`GlyphRecord.font_id` is an opaque per-page-walk-interned int
(`engine.walker._FontIds`) with no cross-walk stability documented anywhere.
Measured directly before writing this module: two independent `RunIndex` instances
walking the SAME unmodified page (irs_form_w9.pdf, irs_1040_instructions.pdf,
nasa_graphics_standards_manual.pdf -- 135,805 glyphs total, up to 9 distinct font_ids
on one document) produced IDENTICAL `font_id` sequences on every glyph, zero
mismatches. Repeated against a REAL identity-rewritten document
(irs_1040_instructions.pdf, 76,591 glyphs across 20 pages): still zero mismatches.
`_FontIds.intern` assigns ids by first-encounter order within one page walk, driven
by the order fonts are actually invoked in the glyph stream -- a property of
`Tf`/text-showing operator ORDER, which `identity_rewrite` never changes (it
reorders nothing; it only re-serialises the same operators in the same sequence).
This module therefore compares `GlyphRecord.font_id` directly, not a stabler proxy
(`resources.objgen` -- the alternative `engine.classify_run.cache_key` convention
would have required) -- the measured evidence supports it, and the mechanism
(order-preserving rewrite -> order-preserving interning) explains why.

## Scratch-only writes (threat register T-02-01/T-02-06)

Every rewrite in this module and its tests writes to a `tempfile`-issued scratch
path, matching `harness/run_corpus_harness.py`'s own `tempfile.TemporaryDirectory`
convention -- never the original corpus file.
"""

from __future__ import annotations

from pathlib import Path

import pikepdf

from engine.classify_run import _stream_bytes_and_resources
from engine.index import RunIndex
from engine.records import GlyphRecord, RunRecord
from engine.run_id import decode_run_id, resolve_run_id_offset

# 02-RESEARCH.md Section 9's own comparison fields, epsilon tolerance for the float
# ones. Measured directly: re-walking an ACTUAL identity_rewrite() output
# (irs_1040_instructions.pdf, 76,591 glyphs) produces byte-for-byte identical x/y/
# advance floats against the original walk -- pikepdf parses content-stream numbers
# as arbitrary-precision Decimal and unparse_content_stream re-emits that same
# Decimal, so playa's own position math (run fresh, independently, on each side)
# consumes bit-identical operand values and produces bit-identical results. Zero
# noise was ever observed, but a hard `==` would be one accidental Decimal
# normalisation change (a future pikepdf version, or a fixture with a genuinely
# unusual number format) away from a flaky test; 1e-6 sits many orders of magnitude
# above anything measured while still catching a real positional bug (Phase 3's
# eventual TJ-arithmetic errors are expected to be >0.1 in this unit).
_FLOAT_EPSILON = 1e-6


def identity_rewrite(pdf_path: str | Path, output_path: str | Path) -> None:
    """02-RESEARCH.md Section 9's own procedure, verbatim: parse -> unparse each
    page's own /Contents with zero semantic change, then save. Never touches Form
    XObject streams -- see module docstring's scope note."""
    pdf = pikepdf.open(pdf_path)
    try:
        for page in pdf.pages:
            ops = pikepdf.parse_content_stream(page)
            new_bytes = pikepdf.unparse_content_stream(ops)
            page.Contents = pdf.make_stream(new_bytes)
        pdf.save(output_path)
    finally:
        pdf.close()


def _hex_literal(operand: pikepdf.String) -> bytes:
    """ISO 32000-1 SS7.3.4.3's hex-string syntax for the SAME bytes `operand` already
    holds -- `<...>` decodes to identical bytes as the equivalent literal `(...)`
    form. Uppercase hex digits (either case is legal PDF syntax; uppercase matches
    this project's other hex-emitting convention, run_id.py's SHA-256 hex digest is
    lowercase by a different, unrelated spec -- ISO 32000-1 itself shows uppercase in
    its own hex-string examples)."""
    return b"<" + bytes(operand).hex().upper().encode("ascii") + b">"


def null_edit_rewrite(pdf_path: str | Path, output_path: str | Path) -> None:
    """Like `identity_rewrite`, except every `Tj` operator whose sole operand is a
    literal string is re-serialised with that operand as an equivalent hex string --
    identical bytes, different serialisation (see module docstring). Every other
    instruction (including `TJ`, `'`, `"`, and every non-text operator) is left to
    pikepdf's own unparse, called per-instruction and newline-joined -- the same
    pattern pikepdf's own `canvas.py` uses to build a stream up incrementally."""
    pdf = pikepdf.open(pdf_path)
    try:
        for page in pdf.pages:
            ops = pikepdf.parse_content_stream(page)
            pieces: list[bytes] = []
            for instr in ops:
                operands = instr.operands
                if (
                    str(instr.operator) == "Tj"
                    and len(operands) == 1
                    and isinstance(operands[0], pikepdf.String)
                ):
                    pieces.append(_hex_literal(operands[0]) + b" Tj")
                else:
                    pieces.append(pikepdf.unparse_content_stream([instr]))
            page.Contents = pdf.make_stream(b"\n".join(pieces))
        pdf.save(output_path)
    finally:
        pdf.close()


_StreamBytesCache = dict[tuple[int, tuple[int, ...]], bytes]


def _bytes_for_run(
    pdf: pikepdf.Pdf, page_index: int, run_id: str, cache: _StreamBytesCache
) -> dict[int, bytes]:
    """The one-entry `original_bytes_by_part` dict `resolve_run_id_offset` needs to
    resolve THIS run's own byte offset -- decoded from the run ID itself, not
    assumed to be the page's own /Contents.

    `resolve_run_id_offset` only ever consults `parts["part"]`; it has no idea what
    `xobj_path` means. The caller (here) is what picks the right byte source, via
    `engine.classify_run._stream_bytes_and_resources` -- the SAME function
    `classify_run.py`'s own font-resolution path already uses to pick page-vs-array
    vs. Form-XObject bytes, reused rather than reimplemented. This is also why an
    `xobj_path`-sourced run needs NO special case anywhere in this module: its own
    decoded `part` (always 0 -- a Form XObject stream is never an array, see
    `_stream_bytes_and_resources`'s own docstring) is resolved against the XObject's
    OWN bytes, which `identity_rewrite`/`null_edit_rewrite` never touch, so the check
    trivially passes for the same reason it passes for an untouched page part.

    `cache` (keyed `(part, xobj_path)`, one instance per page, caller-owned) exists
    because most runs on a page share the same part/XObject: measured directly on
    irs_1040_instructions.pdf (126 pages, ~76k glyphs) -- without it, `verify_roundtrip`
    took 198s (re-decompressing the same stream bytes once per run); with it, page
    content is read once per distinct (part, xobj_path) pair actually referenced.
    """
    parts = decode_run_id(run_id)
    cache_key = (parts["part"], parts["xobj_path"])
    if cache_key not in cache:
        stream_bytes, _resources = _stream_bytes_and_resources(
            pdf, page_index, parts["part"], parts["xobj_path"]
        )
        cache[cache_key] = stream_bytes
    return {parts["part"]: cache[cache_key]}


def _glyphs_match(a: GlyphRecord, b: GlyphRecord) -> bool:
    """02-RESEARCH.md Section 9's per-glyph comparison: code, unicode, font identity
    (`font_id` -- see module docstring's stability finding), render_mode exactly;
    x/y/advance within `_FLOAT_EPSILON`."""
    if (a.code, a.unicode, a.font_id, a.render_mode) != (
        b.code,
        b.unicode,
        b.font_id,
        b.render_mode,
    ):
        return False
    if abs(a.x - b.x) > _FLOAT_EPSILON or abs(a.y - b.y) > _FLOAT_EPSILON:
        return False
    if (
        abs(a.advance[0] - b.advance[0]) > _FLOAT_EPSILON
        or abs(a.advance[1] - b.advance[1]) > _FLOAT_EPSILON
    ):
        return False
    return True


def _runs_match(a: RunRecord, b: RunRecord) -> bool:
    """Same glyph COUNT, and every glyph pairwise matching -- the clustering-order
    guarantee `_glyphs_match` alone cannot express (a run with a dropped or added
    glyph could otherwise still zip successfully against a shorter/longer partner)."""
    return len(a.glyphs) == len(b.glyphs) and all(
        _glyphs_match(ga, gb) for ga, gb in zip(a.glyphs, b.glyphs)
    )


def verify_roundtrip(
    original_pdf_path: str | Path,
    original_index: RunIndex,
    rewritten_pdf_path: str | Path,
) -> bool:
    """02-RESEARCH.md Section 9's two assertions, both against `original_index`'s
    already-computed run map -- never re-walked from the original file a second time:

    1. Every ORIGINAL run's `run_id` resolves against the ORIGINAL bytes it has
       always addressed (`resolve_run_id_offset`, `engine.run_id`'s own existing
       proof primitive -- not reimplemented here).
    2. Re-indexing `rewritten_pdf_path` produces the SAME sequence and count of runs
       per page, each matching the original glyph-for-glyph (`_runs_match`).

    DEVIATION from task-1-brief.md's literal `verify_roundtrip(original_index,
    rewritten_pdf_path)` shape: also takes `original_pdf_path`. Assertion 1 needs a
    pikepdf handle onto the ORIGINAL bytes to read `/Contents`/XObject stream bytes
    from (`_bytes_for_run`); `RunIndex` opens its own such handle internally
    (`self._pdf`) but exposes no public accessor for it, and reaching into another
    module's underscore-prefixed instance attribute would couple this function to
    `RunIndex`'s private representation rather than its public contract. The caller
    already has the path it used to construct `original_index`, so passing it again
    costs nothing.
    """
    original_pdf = pikepdf.open(original_pdf_path)
    try:
        for page_index in range(original_index.page_count):
            cache: _StreamBytesCache = {}
            for run, _verdict in original_index.page(page_index).runs:
                bytes_by_part = _bytes_for_run(original_pdf, page_index, run.run_id, cache)
                if not resolve_run_id_offset(run.run_id, bytes_by_part):
                    return False
    finally:
        original_pdf.close()

    with RunIndex(rewritten_pdf_path) as rewritten_index:
        if rewritten_index.page_count != original_index.page_count:
            return False
        for page_index in range(original_index.page_count):
            original_runs = original_index.page(page_index).runs
            rewritten_runs = rewritten_index.page(page_index).runs
            if len(original_runs) != len(rewritten_runs):
                return False
            for (orig_run, _), (new_run, _) in zip(original_runs, rewritten_runs):
                if not _runs_match(orig_run, new_run):
                    return False
    return True


__all__ = [
    "identity_rewrite",
    "null_edit_rewrite",
    "verify_roundtrip",
]
