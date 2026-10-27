---
phase: 7
slug: exports
status: completed_locally
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-30
updated: 2026-10-26
---

# Phase 7 — Validation Strategy

This current contract replaces the August command/path guesses after inspection of the
Phase 6 workstation. Baseline: 560 local Python tests, 125 client tests, seven G4
technical-proxy tests, build/types/licenses pass. Baseline results are not Phase 7 proof.
No deployment, package installation, new test framework or container setup is included.

| Requirement / risk | Owner | Actual intended check |
|---|---|---|
| EXPO-05 one extraction path, cache reuse, metadata | 01 | `pytest -q tests/test_export_metadata.py tests/test_export_single_path.py` |
| EXPO-05 reading order, headings, styles, closed ruled tables, escaped output | 01 | `pytest -q tests/test_blocks.py tests/test_export_text.py` |
| EXPO-02 native lossless/default and explicit bounded downsample | 02 | `pytest -q tests/test_export_pdf.py` plus G6 pixels |
| EXPO-04 native flatten, appearances/postconditions/refusals | 02 | Same structural suite plus G6 independent annotation masks |
| EXPO-02/04/05 transport/current bytes/password/signature/privacy | 02 | `pytest -q tests/test_export_api.py` with real isolated workers |
| EXPO-01 PNG/JPEG dimensions, chosen DPI, zip, cleanup/budgets | 03 | `node --test client/src/exports/images.test.mjs client/src/exports/zip.test.mjs` plus actual browser files |
| EXPO-03 catalog-safe split, groups/resources/limits | 03 | `node --test client/src/exports/split.test.mjs` plus actual G6 PDFs |
| All formats current-byte identity, stale/cancel, immutable history | 03 | `node --test client/src/exports/controller.test.mjs` plus browser mixed-edit journey |
| Actual split/flatten/compress pixels and structure, nonvacuous controls | 04 | `pytest -q tests/test_gate_g6.py` through PDFium/Poppler/MuPDF, qpdf and pdfcpu |
| ZIP interoperability | 04 | Python zipfile independently reads actual JS-created archives |
| Local/server disclosures and zero API during images/split | 04 | Connected browser observer before Open through actual export/download; unknown-path and navigation controls |
| Compression preview and 320/760px keyboard/focus | 04 | Actual built browser, screenshots, decoded current/prepared download digests |

Use installed `.venv/bin/python -m pytest` (no uv sync). Tests precede implementation
for meaningful behavior. Each owner runs focused tests and relevant types/build once;
root runs one consolidated applicable local regression after integration, the complete
G6 gate, Unicode and runtime license closures. Do not repeat the full corpus sweep.
Do not run heavy native gates concurrently with timing-sensitive browser checks.

Independent oracles compare every generated retained page against its source in the
same native engine; unchanged pages are unmasked. Flatten masks are limited to the
precise annotation rectangles; downsample masks to intended image extents. Corruption
outside a mask, omitted pages, changed text, a wrong ZIP entry and a second extraction
path must fail named controls. No broad mask or tolerance weakening is acceptable.
Actual image bytes/dimensions, native decode, ZIP contents and HTTP traffic must be
observed; mocks alone cannot establish them. Preserve source digests.

Browser-only acceptance includes native compression Before/After of the exact prepared
bytes, current-materialized text/page content in every export, unchanged working PDF
and Undo stack, default lossless/explicit lossy choice, typed notices, signed/encrypted
controls, cancellation/stale preview behavior, DPI presets, no auto analysis/upload,
responsive controls and focus. Markdown/HTML reading order is visually inspected on
constructed heading/column/table fixtures. Record proof/limits in `07-G6-RESULTS.md`.

All four plans must produce summaries; independent goal verification reconciles all five
EXPO requirements. G3 Linux/container/live-CDN, Phase 5 literal contract specimen and
production HEIC confinement remain open. macOS local G6 is not Linux/CI execution.

## Local completion — 2026-10-27

All four plan summaries exist; `07-VERIFICATION.md` passes 12/12 merged must-haves.
Consolidated local regression: 634 passed / 36 deselected; client: 140 passed; G4: 7 passed;
strict types/build/Unicode and 19 license negatives/closures pass. Actual browser and
G6 native evidence, masks, limitations and raw artifact paths are in 07-G6-RESULTS.md.
Existing Linux/CDN/specimen/HEIC release debt stays open; no deployment occurred.
