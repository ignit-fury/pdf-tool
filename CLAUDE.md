<!-- GSD:project-start source:PROJECT.md -->
## Project

**PDF Tool**

A browser-based PDF editor that edits the *actual existing content* of a PDF — replacing text
inside the page's content stream rather than pasting annotations or white boxes on top. Users
open a PDF, find-and-replace text across every page, insert blank pages, merge in images or
other PDFs, restyle text with embedded fonts, and export to several formats. It is aimed at
people who need to change a document that already exists and want the result to look untouched.

It is a real product for other people, used anonymously — no signup to edit a file.

**Core Value:** **Replace text across every page of an existing PDF and have the output look like nothing
happened.** If everything else on this list fails, this one capability must work.

### Constraints

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
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## The One Finding That Drives Everything
| Half of the problem | What it requires | Library |
|---|---|---|
| **Read** — "what text is where, in which font, at which glyph code?" | Decode Type1/TrueType/Type0-CID encodings, resolve CMaps, get per-glyph position + advance | `playa-pdf` (MIT) |
| **Write** — "swap these operators and re-serialize the page" | Parse `Tj/TJ/'/"` into tokens, modify, unparse, save without corrupting the object graph | `pikepdf` (MPL-2.0) over `qpdf` (Apache-2.0) |
| **Fonts** — "the new character isn't in the embedded subset" | Parse the embedded font program, subset a bundled font, re-embed with correct widths + CMap | `fontTools` (MIT) + `uharfbuzz` (Apache-2.0) |
## Recommended Stack
### Core Technologies
| Technology | Version | License | Purpose | Why Recommended |
|---|---|---|---|---|
| **Python** | 3.13.x | PSF | Engine language | Only language where the content-stream half and the font half are *both* best-in-class *and* permissively licensed. 3.13 over 3.14 for wheel availability across the C-extension deps. |
| **pikepdf** | 10.11.0 | MPL-2.0 | Object model + content-stream **rewrite** | `parse_content_stream()` / `unparse_content_stream()` / `TokenFilter` give real token-level rewrite of `Tj TJ ' "`. Wraps qpdf 12.x, which is the most correct open PDF object-layer implementation in existence (it repairs broken xref tables, handles object streams, preserves everything it doesn't touch). |
| **qpdf** | 12.4.0 | Apache-2.0 | C++ engine under pikepdf | Ships inside pikepdf wheels. Apache-2.0 — no copyleft exposure at all. |
| **playa-pdf** | 1.1.0 | MIT | Read side: font encoding decode, glyph positions | Decodes Type1/TrueType/Type3/CID encodings, resolves ToUnicode CMaps, yields per-glyph CID + bbox + `origin`/`displacement`. Read-only by design — that's fine, pikepdf writes. ~10x faster than pdfminer.six with multiprocessing; same author. |
| **fontTools** | 4.63.0 | MIT | Font parsing + subsetting + re-embedding | **The load-bearing dependency.** Parses `glyf`/`CFF`/Type1, reads `hmtx` widths, and `subset.Subsetter` produces the subset you embed. Nothing else in any language is close. Actively developed (commits the day of this research). |
| **uharfbuzz** | 0.56.0 | Apache-2.0 | Shaped advance widths | fontTools gives *unkerned* `hmtx` advances. To build the `TJ` array that makes replacement text occupy the original run's width, you need *kerned* advances — that's `hb.shape()` returning `x_advance`. The delta between unkerned and kerned advance is literally the number you put in the TJ array. |
| **pypdfium2** | 5.12.1 | BSD-3-Clause / Apache-2.0 | Server-side rasterization | PDFium (Chrome's engine). Liberally licensed, faster than both Poppler and Ghostscript. Powers PNG/JPEG export and server-rendered previews. |
| **FastAPI** | 0.141.1 | MIT | HTTP layer | Native async + streaming multipart, and the engine is Python so there is no cross-process boundary to design. |
| **pdfjs-dist** | 6.2.108 | Apache-2.0 | Browser rendering | 87M downloads/month. Apache-2.0. Battle-hardened against malicious PDFs by Mozilla's security process — which matters when you accept arbitrary uploads. |
| **@cantoo/pdf-lib** | 2.8.1 | MIT | Client-side page ops | The maintained fork of pdf-lib (see "What NOT to Use"). Pure JS, no WASM. Page insert/reorder/rotate/delete/merge is exactly what pdf-lib is *good* at — and content-stream editing is exactly what it *cannot* do, which matches the client/server split precisely. |
| **React** | 19.2.8 | MIT | UI | |
| **Vite** | 8.2.1 | MIT | Build | SPA build, not Next.js. See "What NOT to Use". |
### Supporting Libraries
| Library | Version | License | Purpose | When to Use |
|---|---|---|---|---|
| **Pillow** | 12.3.0 | MIT-CMU | Image recompress / downsample | The "compress PDF" export. Extract image XObjects via pikepdf, downsample + re-JPEG via Pillow, write back. Replaces the Ghostscript you cannot use. |
| **python-docx** | 1.2.0 | MIT | DOCX writer | Writer only — you supply the document model from your own run map. Do NOT pair with pdf2docx. |
| **python-multipart** | 0.0.32 | Apache-2.0 | Upload parsing | Required by FastAPI for `UploadFile`. |
| **uvicorn** | 0.52.1 | BSD-3 | ASGI server | |
| **ARQ** | 0.28.0 | MIT | Job queue — **only if needed** | Add *only* when LibreOffice-backed conversion exceeds request timeouts. Everything else should be synchronous. A queue is durable state — an anti-feature for a no-retention product. |
| **veraPDF** | 1.31.32 | GPL-3.0 / MPL-2.0 | PDF/A validation | Run as a CLI subprocess, not linked. Validation only — it does not convert. Use it as the acceptance test for your PDF/A output. |
| **poppler-utils** (`pdftohtml`) | 26.04.0 | GPL-2.0/3.0 | PDF→HTML fallback | Optional. Prefer generating HTML from your own run map (one code path, no subprocess). GPL is safe here — SaaS is not distribution. |
| **LibreOffice** (headless) | 25.x/26.x | MPL-2.0 | DOCX→PDF only | Genuinely good in this direction. **Not** for PDF→DOCX — see the blunt assessment below. |
### Bundled Fonts
| Family | License | Why |
|---|---|---|
| **Liberation** (Sans/Serif/Mono) | SIL OFL 1.1 | Metric-compatible with Arial/Times/Courier. When the original PDF used a Base-14 or Microsoft core font, Liberation substitutes with *identical advance widths* — replacement text lands in the same place with zero fitting work. This is the single highest-leverage font choice in the project. |
| **Noto Sans / Serif** | SIL OFL 1.1 | Coverage fallback for anything Liberation lacks. |
| **DejaVu** | Bitstream Vera / free | Broad glyph coverage, permissive. |
### Development Tools
| Tool | Purpose | Notes |
|---|---|---|
| **uv** | Python dependency management | Fast, lockfile-based. The C-extension deps (pikepdf, uharfbuzz, pypdfium2) all ship wheels — no build toolchain needed. |
| **veraPDF CLI** | PDF/A acceptance test | Wire into CI as a golden test on a fixture corpus, not just a runtime check. |
| **qpdf CLI** (`--check`, `--json`) | Debugging corrupted output | Ships with pikepdf. `qpdf --check out.pdf` catches structural damage your rewrite caused before a user does. |
| **Docker** | Deployment | Needed anyway to pin LibreOffice + veraPDF + poppler versions. |
## Installation
# Engine (Python 3.13)
# API
# Only when a conversion outgrows the request cycle
# Client
# System packages (Dockerfile) — subprocess only, never linked
# veraPDF installed from its own installer JAR
## REWRITE vs APPEND — the capability table
| Library | Parse existing content stream into operators? | Modify + re-serialize? | Verdict |
|---|---|---|---|
| **pikepdf / qpdf** (Py) | Yes — `parse_content_stream()`, `TokenFilter` | Yes — `unparse_content_stream()` | ✅ **REWRITE** — recommended |
| **PyMuPDF / MuPDF** (Py/C) | Yes | Yes | ✅ REWRITE — ❌ **AGPL, rejected** |
| **mupdf.js / mupdf (npm)** | Yes | Yes | ✅ REWRITE — ❌ **AGPL, rejected** |
| **Apache PDFBox 3.0.8** (Java) | Yes — `PDFStreamParser` | Yes — `ContentStreamWriter` | ✅ REWRITE — Apache-2.0. Genuine runner-up, see below |
| **lopdf 0.44.0** (Rust) | Yes — `Content::decode` / `encode` | Yes | ✅ REWRITE — but no font layer |
| **pdf-lib / @cantoo/pdf-lib** (JS) | **No** | Append or wholesale-replace only | ❌ **APPEND ONLY** |
| **pdfjs-dist** (JS) | Reads for rendering; no operator API exposed | **No write API at all** | ❌ **READ ONLY** |
| **pypdf 6.15.0** (Py) | Partial token access | Fragile at the operator level | ⚠️ Not for this |
| **printpdf 0.12.5** (Rust) | Generation-focused | Limited | ❌ Generation, not editing |
| **pdf (pdf-rs) 0.10.0** (Rust) | Read + limited write | Limited | ❌ Less active (last release 2026-03) |
| **pdf-writer 0.15.0** (Rust) | Writer only | N/A | ❌ Writer only |
| **hayro 0.7.1** (Rust) | Renderer | N/A | ❌ Rasterizer, not editor |
| **oxidize-pdf 4.2.3** (Rust) | Claims both | Immature (51k lifetime downloads) | ❌ Too young to bet an engine on |
| Library | Decodes Type1 / TrueType / Type0-CID encodings + CMaps? |
|---|---|
| **playa-pdf** | ✅ Yes — recommended |
| **pdfminer.six 20260107** | ✅ Yes — older, slower, same lineage; acceptable fallback |
| **PDFBox** | ✅ Yes |
| **PyMuPDF** | ✅ Yes — AGPL |
| **pikepdf** | ❌ No — raw objects only |
## The AGPL Trap (read this before anything else)
- `PyMuPDF` 1.28.2 — PyPI license field literally reads *"Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License"*
- `mupdf` (npm) 1.28.0 / `mupdf.js` — AGPL-3.0-or-later
- **Ghostscript** — same Artifex AGPL
- **`pdf2docx` 0.5.13** — MIT itself, but `requires_dist` includes `PyMuPDF>=1.26.7`. **The AGPL comes in through the dependency.** This is the trap most teams walk into, because pdf2docx is the default answer to "PDF to DOCX in Python."
## Alternatives Considered
| Recommended | Alternative | When the alternative is actually better |
|---|---|---|
| Python engine (pikepdf + playa + fontTools) | **Java: Apache PDFBox 3.0.8** | This is a close call and deserves honesty. PDFBox is the *only* single library with permissive licensing (Apache-2.0) that has **both** content-stream token rewrite (`PDFStreamParser`) **and** built-in font subsetting (`TTFSubsetter`, `PDType0Font` auto-subsets). Stirling-PDF's text editor proves it works in production. Choose it if the team is a Java shop. Rejected here because fontTools beats PDFBox's font layer on the hard cases — Type1/CFF parsing, CID re-encoding, subset merging — and that is precisely where this project lives. Also: the Python side has playa, pypdfium2, and Pillow with no equivalent-quality Java counterparts. |
| Python engine | **Rust: `lopdf` 0.44.0** | `lopdf` genuinely rewrites content streams and is MIT with 14.8M downloads. But it has *no font layer at all* — you would reimplement fontTools. Only sane if raw throughput becomes the binding constraint, which for a document-at-a-time editor it will not. |
| `playa-pdf` | **`pdfminer.six` 20260107** | Same author lineage, same font-decoding capability, MIT. Use if you hit a playa API gap — it is more battle-tested and has a wider surface. It is slower and single-process. |
| `@cantoo/pdf-lib` | **`qpdf-wasm` 0.1.0 (Apache-2.0, 2.2 MB)** | If you want the *server's exact* page-op semantics in the browser so client preview and server output are byte-identical. Costs a WASM download. Worth it only if preview/output divergence becomes a real bug source. |
| `pdfjs-dist` | **EmbedPDF (`@embedpdf/*` 2.15.0, PDFium WASM)** | Faster, more accurate rendering; headless React components; MIT on the npm packages. Two cautions: the repo has **mixed licensing** (Apache-2.0 plus a Fair Core License component for `cloudpdf/server`) so audit before adopting, and its 7.2 MB PDFium WASM is a real first-paint cost. pdf.js needs no WASM and has Mozilla's security process behind it, which matters more when the input is untrusted. |
| React + Vite SPA | **SvelteKit 5.56** | Smaller bundles, less ceremony. Fine choice. React wins only on ecosystem depth for the viewer/canvas layer. Do not agonize over this one. |
| Synchronous requests | **ARQ 0.28 + Redis** | Add when a single conversion exceeds ~60s. Keep payloads on tmpfs; put only job IDs in Redis. Redis holding document bytes would quietly break the no-retention promise. |
| `pypdfium2` | **`pdftoppm` (poppler)** | If you want one less Python C-extension. Slower. pypdfium2's license is cleaner (BSD/Apache vs GPL). |
## What NOT to Use
| Avoid | Why | Use Instead |
|---|---|---|
| **PyMuPDF / MuPDF / mupdf.js** | AGPL-3.0. Network clause triggers on SaaS. Commercial license $1.5k–$50k+. It is the *best technical tool for this job* and it is the one you cannot have. | pikepdf + playa-pdf + fontTools |
| **Ghostscript** | Same Artifex AGPL. Its usual jobs here — compress, PDF/A convert, flatten — all have permissive replacements. | pikepdf + Pillow (compress); pikepdf + fontTools (PDF/A, model on `pdftopdfa`) |
| **`pdf2docx`** | MIT wrapper, **AGPL dependency** (`PyMuPDF>=1.26.7`). Reads clean in a license scanner that only checks top-level packages. | `python-docx` + your own run map (which you already have from the editor) |
| **`pdf-lib` 1.17.1 (original)** | **Last published 2021-11-06.** 41M downloads/month of an unmaintained package with 317 open issues. Repo last pushed 2024-07. | `@cantoo/pdf-lib` 2.8.1 — MIT, published 2026-07-30, actively maintained |
| **`@pdf-lib/fontkit` 1.1.1** | Published 2020. If you use the cantoo fork, take its bundled font handling, not this. | `fontkit` 2.0.4 for JS-side needs — but do font work **server-side in fontTools**, not in the browser at all |
| **pdf-lib (any fork) for text editing** | It is an **append-only** library. Reaching for it to "edit text" is how you end up with white-box overlay — the exact failure mode this project exists to avoid. | pikepdf, server-side, always |
| **`pdfjs-dist` for anything but rendering** | No write API. Also: its `getTextContent()` items are *rendering* groupings, not content-stream runs — they do not map 1:1 to the objects your server edits. | pdf.js for pixels; a **server-produced run map** for geometry and hit-testing |
| **Stirling-PDF** | Root `LICENSE` reads MIT, but explicitly carves out `engine/`, `app/proprietary/`, and `app/saas/` under separate licenses — and **`engine/` is where the text editor lives.** v1.0.0 moved to open-core ("may not use in production, at scale, or for business-critical processes" without a subscription; ~$99/mo server tier). Also now a **direct competitor** — 2.1.0 shipped a PDF text editor. | Read it as prior art. Do not vendor it. A top-level "MIT" reading is misleading for exactly the part you would want. |
| **LibreOffice for PDF→DOCX** | Its PDF import routes through **Draw**, producing a page of disconnected text frames, not paragraphs. Headers/footers/page numbers vanish. `--infilter="writer_pdf_import"` improves it and still does not make it good. | `python-docx` + your run map. Keep LibreOffice for **DOCX→PDF**, where it is genuinely strong. |
| **`pdf2htmlEX`** | No longer actively developed; maintainers wanted. Community forks only. | Generate HTML from your run map (you already have positions), or `pdftohtml` from poppler 26.04 |
| **Next.js** | Serverless function body limit is **4.5 MB** — a hard wall for a PDF upload product. SSR buys nothing for a single-page document editor; there is nothing to index but a landing page. It pushes you toward presigned-S3 upload, which is the wrong architecture here (below). | React + Vite SPA, FastAPI serving the API. Static marketing page separately if needed. |
| **Presigned S3 direct upload** | The 2026 default advice — and **wrong for this product.** It puts user documents in object storage under a lifecycle policy, turning "deleted immediately" into "deleted eventually." That contradicts the stated product promise. | Stream multipart straight into FastAPI, process on tmpfs, `unlink` in a `finally`. Cap upload size, cap request duration. |
| **`oxidize-pdf`, `printpdf`, `pdf-rs` for the engine** | Immature / generation-only / low activity respectively. | pikepdf |
## Export Paths — blunt quality assessment
| Export | Tool | Honest quality | Notes |
|---|---|---|---|
| **PDF → PNG/JPEG @ DPI** | `pypdfium2` 5.12.1 | **Excellent** | Chrome's renderer. Solved problem. Ship first. |
| **PDF split / merge / rotate** | `pikepdf` | **Excellent** | qpdf preserves everything it doesn't touch. |
| **PDF compress** | `pikepdf` (object streams, dedupe) + `Pillow` (downsample + re-JPEG image XObjects) | **Good** | Roughly Ghostscript-equivalent for image-heavy docs, and no AGPL. You write ~100 lines instead of shelling out. |
| **PDF flatten** | `pikepdf` (annotation appearance streams → page content) | **Good** | Well-defined operation. |
| **PDF → text** | `playa-pdf` | **Good** | Free — it is the same run map the editor uses. Fails on scanned pages, which you already detect and refuse. |
| **PDF → Markdown** | your run map + heuristics (font size → heading level, x-position → list) | **Fair.** Be honest in the UI. | Structure inference from glyph positions is the reflow problem in miniature. Headings and paragraphs work; tables and columns degrade. |
| **PDF → HTML** | your run map → absolutely-positioned spans; or `pdftohtml` | **Fair to Good** | Absolute positioning is visually faithful and semantically worthless. That is the honest trade and it is fine. |
| **PDF → PDF/A** | `pikepdf` + `fontTools` (embed all fonts, set OutputIntent/ICC, XMP metadata), validate with `veraPDF` | **Good, but the most work of any export** | Model directly on [`pdftopdfa` 0.9.0](https://github.com/iRedPaul/pdftopdfa) (MPL-2.0) — it does exactly this, Ghostscript-free, with veraPDF integrated. Gate on veraPDF passing. |
| **PDF → DOCX** | `python-docx` + run map | **Poor to Fair — as PROJECT.md already predicted** | Every path is bad. pdf2docx is the best of them and is AGPL-tainted. LibreOffice produces frame soup. Rolling your own from the run map at least gives you *control* over the degradation and adds no dependency. Sequence last, label "best-effort" in the UI, and cap ambition at: paragraphs, headings, bold/italic, images. Not tables. |
## Stack Patterns by Variant
- Do it entirely in the browser with `@cantoo/pdf-lib` and let the user download without ever contacting the server.
- Because it is instant, and "your file never left your browser" is a *stronger* privacy claim than "we deleted it." Make the UI say which mode happened. This is the cheapest marketing asset in the product.
- Send the **operation log**, not the mutated file, to the server. The server replays all ops canonically with pikepdf.
- Because two engines mutating the same bytes will diverge, and reconciling client pdf-lib output against server pikepdf output is a bug source with no upside. One canonical writer.
- Add ARQ + Redis, with document bytes on tmpfs and only job IDs in Redis.
- Before then, synchronous request/response with a hard timeout. A queue is durable state, and durable state is the enemy of a no-retention promise.
- Budget a full phase. Gate merge on veraPDF passing against a fixture corpus, not on spot checks.
- Because PDF/A has many conformance levels and font-embedding rules that only a validator catches.
## Version Compatibility
| Package | Compatible with | Notes |
|---|---|---|
| `pikepdf 10.11.0` | Python ≥3.10; bundles qpdf 12.x | Pin `pikepdf<11` if following pdftopdfa's tested combination. |
| `fontTools 4.63.0` | Python ≥3.10 | Pure Python; `[ufo,woff,unicode]` extras add C deps you do not need. |
| `pypdfium2 5.12.1` | Python ≥3.8 | Major-version bumps track PDFium releases and *do* break APIs. Pin exactly. |
| `pdfjs-dist 6.x` | ESM only; Node ≥22 (or `Promise.withResolvers` polyfill) | Worker file is `.mjs`. `renderTextLayer` is removed — use the `TextLayer` class. Vite needs explicit worker URL config. |
| `@cantoo/pdf-lib 2.8.1` | Node ≥18, browsers | Drop-in for `pdf-lib` 1.17 API plus fixes. |
| `uharfbuzz 0.56.0` | Python ≥3.9 | Wheels for all platforms; no HarfBuzz system install needed. |
| LibreOffice / veraPDF / poppler | Subprocess only | Pin exact versions in the Dockerfile — output differs across versions and your golden tests will drift. |
## Confidence
| Claim | Confidence | Basis |
|---|---|---|
| pikepdf can rewrite content streams at the operator level | **HIGH** | Context7 `/pikepdf/pikepdf` — verbatim test-suite code using `parse_content_stream` + `unparse_content_stream` to strip `Tj` and rewrite the page |
| PyMuPDF/MuPDF/Ghostscript AGPL triggers on SaaS | **HIGH** | PyPI license field verbatim; Artifex licensing pages state the SaaS clause explicitly |
| pdf2docx inherits AGPL via PyMuPDF | **HIGH** | PyPI `requires_dist` for pdf2docx 0.5.13 lists `PyMuPDF>=1.26.7` |
| pdf-lib is unmaintained | **HIGH** | npm registry: latest 1.17.1 published 2021-11-06; GitHub last push 2024-07, 317 open issues |
| All version numbers | **HIGH** | Queried live from PyPI / npm / crates.io / GitHub on 2026-08-11 |
| fontTools is the leader for subsetting | **HIGH** | Context7 fontTools docs; corroborated by pdftopdfa, fpdf2, PDFBox-adjacent tooling all depending on it |
| playa-pdf decodes font encodings and gives glyph geometry | **MEDIUM-HIGH** | Project README verified directly; less independent third-party corroboration than pdfminer.six. **Prototype against 3–4 real-world PDFs in Phase 1 before committing** — pdfminer.six is the drop-in fallback |
| PDFBox is a viable single-language alternative | **MEDIUM** | Javadoc for `PDFStreamParser` verified; Stirling-PDF's editor is existence proof. Not hands-on validated here |
| DOCX/Markdown/HTML export quality ratings | **MEDIUM** | Consistent across multiple secondary sources; not independently benchmarked |
| Liberation fonts are metric-compatible with the MS core fonts | **MEDIUM-HIGH** | Well-established and the stated design goal of the project; verify empirically against your fixture corpus, since it is load-bearing for "no visible shift" |
## Gaps for phase-specific research
- **TJ-array reconstruction algorithm.** No library hands you "fit this string into this run's width." You will write it: shape with uharfbuzz → compare against original run advance → distribute the delta across the TJ array. Prototype early; it is the core value.
- **Encrypted / permission-restricted PDFs.** pikepdf handles standard security handlers, but the product policy on "user uploads a locked file" is undecided.
- **Ligature and kerning-split runs.** `pypdf_strreplace`'s author is candid that replacements "only succeed in very specific circumstances" when kerning splits words across TJ elements. Expect this to be the top source of edge-case failures.
- **Type3 fonts and PDFs with no ToUnicode CMap.** Text is visible but unmappable to characters. Needs the same clear-refusal UX as scanned pages.
## Sources
- Context7 `/pikepdf/pikepdf` — content-stream parsing, TokenFilter, stream reconstruction — **HIGH**
- Context7 `/websites/fonttools_readthedocs_io_en` — `Subsetter`, glyph-order remapping, notdef handling — **HIGH**
- https://pikepdf.readthedocs.io/en/latest/topics/content_streams.html — parser vs. filter, rewrite guidance — **HIGH**
- https://mupdf.readthedocs.io/en/1.27.2/license.html + https://artifex.com/licensing — AGPL SaaS clause — **HIGH**
- https://pypi.org/pypi/pymupdf/json — dual-license string verbatim — **HIGH**
- https://pypi.org/pypi/pdf2docx/json — `requires_dist` showing PyMuPDF — **HIGH**
- https://github.com/qpdf/qpdf — Apache-2.0 confirmed verbatim — **HIGH**
- https://github.com/dhdaines/playa — capability, license, read-only status — **MEDIUM-HIGH**
- https://github.com/iRedPaul/pdftopdfa + PyPI metadata — Ghostscript-free PDF/A reference architecture — **HIGH**
- https://fonttools.readthedocs.io/en/latest/subset/ — subsetting options — **HIGH**
- https://uharfbuzz.readthedocs.io/ + fpdf2 text-shaping docs — `x_advance`, TJ kerning derivation — **MEDIUM-HIGH**
- https://github.com/Stirling-Tools/Stirling-PDF/discussions/4332 — license change to open-core — **MEDIUM-HIGH**
- https://github.com/hoehermann/pypdf_strreplace — prior art; candid limitations on subset fonts and kerning — **MEDIUM**
- javadoc.io `PDFStreamParser` (PDFBox 3.x) — token-level rewrite capability — **MEDIUM**
- Nutrient / react-pdf / EmbedPDF comparisons — client rendering landscape — **MEDIUM (vendor-adjacent, treated as directional)**
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
