# Phase 2: Text Model - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-12
**Phase:** 2-Text Model
**Areas discussed:** Run boundaries, Ambiguous encoding, Partial editability, Indexing eagerness (all four presented, all four selected)

---

## Q1 — What is ONE run, the unit a user selects and replaces?

| Option | Description | Selected |
|--------|-------------|----------|
| Visual line | Merge glyphs across operator boundaries into what reads as a line; break on font/size/baseline change or a gap over threshold. Matches what a user thinks they're clicking. Cost: one line spans several operators, so a replacement must rewrite all of them coherently | ✓ |
| Text-showing operator | One run = one Tj/TJ. Mirrors what the PDF stores; simplest to rewrite. Cost: sentences are split across operators for kerning, so clicking "Taxpayer" might select "Taxp" | |
| Word | Break at the space threshold, each word a run. Intuitive granularity. Cost: replacing a word in a justified line changes that line's spacing, and threshold errors become directly user-visible | |

**Notes:** Couples the run model to the rewrite engine — Phase 3 inherits the multi-operator rewrite requirement.

## Q2 — What does the decision table do on an ambiguous font (Symbolic + /Encoding)?

| Option | Description | Selected |
|--------|-------------|----------|
| Refuse, log the ambiguous branch | Mark not-editable with a stated reason, record which branch fired. Consistent with rejecting white-box overlay — a confident wrong result is the failure this product exists to avoid. Cost: some genuinely editable text refused, rate unknown until measured | ✓ |
| Pick a documented branch, log, allow | Choose the likeliest interpretation and let the edit proceed. Fewer refusals. Cost: when wrong, output is silently wrong — the harness would be catching our own deliberate guess | |
| Guess but flag visually | Allow the edit, mark the run lower-confidence. Cost: pushes a correctness judgement onto a user with no way to evaluate it | |

**Notes:** CONTEXT.md records that the refusal *rate* must be measured against the corpus during the phase — a high number is a finding, not a number to absorb.

## Q3 — A run is mostly clean but contains one unmappable glyph

| Option | Description | Selected |
|--------|-------------|----------|
| Split the run at the bad glyph | Editable fragments stay editable; only the problem glyph locks. Best coverage. Cost: run boundaries depend on glyph-level classification, so the map fragments | ✓ |
| Whole run not-editable | Simplest and most conservative. Cost: one stray character locks a paragraph the user expects to edit | |
| Editable, preserve bad glyph verbatim | Maximum editability. Cost: strong candidate for producing visibly wrong output | |

## Q4 — How eagerly does a document get indexed?

| Option | Description | Selected |
|--------|-------------|----------|
| Page-at-a-time, cached | First page usable immediately, memory proportional to pages visited. Cost: first full-document search pays the whole parse cost at once | ✓ |
| Eager whole-document | Search instant afterwards, index complete. Cost: opening a 400-page document blocks on every page — worst first impression for a tool pitched as faster than Acrobat | |
| Page-at-a-time + background full index | Best experience. Cost: two code paths and a partially-complete index — what does find return at 60%? | |

**Notes:** Deferred to Phase 4/5 — a visible progress affordance for the first full-document search.

---

## Follow-ups (raised because Q1 and Q3 interact)

### Q5 — A visual line splits into three pieces. What do run IDs address?

| Option | Description | Selected |
|--------|-------------|----------|
| Sub-runs are addressable | Each editable fragment gets its own ID; an ID always names something actionable. Cost: ID count per line varies with content | ✓ |
| Line keeps one ID with sub-spans | Run map stays line-shaped and stable. Cost: edits need a second coordinate beyond the run ID | |
| Line has one ID and locks | Simplest, but contradicts Q3 — offered only in case Q3 looked wrong on reflection | |

### Q6 — How do we know the synthetic-space threshold is right?

| Option | Description | Selected |
|--------|-------------|----------|
| Tune against the corpus with a measured target | Measure extraction error across the 216 documents, minimise, pin the number with the measurement recorded. Same discipline as Phase 1's derived 8% render tolerance. Cost: needs ground-truth text for a corpus sample | ✓ |
| Fixed multiple of the font's space width | Simple, adapts per font. Cost: still a guessed constant, failing on exactly the pathological documents the corpus exposes | |
| Per-font adaptive from observed gaps | Most robust across producers. Cost: complex, and uniform spacing gives the clusterer nothing to separate | |

---

## Claude's Discretion

- Whether Phase 1's spike modules are absorbed, rewritten, or left alone — with the constraint that
  `playa` decode calls stay confined to one module, no abstraction layer
- Internal structure of glyph and run records beyond the provenance fields research already fixed
- How ground-truth text for threshold tuning is obtained

## Deferred Ideas

- Progress affordance for the first full-document search — Phase 4/5
- Background full-index after page 1 — revisit in Phase 4 if first-search cost proves painful
- Surfacing shared Form XObjects to the user, or an "edit all instances" affordance — Phase 4
- Keeping the ground-truth set as a permanent extraction-quality regression suite
