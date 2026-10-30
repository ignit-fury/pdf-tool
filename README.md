# PDF Tool

A browser-based PDF editor that edits the **actual existing content** of a PDF — replacing text inside the page's content stream rather than pasting annotations or white boxes on top. The current browser supports opening a PDF, editing individual text runs, finding and replacing text across all pages, changing colour or font style, organizing pages, merging PDFs and images, undoing changes and exporting PDFs, page images, plain text, Markdown, HTML, supported PDF/A-2b copies and best-effort DOCX. It is aimed at people who need to change a document that already exists and want the result to look untouched.

It is a real product for other people, used anonymously — no signup to edit a file.

**Core Value:** Replace text across every page of an existing PDF and have the output look like nothing happened. If everything else on this list fails, this one capability must work.

## Architecture

Hybrid client/server — rendering, text selection, original-byte retention and downloads run in the browser. Content indexing, text rewrites and font work run in isolated server workers. Page insertion, reorder, rotation, deletion, PDF merge and PNG/JPEG/WebP placement run in the browser. HEIC conversion is a separate, explicitly chosen image-only server action; production conversion remains disabled until Linux confinement is verified.

Page-image export and splitting also run in the browser. Compression, annotation/form flattening, text/Markdown/HTML, PDF/A and DOCX use isolated server workers after explicit actions. DOCX review and conversion each upload the current PDF separately; reviewing does not create a download. Exports preserve the working PDF and its Undo history.

Editing uses genuine content streams. Preserve-layout edits occupy the original run's
space. Flexible text boxes replace a selected source run with native wrapped text;
surrounding PDF content stays fixed and collision checks protect it.

## Privacy model

Ephemerality is a **structural property**, not a retention policy. "The server has no state whose loss is observable" — testable by killing the cache mid-session and having the session survive.

- Client holds the authoritative bytes.
- The server cache is content-addressed and evictable at any moment.
- Scratch is tmpfs.
- Queues carry opaque handles, never document bytes.
- No document content in logs or error reports.

The novel user-facing claim is **per-operation local/server disclosure** — the UI shows which actions stay in the browser and which don't. Deletion windows are table stakes (every competitor claims 1–2 hours) and privacy reviewers discount them.

**Never claim** "files never leave your device," "we never see your file," or "deleted immediately" without stating the mechanism. The first is false for the text engine and is the claim users check.

## Licensing constraints

No AGPL anywhere in the runtime dependency tree, **including transitively** — CI must fail on AGPL in the resolved lockfile, not top-level metadata. This rules out PyMuPDF, mupdf.js, and Ghostscript.

GPL/LGPL permitted only as a subprocess with a file-in/file-out interface (GPL triggers on distribution, and a hosted service distributes nothing). This keeps Poppler and veraPDF available. AGPL permitted only in CI and dev tooling no served request can reach.

**Known trap:** `pdf2docx` is MIT at the top level and pulls `PyMuPDF>=1.26.7` transitively. A license scanner that only checks top-level packages will miss it. The project generates direct stdlib OOXML from its own shared run map instead.

## Tech stack

| Half of the problem | What it requires | Library |
|---|---|---|
| **Read** — "what text is where, in which font, at which glyph code?" | Decode Type1/TrueType/Type0-CID encodings, resolve CMaps, get per-glyph position + advance | `playa-pdf` (MIT) |
| **Write** — "swap these operators and re-serialize the page" | Parse `Tj/TJ/'/"` into tokens, modify, unparse, save without corrupting the object graph | `pikepdf` (MPL-2.0) over `qpdf` (Apache-2.0) |
| **Fonts** — "the new character isn't in the embedded subset" | Parse the embedded font program, subset a bundled font, re-embed with correct widths + CMap | `fontTools` (MIT) + `uharfbuzz` (Apache-2.0) |

### Core dependencies

| Technology | Version | License | Purpose |
|---|---|---|---|
| Python | 3.13.x | PSF | Engine language |
| pikepdf | 10.11.0 | MPL-2.0 | Object model + content-stream rewrite |
| qpdf | 12.4.0 | Apache-2.0 | C++ engine under pikepdf |
| playa-pdf | 1.1.0 | MIT | Font encoding decode, glyph positions |
| fontTools | 4.63.0 | MIT | Font parsing + subsetting + re-embedding |
| uharfbuzz | 0.56.0 | Apache-2.0 | Shaped advance widths |
| pypdfium2 | 5.12.1 | BSD-3-Clause / Apache-2.0 | Server-side rasterization |
| FastAPI | 0.141.1 | MIT | HTTP layer |
| uvicorn | 0.52.1 | BSD-3 | ASGI server |
| @cantoo/pdf-lib | 2.9.1 | MIT | Client-side page ops |
| pdfjs-dist | 6.2.108 | Apache-2.0 | Browser rendering |
| React | 18.3.1 | MIT | UI |
| Vite | 5.4.21 | MIT | Build |

### Bundled fonts

| Family | License | Why |
|---|---|---|
| Liberation (Sans/Serif/Mono) | SIL OFL 1.1 | Metric-compatible with Arial/Times/Courier. When the original PDF used a Base-14 or Microsoft core font, Liberation substitutes with identical advance widths — replacement text lands in the same place with zero fitting work. |

## Current stage

Phase 3's rewrite engine is integrated into this checkout. Phase 4 implements a browser
viewer and single-run editor with text/style preview, PDF download and recipe-level undo.
Phase 5 adds all-page search, per-occurrence exclusions, exact replacement review,
one atomic batch apply and one-step undo through the same content-stream engine.
Phase 6 adds local page tools, PDF merge with independent embedded fonts and preserved forms/bookmarks, image placement, and one mixed page/text Undo history. Opening and organizing a PDF do not upload it; text analysis starts only when chosen.
Phase 7 adds page-image exports at chosen DPI, PDF splitting, structural compression with optional previewed image reduction, annotation/form flattening, and text/Markdown/HTML from the shared run index.
Phase 8 adds conservative native PDF/A-2b conversion and optional direct OOXML DOCX export. PDF/A refuses unsupported content rather than substituting fonts or rasterizing pages. DOCX first shows findings for the current document, then requires a separate conversion action. It supports single-column body text, detected headings, bold/italic, supported inline images and ruled tables. Complex layouts become plain paragraphs; fonts and pagination may change. It does not reconstruct headers/footers or perform OCR.
The editor uses the actual content stream. Unsupported edits are refused explicitly.

Implemented: password-protected PDFs, signature warnings, server-issued edit boxes,
selectable browser text, progressive thumbnails/classification, bold/italic and colour,
immutable-source replay, cache-loss recovery and isolated parser workers. Font-size shrink/equal and bounded character spacing are supported within the original
run geometry. In Preserve layout, source size growth and multiline rewriting are refused because
neighboring content stays fixed. Flexible text box provides the validated wrapping/
growth alternative described below, without moving unrelated content.
Shorter replacements can leave unused space after the new text while preserving the
following text's position; they do not need to be stretched to the original width.
Edits using stateful quote operators or unsupported Unicode shaping are also refused to
preserve layout and searchable text. Precomposed accents such as `é` remain supported.

Built-in OCR remains deferred. The current screen links to OCRmyPDF's external guide without uploading the
PDF there. The OCR interest counter collects no document or contact data.

## Document viewer upgrade

The page is now the primary editing surface. Its contextual toolbar offers detected
font information, bundled font selection, safe font size/spacing, color/hex, bold and
italic, with Preview/Apply/Cancel. Reading/copying remains available without analysis.
Page tools, search and exports use optional panels. At narrow widths the top action
row scrolls horizontally; choosing page text returns focus to the document.

**Insert image** accepts PNG/JPEG/WebP in this browser. Images added by this editor
can be selected, moved/resized using handles or numeric controls, rotated, replaced
at the same geometry and removed with confirmation. Aspect ratio is locked by default.
Original unowned/shared PDF images remain preserved and are not offered for mutation.

**Insert text** creates a native, searchable text container directly on a page.
It supports explicit line breaks, wrapping, larger/smaller text, bundled font
selection, color, bold/italic, alignment and character/line/paragraph spacing.
Change its dimensions or page in the contextual toolbar. Preview uploads the
current PDF and draft through the isolated worker; Apply publishes those exact
candidate bytes as one Undo/Redo operation. Cancel preserves the working PDF.
The default overlap check includes rendered content and annotation bounds. Overflow
offers explicit height expansion when it fits; text is never silently clipped.
Use **Text boxes → Load inserted text boxes** to select/edit/remove verified boxes
after reopening. A box rotated with its page can be removed or edited after rotating
the page back. Newly inserted boxes on already rotated pages are upright/editable.

Original preserve-layout text edits can be longer or shorter when they fit,
including by choosing a smaller size. When a longer replacement exceeds the
original run's width, Preview opens an expandable draft with the original text
and visible font/size disclosure; no PDF change occurs until its separate
Preview and Apply. You can also choose **Expand text box** or **Layout →
Flexible text box** for wrapping and growth. Entering/pasting line breaks switches
there automatically without losing the draft or caret; pasted tabs use four spaces.
The selected original run is genuinely removed through the validated writer, and
the new native layout includes all prior committed edits. Preview shows the complete
candidate; Apply is one Undo action. Cancel leaves the working PDF unchanged.
**Grow height to fit text** is enabled by default for new/selected managed boxes.
Both the typing surface and validated PDF can grow; the PDF uses actual font metrics.
The selected bundled replacement font is disclosed before Apply.
For a source word split into an oversized initial letter and smaller remaining
letters, flexible replacement retains those two point sizes in the native PDF
text box. It uses one bundled replacement font when the source font program is
unavailable; the exact preview shows the substitution before Apply.
Arbitrary multirun paragraph reconstruction and automatically moving neighboring
content remain unavailable. Growth must fit free space; move/widen the box, choose
another page or reduce the font if it cannot fit. No text is silently clipped.
Missing glyphs, complex shaping and unsafe ownership refuse explicitly. Ordinary
text-run edits cannot rewrite managed containers; select the complete text box.

[Implementation plan](docs/superpowers/plans/2026-10-29-document-viewer.md) and
[verification, known limits and browser reproduction](docs/verification/document-viewer-2026-10-29.md)
record the actual local results. No new dependency or migration is required.
The next-stage [native text-box plan](docs/superpowers/plans/2026-10-29-native-text-boxes.md)
and [verification report](docs/verification/native-text-boxes-2026-10-29.md)
document the added layout support and its limits.

**Outline** reads the current PDF's bookmarks locally. Expand nested sections and
choose an internal destination to navigate while keeping your zoom. External links,
document scripts and attachment actions are not opened. Large/deep outlines show a
bounded portion with a notice. Opening Outline or History pauses further automatic
text analysis; choose **Edit text** or **Find and replace** to resume it explicitly.

**History** lists the original document, applied changes, the current state and
undone changes available to redo. Choose any retained state to restore its exact PDF
in one operation; intermediate states are not rendered or uploaded. New successful
edits clear the undone future. History is retained only in memory while the document
is open and uses the existing memory/entry limits. Failed or canceled restores leave
the document and timeline unchanged.
See the [navigation plan](docs/superpowers/plans/2026-10-29-document-navigation.md)
and [verification report](docs/verification/document-navigation-2026-10-29.md).

Find now highlights the selected substring using measured PDF.js text-layer ranges,
including repeated words within one run, normalized accents, zoom and rotated pages.
Ambiguous or unavailable mappings show a dashed area labeled **Approximate text area**.
Highlights are temporary viewer elements and never become PDF annotations or exports.
The batch walkthrough highlights the actual committed replacement spans, labels
removed-text locations, and waits for each result to render before advancing.
Changing the query or document clears stale ranges. Search/page scrolling stays
inside the document viewport so the top toolbar remains visible.
See the [highlight plan](docs/superpowers/plans/2026-10-29-search-highlights.md)
and [verification and limits](docs/verification/search-highlights-2026-10-29.md).
The [source-expansion plan](docs/superpowers/plans/2026-10-29-source-text-expansion.md)
and [verified fix](docs/verification/source-text-expansion-2026-10-29.md) document
the original-text workflow and its safety boundaries.

## How to run

Python 3.13+ and Node 22.13+ are required. From the repository root:

```bash
uv sync --locked
cd client
npm ci
npm run build
cd ..
uv run uvicorn server.app:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open <http://127.0.0.1:8000>. The FastAPI service serves the built client and all pdf.js
assets on the same origin. Pages scroll continuously; only nearby page canvases are kept
mounted. Choose **Edit text → Analyze text**, click a run directly on its page, edit in
place, preview its fit, then apply. Source-issued IDs remain authoritative; PDF.js text
is used for reading/selection rather than inventing rewrite addresses.
Undo/Redo restores exact mixed document snapshots, including text, pages and images.
Repeated edits to one run replace that run's operation instead of creating duplicate
addresses. Ctrl/Cmd+Z and Shift+Ctrl/Cmd+Z work outside native text inputs.

Choose **Find and replace** to index every page. Search defaults to case-insensitive
substring matching; Match case and Unicode whole-word options are available. Results
show page/context and individual inclusion checkboxes. Unreplaceable occurrences stay
visible with their reasons. Stop/resume and failed-page retry preserve honest partial
counts; replacements require a complete index.

Enter replacement text, optionally choose a fallback font, then select **Preview
Replace One** for the current match or **Preview Replace All** for included matches. The exact remaining full recipe must pass the server's fit checks
before **Replace One** or **Replace All** becomes available. Empty replacement removes included matches and
shows a warning. One Undo or Ctrl/Cmd+Z outside text inputs restores the entire batch,
including earlier text/style choices. Search is local over the server-produced index;
indexing, preview and text replacement use the server. After a batch applies atomically,
a pausable, reduced-motion-aware walkthrough highlights actual accepted results. Stopping
the walkthrough keeps the completed batch; Undo restores it once.

For frontend development, run the API on port 8000 and `npm run dev` in `client/`;
Vite proxies API routes. Opening, reading and page/image operations stay local.
Text analysis and editing upload only after explicit actions; rendering and PDF download
happen locally. Original bytes and passwords stay in browser memory while open, with
passwords sent to the worker when needed. Closing/reloading clears the browser session.
The client transports passwords as UTF-8/base64 in `X-PDF-Password-B64` so Unicode and
whitespace survive HTTP header handling. Base64 is encoding; TLS is required publicly.

### Production container

```bash
docker build -t pdf-tool .
docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /dev/shm:rw,nosuid,nodev,size=1536m --memory 3g --pids-limit 64 \
  -p 127.0.0.1:8000:8000 pdf-tool
```

Use TLS and an appropriately configured reverse proxy for a public deployment. The
server enforces bounded reads with deadlines, concurrent-request/worker caps, no-store
headers and a CSP without JavaScript `unsafe-eval`. Linux workers enforce CPU/address
space limits and seccomp network/process restrictions; production scratch must be tmpfs.
macOS development cannot provide the Linux memory/seccomp/tmpfs guarantees. Container,
Linux and live CDN checks must pass before claiming public-release readiness.

The memory cache is capped at 128 MiB, expires sources after 10 minutes and can be cleared
at any point. A missing source returns `409 SOURCE_MISSING`; the browser reuploads its
original bytes and retries once. No document bytes are placed in queues/object stores,
no password/filename is stored in the cache, and no undo history is held server-side.

### Engine CLI

```bash
uv run python tools/pdftool.py index path/to/document.pdf
uv run python tools/pdftool.py index path/to/document.pdf --page 0
uv run python tools/pdftool.py edit path/to/document.pdf --recipe recipe.json -o edited.pdf
```

A recipe is an array of `{ "run_id": "server-issued-id", "new_text": "replacement" }`.
Optional `style` supports RGB `color` values from 0 to 1, boolean `bold`/`italic`,
`font_size` from 1–512 (shrink/equal only), and `character_spacing` from 0–10pt.
Unsupported font state, growth, multiline text, shaping and overflow refuse atomically.
The inspector displays the detected source font. Choose a replacement when automatic
matching is unavailable, or intentionally change the typeface: Liberation Serif, Sans,
or Mono. Recipes express this as `style.font_family: "Serif" | "Sans" | "Mono"`.
An explicit choice works with unknown source font names and replaces embedded originals;
glyph coverage, searchable Unicode, width fitting and safe geometry are still checked.
`--dry-run` reports fit/refusal without writing. Edits replay atomically against the
original bytes, and stale source hashes are refused.

### Verification

```bash
uv run --frozen pytest -q
uv run --frozen mypy engine/ server/
uv run --frozen python tools/license_gate.py
npm --prefix client test
npm --prefix client run build
uv run --frozen python tools/build_search_unicode.py --check
```

The full PDF/A and optional-module removal gates also require the authenticated
dev/CI veraPDF CLI and Java. Set `VERAPDF_CMD` to its executable; the mandatory
`Harness / pdfa-g7a` workflow installs the pinned CLI with digest/signature checks
and runs both complete gate files. The validator is never called by a served request.

Full corpus checks require `qpdf`, `pdftoppm` and `mutool`; these test renderers belong
only in CI/dev. The OpenType Sanitizer dev wheel supplies the font gate executable.
`Dockerfile.ci` provides pinned renderer versions. Linux-only tests are explicit skips
on macOS; live CDN tests require `PDF_TOOL_DEPLOYMENT_URL`. Browser journey evidence
and remaining release checks are recorded in the Phase 4 verification report. Phase 5
local batch/browser evidence is in
[05-G4-RESULTS.md](.planning/phases/05-find-and-replace-across-all-pages/05-G4-RESULTS.md).
Its 40-page public technical-document proxy does not establish literal contract-source
coverage. Phase 6 browser/network and independent native fidelity evidence is in
[06-G5-RESULTS.md](.planning/phases/06-page-ops-and-merge/06-G5-RESULTS.md), including
unchanged source-baseline renderer discrepancies and production HEIC limitations.
Phase 7 implementation, browser downloads and independent native export proof are in
[07-G6-RESULTS.md](.planning/phases/07-exports/07-G6-RESULTS.md).
Phase 8 local conformance, actual DOCX downloads and literal writer-removal proof are in
[08-G7-RESULTS.md](.planning/phases/08-pdf-a-then-docx/08-G7-RESULTS.md).
Hosted G7a CI and Word/Acrobat observations remain unperformed.
No deployment or public-release sign-off is implied.

## Corpus testing

Two-tier corpus of real-world PDFs used to validate the engine's structural handling.

- **Public tier** (`corpus/public/`): committed to the repo, git-lfs tracked, runs on every PR including fork PRs with no CI secrets. Every structural category required by the conformance design has at least one public-tier example. See `corpus/README.md` for the full schema and list of the 15 canonical categories.
- **Private tier**: never committed. Holds real invoices and contracts that carry third-party personal data. Fetched from a bucket via CI secrets, gates `main` and release branches, and is skipped where credentials are absent. The private tier adds volume and real-world messiness — never unique structural categories.

The public tier contains more than 200 PDFs; the manifest is the authoritative inventory. Every file was individually structurally verified via `pikepdf` object introspection and, for rendering-dependent categories, a `pypdfium2` visual spot-check, rather than added to pad the count.

Testing tools:
- `tools/probe_corpus.py` — walks the corpus through the engine pipeline and reports per-category coverage.
- `tools/check_corpus_size.py` — mechanical floor check: combined public + private manifest entry count must reach 100 before the corpus gate can be signed off.
- `corpus/validate_manifest.py` — re-verifies sha256 + zero-count-category check against the manifest+corpus pair.

## Project structure

```
pdf-tool/
├── README.md              # this file
├── pyproject.toml         # Python deps (pikepdf, playa-pdf, fontTools, etc.)
├── uv.lock                # pinned lockfile
├── tools/
│   ├── pdftool.py         # Engine CLI (index and edit)
│   ├── probe_corpus.py    # Corpus coverage probe
│   ├── check_corpus_size.py
│   ├── license_gate.py    # AGPL gate for CI
│   └── ...
├── tests/                 # pytest suite
├── corpus/
│   ├── README.md          # Corpus design, schema, categories
│   ├── manifest.json      # Public-tier manifest
│   ├── public/            # Committed public-tier PDFs (git-lfs)
│   └── validate_manifest.py
└── client/                # React/Vite SPA (separate repo or subdirectory)
```

## Implemented export paths and limits

| Export | Tool | Quality |
|---|---|---|
| PDF → PNG/JPEG @ DPI | PDF.js in the browser | Rendered pages at selected DPI |
| PDF split / merge / rotate | @cantoo/pdf-lib in the browser | Native page content; conservative safety checks |
| PDF compress | pikepdf + Pillow | Good |
| PDF flatten | pikepdf | Good |
| PDF → text | playa-pdf | Good (free; same run map the editor uses) |
| PDF → Markdown | run map + heuristics | Fair — be honest in the UI |
| PDF → HTML | shared blocks → semantic HTML | Best effort; complex layouts may degrade |
| PDF → PDF/A-2b | pikepdf + fontTools; veraPDF in dev/CI | Audited embedded-font/RGB-gray subset; other content refused; hosted gate pending |
| PDF → DOCX | shared blocks → direct stdlib OOXML | Best effort within the written ceiling; explicit review before conversion |

## What NOT to use

- **PyMuPDF / MuPDF / mupdf.js** — AGPL-3.0. Network clause triggers on SaaS.
- **Ghostscript** — Same Artifex AGPL. Its usual jobs here all have permissive replacements.
- **pdf2docx** — MIT wrapper, AGPL dependency (PyMuPDF).
- **pdf-lib (original 1.17.1)** — Last published 2021-11-06. Unmaintained. Use `@cantoo/pdf-lib` 2.9.1 instead.
- **pdf-lib (any fork) for text editing** — Append-only library. Reaching for it to "edit text" produces white-box overlay — the exact failure mode this project exists to avoid.
- **Stirling-PDF** — Root LICENSE reads MIT, but `engine/` is separately licensed under open-core terms. Also now a direct competitor.
- **Next.js** — Serverless function body limit is 4.5 MB — a hard wall for a PDF upload product.
- **Presigned S3 direct upload** — Wrong for this product. Puts user documents in object storage under a lifecycle policy, turning "deleted immediately" into "deleted eventually."

## License

The engine dependencies are MPL-2.0, MIT, Apache-2.0, BSD-3-Clause, and PSF. See `pyproject.toml` for the full resolved list.
