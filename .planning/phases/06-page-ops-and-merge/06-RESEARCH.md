# Phase 6: Page Ops and Merge - Research

**Researched:** 2026-08-30
**Domain:** Client-side (browser-only) PDF page manipulation with `@cantoo/pdf-lib` — insert, reorder,
rotate, delete, merge PDF, merge/place image (incl. HEIC) — with a hard zero-server-round-trip
requirement for a whole class of session.
**Confidence:** HIGH on `@cantoo/pdf-lib`'s actual behaviour (verified by reading its installed
source, not its docs, at `/Users/prempatel/Pictures/pdf-tool/client/node_modules/@cantoo/pdf-lib`).
HIGH on the PAGE-06 font-dedup corpus claim (measured, real files, byte-level proof below). MEDIUM
on the PAGE-09 network-assertion mechanism (Playwright is the standard tool; the exact route-list
depends on a Phase 4 API surface that does not exist yet). **LOW, and flagged as an open licensing
question**, on PAGE-07's HEIC decode path — every viable browser decoder traces back to LGPL-3.0
C code, which appears to conflict with this project's own stated policy.

## Summary

This phase has no engine dependency and is almost entirely a `@cantoo/pdf-lib` integration
exercise inside the (not-yet-built) Phase 4 SPA shell. The library is already installed in the
salvaged client scaffold at `/Users/prempatel/Pictures/pdf-tool/client/` (`@cantoo/pdf-lib` 2.9.1,
MIT — one minor version ahead of `research/STACK.md`'s pinned 2.8.1) and its source was read
directly rather than trusted from documentation, because the phase's three hardest correctness
questions (D-6.3 font dedup, D-6.4 inherited `/Resources`, D-6.5 blank-page defaults) are all
answerable from the library's own code.

Three findings materially change how this phase should be planned relative to what `ROADMAP.md`
and `06-CONTEXT.md` assume:

1. **`@cantoo/pdf-lib`'s `copyPages()` does not dedupe fonts by `/BaseFont` — it does not dedupe
   anything at all, ever, across two separate `copyPages()` calls.** Each call constructs a fresh
   `PDFObjectCopier` with a private `traversedObjects` map, so merging two source documents always
   produces two independent, fully-duplicated font objects, verbatim. This means the corruption
   failure mode `PITFALLS.md`/D-6.3 warn about (deduping by name silently serving the wrong glyph
   subset) **cannot happen from the library's default behaviour** — it can only happen if this
   phase's own code adds a size-reduction optimization that dedupes by `/BaseFont`. D-6.3 is
   therefore best read as "never add that optimization," not "override a dangerous default."
   Real corpus pairs proving two documents embed the same `/BaseFont` name with genuinely different
   subsets are measured below (govdocs1_000_000010.pdf / govdocs1_001_001038.pdf, both `Arial`).

2. **D-6.4's inherited-`/Resources` mutation bug is real and independently confirmed by reading
   `@cantoo/pdf-lib`'s own source — but the public corpus contains zero pages that would trigger
   it.** `PDFPageLeaf.normalize()` (the method every resource-adding call, including
   `page.drawImage()` — PAGE-08's core primitive — routes through) contains three literal
   `// TODO: Clone 'Resources'/'Font'/'XObject' if it is inherited` comments and does not clone
   before mutating. This is confirmed at file:line below. The public corpus (217 files) has zero
   leaf pages missing an own `/Resources` key (measured), so this bug cannot be reproduced against
   a real fixture today — a constructed fixture is required, following the same
   measure-then-construct discipline Phase 3 used for its G2b fixture.

3. **`@cantoo/pdf-lib`'s `copy()`/`copyPages()` explicitly does not carry over outlines or
   AcroForm fields** ("This method won't copy all information over to the new document (acroforms,
   outlines, etc...)" — the library's own docstring). D-6.7 (nest outlines, announce form-field
   collisions) is 100% this phase's own code to write; there is no library default to correct.

A fourth finding is a genuine open question, not a research gap this document can close:
**every realistic browser HEIC decoder (`heic-to`, `libheif-js`, and the WASM blob bundled inside
`heic2any`/`heic-decode` despite their own MIT/ISC wrapper license) compiles LGPL-3.0 C code
(`libheif`/`libde265`) into the shipped JavaScript bundle.** `CLAUDE.md`'s own licensing constraint
says LGPL is "permitted only as a subprocess with a file-in/file-out interface" — a browser-bundled
WASM blob shipped to every visitor is not a subprocess. This is flagged as an Open Question
requiring a maintainer/legal decision before PAGE-07 can be planned with confidence.

Separately, **`tools/license_gate.py` covers only the Python lockfile** (`importlib.metadata`) and
has zero visibility into `client/package-lock.json` — confirmed at file:line below. No npm-license
tooling exists anywhere in this repo. A client-side HEIC decoder is exactly the "accidental route
in" `06-CONTEXT.md` warns about, and nothing in CI would catch it today.

**Primary recommendation:** Build this phase entirely on the already-installed `@cantoo/pdf-lib`;
do not add a second client-side PDF library. Do not implement any font-dedup optimization on
merge. Treat inherited-`/Resources` as a **constructed fixture + regression test**, not a corpus
find. Resolve the HEIC licensing question with the maintainer before writing PAGE-07 plans — do
not silently ship `heic-to`/`libheif-js` on the assumption that "GPL/LGPL as subprocess" covers a
browser bundle. Add `license-checker` (BSD-3-Clause, npm) as a client-side sibling to
`tools/license_gate.py` before any new client dependency ships.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Page insert/reorder/rotate/delete | Browser / Client | — | D-6.1: zero dependency on the text engine; `@cantoo/pdf-lib` structural page-tree edits, no content-stream interpretation needed |
| Merge another PDF's pages in | Browser / Client | — | Same reasoning; `copyPages()` is a pure object-graph copy, resolves inheritance itself (see Code Examples) |
| Merge/place an image (PNG/JPEG/WebP) | Browser / Client | — | `PDFImage.embedPng/embedJpg` + `page.drawImage()`, both already in `@cantoo/pdf-lib`'s public API |
| HEIC decode | Browser / Client (blocked pending licensing decision) | — | No server round trip is permitted by D-6.1/PAGE-09, but every viable decoder is LGPL-bundled WASM — see Open Questions. If the maintainer rules client-side LGPL unacceptable, this single capability becomes the one exception routed through a server subprocess, which then makes it **not** part of a "zero server requests" session and must be disclosed as such per PRIV-01 |
| Font content during merge | Browser / Client | — | Pass-through only — this phase never re-subsets, re-encodes, or otherwise touches font programs; it only copies them structurally, which `PDFObjectCopier` already does correctly (verbatim byte copy) |
| Download/export of the merged file | Browser / Client | — | `pdfDoc.save()` → `Blob` → `<a download>`, entirely local; PAGE-09's gate is that nothing upstream of this step touched a document route |
| Network-request assertion (PAGE-09's test) | Test harness (Node, outside the app) | — | Playwright driving a real browser is the standard mechanism (see Validation Architecture) — not app code |
| Three-engine render verification of merged output (ROADMAP criterion 3) | Python test harness | Browser (produces the fixture) | The browser produces the merged bytes; `harness/run_corpus_harness.py` and `harness/masked_diff.py` (Python, existing, unmodified) do the actual cross-engine assertion — the merged file must be saved to disk and handed to the existing harness, not re-implemented client-side |

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-6.1: Page ops run entirely in the browser.** PAGE-09 is the phase's headline claim and its
  hardest test: a page-operations-only session produces its download **with zero requests to
  document routes**. This is the structural backing for PRIV-01's per-operation local/server
  disclosure — the disclosure is true because the override set is empty, not because a label says
  so. The test must assert on observed network traffic, not on a flag.

- **D-6.2: `@cantoo/pdf-lib` is the library.** `ROADMAP.md`: "page ops are exactly what
  `@cantoo/pdf-lib` is good at, and the merge correctness traps are already enumerated with their
  fixes." It is already a dependency of the Phase 4 client scaffold. Do not add a second
  client-side PDF library for this.

- **D-6.3: Fonts are deduped by content hash on merge, never by `/BaseFont`.** PAGE-06 and ROADMAP
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

### Deferred Ideas (OUT OF SCOPE)

- Page-size normalization on merge as a **default** — permanently out of scope; the explicit
  opt-in choice is in scope.
- Splitting a PDF — that is EXPO-03, Phase 7.
- Extracting pages to images — EXPO-01, Phase 7.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PAGE-01 | Insert blank page inheriting size/rotation from adjacent page, show what it inherited, never silent Letter default | `insertPage()`'s actual default is measured below (A4, not Letter — corrects the CONTEXT.md's generic warning); `getMediaBox()`/`getRotation()` are the read-side APIs to call on the adjacent page before calling `PDFPage.create()` |
| PAGE-02 | Reorder pages | `PDFDocument` page array is a plain `PDFPageLeaf[]` under `catalog.insertLeafNode`; no text-model dependency confirmed by reading the source (D-6.6) |
| PAGE-03 | Rotate pages | `page.setRotation(degrees(n))` exists (`PDFPage.ts:149`), operates on any page regardless of classification (D-6.6) |
| PAGE-04 | Delete pages | `pdfDoc.removePage(index)` exists (`PDFDocument.ts:938`), no classification dependency |
| PAGE-05 | Merge PDF: outline nesting, form-field collision announcement, per-page size preserved by default | Confirmed **not** handled by `copyPages()`/`copy()` — must be hand-built; `copyPages()` does correctly preserve per-page size via its `InheritableEntries` resolution (Code Examples) |
| PAGE-06 | Font dedup by content hash, never `/BaseFont`, on merge | Measured: `copyPages()` performs **zero** cross-document font dedup by default (Code Examples); real corpus pair with same `/BaseFont`, different subsets, proven below |
| PAGE-07 | Merge image as new page: PNG/JPEG/WebP/HEIC, transparency composited | PNG/JPEG solved by `embedPng`/`embedJpg` (native to the library); WebP and HEIC are **not** natively supported by `@cantoo/pdf-lib` — see Open Questions for HEIC's licensing blocker; WebP needs `createImageBitmap`+canvas re-encode (see Code Examples) |
| PAGE-08 | Place image on existing page with visible aspect-ratio locking | `page.drawImage()` exists but routes through the unimplemented inherited-`/Resources` clone path (D-6.4 finding) — this is the single riskiest primitive in the phase |
| PAGE-09 | Page-ops-only session: zero requests to document routes, asserted on observed traffic | Playwright `page.on('request')` is the standard, verified mechanism (see Validation Architecture); the scaffold's existing server routes (`/upload`, `/jobs/*`) define the concrete "document route" pattern to assert against |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `@cantoo/pdf-lib` | 2.9.1 (installed; `research/STACK.md` pins 2.8.1 — one minor version drift, not itself alarming, but re-run `npm view @cantoo/pdf-lib version` at plan time) [VERIFIED: npm registry, package.json read directly] | Client-side page-tree structural edits: insert, reorder, rotate, delete, merge, image embed/draw | D-6.2, locked. Confirmed by reading its installed source at `client/node_modules/@cantoo/pdf-lib/src/` (not just docs) — genuinely does everything PAGE-01..06,08 need at the object-graph level |

No other core dependency is required for PAGE-01..06 and PAGE-08. PAGE-07's WebP path needs
nothing new (browser-native `createImageBitmap`/`<canvas>`, see Code Examples). PAGE-07's HEIC
path is the one open item — see Package Legitimacy Audit and Open Questions before adding anything.

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `vitest` | 4.1.11 [ASSUMED — package name from training/WebSearch, npm registry confirms existence but not via official docs/Context7] | Fast unit tests for the merge/page-op logic that doesn't need a real browser (e.g. the font-dedup-never-by-name assertion, the blank-page inheritance calculation) | Wave 0 — no JS test framework currently installed in `client/package.json` |
| `@playwright/test` | 1.62.1 [ASSUMED — same provenance caveat] | The PAGE-09 network-assertion E2E test; also the natural place for the three-engine-bar handoff (drive the browser, save the merged file, shell out to the existing Python harness) | Wave 0 — nothing installed today |
| `license-checker` | 25.0.1, BSD-3-Clause [ASSUMED — same provenance caveat] | Extends `tools/license_gate.py`'s AGPL/LGPL scanning to `client/package-lock.json`, which it currently does not cover at all | Recommended before PAGE-07 ships any new client dependency (see Common Pitfalls) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `@cantoo/pdf-lib` | `qpdf-wasm` (Apache-2.0, 2.2MB) | Would give byte-identical client/server page-op semantics, but D-6.2 already locks `@cantoo/pdf-lib` and this phase has zero server-side page-op code to diverge from — not worth the WASM download for this phase |
| `heic-to`/`libheif-js` for HEIC | Server-side HEIC decode via a Python library, called through a new document route | Breaks D-6.1/PAGE-09's "zero server round trips" for any session that merges a HEIC image — the disclosure UI would need to show this one operation as server-side, which is honest but weakens the phase's headline claim. See Open Questions. |
| `heic-to`/`libheif-js` for HEIC | `hevc.js` 0.0.1 (MIT) | Genuinely permissive license, but slopcheck flags it `[SUS]` (GHOST_TOWN — 15 downloads total, created 2026-03, v0.0.1) and it decodes raw HEVC bitstreams, not the HEIF container format — would still need a separate HEIF box parser. **Not recommended without independent validation.** |
| `vitest` for client unit tests | Jest | Vitest is the standard pairing for a Vite-based SPA (same config, same transform pipeline as the app itself); Jest would need a separate Babel/webpack transform setup for no benefit here |

**Installation:**
```bash
# No new core dependency — @cantoo/pdf-lib is already in client/package.json.
cd client
npm install -D vitest @playwright/test
npm install -D license-checker   # closes the tools/license_gate.py client-side gap
npx playwright install chromium  # browser binary for the E2E network-assertion test
```

**Version verification:** Run before locking any of the above into a plan:
```bash
npm view @cantoo/pdf-lib version   # confirm still 2.9.1 or note drift
npm view vitest version
npm view @playwright/test version
npm view license-checker version
```

## Package Legitimacy Audit

> Required because this phase's discretionary HEIC/testing work introduces new client-side
> dependencies. `slopcheck` was available and executed for every package below.

| Package | Registry | Age | Downloads (wk) | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------------|--------------|-----------|-------------|
| `@cantoo/pdf-lib` | npm | already installed, MIT | — | github.com/cantoo-scribe/pdf-lib | not re-checked (existing, D-6.2 locked) | Approved (existing) |
| `vitest` | npm | ~4.7 yrs (2021-12) | 99,306,735 | github.com/vitest-dev/vitest | `[SUS]` — TYPOSQUAT_RISK, "suspiciously close to 'vite'" | **Approved with note** — false positive: `vitest` is the official Vite-ecosystem test runner (`vitejs`/`vitest-dev` org), not a typosquat. Keep the human-verify checkpoint per protocol, but flag it pre-resolved in the plan |
| `@playwright/test` | npm | ~5.9 yrs (2020-09) | (scoped package; not queryable via the point-downloads endpoint used) | github.com/microsoft/playwright | `[OK]` | Approved |
| `license-checker` | npm | ~13.5 yrs (2013-01) | 1,069,455 | github.com/davglass/license-checker | `[OK]` | Approved |
| `heic-to` | npm | ~2 yrs (2024-08), actively updated (2026-05) | 705,445 | github.com/hoppergee/heic-to | `[OK]` | **Flagged — see Open Questions.** Clean per slopcheck, but bundles LGPL-3.0 `libheif`/`libde265` WASM; conflicts with `CLAUDE.md`'s "LGPL only as subprocess" policy for a browser-shipped bundle |
| `libheif-js` | npm | ~6.6 yrs (2020-01) | 1,676,848 | github.com/catdad-experiments/libheif-js | `[OK]` | **Flagged — same LGPL concern as `heic-to`** |
| `heic2any` | npm | ~7.2 yrs (2019-06), last published 2023-03 | 1,176,304 | github.com/alexcorvi/heic2any | `[OK]` | **Flagged — wrapper license is MIT but the compiled WASM inside is derived from libheif/libde265 (LGPL-3.0); this is the exact "MIT top-level, GPL-family underneath" trap `research/STACK.md` already documents for `pdf2docx`/PyMuPDF**. Also unmaintained (3+ years) |
| `heic-decode` | npm | ~6.6 yrs (2020-01), last published 2025-07 | 1,551,713 | github.com/catdad-experiments/heic-decode | `[OK]` | Same LGPL-in-WASM concern as above |
| `hevc.js` | npm | ~5 months (2026-03) | not queried (trivially low per slopcheck) | github.com/privaloops/hevc-js | `[SUS]` — GHOST_TOWN, "Only 15 downloads. Nobody uses this." | **Not recommended.** Genuinely MIT-licensed and avoids the LGPL problem, but too immature to bet a shipped feature on, and does not itself parse the HEIF container (decodes raw HEVC only) |

**Packages removed due to slopcheck `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** `vitest` (false positive, documented above — keep the
checkpoint anyway per protocol), `hevc.js` (genuine immaturity concern, not recommended).
**Packages flagged for a licensing (not supply-chain) reason:** `heic-to`, `libheif-js`,
`heic2any`, `heic-decode` — all clean on slopcheck, all carry an LGPL-3.0 WASM payload. This is a
**policy** question for the maintainer, not a malware/hallucination question — see Open Questions.
The planner should gate any of these behind a `checkpoint:human-verify` regardless of slopcheck
status, because the risk here is legal/licensing, which slopcheck does not check.

## Architecture Patterns

### System Architecture Diagram

```
                     ┌─────────────────────────────────────────────┐
                     │            Browser (Phase 4 SPA)             │
                     │                                               │
 User action ───────►│  Page-op UI (insert/reorder/rotate/delete/    │
 (thumbnail rail,     │  merge/place-image)                          │
  drag, button)       │        │                                     │
                     │        ▼                                     │
                     │  In-memory @cantoo/pdf-lib PDFDocument        │
                     │  (loaded once from the user's original file, │
                     │   held client-side only — D-6.1)              │
                     │        │                                     │
                     │        ├─ insertPage()/removePage()/          │
                     │        │  setRotation() — pure page-tree edit │
                     │        │                                     │
                     │        ├─ copyPages(srcDoc, indices) ─────────┤◄── second local
                     │        │  (merge: structural deep-copy,       │    PDFDocument,
                     │        │   resolves inherited Resources/      │    loaded from a
                     │        │   MediaBox/CropBox/Rotate onto the   │    second user-
                     │        │   copied leaf — see Code Examples)   │    selected file
                     │        │                                     │    (also local)
                     │        ├─ embedPng()/embedJpg()/drawImage()   │
                     │        │  (image merge/place — routes through │
                     │        │   normalize(), the unimplemented     │
                     │        │   inherited-Resources clone path —   │
                     │        │   D-6.4 risk)                        │
                     │        │                                     │
                     │        ▼                                     │
                     │  pdfDoc.save() → Uint8Array → Blob            │
                     │        │                                     │
                     │        ▼                                     │
                     │  <a download> — file leaves the browser only  │
                     │  as a user-initiated download, never a fetch  │
                     │                                               │
                     │  ✗ NO request to /upload, /jobs/*, or any     │
                     │    other document route — this is PAGE-09's   │
                     │    entire test surface                        │
                     └─────────────────────────────────────────────┘
                                        │
                                        │ (test-harness only, not app code)
                                        ▼
                     ┌─────────────────────────────────────────────┐
                     │  Playwright test: page.on('request') asserts │
                     │  zero matches against the API base URL        │
                     │  during a page-ops-only scenario (PAGE-09)    │
                     └─────────────────────────────────────────────┘
                                        │
                                        │ (separately, for ROADMAP criterion 3
                                        │  three-engine bar — not app code either)
                                        ▼
                     ┌─────────────────────────────────────────────┐
                     │  harness/run_corpus_harness.py (Python,       │
                     │  existing, unmodified) renders the merged     │
                     │  file saved to disk in pdfium/Poppler/MuPDF   │
                     │  and diffs against masked_diff.py's tolerance │
                     └─────────────────────────────────────────────┘
```

### Recommended Project Structure

Phase 4's client scaffold does not exist yet beyond `App.jsx`/`main.jsx` — this is an interface
requirement on Phase 4, not an assumed shape. Suggested module boundary within `client/src/`:

```
client/src/
├── pageOps/
│   ├── pdfDocument.ts        # thin wrapper: load, save-as-blob, hold the in-memory PDFDocument
│   ├── insertBlankPage.ts    # PAGE-01: reads adjacent page's getMediaBox()/getRotation() first
│   ├── reorder.ts            # PAGE-02
│   ├── rotate.ts             # PAGE-03
│   ├── deletePage.ts         # PAGE-04
│   ├── mergePdf.ts           # PAGE-05/06: copyPages() + hand-built outline/AcroForm handling
│   ├── mergeImage.ts         # PAGE-07: PNG/JPEG/WebP native; HEIC gated on Open Question
│   └── placeImage.ts         # PAGE-08: drawImage() with the D-6.4 clone guard (see Pitfalls)
├── components/
│   └── ThumbnailRail/        # Phase 4 dependency — VIEW-04, badge display
└── privacy/
    └── operationLog.ts       # per-operation local/server disclosure state (PRIV-01) —
                               # an empty override set for this phase's ops, verified by
                               # the PAGE-09 test, not asserted by a label
```

### Pattern 1: Merge preserving inherited page attributes (D-6.4's safe path)

**What:** `copyPages()` already resolves `Resources`/`MediaBox`/`CropBox`/`Rotate` inheritance
correctly for pages coming **from** the source document, before copying — this is the one place in
the library where the "clone before mutate" discipline the codebase's own `// TODO` comments admit
is missing elsewhere is actually implemented.
**When to use:** Every PAGE-05 merge call. Do not write a custom inheritance resolver for the
merge-donor side — it is unnecessary.
**Example:**
```typescript
// Source: client/node_modules/@cantoo/pdf-lib/src/core/PDFObjectCopier.ts:54-72
private copyPDFPage = (originalPage: PDFPageLeaf): PDFPageLeaf => {
  const clonedPage = originalPage.clone();

  // Move any entries that the originalPage is inheriting from its parent
  // tree nodes directly into originalPage so they are preserved during
  // the copy.
  const { InheritableEntries } = PDFPageLeaf;   // ['Resources','MediaBox','CropBox','Rotate']
  for (let idx = 0, len = InheritableEntries.length; idx < len; idx++) {
    const key = PDFName.of(InheritableEntries[idx]);
    const value = clonedPage.getInheritableAttribute(key)!;
    if (!clonedPage.get(key) && value) clonedPage.set(key, value);
  }

  clonedPage.delete(PDFName.of('Parent'));
  return this.copyPDFDict(clonedPage) as PDFPageLeaf;
};
```

### Pattern 2: The D-6.4 risk in the DESTINATION document, not the merge source

**What:** Any call that adds a resource to a page already living in the working document — most
directly `page.drawImage()` for PAGE-08 — routes through `PDFPageLeaf.normalize()`, which resolves
inherited `Resources`/`Font`/`XObject`/`ExtGState` but does **not clone** before writing back onto
the (possibly shared) dict. Three `// TODO` comments in the library's own source confirm this is
known and unfixed as of 2.9.1.
**When to use (i.e. when to add a guard):** Before any PAGE-08 image placement, or any future
resource-adding operation, on a page that might share an inherited `/Resources` with a sibling.
**Example (the unguarded library code, verbatim):**
```typescript
// Source: client/node_modules/@cantoo/pdf-lib/src/core/structures/PDFPageLeaf.ts:204-247
normalize() {
  if (this.normalized) return;
  const { context } = this;
  // ...
  // TODO: Clone `Resources` if it is inherited
  const dictOrRef = this.getInheritableAttribute(PDFName.Resources);
  const Resources = context.lookupMaybe(dictOrRef, PDFDict) || context.obj({});
  this.set(PDFName.Resources, Resources);   // <- may be the SAME object a sibling page inherits

  // TODO: Clone `Font` if it is inherited
  const Font = Resources.lookupMaybe(PDFName.Font, PDFDict) || context.obj({});
  Resources.set(PDFName.Font, Font);        // <- mutates the shared dict in place

  // TODO: Clone `XObject` if it is inherited
  const XObject = Resources.lookupMaybe(PDFName.XObject, PDFDict) || context.obj({});
  Resources.set(PDFName.XObject, XObject);  // <- same for the image dict PAGE-08 writes into
  // ...
  this.normalized = true;
}
```
The call chain that reaches this from PAGE-08's primary API:
`page.drawImage()` (`api/PDFPage.ts:1123`) → `node.newXObject('Image', image.ref)`
(`api/PDFPage.ts:1136`) → `newXObjectKey()` → `normalizedEntries()` → `normalize()`
(`core/structures/PDFPageLeaf.ts:171-176, 249-262, 204-247`).
**Mitigation this phase must implement itself:** before calling any resource-adding API on a page,
check `'/Resources' in page.node` (i.e., does the page have its own, non-inherited `/Resources`
key) and if not, explicitly `page.node.Resources()` then deep-clone it onto the page before
proceeding — the same copy-on-write discipline `PITFALLS.md` Pitfall 8 already prescribes for the
Python engine, applied here to the client library.

### Anti-Patterns to Avoid

- **Deduping fonts by `/BaseFont` name to shrink merged output.** The library doesn't do this by
  default (verified — see Standard Stack summary), so don't add it. If a size-optimization pass is
  ever wanted, dedupe only by a hash of the embedded font program's raw bytes (`/FontFile*`
  stream contents), never by name — matching D-6.3 and `PITFALLS.md` Pitfall 4/10 exactly.
- **Wiring the client to the scaffold's existing `POST /jobs/{id}/export/merge` or
  `POST /jobs/{id}/export/rotate` routes** (`server/app.py:733`, `server/app.py:801` on `main`,
  pre-GSD prototype). These are exactly the kind of server-side page-op implementation D-6.1
  exists to prevent for this phase's user-facing flow. They may exist in the codebase for other
  reasons (or be deleted per Phase 4's own defect-closing work), but no PAGE-01..09 code path in
  this phase should ever call them.
- **Assuming `PDFPage.create()`'s default is "Letter."** It is `PageSizes.A4`
  (`api/PDFDocument.ts:1017-1024`, `dims = Array.isArray(page) ? page : PageSizes.A4`). Both are
  wrong defaults for D-6.5's purposes, but the plan should cite the correct one when writing the
  guard/test.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Page-tree structural copy across documents (merge) | A custom PDF object-graph walker/copier | `@cantoo/pdf-lib`'s `PDFObjectCopier`/`copyPages()` | Already correctly resolves inheritable attributes onto copied leaves (Pattern 1) and handles the full dict/array/stream/ref graph with cycle-safe `traversedObjects` tracking — reimplementing this is exactly the kind of "custom PDF structure serialization" `PITFALLS.md` Pitfall 8 warns is never worth it |
| Zero-network-request assertion | A custom `fetch`/`XMLHttpRequest` monkey-patch inside app code to count calls | Playwright's `page.on('request')` in a test file, outside app code | The test must assert on **observed** traffic (D-6.1's own wording), which means an external observer, not app-internal instrumentation that could itself be buggy or bypassed by a future `navigator.sendBeacon`/WebSocket call the instrumentation didn't hook |
| AGPL/LGPL scanning for the client bundle | A hand-rolled `package-lock.json` license-field grep | `license-checker` (npm, BSD-3-Clause, 13.5 yrs old, 1M+ weekly downloads) | Purpose-built, walks the full resolved dependency tree the same way `tools/license_gate.py` already does for Python via `importlib.metadata` — don't reinvent that logic in a different language |
| Checking whether an npm package name is a supply-chain risk | Manual npm-page eyeballing | `slopcheck scan --pkg npm <name> --json` (already installed, used throughout this research) | Already the project's established tool (Package Legitimacy Gate); consistent with how Python dependencies are audited |

**Key insight:** Every "don't hand-roll" item in this phase resolves to "the library or tool
already installed/available already does this correctly — the actual risk is not reimplementing
it, it's *trusting* it uncritically where it has a documented gap (D-6.4)."

## Common Pitfalls

### Pitfall 1: Assuming `@cantoo/pdf-lib`'s merge dedupes fonts (in either direction)

**What goes wrong:** A developer either (a) assumes the library already dedupes by hash and skips
verifying it, shipping a merge path that's actually fine but untested for the failure mode named
in D-6.3, or (b) "optimizes" file size by writing a name-based font-merge step, reintroducing the
exact corruption Pitfall 4/10 of `PITFALLS.md` describe.
**Why it happens:** The CONTEXT.md and ROADMAP framing ("fonts deduped by content hash, never by
`/BaseFont`") reads as if the library needs to be told not to do something dangerous. It doesn't —
it does nothing at all, which is safe but not optimized.
**How to avoid:** Write a merge regression test using the real corpus pair below, asserting **both**
that the output renders both documents' text correctly (no dedup corruption — this passes today,
zero code needed) **and**, separately, that any future size-optimization work is hash-gated, never
name-gated (a static/lint-level check, since there is no such code yet to unit-test).
**Warning signs:** Any PR touching merge that introduces a `Map<string, PDFRef>` keyed on
`/BaseFont` or `getName()`.

**Measured real-corpus evidence (command + output):**
```bash
uv run --frozen python3 -c "
import pikepdf
def inspect(path, tag):
    pdf = pikepdf.open(path)
    for page in pdf.pages:
        for fname, font in ((page.get('/Resources') or {}).get('/Font') or {}).items():
            if str(font.get('/BaseFont','')) == f'/{tag}+Arial':
                fd = font.get('/FontDescriptor')
                ff2 = fd.get('/FontFile2') if fd else None
                print(path, fname, 'FirstChar', font.get('/FirstChar'), 'LastChar', font.get('/LastChar'),
                      'nWidths', len(font.get('/Widths') or []), 'fontFileBytes', len(bytes(ff2.read_bytes())) if ff2 else None)
    pdf.close()
inspect('corpus/public/govdocs1_000_000010.pdf', 'EEPLGH')
inspect('corpus/public/govdocs1_001_001038.pdf', 'ACKMHB')
"
# Output:
# corpus/public/govdocs1_000_000010.pdf /TT8 FirstChar 32 LastChar 32  nWidths 1  fontFileBytes 17352
# corpus/public/govdocs1_001_001038.pdf /TT0 FirstChar 32 LastChar 121 nWidths 90 fontFileBytes 32120
```
`govdocs1_000_000010.pdf` (4 pages) embeds `/EEPLGH+Arial` covering exactly **one** glyph (code
32, space). `govdocs1_001_001038.pdf` (46 pages) embeds `/ACKMHB+Arial` covering **90** glyphs
(codes 32–121) with a font program nearly twice the byte size. Both declare `/BaseFont /Arial`
after stripping the subset tag. A name-based dedup merging these two documents would serve one
document's text through the other's 1-glyph subset — spectacular, silent corruption. This exact
pair (or a similar one from the 60+ shared-`/BaseFont` groups found across the corpus — `Helvetica`
alone appears in 20 files, `TimesNewRoman` in 22) is the right fixture for the PAGE-06 regression
test. Full discovery command and the complete list of shared-`/BaseFont` groups (Arial, Helvetica,
Times-*, TimesNewRoman*, HelveticaNeueLTStd-*, etc. — over 60 base-font names shared across 2+
files) is reproducible via a `pikepdf`-based grouping script; see Sources for the exact approach.

### Pitfall 2: Trusting `normalize()` to be safe on any page touched by `drawImage()`/PAGE-08

**What goes wrong:** PAGE-08 places an image on an existing page. If that page (or a sibling page
under the same `/Pages` parent) shares an inherited `/Resources` dict, the unguarded `normalize()`
call mutates the shared dict, and a sibling page — one the user never touched — silently gains (or
later collides on) resource entries it never had.
**Why it happens:** Confirmed directly in `@cantoo/pdf-lib` 2.9.1's own source — three unresolved
`// TODO: Clone ... if it is inherited` comments sit exactly on this path (see Code Examples,
Pattern 2). This is not a hypothetical; it is a known, unfixed gap in the installed dependency.
**How to avoid:** Add an explicit clone-before-mutate guard in this phase's own `placeImage.ts`
(and any other resource-adding op) that checks `'/Resources' in page.node` (own key, not resolved)
before calling any API that reaches `normalize()`, and clones if absent.
**Warning signs:** Any PAGE-08 test that only exercises single-page or already-`/Resources`-owning
documents. The bug is invisible until a two-sibling-pages-sharing-inherited-Resources fixture
exists.

**Corpus measurement result (honest negative — command + output):**
```bash
# Walked the raw /Pages tree of all 217 public-tier files via pikepdf, checking each leaf page's
# OWN dict (not the inheritance-resolved view) for a missing /Resources key.
# Result: 0 leaf pages across the entire public corpus lack an own /Resources key.
```
`/Rotate` and `/CropBox` inheritance is extremely common (far_federal_acquisition_regulation.pdf
alone has 2,026 pages with no own `/Rotate`; ~50 other files show the same pattern for `/Rotate`
and/or `/CropBox`), and no `/Pages` intermediate node in the corpus declares an explicit non-default
`/Rotate` or `/MediaBox` for a descendant to inherit — every inheritance case found resolves to
"absent everywhere, falls through to the PDF spec default" rather than "ancestor sets an explicit
override." `/Resources` inheritance specifically (the D-6.4 case) was not found at all. **This
means the D-6.4 regression test needs a constructed two-page fixture** (one `/Pages` node, two
kid leaves, neither with an own `/Resources`, ancestor `/Pages` node owning one) — following the
same measure-then-construct discipline Phase 3 used for its G2b fixture when the corpus came up
short. This is an honest gap, not a guess: the corpus was searched and the case genuinely isn't
there.

### Pitfall 3: Wiring PAGE-05/07's UI to the scaffold's existing server-side merge/rotate routes

**What goes wrong:** The salvaged `client/` scaffold's `App.jsx` currently talks to a FastAPI
backend that already has `POST /jobs/{id}/export/merge` (`server/app.py:733`) and
`POST /jobs/{id}/export/rotate` (`server/app.py:801`). A developer wiring up Phase 6's merge UI
under time pressure could reach for the already-working server endpoint instead of the
not-yet-built client-side path, silently violating D-6.1 and making PAGE-09's test fail (or worse,
passing PAGE-09 only because nobody wrote the negative-case test that would catch it).
**Why it happens:** The endpoint already exists, already works, and doing the client-side version
is more code.
**How to avoid:** PAGE-09's test IS the guard — but it must run as part of every PR touching page
ops, not just at phase-gate time. Name the specific routes to assert zero traffic against
(`/upload`, `/jobs/**`) in the test itself, derived from the scaffold's actual route table
(`server/app.py` route list, grepped above), not from a guess.
**Warning signs:** Any client code path for PAGE-01..08 that imports a fetch/axios call.

### Pitfall 4: The HEIC decode licensing trap

**What goes wrong:** A developer picks `heic-to` (actively maintained, technically the best
option, MIT on the npm registry per its own `package.json`) and ships it, because `npm view
heic-to license` reports nothing alarming and slopcheck reports `[OK]`. Neither check looks inside
the compiled `.wasm` payload the package bundles, which is built from `libheif`/`libde265`
(LGPL-3.0). This is structurally the same trap `research/STACK.md` already documents for
`pdf2docx` (MIT wrapper, AGPL `PyMuPDF` dependency) — just one license family down, and on the
client instead of the server, which is a context CLAUDE.md's licensing section does not explicitly
address (it was written assuming the copyleft risk is server-side subprocess calls).
**Why it happens:** npm's `license` field and slopcheck both describe the JS/TS wrapper's own
license, never the license of C/C++ code cross-compiled into a bundled `.wasm` blob.
**How to avoid:** Treat this as a policy decision, not an engineering one — see Open Questions.
Do not resolve it unilaterally in a plan; get an explicit maintainer answer first.
**Warning signs:** Any `package.json` addition where `license` is clean but `README.md` mentions
"powered by libheif" or "WebAssembly build of."

### Pitfall 5: `tools/license_gate.py` provides zero coverage for this phase's new client dependency

**What goes wrong:** Phase 6 is the first phase to add new **client-side** npm dependencies since
the project's AGPL gate was built. `tools/license_gate.py` runs in CI (`.github/workflows/license-
gate.yml`) and would report green even if `client/package-lock.json` pulled in an AGPL package
transitively, because it never reads that file.
**Confirmed at file:line:**
```python
# tools/license_gate.py:20-33 — _offending_distributions()
for dist in metadata.distributions():   # <- importlib.metadata: PYTHON packages only,
    ...                                  #    resolved from the active venv, never touches npm
```
`.github/workflows/license-gate.yml` (10 lines) runs exactly one step:
`uv run python tools/license_gate.py` — no `npm`, no `license-checker`, no reference to
`client/` anywhere in the workflow or the script.
**How to avoid:** Add `license-checker` as a client devDependency and a second CI step/workflow
before this phase ships any new client package (see Standard Stack, Don't Hand-Roll). This is a
prerequisite task for PAGE-07 specifically, since that's the requirement introducing new client
dependencies at all — PAGE-01..06,08 need nothing new.
**Warning signs:** A PR that adds any package to `client/package.json` with no corresponding CI
change.

## Code Examples

### Reading the adjacent page's effective size/rotation before inserting a blank page (PAGE-01)

```typescript
// Source: read against client/node_modules/@cantoo/pdf-lib/src/api/PDFPage.ts
// getMediaBox() (line ~483) and getRotation() (line ~155-162) both resolve inheritance
// themselves (PDFPageLeaf.MediaBox()/Rotate() call getInheritableAttribute internally),
// so calling them on an existing page already gives the EFFECTIVE value, not just the
// page's own un-inherited dict entry. This is the correct read path for D-6.5 — no manual
// inheritance walk needed on the read side (only the write side, per Pitfall 2, has a gap).
const adjacentPage = pdfDoc.getPage(insertAtIndex > 0 ? insertAtIndex - 1 : insertAtIndex);
const { width, height } = adjacentPage.getMediaBox();
const rotation = adjacentPage.getRotation(); // { type: 'degrees', angle: 0 | 90 | 180 | 270 }

const blankPage = pdfDoc.insertPage(insertAtIndex, [width, height]);
blankPage.setRotation(rotation);
// UI must then disclose: "New page matches page {insertAtIndex}'s size ({width}x{height}) and
// rotation ({rotation.angle}°)" — the D-6.5 "shows what it inherited" requirement.
```

### WebP: no native `@cantoo/pdf-lib` support, browser-native re-encode path (PAGE-07)

```typescript
// @cantoo/pdf-lib only exposes embedPng()/embedJpg() — confirmed by grepping
// client/node_modules/@cantoo/pdf-lib/src/api/PDFDocument.ts for "embed" (no embedWebp).
// The standard browser-native path: decode WebP via createImageBitmap (broadly supported
// since Chrome 32/Firefox 65/Safari 14), draw to an offscreen canvas, re-encode to PNG,
// then hand the PNG bytes to the library's existing embedPng().
async function embedWebpAsPng(pdfDoc: PDFDocument, webpBytes: Uint8Array) {
  const bitmap = await createImageBitmap(new Blob([webpBytes], { type: 'image/webp' }));
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0);
  const pngBlob = await canvas.convertToBlob({ type: 'image/png' });
  const pngBytes = new Uint8Array(await pngBlob.arrayBuffer());
  return pdfDoc.embedPng(pngBytes);
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `pdf-lib` 1.17.1 (original, unmaintained since 2021-11) | `@cantoo/pdf-lib` (maintained fork) | Already reflected in `research/STACK.md`; this research confirms the fork is current (2.9.1 installed vs. 2.8.1 pinned) | No action beyond re-pinning the version number at plan time |
| `renderTextLayer` (pdf.js) | `TextLayer` class | pdf.js 6.x (per `research/STACK.md`'s Version Compatibility table) | Not this phase's concern (Phase 4's viewer), noted only because the thumbnail rail this phase's UI sits inside is a Phase 4 dependency |

**Deprecated/outdated:** None specific to this phase beyond what `research/STACK.md` already
covers for `pdf-lib`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `vitest` and `@playwright/test` are the right client-side test tools for this phase | Standard Stack, Validation Architecture | Low — both are extremely well-established (99M+/wk and Microsoft-maintained respectively); risk is scope/config mismatch with whatever Phase 4 ultimately picks, not a wrong-tool risk. Package names not confirmed via Context7/official docs in this session — tag per provenance rule regardless |
| A2 | `license-checker` (davglass/license-checker) is the right tool to extend `tools/license_gate.py` to npm | Standard Stack, Don't Hand-Roll, Pitfall 5 | Low-Medium — package is old (last published 2022) but stable and widely used; a newer alternative (`license-checker-rseidelsohn`, a maintained fork) may be worth checking at plan time since this exact package hasn't shipped in ~3 years |
| A3 | `heic-to`/`libheif-js`/`heic2any`/`heic-decode` all bundle LGPL-3.0-derived WASM | Package Legitimacy Audit, Pitfall 4, Open Questions | **High** — this is the load-bearing claim behind blocking PAGE-07's obvious implementation. Verified via WebSearch (libde265.org, libheif GitHub) that the underlying C libraries are LGPL-3.0-or-later; not independently verified by decompiling the actual shipped `.wasm` binaries in this session. If wrong (e.g., a vendor ships a from-scratch permissively-licensed decoder inside one of these packages), the Open Question is moot and PAGE-07 is unblocked |
| A4 | `hevc.js` is too immature to use and doesn't parse the HEIF container | Standard Stack alternatives, Package Legitimacy Audit | Low — slopcheck's own GHOST_TOWN flag (15 downloads) is independent, verifiable corroboration; the "doesn't parse HEIF container" claim is inferred from the project name/description (HEVC decoder, not HEIF), not independently confirmed by reading its source |
| A5 | `@cantoo/pdf-lib`'s installed 2.9.1 source (read directly from `client/node_modules/`) accurately represents what a fresh `npm install` would produce at plan time | Throughout | Low — `node_modules` was committed to git per Phase 4 CONTEXT's own documented defect list, so this is the actual resolved version, but it should be re-verified once that repo-hygiene defect is fixed and `node_modules` stops being committed |

**If this table is empty:** N/A — see rows above.

## Open Questions

1. **Can this project bundle LGPL-3.0-derived WASM into the client-side SPA for HEIC decode
   (PAGE-07)?**
   - What we know: `CLAUDE.md`'s licensing constraint reads "GPL/LGPL permitted only as a
     subprocess with a file-in/file-out interface (GPL triggers on distribution, and a hosted
     service distributes nothing) — this keeps Poppler and veraPDF available." Every realistic
     browser HEIC decoder (`heic-to`, `libheif-js`, and the WASM bundled inside `heic2any`/
     `heic-decode` regardless of their own wrapper license) is built on `libheif`/`libde265`
     (LGPL-3.0-or-later, confirmed via libde265.org and the libheif GitHub repo).
   - What's unclear: Whether "subprocess" was written with only the server-side case in mind, and
     whether the maintainer considers a browser-bundled WASM binary (a) a form of "distribution"
     the LGPL cares about at all in this exact sense, and (b) whether LGPL's relink/replace
     requirement is satisfiable for a minified SPA bundle (some projects satisfy LGPL-in-WASM by
     shipping the `.wasm` as a separate, unminified, dynamically-loaded asset with its own
     unmodified source alongside — that's an engineering answer to a legal question, and worth
     surfacing as an option, but not this document's call to make).
   - Recommendation: Escalate to the maintainer before writing any PAGE-07 HEIC plan. Three
     concrete resolution paths exist for the planner to present: (a) maintainer accepts LGPL as
     "not distribution" for a client bundle and PAGE-07 proceeds with `heic-to`; (b) HEIC decode
     moves server-side as file-in/file-out subprocess (satisfies the existing policy cleanly, but
     means a HEIC-image-merge session is **not** a zero-server-request session, and PRIV-01's
     per-operation disclosure must show that one operation as server-side); (c) HEIC support is
     descoped from v1 entirely, pending a genuinely permissive decoder maturing (`hevc.js` or
     similar). This document does not recommend between them — it's a policy call.

2. **What is the exact "document route" allowlist/blocklist for PAGE-09's network assertion?**
   - What we know: The pre-GSD scaffold's current routes are `/health`, `/fonts`, `/upload`,
     `/jobs/{id}/status`, `/jobs/{id}/replace`, `/jobs/{id}/download`,
     `/jobs/{id}/page/{n}/png|jpeg`, `/jobs/{id}/export/{pdfa,compress,split,merge,rotate,docx}`,
     `/jobs/{id}/text`, `/jobs/{id}/html` (grepped from `server/app.py` on `main`).
   - What's unclear: Phase 4 has not been planned or built yet, and its own hardening pass may
     restructure these routes entirely (e.g., under a `/documents/` or `/api/` prefix, per
     standard REST practice, or with CORS/base-URL changes). The concrete route list this research
     found is prior-art from an unreviewed scaffold, not a locked API surface.
   - Recommendation: Phase 6's PAGE-09 test should assert against **the Phase 4 SPA's configured
     API base URL** as a single pattern (e.g., "zero requests whose target origin/path-prefix
     matches `import.meta.env.VITE_API_BASE`"), not a hardcoded route list — this keeps the test
     correct regardless of how Phase 4 finalizes its route naming, and is the more robust
     interpretation of "zero requests to document routes" as an interface requirement on Phase 4
     rather than an assumed shape.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | All client-side page-op code, test tooling | ✓ | v22.23.2 | — |
| npm | Package installation | ✓ | 10.9.8 | — |
| `@cantoo/pdf-lib` | PAGE-01..06, 08 | ✓ (installed, 2.9.1) | 2.9.1 | — |
| `vitest` | Client unit tests | ✗ | — | Install per Standard Stack; no fallback needed, trivial add |
| `@playwright/test` + Chromium | PAGE-09's network-assertion test | ✗ | — | Install per Standard Stack; `npx playwright install chromium` also required (browser binary, not just the npm package) |
| `license-checker` | Closing the client-side AGPL/LGPL gate | ✗ | — | Install per Standard Stack |
| `slopcheck` | Package Legitimacy Gate (this research + future plans) | ✓ (0.6.1) | 0.6.1 | — |
| `uv` / Python 3.13 harness deps (`pypdfium2`, `PIL`, `qpdf`, `pdfcpu`) | ROADMAP criterion 3's three-engine bar on merged output | ✓ (existing, verified working by Phase 1/3) | — | — |

**Missing dependencies with no fallback:** None — everything missing is a straightforward
`npm install` with no environment blocker.

**Missing dependencies with fallback:** None applicable; all Wave-0-gap installs are additive,
not fallback-requiring.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework (client unit) | `vitest` — not yet installed (Wave 0). No JS test framework exists in `client/package.json` today (confirmed by reading it directly: only `vite`/`@vitejs/plugin-react`/`@types/*` in devDependencies) |
| Framework (client E2E / network assertion) | `@playwright/test` — not yet installed (Wave 0) |
| Framework (three-engine bar on merged output) | `pytest` (existing, configured — `pyproject.toml`) driving the existing `harness/run_corpus_harness.py` / `harness/masked_diff.py`, unmodified |
| Config file (vitest) | none yet — Wave 0: create `client/vitest.config.ts` (or extend `vite.config.js` with a `test` block, the standard Vitest pattern for a Vite project) |
| Config file (playwright) | none yet — Wave 0: create `client/playwright.config.ts` |
| Quick run command (client unit) | `cd client && npx vitest run` |
| Quick run command (E2E) | `cd client && npx playwright test` |
| Full suite command | `cd client && npx vitest run && npx playwright test` + `uv run --frozen pytest -q -m "not corpus"` (Python side, for the merged-output three-engine check, once a Phase-6-specific test exists) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| PAGE-01 | Blank page inserted inherits adjacent page's MediaBox+rotation; UI discloses what was inherited | unit | `npx vitest run src/pageOps/insertBlankPage.test.ts` | ❌ Wave 0 |
| PAGE-01 | Never falls back to A4/Letter silently when an adjacent page exists | unit, negative case | `npx vitest run src/pageOps/insertBlankPage.test.ts -t "does not silently default"` | ❌ Wave 0 |
| PAGE-02 | Reorder works on any page regardless of editability classification | unit | `npx vitest run src/pageOps/reorder.test.ts` | ❌ Wave 0 |
| PAGE-03 | Rotate works on any page (incl. scanned/uneditable) | unit | `npx vitest run src/pageOps/rotate.test.ts` | ❌ Wave 0 |
| PAGE-04 | Delete works on any page | unit | `npx vitest run src/pageOps/deletePage.test.ts` | ❌ Wave 0 |
| PAGE-05 | Merge preserves per-page size by default; outlines nested; form-field collisions announced either way | unit + integration | `npx vitest run src/pageOps/mergePdf.test.ts` | ❌ Wave 0 |
| PAGE-06 | Merging two documents with same `/BaseFont`, different subsets, both render correctly — real corpus pair (`govdocs1_000_000010.pdf` + `govdocs1_001_001038.pdf`) | integration + three-engine | `npx vitest run src/pageOps/mergePdf.test.ts -t "font dedup"` (produces the merged file) then `uv run --frozen pytest tests/test_page6_merge_render.py::test_arial_subset_pair_renders_correctly -x` (three-engine check on the produced file) | ❌ Wave 0 (both sides) |
| PAGE-07 | PNG/JPEG/WebP merge as new page; transparency composited | unit | `npx vitest run src/pageOps/mergeImage.test.ts` | ❌ Wave 0 |
| PAGE-07 | HEIC merge as new page | **blocked** — pending Open Question 1's resolution | n/a | ❌ Wave 0, blocked |
| PAGE-08 | Place image on existing page with aspect-ratio lock; inherited-`/Resources` guard holds (D-6.4) | unit, using a **constructed** two-sibling-inherited-Resources fixture (corpus has none — Pitfall 2) | `npx vitest run src/pageOps/placeImage.test.ts -t "inherited resources"` | ❌ Wave 0 |
| PAGE-09 | Page-ops-only session produces its download with zero requests to document routes | E2E, observed network traffic | `npx playwright test tests/e2e/page09-zero-network.spec.ts` | ❌ Wave 0 |
| Gate G5 criterion 1 | (= PAGE-09) | E2E | same as above | ❌ Wave 0 |
| Gate G5 criterion 2 | (= PAGE-01 + PAGE-02/03/04 on uneditable pages) | unit | same as PAGE-01..04 rows | ❌ Wave 0 |
| Gate G5 criterion 3 | (= PAGE-06, "renders correctly in all three engines") | three-engine | `uv run --frozen pytest tests/test_page6_merge_render.py -x` | ❌ Wave 0 |
| Gate G5 criterion 4 | (= PAGE-05 outline/AcroForm/size + D-6.4 resource guard) | unit + constructed fixture | `npx vitest run src/pageOps/mergePdf.test.ts src/pageOps/placeImage.test.ts` | ❌ Wave 0 |
| Gate G5 criterion 5 | (= PAGE-07/08, incl. transparency composite + visible aspect-ratio lock) | unit + visual | `npx vitest run src/pageOps/mergeImage.test.ts src/pageOps/placeImage.test.ts` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `npx vitest run` (client-side, fast, no browser launch)
- **Per wave merge:** `npx vitest run && npx playwright test` (adds the E2E network-assertion
  suite) + `uv run --frozen pytest tests/test_page6_merge_render.py -x` (targeted, not the full
  corpus sweep — per this session's own instruction not to run full-corpus sweeps while other
  research runs concurrently)
- **Phase gate:** Full suite green, plus one manual/CI run of `harness/run_corpus_harness.py`
  against the actual PAGE-06 merged fixture output before `/gsd:verify-work`, satisfying ROADMAP
  criterion 3's three-engine bar on real merge output (not just the harness's existing corpus,
  which contains no merged files)

### Wave 0 Gaps

- [ ] `client/vitest.config.ts` (or a `test` block in the existing `client/vite.config.js`) —
      no JS test framework configured today
- [ ] `client/playwright.config.ts` + `npx playwright install chromium` — no E2E framework or
      browser binary installed today
- [ ] `client/src/pageOps/` — the entire module does not exist yet (Phase 4 hasn't built the SPA
      shell this phase's UI lives inside)
- [ ] `tests/test_page6_merge_render.py` — new Python test file, reusing
      `harness/masked_diff.py`/`harness/run_corpus_harness.py` unmodified against a Phase-6-produced
      merged fixture (the harness's existing corpus has no merged files — this phase must produce
      one and check it in, or generate it at test time)
- [ ] A constructed two-sibling-pages-sharing-inherited-`/Resources` PDF fixture for the D-6.4/
      PAGE-08 regression test — confirmed absent from the real corpus (Pitfall 2); build via
      `pikepdf` (same tool used to measure its absence) mirroring the minimal-fixture pattern
      `harness/g2b_fixture.py` already established for Phase 3's constructed G2b case
- [ ] `client/package.json` — add `license-checker` and a corresponding CI step, ahead of PAGE-07
      shipping any HEIC dependency (Pitfall 5)

## Security Domain

This phase's runtime surface is a browser tab processing files the *user themselves* selected
(their own document to insert/merge, an image, or another PDF to merge in) — there is no new
server-facing attack surface, since D-6.1 keeps this entirely client-side. The threat model is
narrower than Phase 4's (which accepts arbitrary uploads from strangers), but not zero: a
maliciously crafted PDF a user is tricked into "merging in" is still parsed by `@cantoo/pdf-lib`
in the same tab as the rest of the app.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|--------------------|
| V2 Authentication | No | No accounts in v1 (`CLAUDE.md`), no auth surface this phase touches |
| V3 Session Management | No | No server session this phase creates or reads |
| V4 Access Control | No | No multi-tenant/access-control surface — single-user browser tab |
| V5 Input Validation | Yes (narrow) | `@cantoo/pdf-lib`'s own parser is the boundary for a user-supplied "merge this PDF in" file; this phase doesn't add its own parsing, but should wrap `PDFDocument.load()` calls in try/catch and surface a named refusal (matching the project's existing "refuse with a reason" pattern from Phase 3) rather than letting an unhandled exception crash the tab mid-session |
| V6 Cryptography | No | No cryptographic operations in this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|------------------------|
| Malformed/hostile PDF selected as a merge source crashes the tab or hangs it | Denial of Service (self-inflicted, single-tab) | Wrap `PDFDocument.load()` in try/catch; `@cantoo/pdf-lib` is a pure-JS parser (no native memory-unsafety class of bug the way C/C++ parsers have — `research/STACK.md`'s "REWRITE vs APPEND" table already establishes it as append/structural-only, which is also a smaller attack surface than a content-stream interpreter would be), but an infinite/very-deep page tree or object graph could still exhaust tab memory. Lower priority than Phase 4's server-side hardening (Pitfall 11 in `PITFALLS.md`) since the blast radius is one user's own tab, not a shared server process |
| A client-bundled dependency (HEIC decoder or otherwise) introduces a supply-chain risk | Tampering (supply chain) | `slopcheck scan --pkg npm <name> --json` before adding any new client package, exactly as done throughout this research — already the project's established pattern for Python deps, extended here to npm |
| Inherited-`/Resources` mutation (D-6.4/Pitfall 2) silently altering a sibling page's rendered output | Tampering (data integrity, not security in the classic sense, but a correctness-as-trust issue for a tool whose core value is "look like nothing happened") | The clone-before-mutate guard described in Pitfall 2/Pattern 2 |

## Sources

### Primary (HIGH confidence — directly verified this session, local execution)
- `/Users/prempatel/Pictures/pdf-tool/client/node_modules/@cantoo/pdf-lib/src/api/PDFDocument.ts` —
  `insertPage()` (A4 default, lines 1017-1024), `copyPages()` (lines 1058-1072), `copy()`
  (lines 1088-1104, explicit "won't copy acroforms, outlines" docstring)
- `.../src/core/PDFObjectCopier.ts` — full file read; `copyPDFPage()` inheritance resolution
  (lines 54-72), per-call `traversedObjects` map (no cross-call/cross-document dedup, lines 31-42)
- `.../src/core/structures/PDFPageLeaf.ts` — `InheritableEntries` (lines 12-17), `normalize()`
  and its three `// TODO: Clone ... if it is inherited` comments (lines 204-247),
  `newXObject`/`newFontDictionary` call chain into `normalizedEntries()` (lines 150-190)
- `.../src/api/PDFPage.ts` — `drawImage()` → `node.newXObject()` (line 1136), `getRotation()`
  (lines ~155-162), `getMediaBox()` reference (grepped)
- `/Users/prempatel/Pictures/pdf-tool/client/package.json` — confirmed no test framework
  installed; `@cantoo/pdf-lib ^2.8.1` declared, `2.9.1` actually resolved (from `node_modules/
  @cantoo/pdf-lib/package.json`)
- `tools/license_gate.py` (full file read) — confirmed `importlib.metadata.distributions()` only,
  zero npm/JS coverage, lines 20-33
- `.github/workflows/license-gate.yml` (full file read) — confirmed single-step, Python-only CI job
- `corpus/manifest.json` + direct `pikepdf` measurement (commands and outputs reproduced inline
  above and in Pitfalls 1/2) — the real-corpus font-dedup pair and the inherited-`/Resources`
  negative result
- `/Users/prempatel/Pictures/pdf-tool/server/app.py` (route grep) — confirmed existing server-side
  `export/merge` and `export/rotate` routes, the D-6.1 anti-pattern named in Pitfall 3
- `slopcheck scan --pkg npm <name> --json` (run for `heic-to`, `heic-decode`, `heic2any`,
  `libheif-js`, `license-checker`, `hevc.js`, `vitest`, `@playwright/test`) — full output captured
  above in Package Legitimacy Audit
- `npm view <pkg> version license time.created repository.url` + `curl
  api.npmjs.org/downloads/point/last-week/<pkg>` — age/downloads/repo data for the same package set

### Secondary (MEDIUM confidence — official/authoritative source, fetched and cross-checked)
- libde265.org FAQ and GitHub `strukturag/libde265` — LGPL-3.0 license of the HEVC decoder
  underlying every browser HEIC path
- `strukturag/libheif` GitHub — LGPL-3.0-or-later, depends on libde265 for decode
- Playwright official docs pattern (`page.on('request')`) — confirmed via WebSearch results
  referencing playwright.dev's own network-interception documentation

### Tertiary (LOW confidence — flagged for validation)
- `hevc.js` (privaloops/hevc-js) as a genuinely-permissive alternative — package exists and is
  MIT per `npm view`, but slopcheck flags `GHOST_TOWN` (15 downloads) and its HEIF-container-parsing
  capability was not independently verified by reading its source in this session
- Exact browser support matrix for native HEIC via `createImageBitmap` (Safari yes, Chrome/Firefox/
  Edge no due to HEVC patent licensing) — sourced from WebSearch aggregation, not an official
  caniuse.com/MDN page fetched directly this session

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — `@cantoo/pdf-lib`'s relevant behaviour was read from its own installed
  source, not inferred from documentation or training data
- Architecture: HIGH — the diagram and patterns are grounded in the same source-level reads
- Pitfalls: HIGH for D-6.3/D-6.4/D-6.7 (source-level proof); MEDIUM for PAGE-09's exact route list
  (depends on an unbuilt Phase 4); LOW-flagged-as-open-question for PAGE-07's HEIC licensing, by
  design — this is a policy question, not a research gap that more searching would close

**Research date:** 2026-08-30
**Valid until:** 30 days for the `@cantoo/pdf-lib` findings (stable, source-verified, low churn
risk); 7 days for the HEIC package landscape (fast-moving, and blocked on a pending maintainer
decision anyway); re-verify `tools/license_gate.py`'s coverage immediately before PAGE-07 work
starts, since Phase 4 or another concurrent phase may close that gap independently before Phase 6
reaches it.
