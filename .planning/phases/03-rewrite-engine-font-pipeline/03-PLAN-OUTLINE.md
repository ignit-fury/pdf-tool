# Phase 3: Rewrite Engine + Font Pipeline — Plan Outline

**Phase goal:** A word in a real document can be replaced — including with a character the
document never contained — and the output looks like nothing happened, everywhere. Gates G2a and
G2b; G2b is THE PROJECT GATE. Still CLI-only (`pdftool edit`) — no web tier work begins before G2b
passes.

## Plan Table

| Plan ID | Objective | Wave | Depends On | Requirements |
|---------|-----------|------|------------|---------------|
| 03-01 | Wave-0 env prep: `uharfbuzz` mypy override, Liberation font bundle + `fsType` verify, OTS/qpdf CI pins | 1 | — | FONT-01 |
| 03-02 | A3 spike: byte-offset → instruction-index correlation proof, corpus-validated | 1 | — | EDIT-02 |
| 03-03 | `engine/fit.py`: width-fit ladder port (`trailing_kern`, inter-word) + new `Tz` rung | 2 | 03-01 | EDIT-02, EDIT-03 |
| 03-04 | `engine/fonts.py` (read side): static mapping table + edit-time substitution trigger | 2 | 03-01 | FONT-01, FONT-06 |
| 03-05 | `engine/fonts.py` (write side): subsetting, Type0/CIDFontType2 embedding, `/W`, ToUnicode | 3 | 03-04 | FONT-02, FONT-03, FONT-04, FONT-05 |
| 03-06 | `engine/rewrite.py`: instruction-identity content-stream surgery, never coalesce `/Contents` | 4 | 03-02, 03-03, 03-05 | EDIT-02, EDIT-04, FONT-06 |
| 03-07 | `engine/recipe.py` + `pdftool edit` CLI: JSON recipe, hash refusal, all-or-nothing, dry-run | 5 | 03-03, 03-05, 03-06 | EDIT-03, EDIT-04 |
| 03-08 | Gate G2a: targeted confined-diff, no-substitution-needed correctness | 6 | 03-07 | EDIT-02, EDIT-04 |
| 03-09 | Gate G2b (THE PROJECT GATE): full pipeline with substitution + manual verification | 7 | 03-08 | EDIT-02, EDIT-03, EDIT-04, FONT-01, FONT-02, FONT-03, FONT-04, FONT-05, FONT-06 |

**9 plans, 7 waves.**

## Plan Details

### 03-01 — Wave-0 environment prep

Adds the `[[tool.mypy.overrides]]` block for `uharfbuzz.*` to `pyproject.toml` (mirrors the
existing `fontTools.*` block exactly) — a hard prerequisite that must land before 03-03 and 03-04,
both first-time `uharfbuzz` importers under `engine/` (Pitfall 6). Creates the `fonts/` directory
and fetches Liberation Sans Bold/Italic/BoldItalic (Regular already exists at `spike/fixtures/`),
Serif (4 weights), and Mono (4 weights) from `github.com/liberationfonts/liberation-fonts`
releases — same lineage as the already-verified Sans build — plus one shared `LICENSE-OFL.txt`,
running the `fsType == 0` verification script (Pitfall 11) against every new file. Adds the pinned
`opentype-sanitizer` apt package to `Dockerfile.ci` for the OTS gate and reconciles the
`QPDF_VERSION=12.2.0-1` pin against the locally-verified `qpdf 12.4.0` before G2a's `--qdf`-based
check comes to depend on it. Partially satisfies FONT-01's "bundled open-license font set is
shipped" clause; the mapping-table half of FONT-01 lands in 03-04.

### 03-02 — A3 spike: instruction-ordinal correlation proof

Prototypes and corpus-validates the one mechanism RESEARCH.md flags as genuinely unproven
(Assumption A3, Open Question 1): correlating a run's `operator_byte_offset` values (already on
`GlyphRecord`) to `pikepdf.parse_content_stream()`'s instruction-list indices via ordinal position
among text-showing operators, per the `touched_instruction_indices` sketch in Pattern 1. Mirrors
Phase 1's `spike/tj_refit_prototype.py` precedent: a throwaway `spike/` module plus a corpus-wide
measurement script confirming the ordinal lookup lands on a text-showing instruction of the
expected type for every editable run across all 217 corpus documents (including the 17
known-malformed ones), with explicit pass/fail against the hardest named cases (`irs_form_1040.pdf`
p0 run `:o1391`, a 62-operator/63-glyph run; `irs_form_w4.pdf` p0/p4 non-contiguous runs). Produces
a results doc analogous to `TJ-REFIT-RESULTS.md`/`PLAYA-DECISION.md` recording the measured
agreement rate and any tokenizer-disagreement cases — a failure here blocks 03-06 entirely, so it
must resolve before rewrite.py work begins. No dependency on 03-01 (touches neither `uharfbuzz` nor
`fonts/`).

### 03-03 — engine/fit.py: width-fit ladder

Ports `spike/tj_refit_prototype.py`'s proven `trailing_kern` → inter-word ladder (Δ=0.0000pt both
directions, D-01) into `engine/fit.py`, adding `frozen=True, slots=True` to `FitResult` (a required
deviation from the spike, matching every other verdict type in `engine/`) and porting the
load-bearing `kern_to_displacement_pt` sign convention verbatim. Adds the new `Tz` rung (D-02)
between inter-word and refuse, pinned at a 90% floor per Pattern 3 (`TZ_FLOOR_PERCENT = 90`, named
constant with its reasoning in a comment) and explicitly not stacked with inter-word distribution —
first rung that fits wins. Extends `read_original_advance_pt` for D-14's CID/`/W` case by reusing
`engine/encoding_table.py::cid_width` directly rather than reimplementing, keeping the existing
`/Widths`-via-pikepdf-never-fontTools discipline (Pitfall 7). Tests port
`tests/test_tj_refit_prototype.py`'s cases verbatim onto the real module plus one new Tz-rung case,
wiring to VALIDATION.md's `test_tz_condensing_restores_scale_after_run`.

### 03-04 — engine/fonts.py (read side): mapping table + substitution trigger

Builds the flat, exact-match-only mapping table (D-06/FONT-01) seeded from the corpus-measured
Pitfall 10 survey — the 12 Base-14 non-symbol names plus common MS-core-font variants — refusing by
font name, never a descriptor-flag heuristic, when no entry exists. Implements the genuinely new
FONT-06 edit-time glyph-availability check (Pattern 4/Pitfall 4): for every character in a proposed
replacement, build the reverse glyph-name-to-code lookup from `encoding_table.py`'s existing
tables, then check presence via the existing `glyph_presence` machinery — this must fire on
`editable_original` runs too, not only Phase 2's narrower `editable_substitution` state, and
extends the existing try/except-and-classify pattern since it reads the original (potentially
hostile) document's font program. Measures and pins RESEARCH.md's Open Question 2 (D-08's
threshold): a corpus-wide per-glyph advance-delta comparison between each substitution run's
`/Widths` and Liberation's `hmtx`, extending the same scan that produces the table-coverage report
(`test_corpus_substitution_coverage_report`) — report and pin the number; do not widen the table
from it, which is explicitly deferred. Depends on 03-01 for both the mypy override and the actual
font files these measurements read.

### 03-05 — engine/fonts.py (write side): subsetting + Type0/CIDFontType2 embedding

Implements FONT-02/FONT-05: `fontTools.subset.Subsetter` (`retain_gids=False`) over each bundled
family's whole-recipe glyph union, one subset per family per document, with the WeasyPrint-derived
MD5-tag generator, running `ots-sanitize` immediately after every subset call as a development-time
check (Pitfall 8) rather than only at the final gate. Implements FONT-03/FONT-04: the
Type0/CIDFontType2 dictionary (`/Encoding /Identity-H`, `/CIDToGIDMap /Identity`), `/W` array, and
`/ToUnicode` CMap, built key-for-key against the WeasyPrint reference shapes RESEARCH.md quotes
verbatim and cross-checked against `engine/encoding_table.py`'s existing reader with zero reader
changes needed; the FONT-04 assertion binds every CID in `/W` against the subset's own `hmtx`
(D-14) and never falls through a silent `/MissingWidth` of 0. Shapes replacement text twice —
pre-subset (to learn needed glyphs) and post-subset (to get final CIDs directly, per
Pattern 2/Pitfall 5, since subsetting renumbers GIDs but not glyph names) — and structurally
enforces D-12 (original embedded font never modified). Depends on 03-04 (same file, sequential) for
the mapping table and substitution trigger this module's callers rely on.

### 03-06 — engine/rewrite.py: instruction-identity content-stream surgery

Implements the core rewrite mechanism using 03-02's validated bridge: locate a run's touched
`pikepdf.parse_content_stream()` instructions by ordinal correlation, replace the first touched
instruction with the new `Tj`/`TJ` (or the `Tz`-bracketed triple, using 03-03's `FitResult` scale
data), and delete every other touched instruction individually by list index — never a byte-range
splice — which is what correctly survives both the multi-operator case (10.6% of runs, Pitfall 1)
and the non-contiguous case where a foreign run's own operator sits between this run's first and
last (~1.1% of runs, Pitfall 2). **Must never coalesce or reshape `/Contents`** — replace only the
specific array element containing the edited run(s); `identity_rewrite.py` (the closest analog)
does coalesce, and that behavior measured a 13,689-line spurious `qpdf --qdf` diff for one edited
word (Pitfall 3, 52.5% of the corpus has array `/Contents`) — this is the single most likely
accidental regression in the phase. Implements D-04's runtime guard (re-walk the edited page,
assert the text matrix after the edited run within epsilon, refuse by name on violation) and
promotes `engine.classify_run._stream_bytes_and_resources` to a public API as this module's third
consumer. Regression-tests against `irs_form_1040.pdf` p0 run `:o1391` and `irs_form_w4.pdf` p0/p4,
and confirms no code path builds content-stream bytes via raw string formatting instead of
`pikepdf`'s own operand types.

### 03-07 — engine/recipe.py + pdftool edit CLI

Implements D-09 (JSON recipe, `{run_id, new_text}[]`, parsed via stdlib `json.load`, never `eval`),
D-10 (decode every op's `run_id` through the existing `decode_run_id`, hard-refuse the whole recipe
on any `source_hash` mismatch, no `--force`), and a named, bounded recipe-size cap
(`MAX_RECIPE_OPS`-style typed exception, matching `engine/index.py::MAX_DOCUMENT_GLYPHS`'s
precedent, per the Known Threat Patterns DoS note). Implements D-11's all-or-nothing orchestration
loop: resolve and validate every op first (D-05 glyph check via 03-04, fit ladder via 03-03,
glyph-union collection per family) and only proceed to 03-05's subsetting/embedding and
`pdf.save()` if every op validates cleanly; every refusal extends `RunVerdict`'s named-reason
vocabulary rather than inventing a parallel one (EDIT-04). Implements D-03's dry-run-by-default
CLI: adds an `edit` subparser to `tools/pdftool.py` alongside the existing `index` subcommand
(`pdftool edit doc.pdf --recipe r.json -o out.pdf`), printing the structured per-run fit-plan
report by default and writing output only when an explicit `--commit` flag is passed, proving the
printed table is a rendering of the same structured data via `test_dry_run_matches_commit`.

### 03-08 — Gate G2a: confined-diff, no-substitution-needed correctness

Implements the targeted structural stream-diff RESEARCH.md's Don't-Hand-Roll table specifies in
place of a whole-file `qpdf --qdf` + `diff` (which measured 13,689 spurious lines on an
array-`/Contents` fixture and does not, in practice, confine to the edited operators) — a
comparison of only the touched stream's decoded operator list, old vs new, via
`pikepdf.parse_content_stream` twice. Asserts roadmap criterion 1 in full for the
editable-in-original-font case (no substitution): the confined diff, `|Δwidth| < 0.5pt`, the D-04
text-matrix invariant, `qpdf --check` clean, and same-engine zero-tolerance + cross-engine tolerant
masked pixel diff (`harness/masked_diff.py`, `harness/render_diff.py`, reused unmodified). This is
the first end-to-end exercise of the full 03-01..03-07 pipeline and gates whether the more
expensive G2b work in 03-09 is worth attempting.

### 03-09 — Gate G2b (THE PROJECT GATE): full pipeline with substitution

Runs the complete pipeline against a character absent from the embedded subset — the FONT-06
trigger path through 03-04's check, 03-05's subset/embed, 03-06's substituted-run surgery, 03-07's
orchestration — and asserts roadmap criterion 2's full machine-checkable set (D-15): same-engine
zero-tolerance pixel diff outside the edited run, cross-engine tolerant agreement (reusing
`harness/`), OTS validation of the emitted font, `qpdf --check` clean, and a programmatic
`/ToUnicode` extraction round-trip. Includes a `checkpoint:human-verify` task recording D-15's
three real-viewer opens (Acrobat Reader, macOS Preview, Chrome — no repair prompt) and the Acrobat
copy-paste Unicode check, plus D-08's rendered before/after contact-sheet seam review across corpus
samples — all performed once and recorded in a results document following the
`PLAYA-DECISION.md`/`TJ-REFIT-RESULTS.md` precedent. This is the phase's terminal plan: no web-tier
work of any kind begins until it passes.

## Sequencing Rationale

**Waves 1-3 front-load everything parallelizable; waves 4-7 are a strictly serial pipeline because
the underlying data dependencies are serial, not because of a planning choice.**

- **Wave 1** (03-01, 03-02): both are zero-dependency foundational work touching disjoint files
  (`pyproject.toml`/`fonts/`/`Dockerfile.ci` vs. a throwaway `spike/` module + corpus script). 03-02
  is sequenced here, not later, per RESEARCH.md's explicit instruction to prototype the
  instruction-ordinal bridge (Assumption A3) "before committing engineering time to the full
  rewrite engine" — a failure here is cheap to discover in Wave 1 and expensive to discover after
  03-06 is built.
- **Wave 2** (03-03, 03-04): both depend only on 03-01 (the `uharfbuzz` mypy override; 03-04
  additionally needs the actual font files for its corpus measurements) and touch disjoint files
  (`engine/fit.py` vs `engine/fonts.py`). This is the constraint set's own explicit
  parallelization: "`engine/fit.py` can proceed in parallel with the font work."
- **Wave 3** (03-05): forced sequential after 03-04 purely by file ownership — both are
  `engine/fonts.py`, and same-wave plans cannot share a modified file. The read/write split
  (mapping+trigger vs. subset+embed) is also a real conceptual boundary: 03-05's subsetting needs
  to know which glyphs a run needs, which is 03-04's glyph-availability check's output.
- **Wave 4** (03-06): the highest-risk plan in the phase. It cannot start before 03-02 proves the
  bridge exists, 03-03 provides `FitResult`'s Tz save/restore data, and 03-05 provides the
  CID/Type0 operand construction for substituted runs — all three converge here, matching
  "`engine/rewrite.py` depends on both A3's bridge and `engine/fit.py`," extended transitively
  through fonts.py for the substitution path.
- **Wave 5** (03-07): recipe orchestration is the wiring layer over rewrite + fonts — it has
  nothing to do until both exist.
- **Waves 6-7** (03-08, 03-09): gate tests are kept in separate waves rather than parallelized,
  even though they touch disjoint files, because G2b's per-document cost (corpus-wide substitution
  runs, three real-viewer opens, contact-sheet review) is an order of magnitude more expensive than
  G2a's — validating the simpler no-substitution case first avoids spending that cost against a
  pipeline that hasn't yet proven the easy case. G2b is sequenced last across the entire phase
  because it is, per ROADMAP.md, THE PROJECT GATE: no web-tier work of any kind starts until it
  passes.

**Where the hard constraints landed:**

| # | Constraint | Plan |
|---|------------|------|
| 1 | `uharfbuzz` mypy override before any import | 03-01 |
| 2 | `fonts/` bundling + fsType verification | 03-01 |
| 3 | A3 byte-offset bridge, own early plan | 03-02 |
| 4 | `engine/fit.py` parallel with font work | 03-03 ∥ 03-04 (Wave 2) |
| 5 | `engine/rewrite.py` depends on bridge + fit.py | 03-06 `depends_on` |
| 6 | `engine/recipe.py` + CLI depend on rewrite + fonts | 03-07 `depends_on` |
| 7 | G2a/G2b come last, depend on everything | 03-08, 03-09 (final two waves) |
| 8 | `_stream_bytes_and_resources` promotion | folded into 03-06 (its third consumer) |

**Never-coalesce and confined-diff are the two correctness traps RESEARCH.md measured (not
theorized)** — 03-06 and 03-08 name them explicitly in their own scope so the executing agent
cannot rediscover them the hard way.

**Coverage check:** all 9 phase requirement IDs (EDIT-02, EDIT-03, EDIT-04, FONT-01..FONT-06)
appear in at least one plan's Requirements column (cross-walked above); G2a and G2b's roadmap
success criteria are covered by 03-08/03-09; every CONTEXT.md locked decision (D-01..D-15) and
every RESEARCH.md pitfall (1-12) has an explicit home in exactly one plan's scope paragraph; no
Deferred Idea (`--partial` application, Noto/DejaVu, table-widening-from-evidence, recipe
versioning, the `/Tf` scoping fix) appears in any plan.

## OUTLINE COMPLETE

Plan count: 9
