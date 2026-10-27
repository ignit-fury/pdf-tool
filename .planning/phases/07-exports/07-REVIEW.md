---
phase: 07-exports
reviewed: 2026-10-27T10:35:05Z
depth: standard
files_reviewed: 35
files_reviewed_list:
  - engine/records.py
  - engine/classify_run.py
  - engine/index.py
  - engine/blocks.py
  - engine/export/__init__.py
  - engine/export/text.py
  - engine/export/pdf.py
  - server/app.py
  - server/errors.py
  - server/isolation.py
  - server/worker.py
  - client/src/exports/zip.mjs
  - client/src/exports/images.mjs
  - client/src/exports/split.mjs
  - client/src/exports/controller.mjs
  - client/src/exports/ExportPanel.jsx
  - client/src/App.jsx
  - client/src/style.css
  - client/src/pageOps/pdfDocument.mjs
  - client/src/pageOps/pdfJob.worker.mjs
  - client/src/exports/controller.test.mjs
  - client/src/exports/images.test.mjs
  - client/src/exports/split.test.mjs
  - client/src/exports/zip.test.mjs
  - tests/test_blocks.py
  - tests/test_export_api.py
  - tests/test_export_metadata.py
  - tests/test_export_pdf.py
  - tests/test_export_single_path.py
  - tests/test_export_text.py
  - tests/test_gate_g6.py
  - tools/build_export_fixtures.py
  - tools/materialize_exports.mjs
  - harness/export_fixture.py
  - client/package.json
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
resolved_findings:
  critical: 1
  warning: 6
  total: 7
status: clean
---

# Phase 7: Code Review Report

## Summary

Focused adversarial review against `3b0bf57`, including the final root-owned working-tree corrections and G6 code through `42811d3`. No findings remain open. One blocker and six warnings were found and corrected during review; records below preserve their evidence. The reviewer modified only this report and made no commits.

## Narrative Findings (AI reviewer)

### CR-01 — BLOCKER, resolved: Downsampling modified transparency masks

**File:** `/Users/prempatel/Pictures/pdf-tool/engine/export/pdf.py:42-110`
**Issue:** Scanning every image object independently skipped a masked owner but JPEG-resampled its 2048×1024 grayscale soft mask to 1600×800. The first correction still missed masks reached through direct nested ExtGState dictionaries. Both cases changed unsupported opacity data, sometimes while claiming images were retained.
**Fix/Resolution:** Bounded role discovery now descends direct containers, then protects every image in mask/alternative/OPI closures by object identity before decoding. Ordinary aliases cannot override a mask role. Direct reviewer reproductions now return `changed_images=0`, `IMAGES_SKIPPED`, original 2048×1024 geometry and byte-exact alpha for both the image `/SMask` alias case and direct ExtGState luminosity-Form case. Dedicated real-PDF regressions cover both.

### WR-01 — WARNING, resolved: Empty HTML/Markdown missed the no-text notice

**File:** `/Users/prempatel/Pictures/pdf-tool/server/worker.py:230-238`
**Issue:** Testing serialized `text.strip()` mistook HTML tags and Markdown page separators for extracted content. Two blank pages reproduced missing notices in both formats.
**Fix/Resolution:** One shared block build now returns `ExportResult(text, has_text)`; the worker uses source-span metadata. Direct real-worker reproductions now return `NO_EXTRACTABLE_TEXT` for both formats, with API regressions.

### WR-02 — WARNING, resolved: Font-split list markers were duplicated

**File:** `/Users/prempatel/Pictures/pdf-tool/engine/export/text.py:75-92`
**Issue:** Joined spans identified a list, but stripping only the first span left a separately drawn marker inside the generated Markdown/HTML list item.
**Fix/Resolution:** Consume the matched marker prefix across spans while retaining body style/provenance. The actual PDF regression covers marker/space/body font changes; direct recheck emits `- *First item*` and `<li><em>First item</em></li>`.

### WR-03 — WARNING, resolved: Extraction guard skipped actual client extensions

**File:** `/Users/prempatel/Pictures/pdf-tool/tests/test_export_single_path.py:39-63`
**Issue:** The regression guard scanned only TypeScript while production exports use `.mjs/.jsx`.
**Fix/Resolution:** `c7e087d` adds both actual extensions and forbidden-call negative controls for each, avoiding a vacuous client guard.

### WR-04 — WARNING, resolved: Export bounds were reported as invalid PDFs

**Files:** `/Users/prempatel/Pictures/pdf-tool/engine/blocks.py:31-32`; `/Users/prempatel/Pictures/pdf-tool/engine/export/text.py:32-35`; `/Users/prempatel/Pictures/pdf-tool/server/worker.py:234-235`
**Issue:** Page/run/output bounds raised generic ValueError, which the worker mapped to `PDF_INVALID`; cumulative indexed-glyph overflow also lacked the intended export refusal.
**Fix/Resolution:** Named `ExportLimitError` and `DocumentTooLargeError` now map to fixed `EXPORT_LIMIT`. Reviewed typed-bound and worker-bound regressions.

### WR-05 — WARNING, resolved: Actual server refusal codes lost actionable guidance

**File:** `/Users/prempatel/Pictures/pdf-tool/client/src/exports/controller.mjs:19-22`
**Issue:** Password/signature guidance recognized local aliases but missed server `PASSWORD_INCORRECT` and `SIGNATURE_ACKNOWLEDGEMENT_REQUIRED`, falling back to an unhelpful generic failure.
**Fix/Resolution:** Explicit aliases now map both server codes to the existing guidance; reviewed regression assertions.

### WR-06 — WARNING, resolved: Standard client tests omitted export tests

**File:** `/Users/prempatel/Pictures/pdf-tool/client/package.json:7`
**Issue:** The standard test command's explicit directory globs omitted every new `src/exports/*.test.mjs` test.
**Fix/Resolution:** The root-owned script correction includes the export-test directory.

## Verification and Limits

- Reviewed current-byte transport, admission/cancellation ownership, signature/password boundaries, selected annotation appearances, escaped serializers, ZIP CRC/headers, split graph reuse, stale-result identity/URLs, raster bounds and independent G6 negative controls. No additional concrete security vulnerability was established in this scope.
- Reviewer performed the narrow reproductions above and reviewed owner regression tests; no repeated broad or native-render suite was launched.
- G6 code review includes independent painted references, exact rasterized region support, source hashes, resource/page mapping, damaged-archive and detached-graph controls. Recorded owner evidence: 5 G6 tests; 7 PDFs/13 mapped pages; 14 validator calls; 39 same-engine comparisons; 78 native rasterizations. Of 39 cross-engine pairs, 12 retain explicit baseline failures; these are not claimed as passing cross-engine comparisons. See [automated G6 evidence](07-04-GATE-SUMMARY.md).
- Root owns final consolidated tests and actual-browser evidence; neither is claimed by this review. The source corrections were rechecked in the working tree before root commits.
- Existing G3 Linux/container/CDN, literal-contract and production HEIC confinement debts remain open and outside this review. No deployment, dependency installation or AGPL runtime change occurred.
