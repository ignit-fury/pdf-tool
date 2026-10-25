---
phase: 6
slug: page-ops-and-merge
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-30
updated: 2026-10-25
---

# Phase 6 — Validation Strategy

Use existing Node 22 built-in tests, pytest and installed renderers. No Vitest, Playwright, npx download, host/container install or deployment. Current source baseline is 630ca28, delivery docs through 0f9167a. Root's 25 October baseline is 41 Node tests and 527 Python passed/36 deselected; those are baseline results, not Phase 6 passes.

## Commands and ownership

| Scope | Automated command | Owner |
|---|---|---|
| PDF/history/worker | `node --test client/src/pageOps/pdfDocument.test.mjs client/src/pageOps/documentHistory.test.mjs client/src/pageOps/applyPageOperation.test.mjs client/src/pageOps/pdfWorker.test.mjs` | 06-01 |
| HEIC process/HTTP | `.venv/bin/python -m pytest -q tests/test_image_conversion.py tests/test_heic_contract.py` | 06-02 |
| Merge graphs | `node --test client/src/pageOps/mergeGraph.test.mjs client/src/pageOps/mergePdf.test.mjs` | 06-03 |
| Image geometry/write | `node --test client/src/pageOps/imageGeometry.test.mjs client/src/pageOps/images.test.mjs` | 06-04 |
| Session integration | `node --test client/src/session.test.mjs` | 06-05 |
| Client regression/build | `npm --prefix client test`; `npm --prefix client run build` | Each wave; final 06-06 |
| License negatives/closures | `node --test tools/client_license_gate.test.mjs`; `node tools/client_license_gate.mjs`; `.venv/bin/python tools/license_gate.py` | 06-02; final 06-06 |
| Fast G5 controls | `.venv/bin/python -m pytest -q tests/test_page6_merge_render.py -k negative_control` | 06-06 task 1 |
| Complete G5 | `.venv/bin/python -m pytest -q tests/test_page6_merge_render.py` | 06-06 task 3 |
| Types/Unicode | `.venv/bin/python -m mypy`; `.venv/bin/python tools/build_search_unicode.py --check` | 06-06 task 3 |
| Applicable local regression | `.venv/bin/python -m pytest -q -m 'not corpus' --ignore=tests/test_cdn.py --ignore=tests/test_linux_sandbox.py` | 06-06 task 3 |
| G4 technical proxy if excluded above | `.venv/bin/python -m pytest -q tests/test_gate_g4.py` | 06-06 task 3 |

Every new behavior test follows RED → GREEN. Config/glue/styling use builds and actual browser checks. Focused per-change feedback targets under 60 seconds; full all-page/render/regression checks may take longer and still must run before G5. Do not run broad CPU/render stress concurrently with browser proof. No repeat full-corpus sweep is required.

## Requirement/failure map

| Requirement/source | Acceptance | Owning checks |
|---|---|---|
| PAGE-01 / D-6.5 | Any position, actual adjacent MediaBox origin/size/UserUnit/rotation, shown before insert | 01 Node; 06 browser |
| PAGE-02..04 / D-6.6 | Scanned-page independence, physical refs, last-page/no-op, safe destinations/widgets after delete | 01 Node; 06 graph/render/browser |
| PAGE-05 / D-6.7 / A-6.5 | Default sizes, explicit normalization, nested named/direct outlines, Tx/Btn/Ch/Sig/AP/DR/DA/CO and actual notices | 03 Node; 06 graph/render/browser |
| PAGE-06 / D-6.3 / A-6.3 | Two used visible distinct font programs; real + exact-name controlled variant; bad reuse visibly fails | 03 Node; 06 three-engine |
| PAGE-07 local | PNG/JPEG/WebP, white alpha composite, EXIF orientation, inherited new-page geometry | 04 Node; 06 browser/render |
| PAGE-07 HEIC / A-6.1 | Explicit image-only conversion, actual codec, caps, failures/cleanup/slots/disconnect | 02 pytest; 06 browser |
| PAGE-08 / D-6.4 / A-6.4 | Visible checked lock, crop/rotation/UserUnit placement, inherited/own-shared sibling immutability | 01/04 Node; 06 render/browser |
| PAGE-09 / D-6.1 / A-6.6 | Observed configured-API zero traffic before Open through local download; only disclosed HEIC exclusion | 05 gating; 06 actual connector |
| Mixed Undo / 24 Oct update | Exact preceding bytes/baseline/recipe/font/color/selection, fresh controllers, cache recovery, immutable opened original | 01/05 Node; 06 browser/digests |
| Atomicity/memory/signatures | Fail/stale/cancel/close/no-op do not commit/pop; 30s worker; fail-closed local signatures | 01/05 Node; 06 browser |
| A-6.2 closure | Resolved transitive/optional/bundled graph, forbidden/unknown/drift failures | 02 gate/CI |

Limits chosen by plan 01: 50MiB local input/current PDF, 200MiB unique retained buffers, 300MiB owned transaction buffers, 100 snapshots; refuse without eviction. Existing server 50MiB source/80MiB output limits stay unchanged. A prior >50MiB text output gets a named local refusal retaining bytes/history/download. Count backing stores, not all native/renderer/JS heap memory.

## Wave 0 ownership

Each new test is created RED-first in its named plan. 01 owns pdfDocument/documentHistory/applyPageOperation/pdfWorker tests and npm discovery; 02 owns converter/HTTP/license tests; 03 owns mergeGraph/mergePdf tests; 04 owns imageGeometry/images tests; 05 extends session tests and creates concrete worker entry; 06 owns fixture builder/materializer/independent renderer tests. No unowned missing scaffold. No new dependency/framework is needed.

## Actual browser proof — 06-06 task 2 owns every row

Use existing connector. Begin observation before Open after app boot; resolve configured API origin/path prefix at segment boundaries. Empty base means same-origin fetch/xhr observation with only genuine `/assets/` static exclusions. Do not enumerate/exempt historical API routes. Retain RED provenance `/private/tmp/pdf-tool-phase6-network-red-20261025.json`: actual POST /upload and GET page runs. Record fresh GREEN request methods/URLs/types/counts on built output through local password, rail visibility, panel switching, navigation, all page operations, PDF merge, PNG/JPEG/WebP, Undo/download. Require zero matching requests. Separate explicit Analyze/HEIC journeys prove the only intended crossings and image-only payload without PDF/password.

Record date/browser/revision, source/download digests, screenshot/capture paths and actual outcomes in `06-G5-RESULTS.md`. Must observe: inheritance before insert; scanned keyboard reorder/rotate/delete/Undo; form/outline collision/no-collision/no-fields notices; unchecked normalization; checked lock/live white preview on rotated/cropped pages; EXIF/transparency; 320/760px layout/focus; native find/input Undo; mixed text/page history/cache/password/style; signed/unlocked-copy disclosures; immutable original; cancel/stale/timeout/retention refusal; HEIC actual success/unavailable/cancel/failure. Connector automation satisfies these observations without a user approval pause. Remove injected routes/observers and close sensitive documents afterward.

## Renderer integrity

Generate actual production outputs and cover every generated page. Exact same-engine mapped equality outside intended image content; unaffected siblings unmasked; intended visual changes nonvacuous. Retain existing cross-engine tolerance. qpdf `--check --warning-exit-0` and pdfcpu `validate -m relaxed` must run. Missing tools/failed output never become passing skips. Use final visible Arial pair from research, plus labeled full-name collision variant changing both BaseFont/Descriptor FontName; prove variant itself unchanged and bad page-0 TT2→page-1 TT0 reuse visibly fails all three engines. Historical space-only pair and harmless reverse control are insufficient. Construct inherited and own-shared resource siblings, recording historical corpus absence rather than inventing a new scan.

## Four-source coverage audit

| Source | ID/item | Plans | Status |
|---|---|---|---|
| GOAL | Browser page operations with disclosed HEIC-only exception | 01–06 | COVERED |
| REQ | PAGE-01 | 01,05,06 | COVERED |
| REQ | PAGE-02 | 01,05,06 | COVERED |
| REQ | PAGE-03 | 01,05,06 | COVERED |
| REQ | PAGE-04 | 01,05,06 | COVERED |
| REQ | PAGE-05 | 03,05,06 | COVERED |
| REQ | PAGE-06 | 03,06 | COVERED |
| REQ | PAGE-07 | 02,04,05,06 | COVERED |
| REQ | PAGE-08 | 01,04,05,06 | COVERED |
| REQ | PAGE-09 | 01,02,05,06 | COVERED |
| CONTEXT | D-6.1/A-6.1/A-6.6 local/HEIC/configured API | 02,05,06 | COVERED |
| CONTEXT | D-6.2/version exact cantoo 2.9.1 | 01 | COVERED |
| CONTEXT | D-6.3/A-6.3 no name-keyed optimization | 03,06 | COVERED |
| CONTEXT | D-6.4/A-6.4 resource clone/constructed fixtures | 01,04,06 | COVERED |
| CONTEXT | D-6.5 adjacent blank geometry | 01,05,06 | COVERED |
| CONTEXT | D-6.6 any page/no classification permission | 01,05,06 | COVERED |
| CONTEXT | D-6.7/A-6.5 sizes/outlines/forms/notices | 03,05,06 | COVERED |
| CONTEXT | A-6.2 client closure gate | 02 | COVERED |
| CONTEXT | 24 Oct actual App/Node/browser/local work | 01,05,06 | COVERED |
| RESEARCH | Actual decryption/local signatures/unlocked output | 01,03,05,06 | COVERED |
| RESEARCH | Three byte identities/shared history+owner/prepare/fresh controllers | 01,05,06 | COVERED |
| RESEARCH | Shared copier real refs; Tx/Btn/Ch/Sig/AP/DR/DA/CO; XFA/scripts refusal | 03,06 | COVERED |
| RESEARCH | Bounded graphs/deletion repair/explicit normalization | 01,03,06 | COVERED |
| RESEARCH | Crop/rotation/UserUnit/EXIF/white raster/cleanup | 04,05,06 | COVERED |
| RESEARCH | HEIC body/probe/caps/slots/disconnect/child cleanup/confinement fail-closed | 02,05,06 | COVERED |
| RESEARCH | Linux codec recipe/config only; no host install; actual platform limits | 02,06 | COVERED |
| RESEARCH | Transitive/optional/bundled/unknown licensing; no new packages | 02,06 | COVERED |
| RESEARCH | Visible font pair, exact-name corruption control, all-page three-engine validators | 03,06 | COVERED |
| RESEARCH | API-base observer/static exclusions/download/accessibility | 05,06 | COVERED |

Explicit normalization is covered. Deferred splitting/export/image extraction/default normalization are excluded by source scope. No text rewrite engine/rule change.

## Completion limits

All execution results are pending until tasks run. `wave_0_complete` becomes true only after owned tests/scaffolds exist. G3 Linux/container/CDN and G4 literal legal-contract specimen remain open. Native HEIC Linux containment is unproven locally and required production confinement fails closed. Root owns metadata and independent checker/review convergence before execution.
