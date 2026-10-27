---
phase: 07-exports
plan: "04"
subsystem: native-export-gate
tags: [g6, exports, pdfium, poppler, mupdf, zip]
requires: [07-01, 07-02, 07-03]
provides: [independent-production-output-proof]
affects: [07-04-browser-and-regression-evidence]
tech-stack:
  added: []
  patterns: [independent-python-readback, native-region-union-oracle]
key-files:
  created: [harness/export_fixture.py, tools/materialize_exports.mjs, tests/test_gate_g6.py]
  modified: []
key-decisions:
  - Exact masks use separately rendered black Form/image support, preserving native boundary coverage without padding.
  - Existing cross-engine failures remain explicit baseline disagreements; thresholds are unchanged.
completed: 2026-10-27
---

# Phase 7 Plan 4: Automated G6 Slice Summary

Actual client split/ZIP and isolated worker flatten/compression outputs pass independent structural, archive and three-engine preservation checks on deliberate fixtures plus both pages of public IRS Form 1040.

This is the delegated automated slice; the root executor owns the combined summary, browser observations, regressions and planning-state updates.

## Evidence

Artifacts: `/private/tmp/pdf-tool-phase7-g6-20261027/`; `fixtures.json`, `exports.json`, `gate-evidence.json`, PDFs, ZIP and native PNGs remain there. No installation, deployment, container work or runtime MuPDF integration occurred.

| Check | Result |
|---|---|
| Focused RED | Region-union test failed with `NotImplementedError` before its oracle implementation |
| Task 1 focused GREEN | `4 passed, 1 deselected in 2.32s` |
| Full targeted G6 | `5 passed in 5.96s` |
| Final source-hash assertion | Focused structure test: `1 passed, 4 deselected in 1.97s` |
| Structural validation | 7 outputs × qpdf + pdfcpu relaxed = 14 successful validator calls |
| Mapped output pages | 13 across 7 output PDFs; all pages checked |
| Same-engine comparisons | 39: 27 exact source/output, 9 exact independent flatten-reference/output, 3 confined downsample checks |
| Confined changes | 9 flatten and 3 downsample comparisons; zero changed pixels outside independent region union |
| Appearance proof | 18 disjoint appearance-region comparisons; filled text, selected state and nonidentity AP transform |
| Native rasterizations | 26 page sets × PDFium/Poppler/MuPDF = 78 PNGs |
| Archive | Actual production 2-entry stored ZIP; Python names/count/order/CRC/headers/extracted-byte equality |
| Source immutability | All 8 scratch source/reference hashes and original public corpus hash checked |

Full command:

```text
PDF_TOOL_G6_ARTIFACTS=/private/tmp/pdf-tool-phase7-g6-20261027 .venv/bin/python -m pytest tests/test_gate_g6.py -q -x
```

Fixtures include disjoint colored appearances, a saved filled text field, selected checkbox state, rotated appearance Matrix, nonzero CropBox, page rotation, UserUnit and an untouched sibling sharing resources. Negative controls reject missing/wrong-order pages, detached widgets/destinations, altered sibling resources, removed appearance pixels, unrelated pixels in the gap between regions, damaged ZIP CRC and a missing central directory. Worker refusals cover missing and singular appearances.

| Compression output | Before | After | Evidence |
|---|---:|---:|---|
| Deliberate annotated PDF | 3,737 | 2,505 | Lossless; native equality and resource preservation |
| Deliberate RGB image PDF | 6,292,232 | 6,292,232 | Exact original returned; `NO_SIZE_REDUCTION`; decoded samples preserved |
| Explicit image downsample | 6,292,232 | 735,448 | One image 2048×1024 → 1600×800; genuine changes confined to its rendered support |
| Real IRS Form 1040 | 220,237 | 200,250 | Both pages exact in each engine; decoded samples/resources preserved |

Corpus provenance: `corpus/public/irs_form_1040.pdf`, SHA-256 `3d31c226df0d189ced80e039d01cf0f8820c1019681a0f0ca6264de277b7e982`.

Tools: Node `/Users/prempatel/.local/bin/node`; qpdf, pdfcpu, pdftoppm and mutool under `/opt/homebrew/bin/`. Missing native tools fail the gate rather than silently skip.

## Explicit Limits

Of 39 cross-engine pairs, 27 meet the existing 8% threshold and 12 fail identically to their unmodified source or independently painted reference. These 12 remain baseline disagreements, not passing cross-engine comparisons. Twenty-nine pairs also retain baseline physical raster-size disagreements, including one-pixel rounding and MuPDF honoring UserUnit where the other native paths do not. Exact same-engine comparisons never crop or use a pixel tolerance; the established cross-engine comparator is unchanged.

PDFium's default harness rendering displays the stamp but not the interactive widgets. Flatten checks therefore require full exact equality to the separately painted reference, independently proving the saved field text/state. The reference uses separately created Form streams and explicit known placements, never the production flatten writer or copied output appearances. Separate black Form/image references capture actual native boundary-pixel coverage for the exact intended union, rather than adding padding or using the disjoint rectangles' enclosing box.

Browser-generated PNG/JPEG outputs, image ZIPs, API/UI lifecycle/privacy, and broader regressions belong to the root executor's evidence. This slice makes no claim to close existing G3 Linux/CDN, G4 literal-contract or production HEIC-confinement release checks.

## Commits

- `5800df0`: RED gate tests.
- `43d65e1`: fixtures and actual client materializer.
- `daf1723`: exact native region/reference proof.

## Deviations from Plan

No product deviations. Oracle refinement was required because native Form clipping differs from direct page-space rectangles and Poppler includes an image's boundary pixels. Separately rendered references preserve exact comparisons without loosening masks or tolerances.

No known stubs or new runtime threat surface. Changes remain confined to test/harness tooling; scratch artifacts contain generated fixtures and the identified public corpus sample.

## Self-Check: PASSED

All three owned implementation files and this summary exist. Commits `5800df0`, `43d65e1` and `daf1723` exist. No tracked files were deleted by these commits.
