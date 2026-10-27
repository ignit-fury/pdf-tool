---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: PDF Tool
status: executing
stopped_at: Phase 7 plans checked; wave 1 and independent native helper execution starting
last_updated: "2026-10-27"
last_activity: Started Phase 7 under user instruction; four scoped export plans prepared
progress:
  total_phases: 8
  completed_phases: 4
---

# Project State

**Core value:** Replace existing PDF text while preserving the surrounding document.
**Current focus:** Phase 07 — Exports, local planning and implementation.

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

- On 2026-10-26 the user instructed: “Start the next phase 7.” Four export plans
  cover EXPO-01 through EXPO-05; prior local-only and release-gate boundaries persist.
  Plan check passed; local execution is starting.

- The user's local-only authorization remains in force. All six Phase 6 plans and
  PAGE-01 through PAGE-09 are verified locally. See `06-VERIFICATION.md` and
  `06-G5-RESULTS.md` under `phases/06-page-ops-and-merge/`.
- Opening/organizing PDFs, merge, PNG/JPEG/WebP placement, mixed Undo and downloads
  are browser-local, observed with zero API requests. Explicit Analyze text and
  image-only Convert HEIC cross their disclosed boundaries. Unicode-password and
  signed-document controls, original-byte restoration, styles and index Resume pass.
- Actual native gate: 24 PDFs / 53 pages, 159 exact same-engine mapped comparisons,
  independent RGB oracles, distinct same-named Arial programs, and all qpdf/pdfcpu
  checks pass. Existing 64 cross-engine UserUnit differences match unchanged source
  baselines; they are disclosed, not counted as passing cross-engine comparisons.
- Final checks: 560 Python tests (36 deselected), 125 client tests, seven G4 technical
  proxy tests, 31 typed files, 19 license-gate tests, both closures, Unicode artifact
  and build pass. Source review resolves nine blockers and one warning. Actual
  320/760 px checks also found/fixed hidden-input overflow (`f8fc3e4`).
- G3 Linux/container/live-CDN checks, G4 literal contract-specimen coverage and Linux
  HEIC confinement remain open. Production HEIC stays disabled until confined.
  No deployment, dependency installation or container-tool setup occurred.
- Phase 7 starts from the completed Phase 6 baseline; its execution records live
  under `phases/07-exports/`.

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
operations are delivered locally; exports are the next phase.

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
