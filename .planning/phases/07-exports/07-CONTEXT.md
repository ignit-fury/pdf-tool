# Phase 7: Exports - Context

**Gathered:** 2026-08-30
**Status:** Ready for planning
**Source:** Batch planning pass (no `/gsd:discuss-phase` run). Phase boundary and constraints
transcribed from `ROADMAP.md` and `REQUIREMENTS.md`. Everything not listed as a decision is
Claude's Discretion.

<domain>
## Phase Boundary

A user gets their document out in the format they actually came for, and every text-derived format
comes out of the one run index.

**In scope:** EXPO-01..EXPO-05 — page images (PNG/JPEG at chosen DPI, per-page or zip), compress,
split, flatten, and plain text / Markdown / HTML.

**Explicitly NOT in scope:**
- PDF/A (EXPO-06) and DOCX (EXPO-07/08) — Phase 8, strictly last.
- A second text-extraction path. EXPO-05 is explicit and ROADMAP criterion 1 makes it testable: a
  search of the codebase must find no second extraction path.

## Hard Dependency

Phase 4 (Gate G3) for the SPA and server; consumes the Phase 2 run index for the text-derived
formats.

</domain>

<decisions>
## Implementation Decisions

### Settled upstream — do not relitigate

- **D-7.1: Plain text, Markdown, and HTML all consume the Phase 2 run index. One extraction path,
  total.** EXPO-05 and ROADMAP criterion 1, which states the test in codebase terms: *a search of
  the codebase finds no second extraction path*. The roadmap also states the remedy if one is
  needed — "a second path anywhere means the text model is under-specified, and the fix is Phase 2,
  not a fork." A planner that discovers the index lacks something Markdown needs should plan to
  extend the index, never to bypass it.

- **D-7.2: The reading-order and block-structure layer built here is inherited by DOCX in Phase 8.**
  ROADMAP Phase 8 criterion 3 says DOCX inherits "the reading-order and block-structure layer built
  for Markdown/HTML in Phase 7". That makes this layer a **deliberate, reusable artifact of this
  phase**, not an incidental helper inside the Markdown exporter. Plan it as its own module with
  its own tests.

- **D-7.3: Compress is lossless and structural by default; image downsampling is an explicit,
  labelled choice.** EXPO-02 and ROADMAP criterion 3, which additionally requires showing
  before/after size **and a preview** when downsampling is selected. The roadmap flags compress as
  deserving more polish than its complexity suggests — Smallpdf's own data puts it at ~34% of
  usage, the most-used PDF operation in the category.

- **D-7.4: Split and flatten outputs pass `qpdf --check` and a masked differential diff confined to
  the intended change, in all three engines.** ROADMAP criterion 4. Flatten in particular changes
  rendering by design, so "confined to the intended change" needs a precise definition in the
  validation strategy — this is the clause most likely to be hand-waved.

- **D-7.5: DPI defaults are 150 screen / 300 print.** EXPO-01 and ROADMAP criterion 2, which also
  requires per-page **or** all-pages-as-a-zip.

### Claude's Discretion

- Whether each export runs client-side or server-side, and therefore what PRIV-01's disclosure
  reports for it. (`pypdfium2` + Pillow is server-side; `@cantoo/pdf-lib` split is client-side. The
  choice per operation is open, subject to PRIV-01 being structurally true.)
- Markdown/HTML dialect and how much structure to attempt (headings, lists, tables) — bounded by
  what the block-structure layer can honestly infer, and by not over-building ahead of Phase 8.
- Zip assembly location and streaming strategy for all-pages image export.
- Compression technique selection within "lossless and structural" (object stream packing, stream
  recompression, duplicate-object merging).
- Split UI: ranges, every-N-pages, bookmarks, or a subset of those.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `CLAUDE.md` — project guidelines
- `.planning/ROADMAP.md` — Phase 7 section: goal, four success criteria, and the note on compress's
  outsized usage share
- `.planning/REQUIREMENTS.md` — EXPO-01..05, plus the Out of Scope rows on AGPL runtime libraries
- `.planning/research/STACK.md` — `pypdfium2` and Pillow; and `pdftopdfa` 0.9.0 as a working
  reference for the pikepdf/fontTools shape (named in ROADMAP as the reason this phase needs no
  research pass of its own on the library question)
- `.planning/research/FEATURES.md` — feature-usage evidence behind the compress prioritisation
- `engine/index.py`, `engine/records.py`, `engine/clusterer.py`, `engine/types.py` — the run index
  and its record shape: the single extraction path EXPO-05 requires
- `.planning/phases/02-text-model/02-VERIFICATION.md` — Gate G1 evidence for what the index
  actually guarantees (and, in its gaps, what it does not)
- `.planning/phases/04-web-tier-walking-skeleton-hardening/04-CONTEXT.md` — PRIV-01's structural
  local/server disclosure, which every export operation must report through
- `harness/masked_diff.py`, `harness/run_corpus_harness.py`, `tools/probe_corpus.py` — the
  three-engine harness and structural validators criterion 4 asserts against

</canonical_refs>

<specifics>
## Specific Ideas

- ROADMAP criterion 1's test is a **codebase search**, which means the validation strategy should
  pin an actual grep/AST assertion, not a reviewer's judgement. Phase 2's own discipline (typed
  `Code→Glyph` vs `Code→str`, mypy-enforced) is the precedent for making a structural claim
  machine-checkable.
- The block-structure layer (D-7.2) is the highest-leverage thing in this phase and the easiest to
  under-plan, because Markdown export "works" without it. Phase 8's DOCX scope ceiling — headings
  by font-size clustering, ruled tables only, single-column body text — describes exactly what this
  layer must be able to infer. Plan it to that bar now, not to Markdown's lower one.
- Flatten's interaction with annotation appearance streams touches TEXT-06 territory (text outside
  `/Contents`), already walked by `engine/walker.py`. Reuse rather than re-derive.

</specifics>

<deferred>
## Deferred Ideas

- PDF/A export (EXPO-06) — Phase 8, gated on veraPDF in CI.
- DOCX export (EXPO-07/08) — Phase 8, independently cuttable.
- OCR'd text layers in exports — v2 (OCR-01).

</deferred>

---
*Phase: 07-exports*
*Context assembled: 2026-08-30 during batch planning of Phases 4–8*

---

## Amendments

### 2026-08-30 — post-research rulings (controller decisions)

`07-RESEARCH.md` found one gap that changes this phase's wave structure, and closed its three open
questions with recommendations. None required a maintainer ruling; all are recorded here so the
planner does not re-litigate them.

#### A-7.1 — the run index must be extended before any export module is written

**This is the finding that changes the plan's shape.** `RunRecord` — the object
`engine.index.RunIndex.page()` returns, and the only thing an export can honestly consume without
opening a second parse — carries **no font size and no font identity**. Font size lived transiently
in `ClusterAttrs.effective_em` during clustering (`engine/clusterer.py:127`, `:152`) and is
discarded when `RunRecord` is built (`engine/clusterer.py:308-315`). `GlyphRecord.font_id` is an
opaque per-page-interned integer with **no reverse lookup** to a `/BaseFont` name
(`engine/classify_run.py:23-24`, `engine/walker.py:282`).

Font-size-clustering headings and bold/italic detection — the exact primitives D-7.2 requires this
layer to support, and Phase 8's named ceiling depends on — are therefore **structurally impossible**
against the index as it stands.

This is not a defect; Phase 2 never needed either field. It is precisely the case D-7.1 anticipates:
extend the index, never bypass it. **Ruling:** extending `RunRecord` / `PageIndex` with font size,
font identity/style, and page geometry is a **Wave 0 task**, ordered before any export module.

#### A-7.2 — `engine.blocks` output is renderer-agnostic

*(Research Open Question 1.)* Design the block-structure layer's output as a plain data structure —
block type, source `RunRecord`s, computed style attributes — rather than anything HTML- or
Markdown-shaped, so Phase 8's OOXML writer extends it additively rather than rewriting it. Do not
attempt to predict Phase 8's exact needs beyond that; Phase 8 has its own research pass.

#### A-7.3 — zip assembly location is decided with the PNG-export tier, not independently

*(Research Open Question 2.)* The two decisions are coupled: if PNG export lands client-side, zip
assembly is naturally client-side too — which would be this phase's one genuinely new *client*
dependency and needs its own legitimacy audit plus the `client/package-lock.json` licence gate
being added in Phase 6 (see `06-CONTEXT.md` A-6.2). Lock the export tier first.

#### A-7.4 — multi-column and heading-heavy fixtures must be constructed

*(Research Open Question 3.)* Measured: the 217-document public corpus has **zero** documents tagged
for multi-column layout and only 3 tagged `tables`; no `multi_column` or `headings` category exists
at all. Wave 0 fixture-construction task, following the same "build it deliberately, document why
the corpus lacked it" pattern Phase 2 used for the vector-outlined-text and CLAS-05 mixed fixtures
(`tools/build_mixed_fixture.py` is the precedent).

#### A-7.5 — EXPO-05's single-path rule is currently enforced only by prose

`engine/clusterer.py:10`, `engine/classify_page.py:60-62`, and `engine/shared_xobjects.py:47` all
assert "import playa appears in exactly one file in this repo" in **module docstrings**, and no test
enforces the production-code half. Close this pre-existing gap here — it is cheap and protects the
whole codebase, not just exports — alongside the export-specific call-count proof, modelled on
`engine/index.py:139-143`'s own patchable-method precedent.

#### A-7.6 — use the native APIs that already exist rather than hand-rolling

Verified live: `pikepdf.Pdf.flatten_annotations(mode=...)` implements flatten in C++ via qpdf, and
`pikepdf.Pdf.save(object_stream_mode=ObjectStreamMode.generate, recompress_flate=True)` implements
structural compression. Both exist, are documented, and are called by **no** `.save()` in this repo
today. `pypdfium2`'s `page.render(scale=DPI/72)` is the same call `harness/render_diff.py`'s
`render_pdfium()` already makes — EXPO-01 is a new caller, not new capability. Do not re-derive the
annotation-appearance-to-page-content compositing math a second time.
