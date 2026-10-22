# Phase 5: Find and Replace Across All Pages - Context

## Execution amendment — 2026-10-22

The user explicitly authorized Phase 5 with "dont deploy it yet just go to nxt
phase". Build this phase locally against the delivered Phase 4 UI/API. Keep
deployment on hold and preserve the outstanding Linux/container/CDN release gates;
their absence does not block this user-authorized local phase execution.

The earlier research predates the current Phase 4 implementation. Read
`05-RESEARCH-UPDATE.md` and `05-PATTERNS.md` when present for current contracts.
The existing client uses React/JavaScript and Node's built-in test runner. Reuse
the current style system, cancellation/queue/source-recovery helpers, recipe
engine, explicit replacement-font controls and single undo model. Routine
implementation/UI choices remain delegated to the builder, not new user decisions.

Edit preview now executes actual rewrite validation in disposable worker scratch;
it returns a report without PDF bytes. Preserve all worker limits and fidelity
guards. Search must distinguish partial indexing from a complete-document result,
retain failed/uneditable page information, and invalidate stale previews when the
query, replacement, selection, document or current recipe changes.

**Gathered:** 2026-08-30
**Status:** Ready for planning
**Source:** Batch planning pass (no `/gsd:discuss-phase` run). Phase boundary and constraints
transcribed from `ROADMAP.md` and `REQUIREMENTS.md`. Everything not listed as a decision is
Claude's Discretion — resolve it in research/planning rather than assuming a preference that was
never expressed.

<domain>
## Phase Boundary

A user changes a word everywhere in a 40-page document in one action, sees exactly what will change
before committing, and gets one undo.

**In scope:** FIND-01..FIND-06.

**Explicitly NOT in scope:**
- Page ops and merge (Phase 6), exports (Phase 7), PDF/A + DOCX (Phase 8).
- Regex search, multi-document search, or search across anything but the current document.
- Any new rewrite implementation. Replace-all is N ordinary overrides through the ordinary apply
  path built in Phase 4.

## Hard Dependency

Phase 4 (Gate G3). This phase needs the SPA shell, the viewer, the server-issued run index, the
single-run edit round trip, and the undo/recipe store — all of which land in Phase 4.

</domain>

<decisions>
## Implementation Decisions

### Settled upstream — do not relitigate

- **D-5.1: There is no bulk find-replace endpoint.** `REQUIREMENTS.md` lists "A separate bulk
  find-replace endpoint" in its **Out of Scope** table, and `ROADMAP.md` restates the reason: find
  is a client-side query over the cached index producing N ordinary overrides. A bulk endpoint
  means two rewrite implementations within six months. Replace-all therefore goes through the same
  apply path a single edit does.

- **D-5.2: Find and replace are two features, built in that order.** `ROADMAP.md` is explicit:
  build the match list and preview (FIND-01..05) *before* wiring apply (FIND-06). Find depends only
  on the Phase 2 index, not on the rewrite engine, so it demos early and de-risks replace by making
  its inputs visible. The roadmap names estimating them as one item as the most likely source of a
  blown estimate. Wave structure must reflect the split.

- **D-5.3: Search normalization is the interpreter's own normalization, not a second one.**
  FIND-01 requires intra-word TJ adjustments collapsed and ligatures normalized — using the same
  normalization the Phase 2 interpreter used. A second normalization path anywhere is the same
  smell EXPO-05 names for extraction: a signal the text model is under-specified. If the Phase 2
  index does not already expose the normalized form, the fix is to expose it, not to re-derive it.

- **D-5.4: Unreplaceable matches are shown, disabled, with a reason — never filtered out.**
  FIND-05, and it is the same refusal discipline as CLAS-04 and EDIT-04: refuse the operation
  visibly with a named reason, never silently. The reason strings should come from the existing
  Phase 2/Phase 3 refusal vocabulary rather than a new parallel set of user-facing strings.

- **D-5.5: One Ctrl+Z reverts an entire replace-all batch as a single step.** EDIT-05 and ROADMAP
  criterion 5. Phase 4's undo store must already admit a batch; this phase is the first thing that
  produces one.

### Claude's Discretion

- Whether the match index is built eagerly at document open or lazily on first search, and how it
  is cached client-side.
- Match-list virtualization / pagination strategy for large result sets.
- How "surrounding context" (FIND-03) is windowed and how much is shown.
- Whether opt-out state (FIND-04) is per-match boolean or a selection model.
- Whether replace-all applies as one recipe with N ops or N recipes; subject to D-11
  (all-or-nothing) from Phase 3 and to D-5.5's single-step undo.
- How progress is reported for a long replace-all across 40 pages.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `CLAUDE.md` — project guidelines
- `.planning/ROADMAP.md` — Phase 5 section: goal, five success criteria, and the "find and replace
  are two features" ordering rationale
- `.planning/REQUIREMENTS.md` — FIND-01..06, plus the **Out of Scope** row on bulk endpoints
- `.planning/phases/04-web-tier-walking-skeleton-hardening/04-CONTEXT.md` and the Phase 4 plans —
  the SPA shell, run index API, apply path, and undo store this phase consumes
- `.planning/phases/02-text-model/02-VERIFICATION.md` and `engine/index.py`, `engine/clusterer.py`,
  `engine/space_threshold.py` — the run index and its normalization, including the tuned
  synthetic-space threshold
- `.planning/phases/03-rewrite-engine-font-pipeline/03-CONTEXT.md` — D-03 (dry-run-first report:
  the preview in criterion 2 renders this data), D-11 (all-or-nothing apply), and the refusal
  vocabulary FIND-05 surfaces
- `engine/recipe.py` — `plan_recipe` / `apply_recipe`, `MAX_RECIPE_OPS`, `MAX_NEW_TEXT_CHARS`,
  `RecipeTooLargeError`. **A 40-page replace-all can plausibly exceed `MAX_RECIPE_OPS`** (D-09's
  recipe-size DoS cap); planning must confront that rather than discover it at execution.
- `harness/masked_diff.py`, `harness/run_corpus_harness.py` — criterion 4's masked differential
  diff, confined to the edited runs on every changed page in all three engines

</canonical_refs>

<specifics>
## Specific Ideas

- ROADMAP criterion 4 pins the validation shape: replace-all across a **40-page corpus contract**
  changes every remaining match in one action, and the masked differential diff is confined to the
  edited runs on every changed page in all three engines. The corpus already carries multi-page
  contracts (`corpus/manifest.json`); the fixture should be a real corpus document, not a
  constructed one, matching the project's "measure the corpus, construct only if it fails"
  discipline.
- "Every *remaining* match" in criterion 4 is deliberate — it means after FIND-04 opt-outs are
  applied. The test must exercise an opt-out, not just a full sweep.
- FIND-02's defaults are specified: case-insensitive substring by default, with working "match
  case" and "whole words only" toggles. Both toggles need their own acceptance criteria.

</specifics>

<deferred>
## Deferred Ideas

- Regex / wildcard search — not in FIND-01..06.
- Search across multiple open documents — no multi-document session model exists.
- Replace with formatting changes (FONT-07 applies to a single edited run in Phase 4; batch
  restyling is not in scope here).

</deferred>

---
*Phase: 05-find-and-replace-across-all-pages*
*Context assembled: 2026-08-30 during batch planning of Phases 4–8*
