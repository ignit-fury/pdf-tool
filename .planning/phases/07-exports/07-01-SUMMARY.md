---
phase: 07-exports
plan: "01"
subsystem: engine
tags: [exports, run-index, reading-order, markdown, html]
requires:
  - phase: 02-text-model
    provides: Cached page/run index and immutable glyph provenance
provides:
  - Additive font/style and physical page/ruling metadata
  - Renderer-independent document/page/block/span model
  - Bounded text, Markdown and inert HTML serializers over one RunIndex
affects: [07-02, 07-04, 08-docx]
tech-stack:
  added: []
  patterns: [single indexed extraction, conservative layout, pure bounded serializers]
key-files:
  created: [engine/blocks.py, engine/export/__init__.py, engine/export/text.py, tools/build_export_fixtures.py, tests/test_export_metadata.py, tests/test_blocks.py, tests/test_export_text.py, tests/test_export_single_path.py]
  modified: [engine/records.py, engine/classify_run.py, engine/index.py]
key-decisions:
  - Unknown font style remains None; descriptor/program evidence precedes exact Base-14 defaults.
  - Font identity retains page/stream/resource ownership, including direct dictionaries.
  - Only complete axis-aligned ruled grids become tables; ambiguous layouts retain text with warning codes.
  - Serialized output is capped at 8 Mi characters, at most 32 MiB UTF-8.
requirements-completed: [EXPO-05]
duration: 13min
completed: 2026-10-27
---

# Phase 7 Plan 1: Indexed Text Exports Summary

**One cached RunIndex now supplies reusable layout blocks and escaped text, Markdown and HTML, without another extraction path.**

## Task commits

1. Metadata: RED `8bed0db`; GREEN `fab1913`.
2. Blocks and reproducible fixtures: RED `15df525`; GREEN `d364260`.
3. Serializers and single-path proof: RED `e8ec742`; GREEN `05eaf77`.
4. Direct resource identity regression: RED `1385dea`; fix `22f65ec`.

No tracked files were deleted. No dependencies installed.

## Exported contracts

- `engine.export.text.export_document(index: RunIndex, format: str) -> str`: accepts `text`, `markdown`, `html`. Invalid formats raise content-free `ValueError('unsupported-export-format')` before accessing the index. Output overflow raises `ValueError('export-output-limit')`.
- `serialize_text`, `serialize_markdown`, `serialize_html` each consume the same `DocumentBlocks` type. HTML is a complete UTF-8 document containing escaped semantic markup, without source attributes, executable content or remote references.
- `engine.blocks.build_document(index: RunIndex) -> DocumentBlocks` accesses only cached indexed metadata. Frozen dataclasses: `DocumentBlocks(pages)`, `PageBlocks(page_index, blocks, warnings)`, `Block(kind, source_runs, spans, heading_level, rows)`, `Span(text, bold, italic, source_runs)`. Table rows contain tuples of cells; cells contain tuples of spans. Source runs are the original RunRecord objects, not copies.
- `RunRecord` adds optional `font_name`, `bold`, `italic`, `font_identity`. Existing `effective_em`, `direction`, `page_ctm`, IDs, glyph shape and classification remain intact. Font identity is `(page_index, xobject_path, stream_id, resource_objgen, font_objgen, resource_name)`; stripped subset names are display-only.
- `PageIndex` adds compatible default `geometry=None`, `rulings=()`. Frozen `PageGeometry` carries `media_box`, `crop_box`, `rotation`, `user_unit`, `page_ctm`; rulings are device-frame endpoint tuples. q/Q/cm apply to paths; filled, curved, clipped and non-axis-aligned paths do not manufacture table rulings.

## Verification

- `.venv/bin/python -m pytest tests/test_export_metadata.py tests/test_blocks.py tests/test_export_text.py tests/test_export_single_path.py tests/test_run_id.py tests/test_boxes.py -q -x`: **48 passed**.
- `.venv/bin/python -m mypy engine server`: **35 source files clean**.
- Runtime monkeypatch proof: one parser open, one parse for each of three cache-fitting pages, six repeated format exports and zero additional opens/reparses.
- Production AST guard covers direct playa/pdfminer imports outside the boundary and alternate extraction calls/import aliases in export code. Client export source guard excludes viewer selection. Deliberately forbidden temporary imports/calls prove the guard fails on violations.
- Constructed fixtures independently assert actual 24/12pt operators, font resources, closed grid paths and an image-only page, then assert heading/body/list/style/column/table output. Negatives cover incomplete/unruled grids, heading threshold, unknown styles, curved/filled/clipped paths, invalid format, output and layout work bounds, malicious markup and direct-resource collisions.
- Stub and threat-surface review found no goal-blocking stubs or additional endpoints/auth/file/schema boundaries. Empty optional metadata, source tuples and empty scanned-page blocks are intentional real-data outcomes.

## Deviations from plan

- **[Rule 1 — Bug] Direct font dictionaries share `(0, 0)` object numbers.** Final review added a failing regression, then included page ownership in the additive font identity. This changes no run IDs, glyphs or verdicts. Files: `engine/records.py`, `engine/classify_run.py`, `tests/test_export_metadata.py`; fix `22f65ec`.
- Installed GSD references/templates were read from `.cursor/get-shit-done` because the specified `.Codex/get-shit-done` reference paths were absent. Shared STATE/ROADMAP/REQUIREMENTS changes are delegated to the parent orchestrator as explicitly instructed.

## Remaining integration and limits

- EXPO-05's engine boundary is complete; reachable API/client downloads, current-document materialization and G6 integration remain with plans 02–04. This summary does not claim product/release gate completion.
- Reading order is heuristic for horizontal text. Rotated/unsupported directions emit a warning while retaining text. Columns are inferred within vertical bands; unruled/partial/merged/complex tables remain paragraphs. Only one complete ruling grid per page is recognized; form-contained ruling geometry is not interpreted. No OCR or invented scanned text.
- FontFile2 OS/2 style evidence and descriptors are supported; unsupported font programs retain unknown style when exact Base-14 defaults do not apply.
- Limits: 2,000 pages, 100,000 runs, 100,000 ruling operators, 4,096 ruling segments, 64 grid axes, 1,000,000 grid/run comparisons, 8 Mi serialized characters. Caller-owned worker limits remain required.
- Existing Linux/container/CDN, literal contract-specimen and HEIC confinement gates remain open. No deployment, container setup or new package installation occurred.

## Self-Check: PASSED

All eleven owned implementation/test files and this summary exist. All eight listed task commits exist. Final focused regression and typing results above are from the committed implementation.

## Review addendum

- Added frozen `ExportResult(text: str, has_text: bool)` and `export_document_result(index: RunIndex, format: str) -> ExportResult`. Format validation precedes indexing; the function builds one `DocumentBlocks`, checks its actual spans/table cells for non-whitespace text, then serializes that same model. `export_document` remains a compatible string-returning wrapper. HTML wrappers and Markdown page separators cannot make scanned-only pages appear to contain extracted text.
- Corrected the client source guard to include the production `.mjs`/`.jsx` extensions alongside `.ts`/`.tsx`. Forbidden-call negative controls demonstrate rejection for both production extensions and acceptance after removing the call.
- RED `28e5fa6` recorded both gaps before implementation. Focused GREEN verification: `.venv/bin/python -m pytest tests/test_export_text.py tests/test_export_single_path.py -q -x` — **18 passed**. `.venv/bin/python -m mypy engine/export/text.py` — **1 file clean**. Added tests cover scanned-only two-page HTML/Markdown, normal text, whitespace-only content, table-cell text, same-model serialization, and repeated result/wrapper exports with one parser open and one parse per page.
- Root owns wiring `NO_EXTRACTABLE_TEXT` to `result.has_text`; no worker or shared planning metadata was modified here.
