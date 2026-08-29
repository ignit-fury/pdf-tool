# PDF Tool

A browser-based PDF editor that edits the **actual existing content** of a PDF — replacing text inside the page's content stream rather than pasting annotations or white boxes on top. Users open a PDF, find-and-replace text across every page, insert blank pages, merge in images or other PDFs, restyle text with embedded fonts, and export to several formats. It is aimed at people who need to change a document that already exists and want the result to look untouched.

It is a real product for other people, used anonymously — no signup to edit a file.

**Core Value:** Replace text across every page of an existing PDF and have the output look like nothing happened. If everything else on this list fails, this one capability must work.

## Architecture

Hybrid client/server — light operations (page insert, reorder, rotate, merge, preview) run in the browser for instant feedback; heavy operations (content-stream text rewrite, font subsetting, format conversion) run on the server. Two code paths is the accepted cost of a responsive UI without shipping the whole engine as multi-megabyte WASM.

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
| React | 19.2.8 | MIT | UI |
| Vite | 8.2.1 | MIT | Build |

### Bundled fonts

| Family | License | Why |
|---|---|---|
| Liberation (Sans/Serif/Mono) | SIL OFL 1.1 | Metric-compatible with Arial/Times/Courier. When the original PDF used a Base-14 or Microsoft core font, Liberation substitutes with identical advance widths — replacement text lands in the same place with zero fitting work. |
| Noto Sans / Serif | SIL OFL 1.1 | Coverage fallback for anything Liberation lacks. |
| DejaVu | Bitstream Vera / free | Broad glyph coverage, permissive. |

## How to run

### Engine CLI

```bash
cd /Users/prempatel/Pictures/pdf-tool
uv sync
uv run python tools/pdftool.py index path/to/document.pdf
```

`tools/pdftool.py` is the CLI over the Phase 2 pipeline (`engine.index.RunIndex`). One subcommand, `index`:

- **No `--page`**: a per-page summary table (page number, run count, editable/substitution/not-editable counts, page bucket), iterating every page so `RunIndex`'s own cache/evict machinery runs as intended.
- **With `--page N`**: that page's run list (run ID, display text with synthetic spaces, verdict state, and reason only when state is `not_editable`).

### Server

```bash
cd /Users/prempatel/Pictures/pdf-tool
uv run uvicorn server.app:app
```

The server runs a FastAPI service. Heavy operations — content-stream text rewrite, font subsetting, format conversion — execute here.

### Client

```bash
cd client
npm run dev
```

A React/Vite SPA. Light operations (page insert, reorder, rotate, merge, preview) run in the browser via `@cantoo/pdf-lib` + `pdfjs-dist`. The client never edits content streams — that always goes to the server.

## Corpus testing

Two-tier corpus of real-world PDFs used to validate the engine's structural handling.

- **Public tier** (`corpus/public/`): committed to the repo, git-lfs tracked, runs on every PR including fork PRs with no CI secrets. Every structural category required by the conformance design has at least one public-tier example. See `corpus/README.md` for the full schema and list of the 15 canonical categories.
- **Private tier**: never committed. Holds real invoices and contracts that carry third-party personal data. Fetched from a bucket via CI secrets, gates `main` and release branches, and is skipped where credentials are absent. The private tier adds volume and real-world messiness — never unique structural categories.

The public tier is intentionally small (17 files as of this writing). Every file was individually structurally verified via `pikepdf` object introspection and, for rendering-dependent categories, a `pypdfium2` visual spot-check, rather than added to pad the count.

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
│   ├── pdftool.py         # Engine CLI (index subcommand)
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

## Export paths — honest quality

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
