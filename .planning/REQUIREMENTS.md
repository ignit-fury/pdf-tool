# Requirements: PDF Tool

**Defined:** 2026-08-12
**Core Value:** Replace text across every page of an existing PDF and have the output look like nothing happened.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Engine Foundation

Not user-facing, but the core value is unreachable without it. Research ranked "silent wrong
output" as the highest-probability risk on the register — output that opens without error
everywhere the team looks and is wrong in Acrobat.

- [ ] **ENG-01**: A corpus of 100–300 real-world PDFs harvested from the wild (not generated) covers subset fonts, Type0/Identity-H, symbolic fonts, Type3, CID-keyed CFF, `/Contents` arrays, inline images, Form XObjects, annotation appearance streams, justified and right-aligned text, tables, an OCR'd scan, vector-outlined text, encrypted files, and malformed files — weighted toward invoices and contracts
- [ ] **ENG-02**: A three-engine differential rasterizer (pdfium, Poppler, MuPDF) runs in CI and asserts that a *masked* image diff of the unedited region is pixel-identical, not merely similar
- [ ] **ENG-03**: Structural validation (`qpdf --check`, `pdfcpu validate`) runs on every engine output in CI
- [ ] **ENG-04**: `playa-pdf` is proven to decode encodings and glyph geometry on at least 4 real documents including one Type0/Identity-H and one subset-font document — or the switch to `pdfminer.six` is made in this phase, not later
- [ ] **ENG-05**: A TJ-refit prototype fits replacement text into an original run's width within 0.5pt, proving the one algorithm no library provides
- [ ] **ENG-06**: A one-page data-flow retention map is written *before* infrastructure is selected, since queue-with-payload vs handle-only and object-store vs tmpfs are expensive to reverse
- [ ] **ENG-07**: CI fails the build on any AGPL package anywhere in the resolved lockfile, not just top-level metadata

### Text Model

The keystone. Find, replace, editability classification, and all four text-derived exports sit on
this one component.

- [ ] **TEXT-01**: A content-stream interpreter walks a document in index mode and emits a run record for every text run
- [ ] **TEXT-02**: Every glyph record carries full provenance — code, glyph, unicode, position, advance, font, render mode, visibility, stream id, operator index, index within TJ, and byte offset
- [ ] **TEXT-03**: Run IDs address the immutable original bytes, never the output, so ordinals never drift across edits
- [ ] **TEXT-04**: Forward encoding resolution is implemented as a documented decision table with the fired branch logged per font — never a guess
- [ ] **TEXT-05**: `Code→Glyph` and `Code→str` are distinct types in code and cannot be passed to the wrong function
- [ ] **TEXT-06**: Text is located outside `/Contents` too — Form XObjects, annotation appearance streams, tiling patterns — and shared Form XObjects are marked not-editable rather than silently corrupting every page that references them
- [ ] **TEXT-07**: `/Contents` arrays are coalesced before parsing, so a tokenizer cannot fuse operators across stream part boundaries
- [ ] **TEXT-08**: Text split across multiple operators reconstructs into readable runs, including glyph-at-a-time and two-column documents

### Editability Classification

- [ ] **CLAS-01**: Every page is classified into one of four uneditable buckets or editable, using three signals — visible glyph count, image coverage, and invisible-to-visible glyph ratio
- [ ] **CLAS-02**: An OCR'd scan is identified as "searchable, not editable" rather than as editable text, and says so in plain language
- [ ] **CLAS-03**: Vector-outlined text is identified as its own bucket, distinct from a scan
- [ ] **CLAS-04**: Every text run carries a three-state classification — editable in original font, editable with substitution, or not editable with a stated reason — available *before* the user clicks, so uneditable runs are greyed out rather than discovered
- [ ] **CLAS-05**: The operation is refused, never the document — a 40-page contract with 3 scanned pages stays fully editable on the other 37 and page-op-able on all 40
- [ ] **CLAS-06**: Page classification badges appear in the thumbnail rail
- [ ] **CLAS-07**: The refusal screen names a specific external OCR route and offers a one-click "tell me when OCR ships" signal

### Text Editing

- [ ] **EDIT-01**: User can select a text run in the browser and replace its text, with the browser hit-testing against server-issued boxes rather than pdf.js text items
- [ ] **EDIT-02**: Replacement text is refitted into the original run's width, with the text matrix after the edited run unchanged within epsilon
- [ ] **EDIT-03**: Overflow is measured and disclosed before commit, with bounded condensing (90–95% is visually undetectable) and visible refusal beyond that
- [ ] **EDIT-04**: An edit that cannot be performed correctly is refused visibly with a reason, never guessed at
- [ ] **EDIT-05**: User can undo and redo edits, with a replace-all batch undoing as a single step

### Find and Replace

Two features, not one. Find needs the visible-text index; replace needs the inverse map back to
operator byte-spans plus width recalculation.

- [ ] **FIND-01**: User can search text across all pages, with the same normalization the interpreter used — intra-word TJ adjustments collapsed, ligatures normalized
- [ ] **FIND-02**: Search defaults to case-insensitive substring, with "match case" and "whole words only" toggles
- [ ] **FIND-03**: Matches are listed with page number, surrounding context, and a live count, and clicking a match jumps to it
- [ ] **FIND-04**: User can opt out of individual matches before applying
- [ ] **FIND-05**: Unreplaceable matches appear in the same list, disabled, with the reason shown — never silently filtered out
- [ ] **FIND-06**: User can replace all remaining matches across every page in one action

### Fonts and Formatting

Font subsetting is a peer of replace, not a follow-on. Embedded fonts are subsets, so typing a
character the document never used is the common case. Shipping replace without this reproduces
PDF-XChange's documented limitation.

- [ ] **FONT-01**: A bundled open-license font set is shipped and selected via a static mapping table, never a heuristic
- [ ] **FONT-02**: Fonts are subset against whole-document glyph usage at save time, so a subset never drops glyphs from text the user did not edit
- [ ] **FONT-03**: New fonts embed as Type0/CIDFontType2 with Identity-H, a correct `/W` array, and a generated `/ToUnicode`, so copy-paste out of Acrobat yields correct Unicode
- [ ] **FONT-04**: `/Widths` are regenerated with a consistency assertion against the font program's own metrics, and a character outside `FirstChar..LastChar` never silently falls back to a `/MissingWidth` of 0
- [ ] **FONT-05**: Every re-subset gets a fresh subset tag, so two subsets of the same family never collide
- [ ] **FONT-06**: An entire visual run is re-encoded when substituting, never half of one — half in the original subset and half in a bundled font is worse than all of it substituted
- [ ] **FONT-07**: User can change size, weight, style, and color on edited text

### Viewer

- [ ] **VIEW-01**: User can open a PDF and see pages rendered faithfully
- [ ] **VIEW-02**: Page 1 is interactive before the last page finishes parsing
- [ ] **VIEW-03**: User can select and copy text, and use browser find
- [ ] **VIEW-04**: A thumbnail rail shows all pages with their classification badges

### Page Operations

Zero dependency on the text engine — fully parallelizable, and where "never leaves your browser"
becomes literally true.

- [ ] **PAGE-01**: User can insert a blank page at any position, inheriting page size and rotation from the adjacent page and showing what it inherited — never a silent Letter default
- [ ] **PAGE-02**: User can reorder pages
- [ ] **PAGE-03**: User can rotate pages
- [ ] **PAGE-04**: User can delete pages
- [ ] **PAGE-05**: User can merge another PDF, with outline nesting, announced form-field collision handling, and per-page page size preserved by default
- [ ] **PAGE-06**: Merging two documents that embed different subsets of the same named font renders both correctly — fonts deduped by content hash, never by `/BaseFont`
- [ ] **PAGE-07**: User can merge an image as a new page (PNG, JPEG, WebP, HEIC, with transparency composited)
- [ ] **PAGE-08**: User can place an image onto an existing page with visible aspect-ratio locking, not a hidden modifier key
- [ ] **PAGE-09**: A page-operations-only session produces its download entirely in the browser, with zero requests to document routes

### Ingest and Document Handling

- [ ] **INGE-01**: Uploads are validated by magic-byte sniffing and a size cap, not by file extension
- [ ] **INGE-02**: User can open a password-protected PDF by supplying the password
- [ ] **INGE-03**: A signed document is detected and the user is warned before saving that a rewrite invalidates the signature
- [ ] **INGE-04**: Malformed and hostile inputs — decompression bombs, cyclic page trees, self-referencing XObjects — fail on their own limits rather than on the host

### Export

- [ ] **EXPO-01**: User can export pages as PNG or JPEG at a chosen DPI, per-page or all pages as a zip
- [ ] **EXPO-02**: User can compress a PDF, lossless and structural by default, with image downsampling as an explicit labeled choice showing before/after size and a preview
- [ ] **EXPO-03**: User can split a PDF into separate files
- [ ] **EXPO-04**: User can flatten a PDF
- [ ] **EXPO-05**: User can export plain text, Markdown, and HTML, all consuming the same run index — a second extraction path anywhere is a signal the text model is under-specified
- [ ] **EXPO-06**: User can export PDF/A, gated on veraPDF passing against a fixture corpus in CI rather than on spot checks
- [ ] **EXPO-07**: User can export DOCX, generated as OOXML directly from the text model, within a written scope ceiling: single-column body text, headings by font-size clustering, bold/italic, inline images, ruled tables only
- [ ] **EXPO-08**: DOCX export shows a pre-conversion warning naming what will degrade in *this specific document*

### Privacy and Trust

- [ ] **PRIV-01**: The UI shows, per operation, whether it runs locally or on the server — backed by the structural rule that an empty override set means the client materializes the file with zero upload
- [ ] **PRIV-02**: The server holds no state whose loss is observable — killing the cache mid-session leaves the session working
- [ ] **PRIV-03**: Scratch space is tmpfs in a per-job container, and job queues carry opaque short-TTL handles, never document bytes
- [ ] **PRIV-04**: No document content appears in logs or error reports
- [ ] **PRIV-05**: A canary-marker retention test runs in CI against scratch, queue, logs, object store, and error reporter — on both the success path and the crash path
- [ ] **PRIV-06**: Document routes send `Cache-Control: no-store` and are verified to bypass CDN caching, since Cloudflare's default cacheable-extension list includes `.pdf`
- [ ] **PRIV-07**: PDF parsing never runs in the request process

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### OCR

- **OCR-01**: User can OCR a scanned page to produce a searchable text layer
- **OCR-02**: User can edit OCR'd text via an overlay path, distinct from content-stream editing
- **OCR-03**: Interest in OCR is measured from the v1 refusal screen's notify signal before this is built

### Redaction

- **REDA-01**: User can permanently remove text and images, not merely cover them
- **REDA-02**: Redaction is verified by confirming the content is absent from the output's object graph

Flagged by research as the top v2 differentiator, deferred for legal-exposure reasons.

### Accounts

- **ACCT-01**: User can create an account and save documents across sessions
- **ACCT-02**: User can view edit history

### Format Conversion

- **CONV-01**: User can convert DOCX to PDF (LibreOffice is genuinely strong at this direction)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| White-box overlay editing as a fallback | Permanent anti-feature. The moment it exists it becomes the fallback for every hard case, the quality claim silently dies, and users cannot tell which mode ran. Good refusal UX is the substitute. |
| Full text reflow / word-processor editing | Requires reconstructing a document model from absolute glyph positions. Breaks on tables, columns, and forms. Acrobat-scale problem. |
| AI chat / summarize over documents | Detonates the privacy story for exactly the confidential documents this product courts. |
| Cloud storage OAuth (Drive, Dropbox) | Contradicts the no-account, no-linkage privacy position. |
| Task-per-hour throttling | Sejda's 3/hour limit is its most-cited complaint and close to the frustration that started this project. |
| Page-size normalization on merge by default | Silently resizes the user's pages. Available as an explicit choice, never a default. |
| User-uploaded fonts | Embedding a user's font file in an export is redistribution, which many commercial licenses forbid. |
| Ghostscript, PyMuPDF, mupdf.js in the runtime | AGPL, which triggers on SaaS. Permissive replacements exist for every job here. Permitted in CI only. |
| `pdf2docx` | MIT at the top level, pulls `PyMuPDF>=1.26.7` transitively. The most likely accidental route into an AGPL violation. |
| LibreOffice for PDF→DOCX | Imports through Draw, producing disconnected text frames rather than paragraphs, and brings profile locking, no timeout, memory leaks, zombie processes, and a large native attack surface. Buys almost nothing since our own layout inference sets the ceiling. |
| Collaborative / multi-user editing | No accounts in v1; not part of the problem being solved. |
| Digital signature creation, form filling, redaction certification | Separate problem domains with their own correctness and legal requirements. |
| A separate bulk find-replace endpoint | Find is a client-side query over the cached index producing N ordinary overrides. A bulk endpoint means two rewrite implementations within six months. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENG-01 | Phase 1 — Conformance Harness + Engine Spike | Pending |
| ENG-02 | Phase 1 — Conformance Harness + Engine Spike | Pending |
| ENG-03 | Phase 1 — Conformance Harness + Engine Spike | Pending |
| ENG-04 | Phase 1 — Conformance Harness + Engine Spike | Pending |
| ENG-05 | Phase 1 — Conformance Harness + Engine Spike | Pending |
| ENG-06 | Phase 1 — Conformance Harness + Engine Spike | Pending |
| ENG-07 | Phase 1 — Conformance Harness + Engine Spike | Pending |
| TEXT-01 | Phase 2 — Text Model | Pending |
| TEXT-02 | Phase 2 — Text Model | Pending |
| TEXT-03 | Phase 2 — Text Model | Pending |
| TEXT-04 | Phase 2 — Text Model | Pending |
| TEXT-05 | Phase 2 — Text Model | Pending |
| TEXT-06 | Phase 2 — Text Model | Pending |
| TEXT-07 | Phase 2 — Text Model | Pending |
| TEXT-08 | Phase 2 — Text Model | Pending |
| CLAS-01 | Phase 2 — Text Model | Pending |
| CLAS-02 | Phase 2 — Text Model | Pending |
| CLAS-03 | Phase 2 — Text Model | Pending |
| CLAS-04 | Phase 2 — Text Model | Pending |
| CLAS-05 | Phase 2 — Text Model | Pending |
| EDIT-02 | Phase 3 — Rewrite Engine + Font Pipeline | Pending |
| EDIT-03 | Phase 3 — Rewrite Engine + Font Pipeline | Pending |
| EDIT-04 | Phase 3 — Rewrite Engine + Font Pipeline | Pending |
| FONT-01 | Phase 3 — Rewrite Engine + Font Pipeline | Pending |
| FONT-02 | Phase 3 — Rewrite Engine + Font Pipeline | Pending |
| FONT-03 | Phase 3 — Rewrite Engine + Font Pipeline | Pending |
| FONT-04 | Phase 3 — Rewrite Engine + Font Pipeline | Pending |
| FONT-05 | Phase 3 — Rewrite Engine + Font Pipeline | Pending |
| FONT-06 | Phase 3 — Rewrite Engine + Font Pipeline | Pending |
| INGE-01 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| INGE-02 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| INGE-03 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| INGE-04 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| PRIV-01 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| PRIV-02 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| PRIV-03 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| PRIV-04 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| PRIV-05 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| PRIV-06 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| PRIV-07 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| VIEW-01 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| VIEW-02 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| VIEW-03 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| VIEW-04 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| CLAS-06 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| CLAS-07 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| EDIT-01 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| EDIT-05 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| FONT-07 | Phase 4 — Web Tier Walking Skeleton + Hardening | Pending |
| FIND-01 | Phase 5 — Find and Replace Across All Pages | Pending |
| FIND-02 | Phase 5 — Find and Replace Across All Pages | Pending |
| FIND-03 | Phase 5 — Find and Replace Across All Pages | Pending |
| FIND-04 | Phase 5 — Find and Replace Across All Pages | Pending |
| FIND-05 | Phase 5 — Find and Replace Across All Pages | Pending |
| FIND-06 | Phase 5 — Find and Replace Across All Pages | Pending |
| PAGE-01 | Phase 6 — Page Ops and Merge | Pending |
| PAGE-02 | Phase 6 — Page Ops and Merge | Pending |
| PAGE-03 | Phase 6 — Page Ops and Merge | Pending |
| PAGE-04 | Phase 6 — Page Ops and Merge | Pending |
| PAGE-05 | Phase 6 — Page Ops and Merge | Pending |
| PAGE-06 | Phase 6 — Page Ops and Merge | Pending |
| PAGE-07 | Phase 6 — Page Ops and Merge | Pending |
| PAGE-08 | Phase 6 — Page Ops and Merge | Pending |
| PAGE-09 | Phase 6 — Page Ops and Merge | Pending |
| EXPO-01 | Phase 7 — Exports | Pending |
| EXPO-02 | Phase 7 — Exports | Pending |
| EXPO-03 | Phase 7 — Exports | Pending |
| EXPO-04 | Phase 7 — Exports | Pending |
| EXPO-05 | Phase 7 — Exports | Pending |
| EXPO-06 | Phase 8 — PDF/A, then DOCX | Pending |
| EXPO-07 | Phase 8 — PDF/A, then DOCX | Pending |
| EXPO-08 | Phase 8 — PDF/A, then DOCX | Pending |

**Coverage:**
- v1 requirements: 72 total
- Mapped to phases: 72 ✓
- Unmapped: 0

**Notes on placement** (full rationale in ROADMAP.md "Deviations from the research sequence"):
- `EDIT-01` sits in Phase 4, not Phase 3, because its observable behaviour is a browser interaction
  and Phase 3 is CLI-only until Gate G2b passes. FONT-01..06 and EDIT-02..04 still ship together.
- `CLAS-06` and `CLAS-07` sit in Phase 4 for the same reason — they are the UI surfaces of the
  Phase 2 classification work. All engine-side classification (CLAS-01..05) is in Phase 2.

---
*Requirements defined: 2026-08-12*
*Last updated: 2026-08-12 after roadmap creation — traceability populated, 72/72 mapped*
