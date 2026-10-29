---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: PDF Tool
status: verification_pending
stopped_at: Local outline and atomic history navigation delivered; source reflow and release gates remain open
last_updated: "2026-10-29"
last_activity: Verified local bookmarks, atomic history jumps, stale/failure guards and no-upload navigation
progress:
  total_phases: 8
  completed_phases: 5
---

# Project State

**Core value:** Replace existing PDF text while preserving the surrounding document.
**Current focus:** Outline and atomic history navigation delivered locally after the viewer/text-container stages. Original-source reflow and earlier external release verification remain open. No deployment.

Phases 1–3 are complete. The Phase 3 engine and its fonts, CLI and regression gates are
now present in this checkout; the original source worktree and local edits are preserved.
Phase 4 implementation is delivered locally. Safari/Firefox open/edit/download and Safari
password/undo/cache-recovery journeys were exercised. Public-release Gate G3 remains
open until Linux/container and live CDN checks are actually run.

On 2026-10-22 the user explicitly instructed: "dont deploy it yet just go to nxt
phase". Phase 5 proceeds locally using the delivered Phase 4 interfaces. Deployment
and the open Linux/container/CDN release gates are retained; no public-release
completion is implied. The interrupted container-tool setup was not continued.

Execution record: `.planning/PHASE-4-EXECUTION.md`.
Evidence and remaining checks: `phases/04-web-tier-walking-skeleton-hardening/04-VERIFICATION.md`.

## Current work

### Document navigation and history — 2026-10-29

- Optional nested Outline and retained History panels reuse the current committed
  PDF.js proxy and existing exact-byte timeline. Internal named/explicit bookmarks
  preserve zoom and resolve correctly after page changes. External actions stay disabled.
- History jumps publish one prepared snapshot, preserve mixed operations/recipes,
  expose future Redo and clear it only after successful new edits. Failed/stale
  restores preserve bytes and stacks. Heading/current-state focus is accessible.
- Opening local navigation pauses further automatic analysis; explicit Edit/Find
  resumes it. Cache-miss browser proof shows zero requests/uploads from Outline.
- 187 client tests, production build, both runtime license closures, 19 license
  controls and Unicode check pass. Three new actual browser journeys plus inline,
  image, Find/tour and native-text-box regressions pass. New history downloads:
  five byte-identity checks, 12 structural validations and 13 exact unrelated-pixel
  comparisons; prior viewer/text-box download regressions also pass.
- One fresh review's two Important findings reproduced/fixed: delayed bookmark
  overriding newer navigation and re-upload triggered by analyzed navigation.
  No findings deferred. Backend unchanged; full Python suite not rerun this stage.
- Plan/evidence: `docs/superpowers/plans/2026-10-29-document-navigation.md` and
  `docs/verification/document-navigation-2026-10-29.md`. No deployment/dependency.
- Exact substring glyph highlights, arbitrary original-paragraph reflow/growth,
  neighbor movement and foreign-image editing remain outside this delivered slice.

### Native inserted text containers — 2026-10-29

- Next requested stage delivered: page insertion/edit/removal, native searchable
  multiline/wrap, font growth, alignment and character/line/paragraph spacing.
- Exact separate PDF preview publishes the same bytes on Apply as one mixed Undo
  entry. Cancel/stale/overflow preserve working bytes/history. Rendered-content
  and annotation collision checks, explicit expansion and bounded ownership proof.
- Current-byte API reuses isolated workers/cache/password/signature/resource limits.
  Source runs route verified boxes to complete layout; unsafe individual rewrites refuse.
- Broad regression: 867 passes; final native/API/recipe 114 passes includes the later
  additional PDF-version regression. Client 180 passes; 12 existing export/removal
  gates; strict 39-file typing, build and license/Unicode checks pass. Actual browser
  mixed history, geometry, overflow/cancel and responsive controls verified; five
  downloads pass 10 structural validations and 49 unrelated-pixel comparisons.
- Original arbitrary paragraph reflow/neighbor movement, foreign image editing,
  exact substring glyph highlights remained future work at this baseline. The next
  stage above delivers outline/history panels.
  Rotated existing boxes require rotating back for layout editing. No deployment.
- Plan/evidence: `docs/superpowers/plans/2026-10-29-native-text-boxes.md` and
  `docs/verification/native-text-boxes-2026-10-29.md`. Prior release gates retained.

### Document viewer upgrade — 2026-10-29

- User requested a plan followed by implementation. Design/plan are under
  `docs/superpowers/`; all six tasks are delivered within the conservative scope.
- Continuous, bounded PDF.js rendering and inline text input/contextual formatting
  reuse authoritative run IDs and the atomic native writer. Safe size shrink/equal,
  character spacing, font/color/bold/italic preserve following text state.
- Native managed-image insert/move/resize/rotate/replace/delete, mixed exact Undo/Redo,
  explicit One/All replacement and a post-commit results tour are delivered.
- Final verification: 787 selected Python passes plus one added mandatory combined-
  runtime regression; 170 client passes; 12 G6/G7a/removal gate passes; strict typing,
  build, licenses/Unicode pass. Browser/native proof covers the 12-page synthetic
  document, actual downloads, pointer controls, responsive layout, Unicode password
  and cache-recovery transport. Independent review findings are fixed with regressions.
- At this earlier viewer baseline, new independent text containers and their layout
  controls remained unsupported; the next stage above delivers them. Flexible source
  reflow/multiline/height growth and unowned original image editing remain unsupported. No dependency, migration, deployment or container setup.
- Evidence/commands: `docs/verification/document-viewer-2026-10-29.md`. All earlier
  Linux/container/CDN, contract-specimen, hosted G7a and Word/Acrobat gates remain open.

### Earlier phase delivery

- Phase 8 started under the user's continue instruction. G7b's scope document is
  committed before implementation (`60dd243`). Research/UI contract and the actual
  13-file unchanged-source validator baseline are recorded (`794710e`).
- veraPDF 1.30.3 is authenticated and installed only in `/private/tmp` for dev/CI;
  existing Java works. Initial 13-file baseline and subsequent frozen 31-file
  baseline are retained separately from converted-output results.
- Six sequential plans passed independent plan review after one revision.
  Evidence: `08-PLAN-CHECK.md`.
  The conservative PDF/A converter and fixed positive corpus gate precede DOCX;
  existing release gates and no-deployment instruction remain in force.
- Plan 08-01 is complete: 31 frozen inputs, twelve required successes, actual raw
  baseline, fail-closed veraPDF runner and authenticated CLI installer/CI wiring.
  37 runner controls and five fixture/baseline checks pass. All baseline results
  remain honest: one compliant, 29 noncompliant and one intentional malformed
  parser failure. This is not a converted-output or hosted-CI pass.
- Plans 08-02/03 are complete locally: all twelve frozen positives plus a public
  vector PDF and three supplementary cases validate at PDF/A-2b. Sixteen outputs,
  19 pages, 57 exact native comparisons and 32 structural checks pass. Two cross-
  engine differences match source baselines. The final converter/gate run passes
  47 tests. Primitive/nesting/font-length and absent-Contents issues were fixed.
- The isolated PDF/A API/UI preserves current bytes/history, maps finite refusals,
  and passes 33 API tests, nine controller tests, build and strict typing (36 files).
  Actual browser downloads validate, including an edited two-page source; Undo,
  held-response cancellation, safe refusal and 320/760px layout/focus are observed.
  Evidence: `08-G7A-RESULTS.md`, `08-03-SUMMARY.md`. Hosted G7a CI remains pending.
- Phase 7 is complete locally under the user's start/continue instructions. All four
  plans and EXPO-01 through EXPO-05 pass goal verification: 12/12 merged must-haves.
  Evidence: `phases/07-exports/07-VERIFICATION.md` and `07-G6-RESULTS.md`.
- PNG/JPEG images at chosen DPI and PDF splitting stay in the browser. Compression,
  flatten and text/Markdown/HTML exports explicitly use isolated server workers with
  current materialized bytes; exports preserve the working document and Undo history.
  Text formats consume one RunIndex and reusable reading-order/block model.
- Actual browser proof covers request/body/download identity, styled/rotated outputs,
  exact compression Before/After, PNG/JPEG/ZIP contents, signed/encrypted input,
  cancellation/refusal and 320/760 px focus/layout. Nine downloads pass 18 additional
  native validations; source review resolves one blocker and six warnings.
- Final checks: 634 Python tests (36 deselected), 140 client tests, seven G4 technical
  proxy tests, 35 typed files, 19 license-gate tests, both closures, Unicode and build
  pass. G6 covers 7 PDFs / 13 pages with 39 same-engine comparisons and 14 validations.
  The 12 cross-engine threshold failures and 29 size differences match source/reference
  baselines and remain disclosed, not relabeled passing cross-engine comparisons.
- G3 Linux/container/live-CDN, G4 literal contract-specimen coverage and production
  HEIC confinement remain open. Production HEIC stays disabled until confined.
  No deployment, dependency installation or container-tool setup occurred.
- Plan 08-04 is complete: opt-in bounded image discovery and shared degradation
  facts feed an immutable, deterministic direct OOXML projection. 38 focused
  DOCX/block/text/single-path tests and strict typing (38 files) pass. macOS
  textutil reads the package; Word visual verification remains unperformed.
- Plans 08-05/06 are complete locally: document-specific DOCX review and separate
  conversion bind current source/full-snapshot/policy. The worker rechecks before
  serializing; no receipt secret/cache or second extraction path exists. All 45
  API tests and actual browser Unicode-password/signature journeys pass.
- Actual DOCX downloads preserve source/current PDF bytes and Undo history;
  four-page local insertion changes the review, and Undo invalidates it. Held
  review/conversion responses publish no links after cancel. Focus/wrapping pass
  at 320/760px; unavailable DOCX leaves PNG enabled. Five downloaded packages pass
  CRC/XML checks, including headings/emphasis/images/table and column fallback.
- Literal scratch deletion of the optional writer preserves startup and all other
  exports: 134 Python export/G6/G7a tests, 22 client export tests and build pass;
  a deliberate unconditional-import negative control fails as intended.
- Final selected regression: 754 Python passes plus six sandbox-denied OS checks;
  both affected complete files pass all 26 tests outside the sandbox (760 unique
  selected tests covered; 39 deselected). All 147 client tests, 38-file strict
  typing, build, license closures/controls and Unicode data check pass. The
  integrated G7a/removal command passes seven tests. Raw failures remain recorded.
- Phase 8 progress: 6/6 plans delivered and verified locally. EXPO-07/08 complete
  locally; EXPO-06 retains the explicit hosted-CI acceptance item. Word/Acrobat
  visual observations remain unperformed; textutil is not a substitute. No next
  numbered feature phase is defined. See `08-VERIFICATION.md`, `08-G7-RESULTS.md`
  and `08-REVIEW.md`; no deployment, install or container setup occurred.

### Delivered Phase 6 baseline

All six Phase 6 plans/PAGE-01..09 are verified locally. Browser page operations,
PDF/image merge and mixed Undo need no API request; explicit analysis/image-only
HEIC conversion cross their disclosed boundaries. G5 native, browser and exact-byte
history evidence is retained in `phases/06-page-ops-and-merge/06-G5-RESULTS.md`.

### Delivered Phase 5 baseline

- Phase 5 implementation is delivered: canonical Unicode projection, current-recipe
  matching, individual exclusions, resumable indexing, exact preview, source-box
  navigation, one atomic full-recipe apply and one whole-batch undo.
- All four plans have implementation summaries. All six FIND requirements are
  complete locally; formal phase G4 retains one literal-specimen verification item.
- Local Firefox observations: 40/40 pages indexed; `the` gives 1,029 default
  matches, 851 whole-word matches and 723 whole-word case-sensitive matches.
  Excluding one of two instances in a run preserves the other; the actual page/run
  highlight follows navigation at 115% and 200% zoom. Native browser find remains available.
- Current Chromium browser: one action changed 910 selected occurrences on 28 pages;
  one Cmd+Z restored original text/download and all 1,029 matches. Earlier bold/color
  survived batch undo. Font recovery, signature acknowledgement, Unicode-password
  cache-loss recovery, failed-page retry and stale/closed-preview guards were exercised.
- Final engine `630ca28` previews all 675 accepted operations in 18.302/18.319 CPU
  seconds and applies them in 18.467 CPU / 18.528 wall. CPU20/default wall30 and all
  recipe/security/fidelity limits remain unchanged. Three review blockers are resolved.
- Complete technical-proxy G4 passed all 120 renderer pairs (28 changed pages,
  12 unchanged); final full regression passed G4 again after the last space-width fix.
  Client: 41 tests; build, strict typing (30 files) and Unicode data check passed.
- Broad local regression: 556 passed, one obsolete refusal expectation failed,
  five Linux/CDN checks deselected. Test-only correction independently proves the
  now-safe edit and real late-layout atomic refusal; all three corrected tests pass.
  The raw run is retained, not relabeled zero-failure. No unresolved failure remains.
- Literal legal-contract specimen coverage remains unproven. The all-page source is
  explicitly a public technical-document proxy; G3 release checks remain open.
  Pending item: `phases/05-find-and-replace-across-all-pages/05-HUMAN-UAT.md`.
  Phase 6 page operations/merge is now delivered and verified locally.

### Earlier Phase 4 baseline

- Full regression run passed: 423 passed, 5 skipped; two subsequently added tests passed focused checks.
- Frontend build, ten client helper tests, strict engine/server typing and local browser journeys passed.
- Final review fixed Unicode password transport and added safe refusals for stateful text
  operators and ambiguous/multi-character shaping. The final non-corpus rerun passed
  (420 passed, 5 skipped, 19 deselected), as did all three renderer/font gates.
- Linux resource limits, tmpfs and seccomp tests are configured in CI but not yet run here.
- No deployment URL exists for the live CDN gate; no deployment was published.

## Preserved constraints

Server-issued run addresses; one atomic recipe against immutable original bytes; no overlay
editing; no runtime AGPL; no persistent server document/session history; browser-held
originals recover evicted memory cache. Phase 5 full-document find/replace is
delivered locally; its literal contract-specimen gate remains open. Phase 6 page
operations, scoped exports, supported PDF/A and best-effort DOCX are delivered
locally. Hosted G7a CI remains open alongside the earlier release gates.

## Decisions made during execution

- Use raw bounded PDF upload to avoid multipart disk spooling.
- Use existing recipe engine exclusively; remove obsolete server rewrite/export forks.
- Use OCRmyPDF's official guide as the named external OCR route; no file is sent there.
- Allow same-origin decoder WASM via CSP's narrower wasm-unsafe-eval, never JS unsafe-eval.
- Preserve positive word-space width; use bounded Tz or named refusal for larger compression.
- Reconcile corpus exclusions after enabling AES support and replace obsolete zero-hash
  diagnostic expectations with manifest digests.

### Quick Tasks Completed

| # | Description | Date | Result | Directory |
|---|---|---|---|---|
| 261021-ply | Detect source font and allow explicit replacement when automatic matching fails | 2026-10-22 | 160 regression/gate tests, 17 font-choice tests, 11 client tests passed; build/types passed | [Font selection](./quick/261021-ply-detect-font-names-and-allow-explicit-rep/) |

### Debug fixes

- 2026-10-22: [Short replacement fit](./debug/short-replacement-fit.md) resolved. Shorter
  replacement text can leave unused space after it while preserving following positions;
  fit feedback no longer repeats technical prose. 445 non-corpus tests, renderer gates,
  client build/tests, typing and live HTTP verification passed.
- 2026-10-22: [Corpus compatibility](./debug/corpus-compatibility.md) audit complete.
  All 217 public PDFs and 8,254 pages read-tested; sampled edits independently
  verified in 164 PDFs. Font fallback, physical stream anchors, empty operators,
  dense-page performance, syntax-error routing and full rewrite preview corrected.
  Final 346 outputs: 333 independently verified text results, no detected corruption
  or wrong text, no preview/apply disagreements, immutable sources. Remaining sample
  refusals/unverifiable cases are explicit in the [report](./audits/corpus-compatibility-2026-10-22.md).
  473 quick regression tests, latest 94 focused/gate tests, 12 client tests,
  production build and strict typing passed. Release gates above remain open.
