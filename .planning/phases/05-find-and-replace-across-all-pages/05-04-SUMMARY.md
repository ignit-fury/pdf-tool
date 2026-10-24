---
phase: 05-find-and-replace-across-all-pages
plan: 04
status: completed-locally
subsystem: batch-transactions-and-fidelity
completed: 2026-10-24
requirements-completed: [FIND-01, FIND-02, FIND-03, FIND-04, FIND-05, FIND-06]
key-files:
  created: [client/src/find/replaceAll.mjs, client/src/find/replaceAll.test.mjs, tests/test_find_replace_recipe.py, .planning/phases/05-find-and-replace-across-all-pages/05-G4-RESULTS.md]
  modified: [client/src/App.jsx, tests/test_gate_g4.py]
---

# Phase 5 Plan 4 — Atomic Batch Apply and Local Proof

The completed find/review interface applies one exact accepted full recipe through
the ordinary edit endpoint and creates one undo entry. Actual browser checks cover
one-step undo, preserved earlier styles, font recovery, encrypted source-cache
recovery, signature acknowledgement, failed-page retry and stale responses.
Final applicable regression is resolved. Formal G4 literal contract-specimen
verification remains pending, separately from the delivered six FIND requirements.

## Delivered Behavior

- `applyReviewedReplacement` freezes the accepted recipe and validates exact current
  review, successful resolved rows, original addresses and signature acknowledgement
  before requesting apply. It checks freshness around asynchronous boundaries.
- App prepares the returned PDF before publishing viewer, download and recipe/history
  state. One shared mutation owner covers single edits, batch preview/apply and undo.
  Failed or stale requests/loaders cannot publish output or commit history.
- One successful batch commits the complete prior recipe once. Existing original-byte
  restore or server replay provides one Undo and Ctrl/Cmd+Z outside text inputs.
  Native input undo and previous text/font/color choices are preserved.
- Integration exercises the shipped Node matcher/builder and actual HTTP/worker path:
  per-instance exclusion, earlier text/bold/color, refusal filtering followed by an
  exact new successful preview, unknown-font replacement, and no output on fit/source
  failures. No separate bulk endpoint or persistent server history was introduced.

## Actual Evidence

Detailed dated observations and coverage limits: [05-G4-RESULTS.md](./05-G4-RESULTS.md).
Delegated records: [client transaction](./05-04-CLIENT-SUMMARY.md) and
[integration/G4](./05-04-GATE-SUMMARY.md).

- The immutable 40-page USGS technical proxy has 1,029 occurrences at 772 matching
  addresses. Sixty-nine shared addresses are locked before preview; the 703 proposed
  operations yield 28 additional named refusals. All 675 accepted operations remain.
- The complete G4 batch includes one occurrence opt-out and an earlier RGB operation.
  Real preview returns no PDF; apply returns one PDF with the same resolved report.
  Every requested text/anchor, opt-out, prior style and 25,972 untouched instructions
  is checked, as are independent PDFium page character deltas and unchanged source bytes.
- Combined integration/G4: 12 tests passed in 101.38s after the source-TJ fix. All
  120 same-engine comparisons have zero outside changes: 28 changed pages with unions
  of individual run masks, 12 unchanged pages without masks. Cross-engine checks pass.
- A logging-only defaultdict count error was corrected separately; six fast negative
  controls passed. No mask, rendering tolerance or cap was widened.
- Final engine `630ca28` strict complete-workload tests: 2 passed in 59.93s. Exact
  675-op previews use 18.302/18.319 CPU seconds, apply 18.467 CPU / 18.528 wall.
  Limits remain CPU20, default wall30, body1MiB and existing recipe/text ceilings.
- Chromium browser: one action applied 910 selected occurrences on 28 pages; counts
  became 119; one Cmd+Z restored original text/download, disabled Undo and 1,029 matches.
  The earlier styled canary journey separately proved previous bold/#994333 survived undo.
- Browser fault/delay routes exercised bounded 429 retry, honest 2/3-page incompleteness,
  manual Retry to completeness, pending-input invalidation and document close/reopen.
  Routes were removed and the document closed. Test artifacts are outside Git.
- Client suite 41 passed, production build passed, mypy 30 source files clean and
  canonical Unicode 15.1 data current. The final full Python run passed G4 again
  after `630ca28`: 556 passed, one obsolete refusal expectation failed, five release
  checks deselected in 1,406.65s. Test-only `1f9af02` verifies the now-safe corpus
  edit independently and adds a genuine late-layout refusal; all three corrected
  file tests pass in 2.41s. No production change followed the broad run.

## Review Corrections

All three blockers in [05-REVIEW.md](./05-REVIEW.md) are resolved:

1. Shared source operator addresses produced collapsed occurrence IDs and metadata.
   Distinct fragments now retain unique occurrence identity, exact navigation and
   visible locked ambiguity; independently safe replacements continue. RED `e200666`,
   fix `88702ec`.
2. Source TJ spacing made nominal font-width fitting overflow the original visible
   region while an absolutely positioned follower stayed fixed. Actual source geometry
   and written metrics now fit the visible envelope separately from terminal pen;
   fresh envelope guards cover both rewrite paths. RED `fd8484d`, fix `a49976a`.
3. Narrow dictionary spaces needed a budget based on actual serialized space widths.
   The real regression now selects bounded horizontal scaling and retains positive
   word gaps. RED `68b9911`, fix `630ca28`.

Final focused engine suite: 133 passed. The final full suite passed G4 after
that last spacing correction. The outdated layout-refusal expectation was
superseded by three corrected passing tests, including all 663 following glyphs,
independent text and pixel proof, plus actual corrupted-TJ atomic refusal.

## Commits and Deviations

Client implementation `f269a1e`, client summary `b973c42`, integration `456f3ca`,
full G4 RED `7491ec5`, completed gate/report fix `5321df6`; engine corrections and
strict proof are recorded in 05-01-SUMMARY. Root owns final evidence/metadata commits.

The all-page renderer gate intentionally ran before sign-off and found a real fit
bug; it was fixed rather than hidden by a broader mask. Final review found and fixed
one additional serialized-space edge. During browser checking, concurrent corpus
CPU load caused safe worker failures; the large successful browser batch was then
run without that competing test load, and the unchanged suite resumed afterward.
No concurrent high-throughput claim is made.

## Scope and Remaining Evidence

The source is a technical-document proof proxy, not a literal legal contract.
Literal contract-specimen coverage remains unproven. Structurally signed fixtures
exercise warnings/acknowledgement, not cryptographic signature validation.
macOS CPU/wall proof does not establish Linux memory/tmpfs/seccomp/container or
live CDN behavior. Those Phase 4 public-release checks remain open. No deployment
was attempted; the user explicitly deferred deployment.

Local implementation/tests/browser work is complete. Formal phase verification
retains the literal contract-specimen item in `05-HUMAN-UAT.md`; it is not silently
marked passed. Page operations, merge and exports remain future phases.

Final goal audit: `05-VERIFICATION.md` records **15/16 truths verified**, all six
FIND requirements satisfied locally, no remaining implementation blocker, and
`human_needed` only for the literal 40-page contract specimen. The global roadmap
gate remains open while all four implementation plans are delivered.
