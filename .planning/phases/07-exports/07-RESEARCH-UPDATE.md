# Phase 7 research update — 2026-10-26

This addendum supersedes stale interface and tier assumptions in August's research/pattern map. These are implementer judgments within CONTEXT discretion, not newly user-confirmed decisions. Local implementation is authorized; deployment, container setup and dependency installs are excluded. Existing G3 Linux/CDN, G4 literal-contract and production HEIC-confinement checks remain open.

- **Discovery:** Level 1, current source plus installed API introspection. Installed pikepdf 10.11.0 exposes `flatten_annotations(mode='all')`, `save(object_stream_mode=..., recompress_flate=True)` and `PdfImage.as_pil_image(apply_decode_array=True, apply_mask=True)`. Current cantoo is 2.9.1, React 18, Vite 5; do not copy the older stack version claims. No new packages or package installation tasks.
- **Current index:** `RunRecord` already has `effective_em`, `direction`, `page_ctm`; `_classify_one_page` populates these. Add font identity/style there using its cached stream/resource and operator context; leave locked GlyphRecord shape and walker unchanged. `PageIndex` needs geometry and bounded vector ruling metadata. A ruling scan is vector geometry, never text extraction.
- **Reusable blocks:** plain typed document/page/block/span data, source RunRecords, heading level, bold/italic and ruled-table rows/cells. Single-column paragraphs, font-size-cluster headings, lists and closed ruled grids are supported; detect columns, preserve their order and emit an honest warning when layout is ambiguous. No invented table cells or OCR. This is Phase 8's reusable reading-order artifact per D-7.2/A-7.2.
- **Tier choices:** PDF.js raster exports and split run locally. Sequential raster rendering uses physical viewport dimensions, `DPI/72`, no devicePixelRatio multiplier, white JPEG background and bounded pixels/output. Split reuses existing deletion/catalog safety inside a disposable PDF worker. ZIP32 stored entries need a small bounded writer because browsers have no Python stdlib; independent Python zipfile readback and CRC tests guard this deliberate exception to the old server zipfile recommendation. No general ZIP reader or compression implementation.
- **Server:** compression and native flatten run through existing raw-body ingress, worker admission, isolated scratch/preflight and safe error codes. Default compression only packs/recompresses structure. Explicit downsampling handles a conservatively supported DeviceRGB/DeviceGray subset, bounds decode dimensions before Pillow allocation, preserves unsupported images with a notice and counts changes. Missing/unusable annotation appearances and unsupported interactive forms must refuse rather than silently discard content.
- **Single text path:** server creates one RunIndex over submitted current bytes; `engine.export.text.export_document(index, format)` returns Unicode text. It delegates reading order to `engine.blocks.build_document(index)`; serializers never open PDFs or call another extractor. Existing PDF.js viewer selection/accessibility text is not an export extraction path. AST import/call guards plus runtime parser call counts enforce the distinction.

## Shared contracts

- `POST /exports?operation=compress|flatten|text|markdown|html&downsample=false&acknowledge_signature=false`: raw `application/pdf` current materialized bytes; existing Unicode-safe password headers. Only compress accepts downsampling. Response `{data: base64, media_type: str, filename: str, before_bytes: int, after_bytes: int, notices: list[str], changed_images: int, location: 'server'}`. No persistent export job or cache dependency. API filenames are fixed, not source metadata.
- Backend notice codes: `NO_SIZE_REDUCTION`, `IMAGES_SKIPPED`, `UNLOCKED_COPY`, `SIGNATURES_INVALIDATED`, `ANNOTATIONS_FLATTENED`, `NO_EXTRACTABLE_TEXT`; UI maps these to plain language. Export refusals: `EXPORT_OPTIONS_INVALID`, `EXPORT_LIMIT`, `FLATTEN_APPEARANCE_REQUIRED`, `EXPORT_UNSUPPORTED`, plus existing password/signature/worker codes. Artifacts cap at 48MiB within unchanged80MiB worker transport. Explicit downsampling caps16M pixels, longest edge1600 and JPEG quality80; default compression retains exact source bytes if no size reduction, preserving source encryption in that branch.
- `RunRecord` adds optional `font_name: str|None`, `bold: bool|None`, `italic: bool|None`. Unknown means unknown. `PageIndex` adds optional geometry and ruling tuples with safe defaults for existing synthetic callers. Geometry carries media/crop boxes, rotation, UserUnit and page CTM; ruling coordinates use the same device frame as glyphs.
- `engine.blocks.build_document(index: RunIndex) -> DocumentBlocks`; frozen builtin dataclasses contain `pages`, each page has `page_index`, `blocks`, `warnings`; blocks have kind, source runs, spans, optional heading level and table rows. `engine.export.text.export_document(index, format: Literal['text','markdown','html']) -> str` is the server integration boundary. Heading/list/table heuristics and geometry tolerances are named constants with fixtures at either side.
- Local helpers return `{bytes, filename, mediaType, notices}` or bounded lists of those files. `splitPdf(bytes, groups, {password, acknowledged})`, zero-based ascending page-index groups; `renderPageImages({pdf,pages,format,dpi,signal,onProgress})`; `createStoredZip(entries)`. Export orchestration captures session + bytes identity + edit version + options; discard/abort stale work, release canvas/tasks/object URLs, and never publish document/history state.

## Coverage audit

| Source | Item | Plans | Status |
|---|---|---|---|
| GOAL | Useful output formats, one text index, all four G6 criteria | 01–04 | COVERED |
| REQ | EXPO-01 PNG/JPEG, DPI, per-page/ZIP | 03,04 | COVERED |
| REQ | EXPO-02 structural/default, explicit downsample, sizes/preview | 02–04 | COVERED |
| REQ | EXPO-03 split | 03,04 | COVERED |
| REQ | EXPO-04 flatten | 02–04 | COVERED |
| REQ | EXPO-05 text/Markdown/HTML one index | 01,02,04 | COVERED |
| CONTEXT | D-7.1/A-7.1/A-7.5 additive index and single path | 01,04 | COVERED |
| CONTEXT | D-7.2/A-7.2 reusable reading order/style/ruled tables | 01,04 | COVERED |
| CONTEXT | D-7.3 structural compression and real preview | 02,03,04 | COVERED |
| CONTEXT | D-7.4 structural and confined three-engine proof | 04 | COVERED |
| CONTEXT | D-7.5 150 screen/300 print | 03,04 | COVERED |
| CONTEXT | A-7.3 raster tier determines ZIP tier | 03,04 | COVERED |
| CONTEXT | A-7.4 deliberate heading/columns/table fixtures | 01,04 | COVERED |
| CONTEXT | A-7.6 native flatten/save APIs | 02 | COVERED |
| RESEARCH | Bounds, metadata, resource isolation, honest privacy tiers | 01–04 | COVERED |
| RESEARCH | Reuse native render harness; union of actual annotation regions; no vacuous mask | 04 | COVERED |
| RESEARCH | Current local API/worker interfaces replace hypothetical Phase 4 handles | 02,03 | COVERED |

Excluded by source scope: PDF/A, DOCX, OCR and server fallback for deliberately local exports. Old pattern-map CLI subcommands are examples, not a requirement; the SPA is the reachable user path. No new package audit is needed because this plan set installs none.

## Execution graph

Wave 1: 07-01 (index → blocks → text) and 07-03 (local images/ZIP → split → panel/orchestration), disjoint owners. Wave 2: 07-02 consumes 01's text module and delivers PDF/API work. Wave 3: 07-04 consumes actual outputs from all plans and owns gate materializers, native proof, test-script wiring and results. Each plan has three bounded tasks; no source file has parallel writers. Export clients build against the fixed API above before endpoint delivery; actual server/browser integration is required in 04.
