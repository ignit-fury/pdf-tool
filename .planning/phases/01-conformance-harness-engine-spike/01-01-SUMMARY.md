---
phase: 01-conformance-harness-engine-spike
plan: 01
subsystem: infra
tags: [uv, pikepdf, playa-pdf, fonttools, uharfbuzz, pypdfium2, pillow, pytest, license-gate, agpl, github-actions]

# Dependency graph
requires: []
provides:
  - "One-page data-flow retention map (RETENTION-MAP.md), written and committed before any infrastructure file"
  - "Scaffolded Python 3.13 uv project (pyproject.toml, uv.lock) pinned to research/STACK.md versions"
  - "tools/license_gate.py — AGPL/Affero scanner over the RESOLVED installed dependency closure"
  - "Proven (not just asserted) AGPL gate: red proof (pdf2docx -> transitive PyMuPDF) and green proof (fully reverted)"
  - "CI workflow (.github/workflows/license-gate.yml) enforcing the gate on every push/PR"
affects: [02-text-model, 03-rewrite-engine-font-pipeline]

# Tech tracking
tech-stack:
  added: [uv, pikepdf==10.11.0, playa-pdf==1.1.0, fonttools==4.63.0, uharfbuzz==0.56.0, pypdfium2==5.12.1, pillow==12.3.0, pytest]
  patterns:
    - "License gate scans importlib.metadata.distributions() — the resolved/installed closure — not pyproject.toml top-level metadata"
    - "Retention map precedes infrastructure selection; queue payloads are handle-only, scratch is tmpfs, cache is content-addressed and evictable"

key-files:
  created:
    - .planning/phases/01-conformance-harness-engine-spike/RETENTION-MAP.md
    - pyproject.toml
    - uv.lock
    - tools/license_gate.py
    - tests/test_license_gate.py
    - tests/fixtures/agpl_gate_proof_red.txt
    - tests/fixtures/agpl_gate_proof_green.txt
    - .github/workflows/license-gate.yml
    - .gitignore
  modified: []

key-decisions:
  - "Job queues carry an opaque short-TTL handle, never document bytes (binding for any future ARQ integration)"
  - "Scratch is tmpfs, not a persistent object store; the server cache is content-addressed (sha256) and evictable at any moment"
  - "AGPL gate matches on both the distribution License field and Classifier entries, case-insensitive substring on 'agpl'/'affero'"

patterns-established:
  - "License gate as a stdlib-only (importlib.metadata) script, no new dependency, run identically in local dev and CI via `uv run python tools/license_gate.py`"

requirements-completed: [ENG-06, ENG-07]

# Metrics
duration: 9min
completed: 2026-08-12
---

# Phase 1 Plan 1: Retention Map + Engine Scaffold + Proven AGPL Gate Summary

**Wrote the data-flow retention map before any infra existed, then scaffolded the pinned Python 3.13 uv project and proved the AGPL lockfile gate fires by deliberately adding pdf2docx (which pulls transitive PyMuPDF) and watching it go red, then fully reverting.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-08-12T11:41:31+05:30
- **Completed:** 2026-08-12T11:50:01+05:30
- **Tasks:** 2 completed
- **Files modified:** 15 (1 retention map + 14 scaffold/gate/CI files)

## Accomplishments
- One-page retention map enumerating all 15 hops (browser, CDN x2, LB, app, queue, worker, subprocess, scratch, object store, response, cache, logs, error reporter) with retains/duration/deletion/verification for each, committed before `pyproject.toml` existed (verified via `git log` ordering)
- Python 3.13 project scaffolded with `uv`, dependencies pinned exactly to `research/STACK.md`: `pikepdf==10.11.0`, `playa-pdf==1.1.0`, `fonttools==4.63.0`, `uharfbuzz==0.56.0`, `pypdfium2==5.12.1`, `pillow==12.3.0`, plus `pytest` as dev dependency
- `tools/license_gate.py` scans `importlib.metadata.distributions()` (the actually-resolved, actually-installed closure) for AGPL/Affero, case-insensitively, in both the `License` field and `Classifier` entries
- Gate proven to fire: added `pdf2docx`, ran the gate, captured `tests/fixtures/agpl_gate_proof_red.txt` showing `pymupdf==1.28.2: Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License` and exit code 1; then `uv remove pdf2docx && uv sync`, reran, captured `tests/fixtures/agpl_gate_proof_green.txt` at exit code 0
- Confirmed `pyproject.toml`/`uv.lock` contain zero trace of `pdf2docx`/`pymupdf` after revert (`grep -i` exit 1, no match)
- `.github/workflows/license-gate.yml` runs `uv sync --locked && uv run python tools/license_gate.py` on every push and PR

## Task Commits

Each task was committed atomically:

1. **Task 1: Write the retention map before any infrastructure is selected** - `b56ed05` (docs)
2. **Task 2: Scaffold the Python project and prove the AGPL lockfile gate fires** - `0b10f0e` (feat)

_Note: Task 2 has `tdd="true"` in the plan but is implemented as a single atomic commit (script + red/green proof capture + tests + CI) since the "RED" state here is a live infrastructure event (installing a real trap package and observing the gate fire), not a pre-written failing unit test — the red/green proof files themselves ARE the captured RED/GREEN evidence, asserted by the tests in the same commit._

## Files Created/Modified
- `.planning/phases/01-conformance-harness-engine-spike/RETENTION-MAP.md` - Hop-by-hop data-flow retention table and the two binding decisions (handle-only queues, tmpfs scratch)
- `pyproject.toml` / `uv.lock` - Python 3.13 project, pinned runtime deps, pytest dev dep
- `tools/license_gate.py` - AGPL/Affero scanner over installed distributions; CLI exit 0/1
- `tests/test_license_gate.py` - Red-proof assertion, green-proof assertion, live regression guard
- `tests/fixtures/agpl_gate_proof_red.txt` - Captured proof the gate fired on pdf2docx's transitive PyMuPDF
- `tests/fixtures/agpl_gate_proof_green.txt` - Captured proof of clean exit after full revert
- `.github/workflows/license-gate.yml` - CI job wiring `uv sync --locked` + the gate to every push/PR
- `.gitignore` - Standard Python ignores (`.venv/`, `__pycache__/`, `*.pyc`, `*.egg-info/`)
- `README.md`, `.python-version` - `uv init` scaffold artifacts (kept; harmless project metadata)

## Decisions Made
- Job queues carry an opaque short-TTL handle, never document bytes — binding on any future ARQ integration, per `ARCHITECTURE.md` §3 Option C and Pitfall 12.
- Scratch space is tmpfs, not a persistent object store; the server cache is content-addressed (`sha256(bytes)`) and evictable at any moment — binding on the eventual FastAPI service.
- `check_installed_distributions()` returns `(package_name, version)` 2-tuples per the plan's documented behavior contract; the matched license-field text (needed for the human-readable CLI printout) is carried by an internal `_offending_distributions()` helper rather than widening the public tuple shape.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added `.gitignore`**
- **Found during:** Task 2 (project scaffold)
- **Issue:** `uv init` does not create a root `.gitignore`. `.venv/` and `.pytest_cache/` happened to already be excluded via their own internal self-ignoring `.gitignore` files (a `uv`/`pytest` convention), but `__pycache__/`, `*.pyc`, and `*.egg-info/` are not self-ignoring and would risk being committed by a future `git add -A` elsewhere in the repo.
- **Fix:** Added a minimal root `.gitignore` covering standard Python build/cache artifacts.
- **Files modified:** `.gitignore`
- **Verification:** `git status --short` clean after all task files staged; no cache directories tracked.
- **Committed in:** `0b10f0e` (Task 2 commit)

**2. [Rule 3 - Blocking] Removed `uv init`'s default `main.py`**
- **Found during:** Task 2 (project scaffold)
- **Issue:** `uv init --python 3.13` scaffolds a placeholder `main.py` with a "Hello from pdf-tool-engine!" script entry point. This project is a library/engine consumed by later phases, not a runnable script, and the plan's `files_modified` list does not include it.
- **Fix:** Deleted `main.py` before staging.
- **Files modified:** (removed) `main.py`
- **Verification:** Not present in the Task 2 commit's file list.
- **Committed in:** `0b10f0e` (Task 2 commit, by omission)

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 blocking/scope cleanup)
**Impact on plan:** Both trivial and necessary for a clean scaffold. No scope creep — no new dependencies, no architectural changes.

## Issues Encountered
- The plan's literal verify command (`python tools/license_gate.py`) resolves to the shell's global Python 3.14 interpreter, not the project's `uv`-managed venv, when run outside an activated environment — that global interpreter has unrelated packages installed (e.g. `scipy`) with large bundled license-notice text blocks that make the gate's output noisy (though it still exits 0, since none of those notices contain "AGPL"/"Affero"). Verified instead with `uv run python tools/license_gate.py`, which is what the committed CI workflow actually invokes and is the correct way to exercise "the current environment" (the project's resolved venv, not the ambient shell). No code change needed — this is an invocation detail, not a gate defect.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `pyproject.toml`/`uv.lock` exist and are AGPL-clean; every later plan in this phase (corpus, differential rasterizer, structural validation, playa-pdf spike, TJ-refit prototype) can add its own dependencies against this scaffold via `uv add`.
- The AGPL gate is live in CI and known-working (fired once on a real trap, reverted, still passes) — any future dependency addition that pulls AGPL transitively will be caught automatically.
- The retention map's two binding decisions (handle-only queues, tmpfs scratch + evictable content-addressed cache) are recorded and must be honored by Phase 2's content-stream interpreter work and any future job-queue/storage decisions.
- No blockers.

---
*Phase: 01-conformance-harness-engine-spike*
*Completed: 2026-08-12*

## Self-Check: PASSED

All 8 files verified present on disk; both task commits (`b56ed05`, `0b10f0e`) verified present in `git log --oneline --all`.
