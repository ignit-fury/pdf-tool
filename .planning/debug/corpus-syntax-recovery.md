---
status: resolved
trigger: "govdocs1_011_011089.pdf page 0 RunIndex raises PDFSyntaxError; diagnose and fix without partial-page success"
created: 2026-10-22
updated: 2026-10-22
---

## Current Focus
hypothesis: malformed inline-image termination raises PDFSyntaxError, which the worker fails to map to PDF_INVALID
test: tiny malformed-image and real corpus worker tests fail with WORKER_FAILED; whitespace-delimited control succeeds
expecting: catching only PDFSyntaxError returns PDF_INVALID without any partial runs
next_action: none for error routing; filter-aware recovery of malformed inline images remains unsupported
reasoning_checkpoint:
  hypothesis: binary inline-image bytes immediately precede EI; PLAYA loses the image boundary and raises PDFSyntaxError, which bypasses named input-error routing
  confirming_evidence:
    - all 14 inline-image EI tokens in the fixture lack preceding whitespace; none match the parser delimiter regex
    - tiny equivalent malformed-image test and real fixture test both return WORKER_FAILED, while the valid separator control succeeds
  falsification_test: if the malformed tests return something other than PDF_INVALID after translating PDFSyntaxError, another exception or transport failure is responsible
  fix_rationale: translate the precise parser exception into an existing fixed input refusal; never salvage operator fragments or advertise partial editability
  blind_spots: no attempt to recover invalid inline-image delimiters by filter-aware decoding; raw engine callers still receive the original parser refusal

## Symptoms
expected: faithful page parsing or named refusal for genuinely malformed content
actual: corpus page scan encounters an unexpected parser exception; worker maps it to WORKER_FAILED
errors: playa PDFSyntaxError in engine/playa_boundary.py operator_table
reproduction: RunIndex(corpus/public/govdocs1_011_011089.pdf).page(0)
started: existing known malformed inline-image corpus fixture

## Eliminated

## Evidence
- timestamp: 2026-10-22
  checked: server/worker.py main exception routing
  found: PDFSyntaxError is not among named PDF_INVALID exception handlers
  implication: malformed content is reported as a generic worker failure
- timestamp: 2026-10-22
  checked: actual fixture and installed PLAYA parser source
  found: 14 inline images, zero whitespace-delimited EI markers; permissive fallback does not cross binary newlines, leaving the first image open when the next BI arrives
  implication: recovery needs image-specific decoding and length validation; blanket token recovery would risk incorrect source offsets
- timestamp: 2026-10-22
  checked: tests/test_corpus_syntax_recovery.py before any production change
  found: two failures expecting PDF_INVALID but receiving WORKER_FAILED; valid inline-image control passes
  implication: tests reproduce both the concrete fixture and a tiny structurally equivalent input
- timestamp: 2026-10-22
  checked: tests/test_corpus_syntax_recovery.py after specific PDFSyntaxError translation
  found: all 3 tests pass; malformed tiny input and actual fixture return only PDF_INVALID, valid inline-image text survives, next healthy request works, fixture SHA-256 unchanged
  implication: input refusal is named and atomic, without parser salvage or partial editability
- timestamp: 2026-10-22
  checked: worker/walker/outside-content quick regressions and strict typing
  found: 26 passed, 4 corpus tests deselected, one existing pikepdf PageCopyWarning; mypy engine/playa_boundary.py server/worker.py succeeds
  implication: focused adjacent behavior remains intact; parent owns aggregate/full-suite verification

## Resolution
root_cause: malformed inline-image termination raises PDFSyntaxError outside the worker's named PDF_INVALID handlers
fix: re-export the precise parser exception through engine/playa_boundary.py and translate it to WorkerRefusal(PDF_INVALID) around worker execution
verification: RED tiny and actual fixture regressions observed; all 3 syntax tests GREEN; 26 adjacent quick tests passed; strict mypy clean for both modified modules
files_changed: [engine/playa_boundary.py, server/worker.py, tests/test_corpus_syntax_recovery.py]

## Parent-requested supporting change

Added core_font_widths(base_font_name) to the sole PLAYA boundary for the parent's
Standard 14 width fix. Returns a copy of the known Unicode width table or None.
Parent owns the consumer implementation and behavioral regression for that helper.

Aggregate verification: syntax regressions passed in the 143-test integrated fix
run. The complete read audit encounters this one raw parser exception out of 8,254
pages; the service returns PDF_INVALID and no partial page. This resolution fixes
error routing, not the malformed document's editability.
