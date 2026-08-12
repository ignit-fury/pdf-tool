# Feature Research

**Domain:** Browser-based PDF editor with content-stream text editing
**Researched:** 2026-08-11
**Confidence:** MEDIUM-HIGH (competitor behavior verified against vendor docs and support forums; usage-share numbers are vendor self-reported)

---

## The One Finding That Shapes Everything

The market splits cleanly into two camps, and **neither camp does both things**:

| Camp | Who | Does real text editing? | Uploads your file? |
|------|-----|------------------------|-------------------|
| **Text editors** | Acrobat, Foxit, PDF-XChange, Sejda, iLovePDF, Smallpdf Pro, PDFgear desktop | Yes (with heavy caveats) | Yes — all of them |
| **Privacy-first browser tools** | LocalPDF, ClientPDF, DumPDF, gopdf.run, pdfedit.com, PDF24 (annotation only), Stirling (self-host) | **No** — page ops, conversion, OCR, annotation only | No |

Not one product surveyed does content-stream text editing *and* has a credible privacy story. That gap is the product.

**But be honest about the size of the gap.** Privacy reviewers evaluating tools for confidential documents apply a binary test: *does the file leave the device?* Under that test a hybrid architecture lands in the same bucket as iLovePDF, whose 2-hour deletion and ISO 27001 certification reviewers still call insufficient for legal and medical work, because "many law firm engagement letters... explicitly forbid transmission of client documents to third-party processors." The differentiator cannot be "we delete fast" — every competitor already deletes within 1-2 hours. See [Privacy Positioning](#privacy-positioning-what-competitors-actually-claim).

---

## What Competitors Actually Do When They Say "Edit Text"

Verified against vendor documentation and vendor support forums. This is the single most misrepresented capability in the category.

| Product | What "edit text" actually means | Hard limits (verified) |
|---------|--------------------------------|------------------------|
| **Adobe Acrobat Pro** | Real content editing ("touch-up"). Text reflows **inside its own text box only** — never pushes an adjacent box, never flows to the next page. | **The font must be installed on your machine.** Embedded-but-not-installed → you can change only color and size. Neither installed nor embedded → cannot edit at all. Error: *"All or part of the selection has no available system font."* Adobe cites licensing as the reason. **No Replace All** — Find has Whole words / Case sensitive toggles, but you approve every replacement individually. |
| **Foxit PDF Editor** | Real content editing with the most aggressive reflow claims in the category: "text automatically reflows as you type, just like a word processor," plus **Link** (chain text blocks so text flows across blocks and pages) and **Join** (merge blocks into one paragraph). Search & Replace on Ctrl+T, including across multiple files. | Marketing pages state no font or scanned-document limits; treat the reflow claim as best-case on clean documents. |
| **PDF-XChange Editor** | Real content editing — but **you cannot type a character that isn't already somewhere in that text block's embedded font subset.** Font substitution logic is internal and not user-selectable. | This is the subset problem, unsolved, shipped as a limitation. Workaround offered is "Save As Optimized" to merge subsets. **This is the specific competitor weakness this project's font layer beats.** |
| **Sejda (web)** | Real existing-text editing plus **find-and-replace-all across the document** — genuinely rare online. Bold/italic, font size, family, color. | *"Changing existing text within scanned documents is not supported."* Official fallback advice is the **Whiteout tool + Text tool** — i.e. Sejda tells users to do overlay editing when real editing fails. Free tier: 200 pages / 50 MB / **3 tasks per hour**. |
| **iLovePDF** | Recently shipped direct existing-text editing — font type, size, color, formatting, hyperlinks — plus images, bookmarks, form-field creation, attachments. Guidance: use direct editing when "the document design must remain identical" and changes are small. | Publishes **no** stated limits on scanned pages, fonts, or reflow. Third-party reviews contradict the marketing on what the free tier allows. |
| **Smallpdf** | Existing-text editing exists but is **Pro-only** (7-day trial). Free tier is annotate-and-add. | The free "Edit PDF" that most users hit is not a text editor. |
| **PDFgear** | Desktop app edits existing text with formatting preserved. **The online version does not** — text boxes only. | The web/desktop split is the norm, not the exception. |
| **PDF24** | **Annotation only.** Its own docs concede: *"Editing the text in a PDF is not an easy thing to do, because the PDF format is not a good format for editing the page contents."* Recommends PDF → Word → edit → PDF. | The most honest competitor. Also the clearest statement of the problem this product exists to solve. |
| **Stirling PDF** | 50+ tools: merge, split, rotate, convert, OCR, compress, redact, metadata, batch, REST API. **No documented existing-text content editing. No find-and-replace.** | Self-hosted → privacy by architecture, not by promise. Its feature breadth is the benchmark for page ops, not for text. |
| **LibreOffice Draw / Inkscape / Okular** | Draw imports a PDF as **positioned text boxes** — edits work, layout does not survive the round trip. Inkscape is a vector editor. Okular annotates. | The open-source "PDF editor" category does not contain a content-stream text editor. |
| **Local-first cohort** (LocalPDF, ClientPDF, DumPDF, gopdf.run, ihatepdf, pdfedit.com) | Page ops, conversion, compression, in-browser OCR via Tesseract.js. Marketing: *"Files never leave your device," "the architecture makes uploading impossible."* | **None do text editing.** Their ceiling is what pdf-lib + PDF.js can do client-side. |

**The takeaway users never hear:** every tool that "edits text" either requires you to own the font (Acrobat), refuses characters not already in the document (PDF-XChange), paywalls it (Smallpdf), refuses scans (Sejda), or doesn't do it at all (PDF24, Stirling, every privacy-first tool). Acrobat's own community sums it up: *"Acrobat is not a Document Editor. It is not Word."*

---

## Feature Landscape

### Table Stakes (Users Leave If Missing)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Faithful page rendering** | If page 4 looks wrong on screen, nothing else is believed. Trust in the editor is set in the first 3 seconds. | MEDIUM | The whole product's credibility rests here. Annotation/widget rendering is where fidelity usually slips. |
| **Find-and-replace across all pages** | Sejda has it; Acrobat conspicuously *doesn't* (Replace-All is an open, unanswered Acrobat feature request). This is the core value. | **VERY HIGH** | See [detailed expected behavior](#1-find-and-replace-across-all-pages). |
| **Result looks untouched** | The pass/fail test for the entire product. Users compare visually against the original, at 100% zoom, side by side. | Inherent | Any visible seam = the product failed at its one job. |
| **Page ops: reorder, rotate, delete, insert blank** | Universal. Stirling, PDF24, iLovePDF, Sejda, every local-first tool has all four. Absence reads as "toy." | LOW | Client-side; instant feedback expected, no round trip, no spinner. |
| **Merge another PDF** | Second-most-common PDF operation after compression. Table stakes everywhere. | MEDIUM | Correctness traps in [expected behavior](#3-merging-another-pdf). |
| **Merge an image** | Expected in both modes — as a page and placed on a page. Signature/logo/screenshot use cases. | LOW-MEDIUM | Placement UI is most of the cost. |
| **Undo** | Non-negotiable for a destructive batch operation. Users will test undo before they trust replace-all. | MEDIUM | Replace-all must undo as **one** step, not N steps. |
| **Preview before applying a batch replace** | The one operation users won't run blind. Reviewing before committing is explicitly in the Acrobat feature request. | MEDIUM | Match list + context snippet + per-match toggle + count. |
| **Scanned-page detection with a clear message** | The #1 support-volume generator in the category ("why can't I edit this PDF?"). Silent failure is the worst possible outcome. | LOW (given extraction) | See [refusal UX](#5-the-scanned-pdf-expectation-gap). Detection must be **per page** — mixed OCR'd/not-OCR'd documents cause the most confusion. |
| **Export: compress** | Smallpdf's own usage data puts compression as the **most-used** PDF operation (~34%). Higher demand than any conversion. | LOW-MEDIUM | Never downsample images aggressively by default. |
| **Export: split** | Universal in every competitor's tool list. | LOW | |
| **Export: pages as PNG/JPEG at chosen DPI** | Standard. 150 DPI default, 300 for print. | LOW | Renderer already exists for preview. |
| **Export: PDF→DOCX** | ~16% of usage per Smallpdf; the single most-searched conversion. Users will ask for it whether or not it's good. | HIGH | See [DOCX expectations](#6-export-format-expectations). |
| **No signup to use it** | Sejda, iLovePDF, PDF24, Stirling, and every local-first tool are usable anonymously. A signup wall before the first edit is a bounce. | — | Already locked. |
| **A stated file-size / page limit that isn't insulting** | Sejda's **3 tasks per hour** is the most-cited complaint in its reviews. A hard, honest limit beats a hidden throttle. | LOW | State it up front on the upload screen. |

### Differentiators (Real Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Replace-all that actually replaces all** | Acrobat makes you click Replace on every occurrence; the request for Replace-All sits unanswered. Sejda is the only mainstream web tool with it. This is a demonstrable, demoable win over the market leader. | (part of core) | Demo: 40-page contract, one name changed everywhere, 4 seconds. |
| **Type any character, because the font is subset and embedded on save** | PDF-XChange literally cannot type a character absent from the block's subset. Acrobat demands you *own and install* the font. Bundled open-license fonts sidestep both. | HIGH | The most technically defensible advantage. Also the load-bearing dependency for the core value. |
| **Honest, glyph-aware refusal instead of tofu** | No competitor checks glyph coverage before applying. They render a hollow box (.notdef) and let you discover it. Blocking with *"Ċ is not in Liberation Sans — switch to Noto Sans?"* is a quality signal users notice immediately. | MEDIUM | |
| **Named, per-page scanned detection at open time** | Acrobat silently OCRs; Sejda states a flat "not supported"; most free tools do nothing when you click. Naming the exact pages before the user invests time is unclaimed ground. | LOW | Cheapest credibility win in the whole list. |
| **"Which operations touch the server" stated in the UI** | Every competitor states a deletion window. **None** state *which* operations upload. A per-operation indicator (local vs server) is a genuinely novel trust affordance and it's honest about the hybrid architecture instead of hiding it. | LOW-MEDIUM | This, not "deleted in 1 hour," is the defensible privacy claim. |
| **Everything that can run client-side does** | Reorder/rotate/delete/insert/merge/preview never leave the browser. Halves the exposure surface *and* is faster than every server-round-trip competitor. | (architecture) | Already the locked architecture — just make it visible. |
| **Markdown / clean-text export** | Nobody in the consumer category ships Markdown. Near-free once text extraction exists; strong appeal to the developer / LLM-adjacent audience who currently pipe PDFs through scripts. | MEDIUM | Low cost, distinct positioning. |
| **PDF/A export** | Present in Stirling and Acrobat, absent from most free web tools. Compliance/archival users have no free option they trust. | MEDIUM-HIGH | Conformance validation is the hard part, not generation. |
| **No ads, no upsell mid-task** | The stated origin complaint ("ad-ridden"). Restraint is a feature in this category. | — | |

### Anti-Features (Deliberately NOT Built)

| Feature | Why Requested / Surface Appeal | Why Problematic | Alternative |
|---------|-------------------------------|-----------------|-------------|
| **White-box overlay fallback** | Every competitor has it and it *always works*. Sejda officially recommends it when real editing fails. It will be tempting to add as a "just in case" escape hatch. | It is the exact low-quality result this product exists to replace. Visible on non-white and textured backgrounds. The moment it exists, it becomes the fallback for every hard case and the quality claim dies. | Refuse the edit and explain why. A visible refusal is a quality signal; an invisible white box is a bug the user finds later in print. |
| **AI chat / summarize / "ask your PDF"** | The loudest 2026 trend. Every competitor is shipping it. Feels free to add via an API call. | Directly detonates the privacy positioning: it means shipping full document text to a third-party LLM provider, indefinitely, for exactly the confidential documents this product courts. Also a different product. Reviews already note basic chat "doesn't differentiate one tool from another." | Nothing. Say no publicly and make the refusal part of the pitch. |
| **Full text reflow across lines and pages** | The thing users think "PDF editor" means. Foxit markets it hard. | Locked out of scope. Acrobat — with 30 years of investment — reflows *only within one text box* and cannot push text to the next page. Foxit's reflow works on clean documents and degrades on tables/columns/forms. Chasing it is unbounded work. | Occupy the original run's space; show measured overflow before applying; offer bounded condensing (see [font/formatting behavior](#4-font-and-formatting-changes-on-existing-text)). |
| **OCR in v1** | Every competitor has it; Tesseract.js makes in-browser OCR look nearly free. | Locked out. OCR'd text has no original content stream to rewrite — it needs a second, overlay-based editing path through the engine. "Nearly free" is only true for the *recognition* step, not for making the result editable. | Detect, name the pages, offer a concrete external OCR route, capture interest for v2. |
| **PDF→Excel / table extraction** | The #2 conversion request after Word. | Strictly harder than DOCX: requires table structure inference from ruling lines and whitespace, which is the reflow problem with a stricter correctness bar (a wrong cell boundary is a wrong number). | Not in v1. Reconsider only after DOCX proves the layout-inference layer works. |
| **E-signature** | ~19% of usage per Smallpdf's data — genuinely huge demand. | Locked out. Legal/evidentiary domain with its own correctness bar; also forces retention (iLovePDF keeps signed documents **5 years**), which contradicts the ephemeral promise outright. | Not built. The retention conflict is the clean reason to say no. |
| **Form filling** | High demand, adjacent to text editing, seems like a small addition. | Locked out. Widget appearance streams, field validation, and calculation order are a separate subsystem. | Not built — **but merge must not corrupt existing forms.** See [merge behavior](#3-merging-another-pdf). |
| **Redaction** | Looks like a natural fit: content-stream deletion is the *correct* way to redact, and almost every tool does it wrong (draws a black box over recoverable text). Genuinely tempting. | Legal consequences when wrong. Published research shows even correctly-drawn redactions leak via residual glyph *positions*. Shipping "real" redaction invites reliance the product can't yet warrant. | Defer. Flag as the **highest-value v2 differentiator** — the engine is already the right shape for it; what's missing is the verification and the warranty. |
| **Normalizing page sizes on merge, by default** | Mixed A4/Letter output prints awkwardly and looks sloppy in the thumbnail strip. | Silently rescaling someone's contract changes margins, signature-block positions, and stated dimensions. Worse than a mixed-size document. PDF handles mixed MediaBoxes natively and viewers render them fine. | Preserve each page's own MediaBox by default; offer an explicit "Make all pages the same size" like Sejda's. |
| **Cloud storage integrations (Drive / Dropbox / OneDrive)** | Every competitor has them; users ask. | Contradicts the privacy promise: broad OAuth scopes plus copying files *through* the server. Turns "we hold your file for seconds" into "we hold a token to your whole drive." | Local file picker and drag-drop only. Say why. |
| **Password / encryption removal** | Popular free-tool feature; trivially implementable for owner-password cases. | Attracts abuse, generates "it didn't work on my file" support load for user-password cases, and is a bad-faith signal on a product selling document trust. | Not built. Accept encrypted PDFs the user can supply the password for; don't strip. |
| **Accounts, saved documents, edit history, batch queues** | Repeat users will ask for all four. | Locked out. Each requires storing documents — the exact thing the privacy promise forbids. | Session-scoped work only. If a job outlives the tab, it's out of scope. |
| **Aggressive lossy compression by default** | Small numbers look good on a results screen. | Silently degrades scans and photos; users discover it at print time and don't trust the tool afterwards. | Default to lossless structural compression; make image downsampling an explicit, labeled choice with a before/after size *and* preview. |
| **Task-per-hour throttling** | The standard free-tier monetization lever (Sejda: 3/hr). | The most-cited complaint in Sejda reviews, and the exact frustration this project was started over. | A single honest size/page ceiling, stated before upload. No hidden hourly counters. |

---

## Expected Behaviors: The Features In Scope

### 1. Find-and-Replace Across All Pages

**How the market presents it:**
- **Acrobat** — Find panel, three-dot menu exposing **Whole words only** and **Case sensitive**. Steps occurrence by occurrence; **no Replace All exists.** The open feature request asks for exactly: case options, whole-word, *review before replace*, and *undo*.
- **Sejda** — the only mainstream web tool with true bulk: "find and replace **all occurrences** of words in a PDF."
- **Foxit** — Ctrl+T Search & Replace, next-occurrence stepping, plus batch across multiple files.

**Expected behavior, concretely:**

| Case | Expectation | Recommendation |
|------|-------------|----------------|
| **Case** | Default **case-insensitive** matching (Ctrl+F convention). "Match case" as an explicit toggle. | Replacement is **literal** — insert exactly the typed string. Do **not** implement Word-style smart case preservation; it surprises users on acronyms and proper nouns, and a contract edit is not a place for a guess. |
| **Partial words** | Default **substring** matching. "Whole words only" toggle is table stakes — Acrobat has it, and its absence produces the classic "replacing `Ltd` also broke `Ltda`" disaster. | Ship both. Default substring; make whole-word one click away and remember the choice within the session. |
| **Text split across multiple show operators** | Users expect search to work on what they **see**. A word is routinely split across `Tj`/`TJ` boundaries and interrupted by kerning offsets inside a `TJ` array (`[(A) 120 (W) 95 (AY)] TJ`). Kerning-only splits are invisible on screen. | Build the index over the **decoded, concatenated visible text** of the whole page (via `ToUnicode`), collapsing intra-word `TJ` numeric adjustments and normalizing ligatures (`ﬁ`→`fi`). Map each match back to a `(operator index, byte range)` span. A replacement may span several operators — rewrite the whole run as one. **This is where "find" and "replace" stop being the same feature.** |
| **Hyphenation across lines** | Users know PDF search fails on `key-word` split across lines and they hate it — but they also don't expect a tool to silently un-hyphenate their document. | Detect it; do **not** auto-join for replacement. A cross-line match means editing two runs at two different baselines with two independent positioning states, and any success leaves a hole on line 1. Surface it in the match list as **"split across lines — cannot replace automatically,"** with a jump-to-page link. Refusing visibly beats a wrong edit. |
| **Ligatures / non-standard spacing** | `ﬁnal` should match a search for `final`. | Normalize on the index side only; never rewrite untouched ligatures on save. |
| **Preview before apply** | Mandatory for this operation specifically — it's batch and it looks irreversible. Explicitly named in the Acrobat request. | Match list with: page number, ±40 chars of surrounding context with the hit highlighted, per-match checkbox (all on by default), a live count (*"Replace 14 of 17 occurrences across 6 pages"*), click-to-jump. Matches that **cannot** be replaced (missing glyph, split across lines, scanned page) appear in the same list, disabled, **with the reason** — not silently filtered out. Silent filtering is how users discover three missed occurrences after sending the contract. |
| **Undo** | Ctrl+Z reverts the **entire** replace-all as one operation. | Non-negotiable. Fourteen presses of Ctrl+Z to undo one action is a support ticket. |
| **Overflow** | Longer replacements shift or overlap neighboring text. | Measure before applying; show the count of matches that will overflow *in the preview*, before commit. See §4. |

### 2. Insert Blank Page

**What users expect:** the new page is indistinguishable in size and orientation from the page it sits next to. Acrobat's Insert Blank matches the open document's page size; the recurring complaint is against Create-PDF-from-Blank, which hard-defaults to **Letter with no setting to change it**.

**Recommendation:**
- Inherit **MediaBox and rotation from the adjacent page** — the page it's inserted *after*, or the page it's inserted *before* when at position 0. Not the document's first page, not a global default, never Letter.
- **Show what it inherited** in the insertion affordance (`A4 portrait, matching page 7`) — one line, removes all ambiguity.
- Allow override via a size dropdown, but the override is opt-in and never the default.
- Inherit rotation too. Inserting a portrait page into a landscape run is the bug report.

**Complexity:** LOW. Client-side. Depends only on the page model.

### 3. Merging Another PDF

Four correctness traps, all verified as real failures in shipping products:

| Concern | User expectation | Correct behavior |
|---------|-----------------|------------------|
| **Bookmarks / outline** | Preserved, not silently dropped. Acrobat's Combine creates a top-level bookmark per source file with the source's own bookmarks nested beneath — documented as the option that produces the cleanest outline. | Match Acrobat: top-level entry named for the incoming file, original outline nested under it, destinations remapped to the new page indices. If the incoming file has no outline, still create the single top-level entry so the merge is navigable. Dropping the outline entirely is the common free-tool failure. |
| **Form fields** | Fields keep working and stay independent. | **Name collisions are the documented disaster** — very common when both files came from the same template. Acrobat treats same-named fields as one linked field: type in one, the value appears in all of them. Detect collisions and **auto-prefix incoming field names** with the source filename or `Doc2_`, then tell the user it happened. Given form filling is out of scope, the acceptable v1 alternative is to **flatten** incoming fields to page content and say so explicitly — but flattening silently, with no notice, is not acceptable. |
| **Embedded fonts with colliding names** | Invisible. Users have no expectation here — they just expect the text to render. | The failure is severe and silent: subset-tagged names like `ABCDEF+Arial` collide across documents that carry *different* subsets under the same tag. Wrong glyphs render. **Namespace resources per source document; never merge font dictionaries by name.** Deduplicate only on content hash, never on name. This is invisible when correct and catastrophic when wrong. |
| **Page size mismatch** | Split expectation. Screen readers don't care (PDF supports mixed MediaBoxes natively; viewers handle them fine). Printers do — mixed sizes print awkwardly from a single tray. | **Preserve each page's own MediaBox by default.** Offer an explicit "Make all pages the same size" option (Sejda's model: under "More options"). Detect the mismatch and *mention* it once — `Pages 8-12 are Letter; the rest are A4` — without acting on it. |

Also expected: choose the insertion position (not just append), and see the incoming pages in the thumbnail strip before committing.

**Complexity:** MEDIUM. Resource namespacing and outline remapping are the real work; naive page-array concatenation is LOW and wrong.

### 4. Merging an Image

**Both modes are expected — the choice is the feature.**

*As a new page:*
- Fit to page with **aspect ratio preserved**, sensible margins.
- Page size and orientation derived from the image's aspect ratio, or inherited from the neighboring page (offer both; default to matching the neighbor so the document stays consistent).
- Choose insertion position, same as blank page.

*Placed on an existing page:*
- Drag to position; **corner handles resize with aspect ratio locked by default**, Shift (or a lock toggle) to free it. This is the universal convention — pdfFiller, Acrobat, PDF-XChange all use it, and PDF-XChange has a support thread from people who couldn't find it, so **make the lock state visible rather than a hidden modifier key.**
- Edge handles for single-axis stretch, if free-resize is allowed at all.
- Expected extras, in demand order: opacity (for watermarks/signatures), simple rotation, send-behind-text.
- Formats: **PNG and JPEG are mandatory.** Add WebP and HEIC — phone cameras produce them and users will drag them in; a "format not supported" error on a photo from their own phone reads as broken.
- Transparent PNG must composite correctly, not render on a white rectangle. Signature images are the archetypal use case and they are almost always transparent PNGs.

**Complexity:** LOW-MEDIUM. Client-side (pdf-lib-class embedding). The placement UI is most of the cost; the PDF work is small.

### 5. Font and Formatting Changes on Existing Text

**When the chosen font lacks a glyph:**

The industry default is to render `.notdef` — tofu, a hollow rectangle — and let the user find out. Acrobat blocks editing entirely when the font isn't installed. PDF-XChange refuses characters not already in the block's subset.

Correct behavior, and a real differentiator:
1. **Check coverage of the entire replacement string against the target font before applying anything.**
2. On a gap, **block the apply and name the offending characters**: *"Liberation Sans has no glyph for `ł`. Switch to Noto Sans (covers it), or edit the text."* Noto was explicitly designed to eliminate tofu and should be the recommended fallback for anything outside Latin-1.
3. **Never silently substitute a different font for part of a run** — a mid-word font switch is visible and is exactly the "looks edited" artifact the product exists to avoid.
4. **Never emit `.notdef`.** Under no circumstance. Tofu in an exported contract is a total product failure.
5. Given only bundled open-license families, coverage is a **known, testable matrix** — precompute it, don't probe at runtime.

**When the replacement is longer than the space available:**

Reflow is locked out, so the honest ladder, in order:

1. **Measure and disclose first.** Show the overflow in the preview, in the match list, before commit: `"Page 3: 12pt over — will overlap the following text."` Silence here is the single worst failure mode, because it's invisible until print.
2. **Offer bounded condensing.** Horizontal scale (`Tz`) or tracking (`Tc`) down to roughly 90-95% is visually undetectable and absorbs most real-world deltas (`Smith`→`Smithson`). Apply automatically only within a tight, stated bound; beyond it, ask.
3. **Offer a small font-size reduction** as an explicit, labeled second option — more visible than condensing, so it ranks lower.
4. **Let the user proceed with acknowledged overflow.** Sometimes the trailing space is empty and overlap is harmless. The user can see the page; let them decide.
5. **Never silently overlap.** Acrobat forum threads about overlapping text after editing are a standing category. Don't join it.

**When the replacement is shorter:** don't stretch text to fill. Preserve the run's start position and leave the gap. Justified text will show a slightly wide gap — accept it; the alternative is re-justifying the line, which is reflow.

**Formatting expectations** (size, weight, style, color): all four are table stakes because Sejda, iLovePDF, and Acrobat all offer them. Note that Acrobat's *degraded* mode — when the font is embedded but not installed — is **exactly "color and size only."** That the product can do more than Acrobat's degraded mode is a legitimate claim; that it does bold/italic via a real bundled family rather than synthetic emboldening is a quality claim worth protecting.

**Complexity:** MEDIUM, entirely conditional on the font subsetting/embedding layer existing first.

### 6. Export Format Expectations

**What users actually reach for** (Smallpdf's self-reported usage data — vendor source, MEDIUM confidence, and self-selected by their own tool mix):

| Operation | Share | Read |
|-----------|-------|------|
| Compress | ~34% | The most-used PDF operation, period. Higher than any conversion. |
| Convert (all) | ~28% | |
| E-sign | ~19% | Huge, deliberately out of scope. |
| PDF→Word | ~16% | The largest single conversion, by a distance. |

Implication: **compress deserves more polish than its complexity suggests**, and PDF→Word will be asked for constantly regardless of stated fidelity.

| Format | Demand | Tolerance / expectation |
|--------|--------|------------------------|
| **Compress** | Highest | Expect a visible before/after size *and* a preview. Zero tolerance for silent quality loss on scans. |
| **Split** | High | Expect page ranges and "every N pages"; expect the outputs named after the source. |
| **PNG/JPEG at DPI** | Moderate-high | Deck slides, email, chat. Defaults: 150 DPI screen, 300 DPI print. Expect a per-page and an all-pages-as-zip option. |
| **Flatten** | Moderate | Understood as "lock it so nobody can change it" as much as "reduce size." Both framings appear in tool copy. |
| **PDF/A** | Niche but sticky | Compliance/archival users have essentially no free option. Expect a conformance level choice (PDF/A-2b is the common target) and a pass/fail validation result — a PDF/A file that doesn't validate is worse than no feature. |
| **Plain text** | Moderate | Expect reading order to be right. Multi-column is the failure case. |
| **Markdown** | Low general / high for developer audience | Nobody in the consumer category ships it. Near-free once extraction exists. |
| **HTML** | Low | Mostly a stepping stone to DOCX. |
| **DOCX** | Highest single conversion | See below. |

**PDF→DOCX specifically — what quality users tolerate:**

The universal complaint is unambiguous: **"LibreOffice typically imports PDFs as positioned text boxes, which results in poor editability."** Frames and absolutely-positioned boxes preserve *appearance* and destroy *usefulness*, and users would rather have flowing paragraphs that lost exact positioning than a pixel-accurate document they cannot type into. Optimize for editability, not fidelity.

Known breakers, all documented: **tables, headers/footers, multi-column layouts, rotated text, embedded fonts, text boxes and floating graphics** — everything that depends on fixed positioning, which Word must reinterpret as flow.

Tolerance is high **if the expectation is set first.** The best guidance in the space says so directly: *"No converter is perfect for complex layouts. Setting that expectation upfront saves time, because knowing which element will break lets you focus cleanup efforts."*

Therefore: **ship a pre-conversion warning that names what will degrade in *this specific* document** — "3 tables and a 2-column section detected; these usually need cleanup in Word." That single screen converts a bad review into an accurate expectation, and it is cheap because the layout analysis already ran. It is also the only way "best-effort DOCX" survives contact with users.

### 7. The Scanned-PDF Expectation Gap

**How existing tools handle it, worst to best:**

| Approach | Who | Result |
|----------|-----|--------|
| **Silent nothing** | Most free web tools, native mobile viewers | User clicks the text, nothing happens, no explanation. The origin of every *"why can't I edit this PDF?"* thread. Worst possible. |
| **Flat refusal, stated up front** | Sejda: *"Changing existing text within scanned documents is not supported"* | Honest, but only on the marketing page — the user still has to hit the wall themselves, and Sejda's suggested workaround is Whiteout+Text (overlay). |
| **Silent auto-fix** | Acrobat: OCRs automatically on entering Edit mode, current page only, with a corner prompt showing the detected OCR language and a Settings link | The best UX in the market — but it requires OCR, which is v2 here, and the page-at-a-time behavior still confuses people. |

**The confusion multiplier:** hybrid documents — *some* pages OCR'd, some not — are documented as causing the **most** confusion, because search works inconsistently and the user concludes the tool is broken rather than the file. **Detection must be per page, and the result must be shown per page.**

**Good refusal UX for v1:**

1. **Detect at open, before the user invests any time.** The unforgivable failure is ten minutes of editing followed by nothing to save.
2. **Detect per page.** Heuristic: extractable glyph count on the page versus full-page image coverage. Classify each page as *has text* / *image only* / *mixed*.
3. **Mark it visually on the page thumbnails.** A badge in the thumbnail strip is worth more than any dialog, and it survives scrolling.
4. **Say it in user language, naming the pages.** *"Pages 3-7 are scanned images. There's no text on them to find or edit — only a picture of text."* Not "no text layer detected." Not an error code.
5. **Refuse the operation, not the document.** This is the most important rule. The user should still be able to rotate, reorder, delete, merge, export those pages as images, and **fully edit every page that does have text.** A whole-file rejection on a 40-page document with 3 scanned pages is an over-refusal and will lose the user permanently.
6. **Reflect it in the find-and-replace match list.** Scanned pages appear as skipped with the reason attached, so the user never wonders whether a match was missed.
7. **Give a concrete next step.** Name a specific free OCR route (in-browser Tesseract-based tools exist and are free with no page caps) and say "run it there, come back here." Sending the user away to succeed builds more trust than a dead end.
8. **Capture the interest.** A one-click "tell me when OCR ships" is the cheapest signal available on whether v2 OCR is worth building.

**Complexity:** LOW for detection given text extraction exists. The value is almost entirely in the messaging.

---

## Privacy Positioning: What Competitors Actually Claim

| Product | Claim | Reality |
|---------|-------|---------|
| **Sejda** | "Files stay private. Automatically deleted after 2 hours." | Server-side. Timed deletion. |
| **iLovePDF** | Auto-deleted within 2 hours; ISO 27001; GDPR. **Signed documents retained 5 years.** | Server-side. The e-sign carve-out is the interesting detail. |
| **Smallpdf** | Deleted within 1 hour; TLS; ISO/IEC 27001; GDPR. eSign / shared files kept **14 days**. | Server-side, with carve-outs. |
| **PDF24** | "Files are automatically deleted from the PDF24 server after one hour." SSL transfer, **servers in Germany**, no registration. Desktop Creator available for fully local work. | Server-side for web; jurisdiction is used as a trust signal. |
| **Stirling PDF** | Self-hosted: "processed by your own instance, never a third-party service." | Privacy by **architecture**. Requires the user to run infrastructure. |
| **Local-first cohort** (LocalPDF, ClientPDF, DumPDF, gopdf.run, pdfedit.com, ihatepdf) | "Files never leave your device." "No upload needed. Everything runs 100% locally in your browser." "Not because they promise privacy, but because **the architecture makes uploading impossible**." | Genuinely client-side. **None do text editing.** |

**The uncomfortable conclusion:** *"deleted after N hours"* is table stakes, not differentiation — everyone says it, and privacy reviewers now explicitly discount it. The review consensus for confidential work is architectural and binary: *"every file is uploaded to a third-party server, sits there during processing, and is only deleted afterward"* is treated as disqualifying regardless of certifications, because *"many law firm engagement letters... explicitly forbid transmission of client documents to third-party processors."* The recommended default is *"browser-based tools that process files locally remove the upload step that creates the risk in the first place."*

**What a hybrid product can honestly claim, in descending strength:**

1. **"Most operations never leave your browser — and we show you which."** Per-operation local/server indicators in the UI. **No competitor does this.** It converts the hybrid architecture from a weakness to be hidden into a transparency claim nobody else can make, because nobody else can make it without admitting they upload everything.
2. **"Deleted when the response is sent — not in an hour."** Only meaningful if paired with *how*: in-memory only, never written to disk, no logs of document content, process-scoped. Specificity is the whole claim; "deleted immediately" without a mechanism is the same sentence four competitors already print.
3. **"No account, so there's nothing to link a document to."** Anonymity is a genuine privacy property, and the anonymous-v1 decision already delivers it.
4. **"No AI, no analytics on document content, no cloud-storage OAuth."** Each is a named, checkable absence. Absences are more credible than promises.

**Do not claim** "files never leave your device" — it is false for the text engine, it is the one claim in this category users actually check, and one screenshot of a network tab ends the product's credibility permanently.

**Worth stating publicly:** which operations *cannot* be made local and why. The honest framing — "page ops run locally and always will; the text engine needs the server because font subsetting in WASM would mean a multi-megabyte download and a file-size ceiling" — reads as engineering candor to exactly the technical audience most likely to check.

---

## Feature Dependencies

```
PDF parse + faithful render (client)
  │
  ├──> Page model: thumbnails, insert blank, reorder, rotate, delete   [LOW, client]
  │       └──> Merge PDF (resource namespacing, outline remap, form collisions)  [MEDIUM]
  │       └──> Merge image (page mode + placement mode)                          [LOW-MED]
  │       └──> Export: split / flatten / compress                                [LOW-MED]
  │       └──> Export: page images at DPI                                        [LOW]
  │       └──> Export: PDF/A                                                     [MED-HIGH]
  │
  └──> Text extraction with position mapping (decode ToUnicode, map spans back
       to operator + byte range)                                       [HIGH]  ★ keystone
          │
          ├──> Scanned-page detection (per page)                       [LOW]
          │
          ├──> Search index + match list + preview UI                  [MEDIUM]
          │       │
          │       └──> CONTENT-STREAM REWRITE  ══ core value ══        [VERY HIGH]
          │              │   requires, in the same phase, not after:
          │              ├──> Font subsetting + embedding              [HIGH]
          │              │       └──> Font & formatting changes        [MEDIUM]
          │              ├──> Advance-width / overflow measurement     [MEDIUM]
          │              └──> Undo (whole batch as one operation)      [MEDIUM]
          │                     │
          │                     └──> Single-page direct text edit      [MEDIUM]
          │                            (same engine, different UI)
          │
          └──> Export: plain text / Markdown / HTML                    [MEDIUM]
                  └──> Export: DOCX (layout inference on top of HTML)  [HIGH]
                         └──> Pre-conversion degradation warning       [LOW, given analysis]
```

### Dependency Notes

- **Everything downstream of text extraction is blocked by it.** Extraction with accurate span-to-operator mapping is the keystone: find, replace, scanned detection, and all four text-ish exports sit on it. If it slips, five features slip.
- **Font subsetting is NOT downstream of replace — it is a peer, in the same phase.** Embedded fonts in real PDFs are subsets, so typing a character the original document never used is *the common case*. Shipping replace before the font layer produces exactly PDF-XChange's limitation ("you can't type a character that isn't already in this block"), which the market already has and nobody likes. The honest MVP boundary is: replace + subsetting, together, or neither.
- **Find and replace are separate features.** Find needs the visible-text index. Replace needs the *inverse* map back to operator spans plus width recalculation. Estimating them as one item is the most likely source of a blown estimate.
- **Preview-before-apply depends on the match index but not on the rewrite engine** — it can be built and demoed first, and it de-risks the rewrite by making its inputs visible.
- **Undo depends on an operation log in the document model**, which must be designed before the first mutating feature ships. Retrofitting undo across two code paths (client page ops + server text ops) after the fact is significantly harder than designing for it. This is the highest-leverage early architectural decision on this list.
- **DOCX sits on top of the HTML/structure path**, not directly on extraction. Building text → Markdown → HTML first means DOCX inherits a working reading-order and block-structure layer instead of starting from raw glyph positions. Cheapest sequencing by a wide margin.
- **Merge PDF and merge image do not depend on the text engine at all.** Fully parallelizable with the engine work; good candidates for an independent workstream.
- **Scanned detection is nearly free once extraction exists** and blocks nothing — but it gates the *quality* of every text feature's failure mode, so it should land with the first text feature, not after.
- **PDF/A depends on the full save pipeline** (font embedding, color profiles, metadata) — it is effectively last among the exports regardless of demand.

---

## MVP Definition

### Launch With (v1)

- [ ] **Open + render faithfully** — nothing works without it; credibility is set here
- [ ] **Per-page scanned detection with named-page messaging** — cheap, and it prevents the worst possible first experience
- [ ] **Find across all pages with preview + match list** — demoable before replace works; de-risks the rewrite
- [ ] **Replace across all pages, content-stream, with font subsetting + embedding** — the core value; ships as one unit or not at all
- [ ] **Glyph-coverage check with named refusal** — the quality signal that distinguishes it from every competitor
- [ ] **Overflow measurement + bounded condensing + explicit disclosure** — the honest answer to no-reflow
- [ ] **Undo as one operation** — nobody trusts a batch edit without it
- [ ] **Page ops: insert blank (inherits neighbor size/orientation), reorder, rotate, delete** — LOW cost, table stakes
- [ ] **Merge PDF** with outline nesting, form-field collision handling, per-page MediaBox preserved
- [ ] **Merge image** — new page and placed-on-page, aspect locked by default, transparent PNG correct
- [ ] **Export: PDF, compress, split, page images at DPI** — cheap and expected
- [ ] **Per-operation local/server indicator + plain-language privacy statement** — the actual differentiator, and it's mostly copy

### Add After Validation (v1.x)

- [ ] **Single-page direct text edit** — same engine, new UI surface. *Trigger:* replace-all is stable and users ask for one-off tweaks. It is a UI project pretending to be an engine project; don't let it front-run the core.
- [ ] **Font and formatting changes (size, weight, style, color)** — *Trigger:* subsetting layer proven in production. Table stakes competitively, but the core value ships without it.
- [ ] **Export: plain text / Markdown / HTML** — *Trigger:* extraction stable. Cheap; Markdown is unclaimed ground.
- [ ] **Flatten** — *Trigger:* any user asks. LOW cost.
- [ ] **PDF/A** — *Trigger:* a compliance user shows up. Don't build it speculatively; validation is the expensive half.
- [ ] **Export: DOCX with a per-document degradation warning** — *Trigger:* HTML path stable. Correctly sequenced last already.

### Future Consideration (v2+)

- [ ] **OCR + overlay-editing path** — a second engine path, not an addition. Gauge demand with the v1 refusal screen's notify-me before committing.
- [ ] **Real redaction** — the highest-value v2 differentiator. Content-stream deletion is the *correct* way to redact and almost nobody does it right, but it needs a verification story and a warranty before it can ship.
- [ ] **Batch / multi-file processing** — conflicts with anonymous + ephemeral; needs a job model that implies storage.
- [ ] **Accounts** — only if a validated feature genuinely requires identity. Nothing in v1 does.

---

## Feature Prioritization Matrix

| Feature | User Value | Cost | Priority |
|---------|-----------|------|----------|
| Faithful render | HIGH | MEDIUM | P1 |
| Text extraction with span mapping | HIGH (enabling) | HIGH | P1 |
| Replace across all pages (content-stream) | HIGH | VERY HIGH | P1 |
| Font subsetting + embedding | HIGH (enabling) | HIGH | P1 |
| Preview + match list before apply | HIGH | MEDIUM | P1 |
| Undo (batch as one op) | HIGH | MEDIUM | P1 |
| Glyph-coverage check / no tofu | MEDIUM | LOW | P1 (cheap quality signal) |
| Overflow disclosure + bounded condensing | HIGH | MEDIUM | P1 |
| Per-page scanned detection + messaging | HIGH | LOW | P1 |
| Page ops (insert / reorder / rotate / delete) | HIGH | LOW | P1 |
| Merge PDF (done correctly) | HIGH | MEDIUM | P1 |
| Merge image | MEDIUM | LOW-MED | P1 |
| Compress | HIGH (most-used op) | LOW-MED | P1 |
| Split | MEDIUM | LOW | P1 |
| Page images at DPI | MEDIUM | LOW | P1 |
| Per-operation local/server indicator | HIGH (trust) | LOW | P1 |
| Font / formatting changes | MEDIUM | MEDIUM | P2 |
| Single-page direct text edit | MEDIUM | MEDIUM | P2 |
| Text / Markdown / HTML export | MEDIUM | MEDIUM | P2 |
| Flatten | MEDIUM | LOW | P2 |
| DOCX export + degradation warning | HIGH (demand) | HIGH | P2 |
| PDF/A | LOW-MED | MED-HIGH | P3 |
| OCR | HIGH | VERY HIGH | P3 (v2) |
| Redaction | HIGH | HIGH + legal | P3 (v2) |

---

## Competitor Feature Comparison

| Feature | Acrobat | Sejda | iLovePDF | PDF24 | Stirling | Local-first cohort | **This product** |
|---------|---------|-------|----------|-------|----------|--------------------|------------------|
| Edit existing text | Yes, font must be **installed** | Yes | Yes (recent) | **No** | **No** | **No** | Yes, bundled fonts — no install needed |
| Replace **all** occurrences | **No** — one at a time | Yes | Unclear | No | No | No | Yes, with preview + one-step undo |
| Type a character absent from the subset | Blocked if font not installed | Unstated | Unstated | n/a | n/a | n/a | Yes — subset + embed on save |
| Missing-glyph handling | Blocks editing | Unstated | Unstated | n/a | n/a | n/a | Named refusal + font suggestion, never tofu |
| Longer replacement | Reflows in-box, overlaps out-of-box | Unstated | Unstated | n/a | n/a | n/a | Measured + disclosed pre-apply; bounded condensing |
| Scanned handling | **Silent auto-OCR** | Flat refusal in docs | Unstated | n/a | OCR available | Client-side OCR (some) | **Per-page detection, named pages, page ops still work** |
| Overlay/white-box fallback | Available | **Officially recommended** | Available | Only mode | n/a | n/a | **Never** |
| Merge: bookmark nesting | Yes | Yes | Yes | Yes | Yes | Varies | Yes (Acrobat model) |
| Merge: form-field collisions | **Links same-named fields** | Unstated | Unstated | n/a | Unstated | n/a | Auto-prefix + notify |
| Merge: page-size normalization | Optional | Optional ("More options") | Unstated | Unstated | Available | Varies | Optional, off by default |
| Processing location | Desktop | Server | Server | Server | Self-hosted | **Client** | **Hybrid, disclosed per operation** |
| Retention | n/a | 2 hours | 2 hours (5 yrs signed) | 1 hour (DE) | n/a (yours) | none | Response-scoped, in-memory, mechanism stated |
| Free-tier throttle | n/a | **3 tasks/hour** | Yes | Ads | None | None | Size ceiling only, stated up front |
| AI chat / summarize | Yes | No | Growing | No | MCP server | No | **Deliberately never** |

---

## Confidence Notes

| Claim | Confidence | Basis |
|-------|-----------|-------|
| Acrobat requires the font installed to edit; embedded-only → color/size only | **HIGH** | Adobe helpx documentation + Adobe KB error article |
| Acrobat has no Replace All | **HIGH** | Adobe community + open, unanswered Acrobat feature request |
| Acrobat reflows within a text box only, never across pages | **HIGH** | Adobe documentation + AcrobatUsers answers |
| PDF-XChange refuses characters not in the block's subset | **MEDIUM-HIGH** | Vendor forum and KB; not in marketing material |
| Sejda has replace-all, refuses scans, recommends Whiteout | **HIGH** | Sejda's own product page |
| PDF24 "Edit PDF" is annotation only | **HIGH** | PDF24's own tool page, quoted verbatim |
| Smallpdf gates existing-text editing behind Pro | **MEDIUM-HIGH** | Smallpdf product page + support copy |
| PDFgear online cannot edit existing text; desktop can | **MEDIUM** | Multiple secondary sources, consistent; not vendor-confirmed |
| Stirling PDF has no existing-text content editing | **MEDIUM** | Absent from README and feature summaries; absence of evidence, verify against live docs before relying on it competitively |
| iLovePDF's exact current text-editing capability | **LOW-MEDIUM** | Official blog and third-party reviews contradict each other; recently changed. Re-check before any comparative marketing. |
| Merge form-field name collisions link fields in Acrobat | **HIGH** | Adobe community threads + Evermap technical documentation |
| Retention windows (Sejda 2h, iLovePDF 2h, Smallpdf 1h, PDF24 1h) | **HIGH** | Vendor pages |
| Usage shares (compress 34%, convert 28%, e-sign 19%, PDF→Word 16%) | **MEDIUM** | Smallpdf's own statistics page — vendor-reported and self-selected by their tool mix. Directionally useful; do not treat as market truth. |
| Local-first cohort does not do text editing | **MEDIUM-HIGH** | Consistent across six products' own marketing; none claims it |
| DOCX pain points (tables, columns, rotated text, positioned text boxes) | **HIGH** | Multiple independent conversion vendors agree |

---

## Sources

**Vendor documentation (primary):**
- Adobe — [Edit text in PDFs](https://helpx.adobe.com/acrobat/using/edit-text-pdfs1.html), [No available system font error](https://helpx.adobe.com/acrobat/kb/error-no-available-system-font.html), [Edit scanned PDFs](https://helpx.adobe.com/acrobat/desktop/create-documents/scan-documents-to-pdfs/edit-scans.html), [Searching PDFs](https://helpx.adobe.com/acrobat/using/searching-pdfs.html)
- [Sejda PDF Editor](https://www.sejda.com/pdf-editor), [Sejda Merge PDF](https://www.sejda.com/merge-pdf)
- [Foxit advanced editing](https://www.foxit.com/pdf-editor/advanced-editing/), [Foxit Search and Replace](https://help.foxit.com/csh/q/id/Edit_Replace_Replace/version/11.0.0/product/Phantom/language/en-us.html)
- [PDF24 Edit PDF](https://tools.pdf24.org/en/edit-pdf), [PDF24 FAQ](https://tools.pdf24.org/en/faq)
- [Smallpdf Edit PDF](https://smallpdf.com/edit-pdf), [Smallpdf PDF Statistics](https://smallpdf.com/pdf-statistics)
- [iLovePDF advanced editing announcement](https://www.ilovepdf.com/blog/new-advanced-pdf-editing-ilovepdf), [iLovePDF Security](https://www.ilovepdf.com/help/security)
- [Stirling PDF (GitHub)](https://github.com/Stirling-Tools/Stirling-PDF), [Stirling docs](https://docs.stirlingpdf.com/)
- [PDFgear edit existing text](https://www.pdfgear.com/pdf-editor-reader/edit-existing-text-in-pdf.htm)

**Vendor support forums (limitations not in marketing):**
- [Acrobat: Find and Replace All feature request](https://acrobat.uservoice.com/forums/590923-acrobat-for-windows-and-mac/suggestions/49360541--find-and-replace-all-functionality-for-adobe-acr)
- [Acrobat: embedded font not available for editing](https://community.adobe.com/t5/acrobat/embedded-font-not-available-for-editing-pdf-on-pc/m-p/9698072)
- [Acrobat: can I reflow text between pages](https://answers.acrobatusers.com/Can-I-reflow-text-pages-q294800.aspx)
- [Acrobat: duplicated form fields when combining PDFs](https://community.adobe.com/questions-9/text-get-duplicated-on-form-fields-when-combining-pdf-forms-1251992)
- [PDF-XChange: font substitution](https://forum.pdf-xchange.com/viewtopic.php?t=25016), [wrong characters when editing text](https://forum.pdf-xchange.com/viewtopic.php?t=35103), [aspect ratio when resizing images](https://forum.pdf-xchange.com/viewtopic.php?t=41126)
- [Evermap: handling PDF form fields during a document merge](https://evermap.com/Tutorial_ASP_HandlingFormFieldInMerge.asp)

**Technical background:**
- Jay Berkenbilt — [Text in PDF: Fonts and Spacing](https://medium.com/@jberkenbilt/text-in-pdf-fonts-and-spacing-eae6fd8d2b40)
- iText — [Advanced typography in PDF](https://itextpdf.com/sites/default/files/2018-12/PP_Advanced_typography_in_PDF-compressed.pdf)
- [Story Beyond the Eye: Glyph Positions Break PDF Text Redaction (arXiv)](https://arxiv.org/pdf/2206.02285)
- [Notdef glyph / tofu background](https://symbolfyi.com/guides/tofu-missing-glyphs/)

**Privacy / positioning:**
- [Is iLovePDF safe for confidential documents](https://www.gethonestpdf.com/blog/is-ilovepdf-safe-for-confidential-documents), [Is Smallpdf safe](https://www.gethonestpdf.com/blog/is-smallpdf-safe-2026)
- [LocalPDFs](https://localpdfs.com/), [ClientPDF](https://clientpdf.tech/), [LocalPDF](https://local-pdf.com/), [pdfedit.com OCR](https://pdfedit.com/ocr-pdf)
- [Client-side vs server-side PDF privacy](https://dumpdf.com/blog/client-side-vs-server-side-pdf-privacy)
- [Files you should never upload to online tools](https://www.platoforms.com/blog/files-never-upload-online/)

**Conversion quality:**
- [Nutrient: PDF-to-Word conversion guide](https://www.nutrient.io/blog/convert-pdf-to-word/)
- [How to convert PDF to Word without losing formatting](https://pdf.net/blog/how-to-convert-pdf-to-word)
- [Page sizes when combining PDFs](https://combinepdf.com/blog/combine-page-sizes)

---
*Feature research for: browser-based PDF editor with content-stream text editing*
*Researched: 2026-08-11*
