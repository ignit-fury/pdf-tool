# PDF Tool

A browser-based PDF editor that edits the **actual existing content** of a PDF — replacing text inside the page's content stream rather than pasting annotations or white boxes on top. The current browser supports opening a PDF, editing individual text runs, finding and replacing text across all pages, changing colour or font style, organizing pages, merging PDFs and images, undoing changes and exporting PDFs, page images, plain text, Markdown or HTML. PDF/A and DOCX are planned for Phase 8. It is aimed at people who need to change a document that already exists and want the result to look untouched.

It is a real product for other people, used anonymously — no signup to edit a file.

**Core Value:** Replace text across every page of an existing PDF and have the output look like nothing happened. If everything else on this list fails, this one capability must work.

## Architecture

Hybrid client/server — rendering, text selection, original-byte retention and downloads run in the browser. Content indexing, text rewrites and font work run in isolated server workers. Page insertion, reorder, rotation, deletion, PDF merge and PNG/JPEG/WebP placement run in the browser. HEIC conversion is a separate, explicitly chosen image-only server action; production conversion remains disabled until Linux confinement is verified.

Page-image export and splitting also run in the browser. Compression, annotation/form flattening, and text/Markdown/HTML exports use isolated server workers after an explicit export action. Exports use the current edited PDF and preserve its Undo history.

Editing is **content-stream only**. No white-box overlays. No reflow across lines or pages — replaced text occupies the original text run's space.

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

**Known trap:** `pdf2docx` is MIT at the top level and pulls `PyMuPDF>=1.26.7` transitively. A license scanner that only checks top-level packages will miss it. The project uses `python-docx` + its own run map instead.

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
| @cantoo/pdf-lib | 2.8.1 | MIT | Client-side page ops |
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
The editor uses the actual content stream. Unsupported edits are refused explicitly.

Implemented: password-protected PDFs, signature warnings, server-issued edit boxes,
selectable browser text, progressive thumbnails/classification, bold/italic and colour,
immutable-source replay, cache-loss recovery and isolated parser workers. Font-size
changes are refused because replacements must fit the original run width.
Shorter replacements can leave unused space after the new text while preserving the
following text's position; they do not need to be stretched to the original width.
Edits using stateful quote operators or unsupported Unicode shaping are also refused to
preserve layout and searchable text. Precomposed accents such as `é` remain supported.

PDF/A, DOCX and built-in OCR are later milestones. The current screen links to OCRmyPDF's external guide without uploading the
PDF there. The OCR interest counter collects no document or contact data.

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
assets on the same origin. Select a text run, preview its fit, then apply and download.
Undo restores the previous whole recipe, including text and style. Repeated edits to
one run replace that run's operation instead of creating duplicate addresses.

Choose **Find and replace** to index every page. Search defaults to case-insensitive
substring matching; Match case and Unicode whole-word options are available. Results
show page/context and individual inclusion checkboxes. Unreplaceable occurrences stay
visible with their reasons. Stop/resume and failed-page retry preserve honest partial
counts; replacements require a complete index.

Enter replacement text, optionally choose a fallback font, then select **Preview
replacements**. The exact remaining full recipe must pass the server's fit checks
before **Replace** becomes available. Empty replacement removes included matches and
shows a warning. One Undo or Ctrl/Cmd+Z outside text inputs restores the entire batch,
including earlier text/style choices. Search is local over the server-produced index;
indexing, preview and text replacement use the server.

For frontend development, run the API on port 8000 and `npm run dev` in `client/`;
Vite proxies API routes. Opening a file uploads it for analysis; rendering and download
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
Optional `style` supports RGB `color` values from 0 to 1 and boolean `bold`/`italic`.
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

## Planned export paths — honest quality

| Export | Tool | Quality |
|---|---|---|
| PDF → PNG/JPEG @ DPI | pypdfium2 | Excellent (Chrome's renderer) |
| PDF split / merge / rotate | pikepdf | Excellent |
| PDF compress | pikepdf + Pillow | Good |
| PDF flatten | pikepdf | Good |
| PDF → text | playa-pdf | Good (free; same run map the editor uses) |
| PDF → Markdown | run map + heuristics | Fair — be honest in the UI |
| PDF → HTML | run map → absolutely-positioned spans | Fair to Good |
| PDF → PDF/A | pikepdf + fontTools, validate with veraPDF | Good, but the most work of any export |
| PDF → DOCX | python-docx + run map | Poor to Fair — best-effort, explicitly not pixel-faithful |

## What NOT to use

- **PyMuPDF / MuPDF / mupdf.js** — AGPL-3.0. Network clause triggers on SaaS.
- **Ghostscript** — Same Artifex AGPL. Its usual jobs here all have permissive replacements.
- **pdf2docx** — MIT wrapper, AGPL dependency (PyMuPDF).
- **pdf-lib (original 1.17.1)** — Last published 2021-11-06. Unmaintained. Use `@cantoo/pdf-lib` 2.8.1 instead.
- **pdf-lib (any fork) for text editing** — Append-only library. Reaching for it to "edit text" produces white-box overlay — the exact failure mode this project exists to avoid.
- **Stirling-PDF** — Root LICENSE reads MIT, but `engine/` is separately licensed under open-core terms. Also now a direct competitor.
- **Next.js** — Serverless function body limit is 4.5 MB — a hard wall for a PDF upload product.
- **Presigned S3 direct upload** — Wrong for this product. Puts user documents in object storage under a lifecycle policy, turning "deleted immediately" into "deleted eventually."

## License

The engine dependencies are MPL-2.0, MIT, Apache-2.0, BSD-3-Clause, and PSF. See `pyproject.toml` for the full resolved list.
