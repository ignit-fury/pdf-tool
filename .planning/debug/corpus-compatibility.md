---
status: resolved
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

## F-02 — omitted Standard 14 font widths

Legal Type1 Helvetica/Times/Courier dictionaries may omit /Widths. The fit code
required /FirstChar and /Widths anyway, turning ordinary text into resolution_failed.
It now uses the reader's Adobe standard metrics only for the twelve non-symbolic
Standard 14 faces, applying the actual Encoding/Differences. Unknown faces without
metrics still refuse. Four real-edit regression variants preserve following text
positions and source bytes; a separate test forbids guessing an unknown font's widths.

## F-03 — malformed inline-image syntax

govdocs1_011_011089.pdf lacks valid inline-image terminators. The precise parser
exception is translated into PDF_INVALID rather than WORKER_FAILED. No partial
page or guessed operator recovery is exposed. Three regressions include the real
fixture, a tiny malformed equivalent and a healthy control/next request.

## F-04 — dense-page worker CPU limit

govdocs1_006_006032.pdf exceeded the 20-second CPU budget. Profiling located
repeated full-stream Tf regex scans and response stream decompression. Each worker
response now reuses its own decoded stream; bounded one-stream font histories use
binary lookup. The actual page response fell from a killed 20.24 seconds to 1.27
seconds with 268 runs. Cache regressions preserve active-font and invalid-size
semantics. Parser objects remain in disposable workers.

## F-05 — physical stream provenance and empty showing operators

Clustering ignored /Contents part indices, anchoring glyphs from several streams
to one part. Grouping now includes the physical part. Separately, empty Tj and
numeric-only TJ instructions no longer consume glyph-derived rewrite ordinals;
their instructions and pen effects survive. The real 010118 fixture now applies
shorter edits with independently verified full-page text. The historical five-page
corpus probe has 4 known failures instead of 89, with no new failures.

## F-06 — raw embedded fonts and substitution handoff

Glyph inspection supports raw Type1 and CFF, but the edit shaper expects an sfnt
container. These originals now enter bundled replacement: exact family match or
explicit user choice. Review caught an additional plan/write mismatch: a planned
substitution key did not always force the writer to use its target. The key is now
authoritative at writing. A regression first failed on the missing output font
resource, then passed with actual Liberation Serif embedded and selected. Manual
replacement and independent full-page text verification also pass.

## F-07 — preview agreement

Known shared-operator and correlation refusals now appear during planning. A real
002154 fixture additionally demonstrated a layout-guard refusal only visible after
rewriting. Edit preview now runs the same apply validation inside disposable worker
scratch, returning only the report. It cannot expose output bytes or bypass signed
PDF acknowledgement for a real apply. Tests cover the actual refusal, successful
preview, immutable sources, signature handling and worker isolation.

## Verification and scope

Read audit: all 217 documents and 8,254 pages attempted; 8,253 classified, one known
malformed-page parser exception; no timeouts, named resource limits or subprocess
failures; every source hash unchanged. All read-critical source files match the
per-file recorded stages. 207 documents contain at least one classified editable
run; that is not a guarantee those runs pass the writer's guards.

Final edit results and remaining compatibility limits are recorded in
`../audits/corpus-compatibility-2026-10-22.md` and the final per-file JSON report.
Editing samples up to three candidate runs in the first three pages, plus one late
page discovered by the complete read pass. No claim that every page or font is
editable, or that every corpus output received an outside-box pixel comparison.

Independent final code review found the F-06 handoff defect and verified its
correction; no other introduced defects were found. Linux/container and live CDN
release gates remain open and are outside this local corpus task.

Final audit complete on implementation `5457863`: 217 files, 238 sampled pages,
764 edit cases, 346 returned outputs, 333 independently verified output texts.
154 files have verified identity/shorter pairs (103 automatic, 51 explicit font);
10 more have at least one verified edit. No detected corrupt/wrong-text output,
preview/apply disagreement or edit-worker crash/timeout. All source hashes are
unchanged in a fresh final check. Remaining sample outcomes: 35 named edit
refusals, 10 without an editable sample, 6 independently unverifiable and 2 input/
resource page refusals. These compatibility limits remain disclosed, not erased.

Final quick regression suite: 473 passed, 5 platform/deployment skips, 25 corpus
tests deselected; latest focused font/recipe/preview/render suite: 94 passed;
all three renderer gates and 12 client tests pass; build and strict typing pass.
