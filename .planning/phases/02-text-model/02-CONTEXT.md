# Phase 2: Text Model - Context

**Gathered:** 2026-08-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Any run of text in any real document can be **located, addressed, and honestly labelled**
editable-or-not — *before* the user types.

This is the keystone. Find, replace, editability classification, and all four text-derived exports
(text, Markdown, HTML, and later DOCX) consume this one component. If it slips, five features slip.
It is also the last phase before the rewrite engine, so its data model is the contract Phase 3 is
built against.

Requirements: TEXT-01..TEXT-08, CLAS-01..CLAS-05 (13). Gate G1.

Still CLI-only. No web tier work begins before Gate G2b passes in Phase 3.

</domain>

<decisions>
## Implementation Decisions

### Run Model

- **D-01:** **A run is a visual line.** Glyphs are merged across text-showing-operator boundaries
  into what reads as a line on the page, breaking on font change, size change, baseline shift, or a
  horizontal gap wider than the tuned threshold. Chosen because it matches what a user believes they
  are clicking. Accepted cost: one visual line commonly spans several `Tj`/`TJ` operators, so a
  replacement must rewrite all of them coherently — the run model and the rewrite engine are
  therefore coupled, and Phase 3 inherits this.

- **D-02:** **Sub-runs are the addressable unit when a line splits.** Where a line contains an
  unmappable glyph, each editable fragment gets its own run ID and is independently selectable; the
  locked glyph sits between them and is greyed. An ID always names something that can be acted on.
  Accepted cost: the number of IDs a visual line yields depends on its content, so the run map is
  less uniform than a strictly line-shaped one. Follows from D-01 + D-04.

- **D-03:** **The synthetic-space threshold is tuned against the corpus with a measured target, not
  guessed.** Run extraction across the 216-document public corpus, measure against known-good text,
  minimise error, then pin the number with the measurement recorded — the same discipline that
  produced Phase 1's 8% render tolerance. Research calls this threshold "the whole game" for
  extraction quality, and it is the single tunable that most directly determines whether the text
  model is any good. Requires ground-truth text for a sample of the corpus; that setup is in scope.

### Failure Posture

- **D-04:** **Ambiguous encoding refuses, and logs which branch was ambiguous.** The PDF spec does
  not cleanly resolve `Symbolic` + `/Encoding`, real files do it constantly, and viewers disagree on
  the answer. When the decision table cannot resolve a font, the affected runs are marked
  not-editable with a stated reason and the ambiguous branch is logged. Consistent with rejecting
  white-box overlay: a wrong-but-confident result is the failure mode this product exists to avoid,
  and guessing here would mean the three-engine harness is catching our own deliberate guess.
  Accepted cost: some genuinely editable text will be refused. **The refusal rate is unknown and
  must be measured against the corpus during this phase** — if it is high, that is a finding worth
  surfacing, not a number to quietly accept.

- **D-05:** **A run splits at a bad glyph rather than locking wholesale.** One Type3 glyph or one
  character with no `/ToUnicode` mapping locks only itself; surrounding clean text stays editable.
  Chosen so a single stray character cannot lock a paragraph the user reasonably expects to edit.
  Accepted cost: run boundaries now depend on glyph-level classification, so the map is more
  fragmented and carries more IDs.

### Indexing

- **D-06:** **Page-at-a-time, cached.** A page is parsed when first needed and the result retained.
  First page usable almost immediately; memory proportional to pages actually visited. Accepted cost:
  find-across-all-pages must force a full parse, so the first search on a long document pays the
  whole cost at once. **That needs a visible progress affordance when the UI arrives in Phase 4** —
  record it as a known consequence now rather than discovering it as a UX bug later.

### Claude's Discretion

- Whether the Phase 1 spike modules (`spike/playa_decode_probe.py`, `spike/tj_refit_prototype.py`)
  are absorbed, rewritten, or left alone. Phase 1's CONTEXT.md declared spike code throwaway, judged
  only on whether it answered its question. `playa_decode_probe.py` is nonetheless the established
  single module boundary for `playa` decode calls, and that boundary must be preserved however the
  code is reorganised — no abstraction layer, per Phase 1 D-locked guidance.
- Internal structure of the glyph record and run record, beyond the provenance fields already fixed
  by research.
- How ground-truth text for D-03's threshold tuning is obtained.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase definition and requirements
- `.planning/ROADMAP.md` — Phase 2 section: goal, five success criteria, Gate G1; and the Phase 3
  section, whose Gate G2a/G2b two-layer assertion this phase's data model must be able to satisfy
- `.planning/REQUIREMENTS.md` — TEXT-01..TEXT-08, CLAS-01..CLAS-05
- `.planning/PROJECT.md` — Constraints (Licensing, Privacy, Tech stack) and the Key Decisions table

### Research — read before planning
- `.planning/research/SUMMARY.md` — §"Convergent Conclusions" #1 (text addressing is SETTLED — the
  server owns addresses; do not relitigate), #4 (uneditable-document classification: four buckets,
  three signals, two granularities), §"Implications for Roadmap" → Phase 1 (this phase's definition
  and Gate G1), §"Gaps to Address" (the encoding chain and the space threshold are both named)
- `.planning/research/PITFALLS.md` — the ToUnicode-vs-Encoding distinction stated precisely; the
  `/MissingWidth` default-0 trap; `Tw` applying only to single-byte code 32; text living outside
  `/Contents`; `/Contents` array coalescing (qpdf #444)
- `.planning/research/ARCHITECTURE.md` — the run record's required provenance fields; run ID scheme
  addressing immutable original bytes; index-mode/rewrite-mode single walker

### Phase 1 output this phase builds on
- `.planning/phases/01-conformance-harness-engine-spike/01-CONTEXT.md` — D-01..D-04 (corpus tiers,
  the independent-prober circularity rule)
- `.planning/phases/01-conformance-harness-engine-spike/PLAYA-DECISION.md` — the GO verdict for
  `playa-pdf` with per-file evidence; `pdfminer.six` was never installed
- `.planning/phases/01-conformance-harness-engine-spike/01-04-SUMMARY.md` — the two-layer render
  assertion and why cross-engine pixel identity is impossible
- `.planning/phases/01-conformance-harness-engine-spike/TJ-REFIT-RESULTS.md` — measured Δwidth
  figures and the run whose advance (137.76pt) is a known-good baseline
- `corpus/sources.md` — corpus provenance, the 57-producer breakdown, and the disclosed substitutions

</canonical_refs>

<code_context>
## Existing Code Insights

Unlike Phase 1, there is now a codebase. ~1,100 lines of tooling plus 37 tests, all green.

### Reusable Assets

- **`tools/probe_corpus.py`** (250 lines) — `probe_file()`, `_probe_font()`, `_flags_are_symbolic()`,
  `_content_stream_bytes()`. Plain structural font inspection that already distinguishes Type0,
  Type3, symbolic and subset fonts. **Critical constraint: this is D-04's independent verifier and
  must NOT be wired to consume the Phase 2 interpreter.** Reusing the interpreter inside the prober
  makes the corpus check circular and it proves nothing. Phase 2 may read from `probe_corpus.py`;
  `probe_corpus.py` must never read from Phase 2.
- **`spike/playa_decode_probe.py`** (248 lines) — the established single module boundary for `playa`
  decode calls, with a `pdfminer.six` fallback path behind an `--engine` flag. Preserve the
  one-module boundary however the code is reorganised.
- **`harness/`** — three-engine differential rendering, masked diff, and the corpus runner. Phase 2's
  provenance round-trip (Gate G1) should be verified through this rather than a new mechanism.
- **`corpus/`** — 216 real documents, 57 producers, all 15 structural categories, with
  `manifest.json` recording which document covers what. This is what D-03's threshold gets tuned
  against and what every Gate G1 criterion is measured on.

### Established Patterns

- Verification is **differential and measured**, not asserted. Phase 1 derived its render tolerance
  from 2,476 pages rather than picking a number; D-03 applies the same discipline to the space
  threshold.
- Checks must be able to fail. Phase 1 produced three checks that reported green while measuring the
  wrong thing — a decision-coverage gate that passed 0/0 on four decisions, a producer cap keyed on a
  string that split one product into two buckets, and a corpus label asserting a font class the
  document did not contain. **Before trusting a Phase 2 gate, demonstrate it failing.**
- Licensing boundary is a directory boundary: AGPL components stay CI-only and unreachable from any
  served path. `tools/license_gate.py` enforces it on the resolved lockfile.

### Integration Points

This phase's run map is consumed by Phase 3 (rewrite engine — same walker, rewrite mode), Phase 5
(find and replace — a client query over this index), and Phase 7 (all text-derived exports). A second
extraction path appearing anywhere downstream is a signal that this model is under-specified; the fix
is here, not a fork.

</code_context>

<specifics>
## Specific Ideas

- **Measure the refusal rate.** D-04 chooses refusal over guessing, which is right, but the cost is
  unquantified. Report what fraction of runs across the 216-document corpus end up not-editable and
  why, broken down by reason. A high number is a finding to surface, not a number to absorb quietly.
- **The prober must stay independent.** Repeated from Phase 1 D-04 because this is the phase where
  the temptation to wire them together first becomes real — the interpreter will look like a better
  category detector than the structural prober, and using it would make the corpus self-certifying.
- **Gate G1's round-trip is extract → locate → rewrite → re-extract.** Note that it names *rewrite*,
  which Phase 3 owns. Phase 2 needs enough of a write path to prove IDs survive a round trip without
  building the rewrite engine — the boundary between "enough to prove provenance" and "the Phase 3
  engine" should be drawn explicitly during planning.
- Byte-level round-trip equality is **not** a valid correctness test — qpdf-class libraries silently
  repair broken xrefs. Carried from Phase 1.

</specifics>

<deferred>
## Deferred Ideas

- **Progress affordance for the first full-document search** — a direct consequence of D-06's
  page-at-a-time indexing. Belongs to Phase 4/5 where the UI exists, but it is a known consequence
  now rather than a surprise later.
- **Background full-index after page 1** — the third indexing option, offering the best experience
  at the cost of a partially-complete index to reason about. Revisit in Phase 4 if the first-search
  cost proves painful in practice.
- **Surfacing shared Form XObjects to the user** — they are marked not-editable in v1 because editing
  one changes every page referencing it. Explaining *why* to a user, or offering a "edit all
  instances" affordance, is a Phase 4 UI question.
- **Ground-truth text corpus as a reusable asset** — if D-03's tuning produces a labelled
  ground-truth set, it may be worth keeping as a permanent extraction-quality regression suite rather
  than a one-off tuning input.

</deferred>

---

*Phase: 2-Text Model*
*Context gathered: 2026-08-12*
