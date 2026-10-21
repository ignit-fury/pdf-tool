---
phase: 04-web-tier-walking-skeleton-hardening
plan: isolation-slice
subsystem: isolated-worker
completed: 2026-10-21
requires: [phase-3-engine, phase-4-password-and-geometry]
provides: [bounded-worker-transport, resource-limits, safe-errors, generated-hostile-fixtures]
affects: [http-api, privacy-canary, browser-editor]
key-files:
  - server/isolation.py
  - server/worker.py
  - server/errors.py
  - server/secrets.py
  - tools/build_security_fixtures.py
  - tests/test_isolation.py
  - tests/test_worker.py
  - tests/test_hostile_input.py
---

# Phase 4 Isolation Slice Summary

**PDF parsing and editing run in disposable, bounded subprocesses; parent-owned scratch cleanup survives child crashes and wall-clock termination.**

## Changes

- Parent `run_worker` imports no engine, sends one JSON-over-stdio request, accepts no user filenames, caps PDF input at 50MiB, recipes at 1MiB, and output at 80MiB.
- Nonblocking concurrent pipe exchange enforces the wall deadline and output cap. Parent kills the entire worker process group, discards stderr, and removes its private scratch directory in both success and failure paths. Libraries' TMPDIR/TEMP/TMP stay inside that directory.
- Linux child applies 1GiB RLIMIT_AS and 20-second RLIMIT_CPU; all children disable core dumps. Linux production fails closed unless the configured scratch mount is tmpfs. Default Linux scratch is /dev/shm.
- Fixed-code reporting is opt-in and receives only `{code, action}`, never exceptions, tracebacks, frame locals, source bytes, filenames, or passwords. `SecretStr` reuses the existing Pydantic secret type.
- Inspect returns metadata only. Page requests traverse and bound only that page's reachable streams/resources, then call the lazy engine index for exactly the requested page. Edit uses the existing recipe parser/planner/applicator and returns the engine's report unchanged plus optional output bytes encoded as base64. Original source is immutable.
- Signature detection checks SigFlags bit 1 and recursively inherited /FT /Sig fields carrying /V; append-only flag 2 is not mistaken for a signature. Dry runs do not require signature acknowledgement; commits do.
- Generated fixtures cover user passwords, structural signatures, canary text, cyclic pages, self-referencing Forms, and a compression bomb generated with a fixed 64KiB input allocation. Flate expansion uses a bounded 16MiB decoder call; cycle detection produces a named refusal.

## Verification

- Tests were written first: initial run failed collection because the four worker modules did not exist.
- Latest combined run: `pytest tests/test_isolation.py tests/test_worker.py tests/test_hostile_input.py tests/test_privacy_canary.py tests/test_ephemerality.py -q`: **29 passed, 2 skipped**, 10.14 seconds. One existing Starlette/httpx deprecation warning.
- Strict mypy on the four new server modules plus fixture builder: **passed**.
- Real 126-page IRS instructions document, requested page 0: **0.336 seconds**, 50 runs, no error. This is one local observation, not a performance guarantee.
- Regression tests prove that a later-page compression bomb does not block metadata or page 0, and that requesting page 1 indexes only page 1 once.
- Hostile documents fail with fixed named responses and a subsequent ordinary PDF request succeeds. Timeout, crash, malformed stdout, and output-flood tests preserve host operation and clean scratch.

## Deviations and Limits

- Controller hardening after this slice added a minimal child environment, fail-closed Linux
  seccomp (including x32 syscall bypass rejection), and response backpressure admission.
  The final combined backend/cache check passed 49 tests with four Linux-only skips;
  strict typing passed across 28 engine/server files. Linux checks remain unexecuted locally.

- The outline's full-document stream preflight was narrowed to metadata-only inspection and page-local preflight to retain first-page-first behavior. Full preflight remains on edits.
- A generated test fixture initially omitted font widths; it was corrected to metric-compatible Liberation Sans widths. A same-length replacement tests successful transport without violating the fit ladder.
- macOS cannot enforce RLIMIT_AS or attest Linux tmpfs. Two Linux-only checks (actual memory-allocation refusal and production non-tmpfs rejection) are explicitly skipped locally and must execute in Linux CI.
- The signature fixture is structurally signed, not cryptographically attested; the service does not verify signature trust.
- The Flate cap directly covers single-Flate streams. Other compression filters remain contained by the worker memory/CPU/wall limits.
- This is process/resource isolation, not a separate OS privilege/container boundary. No claim of protection against arbitrary native-code execution outside those controls is made.
- No commits were made in this delegated slice; the controller owns task commits and overall planning state.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| file-access | server/worker.py | Child writes source/output and library temporary files only into parent-owned private scratch; cleanup remains in the parent. |
| process-boundary | server/isolation.py | Bounded JSON protocol, process-group termination, no stderr relay, fixed-code reporter. |

## Self-Check: PASSED

All eight implementation/test files above exist. Focused functional checks and strict typing passed. Linux-only controls remain explicitly unverified on this macOS host.
