# Phase 7: Exports - Research

**Researched:** 2026-08-30
**Domain:** Multi-format PDF export (raster images, compress, split, flatten) + text-derived
formats (plain text, Markdown, HTML) built on the Phase 2 run index
**Confidence:** HIGH on the raster/compress/split/flatten stack (already-pinned, already-verified
libraries with new API surface confirmed live this session). MEDIUM on the block-structure layer's
exact heading/table heuristics (the architecture and the required index extension are established;
the clustering thresholds are not yet corpus-measured — flagged as an Assumption/Open Question, not
asserted as fact).

## Summary

Phase 7 has one already-solved half and one genuinely new piece of engineering. The already-solved
half — page images, compress, split, flatten — is exactly what `.planning/research/STACK.md` scoped
it to be: `pypdfium2` and `pikepdf` (both already pinned, already imported, already proven correct on
the corpus by Phase 1's harness) cover all four with **native APIs verified live this session that
the codebase does not yet call**: `pikepdf.Pdf.flatten_annotations(mode=...)` (flatten, in C++ via
qpdf — do not hand-roll the annotation-appearance-to-page-content compositing math a second time),
and `pikepdf.Pdf.save(object_stream_mode=ObjectStreamMode.generate, recompress_flate=True)` (compress
— both parameters exist, are documented, and are simply unused by any `.save()` call in the repo
today). `pypdfium2`'s `page.render(scale=DPI/72)` is the exact call `harness/render_diff.py`'s
`render_pdfium()` already makes for the CI harness — Phase 7's PNG/JPEG export is the same call with
a new caller, not new capability.

The genuinely new piece is the reading-order/block-structure layer D-7.2 requires, and it exposes a
real gap in the Phase 2 run index that has not been visible until now: **`RunRecord` (the object
`engine.index.RunIndex.page()` returns and the only thing an export can honestly consume without
opening a second parse) carries no font size and no font identity.** Font size lived transiently in
`ClusterAttrs.effective_em` during clustering (`engine/clusterer.py:127`, `:152`) and is discarded the
moment `RunRecord` is built (`engine/clusterer.py:308-315`); `GlyphRecord.font_id` is an *opaque,
per-page-interned integer with no reverse lookup to a `/BaseFont` name* — verified directly by reading
`engine/classify_run.py:23-24` and `engine/walker.py:282`. Font-size-clustering headings and
bold/italic detection (Phase 8's own named ceiling, which this layer must be built *to*, per D-7.2)
are structurally impossible against the index as it exists today. This is not a defect — Phase 2 never
needed either field — but it is exactly the situation D-7.1 anticipates ("a planner that discovers the
index lacks something Markdown needs should plan to extend the index, never to bypass it"), and the
extension is small, additive, and precisely scoped below (Architecture Patterns, Pattern 1).

The single-extraction-path rule (EXPO-05 / ROADMAP criterion 1) turns out to rest on a convention that
is currently **enforced only by module docstrings, not by any test** — `engine/clusterer.py:10`,
`engine/classify_page.py:60-62`, and `engine/shared_xobjects.py:47` all assert "import playa appears
in exactly one file in this repo" in prose, but `grep -rn "import playa" tests/` shows only test
fixtures importing it directly (permitted), and no test enforces the production-code half of the
claim. Phase 7 should both close this pre-existing gap (cheap, protects the whole codebase, not just
exports) and add the export-specific version of it (Pattern 5 / Code Examples below) — a call-count
monkeypatch proof modeled directly on `engine/index.py:139-143`'s own "patchable method... so a test
can monkeypatch.setattr it and assert it runs exactly once" precedent.

**Primary recommendation:** Build every text-derived export (EXPO-05) as a pure function over an
already-open `RunIndex`, never a new parse; extend `RunRecord`/`PageIndex` with the three fields the
block-structure layer needs (font size, font identity/style, page geometry) as a Wave-0 index task
before any export module is written; use `pikepdf.Pdf.flatten_annotations()` and
`pikepdf.Pdf.save(object_stream_mode=..., recompress_flate=True)` for flatten and compress rather than
hand-rolling either; keep PNG/JPEG page export and split as strong client-side candidates (zero
server round trip, matching the PAGE-09/PRIV-01 precedent already locked for Phase 6) and keep
text/Markdown/HTML and compress/flatten server-side by construction (they need the Python-only run
index or pikepdf's C++ object layer, neither of which has a browser equivalent).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Plain text / Markdown / HTML export | API/Backend (Engine, Python) | — | Consumes `engine.index.RunIndex`, which is Python-only; no browser equivalent exists or should exist (D-7.1: one extraction path) |
| Block-structure / reading-order layer (D-7.2) | API/Backend (Engine, Python) | — | Reads the same `RunRecord`/`PageIndex` data the text exports do; must be one module, reused by both this phase's HTML/Markdown and Phase 8's DOCX (D-7.2's own "reusable artifact" framing) |
| PNG/JPEG page image export | Browser/Client (candidate) | API/Backend (fallback) | pdf.js is already loaded for VIEW-01 and already rasterizes every page at a chosen scale; `canvas.toBlob()` at `scale = DPI/72` is the same formula `harness/render_diff.py:37` uses server-side. Strongest PRIV-01 claim if done client-side; server (`pypdfium2`) remains the correct fallback if client-side output must byte-match server-validated renders |
| Split | Browser/Client (candidate) | API/Backend (fallback) | Whole-page copy, zero content-stream rewrite — exactly `@cantoo/pdf-lib`'s documented strength (STACK.md's REWRITE-vs-APPEND table) and exactly PAGE-09's "page ops never touch the server" pattern, extended to an export |
| Compress | API/Backend (Engine, Python) | — | Object-stream packing/recompression is a `pikepdf`/qpdf capability with no browser equivalent; `@cantoo/pdf-lib` is append-only (STACK.md), not a rewrite/recompress engine |
| Flatten | API/Backend (Engine, Python) | — | `pikepdf.Pdf.flatten_annotations()` is a verified, already-available, already-correct native operation; re-deriving the annotation-appearance compositing math client-side duplicates work `qpdf` already does more robustly, and D-7.4 gates flatten on the same server-side CI harness (`qpdf --check` + 3-engine masked diff) compress and split already use |
| PRIV-01 per-operation disclosure | Frontend Server / Browser (UI) | — | Not Phase 7's code to build — Phase 7's job is to make each operation's tier assignment above match what Phase 4 ships as the disclosure mechanism, never a separately hand-maintained label |

## Standard Stack

### Core (already pinned — verified installed, matches `pyproject.toml` exactly; zero new runtime
packages this phase)

| Library | Pinned | Installed (verified) | New capability this phase uses |
|---------|--------|----------------------|-------------------------------|
| pikepdf | 10.11.0 | 10.11.0 `[VERIFIED: uv run python -c "import pikepdf; print(pikepdf.__version__)"]` | `Pdf.flatten_annotations(mode=...)`, `Pdf.save(object_stream_mode=..., recompress_flate=...)`, `Pdf.remove_unreferenced_resources()`, `Object.write(data, filter=...)`, `Page.get_images(recursive=True)`, `PdfImage.as_pil_image()` — all confirmed present via `dir()`/`help()` against the installed package this session; none is called anywhere in `engine/` today (`grep -rn "flatten_annotations\|object_stream_mode\|recompress_flate" engine/` returns nothing) |
| pypdfium2 | 5.12.1 | 5.12.1 `[VERIFIED]` | `page.render(scale=DPI/72)` — already proven correct and already the exact call `harness/render_diff.py:37-39` makes; new caller, not new capability |
| Pillow | 12.3.0 | 12.3.0 `[VERIFIED]` | Image re-encode/downsample for compress's image-XObject path (`Image.open`/`.resize`/`.save(..., quality=...)`), and the existing `ImageChops`-based diff machinery in `harness/masked_diff.py` for validation reuse |
| Python | ≥3.13 | 3.13.7 `[VERIFIED]` | — |
| `zipfile` (stdlib) | — | — | All-pages-as-zip assembly (EXPO-01's "per-page or all pages as a zip"). No third-party zip library is justified — this is exactly the "stdlib does it" rung, and the ladder stops there |

**No new runtime dependency is introduced by this phase.** `tools/license_gate.py` was re-run this
session against the current environment as a sanity check (not because this phase changes the
dependency set, but to confirm the baseline it inherits is clean before adding server-side compress/
flatten code that touches the object layer more deeply than any code has so far):
`[VERIFIED: uv run --frozen python3 tools/license_gate.py` → `"license_gate: no AGPL/Affero licensed
distributions found"`, exit 0`]`.

### Supporting — new to this phase (client-side only, if the client-side candidates in the
Architectural Responsibility Map are taken)

| Library | Version | License | Purpose | Verification |
|---------|---------|---------|---------|---------------|
| `@cantoo/pdf-lib` | 2.8.1 (already pinned in STACK.md/CLAUDE.md for Phase 4/6) | MIT | Client-side split (whole-page copy) | Not newly introduced by Phase 7 — already the pinned page-ops library; Phase 7 is a new *caller*, same as Phase 6's page-ops work. No separate legitimacy audit needed; already covered by Phase 3/CLAUDE.md's pinned-stack provenance |
| pdf.js canvas rendering | 6.2.108 (already pinned) | Apache-2.0 | Client-side PNG/JPEG page export | Same status — already the pinned viewer library (VIEW-01); `page.render({viewport})` + `canvas.toBlob()` is a documented pdf.js API, not a new dependency |

### Alternatives Considered

| Instead of | Could use | Tradeoff |
|------------|-----------|----------|
| `pikepdf.Pdf.flatten_annotations()` | Hand-rolled compositing of each `/AP /N` appearance stream onto page content, reusing `engine.playa_boundary._appearance_ctm`'s read-side geometry | Rejected: `_appearance_ctm` (`engine/playa_boundary.py:451`) computes the `/Matrix x A x page.ctm` transform for **locating text inside** an appearance stream (TEXT-06, a read-only concern) — it does not write anything. Re-deriving the same Rect-to-BBox fit math as a *write*-side operation duplicates qpdf's own C++ implementation of the identical ISO 32000-1 §12.5.5 algorithm, for no capability gain, and risks a second, subtly different geometry engine in the same codebase. Use the native method; keep the walker's geometry as the read-side reference only |
| `pikepdf.Pdf.save(object_stream_mode=ObjectStreamMode.generate, recompress_flate=True)` | Shelling out to Ghostscript's `-dCompressPages`/`-dPDFSETTINGS` | Rejected outright by CLAUDE.md's licensing constraint (Ghostscript is Artifex AGPL) — STACK.md already names this exact substitution ("pikepdf + Pillow (compress)... Replaces the Ghostscript you cannot use") |
| Client-side PNG/JPEG export via pdf.js canvas | Server-side via `pypdfium2` (matching what CI's masked-diff harness validated) | Real tradeoff, not a clear win either way: pdf.js and pdfium are measured (this session, `harness/run_corpus_harness.py:6-14`) to disagree by up to 7.2% pixel delta from antialiasing/gamma differences alone. A client-exported PNG is WYSIWYG against what the user is already looking at (arguably *more* correct for an export named "what you see"), but it is a different rasterizer than the one Gate G2a/G2b's own correctness claims are measured against. Recommend client-side for the privacy/speed win, but flag this tradeoff explicitly for the planner/discuss-phase rather than deciding it silently |
| Client-side split via `@cantoo/pdf-lib` | Server-side via `pikepdf.Pdf.new()` + `dst.pages.append(...)` (STACK.md: "PDF split / merge / rotate — Excellent — qpdf preserves everything it doesn't touch") | Real tradeoff: server-side split gets D-7.4's qpdf-based validation for free and is a ~5-line pikepdf recipe (STACK.md's own top-level use case for the library); client-side split gets PAGE-09-class zero-upload privacy. Both are legitimate; Claude's Discretion per CONTEXT.md. This research recommends client-side for the privacy win but flags that D-7.4's "passes `qpdf --check`" criterion is easiest to satisfy if the *output bytes* are produced server-side, or if the client-side output is round-tripped through a server-side `qpdf --check` as a post-hoc validation step (not full processing) before the CI gate can claim it |

## Package Legitimacy Audit

No new runtime packages. `pikepdf`, `pypdfium2`, and `Pillow` were audited and approved in Phase 3's
own research (`03-RESEARCH.md`'s Package Legitimacy Audit) and re-verified installed and clean of
AGPL this session (`tools/license_gate.py`, exit 0). `@cantoo/pdf-lib` and `pdfjs-dist` are already
pinned client dependencies from CLAUDE.md's stack section, not new introductions.

| Package | Registry | Disposition |
|---------|----------|-------------|
| pikepdf | PyPI | Approved (Phase 3 audit, re-verified clean this session) |
| pypdfium2 | PyPI | Approved (Phase 3 audit, re-verified clean this session) |
| Pillow | PyPI | Approved (Phase 3 audit, re-verified clean this session) |
| `@cantoo/pdf-lib` | npm | Already pinned (CLAUDE.md stack section), not newly introduced |
| pdfjs-dist | npm | Already pinned (CLAUDE.md stack section), not newly introduced |

**Packages removed due to slopcheck [SLOP] verdict:** none — no new packages to check.
**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
                         RunIndex(path)  [Phase 2, engine/index.py -- already open,
                              |            already caching per page; opened EXACTLY
                              |            ONCE per session, by whichever tier holds
                              |            the document]
                              |
         +--------------------+--------------------+----------------------+
         |                    |                     |                      |
   idx.page(n)          idx.page(n)           pikepdf.Pdf handle    pypdfium2.PdfDocument
   for n in range(       for n in range(        (same bytes,          (same bytes,
   page_count)            page_count)            server-side)          server or client)
         |                    |                     |                      |
         v                    v                     v                      v
  +-------------+     +---------------+     +----------------+     +------------------+
  | TEXT export  |     | BLOCK-        |     | COMPRESS        |     | PAGE IMAGE       |
  | (plain text) |     | STRUCTURE     |     | pdf.save(       |     | export           |
  |              |     | LAYER (NEW,   |     |  object_stream_ |     | page.render(     |
  | join         |     | D-7.2)        |     |  mode=generate, |     |  scale=DPI/72)   |
  | RunRecord.   |     |                |     |  recompress_    |     | -> PNG/JPEG,     |
  | display_text |     | groups runs   |     |  flate=True)    |     | per-page or zip  |
  | per page,    |     | into blocks   |     | + Pillow        |     |                  |
  | page breaks  |     | (heading /    |     | downsample      |     | CANDIDATE:       |
  +------+-------+     | paragraph /   |     | image XObjects  |     | client-side via  |
         |              | list) using   |     | (labelled,      |     | pdf.js canvas,   |
         |              | the NEW       |     | explicit choice)|     | zero upload      |
         |              | font_size_pt/ |     +--------+--------+     +--------+---------+
         |              | style fields  |              |                       |
         |              | (extension    |              v                       v
         |              | below)        |     +----------------+     +------------------+
         |              +-------+-------+     | FLATTEN         |     | SPLIT             |
         |                      |              | pdf.flatten_    |     | CANDIDATE:        |
         |          +-----------+-----------+  | annotations(    |     | client-side via   |
         |          |                       |  |  mode=...)      |     | @cantoo/pdf-lib   |
         |          v                       v  | -- native,      |     | (whole-page copy, |
         |    +-----------+          +-----------+ never hand-    |     | no content-stream |
         |    | MARKDOWN   |          |  HTML     | rolled        |     | rewrite needed)   |
         |    | export     |          | export    +--------+------+     +---------+---------+
         |    +-----+------+          +-----+-----+          |                    |
         |          |                        |                v                    v
         v          v                        v         D-7.4 VALIDATION:    D-7.4 VALIDATION:
   +---------------------------+             |         qpdf --check +      qpdf --check +
   | EXPO-05 single-path gate:  |             |         masked_pixel_diff   masked_pixel_diff
   | every one of these three   |             |         (mask = union of   (mask = None, per
   | boxes must resolve to      |             |         flattened Rects)   retained page) in
   | ZERO additional            |             |         in 3 engines       3 engines
   | engine.playa_boundary.     |             |         (harness/ reused)  (harness/ reused)
   | open_document() calls      |             |
   | beyond RunIndex's own one  |             |
   | (Code Examples below)      |             |
   +---------------------------+             |
                                              v
                                    (HTML reuses the SAME
                                     block-structure layer
                                     as Markdown -- one
                                     module, two renderers,
                                     never two structure
                                     inference passes)
```

### Recommended Project Structure

No `engine/export*` module exists yet (`find . -iname "*export*"` under `engine/`/`tools/` returns
nothing — this is greenfield within an established codebase, not a new codebase). Follow the
established one-module-one-concern pattern (`engine/classify_run.py` vs `encoding_table.py` vs
`clusterer.py`):

```
engine/
├── blocks.py          # NEW. D-7.2's own module, per CONTEXT.md's explicit instruction
│                       # ("Plan it as its own module with its own tests"). Consumes
│                       # RunIndex pages, groups RunRecords into Block objects (heading/
│                       # paragraph/list/table-row) using the extended font_size_pt/style
│                       # fields (Pattern 1). Imports nothing from engine/export/*; is
│                       # imported BY engine/export/markdown.py, engine/export/html.py,
│                       # and (Phase 8) the DOCX writer -- this is the "reusable artifact"
│                       # D-7.2 names.
├── export/
│   ├── text.py         # NEW. EXPO-05 plain text. Thinnest exporter: RunRecord.display_text
│   │                    # joined with page breaks. No engine.blocks dependency.
│   ├── markdown.py      # NEW. EXPO-05 Markdown. Consumes engine.blocks output.
│   ├── html.py           # NEW. EXPO-05 HTML. Consumes engine.blocks output -- SAME
│   │                    # Block objects markdown.py consumes, never a second structure pass.
│   ├── images.py         # NEW. EXPO-01, server-side fallback path. pypdfium2 render + zip
│   │                    # assembly (stdlib zipfile).
│   ├── compress.py       # NEW. EXPO-02. pikepdf object-stream/recompress + Pillow
│   │                    # downsample, per Pattern 2/3 below.
│   ├── split.py           # NEW. EXPO-03, server-side fallback path. pikepdf page-copy
│   │                    # recipe (Alternatives Considered).
│   └── flatten.py         # NEW. EXPO-04. pikepdf.Pdf.flatten_annotations() wrapper +
│                        # D-7.4's masked-diff validation harness call.
├── index.py             # EXISTING. RunIndex/PageIndex -- EXTENDED per Pattern 1 (new
│                        # fields, no signature break -- see below).
├── clusterer.py           # EXISTING. RunRecord construction -- EXTENDED at
│                        # `_emit_logical_run` (line 308) to populate the new fields.
├── records.py             # EXISTING. RunRecord -- EXTENDED (additive fields; NOT
│                        # frozen/slots, see Pattern 1's sizing note).
└── encoding_table.py      # EXISTING. FontVerdict -- candidate site for a `base_font`
                          # field if Pattern 1's font-identity extension is threaded
                          # through here rather than around it (see Pattern 1).
```

### Pattern 1: The index extension D-7.2 requires — font size and font identity are not on `RunRecord` today

**What's missing, verified by reading the actual code, not assumed:**

`RunRecord` (`engine/records.py:65-70`) carries exactly `run_id`, `glyphs`, `display_text`, `page`.
Font size is computed as `ClusterAttrs.effective_em` during clustering
(`engine/records.py:36-62`'s own docstring: *"effective_em is `space_threshold.effective_em(text_obj)`
... Constant across one text-showing operator's glyphs"*) and is available at exactly the point
`RunRecord` is constructed — `engine/clusterer.py:308-315`'s `_emit_logical_run` already has
`frag: list[_GlyphItem]` where each item is `(GlyphRecord, ClusterAttrs)` — but `ClusterAttrs` is
never read when building the `RunRecord`, and no field carries it forward. Separately,
`GlyphRecord.font_id` (`engine/records.py:27`) is, by its own docstring
(`engine/classify_run.py:23-24`), *"an opaque integer, interned fresh per page walk... there is no
route from it back to a pikepdf font dict."* The actual `font_dict` (which has `/BaseFont` and, via
its `/FontDescriptor`, `/Flags` and `/ItalicAngle`) **is** resolved, once per run, inside
`classify_run._resolve_font_for_glyph` (`engine/classify_run.py:138-158`) — but only to build a
`FontVerdict` (`branch_id`, `editable`, `substitution`, `reason` — `engine/encoding_table.py:125-137`)
that says nothing about size, weight, or style, and the `font_dict` itself is discarded once
`resolve_font()` returns.

**Why this matters for D-7.2 specifically:** Phase 8's own scope ceiling — the bar D-7.2 says to plan
to — names "headings by font-size clustering" and "bold/italic" as in-scope. Both require exactly the
two fields identified above. Building the block-structure layer against `RunRecord` as it exists today
is structurally impossible for those two capabilities; this is not a tuning problem, it is a missing
field.

**The extension (small, additive, two touch points):**

1. **`RunRecord` gains `font_size_pt: float`** (not `effective_em` renamed — `effective_em` is a
   device-space quantity folding in `Tfs`, `Tz/100`, and CTM/Tm scale per
   `engine/space_threshold.py:118-122`'s own docstring; the block-structure layer wants the same
   *relative* ordering signal effective_em already gives font-size clustering, so passing
   `effective_em` through under an honestly-scoped name, or computing true unscaled `Tfs` separately,
   is Claude's Discretion — but the *value must exist on RunRecord*, whichever it is). `RunRecord` is
   a plain `@dataclass` (`engine/records.py:65`), **not** `frozen=True, slots=True` like
   `GlyphRecord`/`ClusterAttrs` — this is a cheap, compatible field addition, not a locked-shape
   change like TEXT-02's 13-field `GlyphRecord` lock.
   Populate it in `_emit_logical_run` (`engine/clusterer.py:308-315`) from `frag[0][1].effective_em`
   (the fragment's own first glyph's `ClusterAttrs` — already in scope at that exact line, just
   unread today).

2. **`RunRecord` gains font-identity fields for bold/italic detection** — recommend
   `base_font: str | None` plus deriving bold/italic from `/FontDescriptor /Flags` (bit 6,
   `ForceBold`) and `/ItalicAngle != 0` (more principled than string-matching "Bold"/"Italic" in the
   BaseFont name, though the corpus-measured BaseFont survey from `03-RESEARCH.md` Pitfall 10 shows
   name-matching would also work as a fallback for fonts with no descriptor). The cleanest touch
   point is `FontVerdict` (`engine/encoding_table.py:125-137`) — it is already resolved once per run
   at exactly the point `font_dict` is in hand (`_resolve_font_for_glyph`,
   `engine/classify_run.py:138-158`) and is already threaded through to `classify_run`'s caller.
   Adding `base_font: str | None = None` (default preserves every existing positional-and-keyword
   `FontVerdict(...)` construction site — verified additive, not breaking) and reading it once in
   `_resolve_font_for_glyph` from `font_dict.get("/BaseFont")` is the smallest diff. Bold/italic can
   then be derived in `engine.blocks` from `base_font` + the `/FontDescriptor` flags at the same
   point, or precomputed into two more `FontVerdict` booleans — sizing this precisely (which layer
   derives bold/italic vs. which just carries the raw signal) is Claude's Discretion for the planner.

3. **`PageIndex` gains page geometry** (`page_width_pt`, `page_height_pt`) for column-count heuristics.
   Cheap: `classify_page.py`'s own CropBox-based signal-1 clipping check (`engine/classify_page.py:14-19`)
   already resolves the page's CropBox for an unrelated reason at exactly the point `PageIndex` is
   built (`engine/index.py:139-160`'s `_parse_page`) — the same rect is one more field, not a new
   parse.

**Sizing for the planner:** this is a Wave-0-shaped task (extend `RunRecord`/`PageIndex`/
`FontVerdict`, thread the three new values through three existing call sites, add regression tests
pinning the new fields on a hand-picked corpus fixture with a known heading/body-text size ratio) that
must land **before** `engine.blocks` (D-7.2's own module) can be written at all — every export module
in the Recommended Project Structure above that isn't `text.py` depends on it transitively.

### Pattern 2: Compress — lossless/structural via `pikepdf.Pdf.save()`, verified live this session

```python
# Source: this session's direct introspection of the installed pikepdf 10.11.0 package
# (`inspect.signature(pikepdf.Pdf.save)`, `help(pikepdf.ObjectStreamMode)`), cross-checked
# against no `.save()` call anywhere in engine/ currently passing these parameters.
import pikepdf

with pikepdf.open(input_path) as pdf:
    pdf.save(
        output_path,
        object_stream_mode=pikepdf.ObjectStreamMode.generate,  # packs loose objects into
                                                                  # compressed object streams
        recompress_flate=True,        # default is False (preserve encoding as-is) --
                                        # True re-runs zlib at max compression on every
                                        # Flate-encoded stream, structural and lossless
        compress_streams=True,        # already pikepdf's own default; explicit here for
                                        # clarity, not a behavior change
    )
```

This alone is D-7.3's "lossless and structural by default" compress path, with **zero new
dependencies and zero hand-rolled object-graph code** — it is a parameter change on a `save()` call
this codebase already makes five times (`engine/identity_rewrite.py:152,190`, `engine/recipe.py:538,714`,
`engine/rewrite.py:445`). `[VERIFIED: live introspection this session, not documentation-only —
the parameter names, defaults, and enum members shown above were read directly off the installed
package]`.

### Pattern 3: Image downsampling — the explicit, labelled, lossy path (D-7.3's second half)

```python
# Source: this session's direct introspection (`dir(pikepdf.Object)`, `help(pikepdf.Object.write)`,
# `dir(pikepdf.PdfImage)`) -- pikepdf.PdfImage has as_pil_image() for reading; there is no
# .replace() method, so the write-back is via the underlying stream Object's own .write().
import io
import pikepdf
from PIL import Image

with pikepdf.open(input_path) as pdf:
    for page in pdf.pages:
        for name, image_obj in page.get_images(recursive=True).items():  # recurses into
                                                                            # Form XObjects
                                                                            # by default --
                                                                            # the deprecated
                                                                            # `.images`
                                                                            # property does not
            pdf_image = pikepdf.PdfImage(image_obj)
            pil_image = pdf_image.as_pil_image()
            pil_image = pil_image.resize(downsampled_size)          # the labelled, lossy step
            buf = io.BytesIO()
            pil_image.save(buf, format="JPEG", quality=downsample_quality)
            image_obj.write(buf.getvalue(), filter=pikepdf.Name("/DCTDecode"))
    pdf.save(output_path, recompress_flate=True)
```

`Page.get_images(recursive=True)` is a documented pikepdf method (its own docstring, fetched via
`help()` this session, warns explicitly: *"images referenced directly by the page... silently omits
images nested inside form XObjects"* is what the **deprecated** `.images` property does — use
`get_images(recursive=True)`, not `.images`, or this compress path will silently skip exactly the
images most real-world scanned/invoice PDFs draw through a Form XObject wrapper).

### Pattern 4: Flatten — the native operation, and D-7.4's precise "confined to the intended change" definition

**Don't hand-roll:** `pikepdf.Pdf.flatten_annotations(mode='all' | 'screen' | 'print')` — verified via
its live `help()` output this session (`flatten_annotations(self, mode: str = 'all') -> None`) and
corroborated via the pikepdf docs `[CITED: pikepdf.readthedocs.io/en/latest/api/main.html]`: *"'all'
flattens all except those marked /NoView"*, *"'screen' flattens annotations excluding those marked
/NoView"*, *"'print' flattens only those marked for printing"*. It "burns into regular content"
markup, comments, highlights, and **form field data** (interactive form values become permanent page
content) — the same operation `engine.playa_boundary.annotation_appearances()`'s read-side geometry
(`_appearance_ctm`, `engine/playa_boundary.py:451-463`) already proves correct for *locating* text
inside; this native method performs the equivalent *write*.

**The precise, assertable definition of "confined to the intended change" (D-7.4):**

The intended change for flatten is: every annotation's own `/Rect`, transformed to device pixel
coordinates at the render DPI used for validation, becomes potentially different pixels; everywhere
else on the page must be byte-for-byte the same rendered image as before. Concretely:

```python
# mask = union of every flattened annotation's /Rect, transformed to device pixels at
# the harness's own RENDER_DPI (harness/render_diff.py:24, already 150) -- reusing the
# SAME masked_pixel_diff primitive G2a/G2b already use for the analogous "confined to
# the edited run" claim, not a new comparison function.
from harness.masked_diff import masked_pixel_diff

annotation_rects_px = [device_rect(annot.rect, page_ctm, RENDER_DPI) for annot in flattened_annots]
mask = union_bbox(annotation_rects_px)  # a single (left, top, right, bottom) covering all of them
diff_count = masked_pixel_diff(before_png, after_png, mask=mask)
assert diff_count == 0   # same-engine, zero-tolerance, everywhere OUTSIDE the mask
```

Then, separately, run the existing cross-engine tolerant comparison
(`harness/run_corpus_harness.py::_cross_engine_pair_ok`, 8% threshold) on the flattened output in all
three engines, plus `qpdf --check` — this is the exact same two-layer shape (same-engine zero-
tolerance / cross-engine tolerant) `03-RESEARCH.md` already established for G2a/G2b, applied to a
different mask.

### Pattern 5: The EXPO-05 single-extraction-path proof — generalizing an unenforced convention

The "only `engine/playa_boundary.py` may `import playa`" rule is real and consistently followed
(`grep -rn "import playa" engine/` returns nothing outside `playa_boundary.py`, verified this
session), but it is currently enforced by docstring discipline only — no test asserts it. Two
complementary, cheap tests close this for the whole codebase and specifically for exports (Code
Examples below has the runnable versions):

1. A static AST scan asserting no file under `engine/` other than `playa_boundary.py` contains a
   `playa` import — generalizes the existing convention into an actual CI gate, protecting every
   future module, not just this phase's.
2. A call-count monkeypatch on `engine.playa_boundary.open_document`, modeled directly on
   `engine/index.py:139-143`'s own precedent (*"a test can `monkeypatch.setattr` it and assert it
   runs exactly once across two `.page(n)` calls"*) — proves at runtime that calling `export_text`/
   `export_markdown`/`export_html` against an already-open `RunIndex` triggers **zero** additional
   parses, not just that no source file happens to contain the string `"import playa"`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Object-stream packing / stream recompression | A manual pass rewriting the xref/object-stream layer | `pikepdf.Pdf.save(object_stream_mode=ObjectStreamMode.generate, recompress_flate=True)` | Verified live this session: both parameters exist, are documented, and this is exactly qpdf's own job — Pitfall 8 (03-RESEARCH.md's own precedent, inherited from 02-RESEARCH.md's Pitfall 8) already establishes "do not hand-serialize PDF structure" as this codebase's standing rule |
| Annotation-appearance-to-page-content compositing (flatten) | Re-deriving the `/Matrix x A x page.ctm` fit transform as a *write*-side operation | `pikepdf.Pdf.flatten_annotations(mode=...)` | The read-side version of this exact geometry (`engine.playa_boundary._appearance_ctm`) already exists for TEXT-06; qpdf's C++ implementation of the write side is the authoritative one to trust, per CONTEXT.md's own "reuse rather than re-derive" instruction |
| Page rasterization at a chosen DPI | A second rendering pipeline for export, distinct from the CI harness's | `pypdfium2` `page.render(scale=DPI/72)` (server) or pdf.js `page.render({viewport})` (client) | Both are the exact calls already used for VIEW-01 (client) and `harness/render_diff.py` (server) — a *third* rasterization code path is the thing to avoid, not a missing capability |
| All-pages-as-zip assembly | A new dependency for zip creation | stdlib `zipfile.ZipFile` | Ladder rung 3 (stdlib does it) — no library on earth does this job better than 4 lines of `zipfile` |
| Cross-engine / same-engine render validation for split/flatten (D-7.4) | A new validator | `harness/masked_diff.py::masked_pixel_diff` (same-engine, zero-tolerance) + `harness/run_corpus_harness.py`'s cross-engine tolerant comparison (8% threshold) | This is the exact machinery G2a/G2b already proved correct and tuned against the real corpus (Pitfall 9's own "P0 before P3" discipline, restated: build export validation on the harness that already exists, not a parallel one) |
| Unreferenced-resource cleanup after split | Hand-walking `/Resources` to drop unused entries | `pikepdf.Pdf.remove_unreferenced_resources()` | Verified live this session (`remove_unreferenced_resources(self) -> None`, docstring: *"Remove from /Resources any object not referenced in page's contents"*) — but see Common Pitfalls below for its documented shared-`/Resources` caveat, which is the same hazard Pitfall 8 (02/03-RESEARCH.md) already names for this exact codebase |
| Server-side page-subset copy (split, if server-side is chosen) | Manual object-graph page extraction | `pikepdf.Pdf.new()` + `dst.pages.append(src.pages[i])` for each retained page | STACK.md's own top-level rated use case for pikepdf ("PDF split / merge / rotate — Excellent — qpdf preserves everything it doesn't touch") |

**Key insight:** every capability this phase needs already exists in an already-pinned library — the
work is *finding the right already-verified call* (this research did that, live, for every one of
them) and *not building a second version of something Phase 1-3 already solved once* (the harness, the
playa boundary, the annotation-appearance geometry). The one place genuinely new code is required —
the block-structure layer — is new precisely because no prior phase needed reading-order inference,
not because a library is missing.

## Common Pitfalls

### Pitfall 1: Font size and font identity are not on `RunRecord` — building `engine.blocks` against the index as-is will silently produce a heading-detector that cannot detect headings

**What goes wrong:** A plan that treats "build the block-structure layer" as pure application logic
over `RunRecord.display_text` will discover partway through implementation that there is no signal to
cluster on, and either (a) stalls, or (b) reaches back into `engine.playa_boundary` or re-parses with
`pikepdf.parse_content_stream` to recover font size directly — **which is itself a second extraction
path**, violating D-7.1/EXPO-05 in the very module meant to demonstrate the single-path rule most
carefully.

**Why it happens:** Phase 2 never needed font size or font identity past clustering time — D-01's
break-cause table (`engine/clusterer.py:198-237`) uses `effective_em` and `font_id` purely as
*equality comparisons* to decide run boundaries, then discards both. Nothing about TEXT-01..08 or
CLAS-01..05 required carrying either value forward.

**How to avoid:** Do the index extension (Architecture Patterns, Pattern 1) as an explicit Wave-0 task
*before* `engine.blocks` is planned as application logic. Verify the extension with a fixture that has
a known, hand-measured font-size ratio between headings and body text (the corpus's `tables` category
— only 3 documents, per `corpus/manifest.json` — and 0 documents tagged for multi-column layout are
worth flagging as a fixture gap for Wave 0, see Environment Availability below).

**Warning signs:** Any new file under `engine/blocks.py` importing `pikepdf.parse_content_stream` or
`playa` directly, or reading `/Tf` from raw stream bytes the way `classify_run._find_active_font_name`
does (`engine/classify_run.py:96-104`) — that regex-based `Tf`-scanning approach is already a second,
independent path to font information, separate from `RunIndex`, and duplicating it inside an export
module is exactly the fork D-7.1 forbids.

### Pitfall 2: `pikepdf.Pdf.remove_unreferenced_resources()`'s shared-`/Resources` caveat, applied to split

**What goes wrong:** Splitting a document into N single/multi-page files and then calling
`remove_unreferenced_resources()` on each output can, on a document where pages inherit a *shared*
`/Resources` dictionary from a common `/Pages` ancestor (verified as a real, already-documented hazard
in this exact codebase — `02/03-RESEARCH.md`'s own Pitfall 8: *"a page may have no `/Resources` of its
own and inherit from an ancestor `/Pages` node... writing a new font into the inherited dictionary...
alters every other page under that node"*), silently strip resources that a *different* retained page
in a *different* output file still needs, if pikepdf's own page-copy (`dst.pages.append(...)`) did not
already deep-copy resources per destination document.

**How to avoid:** Verify empirically (a cheap, corpus-driven Wave-0 check, not a research-time claim)
whether `pikepdf.Pdf.new()` + `dst.pages.append(src_page)` already performs a deep, document-scoped
copy of inherited `/Resources` (pikepdf's own `copy_foreign` machinery, which STACK.md already trusts
for "qpdf preserves everything it doesn't touch," is the mechanism to check) before calling
`remove_unreferenced_resources()` on a split output. If it does not, the resource-dictionary-sharing
pitfall this codebase's own prior research already names applies directly, and copy-on-write per
Pitfall 8's established remedy (`resolve_and_own`-style helper) is the correct fix, not a fresh
investigation.

### Pitfall 3: Client-side and server-side rasterizers will disagree — decide once, don't let it become an inconsistency bug

**What goes wrong:** If PNG/JPEG export is client-side (pdf.js/PDFium via WASM or canvas) for most
sessions but server-side (`pypdfium2`) as a fallback for some (e.g., very large documents, or a
future feature that needs export off the interactive session), the two paths will produce measurably
different pixels for the same page — this session's own harness measurement
(`harness/run_corpus_harness.py:6-14`) puts cross-engine disagreement at up to 7.2% even between two
*server-side* engines from antialiasing alone; pdf.js (a third, browser-only renderer) has not been
measured against either in this corpus and should be assumed to differ similarly, not identically.

**How to avoid:** Pick one export path as canonical per session type (per the Architectural
Responsibility Map's recommendation: client-side by default, server-side as an explicit fallback for
whatever condition forces it) and make the choice visible in the same PRIV-01 per-operation disclosure
UI Phase 4 builds — never silently mix the two within one document's export options.

### Pitfall 4: The PRIV-01 disclosure must be structurally true for exports, not a hand-maintained label — Phase 4 is not built yet, so this is an interface requirement, not an assumed shape

**What goes wrong:** Phase 4 (not yet built) is expected to establish "an empty override set means
the client materializes the file with zero upload" as PRIV-01's structural rule (`04-CONTEXT.md`
line 64-66, and ROADMAP criterion 5's "backed by the structural rule"). If Phase 7's client-side
export candidates (PNG/JPEG, split) are implemented against a *different*, ad hoc disclosure
mechanism because Phase 4 hadn't landed yet when Phase 7 was planned, the two mechanisms will diverge
and PRIV-01 stops being structurally provable for exports specifically.

**How to avoid:** Treat Phase 4's disclosure mechanism as an **interface requirement** on this phase,
not an assumed shape: whatever Phase 4 ships (a typed operation registry, a per-request header, a
client-side manifest of "operations that never call the server") must be the *same* mechanism Phase 7
registers its client-side exports against. If Phase 7 executes before Phase 4's exact shape is known
(unlikely given the dependency, but the roadmap allows 5∥6∥7 parallelism after G3, so Phase 6 and
Phase 7 could plausibly be planned close together against an early Phase 4 cut), coordinate explicitly
rather than each phase inventing its own disclosure primitive — this is also the answer to avoiding
duplicate client-side page-manipulation utilities between Phase 6 (page ops) and Phase 7 (split),
which both want `@cantoo/pdf-lib` page-copy logic and should share one `client/src/lib/` module rather
than two.

## Code Examples

### The single-extraction-path proof (EXPO-05 / ROADMAP criterion 1), runnable

```python
# Source: this session's design, modeled directly on engine/index.py:139-143's own
# "patchable method... so a test can monkeypatch.setattr it" precedent, and generalizing
# the convention already stated in prose in engine/clusterer.py:10,
# engine/classify_page.py:60-62, engine/shared_xobjects.py:47 -- none of which is
# currently enforced by any test (verified: `grep -rln "def test.*only.*import\|def
# test.*single.*path" tests/*.py` returns nothing this session).

# tests/test_export_single_path.py
import ast
from pathlib import Path

import engine.playa_boundary
from engine.index import RunIndex


def test_only_playa_boundary_imports_playa() -> None:
    """Generalizes the docstring convention into an actual CI gate. Scans every .py file
    under engine/ (AST, not string search -- immune to a docstring or comment containing
    the word 'playa')."""
    offenders: list[str] = []
    for py_file in Path("engine").rglob("*.py"):
        if py_file.name == "playa_boundary.py":
            continue
        tree = ast.parse(py_file.read_text(), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                a.name == "playa" or a.name.startswith("playa.") for a in node.names
            ):
                offenders.append(str(py_file))
            elif isinstance(node, ast.ImportFrom) and node.module and (
                node.module == "playa" or node.module.startswith("playa.")
            ):
                offenders.append(str(py_file))
    assert offenders == [], f"second playa import site(s) found: {offenders}"


def test_export_reuses_open_run_index_no_second_parse(monkeypatch, tmp_path) -> None:
    """The runtime proof, complementing the static one above: exporting text/markdown/
    html from an already-open RunIndex must not open a second playa Document. Mirrors
    engine/index.py's own _parse_page call-count precedent exactly."""
    calls: list[None] = []
    real_open = engine.playa_boundary.open_document

    def counting_open(*args: object, **kwargs: object) -> object:
        calls.append(None)
        return real_open(*args, **kwargs)

    monkeypatch.setattr(engine.playa_boundary, "open_document", counting_open)

    with RunIndex(FIXTURE_PATH) as idx:      # 1 call, from RunIndex.__init__
        for i in range(idx.page_count):
            idx.page(i)                       # 0 additional calls -- already cached
        assert len(calls) == 1

        from engine.export.text import export_text        # NEW module, this phase
        from engine.export.markdown import export_markdown  # NEW module, this phase
        from engine.export.html import export_html          # NEW module, this phase

        export_text(idx)
        export_markdown(idx)
        export_html(idx)
        assert len(calls) == 1, "an export function opened a second playa Document"
```

### Page image export — the exact scale formula already proven correct

```python
# Source: harness/render_diff.py:37-39, the SAME formula, already the CI-validated
# server-side rasterization call. New caller (an export endpoint/module), zero new
# capability. RENDER_DPI here is the export's own chosen DPI (150 screen / 300 print
# per D-7.5), not the harness's fixed 150.
import pypdfium2 as pdfium

def render_page_png(pdf_path: str, page_index: int, dpi: int) -> bytes:
    scale = dpi / 72
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        page = pdf[page_index]
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil()
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    finally:
        pdf.close()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `page.render(dpi=...)` (pypdfium2 API assumed in the pre-GSD `server/` scaffold) | `page.render(scale=DPI/72)` | Already corrected in Phase 4's own known-defects list (`04-CONTEXT.md`'s scaffold defect #2: "the installed pypdfium2 5.12.1 exposes `page.render(scale=...)` — HTTP 500") | Not this phase's discovery, but directly relevant: any export code copying the `server/` scaffold's rendering calls inherits this exact bug. Use `harness/render_diff.py:37`'s already-correct call as the template, not the scaffold |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Client-side PNG/JPEG export via pdf.js canvas rendering is achievable at the same `scale=DPI/72` formula pypdfium2 uses, with acceptable visual fidelity | Architectural Responsibility Map, Alternatives Considered | If pdf.js's canvas output diverges meaningfully from what a "print-quality 300 DPI" export implies (e.g., canvas resolution limits in some browsers), the client-side candidate for EXPO-01 may need to fall back to server-side more often than assumed. Low risk: pdf.js is an already-loaded, mature library and this is a common pattern (screenshot/print tools use it routinely), but not verified against this project's own corpus this session |
| A2 | `pikepdf.Pdf.new()` + `dst.pages.append(src_page)` deep-copies inherited/shared `/Resources` per destination document, making `remove_unreferenced_resources()` safe to call per split output | Common Pitfalls, Pitfall 2 | If false, split outputs could silently lose resources another retained page in a *different* output file needed, or (the safer failure direction) `remove_unreferenced_resources()` simply becomes unsafe to call post-split and must be skipped — a correctness bug either way if unverified before use. This is corpus-testable in under an hour and should be a Wave-0 task, not shipped on faith |
| A3 | `/FontDescriptor /Flags` bit 6 (ForceBold) + `/ItalicAngle != 0` is a sufficiently reliable bold/italic signal across the corpus's real-world font population, without needing a BaseFont-name-substring fallback | Architecture Patterns, Pattern 1 | If descriptor flags are frequently absent or wrong (plausible — `03-RESEARCH.md`'s own Pitfall 11 already documents that font metadata fields, `fsType` specifically, "frequently contradict" the actual truth), bold/italic detection degrades silently rather than refusing visibly, which conflicts with this project's own established "refuse visibly, never guess" discipline (EDIT-04, CLAS-04). Should be corpus-measured, not assumed, before committing to descriptor-flags-only |
| A4 | The block-structure layer's exact clustering thresholds (what font-size ratio distinguishes a heading from body text; what horizontal-position pattern indicates a list) are learnable without a dedicated research pass, using the same corpus-measurement discipline Phase 2 used for `K_EM`/`BREAK_EM` | Summary, Architecture Patterns | If real-world heading/body-text size ratios are less consistent than assumed (unlike Phase 2's space-threshold tuning, which had 91k measured gaps to converge against), the layer may need more iteration than a single Wave-0 pass budgets for. This research does not attempt the corpus measurement itself — flagged as MEDIUM confidence and Claude's Discretion for the planner to size |

## Open Questions (RESOLVED)

Historical questions below were settled by CONTEXT amendments A-7.2/A-7.3/A-7.4
and the current `07-RESEARCH-UPDATE.md`. They remain as provenance, not blockers.

1. **Should `engine.blocks`'s output type be shared verbatim with Phase 8's DOCX writer, or does DOCX need a superset?**
   - What we know: D-7.2 explicitly requires this layer be planned "as its own module with its own
     tests," reusable by Phase 8. Phase 8's own ceiling (D-8.2) names exactly the same primitives
     (headings by font-size clustering, bold/italic, inline images, ruled tables only, single-column
     body text) this phase's Markdown/HTML need.
   - What's unclear: whether OOXML generation (Phase 8) needs additional structural metadata (e.g.,
     explicit paragraph-vs-run distinction beyond what HTML/Markdown rendering needs) that would
     require extending `engine.blocks`'s output type later, or whether the same `Block` shape serves
     both renderers unchanged.
   - Recommendation: design `engine.blocks`'s output as a plain, renderer-agnostic data structure
     (block type, source `RunRecord`s, computed style attributes) rather than anything HTML- or
     Markdown-shaped, so Phase 8 extending it is additive, not a rewrite. Do not attempt to predict
     Phase 8's exact needs beyond that — Phase 8 has its own research pass scheduled.

2. **Where does zip assembly for all-pages image export happen — streamed from the server, or assembled client-side from N individually-fetched/rendered pages?**
   - What we know: `zipfile` (stdlib) is the right tool either way (Don't Hand-Roll). D-7.1/EXPO-01
     requires "per-page or all pages as a zip."
   - What's unclear: this is explicitly Claude's Discretion per CONTEXT.md ("Zip assembly location and
     streaming strategy for all-pages image export"), and depends on whether PNG export itself lands
     client-side or server-side (Architectural Responsibility Map) — if client-side, zip assembly is
     also naturally client-side (`JSZip`-class library or manual DEFLATE via a small library, since
     browsers have no built-in zip API — this would be Phase 7's one genuinely new *client*
     dependency, and should get its own legitimacy audit if chosen).
   - Recommendation: decide this once the PNG-export tier (client vs. server) is locked, not
     independently — the two decisions are coupled.

3. **Corpus fixture gap for multi-column and heading-heavy documents.**
   - What we know: `corpus/manifest.json` has 0 documents tagged for multi-column layout and only 3
     tagged `tables` (measured this session: `python3 -c "... Counter over categories ..."` → no
     `multi_column` or `headings` category exists at all in the current 217-document public corpus).
   - What's unclear: whether the block-structure layer can be adequately tested against the existing
     corpus, or whether new fixtures (or fixtures explicitly built, matching `tools/build_mixed_
     fixture.py`'s Phase 2 precedent for a fixture the corpus itself lacked) are needed.
   - Recommendation: flag as a Wave 0 fixture-construction task, following the same "build it
     deliberately, document why the corpus lacked it" pattern Phase 2 used for the vector-outlined-text
     and CLAS-05 mixed fixtures.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|--------------|-----------|---------|----------|
| pikepdf | Compress, flatten, split (server path) | ✓ | 10.11.0 (matches pin) | — |
| pypdfium2 | Page image export (server path) | ✓ | 5.12.1 (matches pin) | — |
| Pillow | Compress image downsampling | ✓ | 12.3.0 (matches pin) | — |
| `zipfile` (stdlib) | All-pages-as-zip | ✓ | Python 3.13 stdlib | — |
| `qpdf` CLI | D-7.4's `--check` gate | ✓ | 12.4.0 local; 12.2.0-1 pinned in `Dockerfile.ci` (same pre-existing version-gap note as Phase 3's own research — already tracked, not new) | — |
| `@cantoo/pdf-lib` | Client-side split (candidate) | Not independently verified this session — already pinned per CLAUDE.md's client stack, inherited from Phase 4's scaffold | 2.8.1 (pinned) | Server-side split via pikepdf (Alternatives Considered) |
| pdf.js / `pdfjs-dist` | Client-side PNG/JPEG export (candidate) | Not independently verified this session — already pinned, already the viewer (VIEW-01) | 6.2.108 (pinned) | Server-side via pypdfium2 |
| **Phase 4's PRIV-01 disclosure mechanism** | Every client-side export candidate's disclosure | **✗ — Phase 4 not yet built** | — | None — this is a genuine interface dependency, not a fallback-able one. See Common Pitfalls, Pitfall 4 |
| **Phase 4's server-side document/session handle** | Every server-side export's access to an open document | **✗ — Phase 4 not yet built** | — | None — Phase 7's server-side exports need whatever content-addressed handle Phase 4 establishes for PRIV-02; this research treats its exact shape as an interface requirement, per this task's own discipline note, not an assumed API |

**Missing dependencies with no fallback:** Phase 4's PRIV-01 disclosure mechanism and server-side
document-handle shape — both are architectural interfaces this phase must consume, not dependencies
this phase can install or substitute. The planner should express Phase 7's plans' Wave 0 as depending
on Phase 4's actual shipped interface (once it exists), not a guessed one.

**Missing dependencies with fallback:** none beyond the two above — every library dependency proper is
already installed and pinned.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest ≥9.1.1 (already configured) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths=["tests"]`, `corpus` marker for full-corpus-sweep tests |
| Quick run command | `uv run --frozen pytest -q -m "not corpus"` |
| Full suite command | `uv run --frozen pytest -q` |
| Type check | `uv run --frozen mypy engine/` (strict; zero `# type: ignore`) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| EXPO-05 | No second extraction path — static AST scan (generalizes the pre-existing, currently-unenforced docstring convention) | unit | `pytest tests/test_export_single_path.py::test_only_playa_boundary_imports_playa -x` | ❌ Wave 0 |
| EXPO-05 | No second extraction path — runtime call-count proof that export functions reuse an already-open `RunIndex` | unit | `pytest tests/test_export_single_path.py::test_export_reuses_open_run_index_no_second_parse -x` | ❌ Wave 0 |
| EXPO-05 | Plain text export matches `RunRecord.display_text` joined per page, in reading order | unit | `pytest tests/test_export_text.py::test_plain_text_matches_display_text -x` | ❌ Wave 0 |
| EXPO-05 | Markdown export: headings inferred from font-size clustering, on a fixture with a known, hand-measured size ratio | unit + corpus | `pytest tests/test_blocks.py::test_heading_detected_from_font_size_ratio -x` | ❌ Wave 0 |
| EXPO-05 | HTML export reuses the SAME `engine.blocks` output Markdown does — no second structure-inference pass | unit | `pytest tests/test_export_html.py::test_html_and_markdown_share_block_structure -x` | ❌ Wave 0 |
| EXPO-01 | PNG/JPEG export at 150 (screen) and 300 (print) DPI defaults, per-page | unit | `pytest tests/test_export_images.py::test_dpi_defaults_150_and_300 -x` | ❌ Wave 0 |
| EXPO-01 | All-pages-as-zip contains one file per page, correctly named | unit | `pytest tests/test_export_images.py::test_all_pages_zip_contains_every_page -x` | ❌ Wave 0 |
| EXPO-02 | Compress is lossless by default — `masked_pixel_diff(before, after) == 0` when downsampling is not selected | unit + pixel-diff | `pytest tests/test_compress.py::test_lossless_compress_zero_pixel_diff -x` | ❌ Wave 0 |
| EXPO-02 | Compress reduces size on a real corpus document (structural: object-stream packing + Flate recompression) | corpus | `pytest -m corpus tests/test_compress.py::test_corpus_compress_reduces_size -x` | ❌ Wave 0 |
| EXPO-02 | Image downsampling is explicit/labelled and shows before/after size — negative case: downsampling never fires unless explicitly requested | unit, negative case | `pytest tests/test_compress.py::test_downsample_never_fires_by_default -x` | ❌ Wave 0 |
| EXPO-03 | Split output passes `qpdf --check` | unit + subprocess | `pytest tests/test_split.py::test_split_output_passes_qpdf_check -x` | ❌ Wave 0 |
| EXPO-03 | Split — masked differential diff confined to the intended change (each retained page pixel-identical, same-engine, to its original render) in all three engines | corpus + pixel-diff | `pytest -m corpus tests/test_gate_g6.py::test_split_confined_diff_three_engines -x` | ❌ Wave 0 |
| EXPO-04 | Flatten output passes `qpdf --check` | unit + subprocess | `pytest tests/test_flatten.py::test_flatten_output_passes_qpdf_check -x` | ❌ Wave 0 |
| EXPO-04 | Flatten — masked differential diff confined to the union of flattened annotation Rects (Pattern 4's precise definition), in all three engines | corpus + pixel-diff | `pytest -m corpus tests/test_gate_g6.py::test_flatten_confined_diff_three_engines -x` | ❌ Wave 0 |
| G6 criterion 1 | Codebase-wide: a search finds no second extraction path (the ROADMAP's own literal wording, as a repo-wide sweep beyond just the export modules) | unit | `pytest tests/test_export_single_path.py::test_only_playa_boundary_imports_playa -x` (same test as EXPO-05's first row — this IS the criterion, not a separate check) | ❌ Wave 0 |
| G6 criterion 3 | Compress before/after size reported; preview required when downsampling selected (UI-adjacent, server computes the numbers) | unit | `pytest tests/test_compress.py::test_compress_report_includes_before_after_size -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run --frozen pytest -q -m "not corpus"` (fast unit tests — hand-picked
  fixtures, including the AST-scan and call-count single-path proofs, which need no corpus at all and
  should run on every commit as cheaply as `mypy`)
- **Per wave merge:** `uv run --frozen pytest -q` (includes `corpus`-marked full-sweep tests) +
  `uv run --frozen mypy engine/`
- **Phase gate:** Full suite green, plus the actual G6 split/flatten harness runs (reusing
  `harness/masked_diff.py` and `harness/run_corpus_harness.py`'s cross-engine machinery unmodified,
  per Don't Hand-Roll), before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `engine/records.py`, `engine/clusterer.py`, `engine/index.py`, `engine/encoding_table.py` —
      the Pattern 1 index extension (font_size_pt, base_font/style, page geometry) — **blocks every
      other Wave in this phase transitively via `engine.blocks`**
- [ ] `engine/blocks.py` — D-7.2's own module, plus its test file `tests/test_blocks.py`
- [ ] `engine/export/` package (text.py, markdown.py, html.py, images.py, compress.py, split.py,
      flatten.py) — does not exist yet, confirmed by `find . -iname "*export*"` this session
- [ ] `tests/test_export_single_path.py` — both the static AST scan and the runtime call-count proof
- [ ] `tests/test_gate_g6.py` — the phase gate as an explicit, named test, matching Phase 3's
      `test_gate_g2a.py`/`test_gate_g2b.py` precedent
- [ ] Corpus fixture gap: no multi-column-tagged document, only 3 `tables`-tagged documents, in the
      current 217-document public corpus (`corpus/manifest.json`, measured this session) — construct
      or source fixtures for the block-structure layer's tests, following Phase 2's own
      `tools/build_mixed_fixture.py` precedent for a deliberately-constructed fixture where the corpus
      lacked real-world coverage
- [ ] A2's empirical verification (does `pikepdf.Pdf.new()` + `dst.pages.append()` deep-copy shared
      `/Resources`?) — cheap, corpus-testable, should land before `remove_unreferenced_resources()` is
      called anywhere in the split path

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|--------------------|
| V2 Authentication | No | No accounts in v1 (CLAUDE.md) |
| V3 Session Management | Partial | Export operations run within whatever session/handle model Phase 4 establishes for PRIV-02 (content-addressed, evictable cache) — this phase does not define session semantics, only consumes them |
| V4 Access Control | No | No multi-tenant/multi-user surface |
| V5 Input Validation | Yes | Export parameters (DPI, downsample quality, split ranges/every-N-pages) are user-supplied and must be bounded (e.g., a DPI of 100000 or a split range spanning more pages than the document has) before being passed to `pypdfium2`/`pikepdf` — matching `engine/index.py`'s own `MAX_DOCUMENT_GLYPHS`-style named-ceiling precedent, not an unbounded pass-through |
| V6 Cryptography | No | No cryptographic operations in this phase's own scope |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|------------------------|
| A crafted split request (e.g., "every 1 page" on a 10,000-page malformed PDF, or an absurd DPI on image export) used to exhaust server memory/CPU | Denial of Service | Already the established pattern this codebase uses elsewhere (`engine/index.py`'s `MAX_DOCUMENT_GLYPHS`, `engine/recipe.py`'s recipe-size bound noted in `03-RESEARCH.md`'s own Security Domain): bound DPI to the stated defaults' reasonable range (e.g., 72–600), bound split output count, and reuse whatever per-request wall-clock/memory limits PRIV-03/PRIV-07's isolated-worker model (Phase 4) already provides — export requests must run through the same isolation Phase 4 establishes for parsing, not a separate, unisolated code path, since compress/flatten/split all parse untrusted PDF bytes exactly as identically as the edit path does |
| Recompressing/flattening a hostile PDF (decompression bomb inside an image XObject targeted by the compress path's Pillow downsample step) | Denial of Service | Pillow's own `Image.open()` is lazy but `.resize()`/`.save()` force a full decode — the same "parse untrusted input never in the request process" rule PITFALLS.md's Pitfall 11 already establishes for this whole project applies identically here; this is not a new threat class, it is the existing one with a new call site |
| Exported file (PNG/JPEG/zip/PDF) inadvertently carrying identifying metadata beyond what the source had | Information Disclosure | PITFALLS.md Pitfall 12's item 9 already covers this for the engine generally ("do not *add* identifying metadata... beyond what is needed... do not silently strip the user's existing metadata either") — applies unchanged to every export format this phase produces |

## Sources

### Primary (HIGH confidence — directly verified this session, local execution or live introspection)
- `engine/records.py`, `engine/clusterer.py`, `engine/index.py`, `engine/classify_run.py`,
  `engine/encoding_table.py`, `engine/walker.py`, `engine/playa_boundary.py`, `engine/classify_page.py`,
  `tools/pdftool.py`, `tools/license_gate.py`, `harness/masked_diff.py`,
  `harness/run_corpus_harness.py`, `harness/render_diff.py`, `Dockerfile.ci` — read directly this
  session, file:line citations throughout
- `pikepdf 10.11.0`, live introspection (`inspect.signature`, `help()`, `dir()`) — `Pdf.save()`'s full
  parameter set including `object_stream_mode`/`recompress_flate`; `Pdf.flatten_annotations`;
  `Pdf.remove_unreferenced_resources`; `Page.get_images`/`Page.images` (deprecated); `PdfImage`;
  `Object.write` — all confirmed against the actually-installed package, not documentation alone
- `tools/license_gate.py`, executed this session — confirmed clean (exit 0) as the baseline this phase
  inherits
- `corpus/manifest.json`, parsed this session — 217 documents, category counts (0 multi-column, 3
  tables, 2 ocr_scan, etc.)
- `pikepdf.readthedocs.io/en/latest/api/main.html` `[CITED]` — `flatten_annotations` mode semantics,
  `remove_unreferenced_resources` shared-resources caveat (fetched this session via WebFetch)

### Secondary (MEDIUM confidence)
- `.planning/research/STACK.md`, `.planning/research/FEATURES.md`, `.planning/research/PITFALLS.md` —
  prior-phase research, read in full this session, cited throughout for precedent (compress/split/
  flatten tool assessment, DOCX/export usage-share data, the annotation-appearance and shared-
  `/Resources` pitfalls this phase's flatten/split work directly inherits)
- `.planning/phases/03-rewrite-engine-font-pipeline/03-RESEARCH.md`, `02-VERIFICATION.md` — read in
  full this session for the Validation Architecture template and for corroborating the `font_id`/
  `FontVerdict` shape claims against Phase 3's own independent reading of the same code

### Tertiary (LOW confidence)
- None — every claim in this document is either directly verified against the installed
  packages/codebase this session, or explicitly tagged `[ASSUMED]` in the Assumptions Log above.

## Metadata

**Confidence breakdown:**
- Standard stack (compress/split/flatten/images): HIGH — every capability verified live against the
  installed package this session, not from documentation or training-data memory alone
- Architecture (block-structure layer / index extension): MEDIUM — the gap and the extension are
  precisely identified with file:line evidence; the exact clustering thresholds are not corpus-
  measured this session (flagged, A4)
- Pitfalls: HIGH — inherited directly from this project's own prior-phase research (PITFALLS.md,
  02/03-RESEARCH.md) plus new pitfalls found by direct code reading this session, not speculative

**Research date:** 2026-08-30
**Valid until:** 30 days (stable, already-pinned stack; the one fast-moving element is Phase 4's
not-yet-built interface, which this research treats as a dependency to re-verify at plan time, not a
shape to assume)
