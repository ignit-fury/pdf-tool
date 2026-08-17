# Phase 3: Rewrite Engine + Font Pipeline - Context

**Gathered:** 2026-08-17
**Status:** Ready for planning

<domain>
## Phase Boundary

A word in a real document can be replaced — including with a character the document never
contained — and the output looks like nothing happened, everywhere.

This phase retires Risk #1, the unproven composition: replace-with-correct-widths AND
subset/embed-a-bundled-font, together. Replace-without-subsetting is PDF-XChange's shipped
limitation, which the market already has and nobody likes; the honest MVP boundary is both or
neither.

Gates G2a and G2b. **G2b is THE PROJECT GATE.** Still CLI-only (`pdftool edit`) — no web tier
work begins before G2b passes.

**In scope:** EDIT-02, EDIT-03, EDIT-04, FONT-01 through FONT-06.

**Explicitly NOT in scope:** any web/HTTP surface; find-and-replace across pages (Phase 5, which
consumes this engine); reflow across lines or pages (permanently out of scope per CLAUDE.md);
undo/recipe *storage* (Phase 4 — this phase defines the recipe *format*, not its persistence).

</domain>

<decisions>
## Implementation Decisions

### Width Fitting and Refusal (EDIT-02, EDIT-03)

- **D-01: The fit ladder is `trailing_kern` → inter-word distribution → `Tz` 90–95% → refuse.**
  Tried in that order, first rung that fits wins. Chosen because kerning is non-deforming at these
  magnitudes while `Tz` genuinely deforms glyph shapes — so exhaust the free options before
  reaching for the one that changes how letters look. The first two rungs are already proven:
  Phase 1's spike hit Δ=0.0000pt in both the shorter and longer directions using `trailing_kern`
  alone (`TJ-REFIT-RESULTS.md`, ENG-05 retired). Accepted cost: a document whose delta lands just
  past the inter-word range now deforms glyphs slightly rather than refusing outright.

- **D-02: Condensing is `Tz` horizontal scaling, not a per-glyph kern squeeze.** Roadmap criterion
  5 allows condensing "only within 90–95%"; `Tz` is the operator that means exactly that, in one
  place, and maps to the stated percentage directly. A per-glyph squeeze would spread the same
  shortfall across letter-spacing, which reads as more visibly wrong and makes "90–95%" stop
  corresponding to any single number. Accepted cost: `Tz` persists within the text object until
  reset, so the rewrite must save and restore it correctly — a real correctness burden the kern
  approach would not have carried.

- **D-03: Overflow disclosure is a dry run, and dry run is the default.** `pdftool edit` computes
  and prints the per-run fit plan — which ladder rung fires, the resulting Δwidth, and the named
  reason for any refusal — without writing anything. Committing requires a separate explicit flag.
  Chosen because EDIT-03 says overflow is disclosed *before* commit, and a report printed while
  writing is disclosure *during*. Phase 4's UI later renders this same structured data rather than
  recomputing it.

- **D-04: The post-run text matrix invariant is a runtime guard, not just a test assertion.** After
  building a rewrite, re-walk the page and assert the text matrix following the edited run matches
  its original value within epsilon; on violation, refuse that edit with a named reason. Chosen so
  G2a's criterion holds on documents that were never in the fixture corpus — a test-only assertion
  proves it for the shapes we thought to collect, not for the one a user opens. Phase 2 measured
  page parse at ~9–15ms, so the re-walk is affordable per edit.

### Font Substitution (FONT-01, FONT-06)

- **D-05: Any glyph missing from the embedded subset substitutes the ENTIRE visual run.** Not the
  missing character, not the affected word — the whole run, re-encoded in the mapped bundled face.
  This is FONT-06 implemented directly, and it makes a partial-run seam *structurally impossible*
  rather than merely discouraged. Accepted cost: one accented character re-renders a whole visual
  line in Liberation. (The alternative — distinguishing "absent from the subset" from "absent from
  the font" — mostly collapses anyway: the embedded program *is* the subset, and outlines the file
  does not contain cannot be recovered from it.)

- **D-06: A font with no entry in the static mapping table refuses, by name.** No serif/sans
  fallback derived from descriptor flags — that is precisely the heuristic FONT-01 forbids, the
  flags lie often, and a wrong pick is a confident-wrong result, which is the failure mode this
  product exists to avoid. Consistent with Phase 2's D-04 posture. **Consequence worth measuring:**
  the refusal rate is a direct function of table coverage, so table coverage becomes a quality
  number, not an implementation detail.

- **D-07: Phase 3 bundles the Liberation trio only — Sans, Serif, Mono.** Metric-compatible with
  Arial/Times/Courier, which CLAUDE.md calls "the single highest-leverage font choice in the
  project": replacement text lands in the same place with zero fitting work. Noto and DejaVu are
  deferred until refusal data shows a real coverage gap, specifically because they are **not**
  metric-compatible — every Noto substitution would need the full refit path, adding fitting risk
  to the one phase that gates the project. Note: no `fonts/` directory exists in the repo yet; the
  Phase 1 spike borrowed `spike/fixtures/LiberationSans-Regular.ttf`.

- **D-08: Seam quality is gated by a machine metric AND a rendered contact sheet.** The metric is
  per-glyph advance delta against the original (near-zero for Liberation's metric-compatible
  cases), asserted in CI so a regression is caught later. The contact sheet is a rendered
  before/after across corpus samples, reviewed once by a human. Chosen because identical advances
  do not guarantee identical appearance — different stroke weight or x-height reads as a seam even
  when metrics match perfectly — but a pure human review leaves nothing behind to catch a
  regression. Risk #4 is unverified today; this is how it gets retired.

### Edit Representation (EDIT-04)

- **D-09: An edit is a JSON recipe — a list of `{run_id, new_text}` ops.**
  `pdftool edit doc.pdf --recipe r.json -o out.pdf` replays them. This matches `engine/run_id.py`'s
  own stated model verbatim — "(original bytes, recipe) → output, and the output is a throwaway
  that is never the input to the next edit" — and **this format IS Phase 4's wire format,
  unchanged**, since CLAUDE.md specifies the client sends the operation log rather than the mutated
  file. Deliberately no single-edit flag variant: Phase 5 needs batch anyway, and FONT-02's
  save-time subsetting genuinely requires seeing all edits at once.

- **D-10: A source-hash mismatch hard-refuses the entire recipe, with no override flag.** Run IDs
  encode a SHA-256 of the original bytes and address byte offsets into them; against different
  bytes an offset is meaningless and may land mid-token. `resolve_run_id_offset` returning True is
  *not* proof the offset means the same thing in a different file. No `--force` escape hatch,
  because Phase 4 would inherit it as an API parameter on the one invariant the entire addressing
  model rests on. This is what makes TEXT-03's guarantee enforceable rather than aspirational.

- **D-11: Recipe application is all-or-nothing.** Any refusal means nothing is written; the report
  names every failing edit and its reason. Keeps replay deterministic — the same bytes plus the
  same recipe produce the same output regardless of engine version — and hands FONT-02's subsetting
  the final edit set up front. A `--partial` mode was considered and deliberately **not** added:
  Phase 5's find-and-replace will likely want it, and that phase should make the call with its own
  evidence rather than inheriting a pre-commitment from here.

### Font Embedding at Save (FONT-02, FONT-03, FONT-04, FONT-05)

- **D-12: The original embedded font is never modified. Substituted runs point at a newly embedded
  font.** Untouched text keeps its original subset byte-for-byte. Roadmap criterion 3 ("untouched
  text elsewhere that uses the same font still renders correctly after a re-subset") is then
  satisfied *structurally* — you cannot break what you never touched. Re-subsetting the original
  over the whole-document glyph union was rejected: it cannot supply the new character anyway
  (outlines absent from the embedded program cannot be invented), so it would be re-subsetting for
  its own sake while incurring exactly the risk criterion 3 warns about.

- **D-13: One subset per bundled family per document, over the glyph union, emitted once at save.**
  Every substituted run's glyphs are collected across the whole recipe; one Liberation Sans subset
  covering the union is embedded once. This is FONT-02's wording applied to the fonts this phase
  actually adds, and it is a direct beneficiary of D-11 — all-or-nothing application means the
  final edit set is known before subsetting runs. FONT-05's fresh-subset-tag rule then has one tag
  per family to keep distinct, not one per edited run.

- **D-14: The FONT-04 width assertion binds on `/W`, and `/Widths` is the untouched-original
  case.** New bundled fonts embed as Type0/CIDFontType2 with Identity-H (FONT-03), which carries a
  `/W` array — so the assertion is that every CID in `/W` matches the subset program's own `hmtx`
  advance, and that `/DW` never silently covers a glyph actually in use. Original simple fonts keep
  their `/Widths` untouched per D-12, so FONT-04's `/MissingWidth`-of-0 failure mode cannot arise
  there — nothing regenerates them.

- **D-15: G2b is gated on the machine-checkable set; the viewer checks are recorded evidence.** CI
  gates on: OTS validation of the emitted font, `qpdf --check` clean, same-engine zero-tolerance
  pixel diff outside the edited run, cross-engine agreement within the measured tolerance, and a
  programmatic ToUnicode extraction check. The three real-viewer opens (Acrobat Reader, macOS
  Preview, Chrome) and the Acrobat copy-paste check are performed once and recorded in a results
  document, following the established `PLAYA-DECISION.md` / `TJ-REFIT-RESULTS.md` precedent.
  Chosen because a human-in-the-loop gate cannot run in CI, while dropping the viewer checks
  entirely would discard the single check closest to real user experience — pdfium/Poppler/MuPDF
  agreeing does not prove Acrobat is happy.

### Claude's Discretion

- Disposition of the Phase 1 spike modules. `spike/tj_refit_prototype.py` was declared throwaway by
  Phase 1's CONTEXT and judged only on answering its question — but its algorithm, its sign
  convention (`displacement_pt = -(K/1000) * font_size_pt`, explicitly flagged as load-bearing),
  and its `/Widths`-via-pikepdf deviation are all carried-forward knowledge. Absorb, rewrite, or
  leave alone as judged. `spike/playa_decode_probe.py`'s single-module-boundary-for-playa-decode
  rule is already satisfied by `engine/playa_boundary.py` and must stay satisfied.
- Where the rewrite engine's module boundary sits within `engine/` and how it composes with
  `engine/identity_rewrite.py`, which already owns parse→unparse and `verify_roundtrip`.
- The exact `Tz` floor within the 90–95% band, and whether `Tz` may stack with inter-word
  distribution or must replace it.
- How bold/italic variants are selected within a mapped family, and what the mapping table keys on
  (BaseFont name, descriptor flags, or both).
- ToUnicode CMap generation specifics for the emitted Type0 fonts.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 3's own definition
- `.planning/ROADMAP.md` §"Phase 3: Rewrite Engine + Font Pipeline" — goal, G2a/G2b success
  criteria verbatim, and the **assertion-layering correction** (same-engine zero-tolerance vs
  cross-engine measured tolerance — the original "pixel-identical across all three engines" wording
  is empirically unachievable and was corrected in Phase 1)
- `.planning/REQUIREMENTS.md` — EDIT-02/03/04 (lines 51–53), FONT-01..06 (lines 74–79)

### Carried-forward findings this phase builds on
- `.planning/phases/01-conformance-harness-engine-spike/TJ-REFIT-RESULTS.md` — **the TJ refit is
  already proven.** Measured Δwidth both directions, the `trailing_kern` strategy, the TJ sign
  convention, and why `/Widths` is read via pikepdf rather than fontTools
- `spike/tj_refit_prototype.py` — the prototype implementing the above, with its priority-ordered
  absorption strategy and explicit out-of-scope note for `Tz`
- `.planning/phases/01-conformance-harness-engine-spike/PLAYA-DECISION.md` — the playa GO verdict
  and the single-module-boundary rule
- `.planning/phases/02-text-model/02-CONTEXT.md` §D-01 — a run is a visual line spanning several
  `Tj`/`TJ` operators; its own text states "the run model and the rewrite engine are therefore
  coupled, and Phase 3 inherits this"
- `.planning/phases/02-text-model/02-CONTEXT.md` §D-04, §D-05 — the refusal posture and
  split-at-bad-glyph rule this phase's refusals must stay consistent with
- `.planning/phases/02-text-model/02-VERIFICATION.md` — Gate G1's evidence, including the two
  findings left open for later phases (the per-part `/Tf` scoping limit in `classify_run`, exposed
  by identity-rewrite's stream coalescing; and "page-op-able" deferred to Phase 6)
- `.planning/phases/02-text-model/02-RESEARCH.md` §9 — the identity-rewrite procedure and why
  byte-level round-trip equality is rejected as a correctness test

### Project-level constraints
- `CLAUDE.md` — the AGPL constraint (no AGPL transitively, in the *resolved lockfile*), the
  bundled-fonts table and why Liberation is highest-leverage, the "send the operation log, not the
  mutated file" architecture rule, and the content-stream-editing-only / no-reflow constraints
- `.planning/PROJECT.md` — core value statement and the bundled-font commitment

### Verification vehicles (reuse, do not reinvent)
- `harness/masked_diff.py` — `masked_pixel_diff()`, the exact zero-tolerance same-engine primitive
- `harness/render_diff.py` — `render_all()`, three-engine rendering with the CropBox forcing fix
- `harness/run_corpus_harness.py` — module docstring documents the measured cross-engine tolerance
  (3px blur, 20/255 per-channel, 8% threshold) and the record-never-crash convention

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`engine/index.py` — `RunIndex`**: the composed pipeline entry point. `RunIndex(path).page(n)`
  returns a `PageIndex` with per-run `RunVerdict`s. This is how the rewrite engine learns which
  runs are editable *before* attempting anything, and its `_parse_page` is the natural re-walk hook
  for D-04's matrix assertion.
- **`engine/run_id.py` — `decode_run_id`, `resolve_run_id_offset`**: the recipe's run IDs decode
  through these. `resolve_run_id_offset` already implements the token-boundary check that proves an
  offset lands on a real operator keyword. `RunIdParts` carries `source_hash` — D-10's hash check
  reads it from here.
- **`engine/identity_rewrite.py`**: already owns `identity_rewrite`, `null_edit_rewrite`, and
  `verify_roundtrip`. Its module docstring draws the Phase 3 boundary explicitly ("ZERO
  width-fitting, ZERO font subsetting, ZERO glyph substitution, ZERO TJ-array arithmetic") — Phase
  3 is the phase that crosses it. Its per-instruction unparse pattern for `Tj` operands is directly
  reusable.
- **`engine/encoding_table.py` — `resolve_font`, `FontVerdict`, `glyph_verdict`**: the branch
  decision table. `FontVerdict.branch_id` and `.substitution` already distinguish
  editable-in-original from editable-with-substitution — D-05's trigger reads this rather than
  re-deriving it.
- **`engine/classify_run.py` — `RunVerdict`**: the three-state verdict with named reasons. Phase 3's
  refusals should extend this vocabulary, not invent a parallel one.
- **`spike/tj_refit_prototype.py`**: the proven algorithm, sign convention, and `FitResult` shape.

### Established Patterns

- **Frozen/slots dataclasses for record types** (`engine/records.py`, `RunVerdict`, `FontVerdict`) —
  a construction call missing a field raises `TypeError` before a half-built record exists.
- **Named refusals carrying a distinct reason string**, never a generic failure — established by
  `FontVerdict`/`GlyphVerdict`/`RunVerdict` and required by EDIT-04.
- **Measure, then pin, never guess** — every threshold in the codebase (the 8% render tolerance,
  the 0.102-em space threshold, `P_PATH_OBJECT_THRESHOLD`, `CACHE_GLYPH_BUDGET`) carries its
  measured basis in a comment beside it. `Tz`'s 90–95% band must be pinned the same way.
- **A check is not trusted until demonstrated failing** — permanent negative-case tests that
  reproduce the exact bug they guard against (`test_clas05_whole_document_refusal_is_wrong`,
  `test_verify_roundtrip_detects_mutated_tj_text`, the naive-sum coverage reproduction).
- **No document content in logs, assertion messages, or exception text** — store
  `type(exc).__name__`, counts, and filenames only. One corpus `PDFSyntaxError` is known to embed
  raw content-stream bytes in its own `str()`.
- **`import playa` is confined to `engine/playa_boundary.py`** — enforced by a test.
- **Scratch-only writes** — `tempfile`/`tmp_path`, never overwriting a corpus file.
- **mypy strict, zero `# type: ignore` in `engine/`** — currently true across all 14 modules.

### Integration Points

- **New:** `fonts/` does not exist yet. Bundling Liberation is net-new work including license
  files, and CI must confirm no AGPL enters the resolved lockfile.
- **`tools/pdftool.py`**: currently one `index` subcommand behind a real `add_subparsers`, chosen
  precisely so `edit` can be added without a breaking CLI change. Note its `sys.path.insert` shim
  for bare `python tools/pdftool.py` invocation.
- **`engine/identity_rewrite.py`** imports `engine.classify_run._stream_bytes_and_resources`, a
  private helper. Flagged in review as acceptable for two consumers; the rewrite engine would be a
  third, at which point promoting it to a public API is the cheap fix.
- **Known trap:** identity-rewrite coalesces a multi-part `/Contents` array into one stream, which
  changes downstream classification on documents whose `/Tf` and its `Tj` live in different array
  parts (reproduces on every `irs_form_*.pdf`). Phase 3's rewrite will hit this same interaction.

</code_context>

<specifics>
## Specific Ideas

- **The refusal message is a product surface, not a log line.** Every refusal in this phase names
  its reason specifically — unmapped font (with the font's name), won't fit after the full ladder,
  matrix invariant violated, source-hash mismatch. Phase 4's refusal screen (CLAS-07) renders these
  directly, so the vocabulary chosen here is user-facing text.
- **The dry-run fit report is structured data first, human text second.** Phase 4 consumes the same
  per-run records (rung fired, Δwidth, refusal reason) to drive its UI; the CLI's printed table is
  a rendering of it.
- **Table coverage is a measurable number.** D-06 makes the mapping table the sole substitution
  authority, so "what fraction of corpus fonts have a table entry" is a real quality metric worth
  reporting during this phase rather than discovering in Phase 5.

</specifics>

<deferred>
## Deferred Ideas

- **`--partial` recipe application** — apply what works, report what doesn't. Phase 5's
  find-and-replace-across-all-pages is the phase with the evidence to decide whether bulk workflows
  need it; deliberately not pre-committed here (D-11).
- **Noto Sans/Serif and DejaVu bundling** — broader Unicode coverage, deferred until refusal data
  proves a gap. They are not metric-compatible, so they carry real fitting cost (D-07).
- **Widening the static font mapping table from collected evidence** — the "report unmapped fonts
  as corpus data" option. The refusal itself is decided (D-06); the reporting path is a
  nice-to-have that can land whenever the data is wanted.
- **Recipe format versioning field** — raised but not resolved; matters when Phase 4 starts sending
  recipes over a wire and needs compatibility guarantees.
- **The per-part `/Tf` scoping limit in `engine/classify_run.py`** — inherited from Phase 2's
  verification as a recorded, understood finding. Phase 3's rewrite touches the same interaction
  and may be the natural place to fix it, but it is not in this phase's requirement list.

</deferred>

---

*Phase: 3-Rewrite Engine + Font Pipeline*
*Context gathered: 2026-08-17*
