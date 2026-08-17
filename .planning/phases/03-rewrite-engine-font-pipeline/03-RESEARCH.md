# Phase 3: Rewrite Engine + Font Pipeline - Research

**Researched:** 2026-08-17
**Domain:** PDF content-stream rewriting (pikepdf/qpdf) + font subsetting and Type0/CIDFontType2 embedding (fontTools/uharfbuzz)
**Confidence:** HIGH

## Summary

This phase has one already-answered question (the TJ-refit math, proven in Phase 1) and several
genuinely unanswered ones that this research resolves by **reading the actual Phase 2 code and
measuring the actual corpus**, not by re-deriving what the spike already proved. The two biggest
findings are architectural, not library-API, findings:

1. **A `RunRecord` can legitimately span many original content-stream operators** (D-01's own
   documented consequence). This is not a rare edge case: measured directly against the corpus
   (217 documents, 5 pages/doc), **10.6% of editable runs span more than one distinct operator**,
   up to **167 operators fused into a single run**. Of those multi-operator runs, **10.4% (≈1.1%
   of all editable runs) have a *different run's own operator* positioned between their first and
   last operator** — meaning a naive "delete the byte span from first to last operator, splice in
   one new operator" rewrite strategy would silently corrupt unrelated visible text on a real,
   non-trivial fraction of documents. The correct strategy (below) replaces the run's *first*
   touched instruction and deletes the rest individually, by instruction identity, never by byte
   range.
2. **`qpdf --qdf` diffing — G2a's own stated acceptance mechanism — does not work as a naive
   whole-file diff** when the edit touches a document whose `/Contents` is an array (52.5% of the
   corpus). Measured directly: coalescing a page's 8-part `/Contents` array into one stream (the
   pattern `engine/identity_rewrite.py` already established) produces a **13,689-line diff for a
   single-word text edit**, entirely from object renumbering cascading through the rest of the
   file, not from the edit itself. The rewrite engine must never reshape `/Contents` — it must
   replace only the specific array element containing the edited run(s) — and G2a's "confined
   diff" check must be a targeted structural comparison of the touched stream, not a blind
   `qpdf --qdf` + `diff`.

Beyond those two, the font pipeline (fontTools subsetting → uharfbuzz shaping → Type0/CIDFontType2
embedding → OTS validation) was verified **end-to-end, locally, against the project's own bundled
font**: a real fontTools subset of `LiberationSans-Regular.ttf` passes OTS cleanly, and
uharfbuzz's post-shaping glyph IDs were confirmed to match fontTools' glyph IDs exactly when
shaping is run *against the already-subsetted font* — the load-bearing ordering fact for
FONT-02/FONT-03/FONT-04. The bundled fonts' OS/2 `fsType` was also verified directly (not
assumed): Liberation Sans is `fsType=0` (Installable Embedding, unrestricted), consistent with its
SIL OFL license — the "frequently contradict" warning in the roadmap does not hold for the
currently-bundled Sans build, though Serif/Mono still need the identical check once those files
actually exist in `fonts/`.

**Primary recommendation:** Build the rewrite as instruction-identity surgery over
`pikepdf.parse_content_stream()`'s output (never byte-range splicing), touch only the specific
`/Contents` array element containing the edit, subset the bundled font once per family per save
(fontTools, `retain_gids=False`), shape replacement text *against the already-subsetted font* so
uharfbuzz's glyph IDs are directly the CIDs to write, and gate everything on OTS (`ots-sanitize`,
already verified working against this exact font) plus `qpdf --check` plus the existing
same-engine zero-tolerance / cross-engine tolerant harness from Phase 1.

## Architectural Responsibility Map

Phase 3 is deliberately single-tier — CLI-only, no web surface, per the roadmap's binding
constraint 3 ("no web tier before G2b"). Every capability below lives in the Engine tier; the
table exists to record *why* nothing is split across tiers yet, and to flag the one capability
whose *output* a later phase consumes.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Width-fit ladder (trailing_kern → inter-word → Tz → refuse) | Engine (Python/CLI) | — | Pure computation over PDF font metrics; no I/O boundary to split |
| Font-substitution decision (mapping table + glyph-availability check) | Engine | — | Reads the same font dictionaries `engine/encoding_table.py` already reads |
| Content-stream rewrite (operator consolidation, TJ construction) | Engine | — | Requires pikepdf's object graph; browser-side `@cantoo/pdf-lib` cannot do content-stream rewrite (CLAUDE.md: "append-only") |
| Font subsetting + Type0/CIDFontType2 embedding | Engine | — | fontTools/uharfbuzz are Python-only in this stack; no browser equivalent is in scope |
| Recipe (JSON ops) application | Engine (CLI `pdftool edit`) | Browser (Phase 4, wire format only) | D-09: this phase defines the format; Phase 4 sends it, doesn't interpret it |
| Dry-run fit report | Engine (produces structured data) | Browser (Phase 4 renders it) | D-03: "Phase 4's UI later renders this same structured data rather than recomputing it" — Phase 3 owns the computation, not the rendering |
| OTS / qpdf --check / pixel-diff validation | CI / dev tooling | — | Never a served-request code path; matches Phase 1's established subprocess-only pattern for GPL/AGPL-adjacent and validation tools |

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01: The fit ladder is `trailing_kern` → inter-word distribution → `Tz` 90–95% → refuse.**
  Tried in that order, first rung that fits wins. Chosen because kerning is non-deforming at these
  magnitudes while `Tz` genuinely deforms glyph shapes — so exhaust the free options before
  reaching for the one that changes how letters look. The first two rungs are already proven:
  Phase 1's spike hit Δ=0.0000pt in both the shorter and longer directions using `trailing_kern`
  alone (`TJ-REFIT-RESULTS.md`, ENG-05 retired). Accepted cost: a document whose delta lands just
  past the inter-word range now deforms glyphs slightly rather than refusing outright.

- **D-02: Condensing is `Tz` horizontal scaling, not a per-glyph kern squeeze.** Roadmap criterion
  5 allows condensing "only within 90–95%"; `Tz` is the operator that means exactly that, in one
  place, and maps to the stated percentage directly. Accepted cost: `Tz` persists within the text
  object until reset, so the rewrite must save and restore it correctly.

- **D-03: Overflow disclosure is a dry run, and dry run is the default.** `pdftool edit` computes
  and prints the per-run fit plan — which ladder rung fires, the resulting Δwidth, and the named
  reason for any refusal — without writing anything. Committing requires a separate explicit flag.
  Phase 4's UI later renders this same structured data rather than recomputing it.

- **D-04: The post-run text matrix invariant is a runtime guard, not just a test assertion.** After
  building a rewrite, re-walk the page and assert the text matrix following the edited run matches
  its original value within epsilon; on violation, refuse that edit with a named reason. Phase 2
  measured page parse at ~9–15ms, so the re-walk is affordable per edit.

- **D-05: Any glyph missing from the embedded subset substitutes the ENTIRE visual run.** Not the
  missing character, not the affected word — the whole run, re-encoded in the mapped bundled face.
  This is FONT-06 implemented directly. Accepted cost: one accented character re-renders a whole
  visual line in Liberation.

- **D-06: A font with no entry in the static mapping table refuses, by name.** No serif/sans
  fallback derived from descriptor flags. **Consequence worth measuring:** the refusal rate is a
  direct function of table coverage, so table coverage becomes a quality number.

- **D-07: Phase 3 bundles the Liberation trio only — Sans, Serif, Mono.** Metric-compatible with
  Arial/Times/Courier. Noto and DejaVu are deferred until refusal data shows a real coverage gap.
  Note: no `fonts/` directory exists in the repo yet; the Phase 1 spike borrowed
  `spike/fixtures/LiberationSans-Regular.ttf`.

- **D-08: Seam quality is gated by a machine metric AND a rendered contact sheet.** The metric is
  per-glyph advance delta against the original (near-zero for Liberation's metric-compatible
  cases), asserted in CI. The contact sheet is a rendered before/after across corpus samples,
  reviewed once by a human. Risk #4 is unverified today; this is how it gets retired.

- **D-09: An edit is a JSON recipe — a list of `{run_id, new_text}` ops.**
  `pdftool edit doc.pdf --recipe r.json -o out.pdf` replays them. This format IS Phase 4's wire
  format, unchanged. Deliberately no single-edit flag variant.

- **D-10: A source-hash mismatch hard-refuses the entire recipe, with no override flag.** No
  `--force` escape hatch.

- **D-11: Recipe application is all-or-nothing.** Any refusal means nothing is written; the report
  names every failing edit and its reason. A `--partial` mode was deliberately **not** added.

- **D-12: The original embedded font is never modified. Substituted runs point at a newly embedded
  font.** Untouched text keeps its original subset byte-for-byte. Re-subsetting the original over
  the whole-document glyph union was rejected.

- **D-13: One subset per bundled family per document, over the glyph union, emitted once at
  save.** Every substituted run's glyphs are collected across the whole recipe; one Liberation
  Sans subset covering the union is embedded once. FONT-05's fresh-subset-tag rule then has one
  tag per family, not one per edited run.

- **D-14: The FONT-04 width assertion binds on `/W`, and `/Widths` is the untouched-original
  case.** New bundled fonts embed as Type0/CIDFontType2 with Identity-H, carrying a `/W` array —
  so the assertion is that every CID in `/W` matches the subset program's own `hmtx` advance, and
  `/DW` never silently covers a glyph actually in use. Original simple fonts keep their `/Widths`
  untouched per D-12.

- **D-15: G2b is gated on the machine-checkable set; the viewer checks are recorded evidence.** CI
  gates on: OTS validation of the emitted font, `qpdf --check` clean, same-engine zero-tolerance
  pixel diff outside the edited run, cross-engine agreement within the measured tolerance, and a
  programmatic ToUnicode extraction check. The three real-viewer opens (Acrobat Reader, macOS
  Preview, Chrome) and the Acrobat copy-paste check are performed once and recorded in a results
  document.

### Claude's Discretion

- Disposition of the Phase 1 spike modules (`spike/tj_refit_prototype.py`'s algorithm, sign
  convention, `/Widths`-via-pikepdf deviation are carried-forward knowledge; absorb, rewrite, or
  leave alone as judged). `spike/playa_decode_probe.py`'s single-module-boundary rule is already
  satisfied by `engine/playa_boundary.py`.
- Where the rewrite engine's module boundary sits within `engine/` and how it composes with
  `engine/identity_rewrite.py`.
- The exact `Tz` floor within the 90–95% band, and whether `Tz` may stack with inter-word
  distribution or must replace it.
- How bold/italic variants are selected within a mapped family, and what the mapping table keys
  on (BaseFont name, descriptor flags, or both).
- ToUnicode CMap generation specifics for the emitted Type0 fonts.

### Deferred Ideas (OUT OF SCOPE)

- **`--partial` recipe application** — deferred to Phase 5's own evidence (D-11).
- **Noto Sans/Serif and DejaVu bundling** — deferred until refusal data proves a gap (D-07).
- **Widening the static font mapping table from collected evidence** — reporting unmapped fonts as
  corpus data is a nice-to-have, not required now (D-06 decides the refusal; the reporting is
  optional).
- **Recipe format versioning field** — matters when Phase 4 sends recipes over a wire.
- **The per-part `/Tf` scoping limit in `engine/classify_run.py`** — recorded, understood, not in
  this phase's requirement list, though Phase 3's rewrite touches the same interaction.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-------------------|
| EDIT-02 | Replacement text refitted into original run's width, text matrix after the run unchanged within epsilon | TJ-refit algorithm already proven (Phase 1); this research adds the **operator-consolidation architecture** needed to apply it to real multi-operator runs (§ Architecture Patterns, § Pitfall 1–3), and the D-04 re-walk guard's exact mechanism |
| EDIT-03 | Overflow measured and disclosed before commit; 90–95% condensing; visible refusal beyond | `Tz` operator semantics verified (§ Architecture Patterns, Tz section); dry-run report shape recommended (§ Code Examples) |
| EDIT-04 | An edit that cannot be performed correctly is refused visibly with a reason | Existing `RunVerdict`/`FontVerdict` named-reason vocabulary (Phase 2) extended, not replaced (§ Don't Hand-Roll) |
| FONT-01 | Bundled open-license font set, static mapping table, never a heuristic | Corpus-measured BaseFont name survey gives a concrete starting table (§ Pitfall 10); `fsType` verified for Sans (§ Common Pitfalls, Pitfall 11) |
| FONT-02 | Fonts subset against whole-document glyph usage at save time | fontTools `Subsetter` verified locally end-to-end, including GID renumbering behavior (§ Code Examples) |
| FONT-03 | New fonts embed as Type0/CIDFontType2 + Identity-H + correct `/W` + generated `/ToUnicode` | WeasyPrint reference architecture (verified BSD, verified exact dict shapes) (§ Code Examples) |
| FONT-04 | `/Widths` regenerated with a consistency assertion; no silent `/MissingWidth` of 0 | D-14 already binds this to `/W`, not `/Widths`; `cid_width()` (existing) already reads the emit format this research recommends (§ Architecture Patterns) |
| FONT-05 | Every re-subset gets a fresh subset tag | WeasyPrint's MD5-of-description tag generator verified (§ Code Examples) |
| FONT-06 | Entire visual run re-encoded when substituting, never half | D-05 already decides this; this research identifies the **new edit-time glyph-availability check** this requires, distinct from Phase 2's existing `editable_substitution` state (§ Pitfall 4 — the most important single finding for FONT-06) |
</phase_requirements>

## Standard Stack

**The stack is already fully resolved and pinned per CLAUDE.md and `pyproject.toml`.** This
research does not propose alternatives — it verifies what's pinned still works for this phase's
new surface (font embedding, content-stream surgery) and identifies the one genuinely new tool
(OTS) and one new dev-tooling gap (a missing mypy override).

### Core (already pinned — verified installed, matches `pyproject.toml` exactly)

| Library | Pinned | Installed (verified) | Purpose this phase |
|---------|--------|----------------------|---------------------|
| pikepdf | 10.11.0 | 10.11.0 `[VERIFIED: uv run python -c "import pikepdf; print(pikepdf.__version__)"]` | Object graph + content-stream parse/unparse (already used by `identity_rewrite.py`) |
| fontTools | 4.63.0 | 4.63.0 `[VERIFIED]` | Subsetting (`fontTools.subset.Subsetter`) |
| uharfbuzz | 0.56.0 | 0.56.0 `[VERIFIED]` | Shaping — kerned advances (proven in Phase 1) **and** post-subset glyph IDs (new finding, this phase) |
| Python | ≥3.13 | 3.13.7 `[VERIFIED]` | — |

`qpdf` CLI: 12.4.0 installed locally `[VERIFIED: qpdf --version]`. **Note:** `Dockerfile.ci` pins
`qpdf=12.2.0-1` (an older patch series). Since G2a's own acceptance criterion is a `qpdf --qdf`
diff, confirm this version gap doesn't change `--qdf` normalization output before relying on it in
CI — `qpdf`'s own docs describe `--qdf` as stable across minor versions, but this project's stated
discipline ("output differs across versions and your golden tests will drift") argues for pinning
the *same* qpdf version in local dev and CI, not just trusting stability.

### Supporting — new to this phase

| Tool | Version | License | Purpose | Verification |
|------|---------|---------|---------|---------------|
| **OTS** (`ots-sanitize`) | 9.2.0 (via `opentype-sanitizer` PyPI wrapper) / apt `opentype-sanitizer` 8.2.1+dfsg-2 (Debian trixie) | BSD-3-Clause `[VERIFIED: github.com/khaledhosny/ots LICENSE file]` | G2b's font validation gate | `[VERIFIED: ran locally against LiberationSans-Regular.ttf AND a real fontTools-subsetted 22-glyph derivative — both "File sanitized successfully!", exit 0]` |

**Installation (CI, matches the existing Dockerfile.ci subprocess-tool pattern — qpdf/pdfcpu/poppler/mupdf are all installed this way already):**
```dockerfile
# add to Dockerfile.ci's existing apt-get install line, pinned like its siblings
ARG OTS_VERSION=8.2.1+dfsg-2
    ...
    opentype-sanitizer="${OTS_VERSION}" \
```

**Installation (local dev convenience — no Docker needed, verified working):**
```bash
pip install opentype-sanitizer==9.2.0   # bundles a prebuilt ots-sanitize binary
python -m ots path/to/font.ttf          # "File sanitized successfully!" or a specific error
```
Both are legitimate; recommend apt in CI (consistency with the existing tool-install pattern) and
document the pip path for engineers iterating on the font pipeline without Docker.

### Alternatives Considered

| Instead of | Could use | Tradeoff |
|------------|-----------|----------|
| `fontTools.subset.Subsetter` (already pinned, verified OTS-clean locally) | `hb-subset` (HarfBuzz's own C subsetter, via a Python binding) | WeasyPrint's own source comments (fetched this session) note they now *prefer* hb-subset for speed, with fontTools as their fallback. Rejected here: hb-subset would be a **new, unpinned, unaudited dependency** for a marginal speed gain on a per-document (not per-request) operation; fontTools is already pinned, already proven end-to-end (subset → OTS clean) in this research, and CLAUDE.md's "don't propose new runtime dependencies without a licence audit" applies directly. Revisit only if subsetting throughput becomes a measured bottleneck. |
| `qpdf --qdf` + `diff` (whole file) | A targeted structural diff (compare only the touched stream's decoded operator list, old vs new) | The whole-file approach is what G2a's wording suggests literally, but is **measured to fail** on any array-`/Contents` document (§ Pitfall 3). No alternative library needed — this is a ~20-line Python function using `pikepdf.parse_content_stream` twice, not a new dependency. |

## Package Legitimacy Audit

No new **runtime** Python packages are introduced this phase — every library used (`pikepdf`,
`fontTools`, `uharfbuzz`, `pypdfium2`, `Pillow`) is already pinned in `pyproject.toml` and was
installed and version-verified directly above; none needs re-auditing.

One new **dev-tooling** package is recommended (OTS's PyPI wrapper, for local iteration without
Docker) and was run through the full Package Legitimacy Gate this session:

| Package | Registry | Version history | Source Repo | slopcheck | Disposition |
|---------|----------|------------------|--------------|-----------|-------------|
| `opentype-sanitizer` | PyPI | 9.2.0, with a continuous history back through 8.x/7.1.x `[VERIFIED: pip index versions opentype-sanitizer]` | `github.com/googlefonts/ots-python` (maintainer: Cosimo Lupo, fontTools/googlefonts ecosystem) | `[OK]` `[VERIFIED: slopcheck install opentype-sanitizer]` | Approved — dev-tooling only, not a runtime/CI-required dependency (apt `opentype-sanitizer` is the CI path) |

**Packages removed due to slopcheck [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.

The two genuinely new **non-package** supply-chain additions this phase makes are named explicitly
since they fall outside slopcheck's registry scope:
1. **OTS as an apt package** in `Dockerfile.ci` — outside the AGPL-gated resolved Python lockfile
   entirely (a CLI tool, like qpdf/pdfcpu/poppler/mupdf already are), BSD-licensed, no licensing
   concern.
2. **The Liberation Serif/Mono font files themselves** — `fonts/` does not exist yet (only
   `LiberationSans-Regular.ttf` exists, in `spike/fixtures/`). Pin the download source to
   `github.com/liberationfonts/liberation-fonts` **releases** (the same project/version lineage
   already verified for Sans — fsType was explicitly zeroed in that project's changelog at v2.00.3
   in 2012, and the currently-bundled Sans file measures `fsType=0` directly) — not a different
   mirror (e.g., an old Ascender-era or unverified third-party redistribution), and re-run the
   `fsType`/license verification script (§ Common Pitfalls, Pitfall 11) against Serif and Mono
   once fetched.

## Architecture Patterns

### System Architecture Diagram

```
 recipe.json {run_id, new_text}[]
        |
        v
 ┌─────────────────────────┐
 │ 1. DECODE & RESOLVE       │  decode_run_id() (existing) -> source_hash check (D-10,
 │    every run_id            │  hard refuse whole recipe on mismatch) -> resolve against
 │                             │  RunIndex(original_pdf) (existing) to get the RunRecord +
 │                             │  RunVerdict Phase 2 already computed
 └───────────┬─────────────┘
             v
 ┌─────────────────────────┐
 │ 2. PER-EDIT GLYPH CHECK    │  NEW this phase. For every char in new_text: does the run's
 │    (D-05 trigger)          │  OWN font (if editable_original) have a CODE + GLYPH for it?
 │                             │  -> reuse original font.  Else -> substitute (mapping table,
 │                             │  D-06; refuse by name if no entry).
 └───────────┬─────────────┘
             v
 ┌─────────────────────────┐
 │ 3. WIDTH FIT LADDER        │  shape new_text with uharfbuzz (against original font OR the
 │    (D-01, proven Phase 1)  │  bundled font, per step 2's outcome) -> trailing_kern ->
 │                             │  inter-word -> Tz 90-95% -> refuse (named reason, EDIT-04)
 └───────────┬─────────────┘
             v
 ┌─────────────────────────┐
 │ 4. COLLECT (don't write)   │  every substituted run's needed glyphs, unioned PER FAMILY
 │    glyph union             │  across the WHOLE recipe (D-13) -- nothing written yet
 └───────────┬─────────────┘
             v
      [ steps 1-4 repeat for every op in the recipe; D-11 all-or-nothing:
        any refusal here means NOTHING in step 5+ happens ]
             v
 ┌─────────────────────────┐
 │ 5. SUBSET (once per         │  fontTools.subset.Subsetter over each family's glyph union
 │    bundled family)          │  (D-13) -> fresh 6-letter subset tag (FONT-05)
 └───────────┬─────────────┘
             v
 ┌─────────────────────────┐
 │ 6. RE-SHAPE against the     │  NEW finding: shape replacement text a SECOND time, now
 │    SUBSETTED font           │  against the subset font, so uharfbuzz's glyph IDs ARE the
 │                             │  CIDs to write (verified: they match exactly)
 └───────────┬─────────────┘
             v
 ┌─────────────────────────┐
 │ 7. CONTENT-STREAM SURGERY   │  per touched /Contents ARRAY ELEMENT (never coalesced,
 │    (instruction-identity,   │  Pitfall 3): parse_content_stream -> replace the run's
 │    not byte-range)          │  FIRST touched instruction with the new Tj/TJ (+ Tz
 │                             │  save/restore if step 3 used it) -> DELETE the run's other
 │                             │  touched instructions individually -> unparse -> new stream
 └───────────┬─────────────┘
             v
 ┌─────────────────────────┐
 │ 8. EMBED new fonts           │  Type0/CIDFontType2 dict + /W (from subset hmtx) +
 │    (once, after all edits)  │  /ToUnicode CMap (WeasyPrint pattern) -> pdf.save()
 └───────────┬─────────────┘
             v
 ┌─────────────────────────┐
 │ 9. VERIFY (D-04 + G2a/G2b)   │  re-walk edited pages, assert text matrix after each edited
 │                             │  run unchanged (epsilon) -> qpdf --check -> OTS on emitted
 │                             │  font -> same-engine zero-tolerance / cross-engine tolerant
 │                             │  pixel diff (harness/, reused unmodified)
 └─────────────────────────┘
```

### Recommended Project Structure

Claude's Discretion item: module boundary. Recommended, following the established one-module-one-
concern pattern (`engine/classify_run.py` vs `encoding_table.py` vs `clusterer.py` each own one
thing):

```
engine/
├── fit.py            # NEW. Step 3: the width-fit ladder. Absorbs/rewrites
│                      # spike/tj_refit_prototype.py's proven algorithm + sign convention.
├── fonts.py           # NEW. Steps 2, 4, 5, 6, 8: the static mapping table (FONT-01), the
│                      # per-char glyph-availability check (D-05 trigger), subsetting
│                      # (FONT-02/05), Type0/CIDFontType2 + /W + /ToUnicode construction
│                      # (FONT-03/04).
├── rewrite.py         # NEW. Step 7: content-stream surgery. Composes with, does not
│                      # duplicate, engine/identity_rewrite.py's per-instruction unparse
│                      # pattern -- but deviates from its /Contents-coalescing behavior
│                      # (Pitfall 3) since that behavior is wrong for a real edit.
├── recipe.py           # NEW. Steps 1, all-or-nothing orchestration (D-09/D-10/D-11), the
│                      # dry-run report shape (D-03).
├── identity_rewrite.py # EXISTING. Its per-instruction unparse pattern
│                      # (_hex_literal-style, join with b"\n") is the one piece of this
│                      # module directly reused, not its coalescing behavior.
├── index.py            # EXISTING. RunIndex -- unchanged; recipe.py resolves run_ids
│                      # against it exactly as identity_rewrite.py's verify_roundtrip does.
├── encoding_table.py    # EXISTING. resolve_font/glyph_presence/encoding_map -- fonts.py's
│                      # glyph-availability check REUSES encoding_map()'s tables (see
│                      # Pitfall 4) rather than rebuilding a reverse lookup from scratch.
└── ...
fonts/                  # NEW directory, does not exist yet.
├── LiberationSans-Regular.ttf / -Bold.ttf / -Italic.ttf / -BoldItalic.ttf
├── LiberationSerif-*.ttf
├── LiberationMono-*.ttf
└── LICENSE-OFL.txt      # one copy; Liberation's OFL text (already present at
                        # spike/fixtures/LiberationSans-OFL-LICENSE.txt, verified)
```

### Pattern 1: Instruction-identity content-stream surgery, not byte-range splicing

**What:** Rather than computing "the byte range from the run's first operator to its last operator
and replacing that span," parse the target `/Contents` part into pikepdf's instruction list
(`pikepdf.parse_content_stream`), identify which *instructions* (not bytes) the run touches, and
replace/delete by **instruction identity**: the run's first touched instruction becomes the new
`Tj`/`TJ`; every other touched instruction is removed from the list; everything else (including
another run's own instructions that may sit between them — measured to happen in ~1.1% of
editable runs, § Pitfall 2) is left completely untouched, in its original relative position.

**When to use:** Always, for any run — this subsumes the single-operator case (list of touched
instructions has length 1) without a special case.

**Why not byte-range replacement:** Measured directly this session — see Pitfall 1 and Pitfall 2.
A byte-range approach also cannot be made safe by "just checking for disallowed operators in the
range" (this was tried, see Pitfall 2's methodology note): the real hazard is a run's own operators
being non-contiguous, not merely "something scary is nearby."

**Correlating a byte-offset-addressed run to pikepdf's byte-offset-free instruction list:** This
is the one piece of this pattern that is **not yet proven** and is this phase's own version of
Phase 1's TJ-refit spike — a small, cheap thing to prototype and measure *before* committing
engineering time to the full rewrite engine. The recommended approach (reasoned, not yet measured):
walk the SAME stream part with playa (already done — this is exactly how `RunIndex` built the
`GlyphRecord`s in the first place) to get the run's own **ordinal position among text-showing
operators** (the Nth `Tj`/`TJ`/`'`/`"` operator in stream order, counting from the sorted, deduped
set of every `operator_byte_offset` on that part). Independently walk `pikepdf.parse_content_stream`'s
instruction list and assign the same incrementing ordinal to every text-showing instruction. Both
are linear scans of the *same* bytes in the *same* order; assuming pikepdf's and playa's
tokenizers agree on operator boundaries (they should, for well-formed content — this is the part
to verify empirically against the corpus early), the Nth-text-operator ordinal is a stable bridge
between the two representations without ever needing byte offsets from pikepdf.

```python
# Source: synthesized from engine/identity_rewrite.py's own per-instruction pattern +
# this session's direct measurement of operator ordinals via GlyphRecord.operator_byte_offset
def touched_instruction_indices(
    stream_bytes: bytes,        # the target /Contents ARRAY ELEMENT's own decoded bytes
    instructions: list,         # pikepdf.parse_content_stream(...) result for the SAME bytes
    run_operator_offsets: set[int],   # from run.glyphs[i].operator_byte_offset, this run only
    all_operator_offsets_sorted: list[int],  # every distinct operator_byte_offset on this part
) -> list[int]:
    """Map this run's own operator byte offsets to pikepdf instruction-list indices, via
    ordinal position among text-showing operators -- NOT byte offset (pikepdf exposes none)."""
    text_ops = {"Tj", "TJ", "'", '"'}
    ordinal_of_offset = {off: i for i, off in enumerate(all_operator_offsets_sorted)}
    wanted_ordinals = {ordinal_of_offset[off] for off in run_operator_offsets}

    result = []
    seen = 0
    for idx, instr in enumerate(instructions):
        if str(instr.operator) in text_ops:
            if seen in wanted_ordinals:
                result.append(idx)
            seen += 1
    return result
```

### Pattern 2: Shape twice — once against the bundled font (to learn what's needed), once against the subset (to get final CIDs)

**What:** D-13 requires subsetting once, over the whole recipe's glyph union, at save time — which
means the width-fit ladder (step 3, run per-edit) necessarily runs *before* the subset exists, but
the CIDs written into the content stream must reference the *subset's* glyph order (step 6, after
subsetting).

**Verified directly this session:**
```python
# Source: this session's local verification (subset_probe.py + a second uharfbuzz probe)
# Step A (before subsetting exists): shape against the FULL bundled font to learn which
# glyphs a run's replacement text needs, and their kerned advance for the fit ladder.
import uharfbuzz as hb
font = hb.Font(hb.Face(hb.Blob.from_file_path("fonts/LiberationSans-Regular.ttf")))
buf = hb.Buffer(); buf.add_str("Hello"); buf.guess_segment_properties()
hb.shape(font, buf)
needed_glyph_names = {face_glyph_order[info.codepoint] for info in buf.glyph_infos}  # pre-subset GIDs

# ... collect needed_glyph_names across the WHOLE recipe, per family, then subset once (D-13) ...

# Step B (after the subset exists): shape the SAME text again, now against the SUBSET.
# VERIFIED: post-shape info.codepoint values are EXACTLY the subset's own new GIDs --
# gid=7 for 'H', 12 for 'e', 15 for 'l' (x2), 17 for 'o', matching fontTools'
# subset_font.getGlyphID(name) exactly, zero translation needed.
font2 = hb.Font(hb.Face(hb.Blob.from_file_path("subset_output.ttf")))
buf2 = hb.Buffer(); buf2.add_str("Hello"); buf2.guess_segment_properties()
hb.shape(font2, buf2)
cids_to_write = [info.codepoint for info in buf2.glyph_infos]  # == [7, 12, 15, 15, 17]
```
**Why this matters:** fontTools' default subsetting **renumbers** glyph IDs into a compact new
order (verified: 2620 glyphs → 9, with `H` moving from GID 43 to GID 2). Glyph **names** survive
subsetting unchanged; GIDs do not. Writing step A's pre-subset GIDs directly into the Type0 font's
content stream would silently render the **wrong glyphs** — a confident-wrong result that width
checks alone would not reliably catch. `retain_gids=True` is available and would avoid the
renumbering, but produces a much larger sparse font (86 glyphs' worth of table space for 9 real
glyphs, measured) with no benefit here, since D-13's one-subset-per-document-per-family design has
no cross-save GID-stability requirement to protect. **Recommend `retain_gids=False` (the
default).**

### Pattern 3: Tz save/restore via explicit re-assertion, not q/Q bracketing

**What:** Tz (horizontal scaling) is a **text state parameter** — per ISO 32000-1 §9.3, it is part
of the graphics state (Table 51 references Table 104's text state parameters), is **not** reset by
`BT` (unlike the text matrix `Tm`/`Tlm`, which §9.4.1 explicitly does reset at every `BT` — a
different, narrower set of "three parameters" than the text state as a whole), and persists across
text objects and even page content until changed again or the enclosing `q`/`Q` is popped.
`[MEDIUM-HIGH: well-established PDF spec structure, corroborated across multiple sources this
session, though no single fetched source gave the complete Table 104 persistence list verbatim]`

**Why not rely on `q`/`Q` bracketing:** There is a **documented, real spec ambiguity** in this
exact area — PDF Association issue `pdf-association/pdf-issues#368` (fetched this session) records
that whether `q`/`Q` inside a text object also saves/restores the **text matrix** is inconsistently
implemented across viewers (Acrobat and Chrome restore it; the issue implies others don't). That
ambiguity is specifically about `Tm`, not `Tz` — but since the two live in the same disputed
corner of the spec, the safer, simpler, fully unambiguous mechanism is to **never rely on `q`/`Q`
for this at all**: emit the condensed `Tz` value immediately before the run's replacement
text-showing operator, then emit the run's **original** `Tz` value (found by scanning backward for
the nearest preceding `Tz`, defaulting to `100` — the spec default — if none exists) immediately
after it, as a plain, explicit operator. `pikepdf.parse_content_stream`/`unparse_content_stream`
round-trips `Tz` as an ordinary numeric operator with no special handling
`[VERIFIED: local round-trip test, "90 Tz" -> parsed as Tz/[90] -> reserialized as "90 Tz"]` —
this is exactly the same per-instruction emission `identity_rewrite.py` already does for every
other operator, no new pikepdf capability needed.

```python
# Source: this session's verified local pikepdf round-trip + the spec reasoning above
# Pseudocode for step 7's Tz handling when the fit ladder chose the Tz rung:
new_instructions = [
    pikepdf.ContentStreamInstruction([condensed_scale], pikepdf.Operator("Tz")),
    pikepdf.ContentStreamInstruction([new_text_operand], pikepdf.Operator("Tj")),  # or TJ
    pikepdf.ContentStreamInstruction([original_scale], pikepdf.Operator("Tz")),  # explicit restore
]
```

**Claude's Discretion — recommendation on the exact floor and stacking question:** Pin the floor
at **90%** (the wide end of EDIT-03's own "90–95% is visually undetectable" band, since a wider
usable range directly reduces the refusal rate D-06/D-08 already care about measuring, and
CONTEXT.md's own wording treats the whole band as equally acceptable — there is no stated reason
to leave headroom inside it). Do **not** stack `Tz` with inter-word distribution: D-01's own
framing — "first rung that fits wins" — reads as mutually exclusive rungs by design, and stacking
two width-altering mechanisms on one run multiplies the surface area of D-04's post-run matrix
invariant check for no proven benefit. `[MEDIUM: reasoned recommendation, not independently
measured against the corpus — flag for confirmation, per CONTEXT.md leaving this open]`

### Pattern 4: The D-05 substitution trigger is NOT the same code path as Phase 2's `editable_substitution`

**This is the single most important architectural finding for FONT-06,** derived from directly
reading `engine/encoding_table.py`'s `resolve_font` dispatch (not assumed):

Phase 2's `editable_substitution` state is produced **exclusively** by `_resolve_type1`'s `T1-c`/
`T1-d` branches — i.e., **only** for a simple Type1/MMType1 font that is **not embedded in the
document at all**. `_resolve_truetype` never returns `substitution=True` (every branch is either
`editable=True, substitution=False` or a refusal); `_resolve_type0` never returns
`substitution=True` either (its `NOEMB` case is a straight refusal, not a substitution). This is
classification-time information Phase 2 already computed and `RunIndex` already exposes.

D-05/FONT-06's actual scenario — "a glyph missing from the embedded subset" — is a **completely
different, edit-time** question: a run can be `editable_original` (its font **is** embedded) at
classification time, and *still* need substitution once the user proposes specific replacement
text, if that text contains a character the embedded subset doesn't have a glyph for. Phase 2
cannot have pre-computed this, because Phase 2 does not know what the user will eventually type.

**What Phase 3 must build (does not exist anywhere in `engine/` today):** for every character in a
proposed replacement string, against the run's *own* font:
1. **Does this font's own encoding scheme even have a CODE for this Unicode character?** This is
   the *reverse* of `encoding_table.encoding_map()` (which already builds code→glyph-name for a
   font, overlaying `/Differences`) — needs the reverse (glyph-name→code) built from the *same*
   tables (`WIN_ANSI_ENCODING`, `STANDARD_ENCODING`, `MAC_ROMAN_ENCODING`, plus a font's own
   `/Differences`), keyed by AGL name via the same `UV2AGL` mapping `encoding_table.py` already
   imports. If there is no code at all (common — most simple-font encodings don't cover accented
   or non-Latin characters), this **alone** triggers substitution, independent of anything about
   the embedded subset.
2. **If a code exists, is that code's glyph actually present in the embedded program?** This reuses
   the *existing* `_glyph_present`/`glyph_presence` machinery directly (already built, already
   tested) — no new logic needed here, only a new caller.

If either check fails for *any* character in the proposed text, the **entire run** substitutes
(D-05). Corpus measurement (below, Pitfall 10) suggests check 1 will fire more often in practice
than check 2, since the phase's own headline scenario — "a character the document never
contained" — is usually a character the *original encoding* has no representation for at all, not
merely a glyph missing from an otherwise-adequate encoding.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Kerned text-shaping advances | A hand-rolled advance-width-plus-kerning-table walker | `uharfbuzz.shape()` | Already proven correct in Phase 1's spike; this is the industry-standard shaping engine (same one Chrome/Firefox use) |
| Font subsetting | Manual `glyf`/`hmtx`/`cmap` table surgery | `fontTools.subset.Subsetter` | Verified this session: produces an OTS-clean, correctly-metric'd 22-glyph subset from a 2620-glyph font in one call; hand-rolling this is exactly the kind of "deceptively complex problem" this table exists to name |
| Content-stream tokenizing (finding operator/operand boundaries, handling escaped/nested parens in strings) | A regex-based tokenizer over raw stream bytes | `pikepdf.parse_content_stream()` | Directly demonstrated this session: a crude regex tokenizer (built to measure operator interleaving) produced obvious false positives (English prose words like `"trust,"`, `"circle"` misidentified as operators) the moment it hit a literal string with genuinely nested balanced parens — exactly the trap `identity_rewrite.py`'s own design note already warns about |
| Font structural validation | A hand-written OpenType/TrueType table-integrity checker | `ots-sanitize` (OTS) | This is G2b's own literal acceptance criterion; also the same validator Chromium/Firefox run on every downloaded web font, so its false-negative rate on genuinely-broken output is externally battle-tested |
| ToUnicode CMap / Type0 dictionary shape | A novel CMap format invented for this project | The standard `Adobe-Identity-UCS` CMap shape (verified via WeasyPrint's actual source this session) | This is a fixed, spec'd format (ISO 32000-1 §9.10.3) with one well-known correct shape; inventing a variant risks silent incompatibility with exactly the viewers G2b tests against |
| The confined-diff check for G2a | A shell-out to `qpdf --qdf` + `diff` on the whole file | A targeted Python comparison of only the touched stream's decoded operator list (old vs new) | Measured this session: the whole-file approach produces 13,689 lines of unrelated noise for a one-word edit on an array-`/Contents` document — it does not, in practice, measure "confined to the edited operators" at all |

**Key insight:** every "don't hand-roll" item above was already implicitly decided by CLAUDE.md's
stack selection — the only place this project's engineers are at real risk of hand-rolling
something that already has a correct, chosen library is the *connective tissue* between those
libraries (operator-instruction correlation, the confined-diff check, the pre/post-subset GID
translation) — none of which are library problems, all of which are this phase's own new code, and
all of which are covered in Architecture Patterns above precisely because no library does them.

## Common Pitfalls

### Pitfall 1: Multi-operator runs are the norm (10.6%), not a rare edge case, and can span up to 167 operators

**What goes wrong:** A rewrite implementation built and tested against small, hand-picked,
single-`Tj` fixtures (the TJ-refit spike's own two test cases) will look correct until it hits a
run whose glyphs were originally emitted as many separate operators — extremely common in
practice.

**Why it happens:** D-01's own clustering rule (`engine/clusterer.py::_split_logical_runs`) never
breaks a run on "different operator" — it breaks only on font/size/color/visibility change and
gap-distance thresholds. A producer that emits one `Tj` per glyph with an intervening relative
`Td` (verified directly against `irs_form_1040.pdf`: `(F)Tj 0.567 0 Td (o)Tj 0.567 0 Td (r)Tj ...`)
produces exactly one visual run, addressed by one `run_id`, whose `glyphs` list spans dozens of
distinct `operator_byte_offset` values.

**Measured (this session, 217-document public corpus, 5 pages/doc cap, `RunIndex` +
`engine/classify_run.py`):** of 129,491 editable (`editable_original`/`editable_substitution`)
runs, **13,752 (10.62%) span more than one distinct operator**, with counts observed up to **167
distinct operators in a single run** and a concrete example of 62 operators for 63 glyphs (nearly
one operator per glyph).

**How to avoid:** Build and test the rewrite against instruction-identity surgery (Pattern 1)
from the start — never assume "the run is one `Tj`/`TJ` I can locate and replace in place."

**Warning signs:** A rewrite that only ever emits a `Tj`/`TJ` replacing exactly one prior
instruction, with no code path for "delete N-1 additional instructions," will corrupt or silently
fail on ~1 in 10 real edits.

### Pitfall 2: A run's own operators are not always stream-contiguous — something else can sit between them

**What goes wrong:** Even once Pitfall 1 is handled (consolidating N operators into one), a
"delete everything between the run's first and last byte offset" implementation is still unsafe,
because that byte range can contain **another run's own text**.

**Why it happens:** The clusterer groups glyphs by geometric/visual continuity (baseline, gap,
font/size/color), not by stream adjacency. Two runs can legitimately interleave in stream order
while never touching visually (e.g., a repeating form-field pattern, or content drawn in a
different z-order pass).

**Measured (this session, same corpus scan, precise integer-offset check — not the initial
regex-based check, which was demonstrably unreliable, see below):** of the 13,752 multi-operator
runs, **1,431 (10.4%, ≈1.1% of all editable runs) have at least one *other classified run's*
operator positioned strictly between their own first and last operator.** Examples found: a
`irs_form_w4.pdf` run repeated 3 times across the document with 16 foreign operators interleaved
each time; an `irs_1040_instructions.pdf` run ("Requirement To Reconcile Advan...", 57 of its own
operators) with 3 foreign operators interleaved. This is a **measured lower bound** — it only
detects interleaving with another *classified run's* operator, not interleaving with a bare
non-text operator (marked content, graphics state) that has no associated run at all.

**A methodology note worth recording:** the first attempt at this measurement used a regex-based
raw-byte tokenizer and found a wildly higher (and wrong) 50.3% rate — investigation showed the
false positives were literal English words (`"trust,"`, `"circle,"`, `"pension"`) leaking through
because the regex's naive `\([^()]*\)` string-stripping cannot handle a literal PDF string
containing genuinely **nested, balanced, unescaped parentheses** (legal PDF syntax). This is
recorded here specifically because it is exactly the trap Pattern 1 and the Don't-Hand-Roll table
warn against for the *real* rewrite implementation, encountered firsthand while researching it.

**How to avoid:** Never compute a "span" at all. Use Pattern 1's instruction-identity approach,
which handles this case for free — deleting the run's own touched instructions one at a time, by
list index, leaves anything else at intervening indices completely undisturbed.

**Warning signs:** A rewrite that passes every single-run, single-document hand-test but corrupts
unrelated text specifically on repeating-structure documents (forms, tables) is hitting this.

### Pitfall 3: Coalescing `/Contents` (the established `identity_rewrite.py` pattern) breaks G2a's own diff-confinement criterion

**What goes wrong:** `engine/identity_rewrite.py` always collapses a page's `/Contents` array into
one stream (`page.Contents = pdf.make_stream(new_bytes)`), which is correct for that module's own
purpose (proving a round-trip) but is the **wrong default to copy** for the real rewrite engine.

**Why it happens:** Collapsing an N-element array into 1 stream deletes N−1 indirect objects,
which shifts **every subsequent object's number** in the file. `qpdf --qdf`'s per-object text
block for every one of those renumbered objects then differs between old and new, even though
nothing about them actually changed.

**Measured directly this session** (`qpdf 12.4.0`, `spike/fixtures/tj_refit_sample.pdf`, an 8-part
`/Contents` array, one `Tj` string mutated): `qpdf --qdf --object-streams=disable
--no-original-object-ids` on both the original and the mutated-and-coalesced file, then
`diff -a`, produced **13,689 lines of diff** for a single-word text change — dominated by object
renumbering cascading through image/font/annotation objects that were never touched, plus
incidental XMP-metadata whitespace/attribute-order reformatting unrelated to the edit. 114 of 217
corpus documents (52.5%) have an array `/Contents`, so this is not a rare shape.

**How to avoid:** Never reshape `/Contents`. If it's an array, replace only the specific element(s)
containing edited runs (`contents[part_index] = pdf.make_stream(new_bytes)`), leaving the array's
own length and every other element's object number untouched. For G2a's CI assertion, implement
the "confined diff" as a **targeted comparison**: decode and compare only the touched part's own
operator list (old vs new, via `pikepdf.parse_content_stream` on each), not a whole-file text diff.

**Warning signs:** A G2a check that "always" reports a huge diff (teaching engineers to ignore it)
or one that only ever gets tested against single-stream-`/Contents` fixtures and never against the
52.5% of the corpus with array `/Contents`.

### Pitfall 4: Phase 2's `editable_substitution` state is not the same trigger as D-05/FONT-06 — see Pattern 4

Restated here as a pitfall because it is easy to miss: a naive implementation might read
`RunVerdict.state == "editable_substitution"` as "this run needs the bundled font" and stop there,
never checking `editable_original` runs for the *edit-time* per-character glyph-availability
question. That would silently fail the phase's own headline scenario — "including with a character
the document never contained" — for the majority case (an embedded font that's simply missing one
new glyph), while only correctly handling the minority case (a wholly non-embedded font). See
Architecture Patterns, Pattern 4, for the full mechanism.

### Pitfall 5: Pre-subset glyph IDs are not post-subset glyph IDs — glyph NAME is the only stable key

**What goes wrong:** Shaping replacement text against the *original* bundled font (needed early,
to know which glyphs a run requires, before the once-per-document subset exists per D-13) yields
glyph IDs that do **not** match the IDs in the font that actually gets embedded.

**Measured directly this session:** `fontTools.subset.Subsetter` (default options) renumbers a
2620-glyph font's glyph order into a compact 9-glyph order for a 5-character input — `H` moves
from GID 43 to GID 2. Glyph **names** (`H`, `e`, `l`, `o` …) are preserved unchanged by
subsetting; GIDs are not.

**How to avoid:** Use glyph name as the stable cross-subsetting key (fontTools exposes
`font.getGlyphID(name)` on both the pre- and post-subset font objects), or — simpler and also
verified this session — **shape twice**: once against the original bundled font (to learn which
glyphs/widths are needed, feeding the fit ladder and the glyph-union collection), and again against
the *already-subsetted* font once it exists (Pattern 2), taking that second shaping pass's glyph
IDs directly as the CIDs to write. No manual GID translation table is then needed at all.

**Warning signs:** Correct-looking widths (a wrong-but-similarly-wide glyph can pass a width-only
check) paired with visually wrong glyphs in the rendered contact sheet (D-08's own review step) —
this is exactly the kind of bug D-08's *human* review exists to catch precisely because a purely
mechanical width check would not.

### Pitfall 6: `uharfbuzz` has no type stubs — mypy strict will fail the moment `engine/` imports it

**What goes wrong:** The project's binding rule is mypy strict with zero `# type: ignore` in
`engine/`. `uharfbuzz` ships no `py.typed` marker and no stub package.

**Verified directly this session:** `grep -rn "import uharfbuzz" engine/` currently returns
nothing — Phases 1–2 never imported it inside `engine/` (only in `spike/`, outside strict mypy's
`files = ["engine"]` scope). A reproduction test (adding a bare `import uharfbuzz as hb` to a file
under `engine/` and running `mypy engine/`) fails immediately: `error: Skipping analyzing
"uharfbuzz": module is installed, but missing library stubs or py.typed marker
[import-untyped]`.

**How to avoid:** Add a new `[[tool.mypy.overrides]]` block for `uharfbuzz.*` to `pyproject.toml`,
mirroring the existing `fontTools.*` entry exactly, as one of the first setup tasks in this phase
— before writing the module that imports it, not after mypy fails.

```toml
# Add alongside the existing fontTools override in pyproject.toml
[[tool.mypy.overrides]]
module = ["uharfbuzz.*"]
ignore_missing_imports = true
```

**Warning signs:** `mypy engine/` failing on the first commit that touches shaping, with a
confusing "just add `# type: ignore`" temptation that would violate the project's own zero-escape-
hatch rule.

### Pitfall 7: `/Widths` must be read via pikepdf (the PDF dictionary), never via fontTools (the font program) — restated, not re-derived

Already proven and documented in `TJ-REFIT-RESULTS.md`/`spike/tj_refit_prototype.py`
(`read_original_advance_pt`'s own docstring: "the PDF font DICTIONARY's `/Widths` entry, not the
embedded font program's own metrics — the two are allowed to disagree and the dictionary is what
viewers actually use"). Restated here as a pitfall specifically because it is the kind of thing a
well-intentioned refactor ("let's read widths consistently via fontTools since we already import
it for subsetting") would silently reintroduce. The rewrite engine's original-run-width reader
must stay on the pikepdf/`/Widths`-or-`/W` path; fontTools is only for the *replacement* font's
own metrics.

### Pitfall 8: OTS genuinely rejects real font-tool output on real structural bugs — treat it as a development-time check, not a final gate

**What goes wrong:** Running OTS only once, at the very end of the phase, against fully-assembled
output means a structural bug introduced anywhere in the subsetting/embedding pipeline is
discovered as late and as expensively as possible.

**Evidence this is a real risk, not theoretical:** a documented external case (`fontmin`, a
Node.js font subsetting tool, fetched this session) shows OTS rejecting that tool's subsetted
output with genuine `layout table`/`post table` parsing errors — i.e., subsetting tools *can* and
*do* produce structurally invalid output OTS correctly catches.

**Reassuring counter-evidence, also verified this session:** `fontTools.subset.Subsetter`'s output
against `LiberationSans-Regular.ttf` passed OTS cleanly on the first attempt, both for the full
font and for a 22-glyph subset — so this is not a known landmine for this specific
library/font pairing, but the general risk class is real.

**How to avoid:** Run `ots-sanitize` as part of the development loop (e.g., a quick local check
after every subset call during implementation), not only in the final CI gate.

### Pitfall 9: fontTools prints warnings, not errors, to stdout during normal operation — don't mistake noise for failure, and verify none of it leaks document content

**What goes wrong:** Subsetting a real font produces lines like `FFTM NOT subset; don't know how
to subset; dropped` (an Apple-specific FontForge-timestamp table, harmlessly dropped) and, on the
full unsubsetted font, `WARNING: glyf: Glyph bbox was incorrect; adjusting (glyph 2212)` from OTS
itself — both benign, both observed directly this session.

**Why it matters for this project specifically:** CLAUDE.md's privacy discipline requires "no
document content in logs, assertion messages, or exception text." These particular warnings never
included glyph/text content in the cases observed (they reference table names and internal glyph
indices, not decoded text) — but this was only checked against the bundled Liberation fonts, never
against an arbitrary *original* embedded font from a user's uploaded document (out of this phase's
CLI-only scope, but a real concern the moment Phase 4 exists). Verify this holds for whatever
fontTools/OTS operations this phase adds, and route their stdout through the same content-free
logging discipline already established elsewhere in `engine/`.

### Pitfall 10: The mapping table's real-world coverage need is narrower and more concrete than it first looks — corpus-measured

**What goes wrong:** Designing the static mapping table (D-06/FONT-01) from first principles risks
either under-covering the common case or over-building fuzzy matching that violates D-06's own
"never a heuristic" rule.

**Measured directly this session** (every font resource across the corpus, resolved through the
existing `resolve_font`, filtered to `editable=True, substitution=True`):
- **~660+ occurrences** are the **exact, literal Base-14 PostScript names**
  (`Helvetica`/`-Bold`/`-Oblique`/`-BoldOblique`, `Times-Roman`/`-Bold`/`-Italic`/`-BoldItalic`,
  `Courier`/`-Bold`/`-Oblique`/`-BoldOblique`, `Symbol`, `ZapfDingbats`) — these need **only an
  exact-match lookup**, no name parsing or fuzzy matching at all, and weight/style is already
  baked into the 12 non-symbol names (Helvetica/Times/Courier families × regular/bold/italic/
  bolditalic = 12 entries covering the overwhelming majority of substitution volume).
- `Symbol` (20) and `ZapfDingbats` (9) have **no Liberation equivalent** and correctly refuse by
  name under D-06 — this is expected, correct behavior (there is no sane "substitute" for a
  symbol font), not a coverage gap to close.
- A **long tail (~70 occurrences)** of exotic non-Base-14 names appear (`AvantGarde-*`,
  `AGaramond-*`, `Palatino-*`, `StoneSans/Serif/Informal-*`, `Meridien-*`, `Futura*`,
  `Univers-*`, `NewCenturySchlbk-*`, `Bookman-*`, `GillSans*`, `HelveticaNeue-*`) — these have no
  Liberation mapping and also correctly refuse under D-06.
- MS-core-font name variants (`Arial`, `Arial,Bold`, `ArialMT`, `Arial-BoldMT`, `TimesNewRoman`,
  `TimesNewRoman,Bold`, `TimesNewRomanPSMT`, `TimesNewRomanPS-BoldMT`, etc.) **do appear frequently
  in the corpus** (dozens of occurrences each) but in **every observed case are embedded** in this
  specific 217-document corpus, so none of them actually reach the substitution path here.
  **Recommend covering them in the table anyway** as a low-cost, forward-looking robustness
  measure — non-embedded Arial/Times-New-Roman-named text is common in the broader PDF ecosystem
  beyond this corpus (this is precisely CLAUDE.md's own stated rationale for choosing Liberation),
  and the cost is only a handful of additional exact-match dictionary entries, not new logic.

**How to avoid over-building:** Since weight/style is baked directly into every observed name
(`Helvetica-Bold`, `Arial,Bold`, `Arial-BoldMT` are each a complete, distinct string — not
`Helvetica` + a "look for the word bold" parse step), the recommended mapping table is a **flat,
finite, enumerated dictionary of known exact-or-normalized spellings → (bundled family, weight,
style)**, never a substring/regex heuristic on the raw BaseFont name. This satisfies D-06's "never
a heuristic" constraint literally, not just in spirit.

### Pitfall 11: Liberation's `fsType` was verified clean for Sans — Serif and Mono still need the same direct check once they exist

**What goes wrong:** Assuming "Liberation is OFL, so `fsType` must be fine" without checking, or
conversely over-trusting the roadmap's generic "frequently contradict" warning without checking
the *specific* files actually being bundled.

**Verified directly this session** (`fontTools.ttLib.TTFont`, `spike/fixtures/LiberationSans-Regular.ttf`):
`OS/2.fsType == 0` (Installable Embedding, no restriction) — consistent with the font's own `name`
table entries ("Licensed under the SIL Open Font License, Version 1.1") and with the upstream
project's changelog (`liberationfonts/liberation-fonts`, fetched this session: "set fsType bit to
0, Installable Embedding is allowed", v2.00.3, 2012-07-06) — this specific concern does **not**
apply to the currently-bundled Sans build.

**How to avoid the residual risk:** Serif and Mono are not yet in the repository (only Sans
exists, borrowed from the Phase 1 spike). Run the identical check the moment they're fetched, from
the **same source/version lineage** (GitHub releases of `liberationfonts/liberation-fonts`, not a
different redistribution or an older Ascender-era build):
```python
# Source: this session's direct verification method, reusable as-is
from fontTools.ttLib import TTFont
for path in ["fonts/LiberationSerif-Regular.ttf", "fonts/LiberationMono-Regular.ttf", ...]:
    f = TTFont(path)
    assert f["OS/2"].fsType == 0, f"{path}: fsType={f['OS/2'].fsType}, expected 0 (Installable)"
```

### Pitfall 12: Type3 substitution is not this phase's problem — `classify_run` already guarantees it never arrives

Not a trap so much as a reassurance worth stating explicitly, since it's easy to wonder whether
the substitution path needs a Type3 case: `engine/classify_run.py::classify_run` refuses every
Type3 run unconditionally (`if font_verdict.branch_id == "T3-a": return RunVerdict("not_editable",
"Type3")`), checked *before* the font's own editability, and *before* RTL/glyph-level checks.
Type3 runs never reach `editable_original` or `editable_substitution` at all — the rewrite engine
will never see one as an edit target. No Type3-aware substitution logic is needed anywhere in this
phase.

## Code Examples

### Type0/CIDFontType2 dictionary shape (FONT-03), verified against WeasyPrint's actual source

```python
# Source: WeasyPrint (github.com/Kozea/WeasyPrint, weasyprint/pdf/fonts.py, BSD-3-Clause,
# fetched and quoted verbatim this session) -- shown here in its own pydyf-object form as the
# STRUCTURAL reference; translate key-for-key into pikepdf.Dictionary/Array/Name/String for
# this project's own writer.

# The Type0 (composite) font dictionary itself:
font_dictionary = {
    'Type': '/Font',
    'Subtype': '/Type0',
    'BaseFont': subset_tag_plus_name,        # e.g. "/ABCDEF+LiberationSans"
    'Encoding': '/Identity-H',
    'DescendantFonts': [subfont_dictionary],  # one-element array
    'ToUnicode': to_unicode_stream_ref,
}

# The CIDFont (descendant) dictionary:
subfont_dictionary = {
    'Type': '/Font',
    'Subtype': '/CIDFontType2',               # TrueType-flavored (Liberation is TrueType)
    'BaseFont': subset_tag_plus_name,
    'CIDSystemInfo': {
        'Registry': '(Adobe)', 'Ordering': '(Identity)', 'Supplement': 0,
    },
    'CIDToGIDMap': '/Identity',                # matches engine/encoding_table.py's own
                                                # _cid_to_gid_map_ok() reader exactly
    'W': pdf_widths,                           # see below
    'FontDescriptor': font_descriptor_ref,
}
```
Cross-checked against this project's **own existing reader**: `engine/encoding_table.py`'s
`_resolve_type0`/`_cid_to_gid_map_ok`/`cid_width` already expect exactly this shape (`Subtype
/CIDFontType2` → branch `C-3a`; `/CIDToGIDMap /Identity` → `_cid_to_gid_map_ok` returns `True`;
`/Encoding /Identity-H` → `_codespace_widths` resolves via its `{2}` shortcut) — what this phase
writes and what Phase 2's own code already reads agree without any changes to the reader.

### `/W` array construction (FONT-04)

```python
# Source: WeasyPrint weasyprint/pdf/fonts.py, quoted verbatim this session (BSD-3-Clause)
pdf_widths = []  # -> pikepdf.Array in this project's own writer
for i in sorted(widths):          # widths: dict[cid, advance_in_1000ths_em]
    if i - 1 not in widths:
        pdf_widths.append(i)
        current_widths = []       # -> pikepdf.Array
        pdf_widths.append(current_widths)
    current_widths.append(widths[i])
# Produces the "[c [w1 w2 w3 ...]]" run-grouped form -- already handled by this project's
# OWN existing reader, engine/encoding_table.py::cid_width (its `isinstance(nxt, pikepdf.Array)`
# branch), with no reader changes needed.
```

### ToUnicode CMap stream (FONT-03)

```python
# Source: WeasyPrint weasyprint/pdf/fonts.py, quoted verbatim this session (BSD-3-Clause)
# Fixed boilerplate header (Adobe-Identity-UCS is the standard CMap name for this purpose --
# NOT the same CIDSystemInfo as the font's own, which uses Ordering=Identity, not Ordering=UCS):
HEADER = [
    b'/CIDInit /ProcSet findresource begin', b'12 dict begin', b'begincmap',
    b'/CIDSystemInfo', b'<< /Registry (Adobe)', b'/Ordering (UCS)', b'/Supplement 0', b'>> def',
    b'/CMapName /Adobe-Identity-UCS def', b'/CMapType 2 def',
    b'1 begincodespacerange', b'<0000> <ffff>', b'endcodespacerange',
]
# Then beginbfchar/endbfchar blocks, batched at 100 entries per block (Adobe's own documented
# cap on codespacerange/bfchar block size -- engine/encoding_table.py's own
# _parse_codespace_widths docstring already names this same 100-range cap for the READ side):
#   "<{gid:04x}> <{utf16be_hex}>"
TRAILER = [b'endcmap', b'CMapName currentdict /CMap defineresource pop', b'end', b'end']
```

### Fresh subset tag (FONT-05)

```python
# Source: WeasyPrint weasyprint/pdf/fonts.py, quoted verbatim this session (BSD-3-Clause)
from hashlib import md5
tag = ''.join(chr(65 + b % 26) for b in md5(description_string.encode(), usedforsecurity=False).digest()[:6])
# 6 uppercase letters, deterministic per (family, subset-content) description string --
# satisfies FONT-05's "fresh tag per re-subset" directly since D-13 subsets once per family
# per document: a different glyph union naturally hashes to a different tag.
```

### fontTools subsetting call (FONT-02), the exact pattern verified this session

```python
# Source: this session's local verification (subset_probe.py), fontTools 4.63.0
from fontTools.ttLib import TTFont
from fontTools import subset

font = TTFont("fonts/LiberationSans-Regular.ttf")
options = subset.Options()
options.set(notdef_outline=True, recommended_glyphs=False, desubroutinize=False)
# retain_gids left at its default (False) -- see Pattern 2/Pitfall 5 for why.
subsetter = subset.Subsetter(options=options)
subsetter.populate(text=needed_text)   # or glyphs=[...] / unicodes={...} for a precise union
subsetter.subset(font)
font.save(output_path)
# VERIFIED this session: 410,712 -> 9,172 bytes (97.8% reduction) for a 22-glyph subset;
# output passes `ots-sanitize` cleanly with zero warnings.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|-------------------|---------------|--------|
| Byte-level round-trip diffing to prove a rewrite is correct | Structural re-extraction comparison (re-walk and compare run maps, never raw bytes) | Established in Phase 2 (`02-RESEARCH.md` §9); this research adds the same discipline to G2a's own diff check, which the roadmap's literal wording could be misread as requiring byte-level | The `qpdf --qdf` diff (Pitfall 3) is meaningful only as a *targeted* structural comparison, never a whole-file byte/text diff |
| `hb-subset` preferred over `fontTools.subset` for production font tooling | Both remain viable; `fontTools.subset` verified sufficient and OTS-clean for this project's scale (per-document, not per-request) | Observed as an ecosystem opinion in WeasyPrint's own current source comments (fetched this session) | Do not add `hb-subset` as a new dependency without a measured throughput problem — `fontTools.subset` is already pinned and proven |
| Append-only / overlay "editing" (pdf-lib and forks) | Content-stream token rewrite (pikepdf/qpdf) | Already the project's founding premise (CLAUDE.md) | Not new information, restated only to note this phase is where that premise gets exercised for the first time on a real edit, not just an identity transform |

**Deprecated/outdated:** Nothing library-specific is deprecated for this phase's purposes; every
pinned version (pikepdf 10.11.0, fontTools 4.63.0, uharfbuzz 0.56.0, qpdf 12.4.0) is current and
was verified installed and working this session.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|----------------|
| A1 | The 90% Tz floor and "don't stack Tz with inter-word distribution" recommendation | Pattern 3 | Low — this is explicitly Claude's Discretion in CONTEXT.md; if wrong, only the exact floor number or ladder-stacking behavior needs adjustment, not the underlying save/restore mechanism, which is independently verified |
| A2 | Recommended module boundary (`engine/fit.py`, `engine/fonts.py`, `engine/rewrite.py`, `engine/recipe.py`) | Recommended Project Structure | Low — explicitly Claude's Discretion; purely organizational, does not affect correctness |
| A3 | Instruction-ordinal correlation (playa's operator ordinal ↔ pikepdf's instruction-list ordinal) will hold across the corpus | Pattern 1 | Medium — this is the one piece of the recommended architecture not yet directly measured (unlike Pitfalls 1–3, which were). If pikepdf's and playa's tokenizers ever disagree on operator-boundary counts for some malformed/unusual stream, the correlation breaks silently. **Recommend a small early-phase prototype measuring this against the corpus, mirroring how Phase 1's TJ-refit spike de-risked the width math before Phase 2 built on it.** |
| A4 | Recommending Base-14 + common MS-core-font name variants as the mapping table's starting coverage | Pitfall 10 | Low — corpus-measured for Base-14; the MS-core-font recommendation is forward-looking (zero occurrences of *non-embedded* Arial/TimesNewRoman-named fonts in this specific corpus) and costs only a few extra dictionary entries if wrong |
| A5 | fontTools/OTS warning text never includes document glyph/text content | Pitfall 9 | Low-medium — verified only against the bundled Liberation fonts in this session, not against arbitrary uploaded fonts (out of this CLI-only phase's scope, but relevant the moment Phase 4 exists) |

## Open Questions

1. **Does the instruction-ordinal correlation (Pattern 1/Assumption A3) hold on every corpus
   document, or are there streams where pikepdf's and playa's operator counts disagree?**
   - What we know: both are linear, single-pass tokenizers over the same bytes; in principle they
     should agree on operator-boundary counts for well-formed content.
   - What's unclear: whether any of the corpus's 17 malformed documents, or any real-world
     document Phase 3 hasn't seen yet, produces a case where they don't.
   - Recommendation: a small, cheap corpus-wide prototype early in the phase (exactly analogous to
     Phase 1's TJ-refit spike) — for every run in every document, confirm the ordinal-based lookup
     lands on a text-showing instruction of the expected operator type. This is the one piece of
     the recommended architecture genuinely worth a dedicated, gated proof before the full rewrite
     engine is built on top of it.

2. **What is the actual measured advance-delta between Liberation's own metrics and the specific
   non-embedded Standard-14 fonts it substitutes for, to pin D-08's "near-zero" metric threshold
   to an actual number?**
   - What we know: Liberation is *designed* to be metric-compatible with Arial/Times New
     Roman/Courier New, and the TJ-refit spike measured Δ=0.0000pt for a Liberation-vs-original
     substitution on one real run.
   - What's unclear: a systematic, corpus-wide per-glyph advance comparison between Liberation's
     own `hmtx` and the actual `/Widths` of the Standard-14-named (not embedded) fonts in the
     corpus has not been done — this session verified the *mechanism* (fontTools subsetting, OTS
     validation) but not this specific *number*.
   - Recommendation: measure directly, early in the phase, using the same corpus documents that
     produced the Pitfall 10 substitution-name survey — for each `editable_substitution` run,
     compare its own `/Widths`-derived advances against Liberation's `hmtx` advances for the same
     characters, and pin D-08's threshold to the observed distribution (matching this project's
     own "measure, then pin, never guess" convention).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|--------------|-----------|---------|----------|
| Python | Engine runtime | ✓ | 3.13.7 | — |
| pikepdf | Content-stream surgery | ✓ | 10.11.0 (matches pin) | — |
| fontTools | Subsetting | ✓ | 4.63.0 (matches pin) | — |
| uharfbuzz | Shaping | ✓ | 0.56.0 (matches pin) | — |
| qpdf CLI | G2a's `--check`/`--qdf` gates | ✓ | 12.4.0 local; **12.2.0-1 pinned in Dockerfile.ci — version gap, reconcile** | — |
| `ots-sanitize` (OTS) | G2b's font-validation gate | ✗ (not installed by default) | — | `pip install opentype-sanitizer` (verified working) for local dev; add `opentype-sanitizer` apt package to `Dockerfile.ci` for CI (verified available for Debian trixie) |
| `fonts/LiberationSans-*.ttf` (Bold/Italic/BoldItalic) | FONT-01 bundle | ✗ (only Regular exists, in `spike/fixtures/`) | — | Fetch from `github.com/liberationfonts/liberation-fonts` releases |
| `fonts/LiberationSerif-*.ttf`, `fonts/LiberationMono-*.ttf` | FONT-01 bundle | ✗ (do not exist at all) | — | Same source as above |

**Missing dependencies with no fallback:** none — every missing item above has a verified,
concrete fallback (pip/apt install, or a named authoritative download source).

**Missing dependencies with fallback:** OTS (pip or apt, both verified this session); Liberation
Serif/Mono/Sans-variant font files (single named authoritative source, matching the already-
verified Sans build's lineage).

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
| EDIT-02 | Replacement text refitted, text matrix after run unchanged within epsilon (D-04 guard) | unit + corpus | `pytest tests/test_rewrite.py::test_edit02_matrix_invariant_holds_after_fit -x` | ❌ Wave 0 |
| EDIT-02 | Multi-operator run consolidation (Pitfall 1/2) | unit, using the exact `irs_form_1040.pdf`/`irs_form_w4.pdf` examples measured this session as fixtures | `pytest tests/test_rewrite.py::test_multi_operator_run_consolidates_to_one_instruction -x` | ❌ Wave 0 |
| EDIT-02 | Non-contiguous run (another run's operator interleaved) handled without corrupting the foreign run | unit, negative case | `pytest tests/test_rewrite.py::test_foreign_interleaved_operator_survives_unedited -x` | ❌ Wave 0 |
| EDIT-03 | Tz condensing within 90–95%, save/restore correct, subsequent text unaffected | unit | `pytest tests/test_fit.py::test_tz_condensing_restores_scale_after_run -x` | ❌ Wave 0 |
| EDIT-03 | Dry-run report matches actual commit outcome | integration (CLI) | `pytest tests/test_pdftool_edit.py::test_dry_run_matches_commit -x` | ❌ Wave 0 |
| EDIT-04 | Named refusal reasons for every failure mode (unmapped font, won't-fit, matrix violation, hash mismatch) | unit | `pytest tests/test_recipe.py::test_refusal_reasons_are_named_not_generic -x` | ❌ Wave 0 |
| FONT-01 | Static mapping table, exact-match only, no heuristic | unit | `pytest tests/test_fonts.py::test_mapping_table_is_exact_match_no_fuzzy_logic -x` | ❌ Wave 0 |
| FONT-01 | Corpus-wide substitution coverage measurement (restates Pitfall 10) | corpus | `pytest -m corpus tests/test_fonts.py::test_corpus_substitution_coverage_report -x` | ❌ Wave 0 |
| FONT-02 | Subsetting over whole-recipe glyph union, once per family | unit | `pytest tests/test_fonts.py::test_subset_covers_union_across_recipe -x` | ❌ Wave 0 |
| FONT-02 | Untouched text using the same font still renders correctly after re-subset (roadmap criterion 3) | corpus + pixel-diff | `pytest -m corpus tests/test_rewrite.py::test_untouched_same_font_text_unaffected_by_resubset -x` | ❌ Wave 0 |
| FONT-03 | Emitted font passes OTS | unit (subprocess) | `pytest tests/test_fonts.py::test_emitted_font_passes_ots -x` | ❌ Wave 0 |
| FONT-03 | ToUnicode round-trips correctly (copy-paste proxy) | unit | `pytest tests/test_fonts.py::test_tounicode_cmap_roundtrips_ascii_and_accented -x` | ❌ Wave 0 |
| FONT-04 | `/W` entries match subset `hmtx`; no silent `/MissingWidth`-of-0 | unit, negative case | `pytest tests/test_fonts.py::test_font04_missing_width_never_falls_through_silently -x` | ❌ Wave 0 |
| FONT-05 | Two subsets of the same family in one document get distinct tags | unit | `pytest tests/test_fonts.py::test_fresh_subset_tag_per_family -x` | ❌ Wave 0 |
| FONT-06 | Whole-run substitution, never half; the NEW edit-time glyph-availability check (Pattern 4) fires on `editable_original` runs too, not just `editable_substitution` | unit, negative case | `pytest tests/test_fonts.py::test_editable_original_run_still_substitutes_on_missing_glyph -x` | ❌ Wave 0 |
| G2a | `qpdf --qdf` confined-diff check, targeted (not whole-file) | integration | `pytest tests/test_gate_g2a.py::test_confined_diff_isolated_to_edited_stream -x` | ❌ Wave 0 |
| G2b | Full pipeline: substitute a character absent from the subset, same-engine zero-tolerance + cross-engine tolerant pixel diff (reuse `harness/`) | corpus + pixel-diff | `pytest -m corpus tests/test_gate_g2b.py::test_g2b_full_pipeline -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run --frozen pytest -q -m "not corpus"` (fast unit tests, hand-picked
  fixtures — including the specific corpus documents/runs already identified by name in this
  research: `irs_form_1040.pdf` p0 run `:o1391`, `irs_form_w4.pdf` p0/p4 runs, the W9 sample from
  Phase 1's spike)
- **Per wave merge:** `uv run --frozen pytest -q` (includes `corpus`-marked full-sweep tests) +
  `uv run --frozen mypy engine/`
- **Phase gate:** Full suite green, plus the actual G2a/G2b harness runs (reusing
  `harness/masked_diff.py`, `harness/render_diff.py` unmodified), before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_fit.py` — the width-fit ladder, porting `tests/test_tj_refit_prototype.py`'s
      proven test cases (same fixture text, same expected deltas) onto the real module, per
      `TJ-REFIT-RESULTS.md`'s own stated carry-forward instruction
- [ ] `tests/test_fonts.py` — mapping table, subsetting, Type0/CIDFontType2 embedding, OTS
      integration
- [ ] `tests/test_rewrite.py` — content-stream surgery, using the exact multi-operator and
      non-contiguous-run examples measured this session as named regression fixtures
- [ ] `tests/test_recipe.py` — JSON recipe parsing, D-10/D-11 all-or-nothing application
- [ ] `tests/test_pdftool_edit.py` — CLI integration, dry-run vs commit
- [ ] `tests/test_gate_g2a.py`, `tests/test_gate_g2b.py` — the two phase gates as explicit,
      named tests, not just informal manual verification
- [ ] `pyproject.toml` — add the `uharfbuzz.*` mypy override (Pitfall 6) **before** any module
      under `engine/` imports uharfbuzz
- [ ] `fonts/` directory — does not exist; needs Liberation Sans (Bold/Italic/BoldItalic — Regular
      already exists), Serif (all 4), Mono (all 4), plus one shared OFL license file, plus the
      `fsType` verification script (Pitfall 11) run against all of them
- [ ] `Dockerfile.ci` — add the pinned `opentype-sanitizer` apt package

## Security Domain

CLI-only, no served endpoint, no network surface this phase (matches Phase 1/2's own established
posture) — most ASVS categories (Authentication, Session Management, Access Control) do not apply.
The one category that matters is input validation, because this phase's *inputs* (arbitrary PDFs,
embedded font programs) are exactly the kind of untrusted-origin bytes CLAUDE.md's "anyone can
open the site and edit a file, no accounts" posture means this same code will eventually process
from a genuinely hostile source in Phase 4 — hardening habits established here pay forward.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|--------------------|
| V2 Authentication | No | No accounts, no auth surface in this phase or product (CLAUDE.md) |
| V3 Session Management | No | Stateless CLI invocation |
| V4 Access Control | No | No multi-user/multi-tenant surface |
| V5 Input Validation | Yes | Recipe JSON: stdlib `json.load` (no `eval`, matching `engine/run_id.py`'s own existing strict-regex-never-`str.split` precedent for untrusted string parsing); embedded font programs already parsed defensively by `engine/encoding_table.py`'s existing try/except-and-classify pattern (never bare `except: pass`) — extend that same pattern to any *new* font-program parsing this phase adds |
| V6 Cryptography | No | No cryptographic operations in this phase (PDF encryption handling is out of scope here — noted as an open product question in prior research, not this phase's job) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|------------------------|
| Malformed/hostile embedded font program (in the *original* document being edited) crashes or hangs the subsetter/shaper | Denial of Service | Already the established pattern in `engine/encoding_table.py` (`_glyph_present`, `embedded_font_bytes`): wrap font-program parsing in `try/except Exception`, classify as "unusable" rather than crash, never a bare `except: pass`. Extend identically to any new font-program touchpoint this phase adds — do not assume the *original* document's fonts are well-formed just because the *bundled* fonts are |
| Recipe JSON with an implausibly large op count / string length, used to exhaust memory or CPU in a single `pdftool edit` invocation | Denial of Service | Not yet bounded anywhere in the current recipe design (D-09 doesn't mention a size cap). Recommend a sane bound (e.g., matching `engine/index.py`'s own `MAX_DOCUMENT_GLYPHS` precedent of a named, documented ceiling with a typed exception) — low priority for a CLI-only phase with a human operator, but worth naming now since D-09's format IS Phase 4's wire format unchanged, and Phase 4 will need this bound regardless |
| Content-stream injection via `new_text` (a replacement string crafted to contain PDF syntax characters, attempting to break out of the string literal it's placed in) | Tampering | Already structurally prevented by construction: `new_text` is written via `pikepdf.String(...)` and unparsed by `pikepdf.unparse_content_stream` (as `identity_rewrite.py` already does for every operand), which correctly escapes/encodes the string — never string-concatenation-built PDF syntax. Verify no code path in this phase's new modules builds content-stream bytes via raw string formatting instead of pikepdf's own operand types |

## Sources

### Primary (HIGH confidence — directly verified this session, local execution)
- `spike/fixtures/LiberationSans-Regular.ttf` + `fontTools.ttLib.TTFont` — `OS/2.fsType == 0`,
  license `name`-table entries — direct measurement
- `fontTools.subset.Subsetter` against the same file — GID renumbering behavior, `retain_gids`
  comparison, hmtx preservation, 97.8% size reduction — direct measurement
- `uharfbuzz.shape()` against both the original and the fontTools-subsetted font — glyph-ID
  correspondence (Pattern 2) — direct measurement
- `ots-sanitize` (via `opentype-sanitizer` 9.2.0, PyPI) against both fonts above — "File sanitized
  successfully!", exit 0 — direct measurement
- `qpdf 12.4.0 --qdf --object-streams=disable --no-original-object-ids` + `diff -a` against
  `spike/fixtures/tj_refit_sample.pdf` (original vs. one-word-edited-and-Contents-coalesced) —
  13,689-line diff — direct measurement
- `engine/index.py::RunIndex` + `engine/classify_run.py` swept across the full 217-document public
  corpus (5 pages/doc) — multi-operator run distribution (10.62%, up to 167 operators),
  non-contiguous-run rate (10.4% of multi-op / 1.1% of all editable), BaseFont substitution-name
  survey — direct measurement, three independent scripts
- `mypy --strict` against a probe file importing `uharfbuzk` inside `engine/` — `[import-untyped]`
  reproduction — direct measurement
- `pyproject.toml`, `Dockerfile.ci`, `.github/workflows/*.yml` — read directly
- `engine/index.py`, `engine/run_id.py`, `engine/identity_rewrite.py`, `engine/encoding_table.py`,
  `engine/classify_run.py`, `engine/clusterer.py`, `engine/records.py`, `tools/pdftool.py`,
  `harness/*.py`, `spike/tj_refit_prototype.py` — read directly, in full
- `.planning/phases/01-conformance-harness-engine-spike/TJ-REFIT-RESULTS.md`,
  `.planning/phases/02-text-model/02-VERIFICATION.md`, `02-RESEARCH.md`,
  `.planning/phases/03-rewrite-engine-font-pipeline/03-CONTEXT.md`, `REQUIREMENTS.md`,
  `ROADMAP.md`, `STATE.md`, `CLAUDE.md` — read directly, in full

### Secondary (MEDIUM-HIGH confidence — official/authoritative source, fetched and cross-checked)
- `github.com/Kozea/WeasyPrint/blob/main/weasyprint/pdf/fonts.py` (BSD-3-Clause, verified via
  `LICENSE` file) — Type0/CIDFontType2 dict shapes, `/W` construction, ToUnicode CMap generation,
  subset-tag generation — fetched and quoted verbatim
- `github.com/khaledhosny/ots` `LICENSE` — BSD-3-Clause, quoted directly
- `github.com/liberationfonts/liberation-fonts/blob/main/ChangeLog` — fsType history, quoted
  directly
- `packages.debian.org/trixie/...` — `opentype-sanitizer` package availability for the Debian
  release `Dockerfile.ci` is pinned to
- ISO 32000-1 §9.3/§9.4.1 text-state-parameter structure — corroborated across multiple secondary
  sources (PDF Association errata site, PDFlib reference, a PDF-issues GitHub discussion) rather
  than one single fetched primary-source quote (the primary PDF spec document exceeded this
  session's fetch size limit)

### Tertiary (LOW confidence — flagged for validation)
- The exact recommended 90% Tz floor and no-stacking-with-inter-word rule (Pattern 3) — reasoned
  recommendation, explicitly marked Claude's Discretion in CONTEXT.md, not independently measured
- `pdf-association/pdf-issues#368`'s Tm/q/Q ambiguity, cited as the reason to avoid q/Q-bracketing
  for Tz — the issue itself is about Tm specifically, extended here by analogy to justify a safer
  design for Tz, not because the same ambiguity was found to apply to Tz directly

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — already pinned, every version directly verified installed this session
- Architecture (multi-op runs, non-contiguity, qdf-diff pitfall, GID/subset pipeline, D-05 vs
  `editable_substitution` distinction): HIGH — every headline claim is a direct local measurement
  or a direct reading of the actual `engine/` source, not an inference from documentation
- Font pipeline construction (Type0 dict shapes, `/W`, ToUnicode): MEDIUM-HIGH — verified against
  a real, permissively-licensed, production reference implementation (WeasyPrint), cross-checked
  against this project's own existing reader code (`engine/encoding_table.py`) for shape agreement
- Tz save/restore mechanism: MEDIUM-HIGH — spec structure is well-established and corroborated
  across sources; the specific recommended emission pattern is this session's own reasoned
  synthesis, verified only for round-trip syntax (not for the underlying claim about viewer
  behavior, which no fetched source stated in full)
- Pitfalls: HIGH — 9 of 12 are direct measurements; the remaining 3 (Tz mechanism, fsType-for-
  Serif/Mono, warning-content-leakage-for-arbitrary-fonts) are clearly flagged as needing the
  identical verification method already demonstrated, applied to assets that don't exist yet

**Research date:** 2026-08-17
**Valid until:** 30 days (stable domain — PDF spec structure and this project's own corpus/code
don't move; the only fast-moving element, OTS/fontTools point releases, is pinned)
