# Phase 8: PDF/A, then DOCX - Context

**Gathered:** 2026-08-30
**Status:** Ready for planning
**Source:** Batch planning pass (no `/gsd:discuss-phase` run). Phase boundary and constraints
transcribed from `ROADMAP.md` and `REQUIREMENTS.md`. Everything not listed as a decision is
Claude's Discretion.

<domain>
## Phase Boundary

The two archival/interchange formats users ask for exist, are honest about what they are, and
neither can eat the project.

**In scope:** EXPO-06 (PDF/A), EXPO-07 (DOCX), EXPO-08 (per-document pre-conversion warning).

Two gates: **G7a** (veraPDF passes at PDF/A-2b across a fixture corpus in CI) and **G7b** (the DOCX
scope ceiling is written into the phase definition *before* work starts).

**Explicitly NOT in scope — this is the load-bearing list, not boilerplate:**
- Unruled tables, multi-column reading order, header/footer reconstruction, and round-trip back
  into the tool. All four are named in ROADMAP criterion 2 as explicitly excluded from DOCX.
- LibreOffice anywhere in the pipeline. `REQUIREMENTS.md` Out of Scope: it imports through Draw,
  producing disconnected text frames rather than paragraphs, and brings profile locking, no
  timeout, memory leaks, zombie processes, and a large native attack surface — while buying almost
  nothing, since our own layout inference sets the ceiling.
- `pdf2docx`. MIT at the top level, pulls `PyMuPDF>=1.26.7` transitively. `REQUIREMENTS.md` names
  it as **the most likely accidental route into an AGPL violation**, and Phase 1's ENG-07 gate was
  proven by deliberately adding it and watching CI go red.
- A second extraction path. DOCX is generated as OOXML directly from the Phase 2 text model.

## Hard Dependency

Phase 7 (Gate G6) and the Phase 3 save pipeline. DOCX specifically inherits the reading-order and
block-structure layer built for Markdown/HTML in Phase 7 (see `07-CONTEXT.md` D-7.2).

</domain>

<decisions>
## Implementation Decisions

### Settled upstream — do not relitigate

- **D-8.1: PDF/A ships before DOCX, and PDF/A is validator-gated.** EXPO-06 and ROADMAP criterion
  1: veraPDF passes at the chosen conformance level (**PDF/A-2b**) across a fixture corpus in CI,
  **not on spot checks**. The roadmap's own justification: a PDF/A file that does not validate is
  worse than no feature. veraPDF is a CI-only tool here; confirm its licence posture against
  ENG-07's gate before wiring it (Phase 1 established that GPL/LGPL tools are permitted only as a
  file-in/file-out subprocess, and AGPL not at all in the runtime).

- **D-8.2: The DOCX scope ceiling is written down before any DOCX work starts, and is itself the
  G7b gate.** ROADMAP criterion 2 states the ceiling verbatim: single-column body text, headings by
  font-size clustering, bold/italic, inline images, ruled tables only, everything else as plain
  paragraphs. Explicitly not: unruled tables, multi-column reading order, header/footer
  reconstruction, round-trip back into the tool. **Writing this ceiling into the phase definition
  is a task, ordered first.**

- **D-8.3: DOCX is generated as OOXML directly from the Phase 2 text model.** EXPO-07 and ROADMAP
  criterion 3. No LibreOffice, no `pdf2docx`, no second extraction path — see the scope list above
  for why each is excluded.

- **D-8.4: The pre-conversion warning names what will degrade in *this specific document*.**
  EXPO-08 and ROADMAP criterion 4 — e.g. "3 tables and a 2-column section detected". The roadmap
  notes this is cheap *because the layout analysis already ran*, which means the warning is a
  read of the Phase 7 block-structure layer's own output, not a separate document scan.

- **D-8.5: DOCX must be independently cuttable.** ROADMAP criterion 5: deleting it leaves every
  other export still passing its gate. This is a structural requirement on module boundaries and
  on the test suite, not an aspiration — it should have its own verification.

- **D-8.6: "If we just improved table detection a bit" is the named tripwire.** ROADMAP calls DOCX
  Risk #8: the last feature becomes the longest phase and drags in dependencies that compromise the
  posture built earlier, prevented by one written paragraph. Any plan task that widens the D-8.2
  ceiling is out of scope by construction and belongs in a follow-up phase.

### Claude's Discretion

- OOXML generation approach (hand-built XML into a zip container vs. a permissively-licensed
  library) — subject to the AGPL gate and to D-8.3.
- PDF/A remediation strategy: which non-conformances are fixed automatically (font embedding, colour
  profiles, XMP metadata, transparency) versus refused with a named reason, consistent with the
  project's refuse-visibly discipline (EDIT-04, CLAS-04, FIND-05).
- The PDF/A fixture corpus's composition and size, subject to it being a corpus and not spot checks.
- Font-size clustering algorithm for heading inference.
- How the pre-conversion warning is surfaced in the UI.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `CLAUDE.md` — project guidelines
- `.planning/ROADMAP.md` — Phase 8 section: goal, five success criteria, the Risk #8 note, and the
  "strictly last, independently cuttable" ordering constraint (#10)
- `.planning/REQUIREMENTS.md` — EXPO-06/07/08, plus the Out of Scope rows on `pdf2docx`,
  LibreOffice, and AGPL runtime libraries
- `.planning/research/STACK.md` — `pdftopdfa` 0.9.0 as a working reference for the
  pikepdf/fontTools shape; licence posture
- `.planning/research/PITFALLS.md` — PDF/A conformance traps
- `.planning/phases/07-exports/07-CONTEXT.md` and the Phase 7 plans — the block-structure /
  reading-order layer (D-7.2) this phase consumes, and EXPO-05's single-extraction-path rule
- `.planning/phases/03-rewrite-engine-font-pipeline/03-CONTEXT.md` — the save pipeline, D-13
  (one subset per family per document) and FONT-02/03/04 font-embedding behaviour that PDF/A's
  embedding rules will exercise
- `engine/fonts.py`, `engine/index.py`, `engine/records.py` — the font write side and the text model
- `tools/license_gate.py`, `Dockerfile.ci`, `.github/` — the ENG-07 AGPL gate that any new
  dependency in this phase must pass

</canonical_refs>

<specifics>
## Specific Ideas

- ROADMAP flags this phase for `/gsd:plan-phase --research-phase`: PDF/A conformance levels and
  font-embedding rules that only a validator catches, and DOCX layout inference which is heuristics
  all the way down. This is the one remaining phase where the roadmap asks for a real research pass.
- G7b is unusual in that it is satisfied by **a written paragraph existing before work starts**.
  The plan should order that task first and make its acceptance criterion a file assertion, in the
  same style as Phase 3's `G2B-GATE-RESULTS.md` and Phase 1's `PLAYA-DECISION.md` /
  `TJ-REFIT-RESULTS.md` precedent — a `## Decision` header, dated evidence, an explicit
  "what was NOT tested" section.
- veraPDF in CI is the same shape as Phase 1's three-engine harness: a validator run over a fixture
  corpus with the build failing on regression. Reuse `harness/`'s existing CI wiring rather than
  standing up a parallel one.
- PDF/A-2b's font-embedding rules interact directly with Phase 3's subsetting: every font must be
  embedded, and subset tags must be well-formed. FONT-04's `/Widths` consistency assertion and
  FONT-05's fresh-subset-tag rule are already the right behaviour; the plan should verify rather
  than rebuild.

</specifics>

<deferred>
## Deferred Ideas

- PDF/A-1b or PDF/A-3 conformance levels — the roadmap chose PDF/A-2b.
- Any widening of the D-8.2 DOCX ceiling — by construction, a follow-up phase.
- DOCX round-trip back into the tool — explicitly excluded.
- DOCX→PDF conversion (CONV-01) — v2.

</deferred>

---
*Phase: 08-pdf-a-then-docx*
*Context assembled: 2026-08-30 during batch planning of Phases 4–8*
