# Roadmap: PDF Tool

## Overview

This is a PDF engine with a web front-end, not a web app with a PDF feature, and the phase order
follows from that. All the risk sits upstream of the content-stream interpreter, so all the risk is
front-loaded: a conformance harness and a real-world corpus before any engine code, a text model
before any rewrite, a rewrite engine shipped together with its font pipeline, and no web tier at all
until a word can be replaced using a character absent from the embedded font subset and survive
inspection in three renderers plus Acrobat. That milestone — Gate G2b — is the project gate. If it
fails, the product does not exist, and it should fail in week three rather than month four. Only
after it passes does conventional work begin: viewer, hardening, find-and-replace, page ops,
exports, and finally PDF/A and DOCX.

**Phase numbering note.** `research/SUMMARY.md` numbers its proposed sequence 0–7. This roadmap
numbers the same sequence 1–8 to match GSD's convention (integer phases start at 1). The ordering is
unchanged. Each phase carries its SUMMARY.md gate name (G0…G7b) so traceability back to the research
survives the renumber.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Conformance Harness + Engine Spike** - Real-world corpus, three-engine masked-diff CI, and the two bets that gate everything downstream — no product code
- [ ] **Phase 2: Text Model** - The keystone: content-stream interpreter with per-glyph provenance, plus per-page and per-run editability classification
- [ ] **Phase 3: Rewrite Engine + Font Pipeline** - Replace text with correct widths AND subset/embed a bundled font in one phase — the project gate
- [ ] **Phase 4: Web Tier Walking Skeleton + Hardening** - First untrusted input: isolation, structural ephemerality, viewer, and the first in-browser edit with undo
- [ ] **Phase 5: Find and Replace Across All Pages** - The core value in its user-facing form: match list and preview first, apply second
- [ ] **Phase 6: Page Ops and Merge** - Insert, reorder, rotate, delete, merge PDF and image — entirely in the browser, zero server round trips
- [ ] **Phase 7: Exports** - Page images, compress, split, flatten, and text/Markdown/HTML — all consuming the one run index
- [ ] **Phase 8: PDF/A, then DOCX** - Validator-gated PDF/A, then best-effort DOCX within a written ceiling, independently cuttable

## Phase Details

### Phase 1: Conformance Harness + Engine Spike

**Goal**: Every correctness claim this project will ever make has a machine that checks it, and the two unproven bets underneath the engine are settled before a line of engine code exists
**Depends on**: Nothing (first phase)
**Requirements**: ENG-01, ENG-02, ENG-03, ENG-04, ENG-05, ENG-06, ENG-07
**Success Criteria** (what must be TRUE):

  1. A corpus of 100–300 wild-harvested PDFs (not generated), weighted toward invoices and contracts and covering subset fonts, Type0/Identity-H, symbolic fonts, Type3, CID-keyed CFF, `/Contents` arrays, inline images, Form XObjects, annotation appearance streams, justified and right-aligned text, tables, an OCR'd scan, vector-outlined text, encrypted and malformed files, is checked in and enumerated
  2. The three-engine differential rasterizer (pdfium, Poppler, MuPDF) runs in CI and asserts a *masked* image diff of the unedited region is pixel-identical — not merely similar — passing on an identity transform across the whole corpus, with `qpdf --check` and `pdfcpu validate` run on every engine output
  3. `playa-pdf` decodes encodings and glyph geometry on at least 4 real documents including one Type0/Identity-H and one subset-font document — or the switch to `pdfminer.six` is made and recorded in this phase, not later
  4. A TJ-refit prototype fits replacement text into an original run's width within |Δwidth| < 0.5pt on a hand-picked run
  5. CI fails the build on an AGPL package anywhere in the resolved lockfile — proven by deliberately adding a transitively-AGPL dependency (`pdf2docx`) and watching the build go red — and the one-page data-flow retention map is written *before* any infrastructure is selected

**Plans**: 6 plans

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Retention map, repo scaffolding, and the AGPL lockfile gate proof (ENG-06, ENG-07)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Public-tier corpus assembly + manifest, all 15 D-03 categories (ENG-01)
- [x] 01-06-PLAN.md — TJ-refit width-fitting prototype (ENG-05)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-04-PLAN.md — Three-engine differential rendering harness + structural validators (ENG-02, ENG-03)
- [ ] 01-05-PLAN.md — playa-pdf decode spike against real documents (ENG-04)

**Wave 4** *(blocked on Wave 3 completion)*

- [ ] 01-03-PLAN.md — Independent structural prober + private-tier fetch mechanism (ENG-01, D-01/D-02/D-04)

**Research**: yes — phase is itself the spike; no separate `--research-phase` pass needed
**Parallel**: no — gates everything
**UI hint**: no

*Gate G0. Retires Risk #2 (silent wrong output), Risk #3 (playa-pdf on the critical path), Risk #5 (TJ-refit has no reference implementation), Risk #7 (infrastructure that is secretly storage). No user-facing deliverable, deliberately: retrofitting a corpus after the rewrite engine exists means every prior release was unvalidated.*

### Phase 2: Text Model

**Goal**: Any run of text in any real document can be located, addressed, and honestly labelled as editable or not — before the user types
**Depends on**: Phase 1 (Gate G0)
**Requirements**: TEXT-01, TEXT-02, TEXT-03, TEXT-04, TEXT-05, TEXT-06, TEXT-07, TEXT-08, CLAS-01, CLAS-02, CLAS-03, CLAS-04, CLAS-05
**Success Criteria** (what must be TRUE):

  1. Provenance round-trips on the corpus — extract → locate → rewrite → re-extract returns the same run IDs and glyph records, with run IDs addressing the immutable original bytes so ordinals never drift across edits
  2. Glyph-at-a-time (LaTeX/CAD) and two-column documents reconstruct into readable runs; `/Contents` arrays are coalesced before parsing so no tokenizer fuses operators across a stream-part boundary; text inside Form XObjects, annotation appearance streams and tiling patterns is found, and shared Form XObjects are marked not-editable rather than silently corrupting every page that references them
  3. The corpus OCR'd scan classifies as "searchable, not editable" and never as editable text; the vector-outlined page lands in its own bucket distinct from a scan; a 40-page contract with 3 scanned pages reports 37 editable pages and 40 page-op-able pages
  4. Every text run carries one of three states — editable in original font / editable with substitution / not editable with a stated reason — available before any edit is attempted, with symbolic, Type3 and no-`/ToUnicode` runs named specifically
  5. `Code→Glyph` and `Code→str` are distinct types the type checker refuses to interchange, and every font logs which branch of the documented forward-encoding decision table fired

**Plans**: TBD
**Research**: yes — `/gsd:plan-phase --research-phase`. The simple-font encoding chain has ≥5 paths selected by the `Symbolic` flag, `/Encoding` presence and embedded cmap subtables, and the spec does not cleanly resolve `Symbolic` + `/Encoding`. The synthetic-space gap threshold needs tuning against the Phase 1 corpus and "is the whole game" for extraction quality.
**Parallel**: no — five downstream features sit on this
**UI hint**: no

*Gate G1. Classification (CLAS-01..05) ships here rather than as its own phase: it is nearly free once the run index exists, blocks nothing, and gates the quality of every text feature's failure mode. CLAS-06 (thumbnail badges) and CLAS-07 (refusal screen) are the UI surfaces of this work and land in Phase 4, where a UI exists.*

### Phase 3: Rewrite Engine + Font Pipeline

**Goal**: A word in a real document can be replaced — including with a character the document never contained — and the output looks like nothing happened, everywhere
**Depends on**: Phase 2 (Gate G1)
**Requirements**: EDIT-02, EDIT-03, EDIT-04, FONT-01, FONT-02, FONT-03, FONT-04, FONT-05, FONT-06
**Success Criteria** (what must be TRUE):

  1. **G2a** — replacing a run whose glyphs all exist in the embedded subset produces a `qpdf --qdf` normalization diff confined to the edited operators, |Δwidth| < 0.5pt, a text matrix after the edited run bit-identical within epsilon to what it was before, `qpdf --check` clean, and a zero masked pixel diff outside the run in all three engines
  2. **G2b — THE PROJECT GATE** — the same result when the replacement uses a character *absent from the embedded font subset*: pixel-identical outside the edited run in pdfium, Poppler and MuPDF; opens without a repair prompt in Acrobat Reader, macOS Preview and Chrome; copy-paste out of Acrobat yields the correct Unicode; the output font passes OTS
  3. Untouched text elsewhere in the document that uses the same font still renders correctly after a re-subset — subsetting runs once at save over the whole-document glyph union, every re-subset gets a fresh subset tag so two subsets of the same family never collide, and `/Widths` are regenerated with a consistency assertion against the font program's own metrics so no code outside `FirstChar..LastChar` falls back to a `/MissingWidth` of 0
  4. Substitution picks its face from a static mapping table (never a heuristic), re-encodes the entire visual run rather than half of one, and survives side-by-side review at 100% zoom against the corpus with no visible seam mid-paragraph
  5. An edit that cannot be performed correctly is refused with a named reason rather than guessed at, and overflow is measured and reported before commit — condensed only within 90–95%, visibly refused beyond

**Plans**: TBD
**Research**: yes — `/gsd:plan-phase --research-phase`. The TJ-refit algorithm has no library and no reference implementation; kerning-split runs are the documented top edge-case failure source; bundled-font metric-substitution quality mid-paragraph is unverified (Risk #4). Also verify bundled fonts' OS/2 `fsType` bits, which frequently contradict the actual OFL license and are read by corporate preflight tools.
**Parallel**: no — G2b gates the entire web tier
**UI hint**: no

*Gates G2a and G2b. One phase, not two: replace-without-subsetting is PDF-XChange's shipped limitation, which the market already has and nobody likes. The honest MVP boundary is replace + subsetting together, or neither. Still CLI-only (`pdftool edit`) — no web tier work begins before G2b passes. This phase exists to retire Risk #1, the unproven composition.*

### Phase 4: Web Tier Walking Skeleton + Hardening

**Goal**: A stranger can open the site with an untrusted PDF, see it rendered faithfully, understand exactly what is and is not editable and where each operation runs, edit one text run, and undo it — with nothing about the session surviving on the server
**Depends on**: Phase 3 (Gate G2b — hard gate, no web tier work starts before it passes)
**Requirements**: INGE-01, INGE-02, INGE-03, INGE-04, PRIV-01, PRIV-02, PRIV-03, PRIV-04, PRIV-05, PRIV-06, PRIV-07, VIEW-01, VIEW-02, VIEW-03, VIEW-04, CLAS-06, CLAS-07, EDIT-01, EDIT-05, FONT-07
**Success Criteria** (what must be TRUE):

  1. Ephemerality is structural, not a policy: a canary-marker retention test passes in CI against scratch, queue, logs, object store and error reporter on **both** the success path and the crash path; killing the content-addressed cache mid-session leaves the session working via an exercised `409 SOURCE_MISSING` re-upload path; scratch is tmpfs in a per-job container and queues carry opaque short-TTL handles, never document bytes
  2. Hostile input dies on its own limits rather than on the host — a decompression bomb, a cyclic page tree and a self-referencing Form XObject each fail inside an isolated worker with `RLIMIT_AS` and a hard wall-clock timeout; PDF parsing never runs in the request process; uploads are accepted by magic-byte sniff and a size cap, never by file extension
  3. Document routes send `Cache-Control: no-store` and the CDN is verified to report `BYPASS`/`DYNAMIC` (Cloudflare's default cacheable-extension list includes `.pdf`); `isEvalSupported: false` and a CSP forbidding `eval` are in force; no document content appears in logs or error reports
  4. A user opens a PDF — including a password-protected one by supplying the password, and a signed one that warns before saving that a rewrite invalidates the signature — sees pages rendered faithfully with page 1 interactive before the last page finishes parsing, can select and copy text and use browser find, and sees per-page classification badges in the thumbnail rail with uneditable pages naming their reason plus a specific external OCR route and a one-click "tell me when OCR ships"
  5. A user selects a text run in the browser — hit-tested against server-issued boxes, never pdf.js text items — replaces it, restyles it (size, weight, style, colour), sees per operation whether it ran locally or on the server, and reverts it with one Ctrl+Z

**Plans**: TBD
**Research**: no — FastAPI + React/Vite scaffolding and container sandboxing are well-documented and the architecture decisions are already settled in SUMMARY.md. One exception handled as a task, not a research pass: re-verify the CVE specifics in PITFALLS' attack table against NVD at implementation time, since they are partly aggregator-sourced.
**Parallel**: no — gates Phases 5, 6 and 7
**UI hint**: yes

*Gate G3. The largest phase by requirement count (20), deliberately: it is the single "first public exposure" boundary and its gate is one indivisible claim — safe to hand a stranger. The recipe store and undo land here because this is the first mutating feature, and retrofitting undo across the client page-ops path and the server text path is a retrofit nobody wins. EDIT-01 lands here rather than in Phase 3 because its observable behaviour is a browser interaction and Phase 3 is CLI-only by binding constraint — see Deviations below.*

### Phase 5: Find and Replace Across All Pages

**Goal**: A user changes a word everywhere in a 40-page document in one action, sees exactly what will change before committing, and gets one undo
**Depends on**: Phase 4 (Gate G3)
**Requirements**: FIND-01, FIND-02, FIND-03, FIND-04, FIND-05, FIND-06
**Success Criteria** (what must be TRUE):

  1. Search across all pages uses the same normalization the interpreter used — intra-word TJ adjustments collapsed, ligatures normalized — defaulting to case-insensitive substring with working "match case" and "whole words only" toggles
  2. Matches are listed with page number, surrounding context and a live count; clicking a match jumps to it; individual matches can be opted out before applying
  3. Unreplaceable matches appear in the same list, disabled, with the reason shown — never silently filtered out
  4. Replace-all across a 40-page corpus contract changes every remaining match in one action, and the masked differential diff is confined to the edited runs on every changed page in all three engines
  5. One Ctrl+Z reverts the entire replace-all batch as a single step

**Plans**: TBD
**Research**: no — a client-side query over the cached index producing N ordinary overrides through the ordinary apply path. There is no `POST /find-replace`; a separate bulk endpoint means two rewrite implementations within six months.
**Parallel**: yes — independent of Phases 6 and 7 after G3
**UI hint**: yes

*Gate G4. Find and replace are two features, not one: find needs the visible-text index, replace needs the inverse map back to operator byte-spans plus width recalculation. Build the match list and preview (FIND-01..05) before wiring apply (FIND-06) — it depends on the index, not the rewrite engine, so it demos early and de-risks the rewrite by making its inputs visible. Estimating them as one item is the most likely source of a blown estimate.*

### Phase 6: Page Ops and Merge

**Goal**: Every page-shaped operation works instantly and never leaves the browser, so the privacy claim becomes literally true for a whole class of session
**Depends on**: Phase 4 (Gate G3) — zero dependency on the text engine
**Requirements**: PAGE-01, PAGE-02, PAGE-03, PAGE-04, PAGE-05, PAGE-06, PAGE-07, PAGE-08, PAGE-09
**Success Criteria** (what must be TRUE):

  1. A page-operations-only session produces its download entirely in the browser, with **zero requests to document routes**
  2. Inserting a blank page inherits MediaBox and rotation from the adjacent page and shows the user what it inherited — never a silent Letter default; reorder, rotate and delete work on any page including uneditable ones
  3. Merging two documents that both embed `ABCDEF+Arial` with different subsets renders both correctly in all three engines — fonts deduped by content hash, never by `/BaseFont`
  4. No other page changes after a resource-dictionary write — inherited `/Resources` are copied, never mutated — and merging another PDF preserves per-page page size by default, nests outlines, and announces form-field collision handling either way
  5. An image (PNG, JPEG, WebP, HEIC, transparency composited) merges as a new page or is placed on an existing page with visible aspect-ratio locking, not a hidden modifier key

**Plans**: TBD
**Research**: no — page ops are exactly what `@cantoo/pdf-lib` is good at, and the merge correctness traps are already enumerated with their fixes.
**Parallel**: yes — fully independent of the text engine; the natural parallel workstream alongside Phase 5
**UI hint**: yes

*Gate G5. Depends on Phase 4 only for the SPA shell and viewer, not for anything in the engine. Nothing in this phase touches the text model.*

### Phase 7: Exports

**Goal**: A user gets their document out in the format they actually came for, and every text-derived format comes out of the one run index
**Depends on**: Phase 4 (Gate G3); consumes the Phase 2 run index
**Requirements**: EXPO-01, EXPO-02, EXPO-03, EXPO-04, EXPO-05
**Success Criteria** (what must be TRUE):

  1. Plain text, Markdown and HTML all consume the Phase 2 run index — a search of the codebase finds no second extraction path (a second path anywhere means the text model is under-specified, and the fix is Phase 2, not a fork)
  2. Pages export as PNG or JPEG at a chosen DPI, per-page or all pages as a zip, with 150 screen / 300 print defaults
  3. Compress is lossless and structural by default, with image downsampling as an explicit labeled choice that shows before/after size and a preview
  4. Split and flatten produce outputs that pass `qpdf --check` and a masked differential diff confined to the intended change in all three engines

**Plans**: TBD
**Research**: no — `pypdfium2` and Pillow are solved problems; `pdftopdfa` 0.9.0 is a working reference for the pikepdf/fontTools shape.
**Parallel**: yes — independent of Phases 5 and 6 after G3
**UI hint**: yes

*Gate G6. Compress deserves more polish than its complexity suggests — Smallpdf's own data puts it at ~34% of usage, the most-used PDF operation in the category, more than any conversion.*

### Phase 8: PDF/A, then DOCX

**Goal**: The two archival/interchange formats users ask for exist, are honest about what they are, and neither can eat the project
**Depends on**: Phase 7 (Gate G6) and the Phase 3 save pipeline
**Requirements**: EXPO-06, EXPO-07, EXPO-08
**Success Criteria** (what must be TRUE):

  1. **G7a** — veraPDF passes at the chosen conformance level (PDF/A-2b) across a fixture corpus in CI, not on spot checks. A PDF/A file that does not validate is worse than no feature
  2. **G7b** — the DOCX scope ceiling is written into the phase definition *before* work starts: single-column body text, headings by font-size clustering, bold/italic, inline images, ruled tables only, everything else as plain paragraphs. Explicitly not: unruled tables, multi-column reading order, header/footer reconstruction, round-trip back into the tool
  3. DOCX is generated as OOXML directly from the Phase 2 text model — no LibreOffice, no `pdf2docx`, no second extraction path — inheriting the reading-order and block-structure layer built for Markdown/HTML in Phase 7
  4. The pre-conversion warning names what will degrade in *this specific document* ("3 tables and a 2-column section detected"), which is cheap because the layout analysis already ran
  5. DOCX can be cut without touching anything else — deleting it leaves every other export still passing its gate

**Plans**: TBD
**Research**: yes — `/gsd:plan-phase --research-phase`. PDF/A conformance levels and font-embedding rules that only a validator catches; DOCX layout inference is heuristics all the way down.
**Parallel**: no — strictly last
**UI hint**: no

*Gates G7a and G7b. DOCX is Risk #8: the last feature becomes the longest phase and drags in dependencies that compromise the posture built earlier. Prevented by one written paragraph. Any conversation containing "if we just improved table detection a bit" is the tripwire.*

## Ordering Rationale

The binding constraints behind this sequence, restated so a future reader does not re-derive a
different one:

1. **Everything upstream of the interpreter gates everything downstream.** All the risk sits in
   Phases 1–3. The viewer, page ops and exports are conventional work on well-trodden libraries;
   sequencing them early produces an impressive demo on an unproven core.

2. **The harness and corpus come first, before any engine code.** Retrofitting a corpus after the
   rewrite engine exists means every prior release was unvalidated. Phase 1 has no user-facing
   deliverable. That is intentional.

3. **No web tier before G2b.** Discovering the font layer does not work after building a viewer is
   the expensive failure mode.

4. **Rewrite engine and font pipeline are one phase.** Replace-without-subsetting is a shipped
   competitor limitation, not an increment.

5. **Classification ships with the text model.** Nearly free once the run index exists; gates the
   quality of every text feature's failure mode.

6. **Find and replace are separate features**, built in that order within Phase 5.
7. **The recipe/undo model lands with the first mutating feature** (Phase 4).
8. **Page ops have zero dependency on the text engine** — Phase 6 is parallelizable.
9. **Exports consume the Phase 2 run index.** A second extraction path anywhere is a signal the text
   model is under-specified; the fix is Phase 2, not a fork.

10. **DOCX is strictly last and independently cuttable.**

### Deviations from the research sequence

Two, both forced by requirement wording rather than by disagreement with the research:

- **EDIT-01 is in Phase 4, not Phase 3.** The instruction was that FONT-01..06 ship with
  EDIT-01..04. FONT-01..06 and EDIT-02..04 do ship together in Phase 3 — that pairing is the point
  and it is intact. But EDIT-01's observable behaviour is "select a text run *in the browser* and
  replace its text, hit-testing against server-issued boxes," and Phase 3 is CLI-only by binding
  constraint 3 (no web tier before G2b). Placing it in Phase 3 would either break that constraint or
  leave the requirement unverifiable at phase end. SUMMARY.md's own Phase 3 delivers "pdf.js viewer
  with server-issued hit boxes; single-run edit round trip," which is exactly EDIT-01. No ordering
  changes: the rewrite engine and font pipeline still ship together, still before any web tier.

- **CLAS-06 and CLAS-07 are in Phase 4, not Phase 2.** Constraint 5 puts classification with the
  text model, and CLAS-01..05 — all of the engine-side classification — are in Phase 2. CLAS-06
  (badges in the thumbnail rail) and CLAS-07 (the refusal screen with the OCR route) are the UI
  surfaces of that work and cannot exist before a UI does. SUMMARY.md's own Phase 3 lists
  "per-page classification badges in the thumbnail rail" for the same reason.

**Parallelization** (config `parallelization: true`): Phases 1 → 2 → 3 → 4 are strictly serial. After
Gate G3, Phases 5, 6 and 7 can run concurrently — Phase 6 is fully independent (no shared code with
the text engine at all), while 5 and 7 both read the Phase 2 run index but do not write to each
other's paths. Phase 8 waits on Phase 7.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → (5 ∥ 6 ∥ 7) → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Conformance Harness + Engine Spike | 4/6 | In Progress|  |
| 2. Text Model | 0/TBD | Not started | - |
| 3. Rewrite Engine + Font Pipeline | 0/TBD | Not started | - |
| 4. Web Tier Walking Skeleton + Hardening | 0/TBD | Not started | - |
| 5. Find and Replace Across All Pages | 0/TBD | Not started | - |
| 6. Page Ops and Merge | 0/TBD | Not started | - |
| 7. Exports | 0/TBD | Not started | - |
| 8. PDF/A, then DOCX | 0/TBD | Not started | - |

## Requirement Coverage

72 of 72 v1 requirements mapped. No orphans, no duplicates.

| Phase | Requirements | Count |
|-------|--------------|-------|
| 1. Conformance Harness + Engine Spike | ENG-01..ENG-07 | 7 |
| 2. Text Model | TEXT-01..TEXT-08, CLAS-01..CLAS-05 | 13 |
| 3. Rewrite Engine + Font Pipeline | EDIT-02, EDIT-03, EDIT-04, FONT-01..FONT-06 | 9 |
| 4. Web Tier Walking Skeleton + Hardening | INGE-01..INGE-04, PRIV-01..PRIV-07, VIEW-01..VIEW-04, CLAS-06, CLAS-07, EDIT-01, EDIT-05, FONT-07 | 20 |
| 5. Find and Replace Across All Pages | FIND-01..FIND-06 | 6 |
| 6. Page Ops and Merge | PAGE-01..PAGE-09 | 9 |
| 7. Exports | EXPO-01..EXPO-05 | 5 |
| 8. PDF/A, then DOCX | EXPO-06, EXPO-07, EXPO-08 | 3 |
| **Total** | | **72** |

---
*Roadmap created: 2026-08-12 from REQUIREMENTS.md and research/SUMMARY.md*
