---
phase: 06-page-ops-and-merge
reviewed: 2026-10-25T17:56:50Z
depth: standard
files_reviewed: 18
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
  - server/image_conversion.py
  - server/app.py
  - server/errors.py
  - tests/test_image_conversion.py
  - tests/test_heic_contract.py
  - tools/client_license_gate.mjs
  - tools/client_license_gate.test.mjs
  - .github/workflows/license-gate.yml
  - docs/heic-runtime.md
findings:
  critical: 3
  warning: 1
  info: 0
  total: 4
status: issues_found
scope_status: partial_phase_review
---

# Phase 6: Code Review Report

**Depth:** standard
**Files Reviewed:** 18
**Status:** issues_found — staged review of completed plans 01 and 02 only

## Narrative Findings (AI reviewer)

This pass reviews the committed local PDF/history/worker core through `27c3370` and the converter/license implementation through `8a771d9`, against baseline `0f9167a`. Merge, image, App integration and final browser acceptance work were active and are excluded until a later handoff. The package-lock change was checked as pin evidence but excluded from source-file counts under the review filtering rules. Each listed source file was read completely. No source was modified and no commit was made.

Three negative probes demonstrated violations of the catalog-safety and runtime-license contracts. A fourth demonstrated a response-header regression. These findings are open until fixes and their negative controls are reviewed; this artifact does not certify the entire phase.

## Critical Issues

### CR-01: Deletion skips stream dictionaries and leaves dangling page references

**Classification:** BLOCKER
**File:** `/Users/prempatel/Pictures/pdf-tool/client/src/pageOps/pdfDocument.mjs:249-252`
**Issue:** The deletion safety scan follows only `PDFDict` and `PDFArray`. `PDFRawStream` is a separate object type with its own dictionary, so references in a retained catalog/resource stream are invisible to the scan. `removePage()` then deletes the referenced page object. The operation succeeds with a dangling reference instead of the required `CATALOG_UNSAFE` refusal.

**Evidence:** On a two-page document, register `ctx.stream('kept', {Type:'Metadata', Subtype:'XML', PageTarget:pdf.getPage(0).ref})`, attach its ref as catalog `/Metadata`, and call `transformPages(bytes,{type:'delete',index:0})`. Reloading the returned bytes produces one page and retains `/Metadata /PageTarget 4 0 R`, while `out.context.lookup(target)` is undefined. The custom entry is intentionally unknown: the contract explicitly requires refusing unrecognized catalog references rather than silently breaking them.

**Fix:** Traverse each stream's `.dict` using the same identity, depth and node limits as other graph objects. Reject an unknown reference to the deleted page, or handle it through an explicitly supported rewrite. Add a regression asserting `CATALOG_UNSAFE`, unchanged input bytes, and no output for a retained stream dictionary containing the removed page ref. Exercise nested dictionary/array entries inside a stream dictionary as well.

**Suggested test:** `deletion refuses unknown removed-page references inside retained stream dictionaries`.

### CR-02: Unlisted vendored node_modules bypass the bundle audit

**Classification:** BLOCKER
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

## Warnings

### WR-01: CORS preflights bypass the required privacy/security response headers

**Classification:** WARNING
**File:** `/Users/prempatel/Pictures/pdf-tool/server/app.py:164-167`
**Issue:** Moving `CORSMiddleware` outside `privacy_headers` fixes CORS on synthesized busy responses, but its short-circuit OPTIONS responses never enter the header middleware. They now lack `Cache-Control: no-store, private`, CSP, nosniff, referrer policy and frame policy. This regresses the universal response-header contract and is not covered by the new route privacy assertions.

**Evidence:** `TestClient(create_app()).options('/images/heic-decode', headers={'origin':'http://localhost:5173','access-control-request-method':'POST','access-control-request-headers':'content-type'})` returns HTTP 200 with CORS headers and `access-control-max-age: 600`, but none of the five required privacy/security headers. Preflight carries no document bytes; this finding concerns the broken response-policy guarantee rather than a demonstrated document leak.

**Fix:** Make unconditional header application wrap CORS, while keeping CORS outside the admission/error-producing layer so busy responses still receive CORS headers. Add allowed and rejected preflight tests that assert the same privacy headers as normal/error responses, and retain the existing CORS-on-busy regression.

**Suggested test:** `allowed and rejected CORS preflights retain privacy headers`.

## Review Coverage and Limits

The security checklist covered request/input validation; shell/path/template/header injection; HTML output boundaries; anonymous access and authorization assumptions; cross-origin handling; races and stale publication; memory-only session state; crypto/password/error disclosure; byte/pixel/graph/process bounds; and business/state transitions. No database or account/session authentication boundary is added by the reviewed scope. The concrete defects above concern graph consistency, bundled dependency policy and response headers. No additional proven injection, password disclosure, stale-commit, or production native-execution bypass was identified in this pass.

Focused call checks included cantoo's page-tree removal/insertion and resource inheritance, server scratch/worker interfaces, HTTP middleware lifetime and the license gate's traversal. Existing test pass counts in plan summaries were treated as context, not correctness proof. Four small targeted negative probes were run; no heavy corpus, broad suite, package installation or deployment was performed.

Not verified in this scope: active merge/image/UI code; live mixed text/page Undo; actual worker integration; observed browser network traffic; three-renderer G5 output; Linux native confinement/deployment behavior; and a clean npm CI installation. Production HEIC unavailability is the intentional current policy, not a newly discovered defect.

_Reviewer: Codex (gsd-code-reviewer)_
_Depth: standard_
