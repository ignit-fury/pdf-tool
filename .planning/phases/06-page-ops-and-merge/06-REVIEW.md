---
phase: 06-page-ops-and-merge
reviewed: 2026-10-26T03:55:43Z
depth: standard
files_reviewed: 38
files_reviewed_list:
  - client/package.json
  - client/src/pageOps/pdfDocument.mjs
  - client/src/pageOps/pdfDocument.test.mjs
  - client/src/pageOps/documentHistory.mjs
  - client/src/pageOps/documentHistory.test.mjs
  - client/src/pageOps/applyPageOperation.mjs
  - client/src/pageOps/applyPageOperation.test.mjs
  - client/src/pageOps/pdfWorker.mjs
  - client/src/pageOps/pdfWorker.test.mjs
  - client/src/pageOps/mergeGraph.mjs
  - client/src/pageOps/mergeGraph.test.mjs
  - client/src/pageOps/mergePdf.mjs
  - client/src/pageOps/mergePdf.test.mjs
  - client/src/pageOps/imageGeometry.mjs
  - client/src/pageOps/imageGeometry.test.mjs
  - client/src/pageOps/images.mjs
  - client/src/pageOps/images.test.mjs
  - server/image_conversion.py
  - server/app.py
  - server/errors.py
  - tests/test_image_conversion.py
  - tests/test_heic_contract.py
  - tools/client_license_gate.mjs
  - tools/client_license_gate.test.mjs
  - .github/workflows/license-gate.yml
  - docs/heic-runtime.md
  - client/src/App.jsx
  - client/src/session.mjs
  - client/src/session.test.mjs
  - client/src/Viewer.jsx
  - client/src/style.css
  - client/src/pageOps/PageOpsPanel.jsx
  - client/src/pageOps/pdfJob.worker.mjs
  - client/src/find/indexing.mjs
  - client/src/find/indexing.test.mjs
  - harness/page6_fixture.py
  - tools/materialize_page6.mjs
  - tests/test_page6_merge_render.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
resolved_findings:
  critical: 9
  warning: 1
  total: 10
status: clean
scope_status: source_review_complete_browser_acceptance_separate
---

# Phase 6: Code Review Report

**Depth:** standard
**Files Reviewed:** 38
**Status:** clean — no unresolved source-review findings

## Narrative Findings (AI reviewer)

This pass reviews the committed local PDF/history/worker core through `3b96f3b`, converter/license implementation through `52a1876`, merge implementation through `f45b8d0`, image implementation through `45d478d`, integration/indexing through `8a0b532`, and G5 fixture/materializer/render tests through `2105bef` / `b68eb3c`, against baseline `0f9167a`. The package-lock change was checked as pin evidence but excluded from source-file counts under the review filtering rules. Each listed source file was read completely. The reviewer modified only this report and made no commit.

All reviewed files meet quality standards. No unresolved issues found. Nine BLOCKERs and one WARNING are resolved: source fixes were inspected and twenty-four focused permanent regression cases passed independently. Frontmatter finding counts include only open findings; resolved records below retain their original evidence. The clean status applies to this source-review scope, not completion of every browser, platform or release acceptance gate. Root-owned browser verification remains separate.

## Critical Issues

### CR-01: Deletion skips stream dictionaries and leaves dangling page references

**Classification:** BLOCKER
**Status:** RESOLVED in `7255abc`; inspected stream traversal and independently ran the permanent deleted/surviving-reference regression, 1 passed. Its RED case is `f9a25f9`.
**File:** `/Users/prempatel/Pictures/pdf-tool/client/src/pageOps/pdfDocument.mjs:249-252`
**Issue:** The deletion safety scan follows only `PDFDict` and `PDFArray`. `PDFRawStream` is a separate object type with its own dictionary, so references in a retained catalog/resource stream are invisible to the scan. `removePage()` then deletes the referenced page object. The operation succeeds with a dangling reference instead of the required `CATALOG_UNSAFE` refusal.

**Evidence:** On a two-page document, register `ctx.stream('kept', {Type:'Metadata', Subtype:'XML', PageTarget:pdf.getPage(0).ref})`, attach its ref as catalog `/Metadata`, and call `transformPages(bytes,{type:'delete',index:0})`. Reloading the returned bytes produces one page and retains `/Metadata /PageTarget 4 0 R`, while `out.context.lookup(target)` is undefined. The custom entry is intentionally unknown: the contract explicitly requires refusing unrecognized catalog references rather than silently breaking them.

**Fix:** Traverse each stream's `.dict` using the same identity, depth and node limits as other graph objects. Reject an unknown reference to the deleted page, or handle it through an explicitly supported rewrite. Add a regression asserting `CATALOG_UNSAFE`, unchanged input bytes, and no output for a retained stream dictionary containing the removed page ref. Exercise nested dictionary/array entries inside a stream dictionary as well.

**Suggested test:** `deletion refuses unknown removed-page references inside retained stream dictionaries`.

### CR-02: Unlisted vendored node_modules bypass the bundle audit

**Classification:** BLOCKER
**Status:** RESOLVED in `52a1876`; skips now require an exact separately audited runtime lock root. Independently ran the vendored-notice/WASM regression, 1 passed. Its RED case is `39a746c`.
**File:** `/Users/prempatel/Pictures/pdf-tool/tools/client_license_gate.mjs:75-79`
**Issue:** `filesBelow()` skips every directory named `node_modules`, assuming its contents have a separate audited lock entry. That assumption is never checked. A wrapper can ship vendored code under `dist/node_modules` with no corresponding lock entry, and both its forbidden notices and unknown WASM are entirely skipped. The actual runtime closure can therefore pass despite bundled AGPL/LGPL code.

**Evidence:** A temporary fixture with one correctly locked/installed MIT `wrapper`, a permissive root `LICENSE`, and these additional files returns `[]` from `auditClientClosure()`:

```text
node_modules/wrapper/dist/node_modules/copyleft/LICENSE
  GNU AFFERO GENERAL PUBLIC LICENSE Version 3
node_modules/wrapper/dist/node_modules/copyleft/decoder.wasm
  [unreviewed WASM bytes]
```

There is no `copyleft` entry in the lock. The fixture was removed after the probe.

**Fix:** Skip only exact directories that are independently covered by an audited runtime lock entry. Traverse other nested `node_modules` directories, or fail closed on unlisted bundled package roots. Add a negative fixture for vendored `dist/node_modules` without lock entries; it must report the forbidden bundled license and/or missing WASM provenance. Preserve auditing of legitimate separately locked nested dependencies.

**Suggested test:** `unlisted vendored node_modules cannot hide forbidden notices or WASM`.

### CR-03: Copyleft licenses after the first 64 KiB of a bundle are ignored

**Classification:** BLOCKER
**Status:** RESOLVED in `52a1876`; all bounded source text is scanned. Independently ran GPL, LGPL and AGPL headers beyond 64 KiB, 3 passed. Their RED cases are `39a746c`.
**File:** `/Users/prempatel/Pictures/pdf-tool/tools/client_license_gate.mjs:159-165`
**Issue:** Source files up to 8 MiB are accepted, but only their first 65,536 characters are examined for bundled license evidence. Concatenated JavaScript bundles often put a third-party component's own header after preceding modules. A forbidden license later in such a bundle receives no finding, while the wrapper's MIT metadata supplies a pass.

**Evidence:** A temporary MIT wrapper fixture with a permissive `LICENSE` and this `bundle.mjs` returns `[]`:

```javascript
'/*' + 'x'.repeat(66000) + '*/\n' +
'/* SPDX-License-Identifier: LGPL-3.0-only */\nexport default 1;'
```

The entire source is well below the existing 8 MiB scan limit and is already read into memory. The fixture was removed after the probe.

**Fix:** Scan all of the already bounded source text for forbidden bundled licenses. If only a prefix can be inspected, fail closed for files whose remaining content is uninspected. Add permanent negative controls with GPL/LGPL/AGPL component headers beyond 64 KiB, including a normal concatenated bundle with a permissive first component.

**Suggested test:** `copyleft component headers beyond 64 KiB fail bundled source audit`.

### CR-04: Automatic image fits can fail their own placement validation

**Classification:** BLOCKER
**Status:** RESOLVED in `45d478d`; the limiting axis is exact and placement clamps only a few machine rounding units before producing content. Independently ran the Letter/thin-image fit, material-outside refusal and real 600×782 PNG serialization regressions, 3 passed. Their RED cases are `a878772`.
**File:** `/Users/prempatel/Pictures/pdf-tool/client/src/pageOps/imageGeometry.mjs:23-24`
**Affected caller:** `/Users/prempatel/Pictures/pdf-tool/client/src/pageOps/images.mjs:189-192`
**Issue:** Multiplying both image dimensions by a floating-point scale can slightly exceed the limiting page dimension. Centering then produces a negative coordinate, and the strict bounds check rejects the helper's own fit. This blocks valid images in the new-page path and automatic placement drafts.

**Evidence:** `fitImage({width:600,height:782},{visibleWidth:612,visibleHeight:792})` returns `{left:2.163682864450095,top:-5.684341886080802e-14,width:607.6726342710998,height:792.0000000000001}`. Passing that result to `validatePlacement` for the same Letter page returns `{valid:false,code:'IMAGE_OUTSIDE_PAGE'}`. `writeImage` derives its new-page rect using this fit and immediately passes it to the same validator through `placementMatrix`.

**Fix:** Set the limiting fitted dimension directly to the corresponding page dimension, derive the paired dimension from the aspect ratio, and normalize rounding residue when centering. If validation tolerates rounding, use a scale-aware numerical tolerance and preserve rejection of materially out-of-bounds user rectangles. Add a real 600×782 PNG new-page regression on a 612×792 page and fractional/cropped/UserUnit fit cases.

**Suggested test:** `automatic fit remains inside Letter bounds for a 600 by 782 image`.

### CR-05: Shared link annotations are transformed repeatedly during normalization

**Classification:** BLOCKER
**Status:** RESOLVED in `f45b8d0`; ownership preflight now covers every annotation before the no-AcroForm early return. Independently ran shared identity, duplicate slot, wrong page ownership and separate-Link positive regressions, 4 passed. Their RED cases are `67aadab`.
**File:** `/Users/prempatel/Pictures/pdf-tool/client/src/pageOps/mergeGraph.mjs:114-118`
**Affected mutation:** `/Users/prempatel/Pictures/pdf-tool/client/src/pageOps/mergePdf.mjs:67-90`
**Issue:** Ownership preflight detects shared widget identities, but not shared ordinary annotations. The shared copier preserves a link annotation's identity, and normalization mutates its rectangle once per owning page. An ambiguous source graph is therefore accepted and published with incorrect link geometry rather than safely refused.

**Evidence:** Construct two 200×300 source pages whose `/Annots` arrays contain the same Link annotation ref, with `/Rect [10 20 30 40]` and `/A << /S /URI /URI (https://example.test) >>`. Merge with `normalizeTo:{visibleWidth:400,visibleHeight:600}`. The operation succeeds and both imported rectangles become `[40,80,120,160]`; each was scaled twice. One isolated annotation per page would require `[20,40,60,80]`. No special form or active script is needed.

**Fix:** Preflight identities and page ownership for every annotation, including repeated references in a single page's array and inconsistent explicit `/P` values. Refuse ambiguous sharing with a fixed merge-graph error before copying or mutation. Alternatively, implement an explicit supported per-owner clone policy that preserves all annotation relationships; do not mutate shared dictionaries repeatedly.

**Suggested test:** `normalization refuses shared non-widget annotation identities before mutation`.

### CR-06: Deferred image completion publishes coordinates for a page selected earlier

**Classification:** BLOCKER
**Status:** RESOLVED in `c55ee55`; both local and converted decode obtain destination metadata from the live destination ref after completion, and commit rejects a draft belonging to another page. Independently ran local deferred navigation, converted deferred navigation and obsolete-output disposal regressions, 3 passed. Their RED cases are `4136c90`.
**File:** `/Users/prempatel/Pictures/pdf-tool/client/src/App.jsx:259-264`
**Related paths:** HEIC completion and the page-change effect in the same file.
**Issue:** Before the fix, asynchronous decode/conversion captured `page` and its geometry at start. Navigation stayed available. The page-change effect ran before the image draft existed, or while it was still a HEIC disclosure, and did not rerun when completion published a draft for the old page. The viewer hid its overlay while placement validation and commit used the new page with old coordinates.

**Evidence:** Executing the actual pre-fix `chooseImage` body with a deferred decoder, selecting page 2 before resolving it, produced `{selectedPage:2,draftPage:1,rect:{left:0,top:0,width:600,height:800},validOnSelectedPage:{valid:false,code:'IMAGE_OUTSIDE_PAGE'},overlayVisible:false}` for a second 100×100 page. The same captured-page logic existed after HEIC conversion.

**Fix:** Resolve the current destination only after decode, dispose stale results, and verify draft/page identity immediately before placement. These changes are implemented and covered by the passing regressions above.

### CR-07: Valid converted PNGs above 20 MiB were rejected by the browser

**Classification:** BLOCKER
**Status:** RESOLVED in `c55ee55`; response streaming admits up to the server's 64 MiB PNG cap, and `convertedPng:true` raises only PNG input admission while retaining raw-image, dimension and pixel limits. Independently ran the converted/raw boundary regression, 1 passed. Its RED case is `4136c90`.
**Files:** `/Users/prempatel/Pictures/pdf-tool/client/src/App.jsx:275-280`; `/Users/prempatel/Pictures/pdf-tool/client/src/pageOps/images.mjs:151-167`
**Issue:** The server contract allowed PNG output up to 64 MiB, but both response streaming and local re-decoding applied the 20 MiB raw-upload cap. A successful permitted conversion could never reach placement.

**Evidence:** A structurally valid 2×1 PNG containing a permitted ancillary chunk makes the input exceed 20 MiB while remaining below 64 MiB. Before the fix, `decodeLocalImage` refused it before decode. The permanent test now proves explicit converted PNG admission, raw-image refusal, non-PNG refusal, 64 MiB refusal and unchanged pixel checks.

**Fix:** Keep the selected raw-image cap at 20 MiB and explicitly admit only converted PNG responses up to 64 MiB. These changes are implemented and covered above.

### CR-08: Undo restores progress without initializing a resumable indexing controller

**Classification:** BLOCKER
**Status:** RESOLVED in `8a0b532`; new producers receive saved total/completed/failed progress, in-flight status becomes stopped, restored sessions seed cached page results, and explicit Resume lazily initializes deferred analysis. Independently ran stopped/failed/in-flight producer and stopped/in-flight mixed-Undo regressions, 5 passed. Their RED cases are `83a99f8`. Undo itself schedules no source upload in those tests.
**File:** `/Users/prempatel/Pictures/pdf-tool/client/src/App.jsx:161-167`
**Related restoration:** `/Users/prempatel/Pictures/pdf-tool/client/src/App.jsx:202-206` and `:377-380`
**Issue:** Undo restores the saved `indexProgress` status and page sets, then sets `deferAnalysis=true`, leaving `indexingRef` null. A stopped or active search therefore shows Resume/Stop controls that do nothing. Reselecting the Find panel clears the deferral and constructs a fresh controller, but it has the default total of zero and empty completed/failed sets. Automatic initialization runs only when the restored UI status is `idle`. Resume then reports 0/0 complete and clears the restored search matches; an `indexing` snapshot can remain stuck indefinitely.

**Evidence:** Analyze a multi-page document, start Find indexing, stop after a partial result, perform a page operation, Undo, reselect Find and replace, then Resume. A Node probe using the actual controller and App initialization predicate with restored progress `{completed:1,completedPages:[1],total:3,status:'stopped'}` produces `{reads:0,last:{completed:0,completedPages:[],total:0,failedPages:[],status:'complete'}}`. Immediately after Undo, before reselecting the panel, the controller is absent because the creation effect explicitly returns for `deferAnalysis`.

**Fix:** Reconstruct a fresh controller with the saved total/completed/failed progress, without retaining old controllers or promises. Make explicit Resume initialize deferred analysis and the controller before running it. Restore in-flight work to a resumable state, or resume only after an explicit server action; Undo itself must continue making no API requests. Cover stopped, failed and in-flight indexing snapshots in a mixed page/text Undo regression, checking actual page fetches, preserved matches, controller freshness and absence of Undo-triggered uploads.

**Suggested test:** `mixed Undo restores a paused index that resumes remaining pages without losing completed matches`.

### CR-09: Minified PDF string names caused valid deletion to refuse

**Classification:** BLOCKER
**Status:** RESOLVED in `3b96f3b`; PDF string/hex-string detection now uses imported classes and `instanceof`, preserving the strict retained-stream reference guard. Independently ran both real 40-page sequence and renamed-constructor regressions, 2 passed. Root also reported the rebuilt-browser insert/move/rotate/delete and Undo sequence passing with zero API requests.
**File:** `/Users/prempatel/Pictures/pdf-tool/client/src/pageOps/pdfDocument.mjs:133`
**Issue:** The root's built-worker test exposed a difference hidden by unbundled Node execution. Named destinations were identified using `constructor.name === 'PDFString'` / `'PDFHexString'`. Production minification changes those names, so the catalog preflight rejected a valid string destination as `CATALOG_UNSAFE`, blocking deletion of a newly inserted blank page.

**Evidence:** The root observed the failed deletion on the existing 40-page `mixed_scanned.pdf` after insert, move and rotate. The permanent regression repeats that exact byte-level sequence and renames both constructor `name` properties to simulate production bundling; the fixed implementation passes while preserving original input bytes and page metadata.

**Fix:** Use type identity instead of class-name strings. The implemented imported `PDFString` and `PDFHexString` checks address that cause without relaxing unsupported graph refusal.

## Warnings

### WR-01: CORS preflights bypass the required privacy/security response headers

**Classification:** WARNING
**Status:** RESOLVED in `52a1876`; a pure ASGI header wrapper now surrounds CORS and admission. Independently ran the allowed/rejected preflight and route-error regression, 1 passed. Its RED case is `39a746c`.
**File:** `/Users/prempatel/Pictures/pdf-tool/server/app.py:164-167`
**Issue:** Moving `CORSMiddleware` outside `privacy_headers` fixes CORS on synthesized busy responses, but its short-circuit OPTIONS responses never enter the header middleware. They now lack `Cache-Control: no-store, private`, CSP, nosniff, referrer policy and frame policy. This regresses the universal response-header contract and is not covered by the new route privacy assertions.

**Evidence:** `TestClient(create_app()).options('/images/heic-decode', headers={'origin':'http://localhost:5173','access-control-request-method':'POST','access-control-request-headers':'content-type'})` returns HTTP 200 with CORS headers and `access-control-max-age: 600`, but none of the five required privacy/security headers. Preflight carries no document bytes; this finding concerns the broken response-policy guarantee rather than a demonstrated document leak.

**Fix:** Make unconditional header application wrap CORS, while keeping CORS outside the admission/error-producing layer so busy responses still receive CORS headers. Add allowed and rejected preflight tests that assert the same privacy headers as normal/error responses, and retain the existing CORS-on-busy regression.

**Suggested test:** `allowed and rejected CORS preflights retain privacy headers`.

## Review Coverage and Limits

The security checklist covered request/input validation; shell/path/template/header injection; HTML output boundaries; anonymous access and authorization assumptions; cross-origin handling; races and stale publication; memory-only session state; crypto/password/error disclosure; byte/pixel/graph/process bounds; and business/state transitions. No database or account/session authentication boundary is added by the reviewed scope. The concrete defects above concern graph consistency, bundled dependency policy and response headers. No additional proven injection, password disclosure, stale-commit, or production native-execution bypass was identified in this pass.

Focused call checks included cantoo's page-tree removal/insertion and resource inheritance, server scratch/worker interfaces, HTTP middleware lifetime, license traversal, shared-copier field/AP/resource/destination handling, normalization geometry, image ownership/disposal, explicit-analysis gating, immutable opened/current/replay byte ownership, mixed snapshot restore, single mutation ownership, draft freshness and actual UI geometry bindings. Existing test pass counts in plan summaries were treated as context, not correctness proof. Small targeted negative probes and twenty-four focused fix regressions were run independently; no heavy corpus, broad suite, package installation or deployment was performed by the reviewer.

The frozen G5 source review found no additional proven defect. Actual outputs call production helpers; the independent Python references do not inspect production output or call production geometry helpers. Black-tile oracles define bounded intended footprints, full expected-RGB comparisons check pixels inside those footprints, siblings remain entirely unmasked, and deliberate font/widget/destination/sibling/vacuity corruption controls exercise assertion reliability. The gate also records source/output hashes and graph/physical metadata. No gate suite was rerun by the reviewer; the delegated evidence reports 7 passing tests, 24 output PDFs, 53 pages and 159 exact mapped same-engine comparisons.

The gate's 64 cross-engine UserUnit size disagreements remain explicitly recorded against identical independent baselines; they are not presented as passing cross-engine comparisons. Root-owned browser network/mixed-history/native-image observations are reported separately; this source review does not replace those acceptance gates. Linux native confinement/deployment behavior and a clean npm CI installation remain unexecuted locally. Production HEIC unavailability is the intentional current policy, not a newly discovered defect.

_Reviewer: Codex (gsd-code-reviewer)_
_Depth: standard_

## Root browser addendum — 2026-10-26

After the independent source review, responsive testing reproduced hidden page-tool
file inputs with 100% width, causing document scrollWidth 519 at a 320 px viewport.
Root isolated the CSS specificity conflict and committed `f8fc3e4`, restoring a 1 px
box only for `.page-ops input.visually-hidden`. Rebuilt application checks show
320/320 and 760/760 viewport/scroll widths, visible controls and focus outline.
No open source finding is introduced; this addendum is root browser proof, not a claim
that the earlier independent reviewer reviewed the later CSS commit.

Historical impeccable side-tab warning: no thick one-sided card border exists in
current CSS; 1 px brand/inspector dividers remain intentional structural separators.
No ignore was added and no matching issue remains.
