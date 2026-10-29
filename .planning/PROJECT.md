# PDF Tool

## What This Is

A browser-based PDF editor that edits the *actual existing content* of a PDF — replacing text
inside the page's content stream rather than pasting annotations or white boxes on top. Users
open a PDF, find-and-replace text across every page, insert blank pages, merge in images or
other PDFs, restyle text with embedded fonts, and export to several formats. It is aimed at
people who need to change a document that already exists and want the result to look untouched.

It is a real product for other people, used anonymously — no signup to edit a file.

## Current State

Phases 4–8 are implemented locally. The workstation supports atomic text/style editing,
all-page find/replace, browser-local page tools/PDF-image merge, and mixed Undo.
Phase 7 adds browser-local PNG/JPEG/split exports and explicit server compression,
flattening and shared-index text/Markdown/HTML exports. Prepared downloads use the
current materialized PDF without replacing the working document or its history.

Phase 8 adds conservative PDF/A-2b output, verified locally with authenticated
veraPDF, and optional direct OOXML DOCX from the shared model. Document-specific
review and conversion require separate explicit uploads. DOCX supports the locked
body/headings/emphasis/inline-image/ruled-table ceiling; complex layouts become
plain paragraphs. Literal writer removal leaves the other export gates passing.
Evidence: `phases/08-pdf-a-then-docx/08-G7-RESULTS.md`. Hosted G7a CI and
Word/Acrobat observations remain unperformed.

Evidence is in `phases/06-page-ops-and-merge/06-G5-RESULTS.md` and
`phases/07-exports/07-G6-RESULTS.md`. Literal contract-specimen coverage and
Linux/container/CDN release checks remain open. Production HEIC conversion stays
disabled until Linux confinement is verified. No deployment was published.

The post-Phase-8 viewer upgrade adds continuous bounded pages, inline text input
and a contextual toolbar, safe native size/spacing, managed image controls, mixed
Undo/Redo, Replace One/All and a truthful post-commit walkthrough. It retains
preserve-layout geometry. The next stage adds native inserted text containers with
wrapping, multiline layout, growth, spacing, alignment and exact candidate preview.
Arbitrary source reflow and unowned image mutation remain unsupported. Evidence:
`docs/verification/document-viewer-2026-10-29.md` and
`docs/verification/native-text-boxes-2026-10-29.md`.
The following stage adds bounded local bookmark navigation and an atomic retained
history navigator. Navigation pauses further automatic server analysis; explicit
Edit/Find resumes it. Evidence: `docs/verification/document-navigation-2026-10-29.md`.
The next stage adds bounded measured text-layer substring highlights, explicit
approximation/removal labels and an actual-render-gated replacement walkthrough.
Evidence: `docs/verification/search-highlights-2026-10-29.md`. Search coverage stays
within existing authoritative runs; cross-run matching/reflow are not introduced.
The original-run expansion gap is subsequently fixed: Enter/multiline or explicit
Flexible text box replaces a selected source run with a growing native container in
one validated candidate/Undo step. Nearby content stays fixed, source identity and
all committed recipe edits are retained, and space/glyph limits remain explicit.
Evidence: `docs/verification/source-text-expansion-2026-10-29.md`.

## Core Value

**Replace text across every page of an existing PDF and have the output look like nothing
happened.** If everything else on this list fails, this one capability must work.

## Requirements

### Validated

Validated locally in Phases 1–8 (public release remains gated):

- Open and render PDFs in the browser, including password-protected files.
- Classify text and select server-issued text boxes before editing.
- Replace a single run through the atomic content-stream recipe engine.
- Subset/embed bundled fonts; change colour, bold and italic with explicit fitting/refusal.
- Download and undo text/style edits; recover after losing the server cache.
- Find across all pages with canonical Unicode/case/word options, context/navigation,
  per-occurrence exclusions and visible refusals; review then apply one whole recipe
  and undo the batch once, preserving prior text and style.

- Insert, move, rotate and delete pages locally; merge PDFs with preserved independent
  fonts/forms/bookmarks; add or place images with visible aspect locking and mixed Undo.

- Export PNG/JPEG pages at chosen DPI or as ZIP; split PDFs; compress losslessly by
  default or explicitly reduce supported images with exact preview; flatten supported
  appearances; export text/Markdown/HTML through one shared block/index model.

Evidence: `phases/04-web-tier-walking-skeleton-hardening/04-VERIFICATION.md` and
`phases/05-find-and-replace-across-all-pages/05-G4-RESULTS.md`.
Source font-size shrink/equal and bounded character spacing are now supported;
height growth and arbitrary source reflow remain explicitly unsupported.

### Active

- [ ] Open a PDF in the browser and see its pages rendered faithfully
- [ ] Edit text on a single page directly (select a text run, change it)
- [x] Insert a blank page at any position (local Phase 6)
- [x] Merge another PDF into the document (local Phase 6)
- [x] Merge an image into the document, as a new page or placed on an existing page (local Phase 6)
- [x] Reorder, rotate, and delete pages (local Phase 6)
- [ ] Apply a font from a bundled open-license set to edited text, subset and embedded on save
- [ ] Apply basic formatting to edited text — size, weight, style, color
- [ ] Classify every page and every text run for editability *before* the user types — scanned,
      OCR'd scan, vector-outlined text, unwritable font — name the reason in plain language, and
      keep every other operation available on pages that can't be edited
- [x] Export to PDF variants — flatten, compress, split (local Phase 7)
- [ ] Export PDF/A (implemented and validated locally; hosted G7a CI pending)
- [x] Export pages as images (PNG/JPEG) at a chosen DPI (local Phase 7)
- [x] Export to HTML, plain text, and Markdown (local Phase 7)
- [x] Export to DOCX after document-specific review (local Phase 8; see Constraints)
- [ ] Verify production ephemerality: memory-only evictable source cache, per-operation tmpfs
      scratch cleanup, browser-held original recovery, and no queue/object store or content logs

### Out of Scope

- **Full text reflow / word-processor editing** — rewrapping paragraphs across lines and pages
  requires reconstructing a document model from absolute glyph positions. It breaks on tables,
  columns, and forms, and is an Acrobat-scale problem. Content-stream editing was chosen
  deliberately instead.
- **White-box overlay editing** — covering old text with a rectangle and drawing over it. Simpler,
  but produces visible artifacts on non-white and textured backgrounds, and is exactly the
  low-quality result this project exists to avoid.
- **OCR of scanned pages** — deferred to v2. OCR'd text has no original content stream to rewrite,
  so it needs a separate overlay-editing path through the engine, not a free addition. The v1
  refusal screen names a specific external OCR route and offers a one-click "tell me when OCR
  ships" — the cheapest available signal on whether v2 OCR is worth building at all.
- **User accounts, saved documents, edit history** — v1 is anonymous. Accounts are an entire phase
  of work before anyone can edit a single PDF, and nothing in the core value needs them.
- **User-uploaded fonts** — embedding a user's own font file into an exported PDF is
  redistribution, which many commercial font licenses forbid. Bundled open-license fonts sidestep
  the question entirely.
- **Collaborative / multi-user editing** — no accounts means no collaboration; not part of the
  problem being solved.
- **Digital signatures, form filling, redaction certification** — separate problem domains with
  their own correctness and legal requirements.

## Context

**The problem that sparked this:** existing tools are frustrating. Acrobat is expensive. The free
web tools are ad-ridden and upload your documents to strangers with unclear retention. Neither is
trustworthy for documents that actually matter — contracts, invoices, letters.

**Why "edit existing content" is the hard part:** a PDF does not store paragraphs. It stores
instructions of the form "draw glyph 0x41 at x=72.4 y=690.1 using font F3, an embedded subset."
There is no text box, no line wrap, no paragraph object. Replacing a word means locating the
text-showing operators, decoding the font's encoding to know which glyph is which character,
substituting the new glyphs, and fixing the advance widths so surrounding text does not shift.
Every other feature in the requirements list is straightforward by comparison.

**The font layer is load-bearing.** Embedded fonts in real PDFs are usually *subsets* — they
contain only the glyphs the document actually used. Typing a character that was never in the
original document means the glyph does not exist in the embedded font, and a new font must be
subset and embedded to render it. This is not an edge case; it is the common case.

**Privacy is a designed feature, not an afterthought.** Part of the reason for building this is
that free web tools take your files. Hybrid processing means the server does touch the document
for text edits and format conversion. That trade is acceptable only if the handling is ephemeral,
deletion is immediate and verifiable, and the policy is stated plainly in the product.

## Constraints

- **Architecture**: Hybrid client/server — light operations (page insert, reorder, rotate, merge,
  preview) run in the browser for instant feedback; heavy operations (content-stream text rewrite,
  font subsetting, format conversion) run on the server. Two code paths is the accepted cost of
  a responsive UI without shipping the whole engine as multi-megabyte WASM.
- **Editing fidelity**: Content-stream editing only. No white-box overlays. No reflow across
  lines or pages — replaced text occupies the original text run's space.
- **Fonts**: Bundled open-license families only (Liberation, Noto, Source, DejaVu or similar),
  subset and embedded on save. Fixed set means fixed metrics to test against.
- **Privacy**: Ephemerality is a *structural property*, not a retention policy — "the server has no
  state whose loss is observable," testable by killing the cache mid-session and having the session
  survive. Client holds the authoritative bytes; the server cache is content-addressed and evictable
  at any moment; scratch is tmpfs; queues carry opaque handles, never document bytes; no document
  content in logs or error reports. The novel user-facing claim is **per-operation local/server
  disclosure** — the UI shows which actions stay in the browser and which don't. Deletion windows are
  table stakes (every competitor claims 1–2 hours) and privacy reviewers discount them.
  **Never claim** "files never leave your device," "we never see your file," or "deleted immediately"
  without stating the mechanism. The first is false for the text engine and is the claim users check.
- **Licensing**: No AGPL anywhere in the runtime dependency tree, *including transitively* — CI must
  fail on AGPL in the resolved lockfile, not top-level metadata. Rules out PyMuPDF, mupdf.js, and
  Ghostscript. GPL/LGPL permitted only as a subprocess with a file-in/file-out interface (GPL
  triggers on distribution, and a hosted service distributes nothing) — this keeps Poppler and
  veraPDF available. AGPL permitted only in CI and dev tooling no served request can reach.
  Known trap: `pdf2docx` is MIT at the top level and pulls `PyMuPDF>=1.26.7` transitively.
- **Auth**: No accounts in v1. Anyone can open the site and edit a file.
- **DOCX fidelity**: Best-effort, explicitly not pixel-faithful. Producing a Word document requires
  inferring paragraphs, tables, and styles from absolute glyph positions — the same reflow problem
  ruled out of scope above. Complex layouts will degrade. Sequenced last so it cannot block
  anything that matters.
- **Tech stack**: Resolved by research. Python 3.13 engine — `pikepdf` 10.11.0 (MPL-2.0, object layer
  and content-stream rewrite), `playa-pdf` 1.1.0 (MIT, encoding decode and glyph geometry),
  `fontTools` 4.63.0 + `uharfbuzz` (MIT, subsetting and shaped advances), `pypdfium2` (BSD/Apache,
  rasterization). FastAPI service, React/Vite SPA, `@cantoo/pdf-lib` (maintained fork — upstream
  `pdf-lib` last published 2021-11-06) + `pdfjs-dist` on the client. No single permissive library
  does both halves of content-stream editing; the one that does is AGPL. `playa-pdf` is the
  least-corroborated choice and sits on the critical path — validated in Phase 0, with
  `pdfminer.six` as the drop-in fallback.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Content-stream editing over overlay or full reflow | Overlay leaves visible artifacts on non-white backgrounds — the exact low-quality result this project exists to avoid. Full reflow is Acrobat-scale and breaks complex layouts. Content-stream is the quality-per-effort sweet spot. | — Pending |
| Web app, not desktop | Reach and zero install. Cost is the privacy story, addressed by the ephemeral-processing constraint. | — Pending |
| Hybrid client/server processing | Fully client-side WASM caps file size and constrains font subsetting; fully server-side makes every interaction a round trip. Hybrid gets responsive page ops and a capable engine. | — Pending |
| Bundled open-license fonts only | Avoids font-licensing exposure from embedding user-uploaded fonts, and gives a fixed set of metrics to test against. | — Pending |
| Uneditable content detected per page *and* per run; the **operation** is refused, never the document | A 40-page contract with 3 scanned pages must stay fully editable on the other 37 and page-op-able on all 40. Blanket rejection loses the user permanently. Four buckets — scan, OCR'd scan, vector-outlined text, unwritable font — via three signals: visible glyph count, image coverage, invisible:visible ratio. | ✓ Good |
| Refusal UX is the substitute for a white-box fallback | Overlay always works and every competitor has it — Sejda officially recommends it. The moment it exists it becomes the fallback for every hard case, the quality claim silently dies, and users can't tell which mode ran. Permanent anti-feature. | ✓ Good |
| Anonymous v1, no accounts | Nothing in the core value requires identity. Accounts would be a full phase of work before a single PDF could be edited. | — Pending |
| DOCX export kept, sequenced last, generated as **direct OOXML from the text model** — not LibreOffice, not `pdf2docx` | `pdf2docx` is out on licensing (AGPL transitively). LibreOffice imports PDF through Draw, producing disconnected text frames rather than paragraphs, and brings profile locking, no timeout, memory leaks, zombie processes, and a large native attack surface that fights the sandboxing posture. It buys almost nothing, because the fidelity ceiling is set by our own layout inference either way. Optimize for editability, not fidelity. | ✓ Good |
| Text addressing: the **server owns the addresses** | pdf.js `TextItem` has no operator index, byte offset, or object number, and its reconstruction is lossy in documented ways. pikepdf has addresses but no reliable Unicode. Client has Unicode without addresses; server has addresses without Unicode. Reconciling them after the fact is a fuzzy join on the critical path — works on 90% of PDFs and silently corrupts the rest. One walker, two modes (index / rewrite), same traversal so they cannot drift. | ✓ Good |
| Replace and font subsetting ship in the **same phase** | Embedded fonts are subsets, so typing a character the document never used is the common case, not an edge case. Replace without subsetting *is* PDF-XChange's shipped limitation, which the market already has and nobody likes. | ✓ Good |
| Stack resolved by research | Confirmed no permissive library does both halves; the one that does is AGPL. See Constraints. | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-12 after project research (see `.planning/research/SUMMARY.md`)*
