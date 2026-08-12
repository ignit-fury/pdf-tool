---
phase: 01-conformance-harness-engine-spike
plan: 05
subsystem: engine-spike
tags: [playa-pdf, decode-probe, eng-04, risk-3, throwaway-spike]

# Dependency graph
requires: ["01-02"]
provides:
  - "spike/playa_decode_probe.py - the sole module in the repo importing playa/pdfminer.six; per-glyph decode probe (cid, text, bbox, origin, displacement, font) with a --engine playa|pdfminer flag and a per-file wall-clock timeout"
  - "PLAYA-DECISION.md - recorded GO verdict on playa-pdf, with per-file evidence table"
affects: ["02-text-model"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "playa-pdf decode calls confined to exactly one module (spike/playa_decode_probe.py), no abstraction layer -- the module boundary itself is the swap mechanism per 01-CONTEXT.md"
    - "In-process wall-clock timeout via signal.alarm/SIGALRM for a per-file DoS cap on untrusted-shaped PDF input, as a lighter-weight sibling to harness/run_corpus_harness.py's subprocess.run(timeout=...) pattern (no subprocess here since playa/pdfminer run in-process)"

key-files:
  created:
    - spike/playa_decode_probe.py
    - tests/test_playa_decode_probe.py
    - .planning/phases/01-conformance-harness-engine-spike/PLAYA-DECISION.md
  modified: []

key-decisions:
  - "playa-pdf is GO -- no swap to pdfminer.six. Validated against 4 required real documents (irs_form_1040, irs_1040_instructions, irs_form_w9, irs_form_w4; 9k-34k glyphs each, zero exceptions) plus 3 corroborating documents including full CJK Type0/CID-keyed-CFF text (irs_publication_17, wikipedia_zh_monthly_magazine). pyproject.toml unchanged; pdfminer.six was never installed since the fallback path was never needed."
  - "Selection is algorithmic (select_fixtures greedily covers REQUIRED_CATEGORIES = {type0_identity_h, subset_fonts} from corpus/manifest.json, then fills to --min-files), not hand-picked -- reproducible and re-runnable against a changed manifest."
  - "Per-file page sampling (MAX_PAGES_PER_FILE=5) instead of full-document decode -- this spike answers a yes/no decode-correctness question, not corpus-wide validation (that's harness/run_corpus_harness.py's job, already merged from plan 01-04)."

requirements-completed: [ENG-04]

# Metrics
duration: ~35min
completed: 2026-08-12
---

# Phase 1 Plan 5: playa-pdf Decode Spike Summary

**Settled ENG-04 / Risk #3 empirically: playa-pdf decodes per-glyph CID, geometry, and advance data correctly on real Type1-subset, Type0/Identity-H CIDFontType2, and Type0 CID-keyed-CFF (including live CJK) documents, confined to one throwaway module, with a recorded GO verdict — no swap to pdfminer.six.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-08-12
- **Tasks:** 2 completed
- **Files modified:** 3 (`spike/playa_decode_probe.py`, `tests/test_playa_decode_probe.py`, `PLAYA-DECISION.md`)

## Accomplishments

- `spike/playa_decode_probe.py` written as the only module in the repository importing
  `playa` (verified via `grep -rl "^import playa\|^from playa\|^import pdfminer\|^from
  pdfminer" --include="*.py" . | grep -v spike/playa_decode_probe.py` returning empty) —
  no interface/adapter/base-class built around it, per 01-CONTEXT.md's discretion note that
  the single module boundary *is* the mechanism
- Deterministic fixture selection (`select_fixtures`) reads `corpus/manifest.json` and
  guarantees coverage of both required categories (`type0_identity_h`, `subset_fonts`)
  before filling to `--min-files`; selected `irs_form_1040.pdf`, `irs_1040_instructions.pdf`,
  `irs_form_w9.pdf`, `irs_form_w4.pdf` on this manifest
- Per-glyph decode via playa's `Page.glyphs` (`GlyphObject`) extracts exactly the fields
  research/ARCHITECTURE.md's run record needs: `cid`, `text`, `bbox`, `origin`,
  `displacement` (advance), `font` (with `basefont`/`cidcoding`)
- Ran `python spike/playa_decode_probe.py --manifest corpus/manifest.json --min-files 4`:
  exit 0, all 4 fixtures decoded with 9,387-34,400 glyphs each, zero exceptions, zero
  timeouts (30s cap per file)
- Spot-checked Type0/Identity-H CID resolution against a known visible string:
  `irs_1040_instructions.pdf`'s decoded page-1 text reads `'...Page 1 of 126...'`, matching
  the document's actual 126-page count; the `P` glyph resolves to a single stable
  `CIDFont(cidcoding='Adobe-Identity')` CID, not garbage
- Went beyond the required minimum to stress the highest-risk case explicitly: CID-keyed CFF
  CJK decode on `irs_publication_17.pdf` (`NotoSansCJKjp-Regular`, `CIDFontType0C`) resolved
  to correct Chinese/Korean characters (`中`, `文`, `한`, `국`, `어`), and
  `wikipedia_zh_monthly_magazine.pdf` decoded a full Chinese title
  (`维基人 2013年04月13日 第5期`) correctly — the exact scenario research flagged as
  the reason playa is the least-corroborated critical-path dependency
- `pdfminer.six` fallback path (`_decode_with_pdfminer`, `--engine pdfminer`) exists in the
  same module per the plan's "no abstraction layer, two code paths in one file" instruction,
  but was never exercised for a real comparison — no selected or spot-checked file produced
  zero glyphs or an exception under playa
- `PLAYA-DECISION.md` records the GO verdict, cites the exact evidence table (filenames,
  glyph counts, categories, sane/not-sane), and states explicitly that `pyproject.toml` is
  unchanged and `pdfminer.six` was never installed
- `tests/test_playa_decode_probe.py`: 3 tests, all passing — fixture selection covers
  required categories, all 4 selected fixtures decode with `glyph_count > 0` and no
  unhandled exception, and the `looks_sane` heuristic correctly rejects empty/garbage text

## Task Commits

Each task was committed atomically:

1. **Task 1: Confine playa-pdf decode calls to one module; validate against >=4 real documents** - `c1b3781` (feat)
2. **Task 2: Record the playa-pdf vs pdfminer.six decision** - `8ddb4bb` (docs)

## Deviations from Plan

None - plan executed exactly as written. Task 2's conditional pyproject.toml update did not
apply (decision was GO, not SWAP), which the plan itself anticipates ("if pdfminer.six is
chosen instead...").

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required. `playa-pdf==1.1.0` is already an
existing runtime dependency (pyproject.toml, pre-dating this plan); nothing new to install.

## Next Phase Readiness

- ENG-04 and Risk #3 are retired: the playa-pdf bet is settled empirically, confined to one
  module, decision recorded in this phase, not deferred.
- Phase 2 (Text Model) can build the content-stream interpreter's read side directly on
  `playa-pdf`'s `Page.glyphs` API — `PLAYA-DECISION.md` documents which fields are available
  and cites the evidence.
- Noted for Phase 2, not a blocker: `irs_form_w4.pdf`'s `AdobePiStd` symbolic dingbat
  `CIDFont` resource is declared but unused by any glyph in the 5-page sample this probe
  reads — worth a targeted re-check if/when symbolic-font editing is implemented
  (PITFALLS.md Pitfall 2: "Do not attempt to write new codes into a symbolic font. Ever.").
- No blockers for the next plan in this phase.

---
*Phase: 01-conformance-harness-engine-spike*
*Completed: 2026-08-12*

## Self-Check: PASSED

All 3 created artifact paths verified present on disk (`spike/playa_decode_probe.py`,
`tests/test_playa_decode_probe.py`, `PLAYA-DECISION.md`); both task commits (`c1b3781`,
`8ddb4bb`) verified present in `git log --oneline --all`.
