---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: PDF Tool
status: executing
stopped_at: Phase 6 plans 01 and 02 delivered; merge/image implementation and core/server review active, no deployment
last_updated: "2026-10-25"
last_activity: Delivered tested local PDF/history/worker and HEIC/license boundaries; continuing merge and image work
progress:
  total_phases: 8
  completed_phases: 3
---

# Project State

**Core value:** Replace existing PDF text while preserving the surrounding document.
**Current focus:** Phase 06 — page operations and merge, local execution.

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

- On 2026-10-24 the user instructed: "ok go to next phase". Phase 6 proceeds
  independently over the delivered workstation. No deployment or container-tool
  installation is included; G3 release checks and G4 literal-specimen debt stay open.
- Refreshed research, pattern map and approved UI contract are recorded. Six plans
  cover all nine PAGE requirements in four waves; independent review has no blockers.
- Plans 06-01 and 06-02 are delivered with committed summaries. Local PDF load,
  password/signature/geometry/resource handling, page transforms, exact snapshot
  history and terminable worker transport pass 22 focused tests and build.
- The HEIC boundary passes 18 native/lifecycle tests (including real macOS sips),
  25 HTTP/privacy tests, 15 license tests, both dependency gates and strict typing.
  Production conversion fails closed until separate Linux confinement is verified;
  this local proof does not close G3 or claim Linux execution.
- Merge and local image primitives are active; independent review of completed
  core/server slices runs alongside them. Workstation integration and actual G5
  network/renderer/browser proof remain pending. No PAGE requirement is marked
  complete from pure helper tests alone.
- Baseline: 527 Python tests passed (36 deselected), 41 client tests passed.
  Actual browser RED proof caught two API requests on opening; G5 must reach zero
  through local page operations/download, not merely inspect a boolean.

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
  Phase 6 page operations/merge is now in local planning under the user's instruction.

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
operations are the current local work; later exports remain future work.

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
