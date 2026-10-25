---
phase: 06-page-ops-and-merge
plan: "04"
subsystem: client-image-page-operations
tags: [images, canvas, exif, pdf, geometry, resources, tdd]
requires:
  - phase: 06-01
    provides: Password-aware PDF loading, physical page descriptors, signature inspection, resource isolation and whole-document worker transaction contracts
provides:
  - Physical-point image fit, explicit aspect-lock updates and inverse visible-page placement matrices
  - Bounded local PNG/JPEG/WebP decoding with native EXIF normalization, white compositing and disposable flattened preview
  - Real image XObject/content writes with isolated resources, adjacent-page geometry inheritance and fresh rebase metadata
affects: [06-05, 06-06]
tech-stack:
  added: []
  patterns: [Node built-in tests, native browser decode adapters, immutable byte inputs, isolate-before-write]
key-files:
  created:
    - client/src/pageOps/imageGeometry.mjs
    - client/src/pageOps/imageGeometry.test.mjs
    - client/src/pageOps/images.mjs
    - client/src/pageOps/images.test.mjs
  modified: []
key-decisions:
  - Normalize EXIF exactly once with createImageBitmap imageOrientation from-image; refuse native dimensions that disagree with oriented container metadata.
  - Return the actual flattened canvas as preview and the identical encoded PNG bytes for PDF placement; allocate no object URLs in the helper.
  - Keep signature acknowledgement and localMetadata compatible with transformPages and require the caller transaction to own publication.
requirements-completed: [PAGE-07, PAGE-08, PAGE-09]
duration: approximately 8min
completed: 2026-10-25
---

# Phase 6 Plan 4: Local Image Geometry and Content Summary

**Bounded local image decoding, white compositing and real PDF image placement use the same tested physical-point transform across rotated, cropped and UserUnit pages.**

## Performance

- Completed: 2026-10-25
- Tasks: 2 of 2
- Source/test files: 4
- Requirements listed above identify this plan's primitive coverage; visible UI, observed network and native/three-renderer acceptance remain with plans 05/06 and G5.

## Task Commits

1. Task 1 RED: `5a483c6` — tests for image corners at every quarter rotation, crop/media intersection and fallback, UserUnit and explicit lock behavior.
2. Task 1 GREEN: `eaaea61` — physical-point fit, aspect update, named validation and affine placement.
3. Task 2 RED: `26dcf18` — bounded decode, white composite, resource lifecycle and serialized PDF image tests.
4. Task 2 GREEN: `b938baf` — local decode and PDF writer, plus adversarial encoding cancellation and form appearance preservation coverage.
5. Review regression RED: `a878772` — real 600×782 PNG on Letter, thin-image fits and bounded arithmetic-edge tolerance reproduce three failures.
6. Review fix GREEN: `45d478d` — exact limiting-axis fit and scale-aware residual clamping, with serialized placement and material-outside refusal coverage.

RED commands were run before each implementation module existed and failed on the missing module; the subsequent implementations passed all behavior assertions. No task source was implemented before its RED run.

## Interfaces and Ownership

- `fitImage({width,height}, page)` returns a centered fit in physical points. `page` accepts the current descriptor or visible width/height. Geometry is derived from `CropBox ∩ MediaBox`, falling back to MediaBox for empty/disjoint crop, as `describePage` does.
- `updateAspect(rect, field, value, {locked,ratio})` is pure. `ratio` comes from the oriented decoded image; only locked width/height edits change the paired dimension. The UI owns the checked checkbox state.
- `validatePlacement(rect,page)` returns `{valid:true}` or `{valid:false,code}`. `placementMatrix(rect,pageGeometry)` refuses invalid bounds and maps the image unit square into PDF coordinates, including inverse page rotation and UserUnit division. Fits set the limiting axis exactly to page width/height. Validation tolerates only eight machine-epsilon units relative to each page axis, and the content transform clamps that residue to the edge; materially outside rectangles still refuse.
- `decodeLocalImage(file,{signal,decodeBitmap,createCanvas})` returns `{pngBytes,width,height,preview,dispose}`. `preview` is the actual white-flattened canvas, not the original transparent image. Default adapters use native `createImageBitmap`, OffscreenCanvas or DOM canvas and PNG encoding.
- Input magic overrides MIME/extension. Structural preflight rejects animated PNG/WebP, multiple JPEG frames/MPF/trailing images and ambiguous containers. HEIC brands throw `HEIC_CONVERSION_REQUIRED` without any decoder or network invocation. An explicitly converted PNG enters the same local path.
- Admission limits: 20 MiB input; at most 16,000,000 pixels; maximum dimension 16,384; 64 MiB encoded PNG. Header dimensions are checked before decode and native dimensions afterward. These bounds do not guarantee the native decoder's total allocation.
- Native EXIF orientation is requested deliberately once. An actual orientation-6 JPEG fixture proves the preflight expects swapped dimensions, and rejects a seam returning unnormalized dimensions. Native browser pixel/orientation proof is still G5 work.
- The bitmap closes after drawing. Abort rejects pending native work promptly, closes late bitmap arrivals, and clears the canvas on failure or after a successful preview. Caller must abort on stale/close and call `dispose()` on replaced/discarded successful drafts. Disposal is idempotent; the helper allocates no object URLs. If UI creates its own preview URL from `pngBytes`, that URL belongs to the UI.
- `writeImage(bytes,pngBytes,{password,destination,pageIndex,position='after',rect,acknowledged=false})` returns `{bytes,selectedPage,notices,localMetadata}`. Indices are zero-based. `current-page` requires the validated rect; `new-page` fits the image and inherits exact adjacent MediaBox/CropBox/UserUnit/rotation. Geometry is re-read from current bytes.
- Resource dictionaries are isolated before drawing; a real image XObject and affine content operators are appended. Existing operators, annotations, form appearance streams/references and sibling resources remain intact. Saving explicitly uses `updateFieldAppearances:false`; output bytes remain capped by the PDF core.
- Signed inputs require acknowledgement; encrypted inputs are genuinely decrypted by the shared loader and emit `ENCRYPTED_COPY_UNLOCKED`. `localMetadata` describes all output pages, retains signed provenance, and records `encrypted:false`, matching structural-transform rebasing.
- `IMAGE_ERROR_CODES` is an immutable caller-constant allowlist for `runPdfJob({errorCodes})`. Worker dispatch and UI history/preview publication belong to plan 05; this helper does not mutate session/history or call the text engine.

## Verification

- Initial `node --test client/src/pageOps/imageGeometry.test.mjs` — 8 passed; review coverage increases this to 10 geometry tests.
- Latest `node --test client/src/pageOps/images.test.mjs client/src/pageOps/imageGeometry.test.mjs` — 24 passed, including the real 600×782 PNG/new-Letter-page regression and 1×37 thin-image fit.
- Tests use real small PNG/JPEG/WebP bytes and actual PDF serialization/readback. Assertions inspect embedded image resources, content matrices at 0/90/180/270 degrees, original operators/annotations, inherited sibling immutability, form AP bytes/references, Unicode-password decryption, signature refusal, cleanup and limits.
- The injected Node canvas adapter actually composites RGBA pixels and encodes a real PNG; readback verifies white and half-alpha pixel values. It does not certify a browser's native codec or canvas pixels.
- `npm --prefix client run build` — passed; existing Vite large-chunk advisory remains.
- `git diff --check` for owned files — passed.
- The full client suite is delegated to the root orchestrator's combined frozen-helper run, per explicit coordination instruction; it was not run while the merge executor was writing its RED/GREEN files.
- Browser defaults were checked against [createImageBitmap documentation](https://developer.mozilla.org/en-US/docs/Web/API/Window/createImageBitmap) and [OffscreenCanvas PNG encoding documentation](https://developer.mozilla.org/en-US/docs/Web/API/OffscreenCanvas/convertToBlob). Cantoo matrix composition was checked in the installed 2.9.1 primary source. Context7 tools/CLI were unavailable; no package was installed.

## Deviations from Plan

- Added `acknowledged` and complete `localMetadata` to the writer contract to match the delivered plan-01 signature/rebase correctness requirements, as explicitly directed by orchestration. No shared interfaces were edited.
- Shared STATE/ROADMAP/REQUIREMENTS updates are reserved for the root orchestrator to avoid concurrent metadata writes. Only owned source/tests and this summary were committed.

### Review Fix: Floating-Point Fit Rejection

- **[Rule 1 — Bug]** Review found that multiplying both image dimensions by a common scale could yield a height of `792.0000000000001` and negative top on a 612×792 Letter page, rejecting an ordinary 600×782 image as `IMAGE_OUTSIDE_PAGE`.
- Added geometry, thin-image and actual PNG/PDF serialization regressions first; the focused run reproduced exactly three failures (21 passed).
- Set the limiting axis directly to the page dimension, derive the other from the aspect ratio, and clamp only scale-relative machine-rounding residue in the same bounds path consumed by validation and content matrices. Actual outside rectangles, including a 0.000001 pt overrun, remain rejected.
- Verification: 24 focused tests pass; owned diff check passes. No UI, worker or shared API changed, and no broad suite/corpus run was repeated during parallel UI integration.

## Remaining Integration and Evidence

- Plan 05 wires worker dispatch, controlled aspect checkbox, draft preview, destination-change reset, explicit HEIC conversion action and one transaction/Undo entry.
- Plan 06/G5 must prove native browser PNG/JPEG/WebP decoding and oriented/transparent pixels, visibly correct placement, three-renderer unchanged siblings and observed zero document API traffic. No browser/render completion is claimed here.
- No known stubs or new unmodeled threat surfaces were found. No source bytes, filenames or passwords are logged or persisted; no decoder dependency, endpoint, schema, text-engine or deployment change was introduced.

## Self-Check: PASSED

All four source/test files exist, and all six task/review commits listed above exist in git history. Latest focused tests pass; the initial build passed. The root orchestrator owns the remaining shared-state bookkeeping, integration build and aggregate test result.
