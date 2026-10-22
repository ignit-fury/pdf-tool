---
status: investigating
trigger: Test all corpus/public PDFs and fix reproducible errors
created: 2026-10-22
---

# Corpus compatibility audit

User authorized testing `/Users/prempatel/Pictures/pdf-tool/corpus/public` and fixing
errors. Inventory: 217 PDFs, 8,254 pages, 202.8 MiB. Source PDFs must remain unchanged.

## Plan

1. Scan every page for engine parsing/classification errors, recording exact coverage,
   bounded resource/time failures, page buckets and named refusal counts.
2. Exercise genuine per-file edit preview/apply with server-issued run IDs and immutable
   originals. Cover automatic and explicit bundled-font replacement where applicable.
3. Diagnose unexpected crashes, false refusals, timeouts and successful-but-wrong output;
   add regressions and fix their responsible layer. Do not hide failures by changing input
   files, enlarging limits, weakening geometry guards or silently dropping glyphs.
4. Rerun failed cases and relevant rendering/typing/client checks; publish a per-file report
   with editable outcomes, named unsupported features and genuinely unresolved issues.

Classification of expected scan/outlined/symbolic/unsupported geometry is evidence,
not a passing edit claim. No exact promise that damaged or unreadable PDFs are editable.
Public-release Linux/CDN checks stay outside this local corpus task.

## F-01 — whole-document edit planning

Confirmed: FAR (2,026 pages) page 0 returned 17 runs but edit preview ended with
WORKER_FAILED at the CPU limit. Two regression tests showed recipes for one/two pages
classified all 16 pages of a synthetic document. Planning now uses RunIndex for only
the addressed pages and retains every run on each selected page for correlation/guards.
Source-hash and malformed-address refusals remain unchanged.

After correction, the same FAR preview succeeded in 1.66 seconds. Focused page-scope,
recipe, password and short-replacement tests: 46 passed. Strict typing: 28 files clean.
Whole-corpus scan results will be recorded separately with tested revision/coverage.
