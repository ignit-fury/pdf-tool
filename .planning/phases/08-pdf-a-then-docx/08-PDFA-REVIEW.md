# PDF/A source review — 2026-10-28

Scope: native converter, its font/color/operator policy and focused tests.
Independent reviewer `phase8_pdfa_review` reproduced two real acceptance gaps:
graphics-state nesting beyond 28, and excessive name/string lengths. Its output
samples are in `/private/tmp/pdfa-limit-review-wpkdngtb`. The review agent hit a
usage limit before writing a final report; this is not a completed independent
whole-phase review.

The orchestrator verified the implementation-limit rules against the official
[PDF/A-2b profile](https://raw.githubusercontent.com/veraPDF/veraPDF-validation-profiles/integration/PDF_A/PDFA-2B.xml),
added integer/real and page-boundary guards, and reproduced seven failures before
fixing them. A separate native check found a missing simple-TrueType Length1;
two failing missing/wrong-length cases now refuse. Browser testing found a valid
blank page without Contents was refused; a failing regression now succeeds.

All confirmed findings are fixed in `2ad0ec1`. The final converter/gate run passes
47 tests, including the complete frozen corpus, supplementary TrueType and exact
boundary cases, external conformance and native fidelity. No manifest/floor or
renderer tolerance was changed. Metadata/date, output-intent and operator probes
that the reviewer found validator-compliant were not mislabeled as violations.
Nothing was suppressed. Hosted CI and whole-phase integration review remain open.
