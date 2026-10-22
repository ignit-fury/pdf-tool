---
phase: 5
slug: find-and-replace-across-all-pages
status: approved
shadcn_initialized: false
preset: none
created: 2026-10-22
---

# Phase 5 — UI Design Contract

> Visual and interaction contract for FIND-01..FIND-06. Preserve the existing navy, white, and cobalt document workstation. Deliver locally; deployment is not authorized in this phase's current session.

## Design System

| Property | Value |
|----------|-------|
| Tool | none — existing manual CSS design system |
| Preset | not applicable |
| Component library | none — React and native HTML controls already in the client |
| Icon library | none — reuse existing text controls; arrows receive accessible labels |
| Font | `Avenir Next, Avenir, Segoe UI, Arial, sans-serif`, inherited from `client/src/style.css` |

Evidence: `client/src/App.jsx`, `Viewer.jsx`, `session.mjs`, `style.css`, and `client/package.json`. No `components.json` is present. The existing custom design system and explicit instruction to reuse it without new dependencies resolve the shadcn gate: do not initialize shadcn. This phase adds no registry blocks, fonts, imagery, or animation library. Existing welcome typography is outside this contract's change surface.

Sources and precedence: REQUIREMENTS FIND-01..06 and ROADMAP Phase 5 define behavior; 05-CONTEXT decisions D-5.1..D-5.5 are locked. 05-RESEARCH supplies dry-run, per-instance exclusion, per-run recipe, and progress findings. Current Phase 4 code supersedes research proposals about endpoint shape and existing component structure. Routine visual and interaction choices below are defaults delegated in the current session.

## Spacing Scale

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Badge gaps, related inline text |
| sm | 8px | Label/input gaps, button groups, match row gaps |
| md | 16px | Control groups, match row padding, inspector padding at compact desktop widths |
| lg | 24px | Panel padding at normal desktop widths, section separation |
| xl | 32px | Separation between review and results on wide layouts |
| 2xl | 48px | Minimum empty-state vertical padding |
| 3xl | 64px | Reserved; no additional large space needed in the inspector |

Exceptions: 1px borders and 2px focus outlines are stroke widths. Form controls and new buttons have a minimum 44px touch height; checkbox hit areas are at least 44×44px. Preserve existing page rail, viewer, and workspace dimensions instead of globally retuning their legacy spacing. No new arbitrary spacing values.

## Typography

Exactly three sizes and two weights for new phase UI:

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Body | 14px | 400 | 1.5 |
| Label | 12px | 600 | 1.5 |
| Heading | 16px | 600 | 1.2 |
| Display | 16px | 600 | 1.2 — same token as Heading; no display treatment |

Supporting descriptions, page metadata, badges, and reason codes use 12px at 400. Buttons use 12px at 600. Result excerpts use 14px at 400; matched text uses 600 plus the highlight fill. Do not shrink long excerpts or reasons; wrap them. Use tabular numerals for progress and counts. Preserve source PDF typography in the viewer.

## Color

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `#ffffff` | Inspector, controls, match rows, document paper |
| Secondary (30%) | `#edf0f4` | Workstation background; retain existing viewer `#e3e8ef` and subtle section `#f5f7fa` |
| Accent (10%) | `#2458df` | Current primary CTA, checked checkboxes, keyboard focus, active result outline, matching text highlights |
| Destructive | `#994333` | Existing semantic color for the empty-replacement removal notice and its review warning; always paired with explicit removal copy |

The 60/30/10 split describes the interface surfaces; document artwork is excluded. Reuse `--navy: #182840`, text `#243248`, `--muted: #667489`, and `--line: #d9e0e9` from the existing CSS. New supporting copy that needs stronger contrast uses existing `#52647f`. Use existing pale cobalt `#edf3ff` for match/review fills and existing refusal colors `#fff2e8` with `#8c502e` for refusal summaries. Failure text uses existing `#994333`. Every status also has text; color alone never signals inclusion, readiness, or refusal.

Accent reserved for: the enabled `Preview replacements` or `Replace {N} matches` primary button, checked native checkboxes, the active panel selector, focus outlines, text-match marks, and the current run highlight. Secondary navigation, page labels, disclosure badges, and entire result row backgrounds remain restrained. Use ordinary full borders or separators; no accent side borders, gradients, decorative illustrations, or unnecessary transitions.

## Copywriting Contract

Dynamic counts refer to match instances, not recipe operations. Use singular/plural forms throughout.

| Element | Copy |
|---------|------|
| Panel opener and heading | `Find and replace` |
| Return to inspector | `Text inspector` |
| Find label / placeholder | `Find text` / `Word or phrase` |
| Replace label / placeholder | `Replace with` / `Replacement text` |
| Search disclosure badge | `Local search` |
| Index disclosure badge | `Server index` |
| Preview action | `Preview replacements` with `Server` badge |
| Primary apply CTA | `Replace {N} matches` with `Server` badge |
| Search options | `Match case`; `Whole words only` |
| Empty state heading | `Find text across this PDF` |
| Empty state body | `Enter a word or phrase. Matches appear as pages are indexed.` |
| No matches, complete index | `No matches found` / `Try another spelling or turn off Match case or Whole words only.` |
| No matches, incomplete index | `No matches yet. Results cover {P} of {T} pages.` |
| Index progress | `Indexed {P} of {T} pages · {M} matches so far` |
| Stop index action | `Stop indexing` |
| Stopped state | `Indexing stopped at {P} of {T} pages. Results are incomplete.` / `Resume indexing` |
| Completed index | `{M} matches across {T} pages` |
| Search disclosure | `Search runs in your browser over text indexed by the server. Indexing, preview, and replacement use the server.` |
| Index error | `Could not index page {P}. Results are incomplete. Retry indexing to search every page.` / `Retry indexing` |
| Worker busy after retries | `The server is busy. Your results are saved. Retry indexing.` |
| Result checkbox | Accessible label: `Include match {I} on page {P}` |
| Result navigation | Visible `Page {P}`; accessible label `Show match {I} on page {P}: {context}` |
| Excluded match | `Excluded` |
| Classification refusal | `Cannot replace` followed by the existing `explainReason(reason)` output |
| Awaiting preview | `Fit not checked` |
| Required font choice | `No automatic font match. Choose a replacement font, then preview again.` |
| Incomplete-index action help | `Finish indexing every page before previewing replacements.` |
| No selection | `Select at least one replaceable match to preview.` |
| No-op replacement | `The replacement does not change any selected text.` |
| Preview progress | `Checking replacement fit on the server…` |
| Review heading | `Review replacements` |
| Review summary | `{N} matches on {P} pages will change. {E} excluded. {B} cannot be replaced.` |
| Review before / after | `Before`; `After` |
| Review ready | `Ready to replace {N} matches. One undo restores this batch.` |
| Review all refused | `No selected matches can be replaced. Review the reasons below, adjust the text or font, then preview again.` |
| Stale review | `Replacements changed. Preview again before applying.` |
| Preview error | `Could not preview replacements. Your PDF is unchanged. Try again.` |
| Apply progress | `Replacing {N} matches on the server…` |
| Apply error | `Could not apply replacements. Your PDF is unchanged. Preview again, then retry.` |
| Source mismatch | `This preview no longer matches the document. Refresh the index and preview again.` |
| Success | `Replaced {N} matches on {P} pages. Undo restores the whole batch.` |
| Undo action / success | `Undo replacements` / `Replacement batch undone.` |
| Results pagination | `Matches {A}–{B} of {M}`; `Previous results`; `Next results` |
| Deletion by empty replacement | `Replacement is empty. Included matches will be removed.` |
| Destructive confirmation | No separate modal. The required review shows the exact Before/After text, removal notice when relevant, affected count, exclusions, and refusals before the explicit apply CTA. |

Refusal reasons must reuse `explainReason` and `refusalCode` from `session.mjs`, including dynamic fit reasons and a readable fallback. Show the named reason inline below the row; never put essential reasons only in a tooltip. Unknown server errors use the contextual error above and may expose the returned safe reason; do not expose stack traces or PDF content in diagnostics.

## Layout and Component Inventory

1. Add a `Find and replace` button to the existing viewer toolbar. It opens the right inspector as a find panel; a `Text inspector` button returns to the single-run interface. Use a labeled button group with `aria-pressed`; do not introduce a fourth workspace column. Keep the page rail, zoom, page controls, document actions, and signed-document acknowledgment available.
2. The find panel replaces the inspector contents, retaining the existing 294px desktop column, 265px compact column, and 330px wide-screen column. At 760px and below, retain the existing stacked page rail → viewer → inspector flow. New action groups wrap, text inputs fill the panel width, and preview/apply buttons become full width. Do not turn this into a mobile modal or drawer.
3. Panel order: heading and return control; Find text; the two option checkboxes; index progress and stop/resume/retry; Replace with; replacement font; selection counts and Preview replacements; current review and apply action; result list and pagination; operation disclosure. With no query, show the empty state and disable preview/apply. Search result counts remain visible above the list.
4. Use a single-column ordered list with 50 matches per page, ordered by page, run order, then occurrence offset. Each row has a native inclusion checkbox and a separate jump button; never nest controls. Row content contains page number, context with the matched occurrence marked, inclusion/readiness state, and any refusal reason. The context window is up to 48 source characters before and after the match, with ellipses only for omitted source text. Wrap long words. The full run is available in the active result detail.
5. Current row uses a full 1px cobalt outline and `Current match` text or accessible state. Excluded rows remain readable and navigable. Refused rows have disabled unchecked inclusion boxes but an enabled jump button and named reason. Do not dim all row content or hide refused results. After a preview, the active row detail shows the full affected run Before and After; every included result offers this review detail by selecting its jump button.
6. Reuse the existing `font-choice` native select and exact options: `Automatic — preserve or match original`, `Serif — Liberation Serif`, `Sans-serif — Liberation Sans`, `Monospace — Liberation Mono`. Label `Replacement font`. Automatic preserves existing font behavior. Explicit choice applies only to runs requiring substitution or an unresolved font choice; it is not batch restyling. Tell the user `Used where the original font cannot supply the replacement.` Unknown-font matches stay in the list with a named font-choice reason until chosen and previewed. An intentional per-match exclusion survives font changes.
7. Review is an inline bordered section, using existing fit-result patterns, with summary, affected-page count, Before/After active run detail, and apply action. No additional confirmation modal. Every result remains reachable for inspection; pagination does not limit the replacement scope. Use the existing status bar for operation completion and the panel for durable result/review state.

The current PDF page and selected run remain the workstation's primary visual anchor. Within the find panel, `Preview replacements` is the primary CTA until a current successful review exists; `Replace {N} matches` then becomes the primary CTA and preview becomes secondary. Do not present both panel actions as competing primary buttons.

## Interaction and State Contract

### Search and indexing

- Opening the panel begins lazy whole-document indexing through existing page-run requests, reusing cached pages. Fetch missing pages sequentially with the current request queue; prioritize the selected page without launching one request per page concurrently. Ordinary viewing remains interactive.
- Query changes update local matching immediately over available indexed data. Case-insensitive substring is the default; both options start unchecked. Empty query produces zero results and no replacement. Literal punctuation is literal; there is no regex mode. Ligatures and TJ-adjusted text must follow the interpreter's normalization. Whole-word matching uses Unicode word boundaries, including non-ASCII letters, digits, and combining marks; do not implement it with ASCII-only `\b`. Matching offsets must map back to source text so opting out or replacing a normalized match changes the correct characters.
- Count successful indexed pages, not the current page number. Until every page is indexed, label results incomplete and show `so far`; never display a final document-wide zero or final total prematurely. Show a native progress element with actual page counts. No elapsed-time estimate or invented percentage for server preview/apply.
- Stop indexing stops scheduling missing-page work and prevents late responses from changing a stopped generation. Preserve completed pages, query, and exclusions. Resume continues missing pages. Stopping indexing does not close or abort the document session. A failed page leaves the document incomplete; retry targets missing/failed pages. Canceling/closing the document clears all query, list, review, and selection state.
- Changing query or either search toggle resets inclusion to the new match set, resets pagination to page 1, and invalidates preview. Changing replacement or font preserves intentional exclusions but clears replacement-specific verdicts and preview. Pagination and ordinary match navigation do not invalidate a preview. Keep stable occurrence identifiers so page fetches cannot transfer exclusions to a different match.
- Result count includes eligible, excluded, and refused occurrences. Selection count includes only selected eligible occurrences. No-op occurrences are labeled unchanged and excluded from the apply count. More than one occurrence in a run remains individually selectable.

### Match navigation and accessibility

- Selecting a result navigates to its actual 1-based page, waits for the current page render, then scrolls the actual server-issued run bounds into view using the existing PDF viewport transform. Show a persistent run outline and a match mark where source-to-rendered text mapping is reliable. The list excerpt always identifies the exact occurrence; never present a guessed substring rectangle as exact. Highlighting must also work for refused runs and non-default zoom/rotation.
- Retain focus on the selected result for repeated keyboard exploration; announce `Match {I} of {M}, page {P}` politely. On mobile the selected page is brought into view without discarding panel state. Provide an explicit `Back to results` control near the viewer while find is active so keyboard users can return to the current row.
- Opening Find and replace focuses Find text. Returning to Text inspector restores focus to its toolbar control. Do not override browser Ctrl/Cmd+F. Preserve Ctrl/Cmd+Z for batch undo outside inputs; native input undo remains native while typing.
- All controls have visible associated labels and visible 2px cobalt focus outlines with 2px offset. Checkbox Space and button Enter/Space use native behavior. Use ordinary ordered-list semantics, not a listbox with nested checkbox behavior. Disabled checkbox reasons are linked with `aria-describedby` and remain in readable row text.
- Result updates use one `aria-live="polite"` summary, coalesced to at most once per 500ms. Mark index/review regions busy only while their corresponding work runs. Errors use an alert region without duplicate global announcements. Pagination preserves query/exclusions and moves focus to the result-page summary. Respect existing reduced-motion rules; no animated scroll is required.

### Preview, apply, and undo

- Preview requires complete indexing, a nonempty query, at least one selected candidate that changes text, and no operation already mutating the document. Replacement may intentionally be empty. Explicit user action triggers the server dry run; do not send a request per keystroke.
- Build one ordinary operation per affected run, containing only selected occurrences. Preserve prior recipe edits and their style/font decisions. Search and Before/After must represent the current document recipe, including prior single-run edits; never search the original and overwrite an earlier edit invisibly. This is one batch through the existing single-edit path, with no separate find-replace endpoint.
- Classification refusals appear immediately. The dry run adds fit/font/rewrite refusals to the same list and disables their inclusion boxes. A refused operation affects every selected occurrence in that run; communicate that shared refusal rather than claiming that some occurrences in the refused run are ready. Keep intentional exclusions separate from refusals.
- The review counts only passing, changing matches, retaining all refused rows. Ensure the exact final surviving recipe has a current successful dry-run report before enabling apply; filtering refusal candidates is not permission to reuse a mismatched full-recipe preview. Existing prior operations must also validate. Report actionable refusal if they do not; do not silently remove a prior edit.
- Any query/options/replacement/font/exclusion/current recipe/document generation change invalidates preview. Never let a late server response re-enable apply for an older selection. The final CTA states the exact ready occurrence count; excluded and refused matches remain unchanged. During preview, `Cancel preview` dismisses that request generation and returns to the draft without claiming the server computation was terminated.
- Applying locks replacement controls, single-run mutations, and undo while the request runs; prevent duplicate submission. Show stage text, not fabricated progress. Do not offer cancel-after-commit semantics the endpoint cannot guarantee. Closing/opening another document aborts local requests and invalidates late completions; no result may attach to another session.
- Retain the existing signature acknowledgment gate. Review/apply must not bypass its check or repeat its confirmation elsewhere. Keep existing encryption copy unchanged. An apply response that refuses or fails does not change viewer bytes, recipe history, download, or undo state. Source mismatch invalidates index/review and requires refresh.
- Commit viewer bytes and one history entry only after successful apply. One Undo replacements or Ctrl/Cmd+Z restores the entire prior recipe and PDF. Reuse existing local/server undo disclosure according to whether replay is required. An undo failure retains current bytes/history and gives a retry message.
- After success or undo, invalidate replacement preview and recompute results against the current recipe, retaining query/options. Show new match counts; do not leave stale original hits represented as current PDF text. The completion status preserves the just-applied batch count even when search results change.
- Respect existing recipe/text limits. On a limit refusal show `This replacement exceeds the document edit limit. Exclude some matches or use shorter replacement text, then preview again.` Never split apply into multiple undo steps or silently truncate the selection.

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| none | none | Not applicable — no shadcn initialization or third-party registry use; existing native/custom controls confirmed 2026-10-22 |

## Validation Targets

- FIND-01/02: server-normalized TJ text and ligatures; default substring; working case and Unicode whole-word toggles; current-recipe text and correct source offsets.
- FIND-03: live complete/incomplete counts, 50-row pagination, exact page/run jump at changed zoom, readable context and keyboard return to results.
- FIND-04/05: exclude one of two occurrences in the same run; disabled classification and dry-run refusals remain visible with named reasons; explicit unknown-font recovery; all-refused, all-excluded, no-match, and empty replacement states.
- FIND-06: exact fresh dry-run review; apply survivors through ordinary recipe path; successful 40-page replacement reflects opt-outs and refuses unchanged runs; one undo restores the prior recipe. Apply failure and late responses leave document state intact.
- Responsive/accessibility: 760px stack, no horizontal form overflow at 320px, labeled controls, checkbox keyboard access, focus visibility, concise screen-reader summaries, no result navigation focus loss.
- Deployment gate: local contract and implementation verification do not close the pending Phase 4 Linux/CDN proof or authorize deployment.

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS
- [x] Dimension 2 Visuals: PASS
- [x] Dimension 3 Color: PASS
- [x] Dimension 4 Typography: PASS
- [x] Dimension 5 Spacing: PASS
- [x] Dimension 6 Registry Safety: PASS

**Approval:** approved 2026-10-22
**Reviewed at:** 2026-10-22T09:24:10Z
