# Phase 6: Page Ops and Merge - Context

**Gathered:** 2026-08-30
**Status:** Ready for planning
**Source:** Batch planning pass (no `/gsd:discuss-phase` run). Phase boundary and constraints
transcribed from `ROADMAP.md` and `REQUIREMENTS.md`. Everything not listed as a decision is
Claude's Discretion.

<domain>
## Phase Boundary

Every page-shaped operation works instantly and never leaves the browser, so the privacy claim
becomes literally true for a whole class of session.

**In scope:** PAGE-01..PAGE-09.

**Explicitly NOT in scope:**
- Anything touching the text model. This phase has **zero** dependency on the text engine —
  `ROADMAP.md` says so twice, and it is the reason Phase 6 is parallelizable with Phases 5 and 7.
- Exports (Phase 7) and PDF/A + DOCX (Phase 8).
- Page-size normalization on merge **by default** — `REQUIREMENTS.md` lists it in the Out of Scope
  table: it silently resizes the user's pages. Available as an explicit choice, never a default.

## Hard Dependency

Phase 4 (Gate G3) — but **only** for the SPA shell, the viewer, and the thumbnail rail. Nothing in
this phase touches the rewrite engine, the run index, or the server's document routes.

</domain>

<decisions>
## Implementation Decisions

### Settled upstream — do not relitigate

- **D-6.1: Page ops run entirely in the browser.** PAGE-09 is the phase's headline claim and its
  hardest test: a page-operations-only session produces its download **with zero requests to
  document routes**. This is the structural backing for PRIV-01's per-operation local/server
  disclosure — the disclosure is true because the override set is empty, not because a label says
  so. The test must assert on observed network traffic, not on a flag.

- **D-6.2: `@cantoo/pdf-lib` is the library.** `ROADMAP.md`: "page ops are exactly what
  `@cantoo/pdf-lib` is good at, and the merge correctness traps are already enumerated with their
  fixes." It is already a dependency of the Phase 4 client scaffold. Do not add a second
  client-side PDF library for this.

- **D-6.3: Fonts are deduped by content hash on merge, never by `/BaseFont`.** **AMENDED
  2026-08-30 after research — see `## Amendments`. `@cantoo/pdf-lib` does not dedupe at all,
  so this is "never add that optimization", not "override a dangerous default".** PAGE-06 and ROADMAP
  criterion 3. The named failure: merging two documents that both embed `ABCDEF+Arial` with
  *different* subsets. Deduping by name renders one of them wrong. This is the same family of bug
  Phase 3's D-13 (one subset per family per document) exists to prevent on the write side.

- **D-6.4: Inherited `/Resources` are copied, never mutated.** ROADMAP criterion 4: no other page
  changes after a resource-dictionary write. A page tree that inherits `/Resources` from an
  ancestor will otherwise have one page's edit silently alter every sibling.

- **D-6.5: An inserted blank page inherits MediaBox and rotation from the adjacent page and shows
  the user what it inherited.** PAGE-01, and it explicitly rules out "a silent Letter default" —
  which is the common library default and therefore the likely accidental behaviour.

- **D-6.6: Page ops work on *any* page, including uneditable ones.** ROADMAP criterion 2 and
  CLAS-05's framing: a 40-page contract with 3 scanned pages reports 37 editable pages and **40
  page-op-able** pages. Reorder/rotate/delete must not consult text classification at all.

- **D-6.7: Merging another PDF preserves per-page page size by default, nests outlines, and
  announces form-field collision handling either way.** ROADMAP criterion 4, PAGE-05. "Announces
  either way" means the user is told what happened whether or not there was a collision — silence
  on the no-collision path is not sufficient.

### Claude's Discretion

- Client-side state model for the page list and its undo integration with the Phase 4 undo store.
- Thumbnail regeneration strategy after a page op (re-render vs. reorder existing thumbnails).
- HEIC decode path in the browser (PAGE-07 requires it; browser support is uneven).
- How aspect-ratio locking is surfaced visually (PAGE-08 requires it be **visible**, not a hidden
  modifier key — the interaction design within that constraint is open).
- Whether image placement (PAGE-08) uses a drag-resize overlay or numeric fields or both.
- Memory strategy for large documents held entirely client-side.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `CLAUDE.md` — project guidelines
- `.planning/ROADMAP.md` — Phase 6 section: goal, five success criteria, and the note that this
  phase depends on Phase 4 only for the SPA shell and viewer
- `.planning/REQUIREMENTS.md` — PAGE-01..09, plus the Out of Scope rows on page-size normalization
  and on AGPL libraries in the runtime
- `.planning/research/PITFALLS.md` — the enumerated merge correctness traps and their fixes
- `.planning/research/STACK.md` — why `@cantoo/pdf-lib`, and the licence posture
- `.planning/phases/04-web-tier-walking-skeleton-hardening/04-CONTEXT.md` and the Phase 4 plans —
  the SPA shell, thumbnail rail (VIEW-04), undo store (EDIT-05), and PRIV-01's disclosure mechanism
- `harness/masked_diff.py`, `harness/run_corpus_harness.py`, `tools/probe_corpus.py` — the
  three-engine differential harness and `qpdf --check` / `pdfcpu validate` wiring these outputs must
  pass
- `corpus/manifest.json` — real fixtures, including documents with `/Contents` arrays, inherited
  resources, and subset fonts of the same family

</canonical_refs>

<specifics>
## Specific Ideas

- **The licence constraint is live here.** `REQUIREMENTS.md` Out of Scope bans Ghostscript,
  PyMuPDF, and `mupdf.js` from the runtime (AGPL triggers on SaaS), and ENG-07's CI gate fails the
  build on AGPL anywhere in the resolved lockfile. A client-side page-ops library is a plausible
  accidental route in. The existing `tools/license_gate.py` gate must cover the client's
  `package-lock.json`, not only the Python lockfile — confirm whether it currently does.
- PAGE-06's test needs two documents that embed the *same* `/BaseFont` name with *different*
  subsets. The corpus is subset-font-heavy by construction (ENG-01), so this pair should be
  findable in real documents rather than constructed — same discipline Phase 3 used for its G2b
  fixture.
- PAGE-09's assertion is about **observed requests**, not about intent. It should be enforced by
  intercepting network activity during a page-ops-only session, not by asserting a boolean.
- ROADMAP criterion 3 requires the merged output to render correctly **in all three engines**, so
  page ops inherit the same three-engine bar as the text engine even though they never touch it.

</specifics>

<deferred>
## Deferred Ideas

- Page-size normalization on merge as a **default** — permanently out of scope; the explicit
  opt-in choice is in scope.
- Splitting a PDF — that is EXPO-03, Phase 7.
- Extracting pages to images — EXPO-01, Phase 7.

</deferred>

---
*Phase: 06-page-ops-and-merge*
*Context assembled: 2026-08-30 during batch planning of Phases 4–8*

---

## Amendments

### 2026-08-30 — post-research rulings

`06-RESEARCH.md` read `@cantoo/pdf-lib`'s own source rather than trusting its documentation, and
three findings change how this phase must be planned.

#### A-6.1 — HEIC decode moves server-side (maintainer decision)

**Supersedes D-6.1's "entirely in the browser" scope for PAGE-07's HEIC case only.**

Every realistic browser HEIC decoder — `heic-to`, `libheif-js`, and the WASM bundled inside
`heic2any` / `heic-decode` regardless of their own MIT/ISC wrapper licences — compiles LGPL-3.0
`libheif` / `libde265` into the shipped bundle. `CLAUDE.md` permits GPL/LGPL **only as a subprocess
with a file-in/file-out interface**, and a browser-bundled WASM blob shipped to every visitor is
not a subprocess.

**Ruling:** HEIC decode runs server-side as a file-in/file-out subprocess, satisfying the existing
licensing policy unchanged. Three consequences the plans must carry:

1. A HEIC-image-merge session is **not** a zero-server-request session. PRIV-01's per-operation
   disclosure must show that one operation as server-side — which is exactly what PRIV-01 exists
   for, so this is disclosure working, not a workaround.
2. **PAGE-09's assertion must name HEIC decode as its one explicit exclusion.** A blanket "zero
   requests to document routes" claim would now be false for a HEIC session. The test and the
   requirement's wording must agree.
3. PNG, JPEG, and WebP decode stay fully client-side. Only HEIC crosses the boundary.

#### A-6.2 — `tools/license_gate.py` has zero visibility into the client

Measured: the gate scans only the resolved **Python** closure via `importlib.metadata`. There is no
npm-license tooling anywhere in this repo, so nothing in CI would have caught an LGPL WASM blob
entering `client/`. ENG-07's requirement is "AGPL anywhere in the resolved lockfile" — the client
lockfile is part of the resolved runtime and is currently unchecked.

**Ruling (controller decision, follows directly from ENG-07's own wording):** add a client-side
sibling gate covering `client/package-lock.json` as a task in this phase, before any new client
dependency ships. `license-checker` (BSD-3-Clause, npm) is the researcher's suggested tool; the
planner may choose another that clears the same bar.

#### A-6.3 — D-6.3 is "never add the optimization", not "override a default"

`@cantoo/pdf-lib`'s `copyPages()` constructs a fresh `PDFObjectCopier` with a private
`traversedObjects` map per call, so merging two source documents always produces two independent,
fully-duplicated font objects. The corruption mode PITFALLS.md warns about — deduping by
`/BaseFont` and silently serving the wrong glyph subset — **cannot arise from the library's default
behaviour**. It can only arise if this phase's own code adds a size-reduction optimization keyed on
`/BaseFont`.

Plans should therefore assert the *absence* of name-keyed dedup and prove correct rendering of the
duplicated case, rather than plan work to override a dangerous default that does not exist. Real
corpus pairs embedding the same `/BaseFont` with genuinely different subsets were measured and are
named in the research (`govdocs1_000_000010.pdf` / `govdocs1_001_001038.pdf`, both `Arial`).

#### A-6.4 — D-6.4's inherited-`/Resources` bug is real, but needs a constructed fixture

`PDFPageLeaf.normalize()` — the method every resource-adding call routes through, including
`page.drawImage()`, PAGE-08's core primitive — carries three literal
`// TODO: Clone 'Resources'/'Font'/'XObject' if it is inherited` comments and does not clone before
mutating. The bug is confirmed in the library's source.

However, the public corpus (217 files) has **zero** leaf pages missing an own `/Resources` key, so
it cannot be reproduced against a real fixture today. Plans must construct one, following the same
measure-then-construct discipline Phase 2 used for `vector_outlined_text_sample.pdf` and Phase 3
used for its G2b fixture — and record why the corpus lacked it.

#### A-6.5 — D-6.7's outlines and form fields are entirely this phase's own code

`copy()` / `copyPages()` explicitly does not carry over outlines or AcroForm fields (the library's
own docstring says so). There is no library default to correct; nesting outlines and announcing
form-field collisions is new code with its own tests.

#### A-6.6 — PAGE-09 asserts against a configured API base, not a hardcoded route list

*(Controller decision — research Open Question 2.)* Phase 4 has not been built and its hardening
pass may restructure routes entirely. PAGE-09's test should assert "zero requests whose target
matches the SPA's configured API base" as a single pattern, not an enumerated route list. This
keeps the test correct regardless of Phase 4's final route naming, and treats "zero requests to
document routes" as an interface requirement on Phase 4 rather than an assumed shape. Combine with
A-6.1's explicit HEIC exclusion.

#### Version note

`@cantoo/pdf-lib` installed in `client/` is **2.9.1**, one minor ahead of `research/STACK.md`'s
pinned 2.8.1. MIT, unchanged. Plans should pin deliberately rather than inherit whichever version
the scaffold happened to install.
