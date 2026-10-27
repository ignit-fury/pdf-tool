---
phase: 07-exports
verified: 2026-10-27T10:54:37Z
status: passed
score: 12/12 must-haves verified
overrides_applied: 0
---

# Phase 7: Exports Verification Report

**Phase Goal:** A user gets their document out in the format they actually came for, and every text-derived format comes out of the one run index.
**Verified source:** `2bbebe2` (final application source).
**Status:** passed — local Phase 7 goal achieved; release gates remain separate.
**Re-verification:** No — no previous Phase 7 VERIFICATION.md existed.

## Goal Achievement

### Observable Truths

Roadmap criteria are rows 1–4. Rows 5–12 retain additional PLAN truths; overlapping text-path, compression, image and G6 statements are merged rather than counted twice.

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | Plain text, Markdown and HTML all consume the Phase 2 run index; no second extraction path exists. | VERIFIED | `server/worker.py:229` opens one RunIndex; `engine/export/text.py:157` calls `build_document` once and selects a pure serializer. `engine/blocks.py:238` reads indexed pages/runs. Production source search and `tests/test_export_single_path.py` guard parser imports and actual `.mjs/.jsx` exporters, with forbidden-call negative controls and repeated-export parse/open counters. |
| 2 | Pages export as PNG/JPEG at chosen DPI, per-page or all-page ZIP, with 150 screen / 300 print defaults. | VERIFIED | `images.mjs` renders sequential PDF.js viewports at `dpi/72`; `ExportPanel.jsx` provides current/all and 150/300/custom controls. Actual browser artifacts: 300-DPI PNG 1250×834; 150-DPI JPEG ZIP two 625×417 pages; rotated PNG 417×625. ZIP CRC/readback and download hashes verified. |
| 3 | Compression is lossless and structural by default; explicit downsampling shows before/after size and preview. | VERIFIED | `engine/export/pdf.py` uses native object streams/Flate save; default never calls `_reduce_images` and returns exact source on no reduction. Panel checkbox defaults false. Exact-current and returned-PDF canvases precede downsample download. Recorded actual result 6,292,232→735,448 bytes; prepared/download SHA matches. |
| 4 | Split and flatten outputs pass qpdf and intended-change differential checks in all three engines. | VERIFIED | Production outputs: 7 PDFs/13 mapped pages, 14 qpdf/pdfcpu calls. Native G6 has 39 same-engine checks: 27 exact source/output, 9 exact independent painted-reference/flatten, 3 confined lossy-image checks; 12 confined comparisons and 18 appearance-region comparisons, across PDFium/Poppler/MuPDF. Unchanged siblings are unmasked. Cross-engine baseline limitations below remain explicit. |
| 5 | Headings, emphasis, reading order and ruled tables share reusable renderer-independent blocks. | VERIFIED | Frozen Document/Page/Block/Span model in `engine/blocks.py`; geometry and actual resource-owned font style added beside existing index classification. Conservative horizontal/column ordering, heading-size clustering, lists and complete ruled grids feed all serializers. Constructed positive/negative fixtures and actual rendered layout HTML cover heading, two columns, bold/italic, list and 2×2 table. |
| 6 | Flattening preserves supported visible appearances and removes interactivity safely. | VERIFIED | `_check_appearances` validates selected normal AP/state, rectangles/matrix and XFA before native `flatten_annotations`; postconditions reject surviving visual annotations/widgets and remove AcroForm. Independent filled/state/transformed references compare exactly in each engine. Actual filled browser output retains appearances; missing/unsafe AP refuses without a result. |
| 7 | Server exports use submitted current bytes through the existing disposable worker. | VERIFIED | `server/app.py:251` validates bounded raw PDF/options then `dispatch('export', source, ...)`; `server/isolation.py` serializes options into existing worker lifecycle; worker preflights before export. Five actual server-format POSTs carry 7496 current bytes, matching the current PDF SHA, rather than cache/replay baseline bytes. |
| 8 | Current-page images and split PDFs export without an API request. | VERIFIED | Controller's raster branch calls `renderPageImages`; split branch invokes App's existing terminable PDF worker, `subsetPages` and shared deletion graph. Raw observer journeys for image/split and styled/rotated local exports contain zero requests. Observer negative controls count both fetch and document navigation. |
| 9 | Export is reachable without Analyze text and each action discloses its execution tier. | VERIFIED | `client/src/App.jsx:412` mounts Export before the `!meta` analysis gate. Panel/controller derive browser/server labels from the same format branches. Actual open→insert→images/split journey performs no analysis/upload request. |
| 10 | Compression preview/download uses exact prepared bytes and export never changes working PDF or Undo. | VERIFIED | Preview opens `result.files[0].bytes`; links use those bytes. Controller has no document/history writer and guards session/bytes/version/generation; options/close/Undo invalidate and revoke resources. Saved before/after current hashes match for both local and server exports; one subsequent Undo returns two pages and clears results. |
| 11 | Real browser exports include current text/page changes, accurate previews and observed routing. | VERIFIED | Raw 13-journey observer JSON, 23 matching artifact hashes and native validation of 9 actual PDF outputs (18 passing validator calls). Styled three-page current source, current text formats, rotated PNG, 1+2-page split, exact downsample preview, late cancellation, signatures, Unicode password, safe refusal and 320/760px layouts were exercised by coordinating agent. This verifier inspected saved evidence, not a repeated browser run. |
| 12 | All scoped requirements have passing evidence and older release gates remain honestly open. | VERIFIED | EXPO-01–05 map below to production paths, current artifacts and final-source regressions. G3 Linux/container/CDN, Phase 5 literal-contract specimen and production HEIC confinement are explicitly still open. No deployment or dependency installation is claimed. |

**Score:** 12/12 truths verified; no overrides.

### Required Artifacts

Each artifact was checked for existence, substantive behavior and its actual consumer, beyond SUMMARY claims.

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `engine/blocks.py` | Reusable indexed layout model | VERIFIED | Bounded page/run/grid model reads actual `RunRecord.display_text`, style and rulings; consumed by serializer boundary. |
| `engine/export/text.py` | Escaped format serializers | VERIFIED | Three serializers over one block model; UTF-8 HTML escapes source text, no source URLs/scripts; typed output limit and actual `has_text` metadata. |
| `tests/test_export_single_path.py` | Nonvacuous single-path proof | VERIFIED | AST/import/call checks, actual client extensions, negative controls and one-open/one-parse cached fixture assertions. Included in final Python suite. |
| `engine/export/pdf.py` | Native compression and flatten | VERIFIED | Bounded save; safe image subset; global protected mask roles include direct ExtGState/aliases; selected-AP preflight and postconditions. Called by worker. |
| `tests/test_export_api.py` | Bounded current-byte API proof | VERIFIED | Real worker/cache-independent operations, Unicode passwords, signature distinction, ingress/options, AP refusal, empty-format and typed-limit regressions. |
| `client/src/exports/ExportPanel.jsx` | Reachable export controls | VERIFIED | All eight formats; native labels/progress/cancel/errors/focus; exact result preview/download; mounted by App. |
| `client/src/exports/controller.mjs` | Immutable abortable orchestration | VERIFIED | Actual current-byte capture, branch dispatch, strict response validation, memory admission, stale guards and URL release. Used by panel. |
| `client/src/exports/split.mjs` | Bounded safe split | VERIFIED | Group normalization aliases production `subsetPages`; App worker dispatch reaches shared deletion graph. |
| `tests/test_gate_g6.py` | Independent structural/native gate | VERIFIED | Actual client/worker output, validators, three native engines, independent reference/support and effective corruption controls; included in final regression. |
| `tools/materialize_exports.mjs` | Actual client split/ZIP writer | VERIFIED | Imports production helpers, explicit page maps/source hash, writes outputs consumed by Python gate. |
| `.planning/phases/07-exports/07-G6-RESULTS.md` | Dated integrated evidence and limits | VERIFIED | Cross-checked against raw JSON, files, hashes, source and log endings; no blanket cross-engine or release pass. |

### Key Link Verification

| From | To | Via | Status | Evidence |
|---|---|---|---|---|
| `engine/index.py` | `engine/classify_run.py` | Existing shared page parse | WIRED | `_parse_page` calls `_classify_one_page`, then adds geometry/rulings; actual owning-resource style is attached to resulting runs. |
| `engine/export/text.py` | `engine/blocks.py` | All serializers consume one block build | WIRED | `export_document_result` builds once and passes the document to selected serializer; public string API delegates to it. |
| `server/app.py` | `server/isolation.py` | Current raw PDF dispatch | WIRED | `/exports` forwards bounded source/options through existing `dispatch`/`run_worker`, without source-cache dependency. |
| `server/worker.py` | `engine/export/text.py` | One RunIndex | WIRED | Text branches open RunIndex on submitted scratch PDF and serialize its blocks, returning UTF-8 data. |
| `server/worker.py` | `engine/export/pdf.py` | Preflight/signature/native rewrite | WIRED | Shared preflight occurs first; compress/flatten require signed acknowledgement, native result returned with exact size/notices. |
| `client/src/App.jsx` | `ExportPanel.jsx` | Inspector switch before Analyze gate | WIRED | Direct import, mounted export branch, live current/viewer/worker callbacks. |
| `controller.mjs` | `/exports` | Current bytes/fixed response | WIRED | POST body is captured current `bytes`; strict MIME/name/base64/size/notices checked before downloadable Blob. |
| `split.mjs` | `pageOps/pdfDocument.mjs` | Existing safe deletion graph | WIRED | `splitPdf=subsetPages`; worker command reaches independent group loads, `planDeletion`, descending removals and one save. |
| `materialize_exports.mjs` | `split.mjs` | Production helper | WIRED | Actual helper bytes/hash/maps feed gate manifest and archive. |
| `test_gate_g6.py` | `harness/render_diff.py` | Three-engine render/baselines | WIRED | `render_all` produces source/output/reference/support rasters; exact same-engine and baseline-sensitive cross checks consume them. |
| `test_gate_g6.py` | `zip.mjs` | Materializer plus independent Python reader | WIRED | Actual stored ZIP read with Python zipfile; names/order/count/header/CRC/extracted byte assertions and corruption negatives. |

### Data-Flow Trace (Level 4)

| Artifact/output | Data variable | Actual source | Status |
|---|---|---|---|
| Export controls/downloads | `state.result.files`, sizes/notices | Controller → actual PDF.js render, split worker or `/exports` response | FLOWING — actual browser output hashes, archives and native PDF validations |
| Compression canvases | Current `pdf`, prepared `bytes`, selected page | Current materialized viewer and independent PDF.js open of returned result | FLOWING — Before/After canvases recorded; download SHA equals prepared response |
| Text/Markdown/HTML | `document.pages[].blocks[].spans`/table cells | Submitted current bytes → RunIndex pages/runs → blocks → serializer | FLOWING — current styled text present, old text absent, style retained; no hardcoded empty caller props |

### Behavioral Spot-Checks and Regression Evidence

Fresh verifier checks were read-only artifact checks, not repeated tests/build/browser operations. Existing execution results are reused only for the final application source. No server was started by this verifier.

| Behavior/check | Command or evidence | Result | Status |
|---|---|---|---|
| Artifact identity and current-byte transport | Read-only `python3 -c` SHA-256 assertions over native manifest, browser digest map and request records | 16 native manifest hashes + 23 browser hashes match; 3 text request hashes equal current PDF; exact prepared/download and unchanged-current hashes | PASS |
| Actual stored archives | Read-only Python zipfile CRC/readback of native split, browser JPEG, browser split, styled groups | Four archives, two entries each; CRC clean | PASS |
| Honest cross-engine baselines | Read-only JSON assertions against every native pair | 27 pass/12 fail; all 12 failures identical to source/reference baseline; all 29 size disagreements match baseline | PASS — no new discrepancy |
| Final local Python regression, including G5/G6 | `.venv/bin/python -m pytest -m 'not corpus and not linux_only and not cdn' -q`; `/private/tmp/07-python-regression-final.log` | 634 passed, 36 deselected, 2 warnings; 120.71s | PASS (recorded) |
| Standard client suite | `npm --prefix client test`; `/private/tmp/07-client-tests-final.log` | 140 passed; no failures/skips; exports included in package script | PASS (recorded) |
| Production build / strict types | npm build and mypy logs in `/private/tmp/07-client-build-final.log`, `07-review-types-final.log` | Build 1.91s, existing chunk advisory; 35 source files clean | PASS (recorded) |
| G4 technical proxy | `/private/tmp/07-g4-regression-final.log` | 7 passed, 95.02s; does not close literal-contract acceptance | PASS (recorded, limited) |
| Licenses/assets | Consolidated evidence in 07-G6-RESULTS | 19 client gate negatives; resolved runtime closures/notices and Unicode 15.1 artifact checks passed | PASS (recorded) |

### Probe Execution

No PLAN-declared or conventional `scripts/*/tests/probe-*.sh` probe was found. Phase 7's native gate is pytest-based, not a shell probe. Its current-process execution was performed by the coordinating agent and is included in the final 634-pass log; this verifier did not substitute SUMMARY pass counts or claim a new gate invocation.

### Requirements Coverage

| Requirement | Source plan | Description | Status | Evidence |
|---|---|---|---|---|
| EXPO-01 | 03, 04 | DPI page images, individual/all-page ZIP | SATISFIED | Physical viewport rendering, 150/300/custom UI, actual PNG/JPEG dimensions, CRC-clean browser ZIPs, zero-request journeys. |
| EXPO-02 | 02, 03, 04 | Lossless-default compression; explicit downsampling, sizes/preview | SATISFIED | Native save/exact-source fallback; unchanged image samples/exact per-engine rendering; explicit control; real returned-byte preview/download identity. |
| EXPO-03 | 03, 04 | Split PDF into separate files | SATISFIED | Group normalization + shared safe deletion worker; production mapped outputs; actual current styled/rotated 1+2-page download; native/ZIP proof. |
| EXPO-04 | 02, 03, 04 | Flatten PDF | SATISFIED | Native selected-appearance flatten/postconditions; independent filled/state/transformed pixel references; real browser flattened PDF and refusal. |
| EXPO-05 | 01, 02, 03, 04 | Text/Markdown/HTML from same run index | SATISFIED | One indexed block path, metadata/structure, escaped serializers and negative extraction guards; actual current styled downloads. |

All five roadmap-assigned IDs occur in PLAN requirements. No orphaned Phase 7 requirement was found. Pending shared roadmap/requirements checkboxes are orchestrator-owned bookkeeping, not implementation evidence.

### Anti-Patterns Found

| File/scope | Pattern | Severity | Impact |
|---|---|---|---|
| 37 unique PLAN-modified paths | No missing files; no TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER markers | None | No debt-marker blocker. |
| Export state/accumulators and dynamic render paths | Empty initial arrays/nulls are populated by real render/worker/API paths | None | No observable stub, hollow prop or ignored response established. |
| Native engine pair baselines | 12 cross-engine threshold failures; 29 physical-size disagreements | Info | Explicit preexisting source/reference behavior, preserved exactly; not represented as cross-engine passes. |
| Final build/test logs | Existing chunk-size/deprecation warnings | Info | No Phase 7 functional failure. |

The disconfirmation pass specifically checked stale-current-byte races, visually empty flatten output hidden by masks, and unsafe downsampling of mask aliases. Generation/session/version guards, exact independent full-page flatten references plus corruption controls, and direct/aliased protected-mask regression paths provide contrary evidence. Mocked controller tests alone do not prove browser encoding/privacy; saved native/browser artifacts supply that evidence.

### Human Verification Required

None outstanding for this locally authorized phase. The PLAN 04 deferred review of real-browser preview/download/privacy/keyboard evidence was completed by the coordinating agent, including screenshots, rendered layout HTML and actual filled-flatten native preview. Saved raw observations were checked here. This report does not claim a fresh browser run or Safari/Firefox certification.

### Gaps Summary and Limits

No actionable Phase 7 gap remains. No gap was deferred to Phase 8; its PDF/A/DOCX criteria were checked and do not absorb any G6 obligation. Exact same-engine and independent appearance/reference proof satisfies the scoped differential criterion; the separately recorded cross-engine source disagreements remain unchanged and visible.

Preserved external acceptance work: G3 Linux/container/live-CDN checks, Phase 5's literal legal-contract specimen, and production Linux HEIC confinement. These remain open and are not closed by local Phase 7 verification or the G4 technical proxy. No deployment is authorized. Reading-order inference remains conservative; scanned pages receive no OCR, unsupported flatten/images refuse or remain unchanged with notices, and large-limit behavior has automated rather than exhaustive browser coverage.

Verification mechanics: the installed SDK's artifact/link helpers did not parse inline YAML mappings (zero artifacts/empty link paths), so all 11 declared artifacts and 11 links above were verified manually in production source. The requested `~/.Codex/get-shit-done` reference root was absent; available `~/.cursor/get-shit-done` overrides/gates/thinking/calibration references were read. Mandatory-initial/project-skills-discovery references and project-local skill roots were absent. No product or shared metadata was edited, and no commit was made.

---

_Verified: 2026-10-27T10:54:37Z_
_Verifier: Codex (gsd-verifier)_
