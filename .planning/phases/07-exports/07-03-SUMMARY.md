---
phase: 07-exports
plan: "03"
subsystem: ui
tags: [exports, pdfjs, zip32, react, split]
requires:
  - phase: 06-page-operations
    provides: Catalog-safe deletion, disposable PDF workers and immutable history
provides:
  - Sequential local physical-DPI raster exports and stored ZIP32 output
  - Catalog-safe local split worker command
  - Reachable immutable export panel and exact prepared compression previews
affects: [07-04, export-validation]
tech-stack:
  added: []
  patterns: [immutable current-byte export controller, bounded stored ZIP32, sequential raster output]
key-files:
  created: [client/src/exports/images.mjs, client/src/exports/zip.mjs, client/src/exports/split.mjs, client/src/exports/controller.mjs, client/src/exports/ExportPanel.jsx]
  modified: [client/src/pageOps/pdfDocument.mjs, client/src/pageOps/pdfJob.worker.mjs, client/src/App.jsx, client/src/style.css]
key-decisions:
  - "Raster pages use PDF.js one-based numbering; split groups use ascending zero-based indices."
  - "PNG and JPEG use explicit white page backgrounds; transparency is not promised."
  - "Downsampled downloads require successful previews from exact current and prepared PDFs."
requirements-completed: [EXPO-01, EXPO-02, EXPO-03, EXPO-04, EXPO-05]
duration: 10min
completed: 2026-10-27
---

# Phase 7 Plan 3: Client Exports Summary

**Local physical-DPI images and catalog-safe PDF splitting, plus current-byte server exports with faithful compression previews and unchanged Undo history.**

## Accomplishments

- Export is reachable before the Analyze text gate. Eight format choices disclose their actual browser/server location. The panel uses labeled native controls, 2×2 panel buttons, wrapped fields, live progress/errors, cancel, result focus and stacked narrow-screen previews.
- Image export sequentially renders actual PDF.js viewports at `dpi / 72`, without DPR scaling or text extraction. JPEG/PNG encode on white. Canvas surfaces are zeroed on all terminal paths; active renders are cancelled on abort.
- Split loads an independent document per group, reuses existing `planDeletion` graph handling, removes excluded pages descending and saves once. No copyPages implementation, server call, snapshot or document publication was added.
- Compression defaults to lossless. Explicit image downsampling prepares exact output bytes; Before uses the current PDF viewer and After opens those returned bytes in an independent PDF.js loading task. Both render the chosen page. Downloads use the same prepared bytes; task/canvas cleanup follows result invalidation.
- Controller checks session, byte identity and edit version; revokes download URLs on cancellation, option changes, close/unmount or invalidation. It posts `target.bytes`, never `sourceBytes`/`openedBytes`, and has no history/document writer.

## Contracts and Limits

- `renderPageImages({pdf,pages,format,dpi,signal,onProgress,retainedBytes})` → `{files,notices}`; pages are one-based; format is `png`/`jpeg`; progress is `{completed,total}`. Files are `{bytes,filename,mediaType,notices}` with `page-0001.png`/`.jpg` names. Canvas/encoder seams support Node tests.
- `createStoredZip(entries,{retainedBytes})` → `Uint8Array`; entries have `filename` and `bytes`. Stored ZIP32 includes CRC32, local records, central directory and end record. Flat relative ASCII names only, fixed dates, duplicate/path/count/overflow refusal. Single-page all-pages exports also provide ZIP.
- `splitPdf(bytes,groups,{password,acknowledged,retainedBytes})` → `{files,notices}`; safe names are `split-0001.pdf`. Worker command `split` receives `{bytes,groups,options}`; caller supplies `SPLIT_ERROR_CODES` to the existing allowlisted worker facade. `everyNPages`/`parsePageGroups` normalize UI choices to nonempty ascending disjoint zero-based groups.
- DPI: integer 72–600; screen 150, print 300. Raster cap: 16,000,000 pixels/page. Local PDF input: 50 MiB. Files/archive: 48 MiB aggregate. Entries/groups: 1000. Known retained/copy/canvas/encoder/Blob allocations are admitted against the existing 300 MiB transient ceiling.
- Server POST contract matches `07-RESEARCH-UPDATE`: raw current PDF, Unicode password headers, operation/downsample/acknowledgement query. Strict response checks cover exact keys, fixed MIME/filename, canonical base64, matching before/after sizes, output cap, known notice codes, UTF-8 text and PDF signature. HTML only gets a download URL.

## Task Commits

1. Raster/ZIP RED `675eaac`; GREEN `2c519f1`.
2. Split RED `ae9eb43`; GREEN `49fb661`.
3. Controller RED `ef69178`; panel/controller GREEN `abb95cc`.

## Verification

- Watched each task's tests fail before implementation and pass afterward.
- `node --test client/src/exports/*.test.mjs`: **14/14 passed**.
- `node --test client/src/exports/split.test.mjs client/src/pageOps/pdfDocument.test.mjs client/src/pageOps/pdfWorker.test.mjs`: **21/21 passed**.
- `npm --prefix client run build`: **passed**, with the Vite chunk-size advisory.
- `git diff --check`: passed. Stub scan found only live accumulators, defaults and resource state; no incomplete production data path. No new threat surface beyond the plan's registered canvas/worker/API/download boundaries.

## Deviations from Plan

- **[Rule 2 - Missing disclosure]** Updated password-dialog and footer copy to disclose server exports; the earlier text mentioned only analysis. Included in `abb95cc`.
- Per coordinating-agent ownership, shared STATE/ROADMAP/requirements updates and browser/native integration proof remain with 07-04. No new dependency, deployment, container, package-script or shared metadata edits.
- The prescribed `~/.Codex/get-shit-done` reference directory was absent. Used available `~/.cursor/get-shit-done` summary template and installed PDF.js type documentation/current source interfaces. No Context7 MCP/CLI was available.

## Integration Handoff

07-04 must independently read ZIP output with Python zipfile/CRC, verify native PNG/JPEG dimensions and actual PDF render fidelity, exercise real endpoint/download/preview behavior, and observe 320/760px plus keyboard/cancellation/current-byte/Undo behavior. Node seams and a production build do not claim those browser/native checks. The coordinator owns final shared metadata updates.

## Self-Check: PASSED

All five helper/panel artifacts and four test files exist. All six RED/GREEN commits are present. No tracked files were deleted by these task commits.
