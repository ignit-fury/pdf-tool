# PDF Tool

## What This Is

A browser-based PDF editor that edits the *actual existing content* of a PDF — replacing text
inside the page's content stream rather than pasting annotations or white boxes on top. Users
open a PDF, find-and-replace text across every page, insert blank pages, merge in images or
other PDFs, restyle text with embedded fonts, and export to several formats. It is aimed at
people who need to change a document that already exists and want the result to look untouched.

It is a real product for other people, used anonymously — no signup to edit a file.

## Core Value

**Replace text across every page of an existing PDF and have the output look like nothing
happened.** If everything else on this list fails, this one capability must work.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Open a PDF in the browser and see its pages rendered faithfully
- [ ] Find and replace text across all pages, editing the real content stream
- [ ] Edit text on a single page directly (select a text run, change it)
- [ ] Insert a blank page at any position
- [ ] Merge another PDF into the document
- [ ] Merge an image into the document, as a new page or placed on an existing page
- [ ] Reorder, rotate, and delete pages
- [ ] Apply a font from a bundled open-license set to edited text, subset and embedded on save
- [ ] Apply basic formatting to edited text — size, weight, style, color
- [ ] Detect a scanned page with no text layer and say so clearly instead of failing silently
- [ ] Export to PDF variants — flatten, compress, split, PDF/A
- [ ] Export pages as images (PNG/JPEG) at a chosen DPI
- [ ] Export to HTML, plain text, and Markdown
- [ ] Export to DOCX (best-effort fidelity — see Constraints)
- [ ] Uploaded files are processed ephemerally and deleted immediately after the response

### Out of Scope

- **Full text reflow / word-processor editing** — rewrapping paragraphs across lines and pages
  requires reconstructing a document model from absolute glyph positions. It breaks on tables,
  columns, and forms, and is an Acrobat-scale problem. Content-stream editing was chosen
  deliberately instead.
- **White-box overlay editing** — covering old text with a rectangle and drawing over it. Simpler,
  but produces visible artifacts on non-white and textured backgrounds, and is exactly the
  low-quality result this project exists to avoid.
- **OCR of scanned pages** — deferred to v2. OCR'd text has no original content stream to rewrite,
  so it needs a separate overlay-editing path through the engine, not a free addition.
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
- **Privacy**: Uploaded documents are processed ephemerally and deleted immediately. No retention,
  no analytics on document content. This is a product promise, not just an implementation detail.
- **Auth**: No accounts in v1. Anyone can open the site and edit a file.
- **DOCX fidelity**: Best-effort, explicitly not pixel-faithful. Producing a Word document requires
  inferring paragraphs, tables, and styles from absolute glyph positions — the same reflow problem
  ruled out of scope above. Complex layouts will degrade. Sequenced last so it cannot block
  anything that matters.
- **Tech stack**: To be determined by research. Content-stream editing plus font subsetting points
  toward Python tooling for the engine, but this is to be verified rather than assumed.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Content-stream editing over overlay or full reflow | Overlay leaves visible artifacts on non-white backgrounds — the exact low-quality result this project exists to avoid. Full reflow is Acrobat-scale and breaks complex layouts. Content-stream is the quality-per-effort sweet spot. | — Pending |
| Web app, not desktop | Reach and zero install. Cost is the privacy story, addressed by the ephemeral-processing constraint. | — Pending |
| Hybrid client/server processing | Fully client-side WASM caps file size and constrains font subsetting; fully server-side makes every interaction a round trip. Hybrid gets responsive page ops and a capable engine. | — Pending |
| Bundled open-license fonts only | Avoids font-licensing exposure from embedding user-uploaded fonts, and gives a fixed set of metrics to test against. | — Pending |
| Scanned PDFs detected and refused in v1, OCR in v2 | Detection is nearly free and prevents the worst possible support experience — editing for ten minutes and saving nothing. OCR needs a separate overlay path through the engine. | — Pending |
| Anonymous v1, no accounts | Nothing in the core value requires identity. Accounts would be a full phase of work before a single PDF could be edited. | — Pending |
| DOCX export included but sequenced last | User asked for it explicitly after being told the fidelity risk. Scoped best-effort and placed last so it cannot block the core value. | ⚠️ Revisit |
| Stack chosen by research, not assumed | The engine's viability rests on PDF and font library capability. Worth verifying current tooling rather than defaulting to a familiar language. | — Pending |

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
*Last updated: 2026-08-11 after initialization*
