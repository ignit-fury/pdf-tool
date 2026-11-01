# Public corpus test report — 2026-10-30

Tested checkout: `2c881453d3556298a5891c36c46fe231936c6f86`. Testing only: no application fixes, PDF changes, dependency changes or deployment.

All **217 PDFs** in the actual `corpus/public` directory are represented in all three fresh audits. All **8,254 pages** were attempted for text classification and passed through the exact server page preflight function. Final hashes confirm every original PDF is unchanged. No missing files, duplicate files or missing page indices were found.

## Results

| Check | Result |
|---|---|
| Page classification | 8,253 completed; 1 malformed-page extraction error |
| Server page preflight | 8,152 passed; 102 `DOCUMENT_LIMIT` refusals in one PDF |
| PDFs containing editable-classified runs | 207; classification is not a successful-edit guarantee |
| Restricted runs | 254,015 across 1,098 pages in 125 PDFs |
| Edit sampling | 730 preview/apply cases across 238 sampled pages; all 217 PDFs attempted |
| Fully verified identity + shorter pairs | 159 PDFs: 107 automatic, 52 with explicit substitution |
| Additional PDFs with some verified edits | 5 |
| PDFs with no independently verified sample edit | 53: 35 refused, 10 no eligible sample, 6 text-unverifiable, 2 page-error |
| Returned outputs | 342; 330 independently text-verified, 12 source-text-unverifiable |
| Observed corrupt / wrong-text outputs | 0 / 0 in tested cases |
| Preview/apply disagreements | 0 |
| Client tests | 203 passed |
| Full Python suite | 906 passed, 10 failed, 6 skipped initially |
| Targeted reruns | 13 passed, 1 failed with OS permissions/validator configured; one additional validator control passed |
| Combined unique Python outcomes | 916 passed, 1 unresolved failure, 5 platform/deployment skips |

## Unresolved findings

1. **Large batch resource failure:** `govdocs1_013_013050.pdf`, the 40-page technical-document fixture. `test_40page_batch_worker_apply` exceeded its child CPU assertion (20.032 seconds versus 20). A separate rerun returned `WORKER_FAILED` during the 675-operation preview at 20.129 child CPU seconds. This remains a failed test; limits were not changed.
2. **Page resource guard:** every page (1–102) of `govdocs1_002_002166.pdf` returns `DOCUMENT_LIMIT` at preflight. On page 1, image streams `(233, 0)` and `(228, 0)` each expand beyond the 16,777,216-byte limit. Their compressed sizes are 263,112 and 193,053 bytes. Reachable image resources can therefore prevent text analysis even when diagnostic extraction finds editable text. The guard was retained.
3. **Malformed PDF:** page 1 of `govdocs1_011_011089.pdf` raises diagnostic `PDFSyntaxError`; the actual server audit returns `PDF_INVALID`. The preflight guard alone passes, demonstrating that guard acceptance does not prove full parse success.
4. **Independent text verification inconclusive:** six files below produced readable, structurally valid output whose original run text could not be matched in independent PDFium extraction. They are not counted as verified edits. Manual review is still needed.
5. **Other source restrictions:** unmapped source fonts, missing glyphs, missing Unicode mapping, Type3/symbolic fonts, shared operators/forms, truncated stream boundaries, stale instruction correlation, unresolved font widths, unsupported stateful operators, and width/layout guards remain in the per-file and per-page results.

Text-unverifiable files:

- `govdocs1_000_000135.pdf`
- `govdocs1_002_002174.pdf`
- `govdocs1_006_006037.pdf`
- `govdocs1_007_007042.pdf`
- `govdocs1_010_010107.pdf`
- `govdocs1_010_010110.pdf`

## PDFs without editable-classified runs

These nine were fully classified and contain no editable-classified run. The malformed PDF above is excluded because its classification failed.

- `govdocs1_002_002014.pdf`: {'scan_no_text': 71}; run restrictions: no text runs.
- `govdocs1_004_004050.pdf`: {'editable': 4}; run restrictions: {'Type3': 6567}.
- `govdocs1_007_007030.pdf`: {'scan_no_text': 7}; run restrictions: no text runs.
- `govdocs1_010_010123.pdf`: {'editable': 6}; run restrictions: {'TrueType symbolic with /Encoding present': 15183}.
- `invoice_1905_james_green.pdf`: {'editable': 3}; run restrictions: {'shared Form XObject, referenced by 3 pages': 3}.
- `vector_outlined_text_sample.pdf`: {'vector_outlined': 1}; run restrictions: no text runs.
- `verapdf_inline_image_fixture.pdf`: {'empty': 1}; run restrictions: no text runs.
- `verapdf_isartor_malformed_trailer.pdf`: {'empty': 1}; run restrictions: no text runs.
- `verapdf_type3_font_fixture.pdf`: {'editable': 1}; run restrictions: {'Type3': 1}.

`govdocs1_002_002176.pdf` is different: it has 706 editable-classified single-glyph runs on sampled pages 1–3. Its “no eligible sample candidate” outcome comes from the audit's minimum two-character candidate rule, not a proof that its text is uneditable.

## Verification scope

The all-page read pass uses `RunIndex` directly. The separate guard pass executes the existing `_preflight(pdf, page)` for every page, with a 30-second diagnostic timeout. Neither is a complete isolated HTTP request, so their success does not guarantee worker CPU, memory, transport or formatting-metadata success.

The edit audit uses actual isolated inspect/page/edit workers, previews each operation and applies it to temporary output. It considers up to three runs among the first three pages and stops page exploration after any attempts. The specified extra page 6 was reached for `govdocs1_009_009097.pdf`. All 35 fully refused sample files were tested on page 1 only. Every PDF was attempted, but every text run/page was not edited. No conclusion here says all text in a PDF is editable or uneditable merely from its sample outcome.

Successful outputs were checked using pikepdf syntax/page count, qpdf, PDFium rendering and normalized full-page text replacement. This audit does not prove pixel preservation for every generated output. The regression suite separately includes rendering/preservation, fonts, find/replace, text boxes, page operations, image operations, export, undo/history controllers, privacy/cache recovery and license tests on its own fixtures and corpus cases. It is not a manual browser journey of every feature on every PDF; no fresh manual browser journey is claimed.

The six OS-restricted initial failures passed with local permissions. Three initial failures due to missing `VERAPDF_CMD` passed with the installed authenticated validator configured. One initially skipped validator control also passed. Remaining skips are four Linux-only isolation/seccomp checks and the absent live CDN URL. The 675-operation performance failure remains unresolved.

## Evidence and reproduction

- [Per-file CSV](corpus-files-2026-10-30.csv): every PDF, page/run counts, sample outcome and refusal reasons.
- [Per-page CSV](corpus-pages-2026-10-30.csv): every page, editable/restricted run counts, reasons and preflight status. Page numbers are one-based.
- [Edit JSON](corpus-edits-2026-10-30.json): original hashes, run identifiers, individual preview/apply results and independent validation.
- [Read JSON](corpus-read-2026-10-30.json): diagnostic all-page classification, zero-based page indices.
- [Guard JSON](corpus-page-guards-2026-10-30.json): all-page server preflight checks, zero-based page indices.

Manifest SHA checks and independent structural-category probe both passed. Source fingerprint stayed fixed throughout all 217 edit audits.

Commands used:

```sh
.venv/bin/python tools/audit_corpus_edits.py --corpus corpus/public --output .planning/audits/corpus-edits-2026-10-30.json --extra-page govdocs1_009_009097.pdf:5
.venv/bin/python /private/tmp/pdf_tool_full_read_audit.py
.venv/bin/python /private/tmp/pdf_tool_page_guard_audit.py
.venv/bin/python corpus/validate_manifest.py corpus/manifest.json corpus/public
.venv/bin/python tools/probe_corpus.py corpus/manifest.json corpus/public
.venv/bin/python -m pytest -q
npm --prefix client test
```

Reruns used `JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-26.jdk/Contents/Home` and `VERAPDF_CMD=/private/tmp/pdf-tool-phase8-tools/verapdf/verapdf`; OS-dependent tests ran with local OS permissions. Original full-suite and rerun logs are in `/private/tmp/pdf-tool-full-corpus-regression-2026-10-30.log` and `/private/tmp/pdf-tool-corpus-rerun-2026-10-30.log`.

## Every PDF

“Editable pages” means pages with at least one editable-classified run; it is not an edit guarantee. Exact reasons and page details are in the CSV/JSON links above.

| PDF | Pages | Editable pages | Restricted pages | Sample outcome | Verified outputs | Sample refusal categories |
|---|---:|---:|---:|---|---:|---|
| far_federal_acquisition_regulation.pdf | 2026 | 2019 | 0 | Verified pair | 2 | — |
| govdocs1_000_000009.pdf | 4 | 4 | 1 | Sampled edits refused | 0 | operator_shared_by_multiple_runs; part_boundary_truncated |
| govdocs1_000_000010.pdf | 4 | 4 | 1 | Sampled edits refused | 0 | operator_shared_by_multiple_runs; part_boundary_truncated |
| govdocs1_000_000011.pdf | 1 | 1 | 0 | Verified pair | 2 | — |
| govdocs1_000_000013.pdf | 2 | 2 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_000_000015.pdf | 2 | 2 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_000_000016.pdf | 4 | 4 | 2 | Sampled edits refused | 0 | part_boundary_truncated; stale_run_index |
| govdocs1_000_000018.pdf | 9 | 9 | 3 | Verified pair | 2 | — |
| govdocs1_000_000019.pdf | 3 | 3 | 0 | Verified pair | 2 | — |
| govdocs1_000_000024.pdf | 1 | 1 | 1 | Verified pair | 2 | — |
| govdocs1_000_000025.pdf | 4 | 4 | 3 | Sampled edits refused | 0 | part_boundary_truncated |
| govdocs1_000_000026.pdf | 5 | 5 | 1 | Some edits verified | 1 | operator_shared_by_multiple_runs; unmapped original font; width/fit limit |
| govdocs1_000_000028.pdf | 13 | 13 | 5 | Verified pair | 2 | — |
| govdocs1_000_000029.pdf | 1 | 1 | 1 | Sampled edits refused | 0 | stale_run_index |
| govdocs1_000_000135.pdf | 8 | 8 | 3 | Text verification inconclusive | 0 | — |
| govdocs1_000_000137.pdf | 4 | 4 | 1 | Verified pair | 2 | — |
| govdocs1_001_001024.pdf | 59 | 59 | 0 | Verified pair | 2 | — |
| govdocs1_001_001028.pdf | 59 | 59 | 1 | Verified pair | 2 | — |
| govdocs1_001_001029.pdf | 129 | 123 | 2 | Verified pair | 2 | unmapped original font |
| govdocs1_001_001030.pdf | 3 | 3 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_001_001031.pdf | 4 | 4 | 0 | Verified pair | 2 | — |
| govdocs1_001_001032.pdf | 78 | 77 | 3 | Verified pair | 2 | — |
| govdocs1_001_001033.pdf | 24 | 24 | 1 | Verified pair | 2 | — |
| govdocs1_001_001034.pdf | 99 | 99 | 0 | Verified pair | 2 | — |
| govdocs1_001_001035.pdf | 30 | 30 | 0 | Verified pair | 2 | — |
| govdocs1_001_001036.pdf | 37 | 37 | 0 | Verified pair | 2 | — |
| govdocs1_001_001037.pdf | 15 | 15 | 1 | Verified pair | 2 | — |
| govdocs1_001_001038.pdf | 46 | 46 | 1 | Verified pair | 2 | — |
| govdocs1_002_002014.pdf | 71 | 0 | 0 | No eligible sample candidate | 0 | — |
| govdocs1_002_002021.pdf | 142 | 134 | 1 | Verified pair | 2 | resolution_failed; unmapped original font |
| govdocs1_002_002145.pdf | 7 | 7 | 6 | Verified pair | 2 | — |
| govdocs1_002_002154.pdf | 6 | 6 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_002_002166.pdf | 102 | 102 | 0 | Server page error | 0 | DOCUMENT_LIMIT |
| govdocs1_002_002167.pdf | 6 | 6 | 4 | Sampled edits refused | 0 | part_boundary_truncated |
| govdocs1_002_002168.pdf | 12 | 12 | 1 | Verified pair | 2 | unmapped original font |
| govdocs1_002_002169.pdf | 19 | 19 | 0 | Verified pair | 2 | — |
| govdocs1_002_002173.pdf | 2 | 2 | 0 | Verified pair | 2 | — |
| govdocs1_002_002174.pdf | 32 | 32 | 15 | Text verification inconclusive | 0 | — |
| govdocs1_002_002176.pdf | 20 | 20 | 0 | No eligible sample candidate | 0 | — |
| govdocs1_002_002177.pdf | 1 | 1 | 0 | Verified pair | 2 | — |
| govdocs1_003_003005.pdf | 10 | 10 | 1 | Verified pair | 2 | stale_run_index |
| govdocs1_003_003039.pdf | 17 | 17 | 0 | Verified pair | 2 | — |
| govdocs1_003_003049.pdf | 3 | 3 | 0 | Verified pair | 2 | — |
| govdocs1_003_003060.pdf | 3 | 3 | 3 | Sampled edits refused | 0 | part_boundary_truncated; stale_run_index |
| govdocs1_003_003063.pdf | 30 | 30 | 1 | Sampled edits refused | 0 | part_boundary_truncated |
| govdocs1_003_003064.pdf | 3 | 3 | 0 | Verified pair | 2 | — |
| govdocs1_003_003065.pdf | 20 | 20 | 20 | Verified pair | 2 | — |
| govdocs1_003_003066.pdf | 16 | 16 | 14 | Verified pair | 2 | unmapped original font |
| govdocs1_003_003067.pdf | 21 | 21 | 0 | Verified pair | 2 | — |
| govdocs1_003_003072.pdf | 15 | 15 | 15 | Sampled edits refused | 0 | part_boundary_truncated; stale_run_index |
| govdocs1_003_003073.pdf | 9 | 9 | 2 | Verified pair | 2 | unmapped original font |
| govdocs1_003_003074.pdf | 8 | 8 | 1 | Some edits verified | 1 | stale_run_index; unmapped original font; width/fit limit |
| govdocs1_004_004050.pdf | 4 | 0 | 4 | No eligible sample candidate | 0 | — |
| govdocs1_004_004116.pdf | 9 | 9 | 5 | Verified pair | 2 | — |
| govdocs1_004_004117.pdf | 15 | 15 | 1 | Verified pair | 2 | — |
| govdocs1_004_004119.pdf | 26 | 26 | 13 | Sampled edits refused | 0 | operator_shared_by_multiple_runs |
| govdocs1_004_004121.pdf | 10 | 10 | 4 | Verified pair | 2 | — |
| govdocs1_004_004122.pdf | 15 | 15 | 5 | Verified pair | 2 | — |
| govdocs1_004_004124.pdf | 4 | 4 | 1 | Sampled edits refused | 0 | part_boundary_truncated |
| govdocs1_004_004125.pdf | 3 | 3 | 0 | Verified pair | 2 | — |
| govdocs1_004_004126.pdf | 7 | 7 | 0 | Verified pair | 2 | — |
| govdocs1_004_004130.pdf | 2 | 2 | 2 | Sampled edits refused | 0 | resolution_failed |
| govdocs1_004_004132.pdf | 38 | 38 | 0 | Verified pair | 2 | — |
| govdocs1_004_004133.pdf | 10 | 10 | 1 | Verified pair | 2 | — |
| govdocs1_005_005000.pdf | 11 | 11 | 0 | Sampled edits refused | 0 | stale_run_index |
| govdocs1_005_005004.pdf | 19 | 19 | 16 | Sampled edits refused | 0 | part_boundary_truncated |
| govdocs1_005_005005.pdf | 9 | 9 | 5 | Verified pair | 2 | — |
| govdocs1_005_005009.pdf | 3 | 3 | 1 | Verified pair | 2 | — |
| govdocs1_005_005010.pdf | 8 | 8 | 1 | Verified pair | 2 | — |
| govdocs1_005_005012.pdf | 1 | 1 | 1 | Verified pair | 2 | operator_shared_by_multiple_runs |
| govdocs1_005_005013.pdf | 3 | 3 | 1 | Some edits verified | 1 | part_boundary_truncated; unmapped original font; width/fit limit |
| govdocs1_005_005015.pdf | 2 | 2 | 1 | Sampled edits refused | 0 | part_boundary_truncated |
| govdocs1_005_005020.pdf | 60 | 60 | 14 | Verified pair | 2 | — |
| govdocs1_005_005021.pdf | 3 | 3 | 3 | Verified pair | 2 | — |
| govdocs1_005_005084.pdf | 20 | 19 | 2 | Verified pair | 2 | — |
| govdocs1_005_005086.pdf | 48 | 48 | 2 | Verified pair | 2 | — |
| govdocs1_006_006027.pdf | 46 | 46 | 4 | Verified pair | 2 | — |
| govdocs1_006_006029.pdf | 12 | 12 | 1 | Verified pair | 2 | — |
| govdocs1_006_006031.pdf | 1 | 1 | 0 | Verified pair | 2 | — |
| govdocs1_006_006032.pdf | 1 | 1 | 0 | Verified pair | 2 | — |
| govdocs1_006_006034.pdf | 7 | 7 | 0 | Verified pair | 2 | — |
| govdocs1_006_006037.pdf | 13 | 13 | 1 | Text verification inconclusive | 0 | — |
| govdocs1_006_006040.pdf | 7 | 7 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_006_006046.pdf | 4 | 4 | 1 | Verified pair | 2 | — |
| govdocs1_006_006047.pdf | 52 | 51 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_006_006048.pdf | 20 | 20 | 0 | Verified pair | 2 | — |
| govdocs1_006_006050.pdf | 52 | 52 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_006_006053.pdf | 100 | 100 | 5 | Verified pair | 2 | — |
| govdocs1_007_007020.pdf | 10 | 8 | 0 | Verified pair | 2 | — |
| govdocs1_007_007024.pdf | 27 | 27 | 0 | Verified pair | 2 | stateful_text_showing_unsupported |
| govdocs1_007_007030.pdf | 7 | 0 | 0 | No eligible sample candidate | 0 | — |
| govdocs1_007_007042.pdf | 118 | 118 | 0 | Text verification inconclusive | 0 | — |
| govdocs1_007_007071.pdf | 42 | 41 | 40 | Some edits verified | 3 | unmapped original font; width/fit limit |
| govdocs1_007_007074.pdf | 259 | 259 | 78 | Verified pair | 2 | — |
| govdocs1_007_007075.pdf | 20 | 20 | 0 | Verified pair | 2 | — |
| govdocs1_007_007081.pdf | 26 | 25 | 2 | Verified pair | 2 | unmapped original font |
| govdocs1_007_007083.pdf | 60 | 60 | 0 | Verified pair | 2 | — |
| govdocs1_007_007084.pdf | 42 | 42 | 11 | Verified pair | 2 | — |
| govdocs1_007_007087.pdf | 58 | 57 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_007_007089.pdf | 29 | 29 | 0 | Verified pair | 2 | — |
| govdocs1_007_007091.pdf | 128 | 119 | 1 | Verified pair | 2 | unmapped original font |
| govdocs1_007_007092.pdf | 52 | 52 | 1 | Verified pair | 2 | unmapped original font |
| govdocs1_008_008006.pdf | 11 | 11 | 1 | Sampled edits refused | 0 | part_boundary_truncated; stale_run_index |
| govdocs1_008_008008.pdf | 7 | 7 | 3 | Verified pair | 2 | unmapped original font |
| govdocs1_008_008009.pdf | 12 | 12 | 0 | Verified pair | 2 | — |
| govdocs1_008_008010.pdf | 10 | 10 | 8 | Sampled edits refused | 0 | part_boundary_truncated |
| govdocs1_008_008012.pdf | 28 | 24 | 1 | Verified pair | 2 | — |
| govdocs1_008_008015.pdf | 16 | 16 | 1 | Verified pair | 2 | unmapped original font |
| govdocs1_008_008016.pdf | 13 | 13 | 12 | Sampled edits refused | 0 | part_boundary_truncated |
| govdocs1_008_008022.pdf | 28 | 28 | 0 | Sampled edits refused | 0 | text_matrix_shifted_after_edit |
| govdocs1_008_008024.pdf | 15 | 15 | 0 | Verified pair | 2 | — |
| govdocs1_008_008025.pdf | 3 | 3 | 1 | Verified pair | 2 | — |
| govdocs1_008_008028.pdf | 1 | 1 | 1 | Verified pair | 2 | — |
| govdocs1_008_008029.pdf | 15 | 15 | 0 | Verified pair | 2 | — |
| govdocs1_008_008032.pdf | 10 | 10 | 9 | Sampled edits refused | 0 | part_boundary_truncated; stale_run_index |
| govdocs1_008_008034.pdf | 4 | 4 | 1 | Sampled edits refused | 0 | part_boundary_truncated |
| govdocs1_009_009001.pdf | 12 | 12 | 0 | Verified pair | 2 | — |
| govdocs1_009_009002.pdf | 43 | 43 | 35 | Verified pair | 2 | — |
| govdocs1_009_009011.pdf | 18 | 18 | 0 | Verified pair | 2 | — |
| govdocs1_009_009013.pdf | 22 | 22 | 17 | Verified pair | 2 | — |
| govdocs1_009_009015.pdf | 3 | 3 | 2 | Verified pair | 2 | — |
| govdocs1_009_009052.pdf | 267 | 266 | 0 | Verified pair | 2 | — |
| govdocs1_009_009055.pdf | 150 | 150 | 130 | Verified pair | 2 | — |
| govdocs1_009_009057.pdf | 11 | 10 | 1 | Verified pair | 2 | unmapped original font |
| govdocs1_009_009059.pdf | 8 | 8 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_009_009060.pdf | 10 | 10 | 0 | Verified pair | 2 | — |
| govdocs1_009_009067.pdf | 17 | 17 | 0 | Verified pair | 2 | — |
| govdocs1_009_009069.pdf | 41 | 41 | 2 | Verified pair | 2 | — |
| govdocs1_009_009077.pdf | 165 | 163 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_009_009097.pdf | 28 | 14 | 28 | Verified pair | 2 | unmapped original font |
| govdocs1_010_010105.pdf | 173 | 173 | 0 | Verified pair | 2 | — |
| govdocs1_010_010106.pdf | 149 | 149 | 0 | Verified pair | 2 | — |
| govdocs1_010_010107.pdf | 23 | 23 | 1 | Text verification inconclusive | 0 | — |
| govdocs1_010_010109.pdf | 2 | 2 | 0 | Verified pair | 2 | — |
| govdocs1_010_010110.pdf | 17 | 17 | 0 | Text verification inconclusive | 0 | — |
| govdocs1_010_010116.pdf | 138 | 137 | 112 | Verified pair | 2 | — |
| govdocs1_010_010118.pdf | 1 | 1 | 1 | Verified pair | 2 | — |
| govdocs1_010_010120.pdf | 20 | 20 | 0 | Verified pair | 2 | — |
| govdocs1_010_010123.pdf | 6 | 0 | 6 | No eligible sample candidate | 0 | — |
| govdocs1_010_010124.pdf | 4 | 4 | 0 | Sampled edits refused | 0 | resolution_failed |
| govdocs1_010_010129.pdf | 1 | 1 | 0 | Verified pair | 2 | — |
| govdocs1_010_010141.pdf | 4 | 4 | 4 | Sampled edits refused | 0 | part_boundary_truncated; stale_run_index |
| govdocs1_010_010197.pdf | 62 | 62 | 46 | Verified pair | 2 | unmapped original font |
| govdocs1_010_010204.pdf | 45 | 45 | 3 | Verified pair | 2 | unmapped original font |
| govdocs1_011_011001.pdf | 1 | 1 | 0 | Verified pair | 2 | — |
| govdocs1_011_011078.pdf | 8 | 8 | 8 | Sampled edits refused | 0 | operator_shared_by_multiple_runs |
| govdocs1_011_011080.pdf | 5 | 5 | 5 | Sampled edits refused | 0 | operator_shared_by_multiple_runs |
| govdocs1_011_011082.pdf | 3 | 3 | 0 | Verified pair | 2 | — |
| govdocs1_011_011083.pdf | 3 | 3 | 1 | Verified pair | 2 | — |
| govdocs1_011_011087.pdf | 1 | 1 | 0 | Verified pair | 2 | — |
| govdocs1_011_011089.pdf | 1 | 0 | 0 | Server page error | 0 | PDF_INVALID |
| govdocs1_011_011093.pdf | 3 | 3 | 1 | Sampled edits refused | 0 | operator_shared_by_multiple_runs |
| govdocs1_011_011095.pdf | 50 | 50 | 1 | Some edits verified | 3 | unmapped original font; width/fit limit |
| govdocs1_011_011097.pdf | 1 | 1 | 1 | Verified pair | 2 | — |
| govdocs1_011_011098.pdf | 65 | 65 | 3 | Verified pair | 2 | — |
| govdocs1_011_011099.pdf | 1 | 1 | 1 | Verified pair | 2 | — |
| govdocs1_011_011105.pdf | 10 | 10 | 0 | Verified pair | 2 | operator_shared_by_multiple_runs; unmapped original font |
| govdocs1_011_011133.pdf | 52 | 52 | 0 | Verified pair | 2 | — |
| govdocs1_012_012014.pdf | 31 | 31 | 15 | Verified pair | 2 | unmapped original font |
| govdocs1_012_012053.pdf | 4 | 4 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_012_012082.pdf | 214 | 211 | 84 | Verified pair | 2 | — |
| govdocs1_012_012084.pdf | 1 | 1 | 0 | Verified pair | 2 | — |
| govdocs1_012_012087.pdf | 11 | 11 | 10 | Verified pair | 2 | unmapped original font |
| govdocs1_012_012098.pdf | 16 | 16 | 6 | Sampled edits refused | 0 | part_boundary_truncated |
| govdocs1_012_012102.pdf | 8 | 8 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_012_012103.pdf | 8 | 8 | 8 | Verified pair | 2 | — |
| govdocs1_012_012156.pdf | 4 | 4 | 0 | Verified pair | 2 | — |
| govdocs1_012_012158.pdf | 8 | 8 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_012_012159.pdf | 15 | 15 | 1 | Verified pair | 2 | unmapped original font |
| govdocs1_012_012166.pdf | 16 | 16 | 0 | Verified pair | 2 | — |
| govdocs1_012_012170.pdf | 198 | 188 | 1 | Sampled edits refused | 0 | operator_shared_by_multiple_runs; part_boundary_truncated |
| govdocs1_012_012172.pdf | 22 | 22 | 4 | Verified pair | 2 | — |
| govdocs1_013_013043.pdf | 13 | 13 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_013_013047.pdf | 11 | 11 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_013_013048.pdf | 9 | 9 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_013_013050.pdf | 40 | 40 | 0 | Verified pair | 3 | unmapped original font; width/fit limit |
| govdocs1_013_013064.pdf | 6 | 6 | 0 | Sampled edits refused | 0 | operator_shared_by_multiple_runs |
| govdocs1_013_013079.pdf | 43 | 43 | 0 | Verified pair | 3 | unmapped original font; width/fit limit |
| govdocs1_013_013083.pdf | 1 | 1 | 1 | Verified pair | 2 | — |
| govdocs1_013_013085.pdf | 39 | 39 | 0 | Verified pair | 3 | unmapped original font; width/fit limit |
| govdocs1_013_013093.pdf | 4 | 4 | 0 | Verified pair | 2 | — |
| govdocs1_013_013097.pdf | 15 | 15 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_013_013100.pdf | 4 | 4 | 2 | Sampled edits refused | 0 | part_boundary_truncated |
| govdocs1_013_013104.pdf | 166 | 158 | 1 | Verified pair | 2 | unmapped original font |
| govdocs1_013_013107.pdf | 13 | 13 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_013_013110.pdf | 2 | 2 | 0 | Verified pair | 2 | — |
| govdocs1_014_014009.pdf | 129 | 129 | 0 | Verified pair | 2 | — |
| govdocs1_014_014010.pdf | 1 | 1 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_014_014027.pdf | 12 | 12 | 11 | Verified pair | 2 | — |
| govdocs1_014_014091.pdf | 6 | 6 | 0 | Verified pair | 2 | unmapped original font |
| govdocs1_014_014103.pdf | 31 | 31 | 1 | Sampled edits refused | 0 | resolution_failed |
| govdocs1_014_014114.pdf | 51 | 51 | 0 | Verified pair | 2 | — |
| govdocs1_014_014115.pdf | 12 | 12 | 1 | Sampled edits refused | 0 | stale_run_index |
| govdocs1_014_014118.pdf | 12 | 12 | 2 | Verified pair | 2 | stale_run_index |
| govdocs1_014_014222.pdf | 9 | 9 | 6 | Verified pair | 2 | — |
| govdocs1_014_014226.pdf | 4 | 4 | 1 | Sampled edits refused | 0 | part_boundary_truncated |
| govdocs1_014_014228.pdf | 6 | 6 | 1 | Sampled edits refused | 0 | part_boundary_truncated |
| govdocs1_014_014229.pdf | 10 | 10 | 2 | Sampled edits refused | 0 | part_boundary_truncated; stale_run_index |
| govdocs1_014_014230.pdf | 2 | 2 | 1 | Verified pair | 2 | part_boundary_truncated; stale_run_index |
| govdocs1_014_014233.pdf | 7 | 7 | 4 | Verified pair | 2 | unmapped original font |
| invoice_1905_james_green.pdf | 3 | 0 | 3 | No eligible sample candidate | 0 | — |
| invoice_book_1842.pdf | 52 | 45 | 0 | Verified pair | 2 | unmapped original font |
| irs_1040_instructions.pdf | 126 | 126 | 65 | Verified pair | 2 | text_matrix_shifted_after_edit; unmapped original font |
| irs_1040_tax_tables.pdf | 28 | 28 | 2 | Verified pair | 2 | unmapped original font |
| irs_form_1040.pdf | 2 | 2 | 1 | Verified pair | 2 | unmapped original font |
| irs_form_1040_spanish.pdf | 2 | 2 | 1 | Verified pair | 2 | unmapped original font |
| irs_form_w4.pdf | 5 | 5 | 1 | Verified pair | 2 | unmapped original font |
| irs_form_w9.pdf | 6 | 6 | 1 | Verified pair | 2 | unmapped original font |
| irs_form_w9_encrypted.pdf | 6 | 6 | 1 | Verified pair | 2 | unmapped original font |
| irs_publication_17.pdf | 142 | 142 | 68 | Verified pair | 2 | unmapped original font |
| mutopia_vocalise_abt.pdf | 1 | 1 | 1 | Verified pair | 2 | unmapped original font |
| nasa_graphics_standards_manual.pdf | 60 | 60 | 0 | Verified pair | 2 | — |
| vector_outlined_text_sample.pdf | 1 | 0 | 0 | No eligible sample candidate | 0 | — |
| verapdf_inline_image_fixture.pdf | 1 | 0 | 0 | No eligible sample candidate | 0 | — |
| verapdf_isartor_malformed_trailer.pdf | 1 | 0 | 0 | No eligible sample candidate | 0 | — |
| verapdf_type3_font_fixture.pdf | 1 | 0 | 1 | No eligible sample candidate | 0 | — |
| wikipedia_zh_monthly_magazine.pdf | 14 | 14 | 0 | Verified pair | 2 | character_has_no_glyph_in_bundled_font; unmapped original font |
