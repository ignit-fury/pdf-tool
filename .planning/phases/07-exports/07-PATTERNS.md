# Phase 7: Exports - Pattern Map

**Mapped:** 2026-08-30
**Files analyzed:** 25 (5 modified index-extension files, 1 fixture-builder, 1 single-path test,
2 blocks-layer files, 9 export-package files, 6 export test files, 1 gate test, 1 CLI file)
**Analogs found:** 24 / 25 (the `engine.blocks` reading-order/block-structure layer itself has no
analog in this repo — see `## No Analog Found`)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `engine/records.py` (MODIFY) | model | transform | `engine/encoding_table.py` (`FontVerdict`) | exact (additive-optional-field precedent) |
| `engine/types.py` (MODIFY, if a typed wrapper is chosen) | model | transform | itself (`CharCode`/`GlyphId`/`Unicode` `NewType`s) | exact |
| `engine/clusterer.py` (MODIFY) | service | transform | itself (`_emit_logical_run`) | exact (single call site) |
| `engine/index.py` (MODIFY) | store | CRUD | itself (`PageIndex`, `_parse_page`) | exact (single call site) |
| `engine/encoding_table.py` (MODIFY) | model | transform | itself (`FontVerdict`) | exact (single dataclass def) |
| `engine/classify_run.py` (MODIFY) | service | transform | itself (`_resolve_font_for_glyph`) | exact (single call site) |
| `tools/build_export_fixtures.py` (NEW) | utility | batch | `tools/build_mixed_fixture.py` | exact |
| `tests/test_export_single_path.py` (NEW) | test | batch / transform | `tests/test_rewrite.py:1769-1804` (AST half) + `engine/index.py:139-160` (call-count half) | exact |
| `engine/blocks.py` (NEW) | service | transform | `engine/classify_page.py` (pure-function-over-open-data shape) | role-match (new domain logic, established shape) |
| `tests/test_blocks.py` (NEW) | test | transform | `tests/test_classify.py` (`_dummy_run` fixture-construction pattern) | role-match |
| `engine/export/__init__.py` (NEW) | config | — | `engine/__init__.py` (empty package marker) | exact |
| `engine/export/text.py` (NEW) | service | transform | `tools/pdftool.py::_print_page_runs` | exact (identical iterate-and-join shape) |
| `engine/export/markdown.py` (NEW) | service | transform | `engine/blocks.py` (consumption shape only; rendering itself is new) | partial |
| `engine/export/html.py` (NEW) | service | transform | `engine/blocks.py` (consumption shape only; rendering itself is new) | partial |
| `engine/export/images.py` (NEW) | service | file-I/O | `harness/render_diff.py::render_pdfium` | exact |
| `engine/export/compress.py` (NEW) | service | file-I/O | `engine/identity_rewrite.py::identity_rewrite` (open/mutate/save/close shape) | role-match |
| `engine/export/split.py` (NEW) | service | file-I/O | `tools/build_mixed_fixture.py::build_mixed_scanned` | exact |
| `engine/export/flatten.py` (NEW) | service | file-I/O | `engine/identity_rewrite.py` (shape) + `engine/playa_boundary.py::annotation_appearances` (read-side reuse reference) | role-match |
| `tests/test_export_text.py` (NEW) | test | transform | `tests/test_classify.py:444-463` (`_dummy_run`) | exact |
| `tests/test_export_html.py` (NEW, implies a markdown counterpart) | test | transform | `tests/test_classify.py:444-463` + `tests/test_blocks.py` | role-match |
| `tests/test_export_images.py` (NEW) | test | file-I/O | `tests/test_gate_g2a.py` (`render_all` + fixture pattern) | role-match |
| `tests/test_compress.py` (NEW) | test | file-I/O | `tests/test_gate_g2a.py` (`masked_pixel_diff` usage, lines 333-341) | role-match |
| `tests/test_split.py` (NEW) | test | file-I/O | `tests/test_gate_g2a.py` (`qpdf --check` subprocess, lines 317-323) | role-match |
| `tests/test_flatten.py` (NEW) | test | file-I/O | `tests/test_gate_g2a.py` (`qpdf --check` + masked diff, both halves) | role-match |
| `tests/test_gate_g6.py` (NEW) | test | file-I/O | `tests/test_gate_g2a.py` + `tests/test_gate_g2b.py` | exact (same "this test IS the gate" shape) |
| `tools/pdftool.py` (MODIFY — add export subcommands) | controller | request-response | itself (existing `edit` subparser added beside `index`) | exact |

---

## Pattern Assignments

### Wave 0 — Index extension (A-7.1, blocks everything else transitively)

All five files below implement ONE change: thread font size, font identity, and page
geometry through the pipeline at points where the values are already in scope but discarded.
Every touch point below is a **single call site** (verified by grep, not assumed) — this is a
small, additive change, not a redesign.

#### `engine/records.py` (MODIFY)

**Analog for "add an optional field to an existing dataclass safely":** `engine/encoding_table.py`'s `FontVerdict`

**Current shape** (`engine/records.py:65-70`):
```python
@dataclass
class RunRecord:
    run_id: str
    glyphs: list[GlyphRecord]
    display_text: str  # synthetic spaces inserted by the clusterer (D-03)
    page: int
```

`RunRecord` is a **plain** `@dataclass` — not `frozen=True, slots=True` like `GlyphRecord`/
`ClusterAttrs` (`engine/records.py:19-33`) — so adding fields is cheap and does not require
touching a locked 13-field shape (that lock is `GlyphRecord`'s, per TEXT-02, and does not apply
here).

**Where `font_size_pt` already exists but is discarded** — `ClusterAttrs.effective_em`
(`engine/records.py:59-62`):
```python
    effective_em is `space_threshold.effective_em(text_obj)` -- the SAME em D-03 tuned
    K_EM/BREAK_EM against. Constant across one text-showing operator's glyphs, but every
    glyph carries its own copy rather than the caller re-deriving it...
    """

    fill_color: tuple[tuple[float, ...], str | None]
    rise: float
    effective_em: float
    direction: tuple[float, float]
```

**The additive-field precedent to copy** — `FontVerdict` already proves a new trailing field
with a default is safe (`engine/encoding_table.py:125-137`):
```python
@dataclass(frozen=True, slots=True)
class FontVerdict:
    branch_id: str
    editable: bool
    substitution: bool
    reason: str | None = None
```
Verified by grep: every one of the 20+ construction call sites (`engine/encoding_table.py:334,
336,337,340,341,353,...`, `engine/classify_run.py:152,157`) calls `FontVerdict(...)`
**positionally**, e.g. `FontVerdict("NOEMB", False, False, "symbolic simple font, not
embedded")`. A 5th field added with a default (as `reason` itself was) does not break any of
them — the same shape to copy for `RunRecord`'s new fields, and for `FontVerdict.base_font`
below.

**Call sites needing a new field default** (all keyword-based, confirmed by grep):
`engine/clusterer.py:309`, `tests/test_classify.py:437,463`, `tests/test_rewrite.py:766` — a
default value on the new field(s) keeps every one of these compiling unmodified.

---

#### `engine/types.py` (MODIFY, if a typed wrapper is chosen over a bare `float`)

**Analog:** itself — the existing `NewType` discipline

**Current shape** (`engine/types.py:19-24`, full file already read):
```python
CharCode = NewType("CharCode", int)  # a code as it appears in the content stream
GlyphId = NewType("GlyphId", int)  # a GID / CID in the font program
Unicode = NewType("Unicode", str)  # /ToUnicode output — DISPLAY AND SEARCH ONLY

CodeToGlyph = dict[CharCode, GlyphId]  # the FORWARD map. Decides pixels.
CodeToUnicode = dict[CharCode, Unicode]  # /ToUnicode. Decides nothing.
```

This project reaches for a `NewType` whenever two same-underlying-type values must never be
compared/assigned across a semantic boundary (`types.py`'s own docstring: "CodeToGlyph and
CodeToUnicode are distinct types so mypy --strict rejects any attempt to use one where the
other is required"). `font_size_pt` and `page_width_pt`/`page_height_pt` are all plain
`float`s with different units/meanings than any existing float in the codebase — if the
planner wants the same mypy-enforced distinction (e.g. a `Points = NewType("Points", float)`),
this file is the one place that convention lives. **This is genuinely Claude's Discretion**
(RESEARCH.md Pattern 1 says so explicitly: "whichever it is [a passed-through `effective_em`
or a separately computed true `Tfs`] ... the value must exist on RunRecord") — a bare `float`
field on `RunRecord` is equally valid and smaller. Flagged here only so the planner does not
have to rediscover this file's own convention from scratch if they choose the typed route.

---

#### `engine/clusterer.py` (MODIFY — `_emit_logical_run`)

**Analog:** itself — single construction call site

**Current shape** (`engine/clusterer.py:274-317`, the value is already in scope, just unread):
```python
def _emit_logical_run(
    page_index: int,
    path: StreamPath,
    logical: list[_GlyphItem],           # list[(GlyphRecord, ClusterAttrs)] -- ALREADY HERE
    gaps: list[float],
    source_hash: str,
    glyph_verdict_fn: Callable[[GlyphRecord], GlyphVerdict],
) -> list[RunRecord]:
    first_record, _first_attrs = logical[0]
    ...
    out: list[RunRecord] = []
    for start, end in fragments:
        frag = logical[start:end]
        frag_gaps = gaps[start:end]
        ...
        out.append(
            RunRecord(
                run_id=run_id,
                glyphs=[record for record, _attrs in frag],
                display_text=_display_text(frag, frag_gaps),
                page=page_index,
                # NEW: font_size_pt=frag[0][1].effective_em -- frag's own first glyph's
                # ClusterAttrs, already in scope at this exact line, just unread today.
            )
        )
    return out
```
`frag[0][1]` is the fragment's first `(GlyphRecord, ClusterAttrs)` tuple's `ClusterAttrs` —
`frag[0][1].effective_em` is the value RESEARCH.md Pattern 1 names as the signal to carry
forward. One line added inside an existing loop; no new parameter, no new call.

---

#### `engine/index.py` (MODIFY — `PageIndex` + `_parse_page`)

**Analog:** itself — single construction call site

**Current shape** (`engine/index.py:87-96`):
```python
@dataclass(frozen=True, slots=True)
class PageIndex:
    """One page's cached classification result..."""

    bucket: Bucket
    runs: list[tuple[RunRecord, RunVerdict]]
    glyph_count: int
```
Note this one **is** `frozen=True, slots=True` (unlike `RunRecord`) — a new field still needs
only a default to stay compatible, since there is exactly **one** construction call site
(`engine/index.py:160`, inside `_parse_page`, `engine/index.py:139-160`):
```python
    def _parse_page(self, page_index: int) -> PageIndex:
        page = self._doc.pages[page_index]
        bucket, runs, glyph_count = _classify_one_page(
            self._pdf, self._doc, page, page_index,
            self._shared, self._font_cache, self._source_hash,
        )
        ...
        return PageIndex(bucket=bucket, runs=runs, glyph_count=glyph_count)
        # NEW: page_width_pt=..., page_height_pt=... -- `page` (playa's Page, in scope
        # right here) already carries `.cropbox`, per classify_page.py's own precedent
        # below. No new parse, no new parameter threaded in from outside.
```

**Where the CropBox is already resolved for an unrelated reason** — the precedent this reuses
(`engine/classify_page.py:117-118` inside `image_coverage`, and again at `:148` inside
`classify_page`):
```python
    x0, y0, x1, y1 = page.cropbox
```
Same `page` object, same attribute, zero new I/O.

---

#### `engine/encoding_table.py` (MODIFY — `FontVerdict`)

**Analog:** itself

**Current shape** (`engine/encoding_table.py:125-137`, already shown above) — add
`base_font: str | None = None` as a fifth field, after `reason`. Populate it once, at the
point `font_dict` is already resolved and about to be discarded.

**The touch point** (`engine/classify_run.py:136-169`, `_resolve_font_for_glyph`):
```python
def _resolve_font_for_glyph(
    pdf: pikepdf.Pdf, page_index: int, path: StreamPath,
    glyph: GlyphRecord, cache: dict[tuple[tuple[int, int], bytes], FontVerdict],
) -> FontVerdict:
    stream_bytes, resources = stream_bytes_and_resources(
        pdf, page_index, glyph.stream_id, path.xobj_path
    )
    name = _find_active_font_name(stream_bytes, glyph.operator_byte_offset)
    if name is None:
        return FontVerdict("NO-TF", False, False, "no /Tf operator precedes this glyph")

    fonts = resources.get("/Font") if resources is not None else None
    font_dict = fonts.get("/" + name.decode("latin-1")) if fonts is not None else None
    # font_dict is in scope right here -- font_dict.get("/BaseFont") is one more read,
    # never a second parse. Currently font_dict is discarded once resolve_font() returns.
    if font_dict is None:
        return FontVerdict("NO-TF", False, False, "active font resource name not found...")
    ...
    cache_key = (resources.objgen, name)
    if cache_key not in cache:
        cache[cache_key] = resolve_font(font_dict)   # <- base_font must be threaded in here
    return cache[cache_key]
```

**Why `font_id` itself cannot be the reverse-lookup route** (`engine/walker.py:281-303`,
`_FontIds` — read-only reference, do not modify):
```python
class _FontIds:
    """Interns font objects to small ints for `GlyphRecord.font_id`.

    What consumers need is "did the font change between these two glyphs" (D-01 breaks
    runs on font change), and an objid is both unstable across qpdf's repair-on-open and
    absent from playa's Font.
    """
```
This confirms RESEARCH.md's finding directly: `font_id` is opaque by design and stays that
way — the fix lives in `classify_run.py`, not `walker.py`. **`walker.py` needs no
modification for this phase**; it is read-only context for why the fix is where it is.

---

### Wave 0 — Fixture construction (A-7.4)

#### `tools/build_export_fixtures.py` (NEW)

**Analog:** `tools/build_mixed_fixture.py` — exact structural match: a one-off, documented,
re-runnable builder script whose output is committed under `tests/fixtures/`.

**Header/audit-trail convention to copy** (`tools/build_mixed_fixture.py:1-7`):
```python
"""One-off builder for two synthetic test fixtures the corpus cannot supply.

Run once; its output is committed under tests/fixtures/. Re-running regenerates
byte-identical-in-structure fixtures from the same source pages, so this script
is the audit trail for how they were built.

    uv run --frozen python tools/build_mixed_fixture.py
"""
```

**Why-the-corpus-lacked-it documentation convention to copy** (`tools/build_mixed_fixture.py:9-20`
— cite the measured gap exactly the way this phase's corpus gap was measured):
```python
Fixture 1: tests/fixtures/mixed_scanned.pdf
--------------------------------------------
CLAS-05 ("refuse the operation, never the document") needs a document that
genuinely mixes editable text pages with scanned image-only pages. No corpus
document does this...
```
For this phase, cite verbatim what RESEARCH.md already measured: 0 documents tagged
multi-column, only 3 tagged `tables`, in the 217-document `corpus/manifest.json`.

**Build-a-page-from-scratch pattern to copy** (`tools/build_mixed_fixture.py:110-122`,
`build_render_mode_7` — the shape for a heading-heavy fixture with a KNOWN, hand-measured
font-size ratio, since one does not exist in the corpus):
```python
def build_render_mode_7():
    pdf = pikepdf.Pdf.new()
    try:
        page = pdf.add_blank_page(page_size=(612, 792))
        font = pdf.make_indirect(
            Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica)
        )
        page.Resources = Dictionary(Font=Dictionary(F1=font))
        content = b"BT /F1 24 Tf 100 700 Td 7 Tr (Invisible add-to-clip text) Tj ET"
        page.Contents = pdf.make_stream(content)
        pdf.save(FIXTURES_DIR / "render_mode_7.pdf")
    finally:
        pdf.close()
```
For a heading fixture: two `Tf` sizes with a documented, precise ratio (e.g. 24pt heading vs
10pt body — pick the ratio and WRITE DOWN the number, the same way this function's own
docstring states "40 pages = 37 editable + 3 scanned" as the exact, asserted sizing).

**Multi-page-copy pattern to copy** (`tools/build_mixed_fixture.py:93-107`,
`build_mixed_scanned` — the shape for a multi-column fixture assembled from real corpus
pages, if a hand-built one is not preferred):
```python
def build_mixed_scanned():
    text_src = pikepdf.open(CORPUS_DIR / TEXT_SOURCE)
    scan_src = pikepdf.open(CORPUS_DIR / SCAN_SOURCE)
    out = pikepdf.Pdf.new()
    try:
        for kind, i in PAGE_PLAN:
            if kind == "text":
                out.pages.append(text_src.pages[TEXT_PAGES[i]])
            else:
                out.pages.append(scan_src.pages[SCAN_PAGES[i]])
        out.save(FIXTURES_DIR / "mixed_scanned.pdf")
    finally:
        out.close()
        text_src.close()
        scan_src.close()
```

---

### Wave 0 — Single-extraction-path proof (EXPO-05 / A-7.5)

#### `tests/test_export_single_path.py` (NEW)

**Two distinct analogs, one per half — both real, both already in this repo (better than
RESEARCH.md's own from-scratch sketch, which duplicates what already exists).**

**AST-scan half — analog `tests/test_rewrite.py:1769-1804`, a real, already-shipped precedent
for exactly this shape** (scanning one module's own AST for a forbidden pattern, never a text
grep):
```python
def test_no_raw_string_formatting_builds_content_stream_bytes() -> None:
    """T-03-06-01's static half, enforced in CI rather than only at review time: no
    f-string and no `+`-concatenation anywhere in `engine/rewrite.py` may assemble anything
    from `new_text`. Checked over the module's own AST -- not a text grep, which would trip
    over prose in docstrings and miss a multi-line expression.
    """
    module = ast.parse((REPO_ROOT / "engine" / "rewrite.py").read_text())

    def mentions_new_text(node: ast.AST) -> bool:
        return any(
            isinstance(child, ast.Name) and child.id == "new_text"
            for child in ast.walk(node)
        )

    offenders = [
        f"{type(node).__name__} at line {node.lineno}"
        for node in ast.walk(module)
        if (
            isinstance(node, ast.JoinedStr)
            or (isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)))
        )
        and mentions_new_text(node)
    ]
    assert offenders == []
```
For this phase: walk every `.py` file under `engine/` (not just one), assert none besides
`engine/playa_boundary.py` contains an `Import`/`ImportFrom` node naming `playa`. Confirmed
by grep this session: **no existing test does this today** — `grep -rn "import playa"
tests/*.py` finds only fixture-side imports (permitted), and the convention is currently
prose-only in three module docstrings: `engine/clusterer.py:10`, `engine/classify_page.py:60-62`,
`engine/shared_xobjects.py:47` (`` `import playa` appears in exactly one file in this repo ``),
`engine/playa_boundary.py:146` (`` there is a test asserting exactly one file imports playa ``
— this line is itself currently **aspirational**, not yet true).

**Call-count half — analog `engine/index.py:139-143`'s own "patchable method" precedent,
already the exact shape RESEARCH.md's Code Examples names**:
```python
    def _parse_page(self, page_index: int) -> PageIndex:
        """The single per-page parse step, factored out as its own patchable method
        (brief ruling 5) so a test can `monkeypatch.setattr` it and assert it runs
        exactly once across two `.page(n)` calls -- the non-vacuous proof that `.page()`
        actually caches rather than re-parsing."""
```
Apply the identical technique to `engine.playa_boundary.open_document` itself: monkeypatch
it to count calls, open one `RunIndex` (1 call), call every new `export_*` function against
that same already-open index, and assert the call count is still 1.

---

### `engine/blocks.py` (NEW — D-7.2)

**No analog exists in this repo for the block-structure inference itself** — say so plainly,
per instructions, rather than forcing a match. This is a genuinely new capability: no prior
phase needed reading-order/heading/list/table inference.

**What DOES have an analog is the module's *shape*** — a pure function taking already-parsed,
already-decoded data (never re-opening a document, never importing `playa`) and returning a
plain, typed verdict. This is `engine/classify_page.py`'s exact contract:

```python
# engine/classify_page.py:143-147 -- the shape to copy: pure function, plain-dataclass
# input, Literal-typed output, no I/O, no playa import.
def classify_page(glyph_records: list[GlyphRecord], page: Page) -> Bucket:
    """One of six buckets, per 02-RESEARCH.md Section 7's threshold table..."""
```

And `engine/index.py`'s `RunIndex`/`PageIndex` is the shape of the THING `engine.blocks`
consumes — a page-at-a-time, already-cached, already-classified source, never re-derived:
```python
# engine/index.py:162-174 -- what engine.blocks iterates over, never re-parses.
def page(self, page_index: int) -> PageIndex:
    """Page `page_index`'s `PageIndex`, from cache if this page was parsed before..."""
```

**Refuse-loudly-never-guess convention to carry into heading/bold/italic detection** — this
project's established idiom (`RunVerdict`/`FontVerdict`/`GlyphVerdict` all carry a named
`reason: str | None`, never a silent default): a block whose type cannot be confidently
inferred should get its own named "reason", not a silent fallback to `paragraph`.

**Per CONTEXT.md A-7.2:** design the output as a plain, renderer-agnostic dataclass (block
type, source `RunRecord`s, computed style attributes) — additive for Phase 8's DOCX writer,
never HTML/Markdown-shaped.

---

### `tests/test_blocks.py` (NEW)

**Analog:** `tests/test_classify.py`'s `_dummy_run` helper — build minimal `RunRecord`/
`GlyphRecord` fixtures in Python, no real PDF needed for the unit-level cases (`corpus`-marked
tests are separate, per VALIDATION.md's `test_heading_detected_from_font_size_ratio` row).

```python
# tests/test_classify.py:444-463 -- construct exactly the fixture a unit test needs,
# nothing more, reusable verbatim for a RunRecord carrying the new font_size_pt field.
def _dummy_run(display_text: str, unicode: str = "A") -> RunRecord:
    from engine.records import GlyphRecord
    from engine.types import CharCode, Unicode

    glyph = GlyphRecord(
        code=CharCode(1), glyph=None, unicode=Unicode(unicode),
        x=0.0, y=0.0, advance=(1.0, 0.0), font_id=0, render_mode=0,
        visible=True, stream_id=0, operator_byte_offset=0,
        item_index_within_tj=None, byte_offset_within_string=0,
    )
    return RunRecord(run_id="dummy", glyphs=[glyph], display_text=display_text, page=0)
```

For the corpus-marked heading test: build (or load, per `tools/build_export_fixtures.py`
above) a fixture with a KNOWN, hand-measured heading:body font-size ratio, and assert the
specific ratio in the test — never an unmeasured threshold.

---

### `engine/export/text.py` (NEW — EXPO-05, plain text)

**Analog:** `tools/pdftool.py::_print_page_runs` — the exact "iterate `RunIndex` pages, read
`RunRecord.display_text`" shape, already proven in this codebase:

```python
# tools/pdftool.py:76-82 -- the shape to copy almost verbatim. Swap "print" for
# "accumulate into a list, join with a page-break separator, return str".
def _print_page_runs(idx: RunIndex, page_number: int) -> None:
    page = idx.page(page_number)
    for run, verdict in page.runs:
        line = f"{run.run_id}  {run.display_text!r}  {verdict.state}"
        if verdict.state == "not_editable" and verdict.reason is not None:
            line += f"  reason={verdict.reason}"
        print(line)
```

**Iterate-every-page shape** (`tools/pdftool.py:57-73`, `_print_summary` — the whole-document
loop form export_text needs):
```python
def _print_summary(idx: RunIndex) -> None:
    ...
    for page_number in range(idx.page_count):
        page = idx.page(page_number)
        ...
```

**No `engine.blocks` dependency** for this file per RESEARCH.md's Recommended Project
Structure — this is the thinnest exporter, `RunRecord.display_text` joined with page breaks,
nothing else.

---

### `engine/export/markdown.py`, `engine/export/html.py` (NEW — EXPO-05)

**Partial analog only** — the consumption shape (open `RunIndex`, call `engine.blocks`, never
re-parse) is exactly `text.py`'s shape above, extended by one more call. **The actual
Markdown/HTML syntax-emission logic has no precedent in this Python codebase** — no
templating library is imported anywhere in `engine/`, and none should be added (Don't
Hand-Roll's own spirit: this is a small, mechanical, block-type-to-markup mapping, not a
templating problem).

Per RESEARCH.md's architecture diagram and D-7.2/A-7.2: both modules must consume the exact
same `engine.blocks` output — html.py must not run its own structure-inference pass. Enforce
this the same way EXPO-05's single-path proof enforces the `RunIndex` rule: a runtime
call-count/object-identity check that `markdown.py` and `html.py` both receive the identical
`list[Block]` from one `engine.blocks` call, not two.

---

### `engine/export/images.py` (NEW — EXPO-01)

**Analog:** `harness/render_diff.py::render_pdfium` — this is not new capability, it is a new
*caller* of an already-CI-validated function. Copy the scale formula exactly, do not
re-derive it:

```python
# harness/render_diff.py:31-32, 36-51 -- the exact formula and shape to reuse.
RENDER_DPI = 150
_SCALE = RENDER_DPI / 72

def render_pdfium(pdf_path: str | Path, page_index: int, output_dir: str | Path) -> Path:
    """Render one page with pypdfium2 (in-process, no subprocess)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"pdfium_p{page_index}.png"

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page = pdf[page_index]
        bitmap = page.render(scale=_SCALE)
        image = bitmap.to_pil()
        image.save(out_path)
    finally:
        pdf.close()

    return out_path
```
D-7.5's two defaults (150 screen / 300 print) are just two different `dpi` values into
`scale = dpi / 72` — same call, parameterized DPI instead of the harness's fixed 150.

**Zip assembly — stdlib only, no analog needed** (Don't Hand-Roll rung 3): `zipfile.ZipFile`,
per RESEARCH.md's own explicit ruling. No third-party zip library is justified.

---

### `engine/export/compress.py` (NEW — EXPO-02)

**Analog for the open/mutate/save/close shape:** `engine/identity_rewrite.py`'s
`identity_rewrite` (`engine/identity_rewrite.py:145-153` region, already read this session):
```python
    pdf = pikepdf.open(pdf_path)
    try:
        for page in pdf.pages:
            ops = pikepdf.parse_content_stream(page)
            new_bytes = pikepdf.unparse_content_stream(ops)
            page.Contents = pdf.make_stream(new_bytes)
        pdf.save(output_path)
    finally:
        pdf.close()
```
Every existing `.save()` call in this codebase (`engine/identity_rewrite.py:152,190`,
`engine/recipe.py:538,714`, `engine/rewrite.py:445` — all confirmed plain `pdf.save(path)`,
grepped this session, no `object_stream_mode`/`recompress_flate` anywhere in `engine/` today)
follows this exact open/try/finally/close shape. `compress.py` is the same shape with two new
keyword arguments on the final `.save()`:

```python
# The two new parameters, verified live against installed pikepdf 10.11.0 this session
# (07-RESEARCH.md Pattern 2) -- not documentation-only.
pdf.save(
    output_path,
    object_stream_mode=pikepdf.ObjectStreamMode.generate,
    recompress_flate=True,
)
```

**Image downsampling (the explicit, lossy, labelled half, D-7.3)** — `Page.get_images(recursive=True)`,
never the deprecated `.images` (it silently skips images inside Form XObjects — exactly the
scanned/invoice-PDF case this codebase already knows matters, per `invoice_book_1842.pdf`'s
Form-XObject-wrapped scan pages seen in `tools/build_mixed_fixture.py`).

---

### `engine/export/split.py` (NEW — EXPO-03, server-side path)

**Analog:** `tools/build_mixed_fixture.py::build_mixed_scanned` — this is not a new recipe,
it is the SAME recipe already used in this codebase to build a fixture, now exposed as an
export:

```python
# tools/build_mixed_fixture.py:93-107 -- literally the split recipe: Pdf.new() +
# pages.append() for a chosen subset, then .save(). split.py is this same shape with
# the page subset coming from a user-supplied range/every-N/bookmark selection instead
# of a hardcoded PAGE_PLAN.
out = pikepdf.Pdf.new()
try:
    for kind, i in PAGE_PLAN:
        out.pages.append(text_src.pages[TEXT_PAGES[i]] if kind == "text" else scan_src.pages[SCAN_PAGES[i]])
    out.save(FIXTURES_DIR / "mixed_scanned.pdf")
finally:
    out.close()
```

**Wave 0 empirical check before calling `remove_unreferenced_resources()`** (VALIDATION.md's
A2 item): verify whether `pikepdf.Pdf.new()` + `dst.pages.append(src_page)` deep-copies
inherited/shared `/Resources` per destination document. This is corpus-testable directly —
no existing probe script does this specifically, but `tools/probe_corpus.py` is this
codebase's established shape for a corpus-driven, ad hoc empirical check script, if the
planner wants a standalone probe rather than folding the check into `tests/test_split.py`
directly.

---

### `engine/export/flatten.py` (NEW — EXPO-04)

**Analog for the shape:** `engine/identity_rewrite.py` (open/mutate/save/close, as above),
with the "mutate" step being a single native call:
```python
pdf.flatten_annotations(mode="all")  # or "screen" / "print" -- verified live this session
```

**Reuse, do not re-derive, reference** (CONTEXT.md's explicit instruction) — the read-side
annotation-appearance geometry this project already has, which `flatten_annotations` performs
the write-side equivalent of:

```python
# engine/playa_boundary.py:451-463 -- _appearance_ctm. READ-ONLY reference: this is
# TEXT-06's read-side geometry (locating text INSIDE an appearance stream). Do not port
# this into flatten.py as a write operation -- pikepdf.Pdf.flatten_annotations() already
# does the write side, in C++, via qpdf.
def _appearance_ctm(stream: ContentStream, rect: Rect, page_ctm: Matrix) -> Matrix:
    """ISO 32000-1 12.5.5's appearance-to-/Rect fit, composed onto the page CTM."""
```

```python
# engine/walker.py:583-598 -- _located_walk's annotation loop, the CONSUMER of
# annotation_appearances() for text-extraction purposes (TEXT-06). Also read-only
# reference -- confirms annotation appearances are already a first-class, already-solved
# concept in this codebase; flatten.py does not need to rediscover what an appearance is.
for annot_index, state, stream, resources, ctm in annotation_appearances(page):
    yield from _walk_level(page, doc, [stream], dataclasses.replace(path, annot=(annot_index, state)), ...)
```

---

### Test files for `engine/export/*` — shared analogs

**`tests/test_export_text.py`** — analog `tests/test_classify.py:444-463`'s `_dummy_run`
(build a minimal `RunIndex`-shaped fixture in Python; no real PDF required for the pure
`display_text`-joining logic).

**`tests/test_export_html.py`** (and its markdown counterpart) — same `_dummy_run` shape,
plus `tests/test_blocks.py`'s block fixtures, since both exporters consume `engine.blocks`
output.

**`tests/test_export_images.py`, `tests/test_compress.py`, `tests/test_split.py`,
`tests/test_flatten.py`** — all four share the SAME validation trio, already proven at
`tests/test_gate_g2a.py`:

```python
# tests/test_gate_g2a.py:317-323 -- the qpdf --check subprocess pattern (split.py,
# flatten.py's own EXPO-03/04 criterion).
result = subprocess.run(
    ["qpdf", "--check", "--warning-exit-0", str(output_path)],
    capture_output=True, timeout=QPDF_CHECK_TIMEOUT_SECONDS,
)
assert result.returncode == 0, f"qpdf --check exited {result.returncode}"
```

```python
# tests/test_gate_g2a.py:333-341 -- masked_pixel_diff, same-engine zero-tolerance
# (compress.py's lossless claim; flatten's/split's "confined to the intended change").
mask = _edited_run_pixel_mask(run, cropbox_height_pt)
orig_pngs = render_all(fixture_path, run.page, tmp_path / "orig")
new_pngs = render_all(output_path, run.page, tmp_path / "new")
for label, orig_png, new_png in zip(_ENGINE_LABELS, orig_pngs, new_pngs):
    diff = masked_pixel_diff(orig_png, new_png, mask=mask)
    assert diff == 0, f"{label}: expected zero pixel diff outside the edited run's box, got {diff}"
```

```python
# tests/test_gate_g2a.py:344-352 -- the cross-engine tolerant pass, reused unmodified
# (D-7.4's second layer, per every split/flatten/compress corpus test).
for pair_label, png_a, png_b in (("pdfium-vs-poppler", ...), ("pdfium-vs-mupdf", ...), ("poppler-vs-mupdf", ...)):
    ok, detail = _cross_engine_pair_ok(pair_label, png_a, png_b)
    assert ok, detail
```

---

### `tests/test_gate_g6.py` (NEW — the phase gate)

**Analog:** `tests/test_gate_g2a.py` / `tests/test_gate_g2b.py` — same "this test IS the
gate" framing, same discipline. Copy the docstring convention directly:

```python
# tests/test_gate_g2a.py:1-6 -- the framing to copy for G6.
"""Gate G2a: the targeted confined-diff proof, end to end on one real edit.

This test IS the gate. It drives the real pipeline built across 03-01..03-07 ...
against a real fixture, one real single-instruction run, and then asserts
all six of G2a's roadmap clauses against that single edit:
"""
```

**T-02-04 convention, restated in both gate files and to be carried into G6** (`tests/test_gate_g2a.py:24-26`,
`tests/test_gate_g2b.py`'s closing paragraph): no assertion message may embed document
content, `new_text`, or `display_text` — counts, booleans, coordinates, engine labels, and
fixture paths only.

---

### `tools/pdftool.py` (MODIFY — add export subcommands)

**Analog:** itself — the `edit` subparser was added beside the original `index` subparser
for exactly this reason, stated in its own docstring:

```python
# tools/pdftool.py:24-27
"""
Implemented as a real `add_subparsers` subcommand structure (not a bare positional-arg
parser) even when only one subcommand existed, per the plan's own phrasing ("one
subcommand") -- this keeps a natural home for future subcommands without a breaking CLI
change later, which is exactly what `edit` now is.
"""
```

```python
# tools/pdftool.py:138-168 -- the subparser-registration shape to copy per new export
# subcommand (e.g. "export-text", "export-images", "compress", "split", "flatten").
subparsers = parser.add_subparsers(dest="command", required=True)

index_parser = subparsers.add_parser("index", help="...")
index_parser.add_argument("pdf_path", help="Path to the PDF file")
index_parser.set_defaults(func=_cmd_index)

edit_parser = subparsers.add_parser("edit", help="...")
edit_parser.add_argument("pdf_path", help="Path to the PDF file")
edit_parser.add_argument("--recipe", required=True, ...)
edit_parser.set_defaults(func=_cmd_edit)
```

**Network-boundary discipline to carry forward** (`tools/pdftool.py:29-32`): "this file must
never import anything that opens a network surface" — still true for every export subcommand
added here; the CLI stays local/filesystem-only, matching PRIV-01/PRIV-03's server-side
isolation model referenced in CONTEXT.md.

---

## Shared Patterns

### Single playa-import-site discipline
**Source:** `engine/playa_boundary.py:1-10` (module docstring), enforced (once
`test_export_single_path.py` exists) by AST scan modeled on `tests/test_rewrite.py:1769-1804`.
**Apply to:** `engine/blocks.py`, every file under `engine/export/` — none may `import playa`
or `from playa import ...`; all must go through an already-open `RunIndex`/`pikepdf.Pdf`.

### RunIndex reuse discipline (no second parse)
**Source:** `engine/index.py:139-174` (`_parse_page`/`page()`'s cache-or-parse shape).
**Apply to:** `engine/export/text.py`, `markdown.py`, `html.py`, `engine/blocks.py` — every
one of these takes an already-constructed `RunIndex` as a parameter; none constructs its own.

### pikepdf open/mutate/save/close shape
**Source:** `engine/identity_rewrite.py:145-153`, repeated at `engine/recipe.py:538,714`,
`engine/rewrite.py:445`.
**Apply to:** `engine/export/compress.py`, `split.py`, `flatten.py` — `pdf = pikepdf.open(...)`,
`try: ... finally: pdf.close()`, one `.save()` call at the end.

### Refuse loudly, never guess (named `reason`, never a silent default)
**Source:** `FontVerdict`/`GlyphVerdict`/`RunVerdict` (`engine/encoding_table.py:125-152`,
`engine/classify_run.py:70-79`) — every refusal carries a distinct, named string reason.
**Apply to:** `engine/blocks.py`'s heading/list/table detection (a block whose type cannot be
confidently inferred should say so, not silently default to `paragraph`), and every export
module's own input-bounds refusals (DPI out of range, split range past the last page — per
RESEARCH.md's Security Domain, matching `engine/index.py`'s own `MAX_DOCUMENT_GLYPHS`-style
named-ceiling precedent).

### T-02-04: never put document content in an assertion/log message
**Source:** stated and followed throughout `tests/test_gate_g2a.py:24-26`,
`tests/test_gate_g2b.py`, `engine/index.py:82-84` (`DocumentTooLargeError`'s own docstring:
"Never document content in the message -- counts only").
**Apply to:** every new test file, and every refusal message any `engine/export/*` module
produces.

### Cross-engine + same-engine two-layer validation
**Source:** `harness/masked_diff.py::masked_pixel_diff` (same-engine, zero-tolerance) +
`harness/run_corpus_harness.py:124-144`'s `_cross_engine_pair_ok` (cross-engine, tolerant,
blur-then-threshold) + `harness/render_diff.py::render_all` (drives all three engines).
**Apply to:** `tests/test_compress.py`, `test_split.py`, `test_flatten.py`, `test_gate_g6.py` —
D-7.4's validation is this exact, already-tuned machinery reused unmodified, never a new
comparison primitive.

---

## No Analog Found

| File / Concern | Role | Data Flow | Reason |
|---|---|---|---|
| `engine/blocks.py`'s actual clustering heuristics (heading-vs-body font-size ratio, list/table-row grouping) | service | transform | Genuinely new domain logic — no prior phase needed reading-order inference. The MODULE SHAPE has an analog (`engine/classify_page.py`, see above); the HEURISTICS do not. RESEARCH.md flags the exact thresholds as MEDIUM confidence / Assumption A4, corpus-measurement work for the planner, not a transcription job |
| `engine/export/markdown.py` / `html.py`'s syntax-emission logic (the actual Markdown/HTML markup generation) | service | transform | No templating or markup-generation code exists anywhere in this Python codebase today. Small and mechanical per Don't Hand-Roll's own spirit — do not add a templating dependency for this |
| Client-side zip assembly (any `client/src/...` file) | component | file-I/O | Explicitly deferred by CONTEXT.md's own A-7.3 ruling: "decided with the PNG-export tier, not independently... Lock the export tier first." Not this pattern-mapping pass's job to guess a shape for |
| Any HTTP route/endpoint wiring the export modules to a request | route | request-response | Confirmed this session: no `server/`, `api/`, or `client/` directory exists yet in this worktree. Phase 4's server/session-handle shape and PRIV-01 disclosure mechanism are named in RESEARCH.md's own Environment Availability table as "✗ — Phase 4 not yet built... a genuine interface dependency, not a fallback-able one" — treat as an interface requirement to verify against Phase 4's actual shipped shape at plan time, not a file to pattern-map against a guess |

---

## Metadata

**Analog search scope:** `engine/`, `tools/`, `harness/`, `tests/` (all `.py` files); `pyproject.toml`;
confirmed via `find` this session that no `server/`, `api/`, or `client/` directory exists in
this worktree, and no `engine/blocks.py` or `engine/export/` package exists yet.
**Files scanned (read in full or via targeted, non-overlapping ranges):** `engine/records.py`,
`engine/types.py`, `engine/clusterer.py`, `engine/index.py`, `engine/classify_run.py`,
`engine/classify_page.py`, `engine/encoding_table.py` (targeted), `engine/walker.py`,
`engine/playa_boundary.py` (targeted), `engine/shared_xobjects.py` (targeted),
`engine/space_threshold.py` (targeted), `engine/identity_rewrite.py` (targeted),
`engine/recipe.py` (targeted), `engine/rewrite.py` (targeted), `engine/fonts.py` (targeted),
`harness/render_diff.py`, `harness/masked_diff.py`, `harness/run_corpus_harness.py` (targeted),
`tools/build_mixed_fixture.py`, `tools/pdftool.py`, `tests/conftest.py`, `tests/test_gate_g2a.py`,
`tests/test_gate_g2b.py` (header only), `tests/test_classify.py` (targeted),
`tests/test_rewrite.py` (targeted), `pyproject.toml`, `CLAUDE.md` (Conventions/Architecture/
Skills sections — no project-specific conventions or skills established yet beyond this
codebase's own established idioms, which this document transcribes directly from source).
**Pattern extraction date:** 2026-08-30
