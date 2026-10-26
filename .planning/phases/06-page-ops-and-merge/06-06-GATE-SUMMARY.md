---
phase: 06-page-ops-and-merge
plan: "06"
subsystem: independent-page-fidelity-gate
tags: [pdf, page-operations, merge, font-subsets, native-renderers]
requires: [06-01, 06-03, 06-04]
provides: [actual-production-output-fixtures, independent-graph-and-pixel-assertions]
affects: [06-06-final-verification]
tech-stack:
  added: []
  patterns: [production-JavaScript-writer-independent-Python-oracle, exact-mapped-native-pixels]
key-files:
  created: [harness/page6_fixture.py, tools/materialize_page6.mjs, tests/test_page6_merge_render.py]
  modified: []
key-decisions:
  - Use independent image-only PDF footprints to calibrate native crop rounding without padding masks.
  - Retain and report source-baseline cross-engine UserUnit disagreements; never count them as passing comparisons.
duration: final-full-gate-12.42s
completed: 2026-10-26
---

# Phase 6 Plan 6: Independent Automated Gate Slice

Actual production page operations generate 24 PDFs whose 53 pages retain exact mapped native pixels, form graphs and independent font programs.

This summary covers delegated Task 1 and the targeted fidelity part of Task 3.
Root owns browser observations, overall G5 results, broad regression, final review,
STATE/ROADMAP/REQUIREMENTS and the combined plan summary. This slice does not
declare overall Phase 6 or G5 complete.

## Commits and RED/GREEN

- `43aa775` — actual-output RED fixtures, materializer and corruption controls.
  Real `mergePdf` outputs were produced; both wrong-font-sharing and detached-widget
  controls failed with `DID NOT RAISE AssertionError` before assertions were implemented.
- `2105bef` — independent graph/pixel/font/resource assertions and real helper outputs.
  Full committed gate: **7 passed in 12.42 seconds**, no skips/deselections.
- A final small assertion checks serialized CropBox against returned local metadata;
  its focused all-output run passed: **1 passed, 6 deselected in 8.71s**.

No mocked production output, alternate materialization writer, library installation,
browser automation, broad suite or whole-corpus page walk was used. The independent
Python PDF writer generates acceptance references only; actual outputs exclusively
call `transformPages`, `mergePdf` and `writeImage`.

## Actual Verification

UTC verification date: **2026-10-26**, source revision
`2105befa6f8759cf898f9e66478da1d851bdad77` for the full committed run.

| Check | Actual result |
|---|---|
| `pytest -q tests/test_page6_merge_render.py -k negative_control` | 3 passed, 4 deselected, 2.11s |
| `.venv/bin/python -m pytest -q tests/test_page6_merge_render.py` | 7 passed, 12.42s |
| Final CropBox assertion, `-k all_outputs` | 1 passed, 6 deselected, 8.71s |
| Actual production outputs | 24 PDFs, 53 pages; every output page rendered in all three engines |
| Mapped same-engine source/output comparisons | 159 exact comparisons, outside intended image regions zero |
| Independent expected RGB image comparisons | 24 additional exact comparisons across eight placement cases |
| Controlled font rename alone | 6 exact source comparisons; real and controlled merges add 12 |
| `qpdf --check --warning-exit-0` | All 24 actual output PDFs passed |
| `pdfcpu validate -m relaxed` | All 24 actual output PDFs passed |
| Provenance | 40 source/oracle files SHA-256 checked before and after rendering; output SHA-256 recorded/read back |
| `git diff --check` and stub scan | Passed; no remaining incomplete assertions or TODO/FIXME stubs |

Retained final full-run artifacts: `/private/tmp/pdf-tool-phase6-g5-20261026/`.
`fixtures.json` records font/source provenance; `outputs.json` records actual output
hashes, physical page mappings, notices and metadata; `gate-evidence.json` records
all 159 existing-comparator cross-engine results and their independent baselines.
This is an 18.6 MB local dev artifact, copied from `pytest-21/page6-g50` before
pytest retention can remove it. It contains only public-corpus and constructed fixtures.

Tool versions actually read: qpdf 12.4.0; pdfcpu v0.15.0 dev/Homebrew;
MuPDF 1.28.2; Poppler 26.08.0; pikepdf 10.11.0;
pypdfium2 5.12.1 / PDFium 152.0.7947.0.

## Nonvacuous Coverage

- The specified govdocs1_003_003063 page 0 `/TT2` and govdocs1_001_001038 page 2
  `/TT0` execute nonspace letter codes and retain distinct program hashes
  `8c54d9074cb803ce67f4bc1db58cfcd8defca27d27407a39a5c0f6f48dfe5a5b` and
  `674ab0feea74f3f5ae754f3223bde2bfa75473b56cb455172bee5318907d584e`.
  Controlled inputs and output dictionaries have both BaseFont and descriptor
  FontName equal to `/ABCDEF+Arial`. Fonts remain separate indirect objects.
  Bad sharing deliberately replaces page 0 `/TT2` with page 1 `/TT0`: page 0
  changes in all three renderers while page 1 remains exact. The harmless reverse
  direction is never claimed as a corruption control.
- Real nested Tx/Btn/Ch/Sig field hierarchies retain values, effective DR/DA font
  references, real widget AP stream bytes, CO references and actual page/Annots
  ownership. Direct/named/GoTo destinations, internal links and nested outlines
  resolve to surviving physical pages after merge, collision and deletion.
  An XFA source receives the actual `MERGE_XFA_UNSUPPORTED` refusal.
- Image-only scanned fixtures exercise move, rotate, delete and inherited blank
  insertion through helpers without classification calls. Distinct scan colors
  make physical-page mapping observable.
- Default merge and explicit normalization preserve or transform nonzero origins,
  CropBox, rotation and UserUnit=2 against independent references. Returned page
  counts, MediaBox, CropBox, rotation and UserUnit are independently checked on serialized output.
- All four rotations are tested with both inherited and own-shared resource
  dictionaries. Only the target receives an image XObject. Every sibling remains
  entirely unmasked and exact; deliberately mutating a sibling font fails in all
  engines. Placement must change visible pixels, and unchanged output is rejected.
- PNG oracle pixels are independently preflattened onto white: transparent pixels
  are RGB 255/255/255, half-alpha foreground is RGB 247/142/132. Exact expected
  RGB-image PDFs verify serialized pixel color and placement. A new image page
  inherits the neighboring crop/origin/unit/rotation and matches an independent PDF.

## Native Cross-Engine Limitation

The unchanged existing comparator uses blur radius 3, channel delta 20 and 8%.
Of 159 output cross-engine pairs, **95 pass and 64 fail**. Every failing result is
identical to its corresponding independent source/oracle baseline; the assertions
require that exact inherited result, rather than labeling it a pass.

The failures involve UserUnit=2: this installed PDFium and Poppler render, for
example, 271×209 where MuPDF renders 542×417. The comparator crops differing image
sizes and consequently exceeds 8%. This is preserved native renderer disagreement,
not new source/output corruption. Full same-engine mapped equality still holds in
all three engines. This slice cannot claim all cross-engine pairs passed or close
that native compatibility limitation.

## Deviations and Limits

- **Rule 1 — acceptance coordinate bug:** A 34-pixel Poppler strip initially fell
  outside a mask derived solely from physical viewport dimensions. Investigation
  found nonzero rotated crop raster-origin rounding; the strip contained only the
  intended image. Independent image-only black-tile PDFs now determine the exact
  native footprint, and independent full RGB expected PDFs additionally require
  entire-page equality. No tolerance or geometric padding was added; unrelated
  siblings never receive a mask. This correction is in `2105bef`.
- pikepdf's default reader materializes inherited page attributes in memory.
  The inheritance assertion explicitly opens with `inherit_page_attributes=False`
  to verify serialized source leaves truly lack own Resources.
- The measured source font's known fontTools cmap issue is documented in research;
  no font program is parsed, repaired or normalized here. Native pixels and program
  SHA-256 establish this proof. No output structural failure was waived.
- Native browser PNG/JPEG/WebP decode, EXIF orientation, canvas compositing,
  HEIC requests, actual downloads and observed zero-API traffic belong to root.
  Python's flattened PNG is explicitly an oracle, not evidence for browser decode.
- Applicable broad Python/Node/build/type/Unicode/license regression is root-owned
  and was not run concurrently with its browser work. G3 Linux/container/CDN,
  literal G4 legal specimen and Linux HEIC containment remain outside this slice.

## Known Stubs and Threat Surface

No known stubs. No served endpoint, auth path, runtime dependency, persistence or
production trust boundary was added. Local fixture paths are consumed only by the
dev-only materialization CLI. MuPDF remains subprocess-only dev/CI tooling.

## Self-Check: PASSED

All three owned code/test files and this summary exist. RED `43aa775` and GREEN
`2105bef` exist in git history. The full committed gate passed with the counts above;
the deliberate corrupted outputs fail for their intended reasons. No tracked file
deletions were introduced. Shared source and root-owned evidence were preserved.
