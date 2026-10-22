---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: PDF Tool
status: verification
stopped_at: Phase 4 locally verified; Linux/container and live CDN release gates remain open
last_updated: "2026-10-21"
last_activity: Added detected font display and explicit replacement-family selection; Times New Roman aliases fixed
progress:
  total_phases: 8
  completed_phases: 3
---

# Project State

**Core value:** Replace existing PDF text while preserving the surrounding document.
**Current focus:** Phase 04 — browser editor and hardening verification.

Phases 1–3 are complete. The Phase 3 engine and its fonts, CLI and regression gates are
now present in this checkout; the original source worktree and local edits are preserved.
Phase 4 implementation is delivered locally. Safari/Firefox open/edit/download and Safari
password/undo/cache-recovery journeys were exercised. Public-release Gate G3 remains
open until Linux/container and live CDN checks are actually run.

Execution record: `.planning/PHASE-4-EXECUTION.md`.
Evidence and remaining checks: `phases/04-web-tier-walking-skeleton-hardening/04-VERIFICATION.md`.

## Current work

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
originals recover evicted memory cache. Phase 5 full-document find/replace, Phase 6 page
operations, and later exports remain outside this milestone.

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
