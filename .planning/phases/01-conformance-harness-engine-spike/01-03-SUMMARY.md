---
phase: 01-conformance-harness-engine-spike
plan: 03
subsystem: corpus
tags: [pikepdf, corpus, conformance, ci, privacy, private-tier]

# Dependency graph
requires:
  - phase: 01-02
    provides: corpus/public/, corpus/manifest.json (15-category schema)
  - phase: 01-04
    provides: harness/run_corpus_harness.py (reused unmodified against the private tier)
provides:
  - "tools/probe_corpus.py - probe_file(pdf_path) -> set[str], check_manifest(manifest_path, corpus_dir, enforce_full_coverage=True) -> list[str]; independent D-04 structural verifier, serves both tiers"
  - "tools/fetch_private_corpus.py - fetch_private_corpus(bucket_base_url, bearer_token, ...) -> FetchResult(status); D-02 absence-is-normal contract"
  - "corpus/private-manifest.json - empty ([]) private-tier manifest, same schema as public minus source_url"
  - "tools/check_corpus_size.py - check_corpus_size(public, private) -> int; mechanical Gate G0 100-document floor"
  - ".github/workflows/corpus.yml - corpus-public (unconditional), corpus-private-gate (main/release, fetch->probe->validate), corpus-size-gate (main/release, blocking)"
affects: [02-text-model, 03-rewrite-engine-font-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "probe_corpus.py detects category membership via pikepdf object-layer traversal only (font Subtype/Encoding/DescendantFonts/FontDescriptor/Flags/BaseFont, XObject Subtype, Annot AP, Contents array shape, trailer Root/ID keys) plus a single byte-substring scan (BI) for inline images - never parse_content_stream/unparse_content_stream, verified by grep"
    - "check_manifest(..., enforce_full_coverage: bool) is one function serving both tiers - the private-tier CI invocation passes --no-coverage-check rather than a second script"
    - "fetch_private_corpus.py is stdlib-only (urllib.request, hashlib, json) - no cloud SDK; tested against a local http.server mock, never a real bucket"
    - "corpus-private-gate builds Dockerfile.ci AFTER the fetch step (not before, unlike harness.yml) so the image's COPY . . bakes in the freshly-fetched corpus/private/ files, reusing the same pinned poppler/mupdf/qpdf/pdfcpu image rather than re-declaring those installs in the workflow"

key-files:
  created:
    - tools/probe_corpus.py
    - tests/test_probe_corpus.py
    - tools/fetch_private_corpus.py
    - tests/test_fetch_private_corpus.py
    - corpus/private-manifest.json
    - tools/check_corpus_size.py
    - tests/test_check_corpus_size.py
    - .github/workflows/corpus.yml
  modified:
    - .gitignore
    - corpus/README.md

key-decisions:
  - "malformed detection also checks trailer /Root and /ID keys directly (plain object-level inspection), not only pikepdf.PdfError/UserWarning on open - the real D-03 malformed fixture (Isartor missing-/ID trailer) parses cleanly under qpdf's own --check (already independently confirmed by Plan 01-04's harness), so open()-time error/warning detection alone would never fire on it"
  - "symbolic_fonts detection checks a Type0 font's DESCENDANT FontDescriptor (not just the Type0 dict's own, which normally has none - ISO 32000-1 9.7.4), plus special-cases the two Standard-14 BaseFonts (/Symbol, /ZapfDingbats) that are inherently symbolic even with no explicit FontDescriptor present"
  - "corpus-private-gate reuses Dockerfile.ci (built after fetch) instead of installing qpdf/pdfcpu/poppler/mupdf a second time via apt in the workflow YAML - avoids duplicating Plan 01-04's pinned-tool-install logic"

requirements-completed: [ENG-01]

# Metrics
duration: ~90min
completed: 2026-08-12
---

# Phase 1 Plan 3: Private-Tier Corpus Mechanism + Independent Prober + Gate G0 Size Checkpoint Summary

**Built the D-04 independent structural prober (catching a real, pre-existing wrong-label bug in the public manifest along the way), the D-01/D-02 private-tier fetch mechanism with a machine-parseable absence-is-normal contract, wired both the prober and the render/validate harness into CI against the private tier post-fetch, and stopped at the mandatory Task 3 checkpoint with the combined corpus at 17/100 documents.**

## Performance

- **Duration:** ~90 min
- **Completed:** 2026-08-12
- **Tasks:** 2 of 3 completed (Task 3 is the blocking checkpoint itself; its mechanical artifacts are built and committed, then execution halted as designed)
- **Files modified:** 10 (8 created, 2 modified)

## Accomplishments

- `tools/probe_corpus.py`: `probe_file()` independently re-derives 11 structurally-verifiable
  categories from PDF bytes via pikepdf's object-layer API only — fonts (Type0/Identity-H,
  Type3, CID-keyed CFF via descendant `/FontFile3 /Subtype /CIDFontType0C`, subset-tag
  `/BaseFont` regex, symbolic `/FontDescriptor /Flags` bit 3 — checked on both the font's own
  descriptor and, for Type0, its descendant's), XObjects (`/Subtype /Form`), annotations
  (`/AP /N`), `/Contents` array shape, encryption, inline images (byte-substring scan for `BI`,
  explicitly sanctioned as non-interpretive per the plan), and malformed (open-time
  `PdfError`/`UserWarning` OR a missing `/Root`/`/ID` trailer key)
- The four genuinely rendering-only categories (`ocr_scan`, `vector_outlined_text`,
  `justified_right_aligned`, `tables`) are explicitly marked "declared, unverified-by-prober"
  with the plan's exact-verbatim circularity-warning comment in the code
- `check_manifest(manifest_path, corpus_dir, enforce_full_coverage=True)` — one function/CLI,
  parameterized (never hardcoded to `corpus/manifest.json`/`corpus/public`), serving both
  tiers via `--no-coverage-check`
- `grep -c "parse_content_stream\|unparse_content_stream" tools/probe_corpus.py` returns 0
- **Discovered a real, pre-existing bug in Plan 01-02's `corpus/manifest.json`** (see Deviations
  below): the prober working correctly is exactly what surfaced it
- `tools/fetch_private_corpus.py`: stdlib `urllib.request` bearer-token fetch, sha256-verified
  per file, three status outcomes (`skipped`/`ok`/`error`) tested against a local
  `http.server` mock (never a real bucket); absent credentials always exits 0 with
  `status=skipped` on its own line; wrong token or hash mismatch is a distinguishable
  `status=error` (nonzero exit) — the two never collapse into each other
- `corpus/private-manifest.json` authored: same schema as the public manifest minus
  `source_url`, starts as `[]`
- `.gitignore` updated; `git check-ignore corpus/private/x.pdf` confirms private-tier bytes are
  never committable
- `.github/workflows/corpus.yml` created with three jobs: `corpus-public` (unconditional,
  every push/PR including forks), `corpus-private-gate` (main/release only — fetch, then
  probe `--no-coverage-check` and `harness/run_corpus_harness.py` against the private tier,
  both conditioned on the fetch step's `status=ok` output, both running inside `Dockerfile.ci`
  built *after* the fetch so the freshly-downloaded bytes are baked into the image), and
  `corpus-size-gate` (main/release only, hard-fails below 100 combined documents)
- `tools/check_corpus_size.py`: `check_corpus_size(public, private) -> int`, CLI exits 1 below
  100 (printing the public/private breakdown) and 0 at/above — tested against scratch
  fixtures on both sides of the threshold, never against the real (currently 17-document)
  manifests, since that would make the test fail on the gate correctly doing its job

## Task Commits

Each task was committed atomically:

1. **Task 1: Independent structural prober (D-04)** - `78c3be9` (feat)
2. **Task 2: Private-tier fetch, actually probed and validated once fetched (D-01, D-02, D-04)** - `bc7bfd1` (feat)
3. **Task 3 (mechanical artifacts, then HALT): Gate G0 corpus-size checkpoint** - `205b177` (feat)

## Files Created/Modified

- `tools/probe_corpus.py` - Independent D-04 structural prober, both tiers
- `tests/test_probe_corpus.py` - Wrong-label, zero-count (default and disabled), real-manifest, no-interpreter-reuse coverage
- `tools/fetch_private_corpus.py` - D-01/D-02 private-tier fetch with machine-parseable status
- `tests/test_fetch_private_corpus.py` - Local `http.server` mock proving all three status outcomes
- `corpus/private-manifest.json` - Empty private-tier manifest (schema only)
- `tools/check_corpus_size.py` - Gate G0 100-document mechanical floor check
- `tests/test_check_corpus_size.py` - Scratch fixtures on both sides of the threshold
- `.github/workflows/corpus.yml` - `corpus-public`, `corpus-private-gate`, `corpus-size-gate`
- `.gitignore` - `corpus/private/` added
- `corpus/README.md` - Private-tier fetch mechanism and manifest schema documented

## Decisions Made

See `key-decisions` in frontmatter. The two most load-bearing:

1. **`malformed` detection needed a second signal beyond open-time errors/warnings.** The real
   D-03 malformed fixture (Isartor's missing-trailer-`/ID` conformance case) parses cleanly
   under qpdf's own `--check` — confirmed independently by Plan 01-04's harness ("qpdf does not
   flag it at all"). A prober relying solely on `pikepdf.PdfError`/`UserWarning` at open time
   would never detect it. Added a direct, plain trailer-dictionary key check
   (`/Root`/`/ID` presence) — still object-layer inspection, not content-stream interpretation.
2. **`symbolic_fonts` needed descendant-font and BaseFont-name special cases.** A Type0
   composite font's `/FontDescriptor` lives on its descendant CIDFont dict, not the Type0 dict
   itself (ISO 32000-1 §9.7.4) — missed on the first pass, caught by running the prober against
   the real corpus before writing tests. `/Symbol` and `/ZapfDingbats` are inherently symbolic
   Standard-14 fonts even with no explicit `/FontDescriptor` at all (`far_federal_acquisition_regulation.pdf`'s embedded `ZapfDingbats` has none) — added as a plain BaseFont-name check.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `symbolic_fonts` under-detected on first implementation**
- **Found during:** Task 1, running the prober against the real public corpus before finalizing tests
- **Issue:** `_probe_font()` only checked `/FontDescriptor` on the font dict itself. Two real corpus files' symbolic fonts live elsewhere: `irs_form_w4.pdf`'s `AdobePiStd` is a Type0 font whose `/FontDescriptor` is on its descendant CIDFont; `far_federal_acquisition_regulation.pdf`'s `ZapfDingbats` has no `/FontDescriptor` object at all (Standard-14 fonts don't require one).
- **Fix:** Added a descendant-FontDescriptor check for Type0 fonts, plus a BaseFont-name check against `{"/Symbol", "/ZapfDingbats"}`.
- **Files modified:** `tools/probe_corpus.py`
- **Verification:** Both files' `symbolic_fonts` declarations now correctly detected; full-corpus prober run confirmed via re-execution.
- **Committed in:** `78c3be9`

### Known Issues (out of scope for this plan's executor — explicit prohibition on modifying `corpus/manifest.json`)

**2. [Discovered, not fixed] `corpus/manifest.json`'s `nasa_graphics_standards_manual.pdf` entry declares `subset_fonts` but the file has no subset-tagged or custom-embedded font anywhere**
- **Found during:** Task 1, running `check_manifest()` against the real public manifest — this is D-04's independent verifier doing exactly its designed job
- **Evidence:** Every font referenced in every page's `/Resources`, every Form XObject's nested `/Resources`, and the document's `/AcroForm /DR` is a Standard-14 base font (`Helvetica*`, `Times-*`) plus one embedded-but-unsubset-tagged `HiddenHorzOCR` CID font — none carry a `/BaseFont` matching the ISO 32000 6-uppercase-letter-plus-`+` subset-tag pattern, and none are otherwise custom-embedded under a subset name. Independently corroborated: Plan 01-02's own SUMMARY.md coverage table lists `subset_fonts` as "12 of 17 files" and does not name `nasa_graphics_standards_manual.pdf` among them, even though `corpus/manifest.json`'s entry for that file includes `"subset_fonts"` in its `categories` array — the manifest and its own author's narrative summary already disagreed before this plan touched anything.
- **Why not fixed here:** This plan's executor instructions explicitly prohibit modifying `corpus/manifest.json` ("already merged and validated by plans 01-02, 01-06, 01-04 and 01-05"). Weakening the prober's `subset_fonts` detection to force a false pass was rejected — that would defeat D-04's stated purpose (an independent check that never fires is worthless).
- **Effect on tests/CI:** `tests/test_probe_corpus.py` asserts `check_manifest()` against the real manifest returns exactly this one known error (`KNOWN_REAL_MANIFEST_ISSUES`), not `[]` — this is why `corpus-public`'s CI job (`tools/probe_corpus.py corpus/manifest.json corpus/public`) will currently exit 1 on `main`. **This is a real, pre-existing data bug this plan discovered but could not fix**, not a bug in the code this plan delivers.
- **Recommended fix (for a future plan/maintainer with permission to touch `corpus/manifest.json`):** remove `"subset_fonts"` from `nasa_graphics_standards_manual.pdf`'s `categories` array (the file still correctly and exclusively carries `vector_outlined_text`, and `subset_fonts` remains independently covered by 12 other public-tier files).

**Total deviations:** 1 auto-fixed (Rule 1, code bug in this plan's own new prober), 1 discovered-but-out-of-scope (a pre-existing Plan 01-02 data bug, explicitly not fixable under this plan's file-restriction instructions).

## CHECKPOINT REACHED

**Type:** human-action (Task 3, `gate="blocking"`)
**Plan:** 01-03
**Progress:** 2/3 tasks complete (Task 3's mechanical artifacts are built, tested, and committed; the checkpoint itself is the halt)

### Completed Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Independent structural prober (D-04) | `78c3be9` | tools/probe_corpus.py, tests/test_probe_corpus.py |
| 2 | Private-tier fetch, probed + validated once fetched (D-01/D-02/D-04) | `bc7bfd1` | tools/fetch_private_corpus.py, tests/test_fetch_private_corpus.py, corpus/private-manifest.json, .gitignore, corpus/README.md, .github/workflows/corpus.yml |
| 3 (mechanical part) | Gate G0 corpus-size checker + CI wiring | `205b177` | tools/check_corpus_size.py, tests/test_check_corpus_size.py, .github/workflows/corpus.yml |

### Current Task

**Task 3:** Gate G0 corpus-size checkpoint — halt until the combined corpus reaches 100 documents
**Status:** blocked (by design — this is the intended halt, not a failure)
**Blocked by:** Real invoices/contracts have not yet been collected into the private bucket; `corpus/private-manifest.json` is still `[]`. Combined count is 17 (public=17, private=0), 83 short of the 100-document floor.

### Checkpoint Details

`tools/check_corpus_size.py` exists, is tested, and is wired as a blocking `corpus-size-gate`
CI job on `main`/`release/*`. Running it now:

```
$ python tools/check_corpus_size.py corpus/manifest.json corpus/private-manifest.json
Gate G0 requires >= 100 combined documents; have 17 (public=17, private=0)
```

This next part cannot be completed by an automated agent. It requires the maintainer to:

1. Personally collect real invoices and contracts (per ENG-01/D-01 — no synthesized,
   generated, or fabricated documents).
2. Upload them to the private bucket `tools/fetch_private_corpus.py` reads from (set
   `PRIVATE_CORPUS_BASE_URL` / `PRIVATE_CORPUS_TOKEN` as CI secrets — see
   `corpus/README.md`'s private-tier section for the exact contract).
3. Add each file's `filename`, `sha256`, `categories`, and `weight_class` to
   `corpus/private-manifest.json`.
4. Re-run `python tools/check_corpus_size.py corpus/manifest.json corpus/private-manifest.json`
   until it reports a combined count >= 100 and exits 0.

Separately, `corpus/manifest.json`'s one pre-existing `subset_fonts` mislabel on
`nasa_graphics_standards_manual.pdf` (see Known Issues above) should be corrected by whoever
next has permission to touch that file, so `corpus-public`'s CI job returns to green.

### Awaiting

The maintainer to populate the private tier (see above) and confirm a re-run of
`tools/check_corpus_size.py` exits 0, or to explicitly say "deferring Gate G0 sign-off" to let
phase execution continue past this checkpoint while leaving Gate G0 itself unsigned.

## User Setup Required

- **Private bucket credentials:** `PRIVATE_CORPUS_BASE_URL` and `PRIVATE_CORPUS_TOKEN` must be
  set as CI secrets (GitHub Actions repo/environment secrets) before `corpus-private-gate` can
  do anything beyond skip cleanly. No bucket has been provisioned or verified as part of this
  plan — `tools/fetch_private_corpus.py` was tested exclusively against a local mock server.
- **Private-tier document collection:** entirely the maintainer's responsibility per Task 3's
  checkpoint (see above) — cannot be automated, per ENG-01/D-01.

## Next Phase Readiness

- `tools/probe_corpus.py` and `harness/run_corpus_harness.py` (reused unmodified) are both
  independently parameterized and proven to work against an arbitrary manifest+corpus-dir pair
  — the private tier's CI wiring (`corpus-private-gate`) will function correctly the moment
  real credentials and documents exist, with no further code changes needed.
- `tools/check_corpus_size.py` is the single, mechanical source of truth for whether Gate G0's
  volume criterion is met — any future plan or maintainer session can run it directly.
- **Blocker for Gate G0 sign-off:** private tier is unpopulated (0 documents; combined count 17
  of the required 100). This plan's Task 3 checkpoint is the explicit, intended stopping point.
- **Non-blocking known issue:** `corpus/manifest.json`'s `nasa_graphics_standards_manual.pdf`
  `subset_fonts` mislabel (see Known Issues) — does not block Plans 01-04/05/06 or the private
  tier, but does make `corpus-public`'s CI job red until corrected by a plan with permission to
  edit `corpus/manifest.json`.

---
*Phase: 01-conformance-harness-engine-spike*
*Completed (through Task 3's mechanical build; checkpoint pending): 2026-08-12*

## Self-Check: PASSED

All 8 created artifact paths verified present on disk (`tools/probe_corpus.py`,
`tests/test_probe_corpus.py`, `tools/fetch_private_corpus.py`,
`tests/test_fetch_private_corpus.py`, `corpus/private-manifest.json`,
`tools/check_corpus_size.py`, `tests/test_check_corpus_size.py`,
`.github/workflows/corpus.yml`); all 3 task commits (`78c3be9`, `bc7bfd1`, `205b177`) verified
present in `git log --oneline --all`.
