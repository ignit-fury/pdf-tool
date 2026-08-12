---
phase: 01-conformance-harness-engine-spike
plan: 04
subsystem: testing
tags: [pypdfium2, poppler, mutool, mupdf, qpdf, pdfcpu, pillow, differential-testing, docker, github-actions]

# Dependency graph
requires:
  - phase: 01-01
    provides: pinned pyproject.toml/uv.lock, AGPL license gate
  - phase: 01-02
    provides: corpus/public/ (17 files), corpus/manifest.json
provides:
  - "harness/render_diff.py - render_pdfium/render_poppler/render_mupdf/render_all(pdf_path, page_index, output_dir) -> list[Path]"
  - "harness/masked_diff.py - masked_pixel_diff(png_a, png_b, mask=None) -> int, exact-equality primitive"
  - "harness/run_corpus_harness.py - check_file(pdf_path) -> HarnessResult, main(manifest_path, corpus_dir), CLI with two required positional args"
  - "Dockerfile.ci - pinned Debian trixie + poppler-utils/mupdf-tools/qpdf/pdfcpu CI image"
  - ".github/workflows/harness.yml - builds Dockerfile.ci, runs the harness against corpus/manifest.json + corpus/public on every push"
affects: [01-03, 02-text-model, 03-rewrite-engine-font-pipeline]

# Tech tracking
tech-stack:
  added: [poppler-utils (CI-only subprocess), mupdf-tools (CI-only subprocess, AGPL), qpdf CLI, pdfcpu CLI]
  patterns:
    - "Cross-engine pixel comparison is Gaussian-blur + per-channel-delta-tolerant, not literal masked_pixel_diff()==0 - independent rasterizers never produce bit-exact renders of the same unedited page (measured 0%-98% raw diff, all antialiasing noise); tolerance is pinned and documented with the measured evidence"
    - "masked_pixel_diff() stays the exact zero-tolerance primitive (tested), reserved for same-engine before/after preservation checks in later phases where true bit-identity is the correct expectation"
    - "All three renderers forced to rasterize the CropBox, not the MediaBox, so a page where the two boxes differ doesn't produce a false cross-engine diff"
    - "Structural validators run in permissive-but-real modes (pdfcpu --mode relaxed, qpdf --warning-exit-0) chosen after measuring that strict modes fail on common non-corruption spec deviations in real government PDFs"
    - "Every render/subprocess call in the harness is exception-wrapped and recorded as a per-check failure, never propagated - a malformed/encrypted corpus fixture is expected data, not a crash"

key-files:
  created:
    - harness/render_diff.py
    - harness/masked_diff.py
    - harness/run_corpus_harness.py
    - tests/test_masked_diff.py
    - Dockerfile.ci
    - .github/workflows/harness.yml
  modified: []

key-decisions:
  - "pdf.js.comparator rejected (browser/WASM-only harness, no headless CLI or scriptable diff output) - built the three-engine rasterizer directly against native CLI tools + pypdfium2 instead"
  - "Cross-engine tolerance pinned at blur=3px, per-channel delta=20/255, pass threshold=8% of page pixels - derived empirically by rendering every page of the full public corpus (2476 pages) and measuring the real antialiasing-only diff floor/ceiling, not guessed"
  - "pdfcpu validate runs --mode relaxed (plan said --mode strict, and that literal CLI flag doesn't even exist in pdfcpu - it's -m/--mode) - strict fails 13/17 real-world public-tier documents on non-corruption spec deviations (XMP date ordering, Outline /Count bookkeeping); relaxed still catches the deliberately malformed Isartor fixture"
  - "qpdf --check runs with --warning-exit-0 (qpdf's own sanctioned flag) - several real IRS PDFs have harmless linearization hint-table warnings (exit 3), not structural corruption; only exit 2 (real errors) fails the check"
  - "render_diff.py forces -cropbox/-b CropBox on pdftoppm/mutool to match pypdfium2's CropBox-default rendering - without this, nasa_graphics_standards_manual.pdf's CropBox != MediaBox produced a ~98% false cross-engine diff that had nothing to do with content"
  - "MAX_PAGES_PER_FILE=20 caps per-file page sampling - far_federal_acquisition_regulation.pdf alone is 2026 pages of near-identical body text; every page of 14/17 files is still checked in full, only 4 large files are sampled, cutting total CI pages checked from 2476 to 162"
  - "malformed/encrypted corpus handling: every render/validator call is wrapped so a tool that fails on a fixture is a recorded per-check failure, not an unhandled exception aborting the run - documented as a deliberate policy per phase_critical_constraint #8"

patterns-established:
  - "harness/*.py use sibling-module imports (not `harness.foo` package imports) since the plan's own CLI contract invokes them as `python harness/script.py`, which puts harness/ on sys.path[0] rather than the repo root"

requirements-completed: [ENG-02, ENG-03]

# Metrics
duration: ~75min
completed: 2026-08-12
---

# Phase 1 Plan 4: Three-Engine Differential Rasterizer + Structural Validation Summary

**Built a pdfium/Poppler/MuPDF differential rasterizer with an empirically-derived (blur + per-channel-delta) tolerance instead of a literal pixel-identical assertion — three independent rasterizers never produce bit-exact renders of the same unedited page, proven by rendering all 2476 pages of the public corpus and measuring the real antialiasing noise floor before picking a threshold.**

## Performance

- **Duration:** ~75 min
- **Completed:** 2026-08-12
- **Tasks:** 2 completed (Task 2 is TDD: RED commit, GREEN commit)
- **Files modified:** 6 created (harness/render_diff.py, harness/masked_diff.py, harness/run_corpus_harness.py, tests/test_masked_diff.py, Dockerfile.ci, .github/workflows/harness.yml)

## Accomplishments

- Evaluated `pdf.js.comparator`: rejected as browser/WASM-only with no headless CLI (recorded as a code comment in `render_diff.py` per the plan's read-first requirement); built the three-engine rasterizer directly instead
- `harness/render_diff.py`: `render_pdfium()` (in-process pypdfium2), `render_poppler()`/`render_mupdf()` (subprocess, CI/dev-only), `render_all()` entry point — verified `grep -c mupdf pyproject.toml` returns 0, MuPDF never a runtime dependency
- Discovered and fixed a real cross-engine rendering divergence: pdfium rasterizes a page's CropBox by default, pdftoppm/mutool rasterize the MediaBox — on `nasa_graphics_standards_manual.pdf` (CropBox != MediaBox) this alone produced a ~98% pixel "difference" that had nothing to do with content. Fixed by forcing `-cropbox`/`-b CropBox` on both subprocess renderers.
- `harness/masked_diff.py`: `masked_pixel_diff()` implemented with Pillow's `ImageChops` (C-level, no per-pixel Python loop — a 150 DPI page is 1M+ pixels); TDD RED/GREEN proven (`tests/test_masked_diff.py` fails to import before the implementation exists, passes after)
- Measured the real cross-engine antialiasing noise floor before picking a tolerance: exact-equality diff across the whole corpus ranges 0%-98% (pure antialiasing/gamma/hinting noise); a 3px Gaussian blur + 20/255 per-channel delta tolerance collapses that to <5% for text pages and up to ~7.2% for `nasa_graphics_standards_manual.pdf`'s vector-art-heavy pages — `PASS_THRESHOLD_PERCENT` pinned at 8.0% with this evidence documented in a code comment
- `harness/run_corpus_harness.py`: `check_file(pdf_path) -> HarnessResult`, `main(manifest_path, corpus_dir)` CLI with two required positional args (both verified independent — ran against a scratch empty manifest/dir, exits 0 with zero files)
- Full public corpus run: **17/17 files pass** (162 of 2476 total pages checked under the `MAX_PAGES_PER_FILE=20` cap), cross-engine tolerant diff + `qpdf --check --warning-exit-0` + `pdfcpu validate --mode relaxed`, ~3.5 min wall time
- `Dockerfile.ci`: Debian trixie base pinned by digest, `poppler-utils`/`mupdf-tools`/`qpdf` pinned to exact trixie apt versions (verified via the Debian Sources API), `pdfcpu` pinned to a GitHub release tag, `qpdf`/`pdfcpu` also used for structural validation
- `.github/workflows/harness.yml` builds `Dockerfile.ci` and runs `harness/run_corpus_harness.py corpus/manifest.json corpus/public` inside it on every push/PR

## Task Commits

Each task was committed atomically:

1. **Task 1: Evaluate pdf.js.comparator; wire three-engine rasterization** - `ce8b400` (feat)
2. **Task 2 RED: failing test for masked_pixel_diff** - `3d7f0f5` (test)
3. **Task 2 GREEN: implement masked_pixel_diff** - `fc9656d` (feat)
4. **Task 2: corpus harness CLI + CI workflow + render_diff.py CropBox fix** - `6350108` (feat)

## Files Created/Modified

- `harness/render_diff.py` - Three-engine rasterization; `render_all()` entry point; CropBox alignment across all three engines
- `harness/masked_diff.py` - Exact-equality pixel-diff primitive, tested to discriminate a single changed pixel
- `harness/run_corpus_harness.py` - `check_file()`/`main()` CLI; empirically-tolerant cross-engine comparison; qpdf/pdfcpu structural checks; explicit malformed/encrypted handling
- `tests/test_masked_diff.py` - RED/GREEN proof, plus a masking test
- `Dockerfile.ci` - Pinned CI-only image (poppler/mupdf/qpdf/pdfcpu)
- `.github/workflows/harness.yml` - Builds and runs the harness on every push

## Decisions Made

See `key-decisions` in frontmatter — the two biggest ones:

1. **Literal pixel-identical cross-engine comparison is not achievable and was not attempted as written.** The plan's own contingency clause ("only fall back to a small pinned nonzero threshold if pinned-version renders are proven to never match bit-exact") was triggered by direct measurement: rendering all 2476 pages of the public corpus through all three engines showed 0%-98% raw pixel disagreement on an *unedited* identity transform, entirely from antialiasing. A tolerant (blur + per-channel-delta) comparison was built and its threshold pinned from the measured evidence, not guessed.
2. **Structural validator invocation deviates from the plan's literal CLI flags** (`pdfcpu validate -mode strict` isn't valid pdfcpu syntax at all; and even with correct syntax, strict mode fails 13/17 real documents on non-corruption issues). Both `qpdf --check --warning-exit-0` and `pdfcpu validate --mode relaxed` were chosen after measuring their behavior across the whole corpus, and both still correctly flag the deliberately malformed Isartor fixture in at least one tool (pdfcpu; qpdf's `--check` does not flag it at all — an expected, documented Layer 1 disagreement, not a bug).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] pdfium/Poppler/MuPDF CropBox vs MediaBox mismatch produced a false ~98% diff**
- **Found during:** Task 2, measuring cross-engine tolerance against the full corpus
- **Issue:** `pypdfium2` rasterizes a page's `/CropBox` by default; `pdftoppm`/`mutool draw` rasterize `/MediaBox` by default. `nasa_graphics_standards_manual.pdf` has a CropBox (573.48x791.76pt) meaningfully smaller than its MediaBox (708.48x863.76pt) — at 150 DPI this produced genuinely different pixel dimensions per engine (1195x1650 vs 1476x1800), which read as a ~98% pixel difference that had nothing to do with rendering fidelity.
- **Fix:** Added `-cropbox` to the `pdftoppm` invocation and `-b CropBox` to the `mutool draw` invocation in `harness/render_diff.py`, forcing all three engines to rasterize the same box.
- **Files modified:** `harness/render_diff.py`
- **Verification:** Re-ran the full corpus; `nasa_graphics_standards_manual.pdf`'s cross-engine diff dropped from ~98% to ≤7.2% (in line with every other vector-heavy page), and file dimensions now match to within the ±1px rounding difference described below.
- **Committed in:** `6350108` (folded into the Task 2 commit since it was discovered while building Task 2's comparison logic, even though the file was originally written in Task 1)

**2. [Rule 1 - Bug] Literal exact-equality cross-engine "pixel-identical" assertion is empirically false, even on an identity transform**
- **Found during:** Task 2, first full-corpus run
- **Issue:** The plan's `must_haves.truths` states the three engines' unedited-corpus renders are "pixel-identical" to each other. Direct measurement across all 2476 corpus pages showed exact-equality diffs from 0% (near-blank fixtures) to 98% (dense real pages), entirely from independent antialiasing/gamma/subpixel-hinting implementations — not content differences. The plan itself anticipated this exact possibility with a documented contingency ("only fall back to a small pinned nonzero threshold if pinned-version renders are proven to never match bit-exact... state the exact threshold and why").
- **Fix:** Implemented a tolerant comparison (3px Gaussian blur + 20/255 per-channel delta before counting a pixel as "different"), pinned `PASS_THRESHOLD_PERCENT=8.0` from the measured worst case (7.2%, on vector-art-heavy pages), documented at length in `run_corpus_harness.py`'s module docstring. `masked_pixel_diff()` itself is untouched — it remains the exact, zero-tolerance, tested primitive, reserved for a future same-engine before/after preservation check (Phase 2/3 Layer 3) where true bit-identity is the correct expectation.
- **Files modified:** `harness/run_corpus_harness.py`
- **Verification:** Full public corpus (17 files, 162 pages under the sampling cap) passes 17/17 at the pinned threshold.
- **Committed in:** `6350108`

**3. [Rule 1 - Bug] `pdfcpu validate -mode strict` (plan's literal text) is invalid CLI syntax, and strict mode fails most of the real corpus**
- **Found during:** Task 2
- **Issue:** pdfcpu's flag is `-m`/`--mode`, not `-mode` (single dash, unrecognized by pdfcpu — a distinct bug from the mode choice itself). Separately, even with correct syntax, `--mode strict` failed 13 of 17 public-tier files on non-corruption spec deviations (XMP metadata date-field ordering, AcroForm `/FirstChar` bookkeeping, Outline `/Count` mismatches) unrelated to structural integrity.
- **Fix:** Used `pdfcpu validate --mode relaxed` (pdfcpu's own documented "like strict but doesn't complain about common spec violations"). Verified relaxed mode still correctly flags the deliberately malformed Isartor broken-trailer fixture.
- **Files modified:** `harness/run_corpus_harness.py`
- **Verification:** Full corpus run: all 17 files pass pdfcpu relaxed validation; the malformed fixture is confirmed independently caught by pdfcpu relaxed mode.
- **Committed in:** `6350108`

**4. [Rule 1 - Bug] `qpdf --check` flagged harmless linearization warnings as failures**
- **Found during:** Task 2, full-corpus run
- **Issue:** Three real IRS-generated PDFs have linearization hint-table bookkeeping mismatches (qpdf exit code 3, "warnings detected") — not structural corruption. `qpdf --check` without `--warning-exit-0` treats any nonzero exit as a failure.
- **Fix:** Added `--warning-exit-0` (qpdf's own sanctioned flag for exactly this case) so only exit 2 (real errors) fails the check.
- **Files modified:** `harness/run_corpus_harness.py`
- **Verification:** Full corpus run: qpdf check passes on all 17 files; would still fail on a genuine structural error (exit 2), which `--warning-exit-0` does not suppress.
- **Committed in:** `6350108`

---

**Total deviations:** 4 auto-fixed (all Rule 1 — bugs in the plan's literal assertion/CLI text discovered by direct measurement against the real corpus, not shortcuts).
**Impact on plan:** All four were required to make the harness's pass/fail signal meaningful rather than either always-red (literal pixel-identical, literal `pdfcpu -mode strict`) or silently wrong (unhandled CropBox mismatch, unhandled qpdf warning-exit). No scope creep — same three files the plan named, same two validators, same CLI contract.

## Issues Encountered

- `pdftoppm`/`mutool`/`qpdf`/`pdfcpu` are not present in this execution sandbox by default; installed locally via Homebrew (`poppler` 26.08.0, `qpdf` 12.4.0 — exact version match to `research/STACK.md`'s pin — `mupdf-tools` 1.28.2, `pdfcpu` 0.15.0) purely to develop and verify the harness end-to-end. `Dockerfile.ci`'s pinned versions were independently sourced from the Debian trixie package archive (via the Debian Sources API) and the pdfcpu GitHub release, not copied from the local Homebrew versions, since Homebrew (macOS/ARM) and the Debian-based CI image track different package streams.
- No `docker` binary available in this sandbox to build/run `Dockerfile.ci` directly; its correctness (base image digest, exact apt package versions, pdfcpu release tarball layout) was verified via direct queries against Docker Hub's registry API, the Debian Sources API, and the actual pdfcpu release tarball's file listing, rather than an actual `docker build`.

## User Setup Required

None — no external service configuration required. CI (`.github/workflows/harness.yml`) needs no secrets; `docker build`/`docker run` on `ubuntu-latest` GitHub-hosted runners come with Docker preinstalled.

## Next Phase Readiness

- `harness/run_corpus_harness.py`'s `main(manifest_path, corpus_dir)` signature is independently parameterized and proven against a scratch empty manifest/dir pair — Plan 01-03 can invoke it unmodified against `corpus/private-manifest.json` + `corpus/private` once fetched.
- `render_all(pdf_path, page_index, output_dir) -> list[Path]` is available by name for any future plan needing three-engine rasterization (e.g., Phase 2/3's same-engine before/after preservation diff, which should reuse `masked_pixel_diff()` directly at its exact, zero-tolerance default — no blur/threshold needed there, since it's the same rasterizer rendering the same unedited pixels twice).
- The cross-engine tolerance constants (`BLUR_RADIUS`, `CHANNEL_TOLERANCE`, `PASS_THRESHOLD_PERCENT`) are pinned and documented; if the private tier (Plan 01-03) introduces a file whose legitimate content triggers a higher genuine diff (e.g., an even more vector-art-dense scan), the threshold may need revisiting — the code comment states the exact measured evidence so that revision has a baseline to compare against.
- No blockers for Plan 01-03.

---
*Phase: 01-conformance-harness-engine-spike*
*Completed: 2026-08-12*

## Self-Check: PASSED

All 7 created artifact paths verified present on disk (`harness/render_diff.py`,
`harness/masked_diff.py`, `harness/run_corpus_harness.py`, `tests/test_masked_diff.py`,
`Dockerfile.ci`, `.github/workflows/harness.yml`, this summary); all 4 task commits
(`ce8b400`, `3d7f0f5`, `fc9656d`, `6350108`) verified present in `git log --oneline --all`.
