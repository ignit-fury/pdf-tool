# Phase 3: Rewrite Engine + Font Pipeline - Pattern Map

**Mapped:** 2026-08-18
**Files analyzed:** 15 (4 new engine modules, 1 CLI modify, 2 config modifies, 1 new asset directory, 7 new test files)
**Analogs found:** 15 / 15 files have a role/data-flow analog; 3 sub-pieces within those files have no
in-repo precedent at all (flagged individually in Pattern Assignments and summarized in `## No Analog Found`)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `engine/fit.py` | service (pure computation) | transform | `spike/tj_refit_prototype.py` | exact (direct port target) |
| `engine/fonts.py` | service (classify + build + embed) | transform, file-I/O | `engine/encoding_table.py` | role-match (read/classify side); no analog for the write/embed side |
| `engine/rewrite.py` | service (content-stream surgery) | transform, file-I/O | `engine/identity_rewrite.py` | exact (its own docstring names itself the predecessor) |
| `engine/recipe.py` | controller/service (orchestration) | batch, request-response | `engine/run_id.py` + `engine/classify_run.py` + `engine/index.py` | role-match (composite of three) |
| `tools/pdftool.py` (modify) | route/CLI controller | request-response | itself (existing `index` subcommand) | exact (self-analog, extend in place) |
| `pyproject.toml` (modify) | config | — | itself (existing fontTools mypy override) | exact (self-analog, copy-paste block) |
| `Dockerfile.ci` (modify) | config | — | itself (existing pinned apt-get pattern) | exact (self-analog, copy-paste block) |
| `fonts/` (new directory) | config/asset | file-I/O (static) | `spike/fixtures/LiberationSans-Regular.ttf` + its OFL license file | exact (same font family, already partially bundled) |
| `tests/test_fit.py` | test | transform | `tests/test_tj_refit_prototype.py` | exact (explicit port target, named in Wave 0 Gaps) |
| `tests/test_fonts.py` | test | transform, file-I/O | `tests/test_encoding_table.py` | role-match |
| `tests/test_rewrite.py` | test | transform, file-I/O | `tests/test_roundtrip.py` | exact (direct successor test file) |
| `tests/test_recipe.py` | test | batch, request-response | `tests/test_run_id.py` + `tests/test_classify.py` | role-match |
| `tests/test_pdftool_edit.py` | test (CLI integration) | request-response | `tests/test_check_corpus_size.py` | exact (only existing CLI-integration test in the repo) |
| `tests/test_gate_g2a.py` | test (integration/gate) | transform | `tests/test_roundtrip.py` (Task 2 corpus-sweep shape) | partial — the confined-diff mechanism itself has no analog |
| `tests/test_gate_g2b.py` | test (integration/gate) | batch | `tests/test_roundtrip.py` (Task 3 harness-reuse shape) | role-match/exact for the harness-call portion |

## Pattern Assignments

### `engine/fit.py` (service, transform)

**Analog:** `spike/tj_refit_prototype.py` (214 lines — this IS the algorithm to absorb/rewrite, per
CONTEXT.md's Claude's Discretion item; carried-forward, not thrown away)

**Imports pattern** (lines 46-52):
```python
from __future__ import annotations

import dataclasses
from pathlib import Path

import pikepdf
import uharfbuzz as hb
```
`engine/fit.py` needs this unchanged, plus `from engine.encoding_table import cid_width` for D-14's
`/W`-based reading of substituted-font advances (Type0 case — see below).

**Core pattern — the ladder itself** (lines 144-191, `fit_run`):
```python
    # Priority 1: a single trailing TJ kern absorbs everything within ~1 space width.
    if abs(delta) <= space_w:
        kern = delta / font_size_pt * 1000.0
        kerns = [kern]
        final_advance = total_advance_with_kerns(shaped, kerns, font_size_pt)
        return FitResult(
            original_advance_pt, shaped, final_advance - original_advance_pt,
            "trailing_kern", kerns,
        )

    # Priority 2: distribute across inter-word kerns already present in the run.
    gap_count = replacement_text.count(" ")
    max_inter_word_absorb = gap_count * space_w * _INTER_WORD_ABSORB_MULTIPLIER
    if gap_count > 0 and abs(delta) <= max_inter_word_absorb:
        ...
    # Priority 3+ (Tz scale, refuse-if-content-follows) are out of scope for this prototype
    reason = (...)
    return FitResult(original_advance_pt, shaped, delta, "refused", [], refused=True, refusal_reason=reason)
```
This is exactly D-01's ladder minus the `Tz` rung, which the spike's own docstring (lines 22-25)
explicitly scoped out. `engine/fit.py`'s job is to add the `Tz` rung between inter-word and refuse.

**REQUIRED DEVIATION — house dataclass convention.** The spike's `FitResult` (lines 59-66) is a
plain `@dataclasses.dataclass`, NOT frozen/slots:
```python
@dataclasses.dataclass
class FitResult:
    original_advance_pt: float
    replacement_shaped_advance_pt: float
    delta_pt: float
    strategy: str
    kerns: list[float]
    refused: bool = False
    refusal_reason: str | None = None
```
Every other record/verdict type in `engine/` is `@dataclass(frozen=True, slots=True)`
(`engine/records.py`'s `GlyphRecord`, `engine/encoding_table.py`'s `FontVerdict`/`GlyphVerdict`,
`engine/classify_run.py`'s `RunVerdict`) specifically so a construction call missing a field raises
`TypeError` before a half-built record exists. When porting `FitResult` into `engine/fit.py`, add
`frozen=True, slots=True` — this is a real deviation from the spike, not a copy-paste.

**Sign convention** (lines 91-93) — load-bearing, port verbatim:
```python
def kern_to_displacement_pt(kern: float, font_size_pt: float) -> float:
    """TJ sign convention: the kern number is SUBTRACTED, in thousandths of text space."""
    return -(kern / 1000.0) * font_size_pt
```

**Measured-basis constant convention** (line 56):
```python
_INTER_WORD_ABSORB_MULTIPLIER = 2.0
```
comment above it cites "roughly one space width" from the priority-ordered absorption strategy. The
new `Tz` floor constant must carry the same style — a named constant with its measured/reasoned
basis in a comment beside it, e.g. `TZ_FLOOR_PERCENT = 90  # RESEARCH.md Pattern 3: wide end of the
90-95% band, maximizes usable range`. Do not hardcode `90` inline.

**Original-width reading pattern** (lines 104-141, `read_original_advance_pt`) — /Widths via
pikepdf, never fontTools; explicit `FirstChar..LastChar` bounds check that raises `ValueError`
rather than falling through to `/MissingWidth`:
```python
        first_char = int(font["/FirstChar"])
        last_char = int(font["/LastChar"])
        widths = font["/Widths"]
        total_thousandths = 0.0
        for ch in text:
            code = ord(ch)
            if not (first_char <= code <= last_char):
                raise ValueError(
                    f"code {code!r} ({ch!r}) outside FirstChar..LastChar "
                    f"({first_char}..{last_char}) -- refusing to fall through to "
                    "/MissingWidth (spec default 0), see Pitfall 5"
                )
```
D-14 extends this: for the Type0/CIDFontType2 substitution case, bind on `/W` instead, reusing
`engine/encoding_table.py::cid_width` (lines 551-583) directly rather than reimplementing — that
function already handles `/W`'s run-length format and the `/DW` default correctly, including
malformed-array defensiveness.

**Tz emission syntax** — no analog inside `engine/fit.py`'s scope, but the exact pikepdf
construction syntax needed is already used in `tests/test_roundtrip.py` (lines 143-146):
```python
new_ops.append(
    pikepdf.ContentStreamInstruction(
        [pikepdf.String(b"MUTATED TEXT")], instr.operator
    )
)
```
For a `Tz` instruction: `pikepdf.ContentStreamInstruction([pikepdf.Real(scale)],
pikepdf.Operator("Tz"))` — same constructor shape, numeric operand instead of a string one. This
belongs in `engine/rewrite.py` (the module that actually emits it), but `engine/fit.py`'s
`FitResult` must carry enough (`condensed_scale`, `original_scale_to_restore`) for `rewrite.py` to
build it — see RESEARCH.md Pattern 3's full pseudocode for the save/restore pair.

---

### `engine/fonts.py` (service, transform + file-I/O)

**Analog:** `engine/encoding_table.py` (779 lines — role-match for the classify/parse side; no
in-repo analog for the write/embed side, see `## No Analog Found`)

**Imports pattern** (lines 47-63):
```python
from __future__ import annotations

import io
import re
import struct
from dataclasses import dataclass

import pikepdf
from fontTools.agl import UV2AGL
from fontTools.cffLib import CFFFontSet
from fontTools.encodings.MacRoman import MacRoman
from fontTools.encodings.StandardEncoding import StandardEncoding
from fontTools.misc import psLib
from fontTools.ttLib import TTFont
from fontTools.ttLib.sfnt import SFNTReader

from engine.records import GlyphRecord
```
`engine/fonts.py` additionally needs `from fontTools import subset` and `import uharfbuzz as hb` —
the latter requires the new `[[tool.mypy.overrides]]` block landing in `pyproject.toml` FIRST (see
that file's own Pattern Assignment below; Pitfall 6 is explicit that this must happen before any
`engine/` module imports uharfbuzz, and `fonts.py` and `fit.py` are both first-time importers).

**Verdict dataclass shape** (lines 125-137, `FontVerdict`):
```python
@dataclass(frozen=True, slots=True)
class FontVerdict:
    """The logged outcome of one font's resolution.

    `editable=False` with `substitution=False` is a refusal and `reason` names it.
    `editable=True, substitution=True` is A-6's downgrade shape...
    """
    branch_id: str
    editable: bool
    substitution: bool
    reason: str | None = None
```
FONT-01's mapping-table lookup result and FONT-06's edit-time glyph-availability check (Pattern 4)
should mirror this frozen/slots + named-`reason` shape. Per Pattern 4 in RESEARCH.md, this is a
genuinely NEW edit-time check distinct from `FontVerdict.substitution` — do not read
`RunVerdict.state == "editable_substitution"` as the trigger; it only catches non-embedded fonts,
not the "embedded font missing one new glyph" majority case.

**Never-crash classify pattern** (lines 191-193, inside `embedded_font_bytes`):
```python
            try:
                data = bytes(stream.read_bytes())
            except Exception:  # noqa: BLE001 - an unreadable stream is "not usable", not a crash
                return None
```
This exact try/except-and-classify shape (never a bare `except: pass`, always a `# noqa: BLE001`
comment naming *why* the broad catch is intentional) recurs at lines 364-366, 420-423, 442-443, and
726-727 of the same file. RESEARCH.md's own Known Threat Patterns table names this explicitly:
"Extend identically to any new font-program touchpoint this phase adds — do not assume the
*original* document's fonts are well-formed just because the *bundled* fonts are." Every new
font-program read `fonts.py` adds (parsing an original document's embedded font to check glyph
presence, subsetting the bundled Liberation files) must use this pattern.

**Static table, exact-match only, never a heuristic** (lines 68-89):
```python
STANDARD_14 = frozenset(
    {
        "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
        "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
        "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
        "Symbol", "ZapfDingbats",
    }
)

SIMPLE_SUBTYPES = frozenset({"/Type1", "/MMType1", "/TrueType"})
```
Direct template for D-06/FONT-01's mapping table: a flat, finite `dict[str, tuple[family, weight,
style]]` of exact-or-normalized BaseFont spellings, never a substring/regex heuristic. RESEARCH.md
Pitfall 10 gives the corpus-measured starting entries (12 Base-14 non-symbol names plus common
Arial/Times New Roman MS-core-font variants).

**Branch-id-always-logged convention** (lines 586-608, `resolve_font`'s own docstring: "Top-to-
bottom, first match wins, branch ID always logged"). `fonts.py`'s own D-05/D-06 checks should log an
equally specific, named branch/reason — never a generic failure — matching EDIT-04's requirement.

**`/W` array read-side, to match on the way out** (lines 551-583, `cid_width`) — FONT-04's `/W`
construction must produce exactly the shape this existing reader already expects (confirmed
independently by RESEARCH.md's Code Examples section, which cross-checks the WeasyPrint-sourced
`/W`-builder against this function's own `isinstance(nxt, pikepdf.Array)` branch). No reader changes
needed; write to match, don't touch the read side.

---

### `engine/rewrite.py` (service, content-stream surgery)

**Analog:** `engine/identity_rewrite.py` (315 lines — its own module docstring literally names
itself Phase 3's predecessor: "ZERO width-fitting, ZERO font subsetting, ZERO glyph substitution,
ZERO TJ-array arithmetic... Phase 3 is the phase that crosses it")

**Imports pattern** (lines 116-125):
```python
from __future__ import annotations

from pathlib import Path

import pikepdf

from engine.classify_run import _stream_bytes_and_resources
from engine.index import RunIndex
from engine.records import GlyphRecord, RunRecord
from engine.run_id import decode_run_id, resolve_run_id_offset
```
`engine/rewrite.py` needs the same base, plus `engine.fit`, `engine.fonts`, and whatever result type
`engine.recipe` defines for a resolved op.

**Core reusable pattern — per-instruction unparse, newline-joined** (lines 167-192,
`null_edit_rewrite`):
```python
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
```
This is the same instruction-by-instruction, newline-joined construction `pikepdf`'s own bundled
`canvas.py` uses (cited directly in `identity_rewrite.py`'s docstring, lines 84-87) — not a novel
technique. `engine/rewrite.py`'s surgery loop should follow this shape: walk `instructions`, decide
per-index whether to keep/replace/drop, `unparse_content_stream` per surviving instruction, join.

**CRITICAL, REQUIRED DEVIATION from this analog — do not coalesce `/Contents`.**
`identity_rewrite`/`null_edit_rewrite` both end with (lines 151, 189):
```python
            page.Contents = pdf.make_stream(new_bytes)
```
— i.e. always collapsing a page's `/Contents` array into one stream. RESEARCH.md's Pitfall 3
measured this directly: on `spike/fixtures/tj_refit_sample.pdf` (an 8-part array), coalescing plus
one mutated word produced a 13,689-line `qpdf --qdf` diff purely from object renumbering, and 52.5%
of the corpus has an array `/Contents`. `engine/rewrite.py` must instead replace only the specific
array element(s) containing edited runs:
```python
contents[part_index] = pdf.make_stream(new_bytes)   # array length, other elements' object
                                                       # numbers: untouched
```
This is the one place `rewrite.py` must NOT copy its analog's behavior — flag this explicitly in
review, since copying `identity_rewrite.py` verbatim here is the most likely accidental regression.

**Private-helper reuse, with a promotion note already on record** (`identity_rewrite.py` imports
`engine.classify_run._stream_bytes_and_resources`, a private helper defined at
`engine/classify_run.py` lines 105-127). CONTEXT.md's own Integration Points section: "Flagged in
review as acceptable for two consumers; the rewrite engine would be a third, at which point
promoting it to a public API is the cheap fix." `engine/rewrite.py` is that third consumer —
promoting it (drop the leading underscore, add to `classify_run.py`'s `__all__`) is an in-scope,
low-cost cleanup for this phase, not a new abstraction.

**Verify-after-rewrite / epsilon-tolerance pattern** (lines 262-308, `verify_roundtrip`, and the
epsilon constant at line 139):
```python
_FLOAT_EPSILON = 1e-6
...
    if abs(a.x - b.x) > _FLOAT_EPSILON or abs(a.y - b.y) > _FLOAT_EPSILON:
        return False
```
D-04's runtime text-matrix-invariant guard (re-walk the edited page, assert the matrix after the
edited run is unchanged within epsilon, refuse on violation) is the same shape: re-derive via a
fresh walk, compare floats with a named epsilon constant carrying its own measured-basis comment
(lines 127-138 explain exactly why `1e-6` and not exact `==`), refuse with a named reason on
mismatch rather than raising.

**No analog — the byte-offset-to-instruction-index bridge.** Correlating a run's own
`operator_byte_offset` values (already on `GlyphRecord`, `engine/records.py` line 31) to
`pikepdf.parse_content_stream`'s instruction-list indices is new code with no precedent anywhere in
`engine/`. RESEARCH.md's own Pattern 1 names this "this phase's own version of Phase 1's TJ-refit
spike... a small, cheap thing to prototype and measure *before* committing engineering time to the
full rewrite engine," and gives a starting implementation (`touched_instruction_indices`, its own
Architecture Patterns section) built from ordinal position among text-showing operators. Treat this
as a Wave 0 spike task, not something to derive by reading existing code — there is nothing to read.

---

### `engine/recipe.py` (controller/service, orchestration)

**Analogs:** `engine/run_id.py` (untrusted-string-parsing convention), `engine/classify_run.py`
(named-reason verdict vocabulary + orchestration-loop shape), `engine/index.py` (named typed
exception convention)

**Untrusted-input parsing — never eval, never unchecked indexing** (`engine/run_id.py`, lines
106-117):
```python
def decode_run_id(run_id: str) -> RunIdParts:
    """...this is the untrusted-input boundary Phase 4 will
    eventually hit, so it is a strict regex match, never eval or unchecked
    str.split indexing.
    """
    match = _RUN_ID_RE.match(run_id)
    if match is None:
        raise ValueError(f"malformed run id: {run_id!r}")
```
`engine/recipe.py`'s JSON op parsing (`{run_id, new_text}[]`) must use stdlib `json.load` (matching
RESEARCH.md's own V5 Input Validation guidance: "stdlib `json.load` (no `eval`, matching
`engine/run_id.py`'s own existing strict-regex-never-`str.split` precedent"), and every op's own
`run_id` field is decoded through `decode_run_id` itself — reused, not re-derived.

**`RunIdParts` carries the field D-10 needs directly** (lines 64-73):
```python
class RunIdParts(TypedDict):
    source_hash: str
    page: int
    part: int
    ...
```
D-10's hash check is: decode every op's `run_id`, compare `parts["source_hash"]` against the actual
opened document's own SHA-256, hard-refuse the WHOLE recipe on any mismatch (no `--force`). This
reads directly off the existing `TypedDict`, no new decoding logic.

**Named typed exception, citing its own threat-register basis** (`engine/index.py`, lines 68-83):
```python
# 02-RESEARCH.md Section 10 / this plan's own threat register T-02-01: "anything above
# ~10M glyphs is pathological -- abort with a named reason." Cumulative across the whole
# RunIndex's lifetime (see module docstring), not just what is currently cached.
MAX_DOCUMENT_GLYPHS = 10_000_000


class DocumentTooLargeError(Exception):
    """T-02-01: raised once a `RunIndex`'s cumulative walked glyph count exceeds
    `MAX_DOCUMENT_GLYPHS`. Never document content in the message -- counts only
    (T-02-04)."""
```
RESEARCH.md's own Known Threat Patterns table flags an unbounded recipe op-count/string-length as a
DoS surface with no current cap, and explicitly recommends "a sane bound... matching
`engine/index.py`'s own `MAX_DOCUMENT_GLYPHS` precedent of a named, documented ceiling with a typed
exception." `engine/recipe.py` needs the equivalent: a named constant (e.g. `MAX_RECIPE_OPS`) and a
typed `RecipeTooLargeError`, message with counts only.

**Named-reason verdict vocabulary to extend, not duplicate** (`engine/classify_run.py`, lines
69-77):
```python
@dataclass(frozen=True, slots=True)
class RunVerdict:
    """CLAS-04's three-state per-run verdict. `reason` is populated only when
    `state == "not_editable"` -- symbolic, Type3, no-ToUnicode, shared-Form-XObject and
    RTL each get their own distinct string, never a generic "not editable"...
    """
    state: RunState
    reason: str | None = None
```
CONTEXT.md's own code_context is explicit: "Phase 3's refusals should extend this vocabulary, not
invent a parallel one." EDIT-04's four new refusal reasons (unmapped font by name, won't-fit-after-
full-ladder, matrix-invariant-violated, source-hash-mismatch) are new `reason` strings attached to
this same shape (or a recipe-level result embedding it), not a new parallel verdict type.

**Checked-in-this-order, first-match-wins precedence pattern** (`engine/classify_run.py`, lines
181-226, `classify_run`'s docstring and body) — the per-op resolution pipeline in `recipe.py` (D-10
hash check → decode/resolve run_id → D-05 glyph-availability → D-01 fit ladder → D-04 matrix guard)
should read the same way: one function, checked top-to-bottom, first failing check returns a named
refusal and short-circuits — mirroring this file's own documented ordering discipline.

**All-or-nothing orchestration loop shape** (`engine/classify_run.py`, lines 291-320,
`classify_document`):
```python
def classify_document(path: str | Path) -> DocumentClassification:
    pdf = pikepdf.open(path)
    ...
    page_buckets: list[Bucket] = []
    runs: list[tuple[RunRecord, RunVerdict]] = []
    try:
        with open_document(path) as doc:
            for page_index, page in enumerate(doc.pages):
                bucket, page_runs, _glyph_count = _classify_one_page(...)
                page_buckets.append(bucket)
                runs.extend(page_runs)
    finally:
        pdf.close()
    return DocumentClassification(page_buckets=page_buckets, runs=runs)
```
Open once, loop, accumulate into one structured result, return — no partial side effects escape a
failure. `recipe.py`'s `apply_recipe` should resolve/validate every op first (RESEARCH.md's
Architecture diagram steps 1-4), and only proceed to font subsetting and `pdf.save()` (steps 5-9) if
every op validated cleanly — this is D-11 literally.

---

### `tools/pdftool.py` (modify — add `edit` subcommand)

**Analog:** itself — the existing `index` subcommand is the literal template

**Subparser registration pattern** (lines 73-90):
```python
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser(
        "index", help="Walk a PDF through the Phase 2 pipeline and print its run index"
    )
    index_parser.add_argument("pdf_path", help="Path to the PDF file")
    index_parser.add_argument(
        "--page", type=int, default=None,
        help="Print only this page's run list (0-indexed) instead of the whole-document summary",
    )
    index_parser.set_defaults(func=_cmd_index)

    args = parser.parse_args()
    return int(args.func(args))
```
`edit` slots in as a second `subparsers.add_parser("edit", ...)` block with its own
`_cmd_edit(args)` following `_cmd_index`'s shape (lines 64-70):
```python
def _cmd_index(args: argparse.Namespace) -> int:
    with RunIndex(args.pdf_path) as idx:
        if args.page is None:
            _print_summary(idx)
        else:
            _print_page_runs(idx, args.page)
    return 0
```
D-09's exact invocation shape is `pdftool edit doc.pdf --recipe r.json -o out.pdf`; D-03 requires
dry-run as the default with commit needing a separate explicit flag (e.g. `--commit`), so
`edit_parser` needs `pdf_path`, `--recipe` (required), `-o`/`--output` (required only when
committing), and the commit flag — printing the structured fit-plan report by default, writing only
when the flag is passed.

**sys.path shim** (lines 27-33) — reused unmodified, no new shim needed for `edit`:
```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.index import RunIndex  # noqa: E402
```
Add `from engine.recipe import apply_recipe, dry_run_recipe  # noqa: E402` (or equivalent) alongside
the existing `RunIndex` import.

---

### `pyproject.toml` (modify — add uharfbuzz mypy override)

**Analog:** itself — the existing fontTools override, lines 33-38:
```toml
# fontTools ships no py.typed marker, so strict mode cannot see its types. Scoped to
# fontTools alone -- never a blanket ignore_missing_imports, which would silently hide a
# genuinely missing import anywhere in the engine.
[[tool.mypy.overrides]]
module = ["fontTools.*"]
ignore_missing_imports = true
```
Add an identical block, module name changed, per RESEARCH.md Pitfall 6 (verified this session:
`mypy engine/` fails immediately with `[import-untyped]` the moment any `engine/` module imports
`uharfbuzz`, since it ships no stubs and no `py.typed` marker):
```toml
[[tool.mypy.overrides]]
module = ["uharfbuzz.*"]
ignore_missing_imports = true
```
**Sequencing note:** this must land before `engine/fit.py` or `engine/fonts.py` — both first-time
importers of `uharfbuzz` inside `engine/` — is committed, not after `mypy engine/` starts failing in
CI.

---

### `Dockerfile.ci` (modify — add opentype-sanitizer apt package)

**Analog:** itself — the existing ARG-pinned apt-get pattern, lines 17-31:
```dockerfile
ARG POPPLER_UTILS_VERSION=25.03.0-5+deb13u4
ARG MUPDF_TOOLS_VERSION=1.25.1+ds1-6+deb13u1
ARG QPDF_VERSION=12.2.0-1
ARG PDFCPU_VERSION=0.15.0

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl ca-certificates xz-utils \
        poppler-utils="${POPPLER_UTILS_VERSION}" \
        mupdf-tools="${MUPDF_TOOLS_VERSION}" \
        qpdf="${QPDF_VERSION}" && \
    rm -rf /var/lib/apt/lists/*
```
Add `ARG OTS_VERSION=8.2.1+dfsg-2` and `opentype-sanitizer="${OTS_VERSION}"` to the same
`apt-get install` line, following the identical pinned-ARG convention (RESEARCH.md's Standard Stack
section already gives this exact snippet, verified available for Debian trixie).

**Separately flagged, same file:** RESEARCH.md's Standard Stack section notes a real version gap —
this file pins `QPDF_VERSION=12.2.0-1` (line 19) while local dev has `qpdf 12.4.0` installed.
Since G2a's own acceptance criterion is a `qpdf --qdf` diff and this project's own stated discipline
is "output differs across versions and your golden tests will drift" (this exact file's own header
comment, lines 10-11), reconcile this pin as part of this phase rather than discovering drift later.

---

### `fonts/` (new directory — Liberation Sans/Serif/Mono + license)

**Analog:** `spike/fixtures/LiberationSans-Regular.ttf` + `spike/fixtures/LiberationSans-OFL-LICENSE.txt`
(already in the repo, borrowed for Phase 1's spike, same font lineage D-07 commits to)

D-07 bundles the Liberation trio (Sans/Serif/Mono); only Sans-Regular currently exists, and it lives
in `spike/fixtures/`, not `fonts/`. Net-new work: fetch Bold/Italic/BoldItalic for Sans and all 4
weights for Serif and Mono from `github.com/liberationfonts/liberation-fonts` **releases**
specifically (same lineage as the already-verified file — not a different mirror), plus one shared
`LICENSE-OFL.txt`.

**fsType verification check to run against every new file** (RESEARCH.md Pitfall 11's own reusable
snippet, verified this session against the existing Sans file):
```python
from fontTools.ttLib import TTFont
for path in ["fonts/LiberationSerif-Regular.ttf", "fonts/LiberationMono-Regular.ttf", ...]:
    f = TTFont(path)
    assert f["OS/2"].fsType == 0, f"{path}: fsType={f['OS/2'].fsType}, expected 0 (Installable)"
```
Sans is already verified `fsType=0`; Serif/Mono are not yet verified because the files don't exist
yet — run this the moment they're fetched, not assumed from "OFL implies fsType=0."

---

### `tests/test_fit.py`

**Analog:** `tests/test_tj_refit_prototype.py` (113 lines — explicit port target per RESEARCH.md's
own Wave 0 Gaps: "porting `tests/test_tj_refit_prototype.py`'s proven test cases (same fixture text,
same expected deltas) onto the real module")

**Module-scoped fixture pattern** (lines 41-45):
```python
@pytest.fixture(scope="module")
def original_advance_pt() -> float:
    return read_original_advance_pt(
        SAMPLE_PDF, 0, ORIGINAL_FONT_RESOURCE, ORIGINAL_TEXT, FONT_SIZE_PT
    )
```

**Cases to port verbatim** (lines 53-64, shorter/longer replacement; same fixture constants at
lines 33-38 — `SAMPLE_PDF`, `FONT`, `FONT_SIZE_PT = 14.0`, `ORIGINAL_TEXT = "Request for Taxpayer "`):
```python
def test_shorter_replacement_fits_within_threshold(original_advance_pt: float) -> None:
    result = fit_run(original_advance_pt, "Request Payer Tax ID", FONT, FONT_SIZE_PT)
    assert not result.refused
    assert result.replacement_shaped_advance_pt < original_advance_pt
    assert abs(result.delta_pt) < 0.5
```

**Refusal-test convention** (lines 94-101):
```python
def test_refuses_rather_than_guesses_when_delta_is_too_large(
    original_advance_pt: float,
) -> None:
    result = fit_run(original_advance_pt, "X", FONT, FONT_SIZE_PT)
    assert result.refused
    assert result.refusal_reason is not None
    assert result.strategy == "refused"
```
`engine/fit.py`'s new `Tz` rung needs its own case here, between the ported inter-word test (lines
84-91) and this refusal test: a delta landing in the 90-95% band, asserting `strategy == "tz"` (or
whichever literal is chosen) fires before refusal — this is the one case the spike had no path for
at all.

---

### `tests/test_fonts.py`

**Analog:** `tests/test_encoding_table.py` (per-branch test naming + mutation-proof convention)

**Per-branch named test convention** (grepped test names):
```
test_branch_t1_a_embedded_nonsymbolic
test_branch_t1_c_standard14_not_embedded
test_branch_c3a_cidfonttype2_identity
test_branch_c3a_malformed_cidtogidmap_stream_refuses
```
One test per distinct table entry/branch, named for the exact condition and outcome — not a single
parametrized mega-test that obscures which case failed. `fonts.py`'s mapping-table tests (one Base-
14 name, one MS-core-font variant, one unmapped-refuses case) and FONT-06's substitution-trigger
tests should follow this same naming discipline.

**MUTATION PROOF convention** (docstring on the malformed-CIDToGIDMap test, and referenced again in
`engine/encoding_table.py`'s own docstring for `glyph_presence`, lines 716-719):
```
MUTATION PROOF: returning (False, False) from the except branch below (refusing
instead of downgrading) flips `test_glyph_presence_downgrades_on_unparseable_program`
red -- confirmed by running that mutation once (see the report).
```
FONT-04's "no silent `/MissingWidth`-of-0" test and FONT-06's "entire run substitutes, never half"
test must each be a permanent negative case proven this same way — actually flip the real code to
the wrong behavior once, confirm the test catches it, per this project's standing "a check is not
trusted until demonstrated failing" convention (code_context section, citing this exact test by
name).

**Corpus-rate measurement convention** (`test_type1_fontfile_corpus_wide_parse_rate`, line 708 area)
— FONT-01's "table coverage is a measurable number" (D-06's stated consequence) should be a
`@pytest.mark.corpus` test reporting the same kind of pass-rate-over-the-whole-corpus figure.

---

### `tests/test_rewrite.py`

**Analog:** `tests/test_roundtrip.py` (277 lines — direct successor test file)

**Manifest-driven fixture selection** (lines 38-40, 67-68):
```python
CORPUS_DIR = REPO_ROOT / "corpus" / "public"
MANIFEST_PATH = REPO_ROOT / "corpus" / "manifest.json"

def _manifest() -> list[dict]:
    return json.loads(MANIFEST_PATH.read_text())
```

**Named-fixture-by-measured-property convention** (lines 50-64) — this phase's own multi-operator
and non-contiguous-run fixtures should be the SAME real documents RESEARCH.md already measured them
against by name (`irs_form_1040.pdf`, `irs_form_w4.pdf`), matching this file's own precedent of
naming exactly why each fixture was picked (e.g. "does NOT reproduce this interaction (verified
directly)").

**Permanent negative case via a standalone mutation copy** (lines 122-159 build the mutation, lines
162-172 assert against it):
```python
def _mutated_rewrite_changes_one_tj_text(pdf_path: Path, output_path: Path) -> None:
    """THE MUTATION for the negative-case test below -- a standalone COPY... never
    a change to identity_rewrite itself..."""
    ...

def test_verify_roundtrip_detects_mutated_tj_text(tmp_path: Path) -> None:
    idx = RunIndex(WIKIPEDIA_ZH)
    try:
        out = tmp_path / "mutated.pdf"
        _mutated_rewrite_changes_one_tj_text(WIKIPEDIA_ZH, out)
        assert verify_roundtrip(WIKIPEDIA_ZH, idx, str(out)) is False
    finally:
        idx.close()
```
Same shape for D-04's matrix-invariant guard: a standalone function that deliberately breaks the
invariant (e.g. writes a wrong `Tm` after the edited run), asserting the real rewrite path refuses
it by name.

**Exact-set assertion against a measured known-failure set** (lines 190, 231-237):
```python
KNOWN_MALFORMED_WALK_FAILURES = frozenset({"govdocs1_011_011089.pdf"})
...
    assert set(walk_failures) == KNOWN_MALFORMED_WALK_FAILURES, (
        f"walk-failure set changed: "
        f"new={set(walk_failures) - KNOWN_MALFORMED_WALK_FAILURES} "
        f"missing={KNOWN_MALFORMED_WALK_FAILURES - set(walk_failures)}; "
        f"details={walk_failures}"
    )
```
Reuse directly for any new known-interaction set the rewrite corpus sweep discovers — e.g. documents
hitting the pre-existing per-part `/Tf` scoping limit (named in Deferred Ideas as inherited, not
fixed, this phase).

**Harness reuse block** (lines 41-49 import, lines 260-277 usage) — literal template for confirming
untouched page regions are byte-identical post-edit (roadmap criterion 3):
```python
sys.path.insert(0, str(REPO_ROOT / "harness"))
from masked_diff import masked_pixel_diff  # noqa: E402
from render_diff import render_all  # noqa: E402
...
    orig_pngs = render_all(doc_path, _HARNESS_PAGE_INDEX, tmp_path / "orig")
    new_pngs = render_all(rewritten, _HARNESS_PAGE_INDEX, tmp_path / "new")
    for label, orig_png, new_png in zip(_ENGINE_LABELS, orig_pngs, new_pngs):
        diff = masked_pixel_diff(orig_png, new_png)
        assert diff == 0, (...)
```

---

### `tests/test_recipe.py`

**Analogs:** `tests/test_run_id.py` (round-trip/strict-parse convention), `tests/test_classify.py`
(named-refusal test convention, referenced by test name)

**Fixture-constant convention** (line 14):
```python
HASH = "a" * 64
```
D-10's source-hash-mismatch test needs both a real hash (from the actual test document) and a
deliberately-wrong 64-hex-char one — reuse this exact throwaway-constant style for the wrong one.

**Round-trip-per-shape convention** (lines 20-55) — one test per grammar segment:
```python
def test_round_trip_bare_page_part() -> None:
    run_id = encode_run_id(HASH, page=2, part=0, byte_offset=57)
    assert encode_run_id(**decode_run_id(run_id)) == run_id
```
If the recipe JSON schema grows optional fields, one test per shape follows this same pattern.

**Named-refusal-is-scoped-correctly precedent** — `tests/test_classify.py` has
`test_clas05_whole_document_refusal_is_wrong` (line 356) as a named precedent for testing refusal
*scope* specifically (a refusal must stay at the right granularity, never cascade). `test_recipe.py`
needs the mirror image for D-10/D-11's genuinely-different scoping: one test proving a single op's
own refusal (e.g. won't-fit) does NOT abort a well-formed recipe under `--partial`-style logic if
that ever existed (it deliberately doesn't, D-11), and a separate test proving a hash mismatch DOES
abort the entire recipe — these two must not be tested with the same helper or the distinction (D-11
"all failing ops named individually" vs. D-10 "one mismatch kills everything, no per-op detail
needed") gets blurred.

---

### `tests/test_pdftool_edit.py`

**Analog:** `tests/test_check_corpus_size.py` (67 lines — the only existing CLI-integration test in
the repo, and a near-exact structural match for what dry-run-vs-commit testing needs)

**Dual direct-call + subprocess pattern, in full** (lines 22-39):
```python
def test_below_threshold_reports_failure(tmp_path):
    public = tmp_path / "public.json"
    private = tmp_path / "private.json"
    _write_manifest(public, 40)
    _write_manifest(private, 30)

    combined = check_corpus_size.check_corpus_size(str(public), str(private))
    assert combined == 70

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "check_corpus_size.py"), str(public), str(private)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "70" in result.stdout
    assert "public=40" in result.stdout
    assert "private=30" in result.stdout
```
Direct template for D-03's "dry-run report matches actual commit outcome" acceptance test: call
`engine.recipe`'s dry-run function directly for the structured result, THEN invoke
`python tools/pdftool.py edit doc.pdf --recipe r.json` via `subprocess.run` and assert the printed
table agrees with the structured data — proving the CLI output really is, per code_context's own
Specific Ideas wording, "a rendering of it," not a second independent computation.

**Import-the-module-under-test-directly shim** (lines 12-15):
```python
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import check_corpus_size  # noqa: E402
```
Same shim style needed if `test_pdftool_edit.py` calls `_cmd_edit` directly rather than only via
subprocess (subprocess alone is enough for the pure CLI-contract tests; a direct import is cheaper
for tests that need to inspect intermediate structured data without parsing stdout).

---

### `tests/test_gate_g2a.py`

**Analog:** `tests/test_roundtrip.py`'s Task 2 shape (exact-set assertion over a corpus sweep,
already excerpted above) — partial match; the confined-diff mechanism itself is new code.

**No analog for the core mechanism.** RESEARCH.md's own Don't Hand-Roll table names the fix
directly: "A targeted Python comparison of only the touched stream's decoded operator list (old vs
new)... a ~20-line Python function using `pikepdf.parse_content_stream` twice, not a new
dependency." There is nothing in the repo that already does a targeted structural stream diff — this
is Wave 0 work, not something to find by searching. Pitfall 3's own "How to avoid" paragraph is the
closest thing to a spec to build against.

---

### `tests/test_gate_g2b.py`

**Analog:** `tests/test_roundtrip.py`'s Task 3 (harness-reuse shape, already excerpted above under
`test_rewrite.py` — the identical `sys.path.insert` + `masked_diff`/`render_diff` import block
applies here unmodified)

Per canonical_refs' explicit instruction ("Verification vehicles (reuse, do not reinvent)"),
`harness/masked_diff.py::masked_pixel_diff` and `harness/render_diff.py::render_all` must be reused
exactly as `test_roundtrip.py` already calls them, not reimplemented. The one new element G2b needs
beyond what `test_roundtrip.py` already exercises is the CROSS-engine tolerant comparison (not
same-engine zero-tolerance) — `harness/run_corpus_harness.py`'s own module docstring documents the
measured tolerance values to use (3px blur, 20/255 per-channel, 8% threshold), per canonical_refs.

---

## Shared Patterns

### Frozen/slots dataclasses for every new record/verdict type
**Source:** `engine/records.py` (`GlyphRecord`), `engine/encoding_table.py` (`FontVerdict`,
`GlyphVerdict`), `engine/classify_run.py` (`RunVerdict`)
**Apply to:** `FitResult` (ported into `engine/fit.py` — REQUIRES adding `frozen=True, slots=True`,
since the spike version doesn't have it), any new result/verdict type in `engine/fonts.py` and
`engine/recipe.py`
```python
@dataclass(frozen=True, slots=True)
class FontVerdict:
    branch_id: str
    editable: bool
    substitution: bool
    reason: str | None = None
```

### Named refusals carry a distinct reason string, never a generic failure
**Source:** `engine/classify_run.py::RunVerdict`, `engine/encoding_table.py::FontVerdict`/`GlyphVerdict`
**Apply to:** every refusal path in `fit.py` (won't-fit), `fonts.py` (unmapped font, by name),
`rewrite.py` (matrix invariant violated), `recipe.py` (source-hash mismatch) — EDIT-04's own
requirement, and code_context's explicit instruction to extend `RunVerdict`'s vocabulary rather than
invent a parallel one.

### Measure, then pin — every threshold carries its measured basis in a comment beside it
**Source:** `engine/index.py` (`CACHE_GLYPH_BUDGET = 1_900_000`, comment cites the 178MB/1.9M-glyph
measurement; `MAX_DOCUMENT_GLYPHS = 10_000_000`, comment cites the threat register), `engine/
clusterer.py` (`BAND_TOLERANCE_EM = 0.2`, `SUPERSCRIPT_RISE_TOLERANCE_EM = 0.5`), `engine/
space_threshold.py` (`K_EM = 0.10`, `BREAK_EM = 0.33`), `spike/tj_refit_prototype.py`
(`_INTER_WORD_ABSORB_MULTIPLIER = 2.0`)
**Apply to:** the new `Tz` floor constant in `fit.py` (`TZ_FLOOR_PERCENT = 90`, citing RESEARCH.md
Pattern 3's reasoning), any new recipe-size cap in `recipe.py`, any new glyph-union or subset-size
threshold in `fonts.py`.

### Try/except-and-classify, never a bare `except: pass`
**Source:** `engine/encoding_table.py`, five separate sites (e.g. lines 191-193):
```python
            try:
                data = bytes(stream.read_bytes())
            except Exception:  # noqa: BLE001 - an unreadable stream is "not usable", not a crash
                return None
```
**Apply to:** any new font-program parsing in `fonts.py` (subsetting, glyph-availability checks
against an original document's font), any new content-stream parsing in `rewrite.py` — RESEARCH.md's
own Known Threat Patterns table names this as the required extension.

### No document content in logs, assertion messages, or exception text
**Source:** `engine/index.py::DocumentTooLargeError` ("Never document content in the message --
counts only"), `tests/test_roundtrip.py`'s module docstring ("No document content (glyph text)
appears in any assertion message... only counts, filenames and booleans"), `tests/
test_malformed_corpus_roundtrip`'s `type(exc).__name__`-only exception capture (lines 214-216)
**Apply to:** every new refusal reason and every new test assertion this phase adds — refusal
reasons name a font, a rule, a byte offset; never the replacement text or the surrounding original
text.

### `import playa` confined to `engine/playa_boundary.py`
**Source:** enforced by an existing test (referenced in code_context; `engine/encoding_table.py`'s
own module docstring: "imports no playa... conflating them is the TEXT-05 mistake")
**Apply to:** `fit.py`, `fonts.py`, `rewrite.py`, `recipe.py` — none of the four new modules should
import `playa` directly; go through `RunIndex`/`RunRecord`/`GlyphRecord` for anything already walked.

### Scratch-only writes — `tempfile`/`tmp_path`, never the corpus
**Source:** `tests/test_roundtrip.py` module docstring + every test in it (`tmp_path` fixture,
`tempfile.TemporaryDirectory()` at line 219)
**Apply to:** every new test in `test_fit.py`, `test_fonts.py`, `test_rewrite.py`, `test_recipe.py`,
`test_pdftool_edit.py`, `test_gate_g2a.py`, `test_gate_g2b.py` — and to `pdftool edit`'s own
`-o`/`--output` argument, which must never default to overwriting the input path.

### mypy strict, zero `# type: ignore` under `engine/` — new override needed first
**Source:** `pyproject.toml`'s existing `[[tool.mypy.overrides]]` for `fontTools.*`
**Apply to:** add the mirror block for `uharfbuzz.*` (RESEARCH.md Pitfall 6) before `fit.py` or
`fonts.py` land, not after CI fails.

## No Analog Found

Sub-pieces with no in-repo precedent at all (the parent file has a role-match analog for everything
else about it; these specific mechanisms are genuinely new code this phase must design from
RESEARCH.md's own recommendations, not from reading existing `engine/` source):

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `engine/fonts.py` (write/embed portion only — Type0 dict, `/W`, ToUnicode CMap, subset-tag generation) | service | file-I/O | Nothing in `engine/` writes a font or constructs a font dictionary today; every existing module only reads. RESEARCH.md's own Code Examples section supplies the reference shapes (verified against WeasyPrint, BSD-3-Clause, cross-checked against this project's own `encoding_table.py` reader for shape agreement) — use those, not a search for an in-repo precedent that doesn't exist. |
| `engine/rewrite.py` (byte-offset-to-instruction-index bridge, `touched_instruction_indices`) | service | transform | New correlation logic between playa's operator ordinals and pikepdf's instruction-list ordinals; RESEARCH.md flags this as its own not-yet-measured assumption (A3) and recommends a small dedicated prototype, the same way Phase 1's TJ-refit spike de-risked the width math before Phase 2 built on it. |
| `tests/test_gate_g2a.py` (the confined-diff mechanism under test) | test | transform | The targeted structural stream-diff function itself doesn't exist anywhere yet (see Pattern Assignments above) — the test and the implementation are both Wave 0 work. |

## Metadata

**Analog search scope:** `engine/` (14 existing modules), `tools/pdftool.py`, `spike/` (both modules
+ fixtures), `tests/` (all existing test files), `pyproject.toml`, `Dockerfile.ci`
**Files read in full:** `engine/identity_rewrite.py`, `engine/encoding_table.py`,
`engine/classify_run.py`, `engine/index.py`, `engine/run_id.py`, `engine/records.py`,
`engine/types.py`, `tools/pdftool.py`, `spike/tj_refit_prototype.py`, `tests/test_roundtrip.py`,
`tests/test_tj_refit_prototype.py`, `tests/test_run_id.py`, `tests/test_check_corpus_size.py`,
`tests/conftest.py`, `pyproject.toml`, `Dockerfile.ci`
**Files searched/grepped for structure (not fully read — already well-characterized by their own
docstrings quoted in CONTEXT.md, or large and only their names/signatures were needed):**
`engine/clusterer.py`, `engine/space_threshold.py`, `tests/test_classify.py`,
`tests/test_encoding_table.py`
**Pattern extraction date:** 2026-08-18

---

## PATTERN MAPPING COMPLETE

**Phase:** 3 - Rewrite Engine + Font Pipeline
**Files classified:** 15
**Analogs found:** 15 / 15

### Coverage
- Files with exact analog: 9 (`fit.py`, `rewrite.py`, `tools/pdftool.py`, `pyproject.toml`,
  `Dockerfile.ci`, `fonts/`, `test_fit.py`, `test_rewrite.py`, `test_pdftool_edit.py`)
- Files with role-match analog: 5 (`fonts.py`, `recipe.py`, `test_fonts.py`, `test_recipe.py`,
  `test_gate_g2b.py`)
- Files with partial/no analog for a core sub-mechanism: 1 file fully partial (`test_gate_g2a.py`)
  plus 2 named sub-pieces inside otherwise-matched files (`fonts.py`'s write/embed side,
  `rewrite.py`'s instruction-index bridge) — see `## No Analog Found`

### Key Patterns Identified
- Every new record/verdict type must be `@dataclass(frozen=True, slots=True)` — including
  `FitResult` when ported from the spike, which currently is NOT frozen/slots and needs that added.
- `engine/rewrite.py` must deliberately NOT copy `identity_rewrite.py`'s one behavior of coalescing
  `/Contents` into a single stream — that is the one pitfall (measured, 13,689-line spurious diff)
  a naive "copy the predecessor" approach would walk straight into.
- Every numeric threshold this phase adds (the `Tz` floor, any recipe size cap) needs a named
  constant with its measured/reasoned basis in a comment beside it, matching `CACHE_GLYPH_BUDGET`/
  `MAX_DOCUMENT_GLYPHS`/`K_EM`/`BREAK_EM`'s existing style.
- `pyproject.toml`'s `uharfbuzz.*` mypy override is a hard prerequisite for `fit.py`/`fonts.py`, not
  an independent chore — sequence it first.

### File Created
`/Users/prempatel/Documents/pdf-tool/.planning/phases/03-rewrite-engine-font-pipeline/03-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. Planner can now reference analog patterns in PLAN.md files.
