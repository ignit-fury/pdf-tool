# Pitfalls Research

**Domain:** Browser-based PDF editor with content-stream text editing (hybrid client/server, anonymous, ephemeral)
**Researched:** 2026-08-11
**Confidence:** HIGH on PDF/font internals (spec + errata + library source + renderer bug trackers). MEDIUM on CVE specifics sourced from aggregators (flagged inline). MEDIUM on privacy-leak specifics (one verified public incident, rest is mechanism-level reasoning).

---

## Phase Labels Used In This Document

The roadmap does not exist yet, so pitfalls map to logical phases. Suggested names:

| Label | Scope |
|-------|-------|
| **P0 Conformance Harness** | Corpus + multi-renderer diff + structural validators. Cross-cutting, build first. |
| **P1 Ingest & Render** | Parse, render faithfully, hostile-input hardening, resource caps. |
| **P2 Text Model** | Content-stream interpretation, run reconstruction, editability classification, scanned/OCR detection. |
| **P3 Rewrite Engine** | Find-and-replace, single-run edit, width correction, stream serialization. |
| **P4 Font Pipeline** | Encoding resolution, glyph availability, subsetting, embedding, fallback. |
| **P5 Page Ops** | Insert / merge / reorder / rotate / image placement. |
| **P6 Export** | PDF variants, images, HTML/TXT/MD. |
| **P7 DOCX** | Best-effort Word export. Last. |
| **PX Privacy & Infra** | Ephemeral handling, deletion, caching, logging, error reporting. Cross-cutting. |

**P0 is the single highest-leverage recommendation in this document.** Almost every pitfall below is undetectable without it, and most of them are silent — they produce output that opens without error and is wrong.

---

## Critical Pitfalls

### Pitfall 1: Treating ToUnicode as the encoding

**What goes wrong:**
The team builds "which byte do I write to draw the letter 'e'?" by inverting the font's `/ToUnicode` CMap. Replacement text renders as the wrong glyphs, as `.notdef` boxes, or as nothing — while text extraction still reports the intended string, so unit tests pass and only visual inspection catches it.

**Why it happens:**
Both maps take a character code as input, so they look interchangeable. They are not. They run in different directions for different consumers:

| Map | Direction | Consumer | Effect on rendering |
|-----|-----------|----------|---------------------|
| `/Encoding` (simple) or the CMap named by `/Encoding` (Type0) | code → glyph name / CID → GID | **Rasterizer** | Decides which glyph is drawn |
| `/ToUnicode` | code → Unicode string | **Text extraction, copy/paste, search, accessibility** | **None whatsoever** |

`/ToUnicode` is optional advisory metadata. A PDF with no `/ToUnicode` renders identically to one with a completely fabricated `/ToUnicode`. Inverting it is unsound for three independent reasons:

1. **It is not injective.** A ligature code maps to `"ffi"` (three characters, one code). Multiple distinct codes routinely map to the same Unicode value (Firefox bug 1810914 documents printing that emits ligature characters into `ToUnicode`). Inverting a many-to-one map gives you an arbitrary pick.
2. **It is frequently absent or wrong.** Generators emit broken `ToUnicode` constantly; nothing at render time validates it, so nobody notices.
3. **It is overridable.** `/ActualText` on a marked-content span (`/Span <</ActualText (...)>> BDC ... EMC`) overrides `ToUnicode` for extraction — verified in pdf.js issue #12237, which is open specifically because pdf.js does *not* honour it. So extraction-facing text and the code stream can disagree by design.

**How to avoid:**
- Build the **forward** map (code → glyph) from the `/Encoding` chain. That is the only map that decides pixels.
- Use `/ToUnicode` for exactly two things: displaying text to the user, and matching search terms. Never for producing output bytes.
- To write a character into an *existing* font, invert the **forward** map, and accept the result only when (a) the mapping is injective for that character, and (b) the glyph is verified present in the embedded font program. Otherwise re-encode the whole run into a bundled font (Pitfall 5).
- Keep the two maps in separate types in the code so they cannot be passed to the wrong function. `Code -> GlyphId` and `Code -> str` should not be interchangeable dicts.

**Warning signs:**
- Any line resembling `unicode_to_code = {v: k for k, v in tounicode.items()}`.
- A function named `char_to_code` that takes a font and a string and never touches `/Encoding`, `/Differences`, or the font program.
- Tests that assert on extracted text after an edit but never on a rendered image.
- Ligatures (fi, ffl) in the source document producing garbage on edit.

**Phase to address:** P2 (build forward map), P4 (writing path). Type separation should be a P2 design decision, not a P4 retrofit.

---

### Pitfall 2: Assuming one encoding resolution rule for simple fonts

**What goes wrong:**
Glyph lookup works for the first fifty test PDFs, then a document renders as boxes in Acrobat while looking perfect in the browser, or vice versa. Wingdings/Symbol/icon-font content silently becomes wrong glyphs.

**Why it happens:**
"Simple font" (Type1, TrueType, Type3 — one byte per code, 0–255) hides at least five different resolution paths, selected by the `Symbolic` flag in `/FontDescriptor /Flags`, the presence of `/Encoding`, and which `cmap` subtables the embedded font happens to carry:

- **Type1 / CFF:** code → **glyph name** via `/Encoding` (`/BaseEncoding` overlaid with `/Differences`), falling back to the font program's *built-in* encoding. Then name → glyph via the CFF charset. Glyph names are the currency, not code points.
- **TrueType, non-symbolic:** code → glyph name (as above) → Unicode for that name → `(3,1)` Microsoft Unicode cmap. Or `(1,0)` Mac Roman cmap using the code directly. Viewers disagree on ordering.
- **TrueType, symbolic:** the PDF spec direction is that `/Encoding` is ignored; look up the code in the `(3,0)` symbol cmap, commonly with a `0xF000` bias applied, or in `(1,0)`. Real files set `Symbolic` *and* supply `/Encoding`, which the spec does not cleanly resolve.
- **Fonts with multiple conflicting cmaps** (a format-0 Apple Roman plus a format-4 Unicode) resolve differently per viewer.
- **Type3:** glyphs are content-stream procedures in `/CharProcs`, indexed by glyph *name* from `/Encoding`. Widths are in glyph space and must be scaled by `/FontMatrix`, not divided by 1000.

pdf.js PR #6425 ("Only choose a (3,1) cmap table for TrueType fonts that have an encoding specified") and pdf.js issue #14117 (`/Encoding` prevents rendering in pdf.js but works in Ghostscript, Chrome, and Acrobat) are the same class of disagreement, in the wild, unresolved.

**How to avoid:**
- Implement the resolution chain explicitly as a documented decision table, not as a chain of `if` statements grown by bug reports. Record *which branch fired* on every font, and surface that in a debug view.
- **Do not attempt to write new codes into a symbolic font.** Ever. Classify symbolic simple fonts as "read-only run" and force the bundled-font path for any edit touching them.
- Verify glyph presence by loading the embedded font program and querying it, not by trusting the PDF's dictionaries.
- When the branch is ambiguous, prefer refusing the edit over guessing. A clear "this text can't be edited in place" is a far cheaper support outcome than a corrupted invoice.

**Warning signs:**
- Encoding logic with no reference to `/Flags` bit 3 (Symbolic).
- No unit test containing a symbolic font.
- Bug reports of the form "letters are shifted by one" (an off-by-one in `/Differences` array parsing — the array is `[code name name name code name ...]`, mixing integers and names, and a naive pair-wise parse gets it wrong).

**Phase to address:** P2 for classification, P4 for the write path. Symbolic-font refusal is a P2 gate.

---

### Pitfall 3: Treating Type0/CID font codes as characters

**What goes wrong:**
Editing Type0 text writes single bytes into a two-byte codespace. Every byte after the edit re-pairs, and the remainder of the string becomes unrelated glyphs. Or widths come out wrong because the code reads `/Widths` (which does not exist on a Type0 font).

**Why it happens:**
Type0 is a different data model wearing the same operators:

- The code is defined by the **CMap's codespace ranges** — 1, 2, 3, or 4 bytes, and *mixed widths within one string are legal*. `Identity-H` is uniformly 2-byte, which is why "assume 2 bytes" survives testing and then fails on a real Japanese or Korean document.
- code → **CID** via the CMap. `Identity-H` means CID == code; a named CMap (`UniJIS-UCS2-H`, etc.) does not.
- CID → **GID** via `/CIDToGIDMap`, which is `/Identity` **or a binary stream** of 2-byte GIDs indexed by CID. Skipping the stream case gives correct-looking output on most files and garbage on the rest.
- Widths come from `/W` (a nested run-length array: `[c [w w w] cfirst clast w ...]`) with `/DW` default **1000**, not from `/Widths`/`/MissingWidth`.
- `Tw` (word spacing) applies only to the **single-byte** code 32. It does nothing on `Identity-H` text — verified against the spec text and PDF::Builder's documentation of exactly this. Code that "fixes spacing with Tw" works on simple fonts and silently no-ops on CID fonts.
- For CFF-based CIDFonts (`FontFile3`, `/Subtype /CIDFontType0C`), CID→GID goes through the CFF charset, not `/CIDToGIDMap`.

**How to avoid:**
- Decode strings through a real codespace-range matcher. Do not hardcode 2.
- **Always emit hex strings `<00480065>` for edited runs, never literal strings `(He)`.** This removes escaping (`\(`, `\)`, `\\`, balanced-paren rules, raw newlines in literals) as a corruption source and makes byte-width errors visible as odd-length hex.
- Assert on write: for a uniform *n*-byte codespace, `len(bytes) % n == 0`.
- Route width lookups through one function per font type. Do not let a `/Widths` lookup ever see a Type0 font.

**Warning signs:**
- `struct.unpack('>H', ...)` over a whole string with no codespace check.
- `/CIDToGIDMap` referenced only in an equality check against `/Identity`.
- Any spacing correction implemented via `Tw`.

**Phase to address:** P2 (decode), P3 (encode + assertions), P4 (widths).

---

### Pitfall 4: Believing the embedded font contains the glyph you need

**What goes wrong:**
User replaces "Invoice" with "Facture" and the "ç"-class characters render as blank or `.notdef` boxes. Or the edit works on the developer's synthetic test file (generated from a full font) and fails on every real document.

**Why it happens:**
Real embedded fonts are **subsets**. The `ABCDEF+Helvetica` prefix marks it. The subset contains only glyphs the original document used — often 40–80 glyphs out of thousands. The project brief already names this, and it is correct to call it the common case, not an edge case. Two extra traps beyond "the glyph is missing":

- Subsetters frequently **renumber GIDs** to be dense, so the GID for a given character in `ABCDEF+Arial` bears no relation to the GID in real Arial. You cannot patch in a glyph from the full font by ID.
- Two different documents can both embed `ABCDEF+Arial` with **different glyph sets and different GID assignments**. Deduplicating fonts by `/BaseFont` name during a merge silently corrupts one of the two documents. Some PDF optimizers do exactly this.

**How to avoid:**
- Run a **glyph-availability check before accepting the edit**, per character, against the parsed font program (not the PDF dictionaries). Return one of three states to the UI: `keep-original-font`, `substitute-bundled-font`, `refuse`.
- Make the bundled-font substitution path the *default assumption*, not the fallback. Design it first (P4), because it will fire most of the time. `keep-original-font` is the optimization.
- When substituting, re-encode the **entire visual run**, not just the changed characters. Half a word in Helvetica-subset and half in Liberation Sans is worse than the whole word in Liberation Sans.
- Never dedupe fonts by `/BaseFont`. Dedupe by hash of the embedded font stream bytes, if at all.
- Assign a **fresh 6-uppercase-letter subset tag** on every re-subset. Reusing the inherited tag with a changed glyph set makes downstream dedup logic wrong.

**Warning signs:**
- Test corpus generated by your own PDF writer rather than harvested from real-world documents.
- No code path that decides between "reuse font" and "embed new font".
- Merge code that compares font names.

**Phase to address:** P4, but the three-state classification must exist in P2 so the UI can grey out uneditable runs before the user types.

---

### Pitfall 5: Naive replacement wrecks advance widths and shifts the rest of the line

**What goes wrong:**
Replaced text overlaps the following word, or leaves a visible gap. On justified or right-aligned text, the whole line drifts. On a table, cells collide. The PDF opens fine everywhere — it is just wrong.

**Why it happens:**
Advance is computed by the *viewer* from the PDF's own metrics, and there are several inputs the naive path ignores:

- For simple fonts, width comes from **`/Widths[code − FirstChar] / 1000`**, from the font *dictionary*, not the font program. If the code falls outside `FirstChar..LastChar`, the viewer uses `/MissingWidth` from `/FontDescriptor`, **whose default is 0** (verified against the spec). A code outside the range therefore advances zero and every subsequent glyph on the line stacks at the same x. This is the single most spectacular naive-replacement failure and it is one line of missing bounds-checking.
- PDF-based ISO standards require `/Widths` and the embedded program's metrics to agree within 1/1000 unit. Subsetting or swapping the font program without rewriting `/Widths` violates this and produces PDF/A validation failures plus ambiguous layout.
- The full displacement formula is `tx = (w0 − Tj/1000 × Tfs + Tc + Tw) × Th`. Both `Tc` (per-glyph) and `Tz` (`Th`, horizontal scaling) are in play. **Changing the number of glyphs changes total `Tc` contribution**, so a same-width-glyph replacement of different length still shifts the line.
- Type3 widths are in glyph space and must be transformed by `/FontMatrix`. A Type3 font on a 0.1×0.1 em box with a huge `Tfs` breaks the "divide by 1000" assumption completely.

**How to avoid:**
- Implement advance computation **once**, matching the formula above, and use the same function for measurement and for verification.
- Enforce a hard invariant on every edit: **the text matrix after the edited run is bit-identical (within epsilon) to what it was before the edit.** Any subsequent content on the line then cannot move. This is mechanically testable and should be an assertion, not a review item.
- Absorb the width delta explicitly, in priority order:
  1. Adjust the trailing `TJ` kern number to make the run's total advance equal the original. Cheapest, invisible, always correct for the *following* content.
  2. If the delta exceeds what looks natural (roughly one space width), distribute across inter-word kerns in the run.
  3. `Tz` horizontal scale as a last resort — visible as distorted glyphs above about ±3%.
  4. Refuse, with a clear message, if the run must grow and there is content immediately after it on the same baseline.
- Handle the `TJ` sign convention correctly: the number is **subtracted** from the position, so **positive tightens (moves left), negative widens**. Getting this backwards doubles the error instead of cancelling it.
- Rewrite `/Widths` (or `/W`) whenever the font program changes, and validate the 1/1000 consistency rule.
- Detect line alignment from the *block*, not the run. A run that is the last on a left-aligned line can grow; the same run in a centered or right-aligned block must be repositioned via `Td`/`Tm` instead.

**Warning signs:**
- Replacement text longer than the original never triggers a different code path.
- No `MissingWidth` / out-of-range handling anywhere.
- Visual test corpus has no justified text, no tables, and no right-aligned numbers. Invoices are all three.

**Phase to address:** P3 (correction + invariant), P4 (`/Widths` rewrite). The invariant assertion belongs in P3's definition of done.

---

### Pitfall 6: Assuming the sentence exists as a string in the content stream

**What goes wrong:**
Find-and-replace misses most matches. The matches it does find are partial. Replacing across a match boundary corrupts kerning or produces duplicated fragments.

**Why it happens:**
Nothing in PDF stores a sentence. Producers emit whatever was convenient:

- `TJ` interleaves strings with kerning numbers: `[(Inv) -12 (oice) 30 ( ) -8 (Total)] TJ`. A `sed`-style search for "Invoice" finds nothing.
- A single word may be split across several `Tj` operators, or several `BT`/`ET` blocks.
- Some producers (LaTeX, CAD exports, certain print drivers) draw **one glyph per operator** with an explicit `Td`/`Tm` before each. There is no run at all in the file — only in the pixels.
- Visual order ≠ stream order. Producers emit by font, by colour, or by layer. Two-column pages commonly emit both columns interleaved.
- Text also lives outside `/Contents`: inside **Form XObjects** (`Do`), inside **annotation appearance streams** (`/Annots` → `/AP` → `/N`), inside **tiling patterns**, and inside **Type3 `/CharProcs`**. A find-and-replace that walks only `/Contents` misses form-field values and stamps entirely.
- Some of that text is **not visible**: text render mode `Tr 3` (invisible), text clipped away, or text in a hidden optional-content group (`/OCG` off in the default configuration).

**How to avoid — the correct reconstruction algorithm:**

1. **Interpret, don't tokenize.** Run a full graphics + text state machine over the concatenated page content, recursing into Form XObjects invoked by `Do` (with a visited set and a depth cap — see Pitfall 12), composing the CTM.
2. Track the complete text state: `Tf`, `Tfs`, `Tc`, `Tw`, `Tz`, `TL`, `Ts`, `Tr`, `Tm`, `Td`, `TD`, `T*`, `'`, `"`.
3. For each text-showing operator, decode the string into **codes** via the font's codespace, and emit one record per glyph carrying both semantics and **provenance**:
   `{ code, glyph, unicode?, x, y, advance, font, render_mode, visible, stream_id, operator_index, item_index_within_TJ, byte_offset_within_string }`.
4. **Cluster into visual runs** by (same font, size, colour, render mode) + (baseline within tolerance) + (gap between glyph *n*'s advance-end and glyph *n+1*'s origin below a threshold). Insert a **synthetic space** when the gap exceeds a fraction of the font's space width. This is where `wordsruntogether` and `s p a c e d o u t` extraction bugs come from — the threshold is the whole game and needs a corpus to tune.
5. **Match on reconstructed run text, edit via provenance.** The matched span maps back to a set of (stream, operator, item, byte-range) tuples. Rewrite exactly those.
6. Do not attempt global reading order for find-and-replace. Match within a run; extend across runs only when they share a baseline and are adjacent. Full reading-order inference is the reflow problem the project explicitly ruled out — it belongs only in P6/P7 export, where wrong order degrades output rather than corrupting a document.
7. Use `/ActualText` for the text *shown to the user*, but **never as an edit target** — an `/ActualText` span can cover glyphs you cannot individually address.
8. Exclude invisible and hidden text from edit targeting; surface it separately (see Pitfall 7).

**Warning signs:**
- Any regex applied to decompressed content stream bytes.
- Extraction that works on Word-generated PDFs and produces run-together words on InDesign or LaTeX output.
- No provenance in the text model — text extracted as a plain string with no way back to the operator that produced it. This is the architectural fork: retrofitting provenance later means rewriting P2 and P3.

**Phase to address:** P2. This is the load-bearing phase; everything downstream is a consumer of this model.

---

### Pitfall 7: Invisible OCR text defeats scanned-PDF detection

**What goes wrong:**
The user uploads a scanned contract that was OCR'd (by a scanner, by Acrobat, by a previous tool). It **has** a text layer, so "does this page have text?" returns yes, and the tool offers editing. The user edits, saves, and the visible page is completely unchanged — because the text they edited is `Tr 3` invisible text pinned over a raster image. This is precisely the "edit for ten minutes and save nothing" outcome the project set out to prevent, and the naive detection check walks straight into it.

**Why it happens:**
OCR output is conventionally drawn in text render mode 3 (invisible), positioned to align with the raster underneath so that selection and search work. It is real text with real fonts and real `ToUnicode`. Every "is this a scan?" heuristic based on text presence classifies it as born-digital.

**How to avoid:**
- Classify per page on three signals, not one:
  1. **Visible** glyph count (render mode ≠ 3 and ≠ 7, not clipped away, not in a disabled OCG).
  2. **Image coverage** — fraction of the crop box covered by drawn image XObjects.
  3. Ratio of invisible to visible glyphs.
  A page with high image coverage and near-zero *visible* glyphs is a scan, whether or not it carries an OCR layer.
- Communicate the OCR case specifically. "This page is a scanned image with a searchable text layer. The text can be searched but not edited, because it isn't what's actually printed on the page." That is a different message from "this page has no text" and it is the message that avoids the support ticket.
- Report per page and per document. Mixed documents (born-digital body, scanned exhibit appended) are extremely common in the contract/invoice space this product targets, and blanket refusal of a 40-page document because page 39 is a scan is its own bad outcome.
- Note the inverse false positive: a page that is genuinely born-digital but whose text is a **vector outline** (text converted to paths, common in design exports) has zero glyphs and low image coverage. It is not a scan, it is also not editable. Third bucket.

**Warning signs:**
- Detection implemented as `len(page.extract_text()) > N`.
- No `Tr` tracking in the text state machine.
- No test file that is an OCR'd scan. Generate one with `ocrmypdf` and put it in the corpus on day one.

**Phase to address:** P2. This is a gate for the whole editing flow and must exist before P3 ships anything user-visible.

---

### Pitfall 8: Content-stream rewriting produces files that open but are subtly corrupt

**What goes wrong:**
Output opens in the developer's viewer. Somewhere else it shows a blank page, drops content after a certain point, or throws a repair prompt.

**Why it happens — the specific hazards:**

- **`/Contents` is an array.** Multiple streams concatenate *with whitespace inserted between them* to form one logical stream. The spec says the split may occur only at token boundaries, but real files split mid-token and real implementations concatenate without whitespace — qpdf issue #444 documents a tokenizer producing `q403` from a `q` stream followed by a `403 0 0 ...` stream. If you parse each element separately you get different (and wrong) tokens than if you concatenate.
- **Inline images.** `BI ... ID <raw binary> EI` embeds arbitrary bytes directly in the content stream. A naive tokenizer runs straight into the binary and the rest of the page becomes noise. The binary can legitimately contain the sequence `EI`, so "scan to EI" is not sufficient — you need the length implied by `/W /H /BPC /CS` or a heuristic with validation. pypdf has shipped multiple CVEs on this exact parser (see Pitfall 12).
- **`/Resources` is an inheritable attribute.** A page may have no `/Resources` of its own and inherit from an ancestor `/Pages` node. Two failure modes: (a) reading `/Resources` off the page and treating absence as an error; (b) *writing* a new font into the inherited dictionary, which is shared, thereby altering every other page under that node. The pikepdf/PDFNet guidance is explicit that assigning a fresh empty `/Resources` to a page to "fix" this silently corrupts the document by orphaning its real resources. Same inheritance applies to `/MediaBox`, `/CropBox`, `/Rotate`.
- **Shared Form XObjects.** A header drawn via a Form XObject referenced from every page: editing it edits all pages. Copy-on-write before modifying any object with a refcount above one.
- **Filters.** Streams may be `FlateDecode`, `LZWDecode`, `ASCII85Decode`, `RunLengthDecode`, or a *chain* of them, with `/DecodeParms` (PNG predictors) that must round-trip. Re-encoding without preserving or correctly regenerating `/DecodeParms` produces garbage.
- **Object streams and xref streams.** Modern PDFs pack objects into `/ObjStm` compressed object streams with an xref *stream* rather than a table. Hand-writing an xref offset is a byte-count exercise that fails on the first mistake, silently, and only in strict viewers.
- **Full rewrite vs incremental update.** A full rewrite (what qpdf/pikepdf do by default) **invalidates any existing digital signature**, because the signed byte ranges change. Signatures are out of scope for creation, but signed input documents are not — users sign contracts. Detect `/AcroForm /SigFlags` or `/Sig` fields and warn before saving. Also relevant: `qpdf --qdf` drops previous incremental update generations (qpdf issue #22), which discards prior document revisions the user may consider part of the file.
- **Malformed-but-tolerated input.** Files with broken xref tables, wrong `/Length`, or missing `endobj` render fine in tolerant viewers because those viewers *silently rebuild*. If your library also rebuilds, your rewrite "fixes" the file into a structurally different document than the one the user saw. Not always wrong — but it means round-trip byte comparison is not a valid correctness test.

**How to avoid:**
- Use a battle-tested object layer (qpdf/pikepdf class) for structure, xref, object streams, and filters. **Do not hand-serialize PDF structure.** The lazy path here is also the correct one.
- Parse content streams with a real content-stream parser that understands inline images (pikepdf's `parse_content_stream` / `unparse_content_stream`, or an equivalent), and always coalesce `/Contents` arrays before parsing. pikepdf's own docs warn that content streams are stateful and that the robust approach is parse → edit structured representation → re-serialize, rather than append/prepend.
- Copy-on-write for any shared or inherited object. Write a `resolve_and_own(page, '/Resources')` helper and route every mutation through it.
- Generate unique resource names (`/GSD_F1`) when adding to a resource dictionary; never assume `/F1` is free.
- On save, run `qpdf --check` (or equivalent structural validation) in CI on every corpus file.

**Warning signs:**
- Byte-offset arithmetic anywhere in the save path.
- `page['/Resources']` accessed directly without an inheritance walk.
- No inline-image test file.
- Test corpus that is all single-stream `/Contents`.

**Phase to address:** P1 (parser choice, coalescing, inheritance helper), P3 (rewrite + serialization), P0 (structural validation in CI).

---

### Pitfall 9: "It works in the viewer I tested"

**What goes wrong:**
Everything looks right in-browser. Users report boxes in Acrobat, missing text in Preview, or a blank page when printed via a Ghostscript-based print pipeline. Each report arrives weeks apart and each one requires re-deriving the same font-encoding reasoning from scratch.

**Why it happens:**
Every renderer implements a different, undocumented recovery strategy for the same malformed input. This is not a bug in any one of them — it is the state of the ecosystem. pdf.js issue #14117 is literally titled "`/Encoding` prevents characters in a specific font from rendering but they do in ghostscript, chrome, and acrobat." Chrome uses PDFium; Firefox uses pdf.js; Safari/Preview uses CoreGraphics; Acrobat uses its own; most Linux viewers use Poppler; server-side print/convert pipelines use Ghostscript or MuPDF. Six independent implementations, six tolerance profiles.

Compounding it: the tool's *own* preview will most likely be pdf.js, which is one of the more permissive and the one whose font handling diverges most visibly. **The tool's preview is the least representative renderer in the set.** Shipping to a green preview is shipping untested.

**How to avoid — build P0 before P3:**
- **Corpus.** 100–300 real-world PDFs harvested from the wild, not generated. Must include: subset fonts, Type0/`Identity-H`, symbolic fonts, Type3, CID-keyed CFF, `/Contents` arrays, inline images, Form XObjects, annotation appearance streams, justified and right-aligned text, tables, OCR'd scans, vector-outlined text, encrypted files, and structurally malformed files. Government forms, bank statements, and LaTeX papers each contribute distinct pathologies. Real invoices and contracts — the actual target documents — most of all.
- **Multi-renderer reference rasterization.** Render every corpus file before and after every edit with **at least three independent engines** — pdfium, Poppler, and MuPDF or Ghostscript — and diff the images. Mozilla ships `pdf.js.comparator` for exactly this (compares against cairo/poppler, splash, pdfium, mupdf, PDFBox, Ghostscript, Xpdf, with six diff algorithms). SPARCLUR does the same across Ghostscript, MuPDF, PDFium, PDFMiner, Poppler, QPDF, and Xpdf. Do not write this from scratch.
- **The right assertion is a differential one.** For a text edit, the diff between before-image and after-image should be confined to the bounding box of the edited run — everywhere else must be pixel-identical. That catches width drift (Pitfall 5), shared-XObject bleed (Pitfall 8), and resource-dict corruption in one check. It is also robust to renderer-to-renderer differences, which absolute image comparison is not.
- **Structural validation** alongside rendering: `qpdf --check`, and veraPDF if PDF/A export is in scope (it is, per requirements).
- Add every user-reported bad file to the corpus. Permanently.

**Warning signs:**
- CI renders with one engine.
- "Verified by opening the output" appears in a phase's definition of done.
- No before/after image diff.

**Phase to address:** **P0, and it must precede P3.** The engine is unverifiable without it, and retrofitting a corpus after the rewrite engine exists means every past release is unvalidated.

---

### Pitfall 10: Font subsetting and merging errors

**What goes wrong:**
Subsetting on save drops glyphs that other parts of the document still use → boxes appear in text nobody edited. Merged documents lose text. Output fails PDF/A validation.

**Why it happens:**
- **Subsetting closure.** The subset must contain the union of glyphs used by *every* run that references that font, not just the edited run. A per-edit subset that ignores the rest of the document is the classic version of this. Subsetters also need closure over composite glyph components and OpenType layout substitutions — fontTools does this automatically, but it can go wrong: fontTools issue #193 documents `--layout-features=["*"]` **dropping the `kern` table**, and a fixed COLR bug where subsetting retained layer records pointing at removed glyphs, producing a font that fails to compile.
- **Merging name collisions.** Page A's `/F1` and Page B's `/F1` are unrelated fonts. Merging without namespacing resource dictionaries silently swaps fonts. Worse, two documents can both embed `ABCDEF+Arial` with different glyph sets and different GID assignments — deduping by `/BaseFont` corrupts one of them (Pitfall 4).
- **Merged-font validity.** fontTools issue #444 documents `pyftmerge` output failing OTS with "Layout tags not alphabetical, cmap missing subtables." Merged fonts are not automatically valid fonts.
- **`/Widths` must be regenerated** after subsetting to stay consistent with the new program (Pitfall 5).
- **Licensing (`fsType`).** Every OpenType font carries a 16-bit `fsType` in the `OS/2` table declaring embedding permission: Installable / Editable / Preview-and-Print / Restricted, plus modifier bits for no-subsetting and bitmap-only. This is a declaration, not enforcement — nothing stops you technically. Two consequences: (a) the bundled-fonts-only constraint already resolves the legal exposure, so this is *not* a blocker for this project; (b) **check the bundled fonts' actual `fsType` values anyway** — the field is frequently wrong even on permissively licensed fonts (an OFL font shipping `Restricted` is a known and common metadata error), and downstream tools or corporate preflight *do* read it. The license text governs legally; the bit governs what other software does. Verify both, and consider normalizing `fsType` on your bundled copies to match the actual license.

**How to avoid:**
- Subset **once, at save, against the whole-document glyph usage set** collected from the final text model. Never per-edit.
- Use fontTools (`pyftsubset` / the `subset` module) rather than hand-rolling. Pin the version — subsetting behaviour changes across releases.
- Validate every produced font with an independent sanitizer (OTS) before embedding.
- Namespace resource names on merge; never dedupe by font name; dedupe only by content hash.
- Fresh subset tag on every re-subset.
- Regenerate `/Widths` / `/W` from the final program and assert the 1/1000 consistency rule.

**Warning signs:**
- Subsetting invoked inside the edit path rather than the save path.
- No OTS/validator step.
- Merge tests that use two copies of the same source document (which cannot expose name collisions).

**Phase to address:** P4 (subset/embed), P5 (merge namespacing). Validation hook in P0.

---

### Pitfall 11: Under-defending against hostile PDFs on a public, anonymous endpoint

**What goes wrong:**
An anonymous, no-signup upload endpoint that parses arbitrary PDFs is an unauthenticated remote parser exposed to the internet. Outcomes range from a worker pegged at 100% CPU to heap corruption in a native library.

**Why it happens:**
PDF is a container format with a graph object model, arbitrary compression, embedded programs, and thirty years of ambiguous spec. The parsers are large C/C++ codebases or permissive Python ones. **The CVE stream is continuous, not occasional** — which is the actionable point. No library choice makes this go away.

**Concrete attack shapes, with verified references:**

| Shape | Mechanism | Reference | Confidence |
|-------|-----------|-----------|------------|
| **Malicious `/FontMatrix` → JS execution in the browser** | `/FontMatrix [1 2 3 4 5 (0\); alert\('x')]` — pdf.js compiled glyph paths into a JS `Function` body by string concatenation, so a string in the matrix array executed in the hosting origin. | CVE-2024-4367, fixed pdf.js 4.2.67 | **HIGH** (Mozilla advisory GHSA-wgrm-67xf-hhpq + Codean Labs writeup) |
| **Integer overflow → heap OOB write** | Image `/Width` `/Height` `/BitsPerComponent` validated against `SIZE_MAX` instead of `INT_MAX`; stride calculation overflows; undersized allocation then written past. `pdf_load_image_imp`. | CVE-2026-3308, MuPDF ≤ 1.27.0 | **HIGH** (CERT/CC VU#951662) |
| **Cyclic xref `/Prev` → infinite loop** | Circular previous-xref pointers; parser loops forever. | CVE-2026-27628 (pypdf) | MEDIUM (aggregator) |
| **Unterminated inline image → CPU exhaustion** | `BI ... ID` with no `EI`, using ASCII85/ASCIIHex; 100% CPU. | CVE-2026-59935 / CVE-2026-59936 (pypdf, fixed 6.14.2) | MEDIUM (aggregator) |
| **Predictor parameter bomb** | `FlateDecode` with PNG predictor and absurd `/Columns` `/Colors` `/BitsPerComponent` → huge allocation or infinite loop. | CVE-2026-41312 (pypdf) | MEDIUM (aggregator) |
| **Self-referencing Form XObject** | `Do` recursion with no visited set; memory grows per iteration to gigabytes in seconds. | CVE-2026-48155 (pypdf); same shape as MuPDF 1.12.0 recursive `/ObjStm` and xpdf `AcroForm::scanField` recursion | MEDIUM |
| **Text-extraction loop** | Crafted file causes layout-mode extraction to loop with no exit. | CVE-2026-54530 (pypdf) | MEDIUM (aggregator) |
| **Lexer loop** | Comment not followed by a character → infinite loop. | CVE-2023-36464 (pypdf/PyPDF2) | MEDIUM |
| **Ghostscript memory corruption** | Buffer overflow in PDF XRef stream handling; OOB data access → arbitrary code execution. | CVE-2024-46952, CVE-2024-46956; CVE-2025-59798 (`pdf_write_cmap`) | MEDIUM (advisories/aggregators) |
| **Decompression bomb** | Nested Flate streams; small file, gigabytes decompressed. Classic zip-bomb shape applied to `/Length1`-free streams. | General | HIGH (mechanism) |
| **Cyclic page tree** | `/Pages /Kids` referencing an ancestor → infinite recursion on page enumeration. | General, documented | HIGH (mechanism) |
| **Deeply nested arrays/dicts** | Stack overflow in recursive-descent object parsers. | General | HIGH (mechanism) |
| **Encryption** | `/Encrypt` present. Beyond handling: PDFex (Müller et al., CCS 2019, "Practical Decryption exFiltration") showed encrypted PDFs can be manipulated to exfiltrate plaintext on open. Owner-password-only ("permissions") encryption is trivially strippable and is not access control. | pdf-insecurity.org | HIGH (peer-reviewed) |
| **Active content** | `/OpenAction /JavaScript`, `/AA` additional actions, `/Launch`, `/EmbeddedFile`, XFA, `/URI`. Harmless to your parser; dangerous to whoever opens the output. | General | HIGH |
| **External references** | `/Ref` reference XObjects and `/GoToR` point at external files/URLs. A renderer that resolves them is an SSRF primitive. | General | MEDIUM |

**How to avoid:**
- **Process isolation is non-negotiable.** Every parse of untrusted input runs in a short-lived subprocess (or gVisor/Firecracker/container) with: `RLIMIT_AS` memory cap, hard wall-clock timeout, no network egress, read-only filesystem except one scratch dir, non-root, seccomp profile. Assume the parser will be exploited eventually; design so that it does not matter. This single control neutralizes most of the table above regardless of library.
- **Cap before parse, not during.** Max upload size, max page count, max object count, max stream decompressed size (stream-limited decompression, abort at N×), max recursion depth, max total decode time.
- **Visited sets and depth caps on every graph traversal** — page tree, XObject `Do`, `/ObjStm`, `/Parent` chains, annotation `/AP` chains, outline trees.
- **Client-side pdf.js hardening.** The browser preview is an attack surface too: pin a current pdf.js, set `isEvalSupported: false`, serve the viewer under a strict CSP forbidding `eval`/`Function`, and consider a separate sandboxed origin for rendering so a pdf.js escape lands nowhere useful.
- **Encryption policy up front.** Decide and implement in P1: user-password files → prompt or refuse; owner-password-only files → decide deliberately whether stripping permissions is a feature you want to offer (technically trivial, and a support/abuse question, not an engineering one).
- **Neutralize active content on output.** Strip `/OpenAction`, `/AA`, `/JavaScript`, `/Launch`, `/EmbeddedFile`, XFA from saved documents unless deliberately preserved. Otherwise the tool becomes a malware laundering service that returns a "cleaned by <product>" file.
- **Subscribe to advisories for every PDF library in the dependency tree** and treat updates as security patches, not maintenance. Automate.

**Warning signs:**
- Parsing in the web request process.
- No timeout on the parse call.
- Dependency pinning with no upgrade cadence.
- `isEvalSupported` left at default.

**Phase to address:** P1 for caps, isolation, encryption policy. PX for the sandbox and advisory process. **Isolation must land before public launch, not after.**

---

### Pitfall 12: Privacy leaks that are invisible until they aren't

**What goes wrong:**
The product's core differentiator is "unlike the free tools, we don't keep your file." One counterexample destroys it permanently. The leaks are almost never "we forgot to delete" — they are byproducts of infrastructure the team did not think of as storage.

**Where documents actually leak, in rough order of likelihood:**

1. **CDN caching by file extension.** Cloudflare's default cacheable-extension list **includes `.pdf`** (alongside `.doc`, `.docx`, `.zip`, `.jpg`, `.png`). A download route ending in `.pdf` is cached at the edge by default with no configuration and no warning. GrowthBook issue #5669 is a verified public instance of exactly this class — a CDN caching a response purely because the path ended in a file extension. **Mitigation:** `Cache-Control: no-store, private` on every document route; an explicit Cache Rule set to bypass; and do not put user filenames or document extensions in URL paths.
2. **Temp files from subprocess tools.** Ghostscript, LibreOffice, ImageMagick, and font tools all write intermediates to `/tmp`. On crash or timeout they do not clean up — and crash/timeout is the *normal* path for hostile input. LibreOffice specifically is documented to leave zombie processes and to enter recovery mode on next start after a crash, meaning it also persists crashed-document state. **Mitigation:** per-job scratch directory (`tempfile.TemporaryDirectory` or a tmpfs mount) removed in a `finally`, plus a container that is destroyed per job, plus a sweeper for the case where both fail. Ephemeral in-memory (tmpfs) scratch means a container kill is a guaranteed delete.
3. **Job queues.** Putting the document bytes (or an object-store key with a long-lived credential) into a Redis/SQS/Celery payload persists it in the broker, in the broker's AOF/RDB snapshot, in dead-letter queues, and in failed-job retention. Dead-letter queues in particular hold exactly the documents that triggered errors — the ones most likely to be examined by a human. **Mitigation:** queue an opaque short-TTL handle, never content; disable result backends that persist payloads; set DLQ retention to zero or omit DLQs entirely.
4. **Error reporting.** Sentry-class tools capture local variables in stack frames. A frame holding `content_stream_bytes` or `replacement_text` ships document content to a third party. Sentry's own docs note that logging integrations pick up prior log statements as breadcrumbs and that attachments commonly carry PII. **Mitigation:** `before_send` that strips frame locals wholesale for the PDF engine modules, no attachments, no request bodies, and — the actually reliable control — never put document bytes or extracted text into exception messages or log statements in the first place. Test this by triggering a real crash and reading the resulting event.
5. **Logs.** Filenames are content. `invoice_acme_termination_final.pdf` in an access log is a disclosure. Log a job ID; never the filename, never extracted text, never a document hash that could confirm possession.
6. **Object storage.** If uploads land in S3/R2/GCS, lifecycle rules are the *backstop*, not the mechanism — minimum granularity is one day. Delete explicitly. Also: **versioning must be off** (deleting a versioned object leaves a delete marker over retained content), and access logging must not record object keys derived from filenames.
7. **Browser-side.** Service Worker caches, IndexedDB used for client-side page ops, `blob:` URLs left alive, and the browser's own HTTP cache. A shared or kiosk machine leaks the previous user's document. **Mitigation:** explicit teardown on navigation away, `no-store` on responses, and do not persist to IndexedDB at all unless a feature demands it.
8. **Backups and replicas.** Anything that touches a database with PITR/snapshots outlives "immediate deletion" by the retention window. Documents must never touch a backed-up datastore.
9. **The output document's own metadata.** Do not *add* identifying metadata (`/Producer`, `/Creator`, XMP with timestamps/job IDs) beyond what is needed. Note the inverse: do **not** silently strip the user's existing metadata either — that is data loss, and for some users the metadata is the point.

**How to avoid:**
- Write the claim down as a threat model and enumerate every component the bytes traverse: browser → CDN → LB → app → queue → worker → subprocess → scratch → object store → response → CDN → browser. Each hop gets an explicit "does this retain? for how long? how is it deleted?" answer. This is a one-page artifact and it is the whole defence.
- **Deletion must be verifiable**, because it is a public promise. A retention test that uploads a canary file with a unique byte marker, runs a job, then greps every reachable surface (scratch dirs, queue, logs, object store, error reporter) for that marker. Run it in CI. That converts a marketing claim into an assertion.
- Match the public wording to what actually happens. "Deleted immediately after your download" is defensible; "we never see your file" is not true for the hybrid architecture and will be caught.

**Warning signs:**
- Any `logger.debug(f"...{text}...")` in the engine.
- A download URL containing the original filename or ending in `.pdf`.
- Object storage without an explicit delete call ("lifecycle handles it").
- No canary test.

**Phase to address:** PX, but the **data-flow enumeration belongs in the architecture phase before any infrastructure is chosen**, because the choices (queue with persistent payloads vs. handle-only, object store vs. tmpfs) are hard to reverse. The canary test belongs in P0's CI.

---

### Pitfall 13: DOCX export eats the project

**What goes wrong:**
The last feature on the list becomes the longest phase, generates the most support volume per user, and drags in dependencies that compromise the privacy and security posture built in earlier phases.

**Why it happens:**
PDF→DOCX is not an export. It is **document reconstruction from absolute glyph coordinates** — the same reflow problem the project explicitly ruled out of scope for editing, wearing a different hat. The pipeline needs: word segmentation from glyph gaps → line grouping → paragraph inference from leading and indentation → **reading order** (multi-column, sidebars, footnotes) → table detection from ruling lines *and* from whitespace alignment when there are no rules → list detection → style clustering (which glyph runs are "Heading 2") → image extraction and anchoring → font mapping to fonts Word actually has. Every stage is a heuristic. Every stage has a failure mode that produces a plausible-looking wrong answer.

Then there is the fidelity expectation gap. Users do not perceive DOCX export as a separate lower-fidelity feature. They compare it to Acrobat's, which has had two decades and a machine-learning layout engine, and they file it as a bug in *your PDF editor*, which erodes trust in the core product that works.

Concrete balloon vectors:
- **The obvious implementation is LibreOffice headless**, which brings: one-conversion-at-a-time profile locking (workaround: a separate `-env:UserInstallation` per worker), no built-in timeout so a stuck conversion blocks the queue, multi-second cold start, memory leaks on large conversions (gotenberg issue #407), zombie processes, recovery-mode-on-next-start after a crash, and a large native attack surface with its own CVE history — all documented. It is also, by design, a desktop application. Every one of these interacts badly with the ephemeral-processing and sandboxing constraints from Pitfalls 11 and 12.
- **"Round-trip" expectation.** Users will export to DOCX, edit in Word, and expect to import back. That is a second, larger project.
- **Tables.** Table detection is where every converter visibly fails and where invoices and contracts — this product's exact target documents — live.
- **The scanned/OCR interaction.** No text layer means no output at all; an OCR'd scan produces a garbled Word document. Both need the P2 classification (Pitfall 7) or they become support tickets.

**How to avoid:**
- **Hold the line on "best-effort" and make it visible in the product**, not just in the constraints file. Label it in the UI at the point of export: "Best-effort conversion. Complex layouts, tables, and multi-column pages will need cleanup." Ship a preview of the result before download so expectations reset before the file leaves.
- **Timebox the phase explicitly and define its ceiling in advance.** A defensible v1 ceiling: single-column body text, headings by size clustering, images placed inline, ruled tables only, everything else as plain paragraphs. Write that down as the phase's scope so "improve table detection" is a new decision, not a continuation.
- **Reuse P2's text model.** DOCX export should consume the same positioned-glyph records the editor already builds. If it needs a second extraction pipeline, that is a signal the P2 model is under-specified — fix P2 rather than forking.
- **If LibreOffice is used, treat it as the same class of untrusted-input subprocess as the PDF parsers**: per-job container, dedicated user profile, hard external timeout, killed and recreated per job. Never a long-lived pool.
- **Prefer generating the `.docx` OOXML directly** from the text model (python-docx / raw OOXML) over shelling out to an office suite. It is more code up front, but it eliminates the entire LibreOffice operational and security surface, keeps the conversion in-process and sandboxable, and — crucially — the fidelity ceiling is set by *your* layout inference either way, so the office suite is not buying much.
- Keep it strictly last, and make it independently shippable so it can be cut.

**Warning signs:**
- DOCX work starting before the P2 text model is stable.
- A second text extraction path appearing in the codebase.
- Feature requests being accepted against DOCX before the core edit path has validated with users.
- Any conversation containing "if we just improved table detection a bit."

**Phase to address:** P7, gated on P2 being complete. The scope ceiling should be written into the phase definition before work starts.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Regex over decompressed content streams instead of a real interpreter | Find-and-replace demo in a day | Misses most matches, corrupts inline images and TJ arrays, no provenance for the edit, no path to width correction. Total rewrite of P2 and P3. | **Never.** This is the project. |
| Text model without provenance (extract to plain string) | Simpler extraction, works for search | Cannot map a match back to the operator that produced it. Every downstream feature needs it. Architectural fork. | Never |
| Reusing the original embedded font without a per-character glyph check | Smaller output, no font pipeline needed for the demo | Silent `.notdef` boxes on the common case. Discovered by users, not tests. | Never past prototype |
| Ignoring `MissingWidth` / out-of-range codes | One less branch | Glyphs stack at one x. Spectacular, and user-visible only on some documents. | Never |
| `Tw` for spacing correction | One operator, looks right on the first test file | No-op on all Type0 text. Half the corpus silently unfixed. | Never |
| Assuming 2-byte codes for all Type0 fonts | Works on `Identity-H`, which is most Western documents | Garbage output on CJK and mixed-codespace files. | Acceptable **only** if mixed-codespace fonts are explicitly detected and refused, with an assertion |
| Subsetting per-edit rather than per-save | Faster edit loop | Drops glyphs other runs need → boxes in untouched text | Never |
| Single-renderer verification | Fast CI | Every font-encoding bug ships. Found by users, weeks apart, expensively. | Only before the rewrite engine exists |
| Parsing untrusted PDFs in the request process | No queue, no worker, no isolation | One malicious file takes down the service; one parser CVE is RCE in the app | Local dev only |
| LibreOffice for DOCX | Weeks saved | Operational fragility + large native attack surface + conflicts with sandboxing/ephemerality | Acceptable if fully containerized per job with a hard external timeout, and only if direct OOXML generation was actually evaluated |
| Lifecycle rules instead of explicit deletion | Less code | One-day minimum granularity contradicts "deleted immediately"; a public claim becomes false | Never — keep lifecycle as backstop only |
| Overlay fallback "just for hard cases" | Unblocks tricky documents | Reintroduces the exact artifact the product exists to avoid, and users can't tell which mode ran | Never. Refuse instead — refusal is honest, overlay is a silent quality regression |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| pdf.js (browser preview) | Default `isEvalSupported: true`; stale pinned version | Set `isEvalSupported: false`, strict CSP without `eval`/`Function`, track advisories (CVE-2024-4367 pattern), consider an isolated origin for the viewer |
| pdf.js text layer | Using text-layer DOM positions as edit coordinates | Text layer is an approximation and is documented to misalign (pdf.js #6612, #14205, #9316, Bugzilla 1922063). Derive edit coordinates from the server-side text model and use the text layer only for hit-testing |
| pypdf / pure-Python parsers | Using as the untrusted-input front door | Continuous DoS CVE stream of identical shape (7+ in the past year). If used at all, use behind the isolation boundary, never in-request |
| qpdf / pikepdf | Assuming save preserves the input structure | Full rewrite by default: invalidates signatures, drops prior incremental generations (`--qdf`, qpdf #22), repairs malformed input into a different document. Detect signatures and warn |
| Ghostscript | Used casually for rasterization/PDF-A | Large native attack surface with active CVE history (2024-46952, 2024-46956, 2025-59798). Sandbox exactly like any other untrusted-input parser; no network; hard timeout |
| MuPDF / pdfium | Assumed memory-safe because they are mature | CVE-2026-3308 (MuPDF ≤1.27.0) is a heap OOB write from an ordinary image dictionary. Same isolation rules |
| fontTools | Version-floating; trusting subset output | Pin the version; validate every output font with OTS; watch for layout-feature and table-drop regressions (#193, #444) |
| LibreOffice headless | Shared user profile, long-lived process, no timeout | Per-worker `-env:UserInstallation`, per-job container, hard external timeout, kill-and-recreate. Or skip it — generate OOXML directly |
| CDN (Cloudflare et al.) | Assuming dynamic responses aren't cached | `.pdf` is on the default cacheable-extension list. `Cache-Control: no-store, private` + explicit bypass rule + no extensions in document URLs |
| Object storage | Versioning left on; relying on lifecycle | Versioning off, explicit delete, no access logs keyed on filenames, short-TTL presigned URLs with `no-store` on the issuing response |
| Sentry / error reporting | Default frame-locals capture | `before_send` stripping locals in engine modules; no attachments; never interpolate document content into exception messages. Verify by triggering a real crash |
| Job queue | Document bytes or long-lived credentials in the payload | Opaque short-TTL handle only; no persistent result backend; no dead-letter retention |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full-document text model built eagerly on open | Multi-second wait before the first page renders on large files | Render page 1 immediately; build the text model lazily per page, eagerly only for global find-and-replace, with progress | 100+ page documents, i.e. immediately for real contracts |
| Re-parsing content streams on every keystroke | Editor feels laggy on complex pages | Parse once into the positioned-glyph model, keep it in memory for the session, apply edits to the model and serialize once at save | Pages with heavy vector graphics (maps, charts, CAD) — thousands of operators |
| Re-subsetting the font on every edit | Save takes tens of seconds | Subset once at save from the accumulated glyph set | Any document with more than a handful of edits |
| Shipping the full engine as client WASM | Multi-MB download, memory ceiling in-tab, mobile crashes | Already ruled out by the hybrid constraint — keep it ruled out | Files above ~50MB, or any mobile browser |
| Rasterizing every page for preview at full DPI | Memory blowup on large documents, slow scroll | Render visible pages plus a small window, at device DPI, evict aggressively | 50+ pages |
| Unbounded worker concurrency | Memory exhaustion under trivial load; one big file starves everything | Fixed worker pool, per-job memory cap, queue depth limit with a "busy, try again" response | Any real traffic; a single 200MB PDF is a self-inflicted outage |
| Whole-file upload before any feedback | User waits with no signal on a 100MB file | Stream upload with progress; validate header and page count early and reject before the full transfer | Files above ~20MB on typical connections |
| No timeout on any stage | One pathological file pins a worker forever | Wall-clock timeout at every stage — parse, edit, subset, serialize, convert — enforced externally to the process | First malicious upload, or first legitimate 2000-page file |
| Reference rasterization in the hot path | CI takes an hour | Rasterize only changed corpus files per PR; full sweep nightly | Corpus above ~100 files |

---

## Security Mistakes

Beyond the OWASP baseline. See Pitfall 11 for the full attack table.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Parsing untrusted PDFs in the web request process | One malicious file DoSes the service; one parser CVE becomes RCE in the app | Short-lived isolated subprocess/container, memory + CPU + wall-clock limits, no network egress, non-root, read-only FS |
| No recursion depth cap or visited set on graph traversal | Cyclic page tree / self-referencing XObject / recursive `/ObjStm` exhausts memory in seconds | Visited set + depth cap on **every** traversal: `/Kids`, `Do`, `/ObjStm`, `/Parent`, `/AP`, outlines |
| Unbounded decompression | Small file expands to gigabytes | Stream-limited inflate with an abort threshold; cap ratio and absolute output |
| Trusting `/Length`, `/Width`, `/Height`, `/BitsPerComponent` | Integer overflow → undersized allocation → heap OOB write (CVE-2026-3308 shape) | Validate against `INT_MAX`-scale bounds *before* arithmetic; cap decoded image dimensions; prefer libraries that have fixed this and keep them current |
| Default pdf.js configuration in the viewer | Arbitrary JS in the app origin from a crafted `/FontMatrix` (CVE-2024-4367) | Current pdf.js, `isEvalSupported: false`, CSP without `eval`/`Function`, isolated origin |
| Passing through active content on save | Product becomes a malware laundering service; output "cleaned by <product>" gains false trust | Strip `/OpenAction`, `/AA`, `/JavaScript`, `/Launch`, `/EmbeddedFile`, XFA unless explicitly preserved |
| Resolving external references while rendering | SSRF via `/Ref` reference XObjects and `/GoToR` | Disable external resolution entirely; no network egress from the parse sandbox |
| Treating owner-password ("permissions") encryption as access control | Silently stripping restrictions the user expects to be honoured — or refusing files that are trivially openable | Explicit, documented policy decided in P1. Note PDFex (CCS 2019) demonstrated PDF encryption is broken as a confidentiality mechanism generally |
| Anonymous endpoint with no abuse controls | Free compute for anyone; trivial resource-exhaustion | Per-IP rate limits, size and page caps, proof-of-work or a light challenge if abused. Anonymous ≠ unlimited |
| Serving user documents from the app origin | Stored-XSS-equivalent via HTML/SVG-ish content sniffing | Serve downloads from a separate origin with `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff` |
| Dependency freeze | The PDF-library CVE stream never stops | Automated dependency updates + advisory subscriptions for pdf.js, MuPDF, Ghostscript, qpdf, pypdf/pikepdf, fontTools, LibreOffice |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Letting the user type into text that can't be edited in place | Ten minutes of work, then a failure or a visibly broken save. The single worst outcome for this product. | Classify every run **before** the user clicks: editable-in-original-font / editable-with-substitution / not editable. Grey out and explain the third. |
| One generic "this PDF can't be edited" message | User has no idea whether to try another file, OCR it, or give up | Distinct messages for: scanned (no text), OCR'd scan (invisible text over an image), vector-outlined text, encrypted, symbolic font, malformed |
| Silent font substitution | Replaced text is a visibly different typeface; user believes the tool is broken | Say it: "This document's font doesn't include the characters you typed. Using Liberation Sans." Show a before/after preview. |
| Silent refusal to grow a run | User's longer replacement is truncated or overlaps | Warn at type time when the replacement won't fit, showing the overflow, before saving |
| Trusting the in-app preview as ground truth | Output looks right in the tool and wrong in Acrobat | State that preview is approximate; encourage a download check; internally, never verify against pdf.js alone (Pitfall 9) |
| Global find-and-replace with no review step | Silent unintended replacements in headers, footers, page numbers | Show all matches with page/context and per-match opt-out before applying |
| Hiding which pages were modified | User can't verify a 40-page contract | Post-edit summary: pages changed, replacements made, fonts substituted, runs skipped and why |
| Vague privacy claim | Overclaims ("we never see your file") get caught out and destroy the differentiator | State exactly what happens: what is processed in-browser, what is uploaded, how long it exists, when it is deleted |
| No indication that a page mixes scanned and digital content | Partial edits appear to fail | Per-page badges in the page thumbnail rail |

---

## "Looks Done But Isn't" Checklist

- [ ] **Find-and-replace:** works on `Tj` — verify on `TJ` with kerning, on glyph-at-a-time output, across `BT`/`ET` boundaries, inside Form XObjects, and inside annotation appearance streams.
- [ ] **Text replacement:** looks right in the preview — verify the text matrix after the edited run is unchanged, and that a differential image diff shows changes **only** inside the edited run's bounding box, in three renderers.
- [ ] **Font handling:** works on the test files — verify against a subset font missing the typed character, a symbolic font, a Type0 `Identity-H` font, a CID-keyed CFF font, and a Type3 font.
- [ ] **Width correction:** longer text fits — verify on right-aligned, centered, and justified text, and in a table cell.
- [ ] **Scanned detection:** catches image-only pages — verify it also catches an OCR'd scan (invisible `Tr 3` text over a raster) and does **not** flag a vector-outline page as a scan, and that it reports per page on a mixed document.
- [ ] **Save:** output opens — verify `qpdf --check` passes, veraPDF passes for PDF/A output, and the file opens in Acrobat, Preview, Chrome, Firefox, and Ghostscript.
- [ ] **Font subsetting:** edited text renders — verify untouched text elsewhere in the document using the same font still renders, and the output font passes OTS.
- [ ] **Merge:** pages appear — verify resource names were namespaced and that same-named font subsets from the two sources were not deduplicated.
- [ ] **Resources:** the new font renders — verify no other page changed (inherited/shared `/Resources` was copied, not mutated).
- [ ] **Deletion:** the code calls delete — verify with a canary-marker test that greps scratch dirs, queue, logs, object store, and the error reporter after a completed job **and after a crashed job**.
- [ ] **CDN:** downloads work — verify `CF-Cache-Status` (or equivalent) is `BYPASS`/`DYNAMIC` on document routes, not `HIT`.
- [ ] **Sandbox:** workers are containerized — verify with an actual decompression bomb, a cyclic page tree, and a self-referencing XObject that the job dies on the limit rather than the host.
- [ ] **Encrypted input:** the library opens it — verify explicit behaviour for user-password, owner-password-only, and unsupported crypt filters, each with a distinct user-facing message.
- [ ] **Signed input:** editing works — verify the user is warned that saving invalidates the existing signature.
- [ ] **DOCX:** produces a file — verify on a two-column document, a ruled table, and an unruled table, and confirm the UI sets expectations before download.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| ToUnicode used as encoding | **MEDIUM** if types are separated (fix one function); **HIGH** if the inversion is spread through the codebase | Introduce distinct `Code→Glyph` and `Code→str` types, let the compiler/tests find every misuse, re-verify the whole corpus with image diffs |
| No provenance in the text model | **HIGH** — rewrites P2 and P3 | Rebuild the interpreter to emit per-glyph records; every consumer changes. Avoid by designing provenance in from the start |
| Width drift shipped to users | **MEDIUM** | Add the text-matrix invariant as an assertion, backfill the differential image diff, re-run the corpus. Already-saved user documents cannot be fixed — they're gone (by design) |
| Wrong glyphs shipped (encoding branch bug) | **MEDIUM** | Add the failing file to the corpus, fix the branch, re-run all renderers. Recurring cost is why P0 exists |
| Subsetting dropped glyphs from untouched text | **LOW** | Move subsetting to save time against whole-document usage; re-run corpus |
| Corrupt output from hand-serialization | **HIGH** | Replace hand-serialization with a qpdf-class object layer. Rewrite of the save path |
| Parser DoS in production | **LOW** once isolation exists; **HIGH** if it doesn't | Kill the worker, add the file to the corpus, tighten the cap that failed. If isolation doesn't exist, this is an outage plus an emergency architecture change |
| Parser RCE in production | **CRITICAL** | Isolation is the only thing that makes this survivable. Without it: rebuild hosts, assume all in-flight documents disclosed, disclose publicly |
| Document leaked via CDN cache | **CRITICAL — unrecoverable reputationally** | Purge cache, fix headers, disclose. The privacy promise is the differentiator; this is the one that ends it |
| Temp files accumulating | **LOW** | tmpfs scratch + per-job container teardown + sweeper. Confirm with the canary test |
| DOCX scope creep | **MEDIUM** — sunk time, not broken code | Freeze at the written ceiling, ship, label as best-effort. Prevented cheaply by writing the ceiling down before starting |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. ToUnicode-as-encoding | P2 design, P4 write path | Distinct types in code; rendered-image test replacing a ligature-containing word |
| 2. Simple-font encoding chain | P2 classify, P4 write | Documented decision table; corpus includes symbolic + Type1 + TrueType-with-Differences; per-font branch logged |
| 3. Type0/CID model | P2 decode, P3 encode | Codespace-range decoder; hex-string output; even-length assertion; CJK corpus file renders correctly in 3 engines |
| 4. Subset fonts lack glyphs | P4 (classification surfaced in P2) | Three-state classification exists; test replacing text with a character absent from the embedded subset |
| 5. Advance widths | P3 correction, P4 `/Widths` rewrite | Text-matrix-unchanged assertion; differential image diff confined to the edited run; justified/table corpus files |
| 6. Run reconstruction | **P2** | Extraction correct on glyph-at-a-time and two-column corpus files; provenance round-trips (extract → locate → rewrite → re-extract) |
| 7. Invisible OCR text | **P2** (gates P3) | OCR'd scan in the corpus is classified as "scanned with text layer", not "editable" |
| 8. Content-stream rewrite hazards | P1 parser + inheritance helper, P3 serialization | `qpdf --check` in CI; inline-image and `/Contents`-array corpus files; test that editing a shared Form XObject doesn't alter other pages |
| 9. One-viewer trap | **P0, before P3** | ≥3 independent engines in CI with before/after differential diffs |
| 10. Subsetting & merging | P4 subset, P5 merge | Whole-document glyph closure; OTS validation; merge test with same-named different subsets |
| 11. Hostile input | P1 caps + isolation, PX sandbox | Bomb/cycle/deep-nesting files in the corpus die on limits; parse never runs in-request; advisory automation live |
| 12. Privacy leaks | PX; **data-flow map before infra selection** | Canary-marker retention test in CI, on both success and crash paths; `no-store` verified on document routes |
| 13. DOCX balloon | P7, gated on P2 | Written scope ceiling in the phase definition; reuses P2's text model; independently cuttable |

---

## Sources

**Specification and errata (HIGH confidence)**
- PDF specification errata, clause 09 (Text) — https://pdf-issues.pdfa.org/32000-2-2020/clause09.html — glyph width consistency, `TJ`/`Tj` string rules, `ToUnicode` stream dictionary, `Tm` update rules
- pdf-association/pdf-issues #9 — content stream array elements and token-boundary concatenation
- pdf-association/pdf-issues #130 — "FontWidths must be consistent to within 1/1000 unit"
- PDF Association, "What has PDF 2.0 (not) changed for font encoding?" — https://pdfa.org/wp-content/uploads/2018/06/1530_Seggern.pdf
- PDF Reference / FontDescriptor `MissingWidth` default 0, `Widths` `FirstChar`..`LastChar` semantics

**Renderer disagreement and text-layer issues (HIGH confidence — primary bug trackers)**
- mozilla/pdf.js PR #6425 — "(3,1) cmap only for non-symbolic TrueType fonts with an encoding"
- mozilla/pdf.js issue #14117 — `/Encoding` blocks rendering in pdf.js but works in Ghostscript, Chrome, Acrobat
- mozilla/pdf.js issue #12237 — pdf.js does not honour `/ActualText`
- mozilla/pdf.js issues #6612, #14205, #9316; Bugzilla 1922063 — text layer / canvas misalignment
- Bugzilla 1810914 — ligature characters emitted into `ToUnicode`
- mozilla/pdf.js.comparator — multi-renderer reference comparison (cairo, splash, pdfium, mupdf, PDFBox, Ghostscript, Xpdf)

**Library behaviour (HIGH confidence — official docs and source)**
- pikepdf content streams documentation and `tests/test_parsers.py` — `parse_content_stream` / `unparse_content_stream`, stateful-stream warning (via Context7)
- pikepdf pages documentation — inheritable page attributes
- qpdf issue #444 — concatenated content streams producing merged tokens
- qpdf issue #22 — `--qdf` discards prior incremental updates
- fonttools issue #193 — `layout-features=["*"]` drops `kern`
- fonttools issue #444 — `pyftmerge` output fails OTS
- fontTools subset documentation — glyph closure, table pruning, hinting removal

**Security (mixed confidence — flagged inline)**
- CVE-2024-4367, Mozilla GHSA-wgrm-67xf-hhpq + Codean Labs analysis — `/FontMatrix` string injection into a JS `Function`, fixed pdf.js 4.2.67 (HIGH)
- CVE-2026-3308, CERT/CC VU#951662 — MuPDF ≤1.27.0 `pdf_load_image_imp` integer overflow → heap OOB write (HIGH)
- pypdf DoS series: CVE-2026-27628 (cyclic `/Prev`), CVE-2026-59935/59936 (unterminated inline image), CVE-2026-41312 (predictor parameters), CVE-2026-48155 (self-referencing Form XObject), CVE-2026-54530 (layout-mode extraction), CVE-2023-36464 (comment lexer) — MEDIUM, aggregator-sourced; re-verify against NVD at implementation time
- Ghostscript: CVE-2024-46952 (XRef stream buffer overflow), CVE-2024-46956 (OOB → ACE), CVE-2025-59798 (`pdf_write_cmap`) — MEDIUM
- Müller et al., "Practical Decryption exFiltration: Breaking PDF Encryption", CCS 2019 — https://www.pdf-insecurity.org/download/paper-pdf_encryption-ccs2019.pdf (HIGH)
- Historical recursion DoS: xpdf `AcroForm::scanField`, MuPDF 1.12.0 recursive object streams (MEDIUM)

**Fonts and licensing (MEDIUM–HIGH)**
- PDF Association, "Re-Subsetting Embedded Font Subsets" (403 on direct fetch; referenced via search summary — MEDIUM)
- OS/2 `fsType` embedding permission bits — Apple TrueType Reference Manual, TypeDrawers discussion; note that `fsType` is declarative and frequently contradicts the actual license (MEDIUM)

**Operational and privacy (MEDIUM)**
- Cloudflare default cache behavior documentation — `.pdf` on the default cacheable-extension list
- growthbook/growthbook issue #5669 — CDN caching triggered by path extension on a signed-URL endpoint
- Sentry data-management docs — breadcrumb and attachment PII exposure, `before_send` scrubbing
- gotenberg issue #407 (LibreOffice memory leaks on large conversions), gotenberg issue #94 (LibreOffice concurrency), unoserver — profile locking, no built-in timeout, recovery mode after crash

---
*Pitfalls research for: browser-based PDF content-stream editor*
*Researched: 2026-08-11*
