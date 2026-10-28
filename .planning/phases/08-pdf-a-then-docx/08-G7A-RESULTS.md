# G7a — Local native PDF/A-2b evidence

**2026-10-28 · local pass · hosted CI pending.** Converter source: `2ad0ec1`.
Baseline/manifest precede converter implementation (`e3467ba`, `70bde93`).

## Fixed corpus and supplementary cases

- All **31 frozen inputs** processed. All **12 required positive IDs** succeed;
  the public outlined-vector sample also succeeds: **13 accepted / 18 refused**.
- Three additional cases cover simple embedded WinAnsi TrueType, permitted
  primitive/nesting boundaries, and a current document with an inserted blank
  page lacking Contents. They supplement the corpus; no frozen input was changed.
- All **16 output PDFs** validate using authenticated veraPDF **1.30.3**, explicit
  PDF/A-2b. All pass qpdf/pdfcpu: **32 structural validations**.
- **19 pages / 57 exact same-engine comparisons** pass across PDFium, Poppler and
  MuPDF. Text, page operators, geometry, font/resource fingerprints and image
  samples are preserved. Input hashes remain identical to the frozen manifest.
- Of 57 cross-engine comparisons, **55 pass and 2 retain identical source-baseline
  failures**. UserUnit/rounding size differences are likewise unchanged. These are
  not relabeled cross-engine passes or repaired by adjusting tolerances.
- Actual positive/negative validator controls, corrupt output, removed metadata,
  missing-positive/always-refuse floor and native-change controls prove sensitivity.

## Verification

Final command: `PATH="$PWD/.venv/bin:$PATH" JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-26.jdk/Contents/Home VERAPDF_CMD=/private/tmp/pdf-tool-phase8-tools/verapdf/verapdf G7A_EVIDENCE_DIR=/private/tmp/pdf-tool-phase8-g7a-20261028/converted .venv/bin/python -m pytest -q tests/test_pdfa.py tests/test_gate_g7a.py`.

Result: **47 passed in 10.33s**. Log: `/private/tmp/08-g7a-final.log`.
Evidence: `g7a-results.json`, `validator-stdout.json`, native PNGs and
`supplemental/results.json` under the configured directory. Strict typing passes
for engine/server (36 files) during API integration.

Earlier failures are retained: simple-TrueType source lacked required Length1;
the independent review exposed primitive/nesting limits; actual browser page
insertion exposed absent Contents. Fixes add guards or valid blank-page support,
with RED/GREEN proof. No failure was waived.

## Support policy and limits

Native content is preserved; no page rasterization, font substitution or content
stripping. Support covers audited embedded CIDFontType2/Identity-H and WinAnsi
TrueType, finite supported paths/text, raw/Flate RGB/gray images and blank pages.
Missing/unsupported fonts, forms/annotations, active content, unsupported color,
images/filters, existing unhandled XMP and malformed structures refuse with finite
safe reasons. Existing worker limits apply; the validator never runs in a request.

## What was NOT tested

Hosted CI has not run; its mandatory job is authored. This is a conservative
support policy and fixture corpus, not universal certification of arbitrary PDFs.
Acrobat is unavailable. G3 Linux/CDN, G4 literal-contract coverage and production
HEIC confinement remain open. Nothing deployed; DOCX is a later plan.
