---
phase: 05-find-and-replace-across-all-pages
verified: 2026-10-24T17:29:34Z
status: human_needed
score: 15/16 must-haves verified
overrides_applied: 0
implementation_status: delivered_locally
requirements_satisfied: [FIND-01, FIND-02, FIND-03, FIND-04, FIND-05, FIND-06]
source_head: 630ca28
test_correction: 1f9af02
human_verification:
  - test: Literal 40-page contract specimen
    expected: Identify an authorized actual contract specimen, then repeat all-page indexing, exact review, one atomic batch with an individual opt-out, preservation of exclusions/refusals/prior style, all-page three-renderer comparisons and one Undo under unchanged limits.
    why_human: The tested source is a USGS technical document. Its successful technical proof does not identify or establish representative literal legal-contract coverage. The specimen must be identified and its suitability confirmed before that acceptance evidence can be recorded.
---

# Phase 5 — Goal-Backward Verification

**Phase goal:** A user changes a word everywhere in a 40-page document in one action, sees exactly what will change before committing, and gets one undo.

**Status: `human_needed` for literal contract-specimen coverage only.** The local
functional goal and FIND-01 through FIND-06 are implemented and verified. No
remaining implementation BLOCKER was found. The roadmap's literal contract part
of success criterion 4 is unproven, so this report does not close the entire G4
contract or mark Phase 5/public release unconditionally complete.

**Re-verification:** No; initial goal verification. No previous verification or
accepted override was present. All five roadmap success criteria were retained,
then merged with the four plans' additional truths. Plan wording was not used
to remove the roadmap's literal specimen requirement.

## Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | Search across all pages uses interpreter normalization, defaults to insensitive substring, and has working match-case/Unicode whole-word options. | VERIFIED | `server/worker.py:196` projects the actual `run.display_text`; Python and JS consume the same generated Unicode 15.1 data. `search.mjs` uses literal `indexOf`, full folding and native Unicode word boundaries. Independent find-module tests passed; recorded Firefox counts are 1,029 default, 851 whole-word and 723 whole-word plus case-sensitive. |
| 2 | Matches carry page/context/live count, navigate to the actual run, and permit individual opt-outs. | VERIFIED | `findMatches` preserves page/run order and source offsets; `FindPanel.jsx:48` paginates actual matches, and inclusion/jump controls are separate. `sourceRunForMatch` resolves the exact source fragment. App passes its server box to `PageCanvas`, which waits for current rendering and uses `viewportBox`. Browser pagination, row focus, navigation at 115%/200% and one-of-several opt-outs are recorded. |
| 3 | Unreplaceable matches remain in the list, disabled with a reason. | VERIFIED | Matcher retains unsafe normalization/classification/shared-address hits. `FindPanel.jsx:55` disables inclusion, keeps navigation, and renders `explainReason` plus safe named codes. Preview refusals remain a separate record, not deleted matches. Actual fit and unknown-font browser refusals were observed. |
| 4 | Replace-all across a **40-page corpus contract** changes every remaining match in one action, with differences confined to edited runs on every changed page in all three engines. | UNCERTAIN — WARNING | The entire technical mechanism is proven on the immutable 40-page USGS source, including all 120 renderer pairs. That source is tagged `other`, not a literal legal contract. `tests/test_gate_g4.py` explicitly labels it a technical proxy. No literal 40-page contract specimen was tested; no override is applied. See `05-HUMAN-UAT.md`. |
| 5 | One Ctrl/Cmd+Z restores the entire replacement batch. | VERIFIED | App calls `commitRecipe` once in batch commit (`App.jsx:192`), then existing `previousRecipe`/original restore or full-recipe server replay restores one prior state. Native input undo is excluded from the global handler. Browser: one Cmd+Z restored the 40-page original/count 1,029; separate styled-canary flow retained earlier bold/color. |
| 6 | The complete accepted common-word workload previews/applies under unchanged worker limits. | VERIFIED | `test_find_replace_performance.py` builds all 772 initial proposals, asserts all 675 survivors, uses ordinary `run_worker` without a raised timeout, and checks CPU20/wall30/body/source/report contracts. Final `630ca28` proof: two tests passed in 59.93s; previews 18.302/18.319 CPU seconds, apply 18.467 CPU / 18.528 wall. Both performance nodes also passed in the broad final run. |
| 7 | Sequential edits use current font/encoding/offsets and retain fresh following-glyph validation. | VERIFIED | `PartSnapshot._capture` freshly parses the current page, fully consumes the interpreter, freezes yielded state and checks current part bytes/font bindings. `check_after` validates retained state, fresh following witness and replacement geometry. `apply_recipe` rederives later targets and refuses lost identities/changed substitution keys. Complex provenance uses classified fallback. Snapshot and negative-control tests exercise these paths. |
| 8 | Failures are atomic: no output/original mutation, nor stale client viewer/history/download changes. | VERIFIED | `apply_recipe` saves only after every operation succeeds (`recipe.py:920`); refusal exits close/discard the mutated handle. Worker preview uses actual apply and suppresses returned PDF bytes. `applyReviewedReplacement` prepares before commit and disposes stale prepared output. Independent corrected guard tests prove a successful first operation followed by a real corrupted-TJ D04 failure returns no PDF from preview or apply. |
| 9 | Full normalized expansions are safe; partial expansions cannot delete unrelated characters. | VERIFIED | `sourceSpan` checks inverse coverage and grapheme endpoints, retaining source UTF-16 intervals through decomposition/folding/reordering. Tests cover ligatures, sharp-s, accents, reordered marks and astral prefixes. Independent probes confirmed canonical/reordered provenance and fail-closed behavior without `Intl.Segmenter`. |
| 10 | Search/replacement use current committed text and preserve all prior operations/styles. | VERIFIED | App searches `recipeState.recipe`; matcher overlays `new_text` on original source rows. Builder applies selected slices right-to-left and upserts into the complete prior recipe, preserving operation order/style. Real HTTP tests exercise prior text/bold/color and a second batch using original IDs; browser Undo preserved the earlier styled edit. |
| 11 | All-page indexing has honest partial, stopped, failed and complete scope. | VERIFIED | `createIndexingController` counts successful pages, retains failed pages, ignores stale generations and retries only missing work. App renders only accepted `completedPages`. Browser stop/resume/close on 126 pages and injected 429/503 plus Retry showed incomplete counts and disabled preview until completion. |
| 12 | Preview filters only new refusals and validates the exact surviving full recipe before apply. | VERIFIED | `previewReplacement` sends actual complete candidates, rejects prior-operation failures, requires strictly growing refusal sets and obtains an overall successful report for the exact rebuilt recipe. It validates resolved coverage and deeply freezes review data. Node tests and actual Node/HTTP integration prove failed-preview → filter → exact-success → apply. |
| 13 | Query/options/replacement/exclusion/recipe/document changes cannot revive stale readiness. | VERIFIED | `batchKey`, `batchKeyRef`, session identity and `editVersion` guard asynchronous publication; inputs invalidate reviews; apply captures accepted data and checks freshness around awaits. Cancel releases only its mutation owner. Deferred helper tests and delayed actual browser responses/close-reopen journeys demonstrate no stale review/apply or output publication. |
| 14 | Unknown fonts have explicit fallback while intentional prior per-run font/style choices survive. | VERIFIED | Builder supplies the selected family only for substitution/unresolved cases and retains an existing family. Panel keeps unknown-font rows and offers the native Serif/Sans/Mono select. Actual API tests cover both unmapped substitution and embedded original CFF; browser Serif recovery changed four matches on two pages and one Undo restored all four. |
| 15 | The complete accepted technical-proxy batch changes every included safe instance, retains opt-outs/refusals/style, and passes every renderer page. | VERIFIED | G4 asserts all 675 operations, exact Unicode at original physical anchors, independent full-page character deltas, individual opt-out, prior RGB readback, 25,972 untouched instructions, qpdf validity and immutable bytes. All 40 pages × three engines are compared: 28 changed pages use unions of individual run masks; 12 unchanged pages use none. Same-engine outside count is zero; cross-engine tolerance is separate. The final broad run re-exercised this gate after `630ca28`. |
| 16 | Local evidence states actual outcomes and preserves untested specimen/platform/release boundaries. | VERIFIED | Dated `05-G4-RESULTS.md` distinguishes native Firefox history from current Chromium, agent-operated UI checks from user acceptance, safe contended failures from isolated performance success, and proxy from literal contract. G3 Linux/container/CDN checks remain open. No deployment occurred. |

**Score: 15/16 truths verified; one narrowly scoped coverage WARNING.**

## Required Artifacts and Wiring

These checks assessed existence, substantive implementation and actual consumers;
file existence or summary assertions alone were insufficient.

| Artifact(s) | Substantive behavior | Wiring/status |
|---|---|---|
| `engine/data/search-unicode-15.1.json`, `tools/build_search_unicode.py` | Versioned sparse decomposition/fold/CCC data; deterministic generator rejects a different Unicode version and checks freshness. | VERIFIED — Python runtime and JS static import consume the sole artifact; both Docker client stages copy it; Vite narrowly permits the shared data directory. |
| `engine/search.py` | Tagged scalar expansion, stable canonical ordering and UTF-16 provenance. | VERIFIED — existing worker page serializer calls `project_search_text` for actual interpreter text. |
| `client/src/find/search.mjs` | Literal matching, effective committed text, Unicode boundaries, safe inverse spans and distinct shared-address occurrence IDs. | VERIFIED — imported/called by App; exact source lookup is consumed by both App navigation and panel font metadata. |
| `client/src/find/buildRecipe.mjs` | Per-instance exclusion, right-to-left edits, one operation per run, prior recipe/style preservation and complete body/op/text caps. | VERIFIED — App's preview candidate callback invokes it; actual Node/API/G4 integration uses the shipped helper. |
| `client/src/find/indexing.mjs` | Successful-page set, failed-page retention, stop/resume/dispose generations and single producer. | VERIFIED — App injects returned cached `fetchRuns` promises over the existing two-slot request queue. |
| `client/src/find/preview.mjs` | Actual full-recipe dry run, strictly shrinking proposal filtering, prior-edit protection, exact resolved coverage and immutable review. | VERIFIED — App injects ordinary `/edit?dry_run=true`; panel consumes only a current review. |
| `client/src/find/replaceAll.mjs` | Frozen exact review, signature/currentness checks, prepared viewer, one commit and stale/failure disposal. | VERIFIED — App injects ordinary apply, `prepareViewer`, publication and one history callback. |
| `client/src/App.jsx`, `client/src/find/FindPanel.jsx`, `client/src/Viewer.jsx` | Controlled UI, complete-page visibility, source-box navigation, mutation owner, guarded publication and existing undo. | VERIFIED — real server data flows to state and visible controls; no hardcoded result/preview source. |
| `engine/recipe.py`, `engine/rewrite.py`, `engine/part_snapshot.py` | One ordinary atomic rewrite path; fresh per-splice proof; source-TJ envelope/pen separation; actual written-space budget; fallback and named refusals. | VERIFIED — worker edit/preview invokes `apply_recipe`; recipe invokes current resolve/rederive and rewrite; rewrite invokes post-splice guards before any final output save. |
| `tests/test_find_normalize_parity.py` | Exhaustive generated scalar mappings, Unicode seams, wire identity and JS/Python strings plus spans on all 3,000 proxy runs. | VERIFIED — normal pytest discovery; corpus case included in final applicable run. |
| `client/src/find/*.test.mjs` | Matching, builder, indexing, preview and apply failure/stale/history contracts. | VERIFIED — npm discovery includes nested files; independently rerun 28 find-module tests passed. |
| `tests/test_find_replace_performance.py`, `tests/test_find_replace_recipe.py`, `tests/test_gate_g4.py` | Actual bounded workers, actual Node/HTTP recipes and nonvacuous all-page renderer/text/opt-out proof. | VERIFIED — ordinary pytest discovery/corpus markers; all passed on frozen final production code. |
| `tests/test_part_snapshot.py`, `tests/test_recipe_snapshots.py`, `tests/test_batch_ink_bounds.py`, `tests/test_preview_layout_guard.py` | Freshness, geometry, late atomic failures, alternate provenance, actual narrow spaces and corrected safe-preview regression. | VERIFIED — focused checks and final broad coverage; corrected layout file independently passed three tests. |
| `05-G4-RESULTS.md`, plan summaries and `05-REVIEW.md` | Dated runtime/UI evidence, failing-to-passing measurements and three resolved review blockers. | VERIFIED as evidence records — runtime logs and test source were checked independently; historical summary statements do not supersede the final results below. |

## Key Links

| From → To | Actual connection | Status |
|---|---|---|
| Worker → canonical projector | Page serializer uses interpreter `run.display_text`, retaining original text/ID/classification/box. | WIRED |
| Browser projector → canonical data | Static JSON import at `search.mjs:1`; same version as Python runtime. | WIRED |
| Matcher/builder → prior session recipe | Effective `new_text` overlay plus `upsertOperation` on the complete recipe, preserving style. | WIRED |
| Index controller → cached page requests | `App.jsx:124` injects `fetchRuns`, which reuses/promotes pending requests and uses normal source/password recovery. | WIRED |
| Preview → ordinary protected endpoint | `App.jsx:145` posts the exact full candidate to `/edit?dry_run=true`. | WIRED |
| Review → atomic apply → one history entry | `App.jsx:187–192` uses `applyReviewedReplacement`, ordinary `/edit?dry_run=false`, prepared viewer and one `commitRecipe`. | WIRED |
| Undo → full prior recipe/original | `App.jsx:207` obtains `previousRecipe`; empty prior recipe restores browser original, otherwise ordinary server replay. | WIRED |
| Result → actual rendered source box | Exact source fragment supplies `box`; PageCanvas waits for current PDF/page/scale and applies `viewportBox`. | WIRED |
| Recipe → rewrite → fresh guard | `apply_recipe` invokes current resolve/rederive and `rewrite_run`; both fast/fallback paths check following positions and replacement envelope. | WIRED |
| G4 → render/mask harness | Every page renders through all three engines; `_union_diff` masks individual regions and unchanged pages remain unmasked. | WIRED |

## Data-Flow Trace

| Dynamic artifact | Real upstream data | Render/publication | Status |
|---|---|---|---|
| Find result list/count | Server worker page rows → `fetchRuns`/accepted completed pages → canonical matcher over current committed recipe. | Actual `matches`/progress props drive rows, count, pagination and disabled reasons. | FLOWING |
| Before/After and readiness | Full recipe builder → actual rewrite dry run → exact successful immutable current review. | Panel renders selected change/reasons; App only supplies current keyed review/apply permission. | FLOWING |
| In-page result outline | Exact matched source fragment's server-issued box. | PDF viewport transform after current render; no pdf.js-text-item address guessing. | FLOWING |
| Edited viewer/download/history | Ordinary worker apply output → decoded bytes → prepared PDF → final freshness check. | One synchronous publication/history step; failed/stale output is not published. | FLOWING |

## Behavioral Spot-Checks Run by This Verifier

| Check | Result |
|---|---|
| `node --test client/src/find/search.test.mjs client/src/find/buildRecipe.test.mjs client/src/find/indexing.test.mjs client/src/find/preview.test.mjs client/src/find/replaceAll.test.mjs` | **28 passed** in approximately 0.29s. |
| Python assertions for `ﬁß😀é` and reordered combining marks | Passed exact canonical output and source UTF-16 span assertions. |
| Fresh process with `Intl.Segmenter` unavailable | Substring results remained visible but replacement locked; whole-word mode threw the explicit limitation. Passed; runtime capability restored in `finally`. |
| `.venv/bin/python tools/build_search_unicode.py --check` | `Search Unicode 15.1.0 data is current`. |
| `.venv/bin/python -m pytest -q tests/test_preview_layout_guard.py -x` | **3 passed in 2.45s**, independently verifying safe corrected corpus layout and genuine late D04 refusal. |
| Existing 320px browser screenshot | Independently inspected; labeled find controls and visible focus remain within the narrow viewport. No user acceptance is inferred. |

No phase-declared shell probes were found. The generator and executable behavioral
checks above were run directly; no server, deployment, dependency installation or
heavy full corpus rerun was started by this verifier.

## Final Regression Evidence and the Superseded Expectation

Production code is frozen at `630ca28`. The broad command was:

`.venv/bin/python -m pytest -q -m 'not linux_only and not cdn'`

Its **raw result was 556 passed, one failed, five deselected, three warnings in
1406.65s**. The duration includes the documented temporary suspension of the
identified pytest process during the large browser proof. No test was skipped.
This raw run must not be described as a zero-failure command.

The sole failed assertion expected the old real-corpus short-Sans edit to be
refused. The new actual-written-width/terminal-pen correction makes that specific
edit safe. Before adapting the expectation, the executor independently checked
all 663 following glyph positions/advances (maximum difference about 1.14e-13pt),
requested output text and independent PDFium page character delta, and a
nonvacuous 150dpi image diff with zero changed pixels outside the original source
run plus the existing 3pt padding.

Test-only commit `1f9af02` records that safe positive case and adds a separate
actual isolated-worker corrupted-TJ negative: an earlier operation succeeds,
then a real following-text shift triggers `text_matrix_shifted_after_edit`;
preview and apply return no PDF. No production code, tolerance or resource limit
changed. This verifier reviewed the implementation and independently ran all
three corrected tests successfully. The final post-broad-run command also passed
**three tests in 2.41s**, recorded in
`/private/tmp/pdf-tool-phase5-final-layout-guard-20261024.log`.

Thus **558 current applicable cases have passing coverage: 555 unchanged cases
from the broad run plus all three cases in the corrected file**. This is
aggregate evidence, not a claim that the original broad command was green.
The final broad run includes the performance, post-space-budget G4, corpus,
walker, page-scope and web-contract nodes. It supersedes the older integration
page-scope failures retained historically in the 05-02 summary.

Additional final logs confirm 41 client tests passed, production build passed,
mypy found no issues in 30 source files, and Unicode data was current. Existing
build chunk-size and library/corpus warnings are recorded rather than hidden.
The full-suite log is
`/private/tmp/pdf-tool-phase5-final-pytest-20261024.log`.

## Requirements Coverage

| Requirement | Source plans | Status | Implementation/proof |
|---|---|---|---|
| FIND-01 | 02, 03, 04 | SATISFIED locally | Shared interpreter/browser normalization, current-source rows and complete-page indexing. |
| FIND-02 | 02, 03, 04 | SATISFIED locally | Literal insensitive substring, match-case and Unicode whole-word toggles with capability fallback. |
| FIND-03 | 03, 04 | SATISFIED locally | Live count, source context/page, stable unique occurrences and real source-box navigation. |
| FIND-04 | 02, 03, 04 | SATISFIED locally | Per-instance exclusions, including several occurrences in one run, preserved in real output. |
| FIND-05 | 02, 03, 04 | SATISFIED locally | Visible disabled classification/normalization/runtime refusals and explicit font recovery. |
| FIND-06 | 01, 02, 04 | SATISFIED locally | Exact reviewed full recipe, one ordinary atomic apply, bounded complete workload and one whole-recipe Undo. |

Every Phase 5 requirement ID appears in plan frontmatter and has a substantive
implementation and executed proof. No orphaned Phase 5 requirement was found.
These six requirement results do not erase the narrower literal-specimen part
of roadmap success criterion 4.

## Anti-Patterns and Disconfirmation

No implementation stub, orphaned feature module, disconnected dynamic data,
unreferenced `TBD`/`FIXME`/`XXX` marker, new bulk endpoint, injected HTML or
document-content logging was found in the inspected phase source. Legitimate
initial empty state is populated by real page/worker data and is not a stub.

The disconfirmation pass explicitly examined ways a passing narrative could
mislead:

- **Partial requirement:** the literal 40-page contract criterion remains
  unproven. It is the one coverage WARNING, not a silently accepted proxy.
- **Insufficient passing test:** a character counter alone cannot prove correct
  placement/order. G4 additionally checks exact Unicode at physical anchors,
  retained instruction order and every same-engine page image. Timing proof alone
  was likewise not accepted as fidelity proof.
- **Error-path coverage:** absent `Intl.Segmenter` was not established by the
  recorded modern-browser journey. The verifier executed that negative capability
  path directly and confirmed safe locked replacements and explicit whole-word
  guidance. A legacy-browser visual journey is not claimed.

The three concrete source-review blockers—shared physical address identity,
source-TJ visible overflow and narrow serialized-space reversal—have reproduced
tests and reviewed fixes. The final corrected preview test confirms D04 was
preserved rather than weakened to accommodate the new fit behavior.

## Human Verification Required

### 1. Literal 40-page contract specimen

**Test:** Identify an authorized actual 40-page contract specimen and repeat the
recorded full batch/opt-out/prior-style/three-renderer/one-Undo acceptance shape
under the same limits. Establish the document's actual classification and digest.

**Expected:** Every included supported occurrence changes once, excluded/refused
content and prior styles remain, every page passes the existing per-run-mask or
unmasked comparison in all three renderers, and one Undo restores the prior recipe.

**Why still open:** The tested USGS source is explicitly a technical proxy. The
manifest's contract-tagged FAR rulebook does not itself establish a literal
40-page legal-contract specimen. The existing browser observations substantiate
the local functional flows; they do not assert user acceptance or invent the
missing specimen coverage. This single item is persisted in `05-HUMAN-UAT.md`.

## Scope Boundaries

Linux resource enforcement, tmpfs/seccomp/container execution and live CDN/cache
verification remain separate open Phase 4 G3 release checks. macOS local evidence
does not prove them. No deployed URL exists, no deployment occurred, and this
report does not authorize one.

Page operations/merge and later exports remain future roadmap work, not missing
Phase 5 implementation. The literal contract coverage debt is not deferred to a
later feature phase; it remains attached to Phase 5/G4 until actually tested or
explicitly resolved through an accepted scope decision.

---

_Verified: 2026-10-24T17:29:34Z_

_Verifier: Codex (gsd-verifier); no source or state edits, no commit._
