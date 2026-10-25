# Phase 6: Page Ops and Merge — Research Update

**Researched:** 2026-10-25
**Domain:** browser structural PDF transforms, mixed document history, isolated HEIC conversion
**Confidence:** HIGH on measured library/session seams; MEDIUM on full form/outline interoperability and Linux HEIC execution.

<user_constraints>
## User Constraints (from CONTEXT.md)

The following source sections are copied verbatim. Later amendments supersede earlier conflicting statements. [VERIFIED: 06-CONTEXT.md]

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

## Deferred Ideas

- Page-size normalization on merge as a **default** — permanently out of scope; the explicit
  opt-in choice is in scope.
- Splitting a PDF — that is EXPO-03, Phase 7.
- Extracting pages to images — EXPO-01, Phase 7.

## Amendments`. `@cantoo/pdf-lib` does not dedupe at all,
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

### 2026-10-24 — local execution over the delivered workstation

The user explicitly instructed "ok go to next phase" after the Phase 5 local
delivery report. Phase 6 proceeds independently over the existing Phase 4/5
viewer, text editor and search. G3 Linux/container/CDN release checks and G4's
literal contract-specimen item remain open; none is relabeled passed. Deployment
and installation of container tools remain deferred.

The old research predates the delivered application. Implementation planning must
use `06-RESEARCH-UPDATE.md` and `06-PATTERNS.md` to account for its actual current
session, cache, mutation ownership and undo paths. Opening currently uploads and
thumbnail visibility requests classification; both must become explicit opt-in
text analysis for PAGE-09 to hold. Local page mutations must materialize current
bytes, invalidate obsolete server addresses and retain full prior document/text
state for one-step Undo. The text engine and its rewrite rules remain unchanged.

Use the existing Node built-in test runner and available browser connector. The
older suggestion to install Vitest/Playwright is superseded by delivered test
infrastructure. A client lockfile license gate is still required; it need not add
a new test framework or dependency. HEIC's existing A-6.1 exception remains the
only image server boundary and must agree across requirement, UI and observed
network proof. Current installed library behavior, including actual password
decryption, must be probed rather than inferred from old upstream limitations.
</user_constraints>

## Summary

Use the delivered SPA, installed @cantoo/pdf-lib 2.9.1, pdf.js, existing Node test runner and current mutation owner. The August research's absent-SPA, unconditional encryption limitation, old server route inventory and Vitest/Playwright installation suggestions are superseded. The current open path uploads immediately, and visible thumbnails request classification; moving those behind explicit Analyze text is necessary for PAGE-09. [VERIFIED: client/src/App.jsx:97–128; client/src/Viewer.jsx; client/package.json; installed PDFDocument.ts]

Recommendation: implement local-first document ownership and one mixed whole-document history before wiring page commands. Load the current materialized bytes for each operation; prepare saved bytes and a fresh viewer before committing. Keep the immutable opened original separate from the immutable current text replay baseline. The current recipe-only history and session.original recovery semantics cannot represent page mutations by themselves. [VERIFIED: client/src/session.mjs; App.jsx:75–96,205–228; 06-PATTERNS.md]

A targeted research probe found a stronger visible-letter Arial pair, made controlled copies with identical full PDF font names and compared their merged pages with the unmodified real sources in PDFium, Poppler and MuPDF: all six same-engine comparisons were pixel-identical. Deliberate name-based font replacement visibly changed the first page in all three engines. Fresh password probes also confirmed ASCII and Unicode password decryption, wrong-password rejection and unencrypted rotated output readable by independent tools. These prove narrow primitives, not completed PAGE requirements or G5. [VERIFIED: /tmp/phase6-visible-font.py; /tmp/phase6-research-probe.mjs; /tmp/phase6-research-render.py; probe output 2026-10-25]

**Primary recommendation:** establish local-first open/rebase/history, then build structural transforms with shared object copying, safe metadata preflight and bounded image conversion. [VERIFIED: current integration seams and measured probes above]

## Project Constraints (from AGENTS.md)

- The supplied AGENTS instructions require the installed graphify instructions before other actions when the user enters /graphify. This phase research was dispatched without that trigger; no root AGENTS.md or project skill indexes were found in this checkout. [VERIFIED: supplied user instructions; file discovery; 06-PATTERNS.md]
- CLAUDE.md requires GSD workflow entry before repository edits; this artifact is part of the active Phase 6 GSD planning workflow. Preserve browser page operations/server text rewrite separation, content-stream fidelity, client-authoritative recoverable state, no content/password logging and existing anonymous/no-account behavior. [VERIFIED: CLAUDE.md]
- No AGPL runtime closure; GPL/LGPL only behind file-in/file-out subprocesses. Preserve the existing PDF sandbox rather than broadening it for HEIC. No deployment, container-tool installation, new JS framework or runtime dependency is required for this phase research. [VERIFIED: CLAUDE.md; 06-CONTEXT.md amendments; parent execution scope]
- G3 Linux/container/CDN and G4 literal-contract-specimen debt remain open. Do not rename local development checks as release proof. [VERIFIED: 06-CONTEXT.md 2026-10-24 amendment]

<phase_requirements>
## Phase Requirements

| ID | Required behavior | Research support |
|---|---|---|
| PAGE-01 | Insert blank anywhere; show inherited size/rotation | Explicit adjacent box/rotation copy; library defaults to A4 if dimensions omitted. [VERIFIED: REQUIREMENTS.md; PDFDocument.ts:1017] |
| PAGE-02 | Reorder pages | Move existing page objects; retain physical-page identity, metadata targets and one undo snapshot. [VERIFIED: REQUIREMENTS.md; PDFDocument.ts removePage/insertPage; 06-UI-SPEC.md] |
| PAGE-03 | Rotate pages | Absolute normalized 90-degree rotation; reanalyze stale text geometry only on opt-in. [VERIFIED: REQUIREMENTS.md; PDFPage.ts getRotation/setRotation; 06-PATTERNS.md] |
| PAGE-04 | Delete pages | Prepare transaction; last-page protection and exact undo; repair/refuse dangling destinations/widgets. [VERIFIED: REQUIREMENTS.md; 06-UI-SPEC.md; PDFPage/PDFForm source] |
| PAGE-05 | Merge PDF with nested outlines, announced fields, original per-page size | Shared copier, bounded graph walk, name-prefix and resource-aware forms policy. [VERIFIED: REQUIREMENTS.md; PDFObjectCopier.ts; PDFAcroForm.ts] |
| PAGE-06 | Different font subsets survive merge | Pass through independent objects; real Arial hash/render probe; no name-based dedup. [VERIFIED: REQUIREMENTS.md; A-6.3; targeted probe] |
| PAGE-07 | PNG/JPEG/WebP/HEIC new-page merge, transparency composite | Native browser raster path; white canvas; HEIC-only explicit native subprocess boundary. [VERIFIED: REQUIREMENTS.md; 06-UI-SPEC.md; A-6.1; MDN canvas/bitmap docs] |
| PAGE-08 | Existing-page image placement with visible aspect lock | Inverse viewport affine basis, resource copy-on-write, numeric visible-page controls and draft preview. [VERIFIED: REQUIREMENTS.md; PDFPageLeaf.ts; pdf.js PageViewport; 06-UI-SPEC.md] |
| PAGE-09 | Local document journey; HEIC sole disclosed exception | API origin/path-prefix observer begins before open; gate upload/classify behind Analyze text. [VERIFIED: amended REQUIREMENTS.md; A-6.6; App.jsx] |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary tier | Secondary tier | Rationale |
|---|---|---|---|
| Open/view/page count/password/signature preflight | Browser | — | Local bytes and existing pdf.js viewer; no analysis request needed. [VERIFIED: prepareViewer; PDFDocument.load source] |
| Page transforms, merge, images, download | Browser | — | Locked ownership; existing PDF library and canvas APIs. [VERIFIED: context; installed API] |
| Snapshot/undo/rebase/cache recovery | Browser | API cache when explicitly analyzed | Browser owns exact source bytes; server addresses are disposable. [VERIFIED: session.mjs; CLAUDE.md] |
| Text classification/rewrite | Existing API/PDF worker | Browser current-baseline upload | Existing text engine unchanged; Analyze text is explicit. [VERIFIED: App.jsx; server/app.py] |
| HEIC raster conversion only | Separate API/native process | Browser raster placement | Only selected image crosses boundary; never PDF, password or job state. [VERIFIED: A-6.1; UI-SPEC] |
| License closure verification | Build/CI | Local Node script | Python gate has no npm visibility. [VERIFIED: tools/license_gate.py; workflows] |
| Production native-code isolation | OS/container/launcher | API admission/slots | Existing PDF filter prohibits exec/fork; cannot launch decoder inside it. [VERIFIED: server/linux_sandbox.py] |

## Standard Stack

### Core

Reuse installed/locked versions deliberately; this research does not recommend a package installation or upgrade. Values below are installed versions, not claims about the latest registry release. [VERIFIED: client/package-lock.json; importlib.metadata probe]

| Component | Version | Purpose / disposition |
|---|---|---|
| @cantoo/pdf-lib | 2.9.1 | Browser PDF graph transforms; pin deliberately instead of inheriting declared ^2.8.1. [VERIFIED: installed package.json, lockfile; official cantoo repository] |
| pdfjs-dist | 6.2.108 | Local viewer, inverse geometry and prepared publication. [VERIFIED: lockfile; installed source] |
| React / Vite | 18.3.1 / 5.4.21 | Existing workstation/build; no upgrade needed. [VERIFIED: lockfile] |
| Node built-in test runner | Node 22.23.2 available | Existing .test.mjs convention; extend script to new directory. [VERIFIED: node --version; client/package.json] |
| pikepdf / pypdfium2 / Pillow | 10.11.0 / 5.12.1 / 12.3.0 | Existing independent structural/readback/raster checks. [VERIFIED: pyproject.toml; installed metadata] |
| pytest | 9.1.1 | Existing server/renderer test suite. [VERIFIED: installed metadata; pytest config] |

### Supporting native codec

Use allowlisted configured executables, never arbitrary user command strings. Current upstream libheif documents heif-dec; Debian trixie's libheif-examples manual also exposes legacy heif-convert naming. Neither binary is available on this workstation. The existing macOS /usr/bin/sips 316 is a local subprocess backend, subject to actual codec availability. [CITED: github.com/strukturag/libheif#usage; manpages.debian.org/trixie/libheif-examples/heif-convert.1.en.html] [VERIFIED: command -v probes; sips --version]

Recommendation: provide an explicit backend selector/capability check and safe HEIC_UNAVAILABLE result. Add a pinned distro codec recipe and Linux test configuration only; do not install container/native packages locally under the current scope. libheif decode capability depends on its available codec plugins, so executable existence alone is insufficient; use a real small decode smoke fixture. [CITED: github.com/strukturag/libheif#codec-plugins] [VERIFIED: local execution scope]

## Package Legitimacy Audit

No new external npm/Python package is recommended or installed. Reuse the current resolved closure; implement the license gate with Node core filesystem/JSON APIs. Therefore the new-package slopcheck/registry/postinstall install gate is not triggered by this update. Native OS codec installation is deferred; its future version/package/source must be checked when its configuration is finalized. No new package is labeled VERIFIED: npm registry here. [VERIFIED: proposed scope; current package manifests]

| Change | Registry/slopcheck disposition |
|---|---|
| Existing @cantoo/pdf-lib/pdf.js/React/Vite | Reused installed closure, authoritative installed source inspected; no new package assertion. [VERIFIED: manifests and source] |
| license-checker, Vitest, Playwright | Superseded August suggestions; no installation needed. [VERIFIED: 2026-10-24 context amendment; Node runner] |
| Browser HEIC WASM | Do not add; settled subprocess-only constraint. [VERIFIED: A-6.1] |

## Architecture Patterns

### System Architecture Diagram

~~~mermaid
flowchart TD
  Open[Open local PDF] --> View[Prepare local viewer and safety metadata]
  View --> Choice{Requested operation}
  Choice -->|Page edit / PDF merge / PNG JPEG WebP| Transform[Local transform of current bytes]
  Choice -->|Analyze text explicitly| Upload[Upload current immutable text baseline]
  Upload --> Text[Existing text worker / recipe replay]
  Text --> Prepared[Prepare output and new viewer]
  Transform --> Prepared
  HEIC[Select HEIC] --> Consent{Convert HEIC explicitly}
  Consent --> Native[Bounded native conversion: image file in/out]
  Native --> Transform
  Prepared --> Fresh{Session / generation / owner still current?}
  Fresh -->|Yes| Commit[Snapshot previous state; publish bytes and viewer]
  Fresh -->|No| Dispose[Dispose prepared resources]
  Commit --> Download[Local Blob download]
  Commit --> Undo[Restore exact prior bytes and text state]
~~~

The diagram expresses recommended orchestration of verified current boundaries; it does not claim these Phase 6 paths already exist. [VERIFIED: App.jsx prepared publication; replaceAll.mjs transaction; context]

### Recommended Project Structure / Component Responsibilities

Follow the detailed 06-PATTERNS.md mapping: pageOps services and .test.mjs files under client/src/pageOps, controlled PageOpsPanel.jsx, App-owned orchestration, existing Viewer/session integration, isolated server image-conversion service and Node license-gate sibling. No .ts migration or independent global state system is required. [VERIFIED: 06-PATTERNS.md]

| Component | Required responsibility |
|---|---|
| document state/history | Opened original, current materialized bytes, current replay baseline, recipe/style, page identity/selection, signature/encryption/disclosure state and snapshot labels. [VERIFIED: current missing seams; UI-SPEC] |
| local operation transaction | Capture owner/generation/physical target, transform, validate, prepare, freshness-check, one synchronous publication. [VERIFIED: replaceAll.mjs] |
| merge service | Preflight full form/outline behavior, one source→destination reference map, notices for collision/no-collision/no-fields/no-bookmarks. [VERIFIED: source behavior; UI-SPEC] |
| image service | Byte/type validation, decode/pixel limits, orientation, opaque white raster, visible-page affine placement and cleanup. [VERIFIED: canvas/bitmap docs; UI-SPEC] |
| HEIC boundary | Admission, worker slot ownership, bounded scratch/input/output/deadline and native decoder capability. [VERIFIED: server/app.py; isolation.py; context] |

### Pattern 1: distinct byte identities and one mixed history

Store immutable openedOriginalBytes for untouched-original download; currentBytes for visible/downloaded result; textSourceBytes for the baseline against which the current recipe and server run IDs were created. They can share immutable buffers while equal, but must never share a mutable ownership contract. pdf.js may transfer its input typed array to a worker; keep the existing data: bytes.slice() boundary. [VERIFIED: App.jsx prepareViewer; session.mjs withSourceRetry; Mozilla api.js DocumentInitParameters]

A successful page operation transforms currentBytes, publishes its materialized output and makes that output the next textSourceBytes with an empty recipe, no jobId, no run index/selection/find review. Reanalysis is explicit. Cache recovery reuploads that baseline, not the initially opened original. Undo restores exact prior bytes plus baseline/recipe/styles/signature flags/selection; reconstruct fresh controller/queue instances rather than restoring aborted objects. Update text commits to push the same authoritative history used by page commits. [VERIFIED: UI-SPEC; session.mjs; 06-PATTERNS.md]

Do not silently evict retained history to fit a mutation. Preflight limits or disclose an actual retention boundary before committing; failed/no-op/draft operations produce no entry. Closing releases all retained buffers, controllers, passwords, image bitmaps and object URLs. [VERIFIED: UI-SPEC; current clear/disposal patterns]

### Pattern 2: true local open and local safety metadata

Remove eager upload from openFile; separate local viewer metadata from analysis metadata so setting local page count cannot trigger the existing if(meta) classification effect. Gate page runs, thumbnail selection/visibility, find indexing and inspector edit mode behind a completed explicit Analyze text transition. Opening a panel is not consent to analyze. [VERIFIED: App.jsx:97–128,242; Viewer.jsx:49; UI-SPEC]

Mirror existing server signature detection locally: AcroForm SigFlags, bounded/cycle-safe field-tree traversal, inherited FT /Sig plus nonempty V. Keep mutations disabled until detection succeeds; malformed/uninspectable trees require a named refusal rather than an unsigned guess. Inspect imported PDFs independently and require their own acknowledgement. This is a mutation warning, not signature cryptographic verification. [VERIFIED: server/worker.py:_signed; UI-SPEC]

Pass password explicitly to PDFDocument.load, including the empty string when appropriate. Do not use ignoreEncryption as the mutation/decryption mechanism. Preserve password bytes only in current in-memory session/snapshots; no HEIC request includes them. Local saved copies were measured unencrypted, so display the unlocked-copy notice before first local mutation and retain exact encrypted original bytes for original download/undo. [VERIFIED: installed load implementation; fresh probe; official cantoo Encryption Handling; UI-SPEC]

### Pattern 3: mutate the existing destination; import via one shared copier

Load current destination bytes rather than rebuilding every document with copy(): copy() explicitly omits forms/outlines. copyPages() gives one private map per call and cannot share it with separately copied catalog metadata. For forms and destination-bearing metadata, use one explicit PDFObjectCopier for the source and destination; copy source page references through it and use the resulting refs as the actual inserted pages. Copy form field roots, widgets and destinations using that same copier. [VERIFIED: PDFDocument.ts:1058–1104; PDFObjectCopier.ts; shared-copier probe]

Fresh minimal proof: imported text field retained value "Visible value", widget /P was 5 0 R and exactly equaled the actual imported page ref. This validates shared mapping for one simple field; it does not certify radio groups, appearances, resource collisions, scripts, XFA or all outline types. [VERIFIED: /tmp/phase6-research-probe.mjs; independent pikepdf opened forms.pdf with two pages]

Form implementation contract:

1. Preflight all field roots and descendants, including inherited types; preserve hierarchy, field values/flags/options, appearance streams and widget page ownership. Audit Tx, Btn checkbox/radio/pushbutton, Ch list/combo and Sig individually. Never treat unknown types as "no forms". [VERIFIED: PDFAcroForm.ts getAllFields; PDFForm.ts field factories, getFields, flatten; UI-SPEC safe-refusal]
2. Prefix imported field hierarchy with a deterministic unique import namespace, count fully-qualified collisions before renaming, preserve existing destination names and report both collision/no-collision outcomes. Do not rename only leaf T entries without respecting Parent/Kids paths. [VERIFIED: PDFAcroField.ts getFullyQualifiedName; UI-SPEC]
3. Merge AcroForm DR resource categories and inherited/explicit DA resources coherently. Two fields with distinct names can still refer to conflicting /Helv resources. Reuse only proven-equivalent resources or rename imported resource names and correctly rewrite affected DA operands. Preserve/remap calculation-order CO references if supported. [VERIFIED: PDFForm.ts appearance/resource operations; PDFAcroForm.ts dictionary model; object-copy semantics]
4. Safely refuse unsupported XFA, malformed/cyclic trees, scripts/actions requiring unsafe name rewriting, missing/unresolvable appearances or unresolved resource collisions before any commit. Preserve appearances and use save({updateFieldAppearances:false}) to avoid incidental re-generation; do not flatten/drop fields silently. A generic safe refusal is an explicit supported product outcome, not permission to omit testing other field kinds. [VERIFIED: PDFForm.ts hasXFA/deleteXFA/flatten/updateFieldAppearances; SaveOptions; UI-SPEC]

Outline implementation contract: bounded cycle-safe traversal; preserve title strings, color/style and child hierarchy; build a new parent named after the imported filename; resolve direct destinations, named destinations from Dests/name trees and GoTo actions to actual copied page refs. Rebuild Parent/Prev/Next/First/Last/Count consistently; preserve existing destination outlines. Define safe handling/refusal for unresolved destination/actions instead of emitting a broken bookmark. Never send imported actions through DOM execution. [VERIFIED: installed PDFDict/PDFArray/copier primitives; existing omission in PDFDocument.copy; A-6.5] Implementation correctness beyond primitive mapping remains MEDIUM until permanent outline fixtures pass.

Reorder existing page objects rather than rebuilding by ordinal indices; outline references then retain physical-page identity. Delete must prune/refuse destinations to removed pages and remove associated widgets/empty fields coherently; page-tree deletion alone is not evidence of catalog correctness. Explicit page-size normalization additionally transforms content, boxes, annotation rectangles and destinations; if unsupported form/destination geometry cannot be transformed safely, refuse opt-in normalization. [VERIFIED: library removePage/insertPage only manipulate page tree; PDFForm.removeField; UI-SPEC]

### Pattern 4: copy-on-write resources before any resource-adding call

PDFPageLeaf.normalize still has explicit TODOs to clone Resources/Font/XObject/ExtGState and instead mutates resolved dictionaries. Earlier same-run probe confirmed a sibling inheriting the shared Resources gains the inserted image XObject. Clone the destination page's effective Resources and its mutable Font, XObject and ExtGState dictionaries, even when Resources is an own indirect object shared with siblings. Attach the clones to the target before drawImage/normalization. Keep font/image streams themselves shared unless mutated. [VERIFIED: installed PDFPageLeaf.ts:204–246; prior interrupted research probe reported by parent]

Construct a two-sibling inherited-resource fixture because the August corpus scan found no leaf without own Resources; record that historical scan rather than claiming a new full-corpus scan. Add an own-but-shared Resources variant. Require unchanged sibling dictionaries and full unmasked same-engine render equality after placement. [VERIFIED: A-6.4; 06-RESEARCH.md corpus measurement; installed bug]

### Pattern 5: images use visible-page coordinates and an opaque raster

Use the scale-1 pdf.js viewport for the actual rotated visible crop rectangle, including nonzero origins and userUnit. Numeric Left/Top/Width/Height are viewport-point coordinates, not raw bottom-left PDF units. Convert three corners to PDF space and construct an affine image basis; width/height swap alone fails at 90/270 degrees. Validate finite positive dimensions and complete containment before embedding. [VERIFIED: installed pdf.js PageViewport constructor/convertToPdfPoint; UI-SPEC; PDFPage.drawImage matrix support]

Decode PNG/JPEG/WebP from local blobs, normalize orientation once, composite onto a white canvas and encode PNG for embedPng. Explicit bitmap imageOrientation behavior and a real EXIF-oriented JPEG test prevent double rotation. Set bitmap.close(), revoke URLs, zero/release canvas and reject null toBlob output. The source image must not become a remote URL fetch. Pixel/dimension limits must be enforced before canvas allocation where metadata is available and again after decode; byte bounds alone are not decompression bounds. [CITED: developer.mozilla.org/en-US/docs/Web/API/Window/createImageBitmap; developer.mozilla.org/en-US/docs/Web/API/HTMLCanvasElement/toBlob] [VERIFIED: UI-SPEC]

New-page images inherit adjacent MediaBox/rotation and declared visible crop behavior, fit within the visible page with contain scaling and no distortion, and preserve the white composite preview. Blank-page insertion explicitly copies box origin/dimensions and rotation rather than calling the library's A4 default. [VERIFIED: UI-SPEC; PDFDocument.insertPage; PDFPage box APIs]

### Pattern 6: separate bounded HEIC process

Use a dedicated conversion route/service, never an action inside server.worker. Existing Linux PDF filter explicitly denies execve/execveat/fork/vfork/clone/clone3, so a decoder child cannot launch after that filter. Do not broaden the PDF filter. A separate native launcher needs its own tested OS isolation; macOS development is not Linux production egress proof. [VERIFIED: server/linux_sandbox.py; isolation.py]

Route/service acceptance contract:

- Admit the new path through ingress limits; current middleware recognizes only /upload and /jobs/. Acquire shared worker capacity and keep it until the actual converter finishes, even if HTTP disconnects. Use the current shielded task/done-callback ownership model. [VERIFIED: server/app.py:137–204]
- Bounded raw HEIC body; validate content type and bounded ISO-BMFF ftyp/compatible-brand structure instead of filename alone. Fixed internal filenames in per-operation private scratch; no document job ID, PDF cache, original filename or caller-provided output path. [VERIFIED: existing _body/scratch pattern; A-6.1] Recommendation derived from that boundary.
- Native file-in/file-out only; shell=False, fixed executable/argv, minimal environment, process group, CPU/address/file/output/descriptor/deadline limits, capped diagnostics, kill descendants and cleanup in finally. Do not leak raw stderr; fixed error codes only. Guard against decoder-generated multiple files/symlinks; accept one validated expected PNG result or refuse ambiguity. [VERIFIED: isolation.py patterns; libheif example decoder handles multiple images; server/errors.py]
- Retain native security limits; never --disable-limits or LIBHEIF_SECURITY_LIMITS=off. Validate output magic, dimensions/pixels, total bytes and complete image decode before returning. Define primary-image behavior explicitly; do not silently merge all HEIF frames. [CITED: github.com/strukturag/libheif#security-limits] [VERIFIED: UI-SPEC single-image flow]
- Use fixed codes such as HEIC_UNAVAILABLE, INVALID_HEIC, IMAGE_LIMIT_EXCEEDED, IMAGE_CONVERSION_FAILED and IMAGE_CONVERSION_TIMEOUT; extend allowlists intentionally and keep security/no-store headers on every failure. Names are proposed implementation codes, not existing endpoints. [VERIFIED: server/errors.py; app.py response contract]
- Linux recipe must provide codec and a native-code egress/filesystem containment boundary independent of the PDF filter. Exact launcher/runtime proof remains an execution item. Fail closed/unavailable when required production isolation is absent. Do not certify it from macOS or mocked subprocess tests. [VERIFIED: existing Linux/macOS boundary; local execution restriction]

## Don't Hand-Roll

| Problem | Do not build | Use instead |
|---|---|---|
| PDF encryption | ignoreEncryption "bypass", custom cryptography | Actual password loader; named refusal for unsupported encryption. [VERIFIED: cantoo source/probe] |
| Font subset reconciliation | BaseFont-keyed sharing or font program edits | Independent copied objects; hash-only future dedup, none required now. [VERIFIED: A-6.3; copier] |
| Text editing | Image/white-box replacement | Existing server content-stream engine unchanged. [VERIFIED: CLAUDE.md] |
| Browser HEIC decoding | Shipped LGPL WASM | Isolated native file interface. [VERIFIED: A-6.1] |
| Request/session framework | Second global store/lock/test framework | Existing owner/generation helpers, controlled panels and node:test. [VERIFIED: current source; patterns] |
| Coordinate rotation | Manual per-angle offset guessing | pdf.js inverse viewport and affine basis. [VERIFIED: installed geometry] |

## Runtime State Inventory

This is a session-state refactor over a delivered app, not a project rename. [VERIFIED: current scope]

| Category | Items found | Action required |
|---|---|---|
| Stored data | Browser in-memory bytes, recipe/history and server content-addressed source cache. No persistent data migration is requested. [VERIFIED: App.jsx; server/cache.py; context] | Introduce distinct byte identities; invalidate/reupload ephemeral cache addresses. |
| Live service config | VITE_API_URL may be empty; static renderer resources under assets/pdfjs. External deployed configuration was not audited/changed. [VERIFIED: App.jsx] | Parameterize observer; defer deployment audit. |
| OS-registered state | No phase OS registration identified by scoped tracked-source search; native codec availability is separate. This is not an exhaustive host inventory. [VERIFIED: phase source/config discovery] | No registration migration planned. |
| Secrets/env vars | In-memory PDF passwords; VITE_API_URL and PDF_TOOL_SCRATCH_ROOT runtime inputs. Secret values were not read. [VERIFIED: source] | Clear passwords on close; HEIC gets neither PDF/password; retain scratch policy. |
| Build artifacts | client/dist may need rebuilding after source changes; installed lockfile resolves 2.9.1 although range says ^2.8.1. [VERIFIED: app static mount; package files] | Rebuild locally, deliberately align pin/lock; no deployment. |

## Common Pitfalls

| Pitfall | Warning sign | Required prevention |
|---|---|---|
| PAGE-09 looks local but uploads/classifies | Network during open or rail scroll | Gate every current request source; observe real browser. [VERIFIED: App/Viewer paths] |
| History restores the opened original instead of last visible state | Text → page → Undo loses text or styles | One mixed snapshot stack and correct baseline recovery. [VERIFIED: current recipe history limits] |
| Form looks right but fields are detached | Widget /P points at a page absent from page tree | Shared copier/ref identity assertions and independent readback. [VERIFIED: measured shared-copier probe] |
| Imported fields collide through resources | Distinct field names but /DA fonts resolve incorrectly | DR/DA collision preflight and proven remap or safe refusal. [VERIFIED: form/resource source] |
| Sibling changes after image placement | Shared XObject dictionary gains entry | Resource copy-on-write before normalize. [VERIFIED: library TODO/probe] |
| "Three engines" proof never hits Arial page | Merge arbitrary first pages | Use the stronger visible-letter pair: govdocs1_003_003063 index 0 and govdocs1_001_001038 index 2. [VERIFIED: targeted pikepdf scan and renderer probe] |
| Same-family case overclaimed as exact BaseFont collision | Original full names differ by subset prefix | Use controlled exact-name copies and the measured corrupting negative control described below. [VERIFIED: /tmp/phase6-visible-font.py] |
| HEIC route bypasses capacity or blocks native exec | New route outside admission; decoder launched in PDF child | Separate boundary plus shared admission/slots. [VERIFIED: app.py; Linux filter] |
| License gate sees direct deps only | Python gate passes while npm transitive license unknown | Traverse resolved client production closure; fail forbidden/unknown by explicit policy. [VERIFIED: gate source; A-6.2] |

## Code Examples

### Shared copier with real page-reference ownership

This exact primitive passed the minimal text-field/widget probe. Use the same copier for subsequent imported form and destination graphs; never replace an existing destination AcroForm wholesale as the isolated probe did. [VERIFIED: installed exports; /tmp/phase6-research-probe.mjs]

~~~js
import {
  PDFObjectCopier, PDFPage, PDFPageLeaf,
} from '@cantoo/pdf-lib';

const copier = PDFObjectCopier.for(source.context, destination.context);
const imported = source.getPages().map(page => {
  const ref = copier.copy(page.ref);
  const node = destination.context.lookup(ref, PDFPageLeaf);
  return PDFPage.of(node, ref, destination);
});
for (const page of imported) destination.insertPage(insertAt++, page);
// Fields, widgets and resolved destinations MUST use this same copier.
~~~

### Copy-on-write page resource dictionaries

The methods below are verified in installed PDFDict/PDFPageLeaf; regression rendering remains required. Run before the first normalization/resource addition on a freshly loaded target. [VERIFIED: installed source]

~~~js
const effective = page.node.getInheritableAttribute(PDFName.Resources);
const own = (doc.context.lookupMaybe(effective, PDFDict)
  ?? doc.context.obj({})).clone(doc.context);
for (const name of ['Font', 'XObject', 'ExtGState']) {
  const key = PDFName.of(name);
  const dict = own.lookupMaybe(key, PDFDict);
  if (dict) own.set(key, dict.clone(doc.context));
}
page.node.set(PDFName.Resources, own);
~~~

### Visible-page image basis

Derived from verified inverse viewport and drawImage matrix composition; this is implementation guidance, not a completed rotated-image render test. [VERIFIED: pdf.js PageViewport; cantoo api/operations.ts drawImage]

~~~js
// viewport = pageProxy.getViewport({ scale: 1 }); includes UserUnit/rotation.
const bottomLeft = viewport.convertToPdfPoint(left, top + height);
const bottomRight = viewport.convertToPdfPoint(left + width, top + height);
const topLeft = viewport.convertToPdfPoint(left, top);
const matrix = [
  bottomRight[0] - bottomLeft[0], bottomRight[1] - bottomLeft[1],
  topLeft[0] - bottomLeft[0], topLeft[1] - bottomLeft[1],
  bottomLeft[0], bottomLeft[1],
];
page.drawImage(image, { x: 0, y: 0, width: 1, height: 1, matrix });
~~~

## Measured Research Evidence

Fresh probes wrote only temporary files under /tmp/phase6-research-probe and scripts under /tmp; no production source was changed. Probe code is research scratch, not a permanent acceptance test. [VERIFIED: tool history]

| Probe | Result / limit |
|---|---|
| ASCII and Unicode password | AES-256 default library encryption, wrong passwords rejected; load({password}) then 90° rotation/save succeeded. pikepdf opened both outputs with encrypted=false; PDFium text read "Encrypted source". [VERIFIED: fresh probes] |
| Shared copier text field | Value retained; copied widget /P and inserted page both 5 0 R, strict reference identity true. Only simple Tx tested here. [VERIFIED: fresh probe] |
| Real Arial subset merge | govdocs1_000_000010.pdf page index 1 + govdocs1_001_001038.pdf page index 2; all six corresponding-source comparisons pixel-identical at harness DPI 150. [VERIFIED: render_all probe] |
| Font content | /EEPLGH+Arial hash 8f5177dd0a3a8c24d6bc565eb1c79df24d46a1b55fb736ece3bdd5e5ade76325; /ACKMHB+Arial hash 674ab0feea74f3f5ae754f3223bde2bfa75473b56cb455172bee5318907d584e both retained. [VERIFIED: pikepdf output font streams] |
| Strength of font case | Full BaseFont names have different prefixes, same Arial family; historical first subset has space only. Add a controlled same-exact-name nonspace variant for a stronger negative-control test; do not rename the measured case as literal full-name collision. [VERIFIED: original research widths; fresh names] |
| Inherited resources | Prior interrupted research confirmed drawImage mutates sibling-shared Resources; source still contains TODOs. Not re-run during this continuation. [VERIFIED: parent handoff; installed source] |
| Local native HEIC | Prior interrupted probe successfully roundtripped native sips HEIC with OS codec access under approved escalation; default sandbox encoder failed. Not a portable decoder/server isolation proof. [VERIFIED: parent handoff] |

### Stronger PAGE-06 fixture — use this pair for permanent acceptance

The old space-only pair above is retained as historical primitive evidence, not the visible-glyph acceptance fixture. A bounded search stopped after 45 real PDFs and 3,131 page resource dictionaries; content streams were parsed only for candidate Arial resources, with no full-corpus glyph-index walk. It found the following stronger pair. [VERIFIED: /tmp/phase6-find-font.py]

| Source / zero-based page | Resource / original BaseFont | Actual letter codes executed | Font program SHA-256 |
|---|---|---|---|
| corpus/public/govdocs1_003_003063.pdf / 0 | /TT2 /CCEBGE+Arial | ACDFMOPSTWabcdefghijklmnopqrstuvwxyz | 8c54d9074cb803ce67f4bc1db58cfcd8defca27d27407a39a5c0f6f48dfe5a5b |
| corpus/public/govdocs1_001_001038.pdf / 2 | /TT0 /ACKMHB+Arial | ACDEFILMNOPQRSTUVWYacdefghilmnoprstuvy | 674ab0feea74f3f5ae754f3223bde2bfa75473b56cb455172bee5318907d584e |
[VERIFIED: candidate font dictionaries; content-stream Tf plus Tj/TJ operands; /tmp/phase6-visible-font.py]

Controlled collision construction copies just each selected real page with pikepdf, changes the selected font dictionary BaseFont and its descriptor FontName to the exact same /ABCDEF+Arial, and leaves both real embedded font programs, widths, encoding and content bytes intact. Merge the two controlled PDFs with the installed cantoo library. Each merged page is pixel-identical to its unmodified real original in PDFium, Poppler and MuPDF at harness DPI 150: six exact comparisons. This proves the name change itself and normal independent copying preserve visible text. [VERIFIED: /tmp/phase6-visible-font.py; literal-0.pdf, literal-1.pdf and literal-merged.pdf under /tmp/phase6-research-probe]

Negative control: replace merged page 0 /TT2 with merged page 1 /TT0, deliberately simulating same-name font-object deduplication. Page 0 then differs from its real source in every renderer; page 1 remains exact in all three. The reverse replacement direction happened to render identically, so preserve this tested direction in the regression rather than assuming either substitution corrupts visible glyphs. This supplies a nonvacuous negative control without claiming an unmeasured CID-to-glyph mapping. [VERIFIED: bad-name-dedup.pdf and renderer output from /tmp/phase6-visible-font.py]

The CCEBGE font's cmap table triggers a fontTools format-4 length assertion, while all three renderers successfully handle the real page. Do not normalize or reconstruct that embedded program during page copying; preserve its bytes. The measured hashes and render comparisons, rather than inferred fontTools glyph IDs, support this fixture. [VERIFIED: same probe exception/readback]

### Current application baseline evidence

The parent recorded the real browser local-open baseline at /private/tmp/pdf-tool-phase6-network-red-20261025.json: after static boot, opening tests/fixtures/render_mode_7.pdf issued POST /upload and GET /jobs/{id}/pages/0/runs. Observed matched count is 2 and zeroApiPass is false. This is a useful red baseline for the local-first change, not a Phase 6 pass. [VERIFIED: artifact read 2026-10-25]

Parent-reported current regression baseline is 527 Python tests plus 41 Node tests green; this continuation did not rerun or relabel that baseline as Phase 6 validation. [VERIFIED: parent message 2026-10-25]

## State of the Art / Superseded Research

| August statement | Current finding | Planning impact |
|---|---|---|
| SPA/tests not built | Delivered App/Viewer/find/session and Node tests exist | Extend current seams; no framework scaffold. [VERIFIED: current files] |
| Upstream pdf-lib encryption limitations | Cantoo fork supports actual password decryption | Probe supported cases; unlocked-copy disclosure, no blanket refusal. [VERIFIED: current official docs/source and probe] |
| Merge needs a dangerous-default dedup fix | Copier already preserves separate objects | Do not add optimization; prove hashes/rendering. [VERIFIED: copier; A-6.3] |
| Browser-only security surface | HEIC is an explicit API/native boundary | Add ingress/process/isolation/cleanup tests. [VERIFIED: A-6.1] |
| Old ASVS V2 auth / V3 sessions / V4 access labels | ASVS 5 uses different chapter numbering | Use current chapter names, avoid mislabeled controls. [CITED: github.com/OWASP/ASVS/tree/v5.0.0/5.0/en] |

## Environment Availability

| Dependency | Available/version | Fallback / consequence |
|---|---|---|
| Node | Yes / 22.23.2 | Existing runner/build. [VERIFIED: command probe] |
| uv / project Python | Yes / uv 0.10.4; existing .venv | Direct .venv Python probes avoid installation. [VERIFIED: command/import probes] |
| pikepdf/PDFium/Pillow/pytest | Yes / versions in stack table | Existing targeted tests. [VERIFIED: import metadata] |
| qpdf/pdftoppm/mutool | Paths found | Use existing native harness; MuPDF only dev/CI, never served runtime. [VERIFIED: command -v; harness source] |
| heif-dec / heif-convert | Absent | sips local backend or named unavailable; Linux recipe deferred. [VERIFIED: command -v] |
| /usr/bin/sips | Yes / 316 | macOS-local codec probe only; fail safely if native support unavailable. [VERIFIED: version; handed-off probe] |
| Context7 MCP / ctx7 CLI | Not available | Installed authoritative upstream source + official docs used; no auto-download. [VERIFIED: tools inventory; command -v] |
| Linux container/egress environment | Not exercised in this task | Recipe/config only; production validation stays pending. [VERIFIED: execution scope] |

**Missing with fallback:** native HEIC decoder on macOS uses sips when its real smoke decode succeeds; otherwise HEIC refuses with retry/alternative-format guidance. **Missing production proof:** Linux native-code isolation and distro codec execution require the deferred environment; this does not block local PDF/PNG/JPEG/WebP work. [VERIFIED: scope; available tools; UI-SPEC]

## Validation Architecture

Nyquist is enabled in .planning/config.json. Reuse current Node/pytest infrastructure; do not install Vitest/Playwright just because the old research named them. [VERIFIED: config; package.json; context amendment]

### Test Framework

| Property | Value |
|---|---|
| Client | node:test on Node 22; existing script: node --test src/*.test.mjs src/find/*.test.mjs. Add src/pageOps/*.test.mjs. [VERIFIED: package.json] |
| Server/render | pytest 9.1.1, pyproject.toml config. [VERIFIED: config/metadata] |
| Quick | cd client && npm test; targeted .venv/bin/python -m pytest tests/test_page6_merge_render.py -x -q once created. [VERIFIED: current command plus proposed test path] |
| Existing server checks | .venv/bin/python -m pytest tests/test_web_contract.py tests/test_isolation.py tests/test_linux_sandbox.py -q. [VERIFIED: existing tests] |
| Broader phase gate | client test/build + targeted HEIC/merge tests + noncorpus regression suite and actual browser journey; no full-corpus research sweep. [VERIFIED: current suite conventions; scope] |

### Phase Requirements → Test Map

Paths below are proposed permanent tests, currently Wave 0 gaps. [VERIFIED: file discovery]

| Requirements | Test type | Command / evidence |
|---|---|---|
| PAGE-01..04 | Unit/structural/history | node --test src/pageOps/pages.test.mjs src/pageOps/documentHistory.test.mjs; geometry, scanned-page independence, last-page/no-op/stale/save failure. |
| PAGE-05 | Structural/integration/render | node --test src/pageOps/mergePdf.test.mjs; forms Tx/Btn/Ch/Sig and unknown types, fields/widgets/resources, outline destinations, collision/no-collision notices, opt-in normalization. |
| PAGE-06 | Independent renderer | .venv/bin/python -m pytest tests/test_page6_merge_render.py -x -q; selected real pages, font hashes, exact source mapping in all three engines, controlled collision negative. |
| PAGE-07..08 | Unit + browser/render | node --test src/pageOps/images.test.mjs; orientation, white alpha composite, crop origins, 0/90/180/270 rotations, UserUnit, lock/unlock, sibling equality, image bounds. |
| PAGE-07 HEIC | HTTP/process + real codec smoke | .venv/bin/python -m pytest tests/test_image_conversion.py -x -q; malformed/oversized input/output, timeout/disconnect/cleanup, unavailable backend, headers and slot lifetime. |
| PAGE-09 | Real browser network/download | Begin observation before Open PDF after app boot; full local journey below; unit request mocks insufficient. |
| Mixed text/page | Integration + browser | Text→page→text→Undo; reverse order; cache eviction between transitions; original/current download distinction; style/selection/password state. |
| ENG-07 closure | Node gate + negative fixtures | node tools/client_license_gate.mjs; forbidden transitive, unknown license, production-only closure, optional/bundled/nonregistry edge fixtures. |

### PAGE-09 observed-network acceptance

Resolve configured API base against the page URL; match the configured origin and path prefix with a segment boundary. The default empty base resolves to same-origin root, so observer selection must use fetch/xhr request types plus only real served static namespace exemptions (currently /assets/, including /assets/pdfjs/). Do not exempt /jobs or other historical document routes, and do not require a /api route migration. Capture new unknown API paths conservatively. [VERIFIED: App.jsx API; server/app.py static mount; A-6.6; 06-PATTERNS.md]

Observe from before file open through password/local metadata, thumbnail visibility/selection, insert/move/rotate/delete, PDF merge, local images, Undo and download; zero matched API traffic. Separate journey proves explicit Analyze text performs upload/classify only after activation and structural changes require reanalysis. HEIC journey observes its one disclosed image request, with no PDF/password payload, then browser-local placement/download. Use actual browser connector evidence; no checked-in automatic browser runner is currently claimed. [VERIFIED: current request sources; context; UI-SPEC]

### Sampling Rate / Wave 0 Gaps

Run focused Node tests per utility/transaction change, relevant pytest negatives per server boundary change, client regression/build per wave, and actual required browser/three-renderer checks before G5. Keep existing native-input Undo, font/style and source-retry regressions. [VERIFIED: 06-PATTERNS.md existing test analogs]

- Add pageOps test files to npm test.
- Add permanent mixed-history/stale/prepared-publication tests.
- Add the targeted merge-render and constructed resource-sharing fixtures.
- Add HEIC converter boundary tests and Linux configuration-only recipe.
- Add client production-closure license gate, transitive negative fixtures and CI calls after npm ci.
- Record browser/network/accessibility/visual evidence in dated 06-G5-RESULTS.md; do not substitute Node helper assertions.
[VERIFIED: current missing files; UI-SPEC required verification; context]

## Security Domain

Security enforcement is not explicitly disabled, and HEIC adds a native untrusted-image API surface. The old "no new server surface" statement is superseded. [VERIFIED: .planning/config.json; A-6.1]

### Applicable ASVS Categories

Use ASVS 5.0.0 names; no certification claim is made. Its file-handling chapter explicitly covers allowed types, compressed/unpacked size and safe processing. [CITED: asvs.owasp.org; github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x14-V5-File-Handling.md]

| Category | Applies | Required standard control |
|---|---|---|
| V1 Encoding and Sanitization | Yes | React text rendering for names/notices, no HTML/actions execution; fixed error content. [VERIFIED: current React/error patterns] |
| V2 Validation and Business Logic | Yes | Bounds, page indices, no-op/history rules, explicit signature/analysis/HEIC consent. [VERIFIED: UI-SPEC] |
| V3 Web Frontend Security | Yes | Current CSP/static renderer policy and local memory lifecycle. [VERIFIED: app.py CSP; App cleanup] |
| V4 API and Web Service | Yes, HEIC | Shared admission/slots, no-store headers and bounded request deadlines. [VERIFIED: app.py] |
| V5 File Handling | Yes | Byte/magic/dimension/output limits, fixed scratch names and isolated native decoder. [CITED: official ASVS V5] |
| V6 Authentication / V7 Session Management / V8 Authorization | No new account controls | Anonymous app; in-memory document state still needs ownership/freshness correctness. [VERIFIED: CLAUDE.md; current App] |
| Cryptography / Data Protection | Yes, existing encrypted input/privacy | Library decryption, original preservation, memory-only passwords and no content logs. [VERIFIED: current library; project constraints] |

### Known Threat Patterns

| Pattern | STRIDE | Mitigation |
|---|---|---|
| Decompression bomb / oversized object graph | Denial of service | Preflight and decoded-output limits, bounded graph traversal, worker deadlines and resource ceilings. [VERIFIED: current worker patterns; ASVS V5] |
| Crafted HEIC native exploit / path escape | Tampering / information disclosure | Separate sandboxed native process, fixed paths/env, scratch isolation and production egress deny; fail closed absent required boundary. [VERIFIED: project isolation posture; libheif native decoder boundary] |
| Stale response targets a new document | Tampering / information disclosure | Session/generation/owner checks and prepare-before-publish. [VERIFIED: current transaction pattern] |
| Transitive copyleft/unknown license enters client | Supply-chain/policy failure | Complete resolved production closure gate and explicit unknown policy; no wrapper-only license trust. [VERIFIED: A-6.1/A-6.2] |
| Password/content emitted in errors | Information disclosure | Fixed code allowlist, no native stderr/user paths, no PDF/password in HEIC request. [VERIFIED: server/errors.py; UI-SPEC] |

## Assumptions Log

No training-only factual claim is promoted to a locked decision here. Proposed implementation policies and code examples are explicitly recommendations derived from cited source behavior. The following items remain unproven, not assumed passed. [VERIFIED: research scope]

| Item | Status | Required execution evidence |
|---|---|---|
| General form and outline interoperability | MEDIUM | Permanent fixtures for all supported types/resources/destinations plus safe refusals. |
| Inverse image geometry across all crop/rotation/UserUnit cases | MEDIUM | Targeted render/browser tests; formula sourced but not freshly rendered here. |
| Linux native HEIC containment and concrete distro decoder invocation | MEDIUM | Deferred Linux environment/real codec smoke; macOS cannot certify it. |
| Browser-wide orientation/color behavior | MEDIUM | Real oriented/transparency fixtures in target browser; avoid inferred compatibility guarantees. |

## Open Questions (RESOLVED for implementation)

1. **Supported form boundary — RESOLVED:** plan 06-03 preserves the documented standard form/appearance/resource/calculation-order graph through one copier, with explicit namespace handling and tests. Unsupported XFA, scripts or ambiguous structures refuse atomically with a notice; nothing is silently flattened or dropped. Implementation tests remain required. [VERIFIED: 06-03-PLAN.md]
2. **HEIC production isolation — RESOLVED policy, deferred platform verification:** plan 06-02 uses a separate bounded native launcher and explicit decoder capability/configuration; production conversion fails closed when required confinement is unavailable. PDF seccomp stays unchanged. Actual Linux/codec execution proof remains deferred release verification, not an unresolved architecture choice; no container tools are installed here. [VERIFIED: 06-02-PLAN.md; local scope]
3. **Memory retention — RESOLVED:** plan 06-01 sets 50MiB local input/current PDF, 200MiB unique retained buffers, 300MiB transaction-owned buffers and 100 snapshots. Admission refuses without history eviction; larger existing server output remains unchanged. These are application-owned buffer limits, not whole-heap or native-renderer guarantees. [VERIFIED: 06-01-PLAN.md]
4. **Permanent font regression — RESOLVED design:** plan 06-06 ports the stronger visible-letter pair, exact-name controlled variant and tested corrupting page-0 TT2 to page-1 TT0 replacement into permanent all-three-engine tests. Scratch proof establishes fixture suitability, while execution of those tests remains part of G5. The older space-only pair and harmless reverse control are not substituted. [VERIFIED: 06-06-PLAN.md; /tmp/phase6-visible-font.py]

## Sources

### Primary — HIGH confidence

- Installed client/node_modules/@cantoo/pdf-lib/src/api/PDFDocument.ts — password load, copy/copyPages, insert, save.
- Installed core/PDFObjectCopier.ts, core/structures/PDFPageLeaf.ts, api/PDFPage.ts and api/operations.ts — object maps, resource mutation, image matrix.
- Installed api/form/PDFForm.ts and core/acroform/* — field hierarchy, widgets, XFA, appearances and AcroForm dictionaries.
- Installed pdfjs-dist/build/pdf.mjs PageViewport and [Mozilla API source](https://mozilla.github.io/pdf.js/api/draft/api.js.html) — inverse geometry and typed-array transfer.
- [Cantoo official repository](https://github.com/cantoo-scribe/pdf-lib#encryption-handling) — current password/decryption guidance, cross-checked against installed source and probe.
- Current App.jsx, Viewer.jsx, session.mjs, find/replaceAll.mjs; server/app.py, isolation.py, worker.py, linux_sandbox.py, errors.py; test/config/lockfiles — actual delivered integration boundaries.
- [libheif official README](https://github.com/strukturag/libheif) — native decoder, plugins, limits and subprocess rationale; read 2026-10-25.
- [Debian trixie decoder manual](https://manpages.debian.org/trixie/libheif-examples/heif-convert.1.en.html) — legacy packaging/name and decoder invocation; source updated 2026-08-06.
- [ASVS 5.0.0](https://asvs.owasp.org/) and [File Handling chapter](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x14-V5-File-Handling.md) — current chapter taxonomy; published 2025-05-30.
- [Mozilla bitmap docs](https://developer.mozilla.org/en-US/docs/Web/API/Window/createImageBitmap), [canvas encoding docs](https://developer.mozilla.org/en-US/docs/Web/API/HTMLCanvasElement/toBlob) — decode/orientation/encoding APIs.

### Session evidence and inherited research

- /tmp/phase6-research-probe.mjs, /tmp/phase6-research-render.py, /tmp/phase6-find-font.py and /tmp/phase6-visible-font.py — fresh selected-page, encryption, simple form and stronger visible-letter exact-name/negative-control probes; temporary, not checked-in acceptance tests.
- 06-CONTEXT.md, 06-PATTERNS.md, 06-UI-SPEC.md — scope, current seams and visible behavior contracts.
- 06-RESEARCH.md — August corpus measurements only where explicitly retained; no stale SPA/test/security assertions adopted.
- Parent handoff of interrupted same-phase probes — inherited-resource mutation and approved native macOS HEIC roundtrip; explicitly identified where not rerun.
[VERIFIED: sources read or supplied in this session]

## Metadata

**Confidence:** stack/session/copying/encryption/selected-page renderer findings HIGH; generalized form/outline/image interoperability and Linux HEIC containment MEDIUM pending permanent tests. [VERIFIED: evidence distinctions above]

**Research date:** 2026-10-25. **Revalidate:** installed library/API shape on dependency change; native codec/security/version when Linux recipe is executed. No dependency, server or production deployment was performed by this research continuation. [VERIFIED: tool history]


