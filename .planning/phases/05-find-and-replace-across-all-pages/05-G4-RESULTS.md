# Phase 5 local verification — 2026-10-24

**Decision: local functionality verified; literal contract-specimen G4 coverage remains pending. No deployment or public-release sign-off.**

The acceptance source is the unchanged 40-page USGS technical document
`corpus/public/govdocs1_013_013050.pdf`, SHA-256
`d0a3b06606378733a2ec96cfa01e3b12c111d13059d070e3e039b751347a4529`.
It is a public corpus proof proxy, not a literal legal contract. The one-page
browser fixture is the previously generated `Hello world` editing fixture.

## Full-document worker and fidelity evidence

The source has 3,000 runs and 1,029 case-insensitive `the` occurrences at 772
distinct matching addresses. The client detects 69 ambiguous shared addresses
before preview and leaves their matches visible and locked. Actual preview of
the remaining 703 proposals reports 28 additional refusals: six shared operators
and 22 missing font mappings. All 675 accepted run operations remain in the final
candidate; an individual occurrence is excluded in a run with another included
occurrence, and an earlier color edit is retained.

The first full renderer run exposed CR-02: nominal font advances did not account
for source TJ spacing. Some replacement glyphs escaped the source run while the
following absolutely positioned line remained fixed. Page 6 had 76 changed pixels
outside the original per-run masks. This was treated as a real defect; the masks
were not widened. The engine now separates visible-width fitting from terminal
pen preservation and checks the fresh replacement envelope.

Corrected full 675-operation performance proof: exact preview 18.802 CPU / 18.855
wall seconds; a fresh preview 18.871 CPU / 18.977 wall; apply 18.607 CPU / 18.695
wall. Existing CPU20, default wall30, memory, body and recipe limits are unchanged.
Preview returned no PDF, apply returned one complete PDF, reports agreed and
original bytes stayed unchanged.

The corrected combined integration/G4 run passed **12 tests in 101.38s**. The G4
portion took **95.467s**: 675 operations, 910 changing occurrences, one individual
opt-out, 97 refused addresses and 25,972 retained untouched instructions. All
**120 same-engine page pairs passed with zero outside-mask changes**: 28 changed
pages (84 individually masked pairs) and 12 unchanged pages (36 entirely unmasked
pairs). Cross-engine comparisons also passed. Preview took 18.893 CPU / 18.935 wall
seconds; apply took 18.520 CPU / 18.576 wall. The final page-count log was corrected
afterward to avoid a defaultdict lookup inflating the reported count; six fast
controls passed after that reporting-only change. No mask or threshold changed.

Subsequent review found CR-03: inter-word tightening still budgeted the font
program's space width when an original PDF dictionary defined a narrower space.
The real editable-original regression now uses the serialized space width and
bounded horizontal scaling, retaining positive word gaps. RED `68b9911`, fix
`630ca28`; 133 focused tests and strict typing passed. Final performance proof
against that follow-up passed two tests in 59.93s: exact preview 18.302 CPU /
18.388 wall, independent preview 18.319 / 18.396, apply 18.467 / 18.528. All 675
accepted operations remain. G4 passed again in the final full applicable suite
against `630ca28`.

G4 combines exact requested Unicode at every original glyph anchor, independent
PDFium full-page character deltas, untouched-instruction preservation, prior-style
readback, individual opt-out preservation and rendering. Every changed page uses
the union of its individual edited-run masks, with zero same-engine changed pixels
outside that union. Unchanged pages are compared without masks. Cross-engine
agreement uses the existing separately measured harness tolerance. Fast negative
controls reject an unrelated change between disjoint masks and an unchanged output
masquerading as a successful batch.

## Observed browser journeys

These are agent-operated local UI observations, not an assertion of user acceptance.
Current session: Chromium 155.0.0.0 on macOS, through the browser connector. Native
computer control was unavailable on 2026-10-24. Earlier native Firefox 157.0.1
observations on 2026-10-23 are distinguished below. All traffic used localhost.

| Check | Actual observation | Result |
|---|---|---|
| All-page search and options, native Firefox | 40/40 pages; `the`: 1,029 default, 851 whole-word, 723 whole-word plus case-sensitive | Passed |
| Native Firefox result navigation | Actual page/run highlighted at 115% and 200% zoom; browser Cmd+F remained native | Passed |
| Existing single edit before batch, Chromium | `Hello world` styled bold with color `#994333`, previewed and applied | Passed |
| Per-instance exclusion, Chromium | Three `l` occurrences in the same run; first excluded, two selected | Passed |
| Exact review | Before `Hello world`; After `Helio worid`; two changing matches, one exclusion | Passed |
| Review invalidation | Changing replacement removed the review and apply button; PDF text remained unchanged; restoring text required a new preview | Passed |
| One-action apply | One Replace action changed the two included instances; PDF text became `Helio worid`; query count recomputed to one | Passed |
| Native input undo | Typing in Replace with then Cmd+Z restored the field without undoing the PDF batch | Passed |
| One batch undo outside input | Tabbed to Preview button, Cmd+Z restored `Hello world` and three matches, retaining one earlier edited run | Passed |
| Prior style after batch undo | Inspector showed bold checked and color `#994333` after selecting the restored run | Passed |
| Undo button and original restore | A further Undo button restored Download original and disabled Undo | Passed |
| Stop and late-result scope | On the 126-page IRS public fixture, stopped at 10 pages; count remained 10 after later UI work | Passed |
| Honest partial zero | `No matches yet. Results cover 10 of 126 pages.`; preview disabled | Passed |
| Resume and document close | Resume reached 14 pages; closing during active indexing returned to welcome with no document/find panel | Passed |
| 320px layout | Document width 320px; panel and inputs 288px, right edge 304px; visible focus and no form overflow | Passed |
| 760px layout | Document width 760px; 728px panel; rail, viewer and inspector stacked in order | Passed |
| Empty replacement review | `world` → empty showed removal warnings and exact `Hello world` → `Hello` review | Passed |
| Actual fit refusal | Oversized replacement left the result visible and disabled with readable too-wide advice; PDF stayed `Hello world`, Undo stayed disabled | Passed |
| Unmapped font and recovery | Three-page test fixture: automatic preview retained all four matches and visibly refused the unmapped page-3 font; choosing Serif produced a successful four-match/two-page review | Passed |
| Font recovery apply and undo | One apply rendered page 1 as `a a a`, page 3 as `a`; one Undo restored page 3 `cat`, four matches and no remaining history | Passed |
| Unicode-password PDF | Entering `密碼` opened the existing security-helper fixture; batch `canary` → `a` previewed and applied as `Security a` | Passed |
| Encrypted source-cache loss | Restarted only the local review server; preview recovered source/password transparently, applied `Security a` → `Safe a`, and one Undo restored the prior `Security a` recipe | Passed |
| Signed batch | Structurally signed fixture warned; successful preview's apply stayed disabled before acknowledgement; acknowledgement enabled apply and output became `Security a` | Passed |
| Current 40-page apply after final fit fixes | All 40 pages indexed; 1,029 occurrences; one excluded; exact review accepted 910 occurrences on 28 pages, retaining 118 visible blocked occurrences; one apply succeeded and left 119 matches | Passed |
| Current 40-page single undo | Focused page button, Cmd+Z once: original text, original download, disabled Undo and 1,029 matches restored; query and replacement retained | Passed |
| Result pagination and focus | Exactly 50 rows; Next results showed 51–100 of 1,029 and focused its heading; Back to results restored the exact match-101 row button | Passed |
| Actual preview cancellation | Cancel preview removed review/apply; later completion could not publish readiness or change original output | Passed |
| 429 and failed-page retry | Temporary browser-only routes returned two 429s then actual 200 for page 2, and 503 for page 3; UI showed 2/3 pages and disabled preview. Removing routes and Retry fetched only page 3, reaching four matches across three pages | Passed |
| Delayed stale response | Delayed an actual server preview response eight seconds; changed replacement `a` → `b` while pending. After completion there was no review/apply, current field stayed `b`, PDF stayed `cat cat CAT` | Passed |
| Close/reopen during preview | With actual preview delayed, closed the three-page document and opened the one-page fixture. After the delayed request settled: `Hello world`, empty find/replacement fields, no review and no stale status | Passed |

The 320px screenshot is preserved at
`/private/tmp/pdf-tool-phase5-browser-20261024/phase5-mobile-320.png`.
Current Chromium session snapshots/console evidence and existing-test-helper PDF
copies are preserved outside Git under
`/private/tmp/pdf-tool-phase5-browser-20261024/chromium-session-1700/`.
Temporary browser failure/delay routes were removed; the document was closed.
Browser console observations include the existing favicon 404, PDF.js missing-font
warnings from the deliberate unknown-font fixture, expected password-required 422,
source-missing 409 during restart recovery, and the deliberately injected 429/503
responses. No application JavaScript exception was observed.

Two large preview attempts during simultaneous corpus CPU load returned
`WORKER_FAILED`; no review/apply became ready, Undo stayed disabled and Download
original remained available. For the successful full browser preview/apply above,
only the identified local pytest process was temporarily suspended, then resumed
after one-step undo. Limits were unchanged. This is evidence of safe bounded
failure under contention as well as the isolated success; concurrent full-corpus
and large interactive throughput is not claimed.

## Scope and remaining checks

- Client suite: 41 passed. Production build passed (existing large-chunk advisory).
  Strict typing: 30 source files clean. Canonical Unicode 15.1 data check passed.
  All three code-review blockers are resolved through `630ca28`.
- Final applicable Python run: **556 passed, one obsolete layout-refusal expectation
  failed, five Linux/CDN checks deselected**, in 1,406.65s (including the temporary
  browser-isolation pause). G4, complete corpus walks, bounded performance and web
  contracts passed after CR-03. The failed expectation was corrected in test-only
  `1f9af02` after independent glyph/text/pixel proof; the corrected three-test file
  passed in **2.41s**, including genuine late-layout refusal/no partial output.
  Production code remained `630ca28`; no unresolved regression is being hidden.
- Raw and follow-up logs: `/private/tmp/pdf-tool-phase5-final-pytest-20261024.log`
  and `/private/tmp/pdf-tool-phase5-final-layout-guard-20261024.log`. The broad run
  is not relabeled a zero-failure run; the corrected focused result supersedes its
  obsolete expectation.
- Literal legal-contract specimen coverage is unproven; the public source remains
  explicitly labeled a technical-document proxy.
- Linux resource enforcement, tmpfs/seccomp/container execution and live CDN/cache
  verification remain open Phase 4 release checks. macOS evidence does not prove them.
- No deployed URL exists and no deployment was attempted. The user explicitly
  deferred deployment and authorized this local Phase 5 work.
