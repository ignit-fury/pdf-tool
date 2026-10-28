---
phase: 08
slug: pdf-a-then-docx
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-30
updated: 2026-10-28
---

# Phase 8 validation strategy

This map defines coverage, not execution. No Phase 8 product implementation or passing gate is asserted. The dated research refresh supersedes historical Docker/python-docx/pikepdf.pdfa recommendations.

| Task | Requirement | Quick automated command | Full gate / evidence |
|---|---|---|---|
| 08-01.1 | EXPO-07, G7b | `uv run --frozen pytest -q tests/test_gate_g7b.py` | Ceiling commit 60dd243 predates code; freeze inputs/hashes/expectations |
| 08-01.2 | EXPO-06 | `uv run --frozen pytest -q tests/test_verapdf_gate.py tests/test_gate_g7b.py` | Real positive/negative controls and every original baseline |
| 08-02.1 | EXPO-06 | `uv run --frozen pytest -q tests/test_pdfa.py` | Native repair, safe refusal, unchanged source, ICC audit |
| 08-02.2 | EXPO-06, G7a | `uv run --frozen pytest -q tests/test_pdfa.py tests/test_verapdf_gate.py` | `uv run --frozen pytest -q -m corpus tests/test_gate_g7a.py`; fixed twelve-success floor/native fidelity |
| 08-03.1 | EXPO-06 | `uv run --frozen pytest -q tests/test_export_api.py tests/test_worker.py` | Real isolation allowlist; all nine fixed worker→API→UI refusal mappings/fallbacks, password/signature/limits |
| 08-03.2 | EXPO-06 | `node --test client/src/exports/controller.test.mjs` | Client build; no eager upload, current bytes, cancellation/stale results |
| 08-04.1 | EXPO-07/08 | `uv run --frozen pytest -q tests/test_blocks.py tests/test_export_text.py tests/test_export_single_path.py` | Bounded shared image/facts and unchanged prior serializers |
| 08-04.2 | EXPO-07/08 | `uv run --frozen pytest -q tests/test_export_docx.py tests/test_export_single_path.py` | Actual ZIP/CRC/XML/styles/images/tables/flattening/full snapshot digest |
| 08-05.1 | EXPO-08 | `uv run --frozen pytest -q tests/test_docx_api.py -k "acknowledgement or cors"` | Strict 256-byte three-field JSON acknowledgement; allowed-Origin OPTIONS includes X-DOCX-Review, then actual cross-origin review/conversion |
| 08-05.2 | EXPO-07/08 | `uv run --frozen pytest -q tests/test_docx_api.py tests/test_export_api.py` | Isolation forwards reviewed source/full-snapshot/policy; review never generates OOXML; recomputation must match |
| 08-06.1 | EXPO-07/08 | `node --test client/src/exports/controller.test.mjs` | Binary DOCX; separate review/convert and all invalidation triggers |
| 08-06.2 | EXPO-07/08 | `npm --prefix client run build` | Actual focus/keyboard/320px/760px in G7 results |
| 08-06.3 | EXPO-06/07/08, D-8.5 | `uv run --frozen pytest -q tests/test_docx_cuttable.py -m "not corpus"` | Corpus removal test runs all other exports/G6/G7a; browser downloads reuse native helpers |

New tests belong to their listed task, with RED before behavior implementation. Quick commands target under 60 seconds; expensive native/corpus/removal suites are explicit full gates. Missing tools leave a required gate unperformed, never silently skipped green.

## Gate execution

- Freeze thirteen public risk-stratified originals, twelve constructed positive IDs and independent refusal controls. Measure the exact source bytes before creating `engine/export/pdfa.py`. Raw compliant Type3 can prove the validator's positive branch while remaining outside the product support envelope.
- Require every positive ID and `minimum_successes=12`; do not lower the floor or drop fixtures after observing refusals. Always-refuse fails.
- Authenticated local CLI: `/private/tmp/pdf-tool-phase8-tools/verapdf/verapdf`; set `VERAPDF_CMD` accordingly and `JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-26.jdk/Contents/Home` for this installation. Stable 1.30.3 archive SHA-256 `b512bf24945503a33fc10738ecffc1f2dccaaf8593a448e94ee9ac86a9559a59`; publisher fingerprint `13DD102B4DD69354D12DE5A83184863278B17FE7`. CI installs exact authenticated CLI bytes in runner temporary storage; no new containers.
- Parse JSON `report.jobs[].validationResult[].compliant`, rule summaries and batch counters, never XML `isCompliant` as a JSON key. Actual direct positive/negative smokes returned 0/1. A synthetic exit-zero false report must still fail; exit alone cannot prove compliance. Empty/malformed/incomplete reports, parse/encryption/OOM/exception counters and timeouts fail closed.
- Local full G7a passes before PDF/A integration or DOCX. Add a Java corpus job to the existing Harness workflow. Actual hosted CI remains a release gate until observed; local proof is labeled local.
- CI executes G7a inside the existing unchanged Dockerfile.ci image so its pinned native renderers/qpdf/pdfcpu are actually available. The host job installs the pinned CLI/JRE, mounts both read-only into that image and runs the complete real G7a command; smoke both Java and veraPDF inside the image first. Never silently omit native checks or assume uninstalled host tools. No local container setup is authorized.
- DOCX review acknowledgement is plain bounded JSON containing source_sha256, snapshot_sha256 and policy_version, independently recomputed before conversion. No HMAC/token/secret/expiry/cache/authentication module. Server CORS explicitly admits X-DOCX-Review and real OPTIONS→review→convert is tested.
- After final changes run `uv run --frozen pytest -q -m "not corpus"`, full G6/G7a/removal corpus gates, `node --test client/src/exports/*.test.mjs`, `npm --prefix client run build`, `uv run --frozen mypy engine server` and `uv run --frozen python tools/license_gate.py`. Reuse Phase 7 helpers.

## Client observations

Plan 06 records actual warning/convert ordering, current bytes/download identity, password/signature/refusal/cancel/Undo and 320/760px keyboard/focus in `08-G7-RESULTS.md`. ZIP/XML assertions do not prove Word compatibility: observe an available Word client, otherwise record unperformed. Available Acrobat preflight is additional evidence, never a veraPDF replacement. No app installation, deployment or container setup. G3 Linux/CDN, G4 literal-specimen and production HEIC gates stay open.

## Multi-source coverage audit

| Source | ID / item | Plans | Status |
|---|---|---|---|
| GOAL | Honest archival/interchange formats without uncontrolled scope | 01–06 | COVERED |
| REQ | EXPO-06 validator-gated PDF/A | 01–03, 06 | COVERED |
| REQ | EXPO-07 direct OOXML within ceiling | 01, 04–06 | COVERED |
| REQ | EXPO-08 this-document warning before conversion | 04–06 | COVERED |
| CONTEXT | D-8.1 PDF/A first, 2b corpus, CI/dev-only validator | 01–03 | COVERED |
| CONTEXT | D-8.2 ceiling before implementation | 01 | COVERED |
| CONTEXT | D-8.3 shared model, no second extractor | 04–05 | COVERED |
| CONTEXT | D-8.4 identical analyzed warning/output projection | 04–06 | COVERED |
| CONTEXT | D-8.5 independent cuttability | 04–06 | COVERED |
| CONTEXT | D-8.6 no table-detection scope creep | 01, 04 | COVERED |
| RESEARCH | pikepdf 10.11, no unavailable API/upgrade | 02 | COVERED |
| RESEARCH | Authenticated stable CLI/report parser/controls/baseline | 01–02 | COVERED |
| RESEARCH | Non-vacuous embedded-font/RGB/gray envelope and refusal | 01–02 | COVERED |
| RESEARCH | Phase 3 font/width/glyph guards reused | 01–02 | COVERED |
| RESEARCH | Audited reproducible ICC | 02 | COVERED |
| RESEARCH | Existing-model images/facts, truthful counts/unknowns | 04 | COVERED |
| RESEARCH | Direct bounded stdlib OOXML without package install | 04 | COVERED |
| RESEARCH | Review/source/revision binding to complete projection | 05–06 | COVERED |
| RESEARCH | Worker limits/isolation/privacy/errors and typed regressions | 02–06 | COVERED |
| RESEARCH | Licence evidence, no runtime validator/AGPL | 01–06 | COVERED |

Deferred PDF/A-1/3, wider DOCX reconstruction, round-trip and DOCX→PDF stay excluded. Historical python-docx/Docker/Phase-3-defect assumptions are superseded by the dated refresh, not omitted requirements.

## Sign-off

- [x] Every requirement/locked decision has an owning plan and automated check.
- [x] Every new test/scaffold has an owning task; no test is assumed passing.
- [x] No per-task verification is manual-only.
- [ ] Frozen baseline and full gates actually executed.
- [ ] Browser/native/client results recorded with honest unavailable checks.
- [ ] Actual hosted G7a CI observed before release.
