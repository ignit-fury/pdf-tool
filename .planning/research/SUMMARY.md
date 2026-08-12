# Project Research Summary

**Project:** PDF Tool — browser-based PDF editor with content-stream text editing
**Domain:** Document engineering (PDF internals + font engineering) behind a consumer web app
**Researched:** 2026-08-11
**Confidence:** MEDIUM-HIGH — the parts are well-established, the composition is unproven

## Executive Summary

This is not a web app with a PDF feature. It is a **PDF engine with a web front-end**, and every scheduling decision follows from that. All four research tracks converged on the same shape: a headless Python engine (`pikepdf` for the object layer and content-stream rewrite, `playa-pdf` for encoding decode and glyph geometry, `fontTools` + `uharfbuzz` for subsetting and shaped advances), driven by a **server-issued run index** that the browser can only echo back — never invent. The single library that does all of this in one package is MuPDF/PyMuPDF, and it is AGPL, which triggers on SaaS. That one licensing fact is why three libraries are required instead of one, and it reaches further than expected: `pdf2docx`, the default answer to "PDF to DOCX in Python," is MIT at the top level and pulls `PyMuPDF>=1.26.7` transitively.

The core value — replace text and have the output look untouched — has **no reference implementation to copy**. `pikepdf` gives token-level rewrite but explicitly refuses to decode text; `pdf.js` gives text but no addresses; nothing hands you "fit this string into this run's width." The TJ-refitting algorithm is code this project writes. That means the risk is entirely front-loaded and the build order must be too: a multi-renderer conformance harness and a real-world corpus **before** the rewrite engine, a CLI end-to-end slice **before** any web tier, and font subsetting shipped **in the same phase as replace** rather than after it. The gating milestone is not a demo — it is: *replace a word in a real invoice using a character absent from the embedded font subset, and have the output be pixel-identical outside the edited run in pdfium, Poppler and MuPDF, open without a repair prompt in Acrobat, and copy-paste back the correct Unicode.* If that fails, the product does not exist, and it should fail in week three rather than month four.

The dominant risk is not that something breaks loudly. It is that **output looks fine in the viewer the team tests with and is silently wrong somewhere else** — wrong glyphs from an encoding branch, a line that drifts because `/MissingWidth` defaults to 0, a subset that drops glyphs from text nobody edited. Every one of those opens without an error. That is why the conformance harness is P0 and not a testing chore, and why a *masked* differential image diff (unedited region must be pixel-identical, not merely similar) is the primary correctness assertion for the whole project. The second-order risk is reputational: the privacy claim is the differentiator, and it dies to a CDN that caches `.pdf` by default, a subprocess that leaves temp files on crash, or an error reporter that ships frame locals containing document bytes.

## Convergent Conclusions

Four researchers worked independently. These are the points they reached separately, stated once.

### 1. Text addressing is settled: the server owns the addresses (SETTLED — do not relitigate)

ARCHITECTURE and STACK independently concluded that pdf.js `getTextContent()` items are **rendering groupings, not content-stream runs**, and PITFALLS independently concluded the text model must carry **per-glyph provenance**. Same conclusion from three directions.

The mechanics: `TextItem` carries `{str, dir, transform, width, height, fontName, hasEOL}` — no operator index, no byte offset, no object number — and the reconstruction is lossy in documented ways (overlapping strings merged, pdf.js #7445; font transitions lost from `fontName`, #7297; `fontRef` disagreeing with what rendered, #14755). From the other side, pikepdf's own docs say *"we strongly recommend against trying to scrape text from the content stream"* and *"content streams should be thought of as an output format."* **The client has Unicode without addresses; the server has addresses without Unicode.** Any design that reconciles them after the fact — string-matching or geometry-matching — is a fuzzy join on the critical path of the core value. It works on 90% of PDFs and silently corrupts the rest.

Consequences, all binding:

- **One content-stream walker, two modes.** Index mode emits run records; rewrite mode emits new operators consulting the same IDs it issued. Literally the same traversal function, so index and rewrite cannot drift. Two implementations will, and the drift looks like data corruption.
- **Per-glyph provenance is a P1 design decision, not a P2 retrofit.** Each glyph record carries `{code, glyph, unicode?, x, y, advance, font, render_mode, visible, stream_id, operator_index, item_index_within_TJ, byte_offset_within_string}`. Retrofitting this later rewrites the text model *and* the rewrite engine. PITFALLS names it "the architectural fork."
- **Run IDs address the immutable original bytes**, never the output: `{sourceHash}:p{page}:c{contentStreamPart}:o{operatorOrdinal}[:g{start}-{end}]`. Edits always apply to the original; the output of an edit is never the input to the next edit. Ordinals therefore never drift, undo/redo/reorder fall out free, and page ops never invalidate an override.
- **A fingerprint (`fp = hash(raw glyph bytes + Tm + font ref)`) rides on every override** and is verified before applying. It converts a stale client run map from a corruption class into a `409 STALE_RUN` error class.
- **`/Contents` may be an array**, so the ID needs the stream-part index, and the parts must be **coalesced before parsing** — qpdf #444 documents a tokenizer producing `q403` from a `q` stream followed by a `403 0 0 …` stream.
- **`/ToUnicode` is display and search only.** It never produces output bytes. The forward `/Encoding` chain decides pixels. Keep `Code→Glyph` and `Code→str` as distinct types in code so they cannot be passed to the wrong function.
- **Text lives outside `/Contents`** — Form XObjects, annotation appearance streams, tiling patterns, Type3 `/CharProcs`. Shared Form XObjects are a correctness trap: editing one changes every page that references it. Mark such runs `editable: false` with a reason in v1, or extend the ID with an XObject path.
- **pdf.js is used for pixels only.** Its text layer is permitted for select/copy/browser-find UX and nothing else.
- **There is no `POST /find-replace`.** Find is a client-side query over the cached index that produces N ordinary overrides through the ordinary apply path. A separate bulk endpoint means two rewrite implementations within six months.

### 2. Licensing policy — one rule

**No AGPL anywhere in the runtime dependency tree, including transitively. GPL/LGPL is permitted only as a subprocess with a file-in/file-out interface. AGPL is permitted only in CI and developer tooling that no served request can reach.**

The reasoning, reconciled from ARCHITECTURE (calls AGPL an architectural constraint needing a process boundary) and STACK (identifies the hidden entry point and the GPL counterpoint):

- **AGPL follows you over the network.** Artifex is explicit: making the software available as SaaS counts as conveying it. Commercial licensing reportedly runs $1.5k–$50k+. Out of the runtime: `PyMuPDF`, `mupdf`/`mupdf.js`, **Ghostscript**.
- **GPL triggers on distribution, and a hosted service distributes nothing.** Poppler (`pdftohtml`, GPL) and veraPDF (GPL-3.0/MPL-2.0) are therefore safe as subprocesses. Do not let a blanket "no copyleft" rule cost you those; do not let a loose one cost you the company.
- **The trap is transitive.** `pdf2docx` 0.5.13 is MIT and its `requires_dist` lists `PyMuPDF>=1.26.7`. It reads clean in a scanner that only checks top-level packages. **CI must fail on AGPL anywhere in the resolved lockfile, not in top-level metadata.**
- **Process boundary is retained as a hedge, not as a permission.** ARCHITECTURE's `sidecars/` directory stays — it mirrors a license boundary and makes the answer changeable — but it holds veraPDF and (if ever needed) LibreOffice, not Ghostscript. Whether subprocess isolation is legally sufficient for AGPL is a lawyer's question the project does not need to ask, because permissive replacements exist for every AGPL job here.
- **Not vendorable:** Stirling-PDF. Root `LICENSE` reads MIT but carves out `engine/` — which is exactly where its text editor lives — under an open-core license. Read it as prior art; do not copy code.

### 3. Build order — one merged sequence with gates

ARCHITECTURE wants a CLI slice before any web tier. PITFALLS wants the conformance harness before the rewrite engine. STACK wants a spike validating `playa-pdf` against real documents plus the TJ-refit algorithm. FEATURES says font subsetting is a peer of replace, not a follow-on. These are compatible; merged below in [Implications for Roadmap](#implications-for-roadmap).

One reconciliation is worth stating because it looks like a conflict: PITFALLS puts "P1 Ingest & Render — hostile-input hardening" early, while ARCHITECTURE says no web tier until the font slice passes. Resolution: **hostile-input hardening belongs with the first code that parses an untrusted upload, which is the web tier — not the CLI**, which consumes local trusted files. The parser-choice, `/Contents`-coalescing and `/Resources`-inheritance work from PITFALLS' P1 lands in the engine phases; the isolation, caps and encryption policy land with the web tier, before public exposure.

### 4. Uneditable-document classification — four buckets, three signals, two granularities

This is the conclusion that **invalidates a requirement in PROJECT.md**. See [Corrections to PROJECT.md](#corrections-to-projectmd).

The naive check (`len(extract_text()) > N`) fails on OCR'd scans, which carry a real, searchable text layer drawn in **render mode 3 (invisible)** over a raster. It classifies them as editable, the user edits for ten minutes, saves, and the visible page is unchanged — precisely the outcome the requirement exists to prevent.

**Three signals, evaluated per page:** (1) *visible* glyph count — render mode ≠ 3 and ≠ 7, not clipped away, not in a disabled OCG; (2) image coverage as a fraction of the crop box; (3) invisible:visible glyph ratio.

**Four uneditable buckets, each with its own message:**

| Bucket | Signature | User-facing message |
|---|---|---|
| **Scan, no text layer** | High image coverage, ~0 glyphs | "This page is a picture of text. There's nothing to find or edit." |
| **OCR'd scan** | High image coverage, ~0 *visible* glyphs, many invisible | "Scanned image with a searchable text layer. Searchable, not editable — the text isn't what's printed." |
| **Vector-outlined text** | ~0 glyphs *and* low image coverage | "The text here was converted to shapes. It's not text any more." |
| **Unwritable fonts** | Real visible text, but Type3, no `/ToUnicode`, symbolic simple font, or mixed-codespace Type0 | Per-run: "This text can't be edited in place." |

Plus an operational fifth that is policy, not classification: **encrypted** (user-password vs owner-password-only) and **signed** input (a full rewrite invalidates the signature — detect `/AcroForm /SigFlags` or `/Sig` and warn before saving).

**Two granularities.** Per *page* for the thumbnail-rail badges. Per *run* for the three-state edit classification — `editable-in-original-font` / `editable-with-substitution` / `not-editable` + reason — which must exist before the user clicks, so uneditable runs are greyed out rather than discovered.

**Refuse the operation, not the document.** A 40-page contract with 3 scanned pages must remain fully editable on the other 37 and fully page-op-able on all 40. Blanket rejection is its own bad outcome.

### 5. Positioning — one honest statement

FEATURES, STACK and ARCHITECTURE converge on the same claim from three angles: FEATURES says do not claim "files never leave your device" (false for the text engine, and the one claim users actually check) and that deletion windows are table stakes rather than differentiating; STACK notes page-ops-only sessions genuinely never touch the server; ARCHITECTURE frames ephemerality as structural ("the server has no state whose loss is observable") rather than as policy.

**The claim, in descending strength:**

1. **"Most operations never leave your browser — and we show you which."** A per-operation local/server indicator in the UI. No competitor does this, because none of them can without admitting they upload everything. It is backed by a structural rule, not a promise: *if the recipe's `overrides` map is empty and no font or format operation is present, the client materializes the file and downloads it with zero upload; otherwise the server produces it.* One well-defined crossover.
2. **Ephemerality stated as a mechanism, not a window.** Client-authoritative bytes; a content-addressed server cache that is evictable at any moment (kill it mid-session in a test and the session must survive); tmpfs scratch; no document bytes in any queue payload; no document content in logs or error reports. Proven by a canary-marker retention test in CI on the success path **and the crash path**. "Deleted immediately" without a mechanism is the same sentence four competitors already print.
3. **Named, checkable absences.** No account, so there is nothing to link a document to. No AI. No analytics on document content. No cloud-storage OAuth.
4. **Publish what cannot be local and why.** "The text engine needs the server because font subsetting in WASM would mean a multi-megabyte download and a file-size ceiling." Candor reads as competence to the audience most likely to check the network tab.

**Never claim:** "files never leave your device," "we never see your file," or "deleted immediately" without stating the mechanism.

### 6. DOCX — keep it, last, and generate OOXML directly

PROJECT.md carries DOCX as ⚠️ Revisit. Consolidated recommendation: **keep it, sequenced strictly last, best-effort, generated as OOXML directly from the text model via `python-docx` — not via LibreOffice, not via `pdf2docx`.**

- `pdf2docx` is out on licensing (AGPL transitively, §2).
- LibreOffice's PDF import routes through **Draw**, producing a page of disconnected text frames rather than paragraphs; headers, footers and page numbers vanish. FEATURES confirms the universal user complaint is exactly this, and that users prefer flowing paragraphs that lost positioning over a pixel-accurate document they cannot type into. **Optimize for editability, not fidelity.**
- LibreOffice headless also brings profile locking, no built-in timeout, multi-second cold start, memory leaks on large conversions, zombie processes, recovery-mode-on-next-start after a crash, and a large native attack surface — every one of which fights the sandboxing and ephemerality posture built in earlier phases.
- **And it buys almost nothing**, because the fidelity ceiling is set by *your* layout inference either way. That is the argument that settles it.
- Keep LibreOffice only for DOCX→PDF, where it is genuinely strong. Not needed in v1.

**Scope ceiling, to be written into the phase definition before work starts** (so "improve table detection" is a new decision, not a continuation): single-column body text; headings by font-size clustering; bold/italic; images placed inline; **ruled tables only**; everything else as plain paragraphs. Explicitly not: unruled tables, multi-column reading order, header/footer reconstruction, round-trip back into the tool.

Two supports: build text → Markdown → HTML first so DOCX inherits a working reading-order and block-structure layer instead of starting from raw glyph positions; and ship a **pre-conversion warning that names what will degrade in this specific document** ("3 tables and a 2-column section detected"), which is cheap because the layout analysis already ran. It must remain independently cuttable.

## Conflicts Between the Research Documents

Surfaced rather than smoothed. Six real ones.

| # | Conflict | Resolution |
|---|---|---|
| 1 | ARCHITECTURE's sidecar diagram uses **Ghostscript for PDF/A**; STACK rejects Ghostscript as Artifex AGPL and prescribes `pikepdf` + `fontTools` modelled on `pdftopdfa` 0.9.0 (MPL-2.0, Ghostscript-free), validated with veraPDF. | **STACK wins.** Ghostscript is not needed for any job here — compress, flatten and PDF/A all have permissive replacements. Delete it from the runtime. |
| 2 | ARCHITECTURE lists **MuPDF** as a rasterizer option and in the differential harness; STACK rejects MuPDF as AGPL. | **Split by reachability.** Runtime rasterization is `pypdfium2` (BSD/Apache). MuPDF and Ghostscript are permitted as **CI-only** differential renderers — internal use is not conveying, and their disagreement is the point of the harness. |
| 3 | ARCHITECTURE: **every export is an async job** (202 + job id + SSE), uniformly. STACK: synchronous by default, add ARQ only when a conversion outgrows the request cycle, because "a queue is durable state — an anti-feature for a no-retention product." PITFALLS: queue payloads persist in the broker, its AOF/RDB snapshots, and dead-letter queues. | **Both, split by what the queue holds.** ARCHITECTURE's argument is about client API shape (one code path, one cancel path, no HTTP timeouts); STACK's is about durable payload storage. Adopt the uniform async *envelope*, but the queue carries an **opaque short-TTL handle only, never bytes**, with no persistent result backend and no DLQ retention. For v1 on a single box that is an in-process job registry — no Redis, no conflict. |
| 4 | ARCHITECTURE proposes **Redis** (`SET … EX 900`, `allkeys-lru`) for the blob cache; STACK and PITFALLS both flag Redis holding document bytes as quietly breaking the no-retention promise. | **In-process LRU for v1** (single box, 0–1k users — ARCHITECTURE's own scaling table says the same). If Redis is introduced at 1k+, **persistence off**: no AOF, no RDB, `maxmemory` + `allkeys-lru`. |
| 5 | FEATURES: **Stirling PDF has no documented existing-text content editing** (MEDIUM, explicitly flagged as absence-of-evidence). STACK: **Stirling-PDF 2.1.0 shipped a PDF text editor** and moved to open-core. | **STACK wins** — more specific, more recent, and cites the license-change discussion. Treat Stirling as a competitor that has shipped a text editor. Re-verify before any comparative marketing claim. |
| 6 | PROJECT.md: scanned PDFs "**detected and refused** in v1." FEATURES: refuse the *operation*, not the *document* — whole-file rejection loses the user permanently. | **FEATURES wins.** See [Corrections to PROJECT.md](#corrections-to-projectmd). |

## Key Findings

### Recommended Stack

Python 3.13 engine, React/Vite SPA, FastAPI HTTP layer, no Next.js (its 4.5 MB serverless body limit is a hard wall for a PDF upload product, and it pushes toward presigned-S3 upload, which turns "deleted immediately" into "deleted eventually"). Three libraries do the work one AGPL library would have.

**Core:**
- **`pikepdf` 10.11.0** (MPL-2.0, wraps qpdf 12.4.0 / Apache-2.0) — object model and **content-stream rewrite**. `parse_content_stream` / `unparse_content_stream` / `TokenFilter` give real token-level rewrite of `Tj TJ ' "`. qpdf preserves everything it does not touch and repairs broken xref tables.
- **`playa-pdf` 1.1.0** (MIT) — read side: Type1/TrueType/Type3/CID encoding decode, ToUnicode resolution, per-glyph CID + bbox + origin/displacement. pikepdf deliberately does *not* decode text, which is why two libraries are needed on the read side. **Fallback: `pdfminer.six` — same author lineage, same capability, slower, more battle-tested.**
- **`fontTools` 4.63.0** (MIT) — the load-bearing dependency. Font parsing, `subset.Subsetter`, `hmtx` widths. Nothing in any language is close.
- **`uharfbuzz` 0.56.0** (Apache-2.0) — *kerned* advances via `hb.shape()`. The delta between unkerned `hmtx` and kerned advance is literally the number that goes in the TJ array.
- **`pypdfium2` 5.12.1** (BSD/Apache) — server rasterization. Chrome's engine, faster than Poppler or Ghostscript, cleanly licensed. Pin exactly; major bumps break APIs.
- **`pdfjs-dist` 6.2.108** (Apache-2.0) — browser rendering only. Mozilla's security process matters when input is untrusted. ESM-only; `renderTextLayer` is removed, use the `TextLayer` class.
- **`@cantoo/pdf-lib` 2.8.1** (MIT) — client page ops. The maintained fork; original `pdf-lib` last published 2021-11-06 with 317 open issues. It is **append-only** and cannot edit content streams — which matches the client/server split exactly.
- **Bundled fonts:** Liberation (Sans/Serif/Mono), Noto Sans/Serif, DejaVu — all SIL OFL 1.1 or equivalent. **Liberation is the highest-leverage choice in the project**: metric-compatible with Arial/Times/Courier by design, so replacement text in a Base-14-derived document lands in the same place with zero fitting work.

**Runner-up worth knowing:** Apache PDFBox 3.0.8 (Apache-2.0) is the only single permissive library with both token-level rewrite and built-in subsetting, and Stirling-PDF's editor proves it works. Rejected because fontTools beats PDFBox on Type1/CFF parsing, CID re-encoding and subset merging — precisely where this project lives.

### Expected Features

**Must have (table stakes — absence loses users):** faithful page rendering (credibility is set in the first 3 seconds); find-and-replace across all pages with a **preview + match list**; result looks untouched; page ops (insert blank / reorder / rotate / delete) client-side and instant; merge PDF; merge image; **undo as one operation** for a batch replace; per-page scanned detection with a clear message; compress (Smallpdf's own data puts it at ~34% of usage — the most-used PDF operation, more than any conversion); split; page images at DPI; DOCX (~16%, the largest single conversion — users will ask regardless of stated fidelity); no signup; an honest stated size limit rather than a hidden throttle (Sejda's 3-tasks-per-hour is the most-cited complaint in its reviews and is the exact frustration that started this project).

**Should have (real differentiation):** **replace-all that actually replaces all** — Acrobat makes you click Replace on every occurrence and the Replace-All request sits unanswered; **type any character** because the font is subset and embedded on save — PDF-XChange literally cannot type a character absent from the block's subset, and Acrobat requires the font *installed on your machine*; **glyph-aware named refusal instead of tofu** — no competitor checks coverage before applying, they render `.notdef` and let you find out; **per-page scanned detection at open time** with the pages named; **per-operation local/server disclosure**; Markdown export (nobody in the consumer category ships it, near-free once extraction exists).

**The market gap, precisely:** every tool that edits text uploads your file, and every privacy-first browser tool does page ops only. Not one product surveyed does content-stream text editing *and* has a credible privacy story.

**Defer (v2+):** OCR + overlay editing path (a second engine path, not an addition); **real redaction** — the highest-value v2 differentiator, since content-stream deletion is the *correct* way to redact and almost nobody does it right, but it needs a verification story and a warranty first; batch/multi-file; accounts.

**Anti-features to hold the line on:** white-box overlay fallback (the moment it exists it becomes the fallback for every hard case and the quality claim dies — refusal is the substitute, and refusal is a quality signal); AI chat (detonates the privacy positioning by shipping full document text to a third party); full reflow; e-signature (forces retention — iLovePDF keeps signed documents 5 years); cloud-storage OAuth; password removal; task-per-hour throttling; silent page-size normalization on merge.

### Architecture Approach

The browser holds the authoritative bytes and a small declarative **recipe** (`{sources, pages[], overrides{}}`, kilobytes of JSON). The server holds a content-addressed, freely-evictable cache and nothing else — on a miss it returns `409 SOURCE_MISSING` and the client re-uploads. Overrides are a **sparse map, not an ordered op log**, because reflow is out of scope, so edits to different runs are independent and commutative and edits to the same run simply supersede each other. Undo is `structuredClone(recipe)` on a stack in browser memory — the entire undo system is about eight lines, and it works *only* because edits always apply to originals.

**Major components:**
1. **Content-stream interpreter** ★ — one text-state-machine walk, two outputs (run index + rewritten stream). The load-bearing component; everything else consumes run records.
2. **Font service** — encoding decode (once per document, cached with the index), coverage query (per edit, cheap), subset + embed (**once, at export, over the union of all characters used across all runs assigned to that face**). Never subset on a keystroke.
3. **Width fitter** — trailing `TJ` kern adjustment first, then distribute across inter-word kerns, then `Tz` (visible above ~±3%), then refuse. Note the sign convention: the TJ number is *subtracted*, so positive tightens.
4. **Document assembler** — recipe → output bytes via pikepdf/qpdf. Never re-parses already-edited output.
5. **Recipe store (client)** — document state + undo stack. Must land with the first mutating feature; retrofitting undo across two code paths is significantly harder.
6. **Ephemeral blob cache** — content-hash keyed, TTL, evictable at any moment. Never key on a client-supplied ID.

**Font rule that makes the fidelity claim defensible:** the pipeline only ever *adds* a bundled face; it never modifies or merges an existing embedded font. Two merged documents that both embed `ABCDEF+Arial` with different subsets stay separate — unifying them without remapping every glyph code produces a file that shows the right words in Chrome and mojibake in Acrobat.

### Critical Pitfalls

1. **Inverting `/ToUnicode` to produce output bytes.** Both maps take a code as input so they look interchangeable; they are not. `/ToUnicode` is optional advisory metadata with **zero effect on rendering**, is not injective (a ligature code maps to "ffi"), is frequently absent or wrong, and is overridable by `/ActualText`. → Build the forward `/Encoding` map. Keep `Code→Glyph` and `Code→str` as distinct types. Warning sign: `{v: k for k, v in tounicode.items()}`.
2. **Advance-width drift.** `/Widths[code − FirstChar] / 1000` comes from the font *dictionary*; a code outside `FirstChar..LastChar` falls back to `/MissingWidth`, **whose default is 0** — so every subsequent glyph on the line stacks at the same x. One line of missing bounds-checking, spectacular failure. Also: changing the glyph count changes the total `Tc` contribution, so even a same-width replacement shifts the line. → Enforce a **hard invariant: the text matrix after the edited run is bit-identical (within epsilon) to what it was before**. Mechanically testable; belongs in the phase's definition of done. And `Tw` is a no-op on `Identity-H` text — spacing "fixes" via `Tw` silently do nothing on half the corpus.
3. **The sentence does not exist as a string in the content stream.** `[(Inv) -12 (oice)] TJ`; words split across `Tj` operators and `BT`/`ET` blocks; LaTeX and CAD exports draw one glyph per operator; visual order ≠ stream order. → Interpret with a full graphics+text state machine, recurse into Form XObjects with a visited set and depth cap, emit per-glyph provenance, cluster into visual runs, match on reconstructed text, edit via provenance. Any regex over decompressed content-stream bytes is the project's single worst shortcut.
4. **Invisible OCR text defeats scanned detection** — see [Uneditable classification](#4-uneditable-document-classification--four-buckets-three-signals-two-granularities).
5. **"It works in the viewer I tested."** Six independent renderers with six undocumented recovery strategies. **The tool's own preview (pdf.js) is the least representative renderer in the set** and the one whose font handling diverges most visibly — shipping to a green preview is shipping untested. → Three-engine differential rasterization with a **masked** diff: the before/after difference must be confined to the edited run's bbox and pixel-identical everywhere else. That one assertion catches width drift, shared-XObject bleed and resource-dict corruption simultaneously, and it is robust to renderer-to-renderer differences in a way absolute comparison is not. Do not write the comparator from scratch — `pdf.js.comparator` and SPARCLUR exist.
6. **Hostile input on an anonymous public endpoint.** The CVE stream is continuous, not occasional: CVE-2024-4367 (`/FontMatrix` string injection executing JS in the hosting origin via pdf.js), CVE-2026-3308 (MuPDF ≤1.27.0 integer overflow → heap OOB write from an ordinary image dictionary), and a steady pypdf DoS series (cyclic `/Prev`, unterminated inline image, predictor bomb, self-referencing Form XObject). **No library choice makes this go away.** → Short-lived isolated subprocess per parse: `RLIMIT_AS`, hard wall-clock timeout, no network egress, read-only rootfs + tmpfs scratch, non-root, seccomp. Caps *before* parse. Visited sets and depth caps on every graph traversal. `isEvalSupported: false` + a CSP forbidding `eval`. Strip active content (`/OpenAction`, `/AA`, `/JavaScript`, `/Launch`, `/EmbeddedFile`, XFA) on save, or the product becomes a malware laundering service that returns a "cleaned by" file.
7. **Privacy leaks from infrastructure nobody thought of as storage**, in likelihood order: **Cloudflare's default cacheable-extension list includes `.pdf`** — a download route ending in `.pdf` is cached at the edge with no configuration and no warning; subprocess temp files left behind on crash (and crash is the *normal* path for hostile input); queue payloads persisting in the broker's snapshots and dead-letter queues (which hold exactly the documents that triggered errors — the ones a human is most likely to examine); Sentry-class frame-locals capture shipping `content_stream_bytes` to a third party; filenames in access logs (`invoice_acme_termination_final.pdf` is itself a disclosure).

## Implications for Roadmap

Eight phases. Risk front-loaded on purpose: if the interpreter cannot faithfully round-trip real documents, the product does not exist, and that should surface in week three.

### Phase 0: Conformance Harness + Engine Spike
**Rationale:** PITFALLS' single highest-leverage recommendation — almost every pitfall is undetectable without this, and most are *silent*. STACK's `playa-pdf` bet and the TJ-refit algorithm both need proving before anything is built on them. No product code in this phase.
**Delivers:** 100–300 real-world PDFs harvested from the wild (not generated), covering subset fonts, Type0/`Identity-H`, symbolic fonts, Type3, CID-keyed CFF, `/Contents` arrays, inline images, Form XObjects, annotation appearance streams, justified/right-aligned text, tables, an `ocrmypdf`-generated scan, vector-outlined text, encrypted files, malformed files — invoices and contracts most of all; a pinned three-engine differential rasterizer in CI with the masked-diff assertion; `qpdf --check` + `pdfcpu validate`; the `playa-pdf` viability spike; a TJ-refit prototype; the one-page data-flow retention map (**before infrastructure is chosen** — queue-with-payload vs handle-only and object-store vs tmpfs are hard to reverse).
**Gate G0:** masked-diff harness passes on an identity transform across all three engines · `playa-pdf` decodes encodings and glyph geometry on ≥4 real documents including one Type0/`Identity-H` and one subset-font document, **or** the switch to `pdfminer.six` is made now, not later · TJ-refit prototype achieves |Δwidth| < 0.5pt on a hand-picked run · retention map written.
**Avoids:** Pitfalls 9, 5, 12.

### Phase 1: Text Model
**Rationale:** the keystone. Find, replace, scanned detection and all four text-ish exports sit on it — if it slips, five features slip. Provenance and the type separation are design decisions here, not retrofits.
**Delivers:** the content-stream interpreter (index mode) with per-glyph provenance; forward encoding resolution as a **documented decision table** with the fired branch logged per font; codespace-range decoding for Type0; run clustering with the synthetic-space threshold; three-state per-run editability classification; four-bucket per-page document classification; `pdftool index`.
**Gate G1:** provenance round-trips (extract → locate → rewrite → re-extract) on the corpus · glyph-at-a-time and two-column files extract correctly · the OCR'd scan classifies as "scanned with searchable text layer" and not as editable · vector-outline page lands in its own bucket · symbolic/Type3/no-`ToUnicode` runs marked not-editable **with a reason** · `Code→Glyph` and `Code→str` are distinct types.
**Avoids:** Pitfalls 1, 2, 3, 6, 7.

### Phase 2: Rewrite Engine + Font Pipeline (one phase, not two)
**Rationale:** FEATURES is explicit — font subsetting is a **peer** of replace, not downstream. Embedded fonts are subsets, so typing a character the document never used is *the common case*, and shipping replace first produces exactly PDF-XChange's shipped limitation, which the market already has and nobody likes. **The honest MVP boundary is replace + subsetting together, or neither.** Still CLI-only; ARCHITECTURE's Slice 0a then 0b.
**Delivers:** rewrite mode over the same traversal; width fitter with the text-matrix invariant; bundled-font selection from a **static mapping table, not a heuristic**; whole-document glyph-union subsetting at save; Type0/CIDFontType2 + `Identity-H` embedding with `/W` and a generated `/ToUnicode`; `/Widths` regeneration with the 1/1000 consistency assertion; fresh subset tag on every re-subset; `pdftool edit`.
**Gate G2a (Slice 0a):** replace a run where all glyphs exist in the embedded subset — `qpdf --qdf` normalization diff confined to the edited operators · |Δwidth| < 0.5pt · text matrix after the run bit-identical · `qpdf --check` clean · masked pixel diff zero outside the run in all three engines.
**Gate G2b (Slice 0b) — THE PROJECT GATE:** the same, with a character **absent from the embedded subset** — copy-paste out of Acrobat yields the correct Unicode · output font passes OTS · untouched text elsewhere using the same font still renders · opens without a repair prompt in Acrobat Reader, macOS Preview and Chrome. **No web-tier work begins before G2b passes.** Slice 0a can pass by getting lucky about glyph coverage; 0b is what actually proves the architecture.
**Avoids:** Pitfalls 4, 5, 10.

### Phase 3: Web Tier Walking Skeleton + Hardening
**Rationale:** first untrusted input, so this is where isolation lands — and it must land before public exposure, not after. Also where the recipe model and undo land, because retrofitting undo across two code paths later is significantly harder.
**Delivers:** ingest (magic-byte sniff, size cap, SHA-256, encryption check); sandboxed engine workers; content-addressed evictable cache with the `409 SOURCE_MISSING` re-upload path; `/v1/index` (NDJSON stream so page 1 is interactive before page 400 parses) and `/v1/render`; pdf.js viewer with **server-issued hit boxes**; single-run edit round trip with the optimistic DOM overlay replaced by a rendered PNG; recipe store + undo; per-page classification badges in the thumbnail rail.
**Gate G3:** parse never runs in the request process · decompression bomb, cyclic page tree and self-referencing XObject die on their limits rather than on the host · **canary-marker retention test passes on the success path and the crash path** · `Cache-Control: no-store` verified and CDN status is `BYPASS`/`DYNAMIC` on document routes · `isEvalSupported: false` + CSP without `eval` · the `409` re-upload path is exercised in tests · killing the cache mid-session leaves the session working.
**Avoids:** Pitfalls 11, 12.

### Phase 4: Find and Replace Across All Pages
**Rationale:** the core value's user-facing form, and it is nearly free architecturally — a client-side query over the cached index producing N ordinary overrides. Within the phase, build the **match list and preview before wiring apply**: it depends on the index, not the rewrite engine, so it demos early and de-risks the rewrite by making its inputs visible.
**Delivers:** client-side index search with the same normalization the interpreter used (collapse intra-word `TJ` adjustments, normalize ligatures `ﬁ`→`fi`); default case-insensitive + substring, with "match case" and "whole words only" toggles; match list with page, ±40 chars of context, live count, per-match opt-out, click-to-jump; **unreplaceable matches shown in the same list, disabled, with the reason** — never silently filtered; overflow measured and disclosed pre-commit with bounded condensing (90–95% `Tz`/`Tc` is visually undetectable); undo as one step.
**Gate G4:** replace-all across a 40-page corpus contract · one Ctrl+Z reverts the batch · masked differential diff confined to edited runs on every changed page in three engines.
**Addresses:** replace-all, preview-before-apply, glyph-coverage refusal, overflow disclosure, per-page scanned messaging.

### Phase 5: Page Ops and Merge
**Rationale:** zero dependency on the text engine — fully parallelizable, and a good independent workstream. Also where the "never leaves your browser" claim becomes literally true for page-op-only sessions.
**Delivers:** insert blank (**inherits MediaBox and rotation from the adjacent page**, shows what it inherited — never a Letter default), reorder, rotate, delete; merge PDF with outline nesting on the Acrobat model, form-field collision handling (auto-prefix or flatten, but **announced either way**), per-page MediaBox preserved by default; merge image as new page and placed-on-page with aspect lock **visible rather than a hidden modifier key**, transparent PNG compositing, PNG/JPEG/WebP/HEIC; the pure-page-op local download path.
**Gate G5:** a page-ops-only session produces a download with **zero requests to document routes** · merging two documents that both embed `ABCDEF+Arial` with different subsets renders both correctly in three engines (resource names namespaced; **never dedupe fonts by `/BaseFont`, only by content hash**) · no other page changed after a resource-dictionary write (inherited `/Resources` copied, not mutated).
**Avoids:** Pitfalls 8, 10.

### Phase 6: Exports
**Rationale:** conventional work on solved libraries, and most of it is a byproduct of the run index that already exists. Compress deserves more polish than its complexity suggests — it is the most-used PDF operation in the category.
**Delivers:** page images at DPI via `pypdfium2` (150 screen / 300 print defaults, per-page and all-pages-zip); compress via pikepdf object streams + Pillow image downsampling, **lossless structural by default with downsampling as an explicit labeled choice showing before/after size and a preview**; split; flatten; plain text / Markdown / HTML from the run index.
**Gate G6:** every export consumes the Phase 1 run index — **a second extraction path appearing anywhere is a signal the text model is under-specified, and the fix is Phase 1, not a fork.**

### Phase 7: PDF/A, then DOCX
**Rationale:** both are gated on the full save pipeline. PDF/A's hard part is conformance validation, not generation. DOCX is last by locked constraint and by output honesty, and must stay independently cuttable.
**Delivers:** PDF/A via pikepdf + fontTools (embed all fonts, OutputIntent/ICC, XMP), modelled directly on `pdftopdfa` 0.9.0, **gated on veraPDF passing against a fixture corpus in CI, not on spot checks** — a PDF/A file that does not validate is worse than no feature. Then DOCX per the written ceiling in §6, with the per-document degradation warning.
**Gate G7a:** veraPDF passes at the chosen conformance level (PDF/A-2b is the common target) across the fixture corpus in CI.
**Gate G7b:** the scope ceiling is written into the phase definition *before* work starts · no second extraction path · the warning names what will degrade in this specific document · the phase can be cut without touching anything else.

### Phase Ordering Rationale

- **Everything upstream of the interpreter gates everything downstream**, so all the risk sits in Phases 0–2. The viewer, page ops and exports are conventional work on well-trodden libraries; sequencing them early would produce an impressive demo on an unproven core.
- **Phase 2 is one phase, not two**, because replace-without-subsetting is a shipped competitor limitation rather than an increment.
- **No web tier before G2b** — discovering the font layer does not work after building a viewer is the expensive failure mode.
- **The harness precedes the engine** because retrofitting a corpus after the rewrite engine exists means every prior release was unvalidated.
- **Scanned/uneditable classification ships with the text model, not as its own phase.** It is nearly free once the index exists, blocks nothing, and gates the *quality* of every text feature's failure mode.
- **Find and replace are separate features.** Find needs the visible-text index; replace needs the inverse map plus width recalculation. Estimating them as one item is the most likely source of a blown estimate.
- **The recipe model must land with the first mutating feature** (Phase 3), because undo across two code paths is a retrofit nobody wins.

### Research Flags

Phases likely needing `/gsd:plan-phase --research-phase`:
- **Phase 1** — the simple-font encoding resolution chain has at least five paths selected by the `Symbolic` flag, `/Encoding` presence and which cmap subtables the embedded font carries, and the spec does not cleanly resolve `Symbolic` + `/Encoding`; the synthetic-space gap threshold needs corpus tuning and "is the whole game" for extraction quality.
- **Phase 2** — the TJ-refit algorithm has no library and no reference implementation; kerning-split runs are the known top edge-case failure source; bundled-font metric substitution quality mid-paragraph is unverified.
- **Phase 7** — PDF/A conformance levels and font-embedding rules that only a validator catches; DOCX layout inference is heuristics all the way down.

Phases with standard patterns (skip research):
- **Phase 3** — FastAPI + React/Vite scaffolding and container sandboxing are well-documented; the *architecture* decisions are already settled above.
- **Phase 5** — page ops are exactly what `@cantoo/pdf-lib` is good at; the merge correctness traps are already enumerated with fixes.
- **Phase 6** — `pypdfium2` and Pillow are solved problems; `pdftopdfa` is a working reference for the pikepdf/fontTools shape.

## Risk Register

Ranked by probability × damage × how late you find out.

| # | Risk | Why it ranks here | Mitigation / gate |
|---|---|---|---|
| **1** | **The composition is unproven.** No public reference implementation of server-issued-run-index + declarative recipe + pikepdf rewrite + fontTools embed was found. ARCHITECTURE flags this at LOW confidence explicitly. | The individual pieces are each well-supported; the assembly is a synthesis. If it does not hold, there is no product and no fallback plan. | **Gate G2b.** Do not build the web tier before it passes. This risk is what Phase 2 exists to retire. |
| **2** | **Silent wrong output** — encoding branch bugs, width drift, subset gaps — that opens without error everywhere the team looks and is wrong in Acrobat. | Highest probability on the list, and it is discovered by users weeks apart, each report requiring the same reasoning re-derived from scratch. | **Phase 0 before Phase 2.** Masked differential diff in three engines; text-matrix invariant as an assertion; corpus of real documents, and every user-reported bad file added permanently. |
| **3** | **`playa-pdf` is on the critical path with thin third-party corroboration.** STACK rates it MEDIUM-HIGH on the project README alone and says to prototype against real PDFs before committing. | It sits in the one place with no permissive alternative that is equally good, and the decision is cheap now and expensive in Phase 2. | **Gate G0** decides it against ≥4 real documents. `pdfminer.six` is the drop-in fallback. Keep decode calls confined to one engine module so the swap stays a contained change — do not build an abstraction layer for it. |
| **4** | **Substituted bundled fonts look pasted-in mid-paragraph.** Liberation's metric compatibility with Arial/Times/Courier is documented *by design* but "visually good enough mid-paragraph" is unverified. | This *is* the core value's pass/fail test — users compare side by side at 100% zoom, and any visible seam means the product failed at its one job. | Empirical check inside **Gate G2b** against the real-document corpus. Static substitution table, not a heuristic. Re-encode the **entire visual run**, never half a word — half in Helvetica-subset and half in Liberation is worse than all of it in Liberation. |
| **5** | **The TJ-refit algorithm is code this project writes**, and kerning-split runs are the documented top failure source (`pypdf_strreplace`'s author: replacements "only succeed in very specific circumstances"). | No library, no reference. It is the mechanism the core value runs on. | Prototype in **Phase 0** alongside the playa spike. Text-matrix invariant as a hard assertion. Refuse visibly rather than guess. |
| **6** | **Hostile input on an anonymous public endpoint.** Continuous CVE stream across every PDF library; parser RCE means assuming every in-flight document was disclosed. | Lower probability than 1–5, but the damage is unbounded and the recovery is "rebuild hosts and disclose publicly." | Isolation lands in **Phase 3, before public exposure.** Assume the parser will be exploited eventually and design so it does not matter. Verify with an actual bomb, cyclic page tree and self-referencing XObject. |
| **7** | **Privacy leak via infrastructure nobody classified as storage.** CDN caching `.pdf` by default is the most likely single vector. | The privacy claim is the differentiator; one counterexample ends it permanently and unrecoverably. | Data-flow map **before infrastructure selection** (Phase 0). Canary retention test in CI on success **and crash** paths. `no-store` + CDN bypass verified in **G3**. |
| **8** | **DOCX eats the project** — the last feature becomes the longest phase and drags in dependencies that compromise the posture built earlier. | High probability (it always happens), moderate damage, and it is entirely preventable with one written paragraph. | Ceiling written into the phase definition **before** work starts. Direct OOXML generation, no LibreOffice. Independently cuttable. Any conversation containing "if we just improved table detection a bit" is the tripwire. |
| **9** | **Scope drift into a white-box overlay fallback.** It always works, every competitor has it, and Sejda officially recommends it. | The moment it exists it becomes the fallback for every hard case and the quality claim silently dies — and users cannot tell which mode ran. | It is an anti-feature, permanently. The substitute is refusal UX that is genuinely good, which is why the four-bucket classification and per-run greying-out are Phase 1 work rather than polish. |
| **10** | **Competitive drift.** Stirling-PDF 2.1.0 shipped a text editor and moved to open-core; iLovePDF recently shipped direct text editing. | Not existential — neither pairs text editing with a credible privacy story — but "nobody does this" has a shelf life. | Re-verify competitor capability before any comparative marketing. The defensible position is the *combination*, not the feature. |

## Corrections to PROJECT.md

Flag these during requirements scoping.

| PROJECT.md text | Problem | Suggested replacement |
|---|---|---|
| *"Detect a scanned page with no text layer and say so clearly instead of failing silently."* (Active requirement) | **Invalidated by research.** "No text layer" is the wrong test: OCR'd scans have a real, searchable text layer in render mode 3 over a raster, and a naive extract-length check classifies them as editable — producing exactly the ten-minutes-then-nothing outcome this requirement exists to prevent. It also misses two further uneditable categories (vector-outlined text; Type3 / no-`ToUnicode` / symbolic / mixed-codespace fonts). | *"Classify every page and every text run for editability before the user types — scanned, OCR'd scan, vector-outlined text, unwritable font — name the reason in plain language, and keep every other operation available on pages that can't be edited."* |
| Key Decision: *"Scanned PDFs detected and **refused** in v1"* | Over-refusal. A 40-page contract with 3 scanned pages must stay fully editable on the other 37. | *"Uneditable content detected per page and per run; the operation is refused, never the document."* |
| Constraint: *"Uploaded documents are processed ephemerally and deleted immediately… This is a product promise"* | Correct but under-specified, and "product promise" is the weaker framing. Deletion windows are table stakes — every competitor already claims 1–2 hours and privacy reviewers explicitly discount them. | Restate ephemerality as a **structural property** ("the server has no state whose loss is observable," testable by killing the cache mid-session) plus **per-operation local/server disclosure**, which is the actually novel claim. Add an explicit non-claim: never say "files never leave your device." |
| Key Decision: *"DOCX export included but sequenced last"* — ⚠️ Revisit | Resolvable now. | Keep, last, best-effort, **direct OOXML from the text model** (not LibreOffice, not `pdf2docx`), with the scope ceiling in §6 written into the phase definition before work starts. Mark the decision resolved. |
| Constraint: *"Tech stack: To be determined by research"* | Resolved. | Python 3.13 engine (pikepdf + playa-pdf + fontTools + uharfbuzz + pypdfium2), FastAPI, React/Vite SPA, `@cantoo/pdf-lib` + pdfjs-dist client. Add the licensing rule as a constraint in its own right: **no AGPL in the runtime tree, transitively; GPL only as a subprocess.** |
| Out of Scope: *"OCR of scanned pages — deferred to v2"* | Still correct, but add the cheap v1 hook. | Keep. Add: the refusal screen names a specific external OCR route and offers a one-click "tell me when OCR ships" — the cheapest available signal on whether v2 OCR is worth building. |

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | **HIGH** on engine, fonts and licensing; **MEDIUM** on export quality and the client split | Every version and license queried live from PyPI/npm/crates.io/GitHub on 2026-08-11. Content-stream rewrite verified against pikepdf's own test-suite code. AGPL claims verified against verbatim PyPI license fields and Artifex's own pages. `pdftopdfa` 0.9.0 is a working proof of the stack shape. Export quality ratings are consistent across secondary sources but not independently benchmarked. |
| Features | **MEDIUM-HIGH** | Competitor limitations verified against vendor documentation and vendor *support forums* — which is where the real limits live, not marketing. Usage-share numbers are Smallpdf's own self-reported and self-selected data; directionally useful, not market truth. One claim already stale (Stirling text editing — see Conflict 5). iLovePDF's current capability is LOW-MEDIUM and self-contradictory across sources. |
| Architecture | **MEDIUM-HIGH** on the pieces; **LOW** on the composition | Every component's library capability verified against official docs and issue trackers. But **no public reference implementation of this exact composition was found** — the researcher flagged this explicitly and it is Risk #1. Latency figures are order-of-magnitude estimates, not measurements on this workload. |
| Pitfalls | **HIGH** on PDF and font internals; **MEDIUM** on CVE specifics and privacy mechanics | Internals grounded in the PDF spec errata, PDF Association clause discussions, and primary bug trackers (pdf.js, qpdf, fontTools). CVE details are partly aggregator-sourced and flagged inline — **re-verify against NVD at implementation time.** Privacy leak vectors are one verified public incident (GrowthBook #5669) plus mechanism-level reasoning. |

**Overall confidence:** **MEDIUM-HIGH.** The technology choices, the failure modes and the market shape are all well-established. What is unproven is whether these specific pieces compose into a text editor that produces output Acrobat accepts — which is exactly what Phases 0–2 and Gate G2b exist to answer before anything is built on top.

### Gaps to Address

- **Simple-font encoding resolution when `Symbolic` and `/Encoding` are both present** — the spec does not cleanly resolve it and real files do it constantly; viewers disagree. → Phase 1 research; implement as a documented decision table with the fired branch logged per font, and prefer refusal over guessing.
- **The synthetic-space gap threshold** in run clustering — "the threshold is the whole game" for extraction quality and needs corpus tuning. → Phase 1, tuned against the Phase 0 corpus.
- **TJ-array reconstruction / width refitting** — no library provides it; kerning-split runs are the expected top edge-case source. → prototyped in Phase 0, built in Phase 2.
- **Bundled-font substitution visual quality mid-paragraph** — metric compatibility is documented by design, visual acceptability is not verified. → empirical, inside Gate G2b. Risk #4.
- **Encrypted and permission-restricted PDFs** — pikepdf handles the standard security handlers, but the *product policy* is undecided: user-password → prompt or refuse; owner-password-only → deliberately decide whether stripping permissions is a feature. Note PDFex (CCS 2019) showed PDF encryption is broken as a confidentiality mechanism generally. → decide in Phase 3, it is a policy question not an engineering one.
- **Signed input documents** — a full rewrite invalidates existing signatures, and users sign contracts. → detect `/AcroForm /SigFlags` or `/Sig` and warn before saving. Phase 3.
- **Bundled fonts' `fsType` bits** — the OS/2 embedding-permission field is declarative and frequently contradicts the actual license (OFL fonts shipping `Restricted` is a known common metadata error), and downstream corporate preflight tools *do* read it. → verify and consider normalizing on the bundled copies. Phase 2.
- **Malformed-but-tolerated input** — qpdf-class libraries silently repair broken xrefs, so the rewrite "fixes" the file into a structurally different document than the user saw. Not necessarily wrong, but it means **byte-level round-trip comparison is not a valid correctness test**. → the masked image diff is the valid test. Phase 0.
- **CVE specifics** in PITFALLS' attack table are partly aggregator-sourced. → re-verify against NVD when implementing Phase 3 hardening.
- **Competitor capability claims** (Stirling, iLovePDF) are stale or contradictory. → re-verify before any comparative marketing copy ships.

## Sources

### Primary (HIGH confidence)
- Live PyPI / npm / crates.io / GitHub API queries, 2026-08-11 — every version and license stated
- Context7 `/pikepdf/pikepdf` + [pikepdf content streams docs](https://pikepdf.readthedocs.io/en/latest/topics/content_streams.html) — `parse_content_stream` / `unparse_content_stream` / `TokenFilter`; the explicit warning against scraping text
- Context7 `/websites/fonttools_readthedocs_io_en` + [fontTools subset docs](https://fonttools.readthedocs.io/en/latest/subset/) — `Subsetter`, glyph closure, notdef handling
- [Artifex licensing](https://artifex.com/licensing) + [MuPDF license](https://mupdf.readthedocs.io/en/1.27.2/license.html) + [Ghostscript FAQ](https://ghostscript.com/faq/) — the AGPL SaaS clause, verbatim
- `https://pypi.org/pypi/pdf2docx/json` — `requires_dist` showing `PyMuPDF>=1.26.7`, the transitive AGPL trap
- [PDF spec errata clause 09 (Text)](https://pdf-issues.pdfa.org/32000-2-2020/clause09.html) + pdf-issues #9 (content-stream array token boundaries) and #130 (widths consistent to 1/1000)
- mozilla/pdf.js — [api.js `TextItem`](https://github.com/mozilla/pdf.js/blob/master/src/display/api.js), [evaluator.js `getCurrentTextTransform()`](https://github.com/mozilla/pdf.js/blob/master/src/core/evaluator.js), PR #6425, issues #7297, #7445, #12237, #14117, #14755
- [qpdf #444](https://github.com/qpdf/qpdf/issues/444) (concatenation producing merged tokens), [#22](https://github.com/qpdf/qpdf/issues/22) (`--qdf` discards incremental updates)
- fontTools issues #193 (`layout-features=["*"]` drops `kern`), #444 (`pyftmerge` output fails OTS)
- CVE-2024-4367 / Mozilla GHSA-wgrm-67xf-hhpq — `/FontMatrix` string injection; CVE-2026-3308 / CERT VU#951662 — MuPDF heap OOB write
- Müller et al., [Practical Decryption exFiltration (CCS 2019)](https://www.pdf-insecurity.org/download/paper-pdf_encryption-ccs2019.pdf)
- Adobe helpx — [Edit text in PDFs](https://helpx.adobe.com/acrobat/using/edit-text-pdfs1.html), [No available system font](https://helpx.adobe.com/acrobat/kb/error-no-available-system-font.html); [Sejda PDF Editor](https://www.sejda.com/pdf-editor); [PDF24 Edit PDF](https://tools.pdf24.org/en/edit-pdf)
- [`pdftopdfa` 0.9.0](https://github.com/iRedPaul/pdftopdfa) — Ghostscript-free PDF/A reference architecture
- [veraPDF](https://verapdf.org/) + [veraPDF test corpus](https://github.com/veraPDF/veraPDF-corpus)

### Secondary (MEDIUM confidence)
- [playa-pdf](https://github.com/dhdaines/playa) — capability and license from the project README; thinner third-party corroboration than pdfminer.six (Risk #3)
- [pypdf_strreplace](https://github.com/hoehermann/pypdf_strreplace) — prior art, candid about subset-font and kerning limitations
- [uharfbuzz docs](https://uharfbuzz.readthedocs.io/) + fpdf2 text-shaping docs — `x_advance` and TJ kerning derivation
- PDF-XChange forum threads on font substitution and subset limits; Evermap on form-field collisions during merge
- [Stirling-PDF discussion #4332](https://github.com/Stirling-Tools/Stirling-PDF/discussions/4332) (open-core license change), [#5021](https://github.com/Stirling-Tools/Stirling-PDF/discussions/5021) (stateless/tmpfs pattern)
- [unoserver](https://github.com/unoconv/unoserver); gotenberg #407, #94 — LibreOffice operational failure modes
- Cloudflare default cacheable-extension docs; [growthbook #5669](https://github.com/growthbook/growthbook/issues/5669) — CDN caching by path extension
- pypdf DoS CVE series (CVE-2026-27628, -59935/59936, -41312, -48155, -54530, CVE-2023-36464) — aggregator-sourced, re-verify at implementation time
- Smallpdf [PDF statistics](https://smallpdf.com/pdf-statistics) — usage shares, vendor self-reported and self-selected
- javadoc.io `PDFStreamParser` (PDFBox 3.x) — token-level rewrite capability of the runner-up stack

### Tertiary (LOW confidence — needs validation)
- Latency figures for engine operations (ARCHITECTURE) — order-of-magnitude estimates, not measured on this workload. Measure in Phase 0/2.
- Liberation ↔ Arial/Times/Courier metric compatibility as *visually* acceptable mid-paragraph — documented by design, unverified in practice. Risk #4.
- Absence of any public reference implementation of the server-issued-run-index + declarative-recipe composition — absence of evidence, and the basis for Risk #1.
- iLovePDF's exact current text-editing capability — official blog and third-party reviews contradict each other.
- OS/2 `fsType` guidance — declarative field, frequently contradicts the actual license.

---
*Research completed: 2026-08-11*
*Ready for roadmap: yes*
