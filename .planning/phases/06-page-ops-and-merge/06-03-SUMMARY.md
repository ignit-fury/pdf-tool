---
phase: 06-page-ops-and-merge
plan: "03"
subsystem: client-pdf
tags: [pdf-lib, merge, acroform, outlines, fonts, geometry, tdd]
requires:
  - phase: 06-01
    provides: Bounded local loading, genuine password decryption, signature detection and immutable page geometry helpers
provides:
  - Atomic local PDF merge with explicit opt-in normalization
  - Shared-copier interactive form, outline, named-destination and internal-link imports
  - Serializable import review with source identity and complete field/bookmark outcomes
affects: [06-05, 06-06, PAGE-05, PAGE-06, PAGE-09]
tech-stack:
  added: []
  patterns: [page-reference-first copying, bounded semantic graph preflight, independent field and resource namespaces, affine normalization]
key-files:
  created:
    - client/src/pageOps/mergeGraph.mjs
    - client/src/pageOps/mergeGraph.test.mjs
    - client/src/pageOps/mergePdf.mjs
    - client/src/pageOps/mergePdf.test.mjs
  modified: []
key-decisions:
  - Keep AP streams and local resource aliases intact; namespace DA and global DR resources independently for each effective field resource scope.
  - Recover missing default fonts from AP only when all relevant appearances identify the same font object; ambiguous resources refuse.
  - Explicit normalization flattens page rotation into one affine transform, preserves aspect ratio with centered margins, and transforms widget appearances and default font sizes.
  - Refuse requested normalization for unsupported annotations or a shared field requiring incompatible fixed font scales; default-preserving merge remains available.
requirements-completed: [PAGE-05, PAGE-06, PAGE-09]
duration: 511min wall including quota interruption
completed: 2026-10-25
---

# Phase 6 Plan 3: PDF Merge Summary

**Local PDF merge preserves real font programs, page geometry, interactive form hierarchies and nested bookmarks through one memoized object copier.**

## Performance

- Recorded RED commit: 2026-10-25T09:25:17Z.
- Completed: 2026-10-25; elapsed wall time includes the quota interruption between the two tasks.
- Tasks: 2/2. Source/test files: 4.
- Plan 01 dependency confirmed complete by the orchestrator (`bea2069` summary; `7457739` root progress).

## Task Commits

1. Task 1 RED: `c68ea42` — serialized form and outline graph tests.
2. Task 1 GREEN: `b9fa660` — shared-copier form and outline preservation.
3. Task 2 RED: `7cd86b0` — atomic merge, geometry, password, signature and font tests.
4. Task 2 GREEN: `0f90a29` — public merge/review, affine normalization and adversarial graph refinements.

## Exported Contracts

- `inspectPdfImport(bytes, {password, existingBytes, existingPassword, filename})` returns data only: `pageCount`, `pages`, `signed`, `existingSigned`, `encrypted`, `formCount`, `collisionCount`, `prefix`, `bookmarkCount`, `notices`, and SHA-256 `sourceIdentity`.
- `mergePdf(destinationBytes, sourceBytes, {password, sourcePassword, filename, position, normalizeTo, acknowledged, sourceAcknowledged, sourceIdentity})` returns `{bytes, selectedPage, notices, localMetadata}`. `position` is zero-based; the default is append. Passing the reviewed `sourceIdentity` detects changed source bytes. Every commit independently reloads and rechecks both inputs.
- `localMetadata` contains `pageCount`, `pages`, `signed`, and `encrypted:false`. Known signed state remains true after the disclosed signature-invalidating rewrite so later mutations retain the acknowledgement gate.
- `preflightMergeGraph(source, {destination, filename})` returns the internal validated graph, counts, chosen prefix and notices. This graph stays inside the worker operation.
- `importMergeGraph({source, destination, copier, pageMap, prefix, preflight, filename})` imports catalog structures using the same copier that copied source page references first. `pageMap` maps source `PDFRef` objects to actually inserted destination page references.
- Notices include form collision, no-collision, no-fields and bookmark/no-bookmark outcomes, the geometry policy, and signature invalidation where applicable. Encryption rewrites include the shared `{code:'ENCRYPTED_COPY_UNLOCKED'}` notice. No network calls are introduced.

## Supported and Refused Boundaries

Supported forms include ordinary Tx, Btn and Ch fields; hierarchical names and inherited defaults; multiple widgets and radio options; values/options; existing appearance streams; independent field/DR namespaces; `NeedAppearances`, calculation order and signature flags. Sig fields retain their structure only after the separate imported-signature acknowledgement. Destination fields, catalog entries, names categories and outlines remain attached. Imported outlines retain Unicode titles, styles, colors and child structure under the filename root. Named and direct destinations and internal link actions resolve to inserted pages.

The importer refuses XFA, JavaScript/additional actions, unsupported action kinds, ambiguous fonts/default appearances, unsafe field/AP/outline/destination graphs, orphan widgets, invalid targets and graph limits with named errors. Limits are 50 MiB per input/output, depth 64 and 100,000 visited graph entries. It neither flattens fields nor silently removes unsupported structures.

Default merge preserves each page's original MediaBox, CropBox, rotation and UserUnit. Explicit `normalizeTo` uses `visibleWidth`/`visibleHeight` from PageGeometry, fits the visible crop without distortion, clips original content to that crop, and transforms annotations, AP matrices, borders, default font sizes and destination coordinates coherently. Output normalized pages use an origin-zero target box, rotation zero and UserUnit one. Requested normalization supports safe Link/Widget annotations; unknown geometry, NoRotate/NoZoom flags and incompatible fixed-font scales on shared multi-page fields refuse while leaving default merge available.

## Verification

- Focused Node verification: **18/18 passed**, with actual serialized/readback PDF objects and no mocked PDF import implementation.
- Form tests prove actual widget `/P` and page `/Annots` identity, surviving values/AP, hierarchical names, radio/dropdown state, independent field and font resource collisions, deterministic unused prefixes, inherited DA token rewriting, calculation order and destination catalog preservation.
- Graph tests prove nested styled outlines, name-tree import, actual inserted targets, internal links, named refusals for cycles/orphans/active content, and both depth and node limits.
- Merge tests cover insertion at start/middle/end, original inputs unchanged, serializable review/source SHA-256, genuine AES Unicode passwords on both inputs, independent signature acknowledgements, geometry defaults, explicit rotation/crop/UserUnit normalization and safe refusal.
- The stronger real Arial pair uses `govdocs1_003_003063.pdf` page 0 `/TT2` and `govdocs1_001_001038.pdf` page 2 `/TT0`. Controlled copies give both fonts the identical `/ABCDEF+Arial` name while preserving real font programs; output retains both measured program hashes and distinct dictionary references. No font-name deduplication or program reconstruction is added.
- `npm --prefix client run build` passed; the existing large-chunk warning remains.
- Full client suite during parallel work: **89 passed / 1 failed**, solely the concurrent plan 04 `images.test.mjs` module-load RED state. The orchestrator subsequently confirmed plan 04 implementation GREEN and owns the final stable combined suite; this earlier run is not relabeled all-green.
- Independent actual-output probe: `qpdf --check` passed default and normalized PDFs; `pdfcpu validate --mode relaxed --conf disable` passed normalized output. A Poppler crop/rotation/UserUnit form-page comparison against the expected 600×600 fit had **zero differing pixels**, including form AP.
- `pdfcpu --mode strict` reports missing `FirstChar` for the cantoo-generated Standard-14 Helvetica resource in **both source and output**. This inherited fixture limitation was not silently repaired by changing font dictionaries. The complete three-renderer/exact-name negative-control G5 gate remains owned by plan 06.

## Decisions Made

All copies share one `PDFObjectCopier`; there is no mixing with `copyPages()`' private copier in production. Per-field resource aliases prevent different field-local fonts from conflicting even when field-name collision counts are zero. Existing AP resources remain local; missing AP resources are materialized from the source effective DR. DA is parsed as a restricted PDF token program, including escaped PDF names, rather than rewritten with substring replacement.

Source and destination signature acknowledgements are independent. Saves always use `updateFieldAppearances:false`. Original byte arrays remain immutable on success and refusal, and no intermediate history/output is published.

## Deviations from Plan

None in implementation scope. The committed execution refinement allowed task 1 to begin against plan 01's fixed exports; the full plan 01 dependency was confirmed before completing this plan. Additional cycle, orphan, node-budget and normalization-font assertions refine the planned graph-safety and interactive-form requirements.

The requested `.Codex` mandatory-initial-read/project-skills-discovery files were absent at both the specified and `.cursor` fallback paths. Available `.cursor` execution-thinking/summary references, committed plan/context/research/UI contracts, installed dependency source and project instructions were used. No package was installed.

## Deferred Issues and Readiness

Worker/UI dispatch, mixed-history integration, observed zero API traffic and G5 renderer/browser gates belong to plans 05/06. The historical concurrent image RED and inherited strict Helvetica fixture warning are reported above. No deployment, container setup, new dependency or shared-helper change was made.

Stub scan found only intentional temporary accumulators, null destination coordinates and the recognized cantoo radio `dummy__noop` marker; no unwired feature stub prevents this library plan's goal. Threat-surface review found no additional endpoint, auth, filesystem or schema boundary outside the plan's imported-PDF graph threat model.

Root STATE/ROADMAP/REQUIREMENTS updates are explicitly owned by the orchestrator during parallel execution; this executor commits only its four source/test files and this summary.

## TDD Gate Compliance

Both tasks have RED test commits preceding their GREEN implementation commits. The initial RED runs exercised real constructed/loaded PDFs and failed because the corresponding production module was absent; later adversarial and normalization regressions failed against the existing implementation before their fixes.

## Self-Check: PASSED

All four source/test files and this summary exist. All four recorded task commits resolve to real commits. No tracked file deletion is included in the task implementation commit.
