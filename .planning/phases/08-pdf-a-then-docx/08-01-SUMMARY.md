---
phase: 08-pdf-a-then-docx
plan: "01"
subsystem: archival-validation
tags: [pdfa, verapdf, corpus, ci, g7b]
key-files:
  created: [harness/pdfa_fixture.py, harness/pdfa-manifest.json, harness/pdfa-baseline.json, harness/verapdf_gate.py, tools/install_verapdf.py, tests/test_gate_g7b.py, tests/test_verapdf_gate.py]
  modified: [.github/workflows/harness.yml]
metrics:
  completed: "2026-10-28"
  fixtures: 31
  required_successes: 12
---

# 08-01 — Frozen baseline and executable validator

G7b scope was committed first (`60dd243`). The 31-source manifest and twelve
required positive IDs are frozen before any PDF/A converter exists. The fixture
generator reuses production font embedding and normalizes font timestamps for
byte-identical generation. Thirteen original public PDFs are unchanged; six
constructed refusal cases include malformed input and inline LZW.

## Commits

| Commit | Result |
|---|---|
| `d4fec34` | Validator RED controls |
| `e3467ba` | Deterministic fixtures, manifest and success floor |
| `92c6c16` | Fail-closed runner, authenticated installer and additive CI job |
| `70bde93` | Actual complete pre-conversion baseline and coverage assertion |

## Verification

- Fixture tests: initial four failures from missing implementation observed;
  then four passed, expanded to **five passed** after baseline measurement.
- Runner tests: **33 passed**, including actual installed positive/negative PDFs.
  Synthetic controls cover exit-zero noncompliance, false/missing counts, wrong
  profile/filenames, parser/OOM failures, timeout and output bounds.
- Subsequent non-vacuity review added three RED zero-check cases (`8be81d3`),
  required executed checks (`03100f9`) and passed **37** runner tests. The
  pre-conversion baseline was not rerun or altered for that tightening.
- Actual authenticated unattended CLI-only installation passes `--version` at
  1.30.3; tampered archive and wrong publisher fingerprint are rejected.
- All **31** immutable inputs measured: **1 compliant, 29 noncompliant, 1 malformed
  parser-control failure** (exit 7). Baseline command exit 1 / `passed: false` is
  preserved. `measurement_complete: true` means every source was measured; it
  does not mean the baseline or a converted output passed conformance.
- Full raw report: `/private/tmp/pdf-tool-phase8-g7a-20261028/frozen-baseline-raw.json`.
  Checked-in baseline retains verdicts/rules/process statuses and raw-stream
  digests; source hashes reconcile with the manifest. No converter existed.
- Workflow YAML/shell and whitespace checks pass. CI combines the authenticated
  CLI/JRE with the existing pinned native-tools image; Dockerfile.ci is unchanged.

## Interfaces

`materialize_manifest(manifest, directory)` returns `(case, Path)` pairs after
hash/coverage checks. `run_validator(paths, executable, timeout_seconds=60)` returns
typed verdicts and infrastructure errors; `parse_report(payload, expected_count)`
checks complete explicit-2b reports. Runner CLI modes are `baseline --manifest …
--output …` and `gate <paths> --output …`. Conversion evidence should honor
`G7A_EVIDENCE_DIR`; CI sets it to `/g7a-evidence`.

## Deviations and limits

A daemon restart interrupted the first runner executor after its RED commit;
recovery preserved completed work and resumed the implementation. One automatic
approval-review timeout affected a planning commit; the permitted retry succeeded.
No work remains blocked by that timeout. Historical `.Codex` workflow paths were
replaced with the installed `.cursor` equivalents without installing agent files.

Hosted CI has **not** run. No converter, DOCX feature, deployment, local container
setup or runtime dependency installation is claimed. G3/G4/HEIC remain open.

## Self-Check: PASSED

All eight owned artifacts exist, both task deliverables and exact source/baseline
hashes are committed, and the required positive floor precedes converter work.
