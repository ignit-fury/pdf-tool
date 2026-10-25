---
phase: 06-page-ops-and-merge
plan: "02"
subsystem: api
tags: [heic, native-process, admission, privacy, license-gate, wasm, tdd]
requires:
  - phase: 04-web-tier-walking-skeleton-hardening
    provides: Anonymous ingress, shared worker slots, fixed errors and privacy headers
provides:
  - Bounded image-only HEIC conversion endpoint independent of PDF jobs/cache
  - Native file-in/file-out development launcher with production fail-closed policy
  - Dependency-free resolved client runtime and bundled-WASM license gate in CI
affects: [06-04, 06-06, PAGE-07, PAGE-09, linux-release-verification]
tech-stack:
  added: []
  patterns: [shared shielded worker lifetime, bounded native image child, exact artifact license evidence]
key-files:
  created:
    - server/image_conversion.py
    - tests/test_image_conversion.py
    - tests/test_heic_contract.py
    - tools/client_license_gate.mjs
    - tools/client_license_gate.test.mjs
    - docs/heic-runtime.md
  modified: [server/app.py, server/errors.py, .github/workflows/license-gate.yml]
key-decisions:
  - Production HEIC always returns HEIC_UNAVAILABLE until separate Linux filesystem/egress confinement is implemented and verified; no environment assertion bypasses this policy.
  - Accept only a bounded single hvc1 primary-image subset; explicitly refuse ambiguous sequences, grids, auxiliary references and protected/external data.
  - Preserve PDF worker actions, seccomp and resource caps; image work shares only HTTP admission, two slots and tracked lifetime.
  - Pin missing QuickJS packaged-notice evidence to pdfjs-dist 6.2.108, the exact WASM path/SHA256 and versioned upstream MIT evidence.
requirements-completed: [PAGE-07, PAGE-09]
duration: 8h 34m elapsed, including quota suspension; approximately 20m active
completed: 2026-10-25
---

# Phase 6 Plan 2: Isolated HEIC and Client License Closure Summary

**Image-only HEIC conversion shares anonymous server capacity, while an installed-closure gate rejects transitive and bundled client copyleft or missing evidence.**

## Delivered behavior

`POST /images/heic-decode` accepts raw `image/heic` or `image/heif`, returns raw
`image/png`, rejects PDF/password/query arguments and creates no source-cache/job
entry. This is the disclosed image exception only; browser consent/placement and
the observed zero-document-request journey are integrated by subsequent plans.

Admission occurs before body reads. Image and PDF work use the existing two
worker slots, tracked tasks, completion callback, cancellation shielding and
lifespan cleanup. Cancellation retains a slot until the real work terminates;
response backpressure retains ingress admission. No independent image pool exists.

The dedicated native launcher imports no HEIF decoder in the server process and
does not enter or weaken the PDF seccomp worker. macOS uses installed
`/usr/bin/sips`. Linux development allowlists existing `/usr/bin/heif-dec` and
legacy `/usr/bin/heif-convert`; neither was installed/run on this workstation.
File existence does not qualify as conversion capability: complete validated
native output is required. The real macOS test encodes a generated tiny HEIC and
converts it through this boundary.

## Limits and fixed failures

| Boundary | Enforced limit/policy |
|---|---|
| Raw input | 20 MiB, bounded BMFF boxes/brands and single `hvc1` primary item |
| Decoded dimensions | 16,000,000 pixels; 16,384 maximum per dimension |
| PNG | 64 MiB; single-link regular file; signature/chunk CRC/IEND; no APNG; complete Pillow verify and pixel load in bounded child |
| Overall wall | 20 seconds covering preflight/probe/conversion/validation together |
| Child resources | CPU 20 seconds, open descriptors 64, file size 64 MiB, core dumps disabled; Linux address space 1 GiB |
| Probe output | 64 KiB, never returned or logged |
| Scratch | Random private directory under existing scratch-root policy, fixed internal names, no additional outputs/symlinks |
| Child launch | Fixed executable/argv, no shell, minimal environment, closed FDs, new process group; group kill/direct-child wait and parent cleanup |

Fixed image codes are `HEIC_UNAVAILABLE` (HTTP 503), `INVALID_HEIC` (400),
`IMAGE_LIMIT_EXCEEDED` (413), `IMAGE_CONVERSION_FAILED` (422), and
`IMAGE_CONVERSION_TIMEOUT` (422). Existing ingress/body codes and statuses remain.
Unexpected native exceptions are converted to a fixed code. Optional reporting
receives only `{code, action: 'heic-decode'}`. Responses preserve no-store, CSP,
nosniff, referrer/frame and configured CORS policy, including admission failures.

## Client runtime license closure

The Node-built-in-only gate walks every non-dev lock entry including nested and
installed optional dependencies. It checks installed name/version/license
agreement, dependency lock presence and registry/integrity evidence; rejects
unreviewed nonregistry sources, unknown SPDX and missing applicable metadata;
and scans bundled notices/source headers independently of wrapper metadata.
Missing foreign-platform optional packages are excluded only when platform/CPU
constraints establish they are absent from this installation.

Known SPDX `OR` permits a permissive option; `AND` requires all branches. Any
AGPL/Affero expression refuses, including an OR branch. Bundled GPL/LGPL refuses.
WASM needs a component notice or an exact reviewed evidence exception.

The installed PDF.js QuickJS artifact lacks a dedicated notice. The sole
`REVIEWED_WASM` entry is narrowly keyed to `pdfjs-dist@6.2.108`,
`wasm/quickjs-eval.wasm`, SHA-256
`7bcacc9f22cacf7e9b23866d2a6d1639693d40c7f144e41b7c69ed37ba9cbe8f`.
The [versioned upstream build README](https://raw.githubusercontent.com/mozilla/pdf.js/v6.2.108/external/quickjs/README.md)
identifies QuickJS/pdf.js.quickjs as MIT. The entry stores that source and reason;
changed bytes refuse in a permanent negative control. It never suppresses a
forbidden package or bundled notice.

CI preserves the Python gate, installs the locked client closure using Node 22
and `npm ci --ignore-scripts --no-audit --no-fund`, then runs the synthetic policy
tests and actual installed-closure audit. No npm dependency/framework was added.

## Task commits and TDD evidence

| Task | RED | GREEN |
|---|---|---|
| 1. Native boundary | `ff2fdb2` — absent boundary fails | `08b135a` — native codec, caps and lifecycle |
| 2. HTTP shared lifecycle | `8e8fea9` — missing converter injection fails | `c553cf7` — admitted image-only route and fixed reporting |
| 3. Client license gate | `330e726` — gate module absent | `713b9bd` — actual closure, policy fixtures and CI |

Every task has a test commit before its implementation commit. Explicit owned
paths were used with `git commit --only` to preserve parallel executor changes.

## Verification performed

- `.venv/bin/python -m pytest -q tests/test_image_conversion.py`: **18 passed**,
  including actual installed sips encode/decode with OS codec access, bad brands,
  dimension/pixel/input caps, missing/production codec, timeout/crash/flood,
  truncated/symlink/extra output, invalid compressed pixels despite valid CRCs,
  descendant termination and secret-environment omission.
- `.venv/bin/python -m pytest -q tests/test_heic_contract.py tests/test_web_contract.py tests/test_headers.py tests/test_privacy_canary.py`:
  **26 passed after review fixes**. Admission-before-read, false Content-Length/streamed oversize,
  body deadline, shared image/PDF cancellation capacity, recovery, backpressure,
  exact fixed errors/reporting and privacy/CORS responses passed, including
  allowed/rejected CORS preflights and early errors. Existing
  Starlette TestClient/httpx deprecation warning remains; no package substitution.
- `node --test tools/client_license_gate.test.mjs`: **19 passed after review fixes**. Transitive
  AGPL, bundled LGPL WASM, unknown/missing metadata/notices, version/license
  drift, optional runtime packages, SPDX branches, nonregistry sources, lock
  traversal, bundled GPL source and changed QuickJS artifact controls passed.
  Review controls additionally detect unlisted vendored `dist/node_modules`
  forbidden notices/unknown WASM and GPL/LGPL/AGPL component headers beyond
  64 KiB in a concatenated bundle with a permissive first component.
- `node tools/client_license_gate.mjs`: existing installed runtime closure and
  bundled notices **passed**.
- `.venv/bin/python tools/license_gate.py`: existing Python closure **passed**.
- `.venv/bin/python -m mypy`: **31 source files passed**; Node syntax and
  `git diff --check` passed.

The combined broad regression is coordinated by the parent executor. Converter
tests were not rerun after fixes confined to Node/HTTP middleware/docs; the full
targeted HTTP/header/privacy set was rerun for the middleware correction.

## Review fixes

The initial review found two genuine client license bypasses and a preflight
header regression. New regressions reproduced all of them before implementation:
15 existing Node cases passed and four new Node cases failed; the new HTTP
preflight case failed on missing `cache-control`.

- **CR-02:** Traversal formerly skipped every directory named `node_modules`.
  It now skips only exact independently audited runtime lock roots. Unlisted
  vendored folders are traversed, and the permanent fixture reports both its
  AGPL notice and unknown WASM provenance.
- **CR-03:** Formerly only the first 65,536 source characters were checked.
  The entire already-bounded file is now scanned. Three permanent controls
  place GPL/LGPL/AGPL SPDX headers after 66,000 characters of an MIT-first bundle.
  Files exceeding 8 MiB continue to refuse rather than escaping inspection.
- **WR-01:** CORS remains outside admission so busy replies have CORS. A pure
  ASGI privacy-header send wrapper now surrounds CORS too, so allowed/rejected
  preflights, early errors and normal replies have the same five headers.
  It buffers no body and preserves the existing admitted response lifetime.

Review RED commit: `39a746c`; GREEN fix: `52a1876`. Focused revalidation passed
19 Node cases, both installed closure gates, 26 HTTP/header/privacy cases and
strict mypy over 31 files. Independent reviewer recheck is coordinated by root.

## Decisions and platform limitations

Production conversion intentionally fails closed as `HEIC_UNAVAILABLE` until a
separate Linux native filesystem/egress boundary is implemented and proven.
Development subprocess smoke is not a security certification. Linux CPU/memory,
tmpfs and actual decoder/containment proofs remain release verification debt;
no container tooling, host decoder, package or deployment was installed.

`docs/heic-runtime.md` records exact CLI/configuration, supported subset, limits,
cleanup, error policy and a configuration-only Debian trixie
`libheif-examples=1.23.6-2~deb13u1` packaging candidate sourced from current Debian
metadata. Its complete dependency/plugin closure and image digest still need
release pinning/verification. No clean locked npm CI installation ran locally;
the local license proof audits the existing installation only.

## Deviations from Plan

1. **[Rule 2 — missing critical behavior] CORS wrapping for admission failures.**
   The new negative test showed that middleware-synthesized busy responses
   lacked configured CORS headers. Moved the existing CORS wrapper outside
   privacy/admission middleware, preserving configured origins and policy.
   Files: `server/app.py`, `tests/test_heic_contract.py`; commit `c553cf7`.
2. **[Rule 1 — platform cleanup behavior] Already-exited macOS group cleanup.**
   macOS can return EPERM for an already-reaped empty group. Cleanup tolerates
   that only after confirming the direct child is no longer running; a live
   child's permission error remains a failure. Descendant timeout cleanup is
   tested. File: `server/image_conversion.py`; commit `08b135a`.
3. **[Rule 3 — unavailable workflow reference paths]** Mandatory initial-read
   and project-skills-discovery reference files were absent at supplied Codex
   and Cursor locations. Read the reachable execution/TDD/thinking/template
   instructions and project `CLAUDE.md`; no project skills were configured.
   Root explicitly retains STATE/ROADMAP/requirements orchestration ownership.

## Known Stubs

None. Production unavailability is the plan's intentional security policy and
documented platform release debt, not a claimed working production codec.

## Self-Check: PASSED

All seven created artifacts/summary exist; all six task RED/GREEN commits and
both review-fix RED/GREEN commits resolve as commits. No implementation
placeholder was found in the owned files, no
unexpected deletion was committed, and the root peer review accepted the narrow
QuickJS source/hash evidence. Parallel executor files were preserved.
