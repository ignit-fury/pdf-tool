---
status: resolved
trigger: "govdocs1_010_010118.pdf page 0 shorter edit preview succeeds but apply refuses stale_run_index"
created: 2026-10-22
updated: 2026-10-22
---

## Current Focus
hypothesis: independent empty-showing instructions incorrectly consume glyph-derived rewrite ordinals
test: tiny one-part fixture maps Alpha to index 3 (empty Tj) instead of index 5, and cannot correlate
expecting: counting only instructions with at least one nonempty string targets index 5 and preserves every glyphless instruction
next_action: none; final corpus edit audit records remaining named structural refusals separately
reasoning_checkpoint:
  hypothesis: rewrite counts all showing keywords while reader ordinals exclude operators with no nonempty string, so empty instructions consume the target ordinal
  confirming_evidence:
    - synthetic fixture actual offsets include only Alpha and Bravo, while pikepdf retains seven glyphless showing instructions
    - touched_instruction_indices returns empty Tj index 3 instead of independently known Alpha index 5
  falsification_test: filtering ordinal counts still targets index 3 or changes any numeric-only TJ instruction or following glyph origin
  fix_rationale: match reader's nonempty-string ordinal domain while retaining all instructions in the splice input and output
  blind_spots: malformed operand shapes remain refused by existing safeguards; no attempt to make zero-decoded-glyph nonempty text editable

## Symptoms
expected: a resolvable shorter edit applies while preserving all other instructions and positions
actual: page 0 shorter edit previews resolve but apply refuses stale_run_index
errors: stale_run_index
reproduction: first editable candidates on corpus/public/govdocs1_010_010118.pdf page 0
started: existing corpus failure

## Eliminated
- hypothesis: empty text operators cause stale_run_index in govdocs1_010_010118.pdf page 0
  evidence: first candidate part has zero empty/numeric-only showing operators; 38 glyph-derived offsets exceed 36 real operators
  timestamp: 2026-10-22

## Evidence
- timestamp: 2026-10-22
  checked: engine/rewrite.py touched_instruction_indices and _correlate
  found: both count every text-showing keyword, whereas reader gate omits all-empty strings and numeric-only TJ arrays
  implication: glyphless showing instructions may invalidate the bridge even for a current index
- timestamp: 2026-10-22
  checked: actual fixture part 1 and clustering provenance
  found: preview succeeds, apply refuses stale_run_index; 247 runs on page 0 inherit a foreign part anchor; StreamPath grouping ignores record.stream_id
  implication: clustering is the actual fixture root cause, independent of the empty-operator bridge bug
- timestamp: 2026-10-22
  checked: three new regressions before production changes
  found: empty-showing bridge targets index 3 instead of real index 5; tiny multi-part and actual corpus anchor assertions both fail
  implication: both defects are directly reproducible and independently testable
- timestamp: 2026-10-22
  checked: tiny multi-part and actual fixture after cluster grouping fix only
  found: both tests pass, every glyph anchor agrees with its part, shorter preview and apply succeed, PDFium finds replacement, source hash unchanged
  implication: complete physical stream grouping resolves the concrete corpus failure independently of empty-operator handling
- timestamp: 2026-10-22
  checked: both production fixes and adjacent regression suites
  found: new regressions 3 passed; rewrite/clustering/correlation/quote/recipe quick checks 99 passed, 2 corpus deselected; strict mypy clean
  implication: both defects corrected with stale count guard retained; integrated full suite is next

## Resolution
root_cause: cluster groups omitted physical part index, assigning 247 actual fixture glyphs foreign-part run anchors; independently rewrite counted glyphless showing instructions against glyph-derived ordinals
fix: group clusters by (StreamPath, stream_id); count only nonempty-string showing instructions in both touched indices and the unchanged count guard while preserving every instruction
verification: 3 regressions and 143 integrated fix tests passed; strict typing clean; historical five-page corpus correlation sweep passed after pinning the measured reduction from 89 to 4 known failures, with no new failures
files_changed: [engine/clusterer.py, engine/rewrite.py, tests/test_empty_showing_correlation.py]

The initial full suite passed 485 tests and found four sandbox-only HTTP bind
failures plus the now-smaller historical correlation baseline. HTTP tests passed
outside the sandbox; the full correlation sweep passed in 117 seconds with the
four measured remaining historical-probe failures pinned exactly. The read-critical
pipeline files match every file stage of the complete 217-document read audit.
