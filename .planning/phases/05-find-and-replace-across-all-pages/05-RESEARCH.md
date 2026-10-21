# Phase 5: Find and Replace Across All Pages - Research

**Researched:** 2026-08-31
**Domain:** Client-side text search over a server-issued run index; N-op batch replace through the
existing Phase 3 recipe/apply path. No new engine capability — this phase is an assembly problem,
not an algorithm problem.
**Confidence:** HIGH on engine-contract findings (direct code read + live measurement against real
corpus documents this session). MEDIUM on Phase 4 wire-shape specifics — `04-CONTEXT.md`
Amendment A-4.1 (2026-08-30) reduced the Phase 4 scaffold's status to "route map and dependency
set"; no server endpoint shape is locked yet, so anything cited from `04-RESEARCH.md` below is a
*proposal*, not a contract. MEDIUM-LOW on browser-JS specifics — verified live against Node 22
this session (real behavior, not assumed), but no Phase 5 client code exists yet to anchor file:line
citations against.

*Note on provenance: this document was rebuilt after two session-rate-limit kills lost two prior
attempts. It is written and saved incrementally, section by section, for exactly that reason.*

---

<user_constraints>
## User Constraints (from 05-CONTEXT.md)

### Locked Decisions

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

### Deferred Ideas (OUT OF SCOPE)

- Regex / wildcard search — not in FIND-01..06.
- Search across multiple open documents — no multi-document session model exists.
- Replace with formatting changes (FONT-07 applies to a single edited run in Phase 4; batch
  restyling is not in scope here).

### Amendment affecting this research (04-CONTEXT.md A-4.1, 2026-08-30)

The Phase 4 scaffold's salvage boundary was reduced to "route map and dependency set" — the audit
found it satisfies zero of seven privacy requirements and zero of four ingest requirements, and
most of `server/app.py` is being deleted and rebuilt around `engine.recipe`. **No endpoint shape
in the current scaffold, and no endpoint shape proposed in `04-RESEARCH.md`, is a locked API.**
Every wire-shape reference below is flagged accordingly; this research constrains itself to the
*contract principles* (server owns text/addresses, client echoes `run_id`, no bulk mutate route)
which are locked, not to specific route paths, which are not.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FIND-01 | Search text across all pages, same normalization the interpreter used (TJ adjustments collapsed, ligatures normalized) | §Key Measurement (normalization gap), §Architecture Patterns Pattern 1 |
| FIND-02 | Case-insensitive substring default; "match case" and "whole words only" toggles | §Architecture Patterns Pattern 1, §Code Examples |
| FIND-03 | Match list: page number, surrounding context, live count; click jumps to it | §Architecture Patterns (match data model), §Common Pitfalls |
| FIND-04 | Opt out of individual matches before applying | §Architecture Patterns (match data model + recipe construction) |
| FIND-05 | Unreplaceable matches shown, disabled, with reason — never filtered | §Key Measurement, §Don't Hand-Roll (refusal vocabulary), §Common Pitfalls |
| FIND-06 | Replace all remaining matches across every page in one action | §Key Measurement, §Architecture Patterns Pattern 2 (batch-as-one-recipe) |
</phase_requirements>

## Summary

Phase 5 adds no new engine capability. Every match becomes an ordinary `{run_id, new_text}`
`RecipeOp` (`engine/recipe.py:82`) and the whole batch is one call to the SAME `plan_recipe` /
`apply_recipe` pair Phase 3 built and Phase 4 wires to the browser. The engine already anticipated
this: `apply_recipe`'s own docstring (`engine/recipe.py:601-618`) states, almost verbatim, "this is
not an exotic recipe shape: 'replace this phrase everywhere' hits one page, and one part,
repeatedly" — and the multi-op-per-part re-derivation logic that sentence justifies
(`_rederive_op`, `edited_parts`, `recipe.py:662-712`) is already implemented and regression-tested
(`tests/test_recipe.py::test_apply_recipe_second_op_on_same_part_restores_its_own_font` and
`...uses_its_own_encoding`, lines 950/1063). Phase 5's real work is entirely at the assembly layer:
turn a search query into a set of matches, turn opted-in matches into ops, and — this is the part
the phase context flags and this research confirms is the crux — turn D-11's all-or-nothing
`apply_recipe` semantics into a UX where one bad match never blocks the other 700.

The concrete mechanism: `plan_recipe` (D-03's dry run) must run over the FULL candidate batch
*before* the user is offered "Replace All," not just at commit time. Its per-op `ResolvedOp.ok`/
`reason` (`recipe.py:133-159`) is FIND-05's disabled-with-reason list, literally — this is not two
features that happen to use the same data, it is one dry-run call serving both. Refused ops are
excluded from what gets submitted to `apply_recipe`; only survivors go in. Because the survivor set
already resolved cleanly against the same `source_hash`, the commit call is expected to succeed for
100% of what it's given (baring a source change between preview and commit), so D-11's "op 37 of 50
refuses" scenario is designed away rather than handled — measured directly below, both refusal
families the dry run surfaces (font-mapping-table misses and fit-ladder refusals) already occur on
a real, unmodified 40-page corpus document with no fixture construction required.

**Primary recommendation:** search (FIND-01..05) is pure client-side string matching over
`display_text` already fetched from the server's run index (no algorithm to write beyond a normalize
+ substring/whole-word scan — stdlib `unicodedata.normalize('NFKD', …)` server-side and
`.normalize('NFKD')` client-side, verified byte-identical output for every common Latin ligature);
replace-all (FIND-06) is one `plan_recipe` dry-run call over every included match, followed by one
`apply_recipe` commit call over the ops that dry run marked `ok=True`, landing as one entry in
Phase 4's recipe-is-the-undo-unit stack (`04-RESEARCH.md` §11). Nothing here needs a new dependency,
a new normalization algorithm, or a second rewrite path.

## Key Measurement: MAX_RECIPE_OPS Against a Real 40-Page Corpus Document

The phase context flags this as "the single most likely execution-time surprise in this phase."
Measured directly against `corpus/public/govdocs1_013_013050.pdf` — 40 pages exactly (the one exact
page-count match in the whole 217-file public corpus; see §Architecture Patterns for the candidate
survey), "The Life Cycle of a Mineral Deposit" (USGS teacher's guide), `editable` bucket on every
page, dense running prose.

```
$ uv run --frozen python3 - <<'PY'   # engine.index.RunIndex walked over all 40 pages
pages=40  total_runs=3000  max_runs_on_one_page=153  index_time=5.22s
MAX_RECIPE_OPS=50000  ->  total_runs is 6.000% of the cap
PY
```

`engine/recipe.py:73`: `MAX_RECIPE_OPS = 50_000`. Even in the worst case where **every single run
in the whole 40-page document** matched (3,000 runs), a replace-all recipe would use 6% of the cap.
For an actual common-word replace-all, built by walking every page's runs and replacing all
case-insensitive occurrences within each run's own `display_text` (one `RecipeOp` per run, never
per match — see §Architecture Patterns Pattern 2 for why this is the correct granularity):

| Search term | Matched runs (= ops) | % of `MAX_RECIPE_OPS` | Match instances | `plan_recipe` wall time |
|---|---|---|---|---|
| `"the"` (most common English word) | 772 | 1.5% | 1,029 | 6.86s |
| `"mineral"` (a genuinely common word for this document) | 269 | 0.5% | 292 | 5.81s |

**Verdict: `MAX_RECIPE_OPS` does not bind for the phase's stated 40-page target, and it is not
close.** Reaching it would require either a pathologically common single-run-per-match term across
~650 pages at this document's own run density (50,000 ÷ (772÷3000) ≈ 194,000 total runs ÷ 75
runs/page ≈ 2,600 pages), or a single document near `engine/index.py:63`'s own
`MAX_DOCUMENT_GLYPHS = 10_000_000` pathological-document ceiling. Both are out of this phase's
stated scope (a 40-page document). `04-CONTEXT.md`'s "Engine gaps" list independently reaches the
same conclusion from the other direction — `MAX_RECIPE_OPS` is described there as "a CLI-era number
… not chosen against a web workload" — this measurement is the missing web-workload data point: at
40-page scale it is not the risk it looks like on paper. **Recommendation: do not raise or remove
the cap. Add one integration test asserting a real 40-page replace-all's op count stays under it
(cheap insurance, not a redesign), and leave the cap's actual value as Phase 3/4's decision.**

**The more expensive finding hiding in the same measurement:** `plan_recipe` calls
`classify_document(path)` (`recipe.py:432`, the EAGER whole-document classifier), not the lazy
`RunIndex` the match-list search itself uses. Building the match list (walking `RunIndex` page by
page) and then dry-running the replace (`plan_recipe`, which re-walks the whole document again via
`classify_document`) are two independent full parses of the same document — measured back-to-back
above at ~5.3s + ~6.9s ≈ 12s total for this 40-page document, and Phase 4's own research measured
classify-family costs at ~96s for a 126-page document. This is not a correctness bug — it is a real,
measured latency cost that belongs in the progress-reporting discretion decision (see §Common
Pitfalls and §Architecture Patterns Pattern 3), not a surprise discovered in a demo.

**Real refusals, found on this document with zero fixture construction:** the `"the"→"a"` dry run
above refused 56 of 772 ops (7.3%); `"mineral"→"minerals"` refused 60 of 269 (22.3%) — both entirely
from `MappingVerdict`'s `"no mapping table entry for BaseFont 'Univers-Condensed'"`-family reasons
(`engine/fonts.py:216`) plus a handful of `fit_run` refusals (`engine/fit.py:366`) on the shrinking
case. `report.ok` was `False` for the whole batch in both runs (D-11), which is exactly the scenario
D-5.4/FIND-05 exists for, and it fires on a real, unmodified corpus document, not a constructed
edge case. Full detail and the refusal-vocabulary inventory is in §Don't Hand-Roll and §Common
Pitfalls.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Search query matching (substring/whole-word/case) | Browser / Client | — | D-5.1: "client-side query over the cached index." Pure string ops over already-fetched text; no reason to round-trip per keystroke. |
| Search normalization (TJ-collapse) | API / Backend (already done) | — | D-5.3: baked into `RunRecord.display_text` at classify time (`engine/clusterer.py:261-270`, D-03's synthetic spaces). Never re-derived client-side. |
| Search normalization (ligature fold, case fold) | Browser / Client AND API/Backend (same algorithm, both runtimes) | — | Pure Unicode-standard transform (`NFKD` + casefold), not a heuristic — safe to apply identically in both runtimes without violating D-5.3's "not a second normalization" rule. See §Key Measurement's ligature verification. |
| Match-list data (`run_id`, text, page) fetch | API / Backend | Browser / Client (cache) | D-4.2: server owns text addresses; client never invents a `run_id`. Search needs the server-issued text FIRST, then queries it locally — "client-side query" is not "client-side data." |
| Per-match unreplaceability (classify-time) | API / Backend | Browser / Client (render only) | `RunVerdict.reason` (`engine/classify_run.py`) is server-computed; client renders it verbatim (EDIT-04: never invented prose). |
| Per-match unreplaceability (plan-time / fit refusals) | API / Backend | Browser / Client (render only) | Only knowable via a `plan_recipe` dry run over the actual replacement text — cannot be precomputed at classify time. See §Key Measurement. |
| Recipe construction (matches → ops) | Browser / Client | — | The client already holds the match list, opt-out state, and replacement text; building `{run_id, new_text}` pairs from them is pure client-side assembly, not a server responsibility. |
| Recipe dry-run + commit (`plan_recipe`/`apply_recipe`) | API / Backend | — | D-4.3: unchanged Phase 3 contract. Content-stream rewrite is server-only (`CLAUDE.md` hybrid architecture: "heavy operations … run on the server"). |
| Undo stack | Browser / Client | — | `04-RESEARCH.md` §11: undo lives in the browser; a server-side history is durable per-session state, which PRIV-02 forbids. |

## Standard Stack

**No new runtime dependency is needed for this phase.** Every capability FIND-01..06 requires is
either already in the pinned stack (`CLAUDE.md`) or a standard-library call in an already-used
language. This was checked, not assumed — the searches below found nothing to add. (A dev-only test
framework addition is separately identified in §Validation Architecture's Wave 0 Gaps — that is
tooling, not a product/runtime dependency, and does not contradict this finding.)

### Reused (already pinned, verified present)

| Library | Version | Purpose in Phase 5 | Verified |
|---------|---------|---------------------|----------|
| `engine.recipe` (`plan_recipe`/`apply_recipe`) | in-repo, Phase 3 | The entire replace-all execution path — dry run and commit | Read in full this session; live-measured against real corpus data above |
| `engine.index.RunIndex` | in-repo, Phase 2 | Source of `display_text` the client searches over | Read in full this session |
| Python `unicodedata` (stdlib) | 3.13 (pinned) | Ligature normalization (`NFKD`) — see below | Live-verified this session: `unicodedata.normalize('NFKD', 'ﬁ')` → `'fi'` for all 7 standard Latin ligatures (ﬁ ﬂ ﬀ ﬃ ﬄ ﬅ ﬆ) |
| JS `String.prototype.normalize` (native, ES2015+) | — | Client-side mirror of the same fold | Live-verified this session against Node 22.23.2: byte-identical output to Python's `unicodedata` for the same 7 ligatures |
| React / Vite / pdfjs-dist / `@cantoo/pdf-lib` | pinned in `CLAUDE.md` | Match-list UI, highlight/jump-to-match rendering | Already the pinned client stack; nothing Phase 5 needs is outside it |

### Explicitly rejected (searched for, not needed)

| Considered | Verdict | Why not |
|---|---|---|
| A JS ligature-mapping table / npm package (e.g. hand-rolled `{ 'ﬁ':'fi', … }`) | Rejected | `String.prototype.normalize('NFKD')` is the same Unicode Character Database decomposition table, built into every evergreen browser and Node ≥6. Adding a package or a hand-written table for this is `Don't Hand-Roll` territory — see below. |
| A fuzzy-search / full-text-index library (Fuse.js, lunr, elasticlunr) | Rejected | FIND-02 asks for exact case-insensitive substring / whole-word matching, not fuzzy/ranked search. A library built for ranked relevance search is the wrong tool and adds a dependency for what `String.prototype.includes` plus a fold already does. |
| A JS `unicode-casefold` polyfill | Considered, not required | JS has no native full Unicode case-folding (only `toLowerCase`/`toUpperCase`/`toLocaleLowerCase`), which is a real but narrow gap — documented under Assumptions Log, not treated as blocking, since it only diverges from true casefold on a handful of scripts (e.g. Turkish dotless-ı, German ß) not exercised by the corpus's Latin/CJK content. |

**Version verification:** no new packages, so no new `npm view` / `pip index versions` calls are
needed. The one live check that mattered — whether Python's stdlib and the browser's native string
API agree on ligature decomposition — was run directly (see table above), not assumed from training
data, per this project's own measure-don't-assume discipline.

## Package Legitimacy Audit

**Not applicable to the runtime/product dependency set.** This phase installs zero new external
runtime packages (confirmed above). The one addition anywhere in this research is a **dev-only**
test framework (`vitest`, §Validation Architecture) — MIT-licensed, published by the Vite team
(the same maintainers as the already-pinned `vite`), zero runtime/production footprint. The Package
Legitimacy Gate protocol is written for runtime dependencies installed to serve requests; it is
skipped here, but the choice itself is still justified (ladder rung 5 — an already-installed
project's own sibling tool, not a new unknown package) rather than assumed.

## Architecture Patterns

### System Architecture Diagram

```
 Browser (React SPA)                                    Server (FastAPI + engine/)
 ───────────────────                                    ──────────────────────────
 1. User opens doc, clicks "Find"
        │
        ▼
 2. Sequential per-page fetch  ────GET /pages/{n}/runs──▶  RunIndex.page(n)  (D-06 lazy,
    (page 0, 1, 2, … N-1,          (existing Phase 4        cached per page — reused
     one request at a time,        endpoint shape;          verbatim, not re-derived)
     NOT parallel — see            route path itself is
     Pitfall "concurrent           NOT locked per A-4.1)
     page fetch races the
     server cache")
        │  each response: {run_id, text=display_text, page, box?, state, reason?}
        ▼
 3. Client-side match engine
    normalize(display_text) via NFKD + casefold  ◄── SAME transform run server-side
    substring / whole-word scan, per query            (§Standard Stack) — not re-derived,
    → live match count grows as pages arrive           applied identically in both runtimes
    → match list: page, run_id, offset-in-run,
      ± N chars context (FIND-03)
        │
        ▼
 4. User types replacement text, toggles opt-outs (FIND-04)
        │
        ▼
 5. Client builds a DRAFT recipe: one RecipeOp per
    run with ≥1 INCLUDED match (new_text = that
    run's display_text with only included matches
    substituted — never one op per match instance)
        │
        ▼
 6. "Preview" ───────POST recipe (dry run)────────────▶  plan_recipe(path, recipe)
                                                            (D-03: writes nothing)
        │  ◄────────────── RecipeReport ─────────────────────────┘
        ▼      { ok, resolved: [{op, ok, reason, …}] }
 7. Merge dry-run verdicts into match list:
    ok=False → shown disabled, `reason` rendered
    verbatim (FIND-05) — same reason vocabulary
    as classify-time refusals, one lookup table
        │
        ▼
 8. User clicks "Replace All". Client re-submits
    ONLY the ok=True, still-included ops as the
    real recipe (a subset of step 5/6's draft)
        │
        ▼
 9. "Apply" ─────────POST recipe (commit)─────────────▶  apply_recipe(path, recipe, out)
                                                            (D-11: all-or-nothing; D-13: one
                                                             font subset per family; D-10:
                                                             source_hash re-checked)
        │  ◄──────────── RecipeReport + output ─────────────────┘
        ▼
 10. Client pushes this ONE recipe onto the undo
     stack (04-RESEARCH.md §11: undo unit = one
     recipe of length N) — D-5.5 satisfied for free
```

The critical structural point the diagram is built to make visible: **steps 6/7 and 8/9 call the
SAME two engine functions** (`plan_recipe` then, later, `apply_recipe`, which itself begins with an
internal `plan_recipe` call per `recipe.py:583-584`, "a dry run and a commit of the same recipe are
the same report by construction"). There is no separate "check if replaceable" code path and no
separate "do the replace" code path — one dry run, filtered, becomes the commit.

### Recommended Project Structure

No new server module is required beyond whatever Phase 4 already builds for a single-run edit —
`plan_recipe`/`apply_recipe` already accept a `tuple[RecipeOp, ...]` of *any* length, so a
replace-all submitting 772 ops and a single edit submitting 1 op hit the same endpoint, if Phase 4's
endpoint is written recipe-length-agnostic (it should be; nothing in `engine.recipe` assumes a
length of 1). **Verify this explicitly during planning — it is the one place a Phase-4-first
implementation could accidentally bake in a single-op assumption** (e.g., a request/response
Pydantic model shaped around one run instead of a list).

```
client/src/
├── features/find-replace/
│   ├── search.ts / .js      # pure functions: normalize(), findMatches(text, query, opts) —
│   │                        # zero React/DOM dependency, unit-testable in isolation (this is
│   │                        # the module the mirrored-normalization test in §Validation
│   │                        # Architecture targets)
│   ├── buildRecipe.ts       # matches + opt-outs + replacement text -> RecipeOp[]
│   │                        # (dedupes to one op per run — see Pattern 2)
│   ├── MatchList.tsx        # FIND-03/04/05 UI: context, live count, opt-out, disabled+reason
│   └── useReplaceAll.ts     # orchestrates preview (dry run) -> filter -> commit -> undo push
```

Server-side: no new file is implied by this research beyond whatever Phase 4 names its recipe
route(s). If Phase 4 ships separate `/recipe/preview` and `/recipe/commit` routes (or a single route
with a `commit: bool` flag mirroring `tools/pdftool.py`'s own `--commit` CLI flag,
`tools/pdftool.py:114+`), Phase 5 needs no new route at all — only a client that calls it twice,
once with N draft ops, once with the filtered subset.

### Pattern 1: Search is a pure fold-then-scan over already-fetched text

**What:** `findMatches(runs, query, { matchCase, wholeWord })` — normalize both the haystack
(`run.text`) and the needle (`query`) with the same transform, then a plain substring or
word-bounded scan. No index structure beyond the array of runs already in memory.

**When to use:** Always, for FIND-01/02/03. The corpus measurement above (§Key Measurement) shows
runs are naturally phrase-sized (median 39 chars, p99 88 chars, max 122 chars across the 40-page
document's 3,000 runs) — there is no case in this corpus where a run is long enough to need its own
internal windowing for "surrounding context" (FIND-03); the run's own `display_text` typically *is*
the context.

**Example (mirrors the exact transform verified server-side):**
```python
# Source: direct measurement this session (Python 3.13 stdlib, no import beyond unicodedata)
import unicodedata

def normalize_for_search(s: str) -> str:
    return unicodedata.normalize("NFKD", s).casefold()

normalize_for_search("ﬁnal")  # -> "final" — ligature folded
normalize_for_search("Café")  # -> "café" — NFKD decomposes é to e+combining-acute;
                               #    a plain substring search for "cafe" still matches as a
                               #    PREFIX of this, so accented text is not broken, just not
                               #    specially diacritic-insensitive (out of FIND-02's stated scope)
```
```javascript
// Source: direct measurement this session (Node 22.23.2, native String.prototype)
function normalizeForSearch(s) {
  return s.normalize("NFKD").toLowerCase();
}
normalizeForSearch("ﬁnal");  // -> "final" — byte-identical to the Python output above
```

### Pattern 2: Replace-all is ONE recipe; the op granularity is per RUN, never per MATCH

**What:** A run containing 2 occurrences of the search term produces exactly **one** `RecipeOp`,
whose `new_text` is that run's full `display_text` with only the *included* occurrences substituted
(opted-out occurrences within the same run are left untouched, in place, in the same op).

**Why this is not optional:** `plan_recipe` refuses a recipe containing a duplicate `run_id`
*outright* — every op gets `"duplicate_run_id_in_recipe"`, including ones that were not duplicated
(`recipe.py:419-426`, confirmed by direct read). Two ops naming the same run is not "two edits," it
is a malformed recipe. This was independently confirmed by measurement: the "the" replace-all above
found 1,029 match *instances* across only 772 distinct *runs* (some runs contain 2+ occurrences) —
the correct op count is 772, and the search/match-list data model must therefore carry each match's
**offset within its own run**, not just "this run has a match," so a per-instance opt-out (FIND-04)
can be folded into the single op's `new_text` correctly.

**Data model implication for FIND-03/04:**
```typescript
// One entry per MATCH INSTANCE (for the UI list, opt-out, and live count) —
// but multiple instances sharing a run_id collapse to ONE RecipeOp at build time.
type Match = {
  runId: string;
  page: number;
  startOffset: number;   // offset into that run's display_text
  endOffset: number;
  context: string;       // typically the whole run's display_text (Pattern 1)
  included: boolean;      // FIND-04 opt-out state
  planVerdict?: { ok: boolean; reason: string | null };  // filled in after the dry run, FIND-05
};
```

### Pattern 3: Sequential per-page fetch, not a new bulk-read endpoint

**What:** To search "across all pages" (FIND-01), the client needs every page's run text, which the
server computes lazily per page (`RunIndex.page(n)`, `engine/index.py:139-155`). The lazy, ladder-
rung-2 answer is: the client calls whatever per-page endpoint Phase 4 already builds, once per page,
**sequentially**, accumulating matches and updating the live count (FIND-03) as each response
arrives — not a new bulk endpoint, and not N parallel requests.

**Why sequential, not parallel:** `RunIndex` holds mutable, non-thread-safe state per document
instance — `self._cache: OrderedDict[int, PageIndex]` and `self._font_cache: dict[...]`
(`engine/index.py:110-115`), mutated on every `.page(n)` call (`index.py:157-168`). If the server
keeps one live `RunIndex` per document across requests (the only design that gives D-06's caching
any cross-request value at all — re-opening a fresh `RunIndex` per request, which the pre-A-4.1
scaffold did at `app.py:207`, was flagged in `04-RESEARCH.md` PRIV-07 as a defect, not a feature),
then N concurrent page-fetch requests against the same document race on that shared mutable state.
Sequential client-side fetching sidesteps this by construction, and — a genuine free win, not a
compromise — it produces exactly the incremental "searched N/40 pages, M matches so far" progress
indicator the phase leaves to Claude's discretion, with no new infrastructure.

**Why this is a genuine bulk operation regardless of endpoint shape:** searching "all pages" is
inherently whole-document work — the cost cannot be made to disappear by choosing a different wire
shape, only shown honestly. `04-RESEARCH.md` §10.2 measured the SAME underlying per-page-parse cost
this way for a 126-page document: ~96s to walk every page once, via the identical
`RunIndex.page(n)` loop this phase's own search-across-all-pages must perform, the first time the
document is not already cache-warm from viewing. This is not a VIEW-02 regression to avoid; it is
an unavoidable cost of FIND-01's own definition, applicable regardless of which pages the user
already happened to scroll past.

### Anti-Patterns to Avoid

- **Re-deriving TJ-adjustment collapsing or ligature decomposition client-side from raw glyph
  data.** The client never sees raw glyph data (D-4.2) and must not reconstruct
  `display_text`-equivalent logic from whatever it does see. TJ-collapse is server-computed and
  arrives pre-baked in `display_text`; only the ligature/case fold (a pure Unicode-standard
  transform, not a heuristic) is safe to also run client-side, per the Architectural Responsibility
  Map above.
- **A dedicated bulk find-replace endpoint.** D-5.1/Out of Scope. `plan_recipe`/`apply_recipe`
  already accept a list of any length; a purpose-built "replace all matches of X with Y" endpoint
  would be a second, parallel way to express the same operation and the exact trap `ROADMAP.md`
  names ("two rewrite implementations within six months").
- **Submitting the full, unfiltered match set straight to `apply_recipe`.** Because of D-11
  (all-or-nothing), this single-handedly defeats FIND-06's "changes every remaining match" promise
  the instant one match in a large batch is unreplaceable — measured above, this is not a rare edge
  case (7-22% refusal rates on a real, unmodified document). The dry-run-then-filter step (Pattern
  2 / the diagram) is not an optimization, it is required for correctness.
- **One `RecipeOp` per match instance instead of per run.** Produces `"duplicate_run_id_in_recipe"`
  for every multi-match run and refuses the WHOLE batch, per `recipe.py:419-426`. Confirmed to occur
  in practice — this document's own "the" search has 772 runs sharing 1,029 matches.
- **Firing all N page-run fetches concurrently ("Promise.all across every page") to speed up
  search.** Races the server's per-document `RunIndex` mutable cache state — see Pattern 3.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Ligature normalization (`ﬁ`→`fi`) | A hand-written `{ 'ﬁ': 'fi', … }` lookup table (in either language) | `unicodedata.normalize('NFKD', s)` (Python) / `s.normalize('NFKD')` (JS) | Stdlib in both runtimes, standardized Unicode Character Database decomposition, verified byte-identical output this session for all 7 standard Latin ligatures. A hand-rolled table would need separate maintenance in two languages and would inevitably miss a ligature the standard table already has. |
| Case-insensitive compare | A custom lowercase-and-strip-accents function | `.casefold()` (Python) — closer to true Unicode case folding than `.lower()`/`toLowerCase()`; see Assumptions Log for the one narrow JS gap | Already correct for every script this corpus exercises; a hand-rolled version would re-solve a problem the stdlib already solves correctly. |
| Whole-word boundary detection | A custom tokenizer / whitespace-splitter | Regex `\bterm\b` (both languages) | One line, correct for the ASCII/Latin case this phase's requirements target. See Assumptions Log for the CJK caveat (out of stated scope, flagged not solved). |
| Refusal reason vocabulary for FIND-05 | A new parallel set of user-facing strings | The existing, measured EDIT-04/CLAS-04 vocabulary — full inventory below | D-5.4 says this explicitly. The table below is the *real*, measured vocabulary (not a guess) — every classify-time and plan-time reason string this project's engine currently emits. |
| Masked pixel diff across many edited-run boxes on one page (criterion 4) | A new diff algorithm / a rewrite of `masked_diff.py`'s single-mask signature | Generalize `tests/test_gate_g2b.py:373-403 _two_region_masked_diff`'s own technique (paint every edited-run box the same flat colour onto BOTH before/after renders — this zeroes their contribution — then `masked_pixel_diff(...,mask=None)` on the fully-painted pair) | This exact 2-region version is already written, working, and used by an existing gate test. Generalizing "paint 2 boxes" to "paint N boxes" is a loop-bound change, not new logic. |
| Run bounding box (for match highlight / masked-diff test regions) | Re-deriving glyph→pixel-box math from scratch | `tests/test_gate_g2b.py:111-150 _edited_run_pixel_mask` — glyph x/y/advance + `MASK_VERTICAL_PAD_PT=14.0`/`MASK_HORIZONTAL_PAD_PT=3.0` fixed padding, already measured against a real fixture and ponytail-tagged as a deliberate simplification with a named upgrade path (real font ascent/descent) | Phase 4's own research (§3.1) independently proposed the identical approach for the web-facing hit box before this research found it was **already implemented and measured** in Phase 3's own test suite — strong convergent evidence this is the right lazy solution, not just an assumption. |
| Progress indicator for a 40-page search or replace-all | New polling/websocket/SSE infrastructure | The sequential per-page fetch loop (Pattern 3) already yields one progress tick per page for free | No new infrastructure needed for something a plain `for` loop over existing per-page requests already provides. |

### The full refusal-reason vocabulary (measured, not guessed)

D-5.4 requires FIND-05's reasons come from the *existing* vocabulary. Every string below was found
either by direct code read or by firing a real dry run against a real corpus document this session
— rows marked **MEASURED** actually fired during this research, not just theoretically reachable.

**Classify-time (`RunVerdict.reason`, `engine/classify_run.py`, only when `state="not_editable"`):**

| Reason string | Source | Status |
|---|---|---|
| `f"shared Form XObject, referenced by {n} pages"` | `classify_run.py:212` | **MEASURED** — `irs_1040_tax_tables.pdf` p1/p13, text `"CAUTION"` / `"!"`, referenced by 2 pages |
| `"Type3"` | `classify_run.py:216` | **MEASURED** — `verapdf_type3_font_fixture.pdf`, text `"αβ"` |
| `"right-to-left text"` | `classify_run.py:222` | Code-verified, not fired on a corpus fixture this session |
| `"no /Tf operator precedes this glyph"` | `classify_run.py:152` (via `font_verdict.reason` passthrough) | **MEASURED** — `govdocs1_007_007081.pdf` (708 runs), `govdocs1_011_011095.pdf` (20 runs) |
| `"NOUNI"` | `encoding_table.py:750` (via glyph-verdict passthrough) | **MEASURED** — `mutopia_vocalise_abt.pdf` (232), `govdocs1_004_004119.pdf` (66) |
| `"symbolic simple font, not embedded"` / `"TrueType symbolic with /Encoding present"` / `"cmap subtable directory unreadable"` / `"TrueType with no cmap table"` / `"symbolic TrueType with only a (3,1) cmap"` / `"Type0 with no /DescendantFonts"` / `"mixed-byte-width codespace ranges"` / `"Type0 descendant font not embedded"` / `"Type3 font with no /CharProcs"` / `"unrecognised CIDFont /Subtype …"` / `"unrecognised /Subtype …"` / `"span covered by /ActualText"` | `engine/encoding_table.py` (various `FontVerdict`/`GlyphVerdict` reasons) | Code-verified (`grep` inventory), not individually fired this session |
| `"font resolution lost across clustering"` | `classify_run.py:297` | Code-verified, defensive branch |

**Plan-time (`ResolvedOp.reason`, `engine/recipe.py`, only when `ok=False`):**

| Reason string | Source | Status |
|---|---|---|
| `"malformed_run_id"` / `"source_hash_mismatch"` / `"run_id_not_found"` / `"resolution_failed"` / `"fit_refused"` (fixed backstop) | `recipe.py:137-143` | Code-verified |
| `"duplicate_run_id_in_recipe"` | `recipe.py:423` | Code-verified — this is the one that fires on the anti-pattern above (one op per match instead of per run) |
| `"run_lost_after_earlier_edit"` / `"substitution_key_changed_after_earlier_edit"` | `recipe.py:626-631` | Code-verified — the multi-op-per-part re-derivation guard |
| `f"no mapping table entry for BaseFont {name!r}"` | `engine/fonts.py:216` (`MappingVerdict`, passed through) | **MEASURED** — 52/56 refusals on `"the"→"a"`, 60/60 on `"mineral"→"minerals"` (govdocs1_013_013050.pdf), all `Univers-Condensed`/`UniversLTStd-*Cn` family variants |
| `f"delta {d:.2f}pt exceeds trailing-kern (±{s:.2f}pt) and inter-word-kern (±{m:.2f}pt over {g} gaps) absorption range[; Tz condensing would require …]"` | `engine/fit.py:363-375` (`FitResult.refusal_reason`, dynamic, includes live numbers) | **MEASURED** — 4/56 refusals on `"the"→"a"` |

**Plan implication for the client's reason→copy table:** the fit-ladder reason is a *dynamic*
string with embedded floats, not a fixed enum value — a reason→copy lookup table needs a pattern
match (or a prefix check) for this one, not an exact-string map, plus an explicit fallback row for
any reason string not in this table (this vocabulary will grow — e.g. A-4.2's planned font-size
refusal for FONT-07 does not exist yet).

**Key insight:** this domain's overriding discipline is D-5.3 generalized — don't build a second
version of something Phase 2/3 already solved. Every row above is either already correct in the
engine or already correct in a sibling test file; Phase 5's job is wiring, not invention.

## Common Pitfalls

### Pitfall 1: Submitting the unfiltered match set straight to `apply_recipe`
**What goes wrong:** D-11's all-or-nothing means ONE unreplaceable match blocks the entire batch —
`report.ok=False`, nothing written, no partial credit (`recipe.py:707-711`).
**Why it happens:** "Replace All" reads as one action, so it's natural to build the recipe once and
POST it once.
**How to avoid:** dry run (`plan_recipe`) first over every included match, filter to `ok=True`, THEN
commit only the filtered subset (Pattern 2 / diagram steps 6-9).
**Warning signs:** a replace-all that works on toy fixtures (all-editable, no condensed fonts) but
silently does nothing on any real corpus document — measured above, real documents refuse 7-22% of
a common-word replace-all.

### Pitfall 2: Treating "match count" and "op count" as the same number
**What goes wrong:** `"duplicate_run_id_in_recipe"` fires and refuses the WHOLE recipe the moment
two ops name the same `run_id` (`recipe.py:419-426`).
**Why it happens:** the match list is naturally per-instance (FIND-03's live count counts
instances); it's easy to map that 1:1 into ops without deduplicating by run.
**How to avoid:** group matches by `run_id` before building ops; one op per run, `new_text` reflects
every *included* match within that run (Pattern 2).
**Warning signs:** works for search terms that never repeat within one line/run; breaks the moment a
run contains the term twice — exactly what happened with hundreds of this corpus document's own
runs for "the" (1,029 instances / 772 runs = ~1.33 avg, meaning many runs have 2+ matches).

### Pitfall 3: FIND-05 shown from classify-time verdicts only, missing plan-time fit refusals
**What goes wrong:** a match on a run that is `editable_original` at classify time (Phase 2) can
still refuse at plan time (Phase 3's fit ladder or mapping table) once the ACTUAL replacement text is
known — measured directly: `govdocs1_013_013050.pdf` has **zero** classify-time `not_editable` runs
(bucket survey: `{'editable_original': 3000}`) yet 56-60 of its runs refuse a real replace-all at
plan time. A FIND-05 implementation that only reads `RunVerdict.reason` and never calls
`plan_recipe` will show 100% of matches as replaceable right up until the user clicks Apply and a
chunk of them silently fail (or, worse, block the WHOLE batch per Pitfall 1).
**Why it happens:** classify-time refusal (CLAS-04) is the more visible, more heavily-documented
vocabulary; the fit-ladder/mapping-table refusal only exists once real replacement text is plugged
in, which happens later in the user's workflow (D-5.2's "find before replace" ordering).
**How to avoid:** FIND-05's disabled-with-reason list must be refreshed by re-running the dry run
whenever the replacement text changes (debounced — `plan_recipe` measured at ~6-7s for a few hundred
ops on a 40-page document, so this must NOT run per keystroke; debounce on pause-in-typing, or gate
behind an explicit "Preview" action).
**Warning signs:** a demo that only shows classify-time refusals (Type3/symbolic/RTL) and never a
mapping-table or fit-ladder refusal, on ANY corpus document, is under-testing this requirement.

### Pitfall 4: Concurrent per-page fetches racing the server's `RunIndex` cache
**What goes wrong:** `RunIndex._cache` (`OrderedDict`) and `_font_cache` (`dict`) are mutated on
every `.page(n)` call with no locking (`engine/index.py:110-115,157-168`). If the client fires many
page-run requests in parallel against a server that keeps one live `RunIndex` per document (the only
design giving cross-request caching any value), concurrent mutation of that shared state is a real
race, not a theoretical one.
**Why it happens:** parallelizing "fetch all 40 pages" looks like an obvious speed win.
**How to avoid:** fetch sequentially (Pattern 3) — it's also required for the incremental-progress
UX (Claude's Discretion item), so there's no tradeoff being made, only a win being taken.
**Warning signs:** intermittent wrong/missing page data under load, worse with more concurrent users
searching the same or different documents simultaneously; hard to reproduce in a single-request dev
test.

### Pitfall 5: Reading "client-side query" as "no server round trip"
**What goes wrong:** D-5.1's "client-side query over the cached index" describes where the STRING
MATCHING algorithm runs, not where the DATA comes from. The client cannot derive `display_text`
from raw PDF bytes itself (D-4.2: the server owns text addresses; content-stream parsing is
server-only per `CLAUDE.md`'s hybrid architecture). Misreading this can lead an implementer toward
re-deriving TJ-collapse client-side from raw glyph positions — exactly the "second normalization
path" D-5.3 forbids.
**How to avoid:** state explicitly in planning that "client-side query" means "client-side string
matching over server-fetched, server-normalized text," and that fetching that text is an
unavoidable, potentially slow (§Key Measurement), server round trip.

### Pitfall 6: A single fixture cannot exercise every criterion-4 clause
**What goes wrong:** `govdocs1_013_013050.pdf` (the exact 40-page match) has **zero** classify-time
refusals — good for proving "every remaining match" mechanics at scale, insufficient alone for
proving FIND-05's disabled-with-reason UI renders a *classify-time* reason (it CAN prove a plan-time
reason, per Pitfall 3/§Key Measurement). `irs_1040_tax_tables.pdf` (28 pages) supplies the missing
case: a real, findable, disabled-with-reason match (`"CAUTION"`, shared Form XObject).
**How to avoid:** plan at least two corpus fixtures for FIND-05/criterion-4 coverage — see
§Validation Architecture's test map for the specific documents and reasons each one proves.

### Pitfall 7: `\b` word-boundary regex is ASCII-only in both Python and JS
**What goes wrong:** FIND-02's "whole words only" toggle, implemented as `\bterm\b`, is correct for
Latin-script text but not meaningfully defined for languages without ASCII word characters between
tokens (the corpus has one CJK document, `wikipedia_zh_monthly_magazine.pdf`).
**How to avoid:** not solved here — flagged in Open Questions. FIND-01..06's own wording does not
call out non-Latin scripts, so this is not blocking, but an implementer should not assume "whole
words" is well-defined for the one CJK fixture the corpus happens to include.

## Code Examples

### Whole-word / match-case query construction
```javascript
// Source: standard regex construction, verified against Node 22.23.2 this session
function buildMatcher(query, { matchCase, wholeWord }) {
  const normalize = (s) => (matchCase ? s : s.normalize("NFKD").toLowerCase());
  const escaped = normalize(query).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = wholeWord ? `\\b${escaped}\\b` : escaped;
  return { pattern, normalize };
}
// Same construction in Python for the (optional) server-side mirror / test parity check
import re
def build_matcher(query, match_case, whole_word):
    normalize = (lambda s: s) if match_case else (lambda s: unicodedata.normalize("NFKD", s).casefold())
    escaped = re.escape(normalize(query))
    pattern = rf"\b{escaped}\b" if whole_word else escaped
    return pattern, normalize
```

### Dry-run-then-filter (the core replace-all mechanism)
```python
# Source: direct read of engine/recipe.py this session — this is the shape plan_recipe/
# apply_recipe already impose, not a new design
draft_recipe = build_ops(matches, included_only=True)   # Pattern 2: one op per run
report = plan_recipe(pdf_path, draft_recipe)             # engine/recipe.py:369 — writes nothing
for resolved in report.resolved:
    match_list.set_verdict(resolved.op.run_id, ok=resolved.ok, reason=resolved.reason)  # FIND-05

commit_recipe = tuple(r.op for r in report.resolved if r.ok)
if commit_recipe:
    final_report = apply_recipe(pdf_path, commit_recipe, output_path)  # engine/recipe.py:562
    # final_report.ok is expected True for every op in commit_recipe — it already passed
    # the identical resolution plan_recipe just ran, against the same source_hash
```

### N-region masked diff (generalizing the existing 2-region test helper)
```python
# Source: tests/test_gate_g2b.py:373-403 _two_region_masked_diff, generalized from 2 boxes to N.
# The technique is unchanged: paint every excluded box the SAME flat colour onto copies of BOTH
# images (making those pixels contribute zero diff by construction), then diff with mask=None —
# simpler than the original's "N-1 painted + 1 passed through masked_pixel_diff's own mask=" split,
# and correct for any N >= 0 without special-casing N=1.
def _n_region_masked_diff(png_a, png_b, boxes, scratch_dir):
    scratch_dir.mkdir(parents=True, exist_ok=True)
    masked = []
    for index, source in enumerate((png_a, png_b)):
        target = scratch_dir / f"{index}.png"
        with Image.open(source) as image:
            rgb = image.convert("RGB")
            for box in boxes:
                rgb.paste((0, 0, 0), box)
            rgb.save(target)
        masked.append(target)
    return int(masked_pixel_diff(masked[0], masked[1], mask=None))
```

## State of the Art

This phase has no external-ecosystem trend to track — the relevant "state of the art" is entirely
internal: what an earlier, now-partially-deleted prototype got wrong, and what the current engine
already gets right.

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Search/replace via `pdfjs-dist`'s `getTextContent()` items | Search over server-issued `RunRecord.display_text`, addressed by `run_id` | Settled by D-4.2 (Phase 4, "do not relitigate") | `getTextContent()` items are rendering groupings, not content-stream runs (`CLAUDE.md` "What NOT to Use"); they do not map 1:1 to what the server can edit. Using them for search would produce matches the replace path cannot act on. |
| `server/engine_replace.py`'s pre-G2b fork (saved output even after collecting refusals, no `source_hash` check) | `engine.recipe.plan_recipe`/`apply_recipe` (D-10/D-11 enforced) | Identified as a defect in `04-CONTEXT.md` A-4.1 and slated for deletion, not patching | The prototype's "replace this pattern" code is the negative example of what Phase 5 must not resemble — it violated the exact all-or-nothing/hash-check guarantees this research leans on to make batching safe. |
| Whole-document eager classification for any read need | `RunIndex`'s lazy per-page cache (D-06) | Phase 2 | Still the right tool for VIEWING; this research's own finding is that a true "search all pages" action is inherently whole-document work regardless (§Architecture Patterns Pattern 3) — an important nuance, not a regression back to the old approach. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|----------------|
| A1 | `plan_recipe`'s dry-run endpoint (or equivalent) will be recipe-length-agnostic when Phase 4 builds it, not hard-coded to one op | Architecture Patterns, Recommended Project Structure | If Phase 4 ships a single-op-shaped request model, Phase 5 needs a Phase-4-touching change to submit N ops, not just new client code — re-verify Phase 4's actual request/response schema once it exists, since A-4.1 confirms no schema is locked yet |
| A2 | JS `String.prototype.normalize('NFKD')` and Python `unicodedata.normalize('NFKD', …)` will continue to agree for any character actually present in this project's bundled/substitution fonts, beyond the 7 ligatures spot-checked this session | Standard Stack, Pattern 1 | Both implement the same versioned Unicode Character Database, so divergence is unlikely, but only 7 characters were actually checked, not the full corpus's character inventory |
| A3 | The server keeps one live `RunIndex` per document across requests (not a fresh one per request) once Phase 4 is (re)built post-A-4.1 | Pattern 3, Pitfall 4 | If Phase 4 instead re-opens a fresh `RunIndex` per request (as the now-being-deleted scaffold did), the concurrency race in Pitfall 4 does not exist, but neither does any cross-request caching benefit — the sequential-fetch recommendation is still correct either way, but the *reason* changes from "avoid a race" to "avoid redundant full re-parses per request" |
| A4 | JS `\b` regex word-boundary behavior (ASCII-`\w`-only in non-Unicode mode) is standard, well-documented ECMAScript behavior | Common Pitfalls Pitfall 7, Code Examples | Extremely low risk — this is long-standing, spec-defined behavior, not a claim needing runtime verification, but flagged since it directly limits FIND-02's "whole words" correctness on non-Latin scripts |
| A5 | "40-page corpus contract" in `ROADMAP.md` criterion 4 refers to a corpus-sourced fixture of approximately that scale, not a literal legal-contract document or an exact page count | Key Measurement, Validation Architecture | Low risk — no literal "contract" (legal-agreement) document exists in the 217-file public corpus (verified by manifest/notes grep), and the exact-40-page match is a USGS teacher's guide, not a contract. If a literal contract-typed document at exactly 40 pages is actually required, this assumption is wrong and a fixture would need to be sourced or constructed — flagged rather than guessed past |

**If this table is empty:** not applicable — see rows above.

## Open Questions

1. **What exact server endpoint shape will Phase 4 land for recipe dry-run vs. commit?**
   - What we know: `plan_recipe`/`apply_recipe` are the underlying functions and already share a
     report shape (D-03); `04-RESEARCH.md` proposes `GET /jobs/{id}/pages/{n}/runs` for read and
     implies symmetric preview/commit recipe routes, but per A-4.1 none of this is locked.
   - What's unclear: route paths, whether preview/commit are one route with a flag or two routes,
     request/response Pydantic model shapes.
   - Recommendation: Phase 5 planning should treat this as a Phase 4 output to consume, not
     pre-design; the client-side contract this research assumes (submit a list of `{run_id,
     new_text}`, get back a per-op ok/reason list) is the part that's actually locked (it's
     `engine.recipe`'s own public shape), and is enough to plan Phase 5's client logic against
     independent of the exact route.

2. **Does "whole words only" need to mean anything for the corpus's one CJK document?**
   - What we know: JS/Python `\b` is ASCII-`\w`-based; FIND-02's requirement text doesn't scope to
     Latin-only.
   - What's unclear: whether this is a real product requirement gap or simply out of this phase's
     practical scope (no CJK fixture appears in the phase's own success criteria).
   - Recommendation: treat as out of scope unless the planner/product owner says otherwise; do not
     silently ship broken CJK whole-word matching without a decision that it's acceptable.

3. **Should there be a page-count or estimated-cost warning before a "search all pages" action on a
   very large, not-yet-cache-warm document?**
   - What we know: measured ~5.3s for 40 pages, and Phase 4 research measured ~96s for 126 pages —
     both for the SAME underlying per-page walk this phase's search must also perform.
   - What's unclear: whether this phase's scope includes any UX for the (out-of-target-range) case
     of a much larger document, or whether that's accepted as "slow but correct, no special case."
   - Recommendation: no special case needed for the phase's stated 40-page target; note the ~96s
     number in the plan so it isn't rediscovered as a surprise if a reviewer tests a larger corpus
     document.

## Environment Availability

**Skipped.** This phase has no new external dependency, service, or CLI tool beyond what Phases
1-4 already require and (per those phases' own research) have already verified available in this
environment (`uv`, `pikepdf`/`playa`/`fontTools`/`uharfbuzz`/`pypdfium2` for the engine reused
unchanged; Node/npm for the client, already probed working this session — `node --version` →
`v22.23.2`).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework (server/engine) | pytest ≥9.1.1 (already configured, reused unchanged from Phase 3) |
| Framework (client) | **none exists yet** — `client/package.json` has no test script and no `vitest`/`jest` devDependency (measured this session). Recommend `vitest`: MIT, maintained by the Vite team (same maintainers as the already-pinned `vite`), zero-config against the existing `vite.config.js`. This is the phase's one Wave 0 tooling gap. |
| Config file (server) | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths=["tests"]` (existing) |
| Config file (client) | `client/vitest.config.ts` or a `test` block added to the existing `vite.config.js` — ❌ Wave 0 |
| Quick run command (server) | `uv run --frozen pytest -q -m "not corpus" tests/test_recipe.py tests/test_find_replace_recipe.py` |
| Quick run command (client) | `npm --prefix client test` (❌ Wave 0 — script does not exist yet) |
| Full suite command | `uv run --frozen pytest -q` (server, includes `corpus`-marked) + `npm --prefix client test` (client) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| FIND-01 | Ligature fold matches interpreter normalization (7 standard Latin ligatures) | unit (client) | `npm --prefix client test -- search.test.ts -t "normalizes ligatures"` | ❌ Wave 0 |
| FIND-01 | Client and server normalization agree on real corpus text, not just the 7 spot-checked ligatures (closes Assumption A2) | corpus | `pytest -m corpus tests/test_find_normalize_parity.py::test_js_and_python_nfkd_agree_on_corpus_text -x` | ❌ Wave 0 |
| FIND-02 | Case-insensitive substring is the default | unit (client) | `npm --prefix client test -- search.test.ts -t "case insensitive by default"` | ❌ Wave 0 |
| FIND-02 | "Match case" toggle changes results | unit (client) | `npm --prefix client test -- search.test.ts -t "match case toggle"` | ❌ Wave 0 |
| FIND-02 | "Whole words only" toggle changes results | unit (client) | `npm --prefix client test -- search.test.ts -t "whole word toggle"` | ❌ Wave 0 |
| FIND-03 | Match list shows page number, context, live count (data) | unit (client, component) | `npm --prefix client test -- MatchList.test.tsx -t "renders page context and live count"` | ❌ Wave 0 |
| FIND-03 | Click a match jumps to it (journey) | recorded manual check (per `04-CONTEXT.md` A-4.3 precedent: journey rows are recorded, not automated, absent an e2e browser harness) | N/A — dated results doc with a `## Decision` header, per `G2B-GATE-RESULTS.md`'s precedent | ❌ Wave 0 (no e2e harness) |
| FIND-04 | Opted-out match instance excluded from the built `RecipeOp.new_text` | unit (client) | `npm --prefix client test -- buildRecipe.test.ts -t "opted-out instance excluded, run still edited for remaining matches"` | ❌ Wave 0 |
| FIND-05 | Classify-time-refused match (`"shared Form XObject"`) shown disabled with reason, never filtered | corpus integration | `pytest -m corpus tests/test_find_replace_recipe.py::test_shared_xobject_match_shown_disabled_with_reason -x` (fixture: `corpus/public/irs_1040_tax_tables.pdf`, term `"CAUTION"`) | ❌ Wave 0 |
| FIND-05 | Plan-time-refused match (font-mapping-table miss) shown disabled with reason, never filtered | corpus integration | `pytest -m corpus tests/test_find_replace_recipe.py::test_mapping_table_refusal_shown_disabled_with_reason -x` (fixture: `corpus/public/govdocs1_013_013050.pdf`, term `"mineral"`→`"minerals"`) | ❌ Wave 0 |
| FIND-05 | Unknown/future reason string falls back to a generic disabled state, never crashes the UI | unit (client) | `npm --prefix client test -- reasonCopy.test.ts -t "unknown reason falls back gracefully"` | ❌ Wave 0 |
| FIND-06 | Op count for a real 40-page replace-all stays under `MAX_RECIPE_OPS` (cheap insurance per §Key Measurement) | corpus | `pytest -m corpus tests/test_find_replace_recipe.py::test_40page_replace_all_op_count_under_cap -x` (fixture: `govdocs1_013_013050.pdf`) | ❌ Wave 0 |
| FIND-06 | Dry-run-then-filter: refused ops excluded, committed ops all resolve `ok=True` | integration | `pytest tests/test_find_replace_recipe.py::test_filtered_commit_matches_dry_run_verdicts -x` | ❌ Wave 0 |
| FIND-06 | Multi-match-per-run collapses to one op (Pattern 2), no `duplicate_run_id_in_recipe` | unit (client) + integration | `npm --prefix client test -- buildRecipe.test.ts -t "collapses multiple matches in one run to one op"` AND `pytest tests/test_find_replace_recipe.py::test_multi_match_run_produces_single_op -x` | ❌ Wave 0 |
| G4 criterion 4 | Replace-all changes every REMAINING match (opt-out exercised) across the 40-page corpus contract; masked diff confined to edited runs, on every changed page, in all 3 engines | corpus + pixel-diff (gate) | `pytest -m corpus tests/test_gate_g4.py::test_g4_replace_all_masked_diff_all_engines -x` (fixture: `govdocs1_013_013050.pdf`; N-region mask per §Code Examples) | ❌ Wave 0 |
| D-5.5 / G4 criterion 5 | One Ctrl+Z reverts the entire replace-all batch as a single step | unit (client, undo stack) | `npm --prefix client test -- useReplaceAll.test.ts -t "single undo reverts whole replace-all batch"` | ❌ Wave 0 |
| (existing coverage, not new) | `MAX_RECIPE_OPS`/`MAX_NEW_TEXT_CHARS` parse-time boundary | unit (already exists) | `uv run --frozen pytest tests/test_recipe.py -k max_ops` | ✅ Exists (`tests/test_recipe.py`, boundary test already present — Phase 5 does not need to re-test `parse_recipe`'s own cap, only that realistic usage stays under it, per the row above) |

### Sampling Rate

- **Per task commit:** `uv run --frozen pytest -q -m "not corpus" tests/test_recipe.py tests/test_find_replace_recipe.py` (server) + `npm --prefix client test` (client) — fast, hand-picked fixtures named above (`govdocs1_013_013050.pdf` "the"/"mineral" runs, `irs_1040_tax_tables.pdf` "CAUTION" run — all already-measured, named-by-run examples, not freshly discovered each time).
- **Per wave merge:** `uv run --frozen pytest -q` (includes `corpus`-marked tests, ~12s+ per corpus-touching test per the measurements above — expect this suite to take longer than Phase 3's, budget for it) + `npm --prefix client test` (client full suite) + `mypy engine/` (existing project convention, unchanged).
- **Phase gate:** full suite green, plus `tests/test_gate_g4.py` run directly against the two named fixtures, plus `04-CONTEXT.md` A-4.3's recorded-manual-check for the journey row (click-to-jump) — a dated results document with a `## Decision` header and an explicit "what was NOT tested" section, following the `G2B-GATE-RESULTS.md` precedent — before `/gsd:verify-work`.

### Wave 0 Gaps

- [ ] `client` test framework: add `vitest` devDependency + `client/vitest.config.ts` (or extend
      `vite.config.js`) and an `npm test` script — none exists today.
- [ ] `client/src/features/find-replace/search.ts` + `search.test.ts` — normalize/match logic,
      framework-free.
- [ ] `client/src/features/find-replace/buildRecipe.ts` + `buildRecipe.test.ts` — matches → ops,
      the per-run dedup logic (Pattern 2).
- [ ] `client/src/features/find-replace/reasonCopy.ts` — the reason-string → user-facing-copy
      lookup, including the dynamic fit-ladder-reason prefix match and the explicit unknown-reason
      fallback (§Don't Hand-Roll vocabulary table).
- [ ] `tests/test_find_replace_recipe.py` — server/engine-level integration tests for the
      dry-run-then-filter flow, using the exact named corpus fixtures/terms measured in this
      research (no new fixture construction needed).
- [ ] `tests/test_find_normalize_parity.py` — cross-checks the JS and Python NFKD+casefold
      transforms agree on real corpus text, not just the 7 ligatures spot-checked this session
      (closes Assumption A2); likely shells out to `node` the way this research did.
- [ ] `tests/test_gate_g4.py` — the masked-diff-all-engines gate test, generalizing
      `_two_region_masked_diff` from `tests/test_gate_g2b.py` to N regions (§Code Examples),
      against `govdocs1_013_013050.pdf`.
- [ ] Confirm whatever recipe dry-run/commit endpoint(s) Phase 4 ships accept a `RecipeOp` list of
      arbitrary length (Assumption A1) — a five-minute check once Phase 4's server code exists,
      before Phase 5 client work assumes it.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | No accounts in v1 (`CLAUDE.md`); unchanged by this phase |
| V3 Session Management | No (inherited from Phase 4) | This phase adds no new session concept; it reuses whatever job/session handle Phase 4 establishes |
| V4 Access Control | No | No multi-tenant/multi-user surface |
| V5 Input Validation | Yes | The search query and replacement text are user input that ultimately becomes `RecipeOp.new_text`, reaching the server through `parse_recipe`'s existing untrusted-input boundary (`recipe.py:95-129`: stdlib `json.loads`, exact-key check, `MAX_RECIPE_OPS`/`MAX_NEW_TEXT_CHARS` bounds checked before any per-op object is built). Phase 5 must submit through this exact path — never construct `RecipeOp` objects server-side from a request body without going through `parse_recipe`, which would bypass its bounds checks. |
| V6 Cryptography | No | No cryptographic operations in this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-------------------------|
| A crafted, oversized recipe submitted directly to the API (bypassing the real search UI entirely — e.g. 50,000 synthetic ops) used to exhaust server CPU/memory | Denial of Service | Already the existing `MAX_RECIPE_OPS`/`MAX_NEW_TEXT_CHARS` bound in `parse_recipe` (`recipe.py:73,78,108-113`), reused unchanged — §Key Measurement shows legitimate 40-page usage sits at 0.5-1.5% of this cap, so the existing bound has ample headroom without needing to be loosened for real traffic. `04-RESEARCH.md` §3.4 additionally flags that the recipe route itself needs a request-body size cap applied *before* `json.loads` — that is Phase 4's implementation task, inherited here, not solved anew. |
| A maximal recipe (near `MAX_RECIPE_OPS`, every op requiring font substitution/shaping) imposing real per-request CPU cost via `plan_recipe`'s `uharfbuzz` shaping work | Denial of Service | Same existing bound as above. The framing shift this phase introduces: this cost profile is no longer purely a hypothetical-attacker scenario — a legitimate large replace-all now produces genuinely large ops sets as expected traffic (measured: ~7s of `plan_recipe` time for a few hundred ops on a 40-page document). Confirm the existing cap and any Phase 4 request-timeout setting jointly tolerate the phase's own realistic peak (measured above), not just small requests. |
| Content-stream injection via `new_text` (a replacement string crafted to break out of its PDF string literal) | Tampering | Already structurally prevented by construction — `pikepdf.String(...)` / `unparse_content_stream` correctly escape/encode the string (documented in `03-RESEARCH.md`'s own Security Domain, reused unchanged). Phase 5 introduces no new code path that builds content-stream bytes via raw string formatting; every `new_text`, however constructed by the search/replace UI, flows through the same pikepdf operand types as a single-run edit. |

## Sources

### Primary (HIGH confidence — direct measurement or direct code read this session)
- `engine/recipe.py` — read in full; `MAX_RECIPE_OPS`/`MAX_NEW_TEXT_CHARS` (:73,:78), `RecipeOp`
  (:82), `parse_recipe` (:95), `plan_recipe` (:369, including its `classify_document` call at
  :432), `apply_recipe` (:562), the multi-op-per-part re-derivation (`_rederive_op`/`edited_parts`,
  :662-712), `"duplicate_run_id_in_recipe"` (:423)
- `engine/index.py` — read in full; `RunIndex` mutable cache state (`_cache`, `_font_cache`,
  :110-115), `_parse_page`/`page` (:139-168), `MAX_DOCUMENT_GLYPHS` (:63)
- `engine/classify_run.py` — read in full; `classify_run` (:187-232), `_is_rtl` (:172), refusal
  reason strings
- `engine/clusterer.py` — read; `_display_text`, K_EM/BREAK_EM synthetic-space logic (:261-270)
- `engine/records.py`, `engine/space_threshold.py`, `engine/fonts.py`, `engine/fit.py` — read for
  the refusal-vocabulary inventory and normalization-gap analysis
- `engine/shared_xobjects.py` — read, including its own `govdocs1_013_013085.pdf` "7 shared / max
  36" measurement note used to locate the shared-XObject fixture candidate
- Live measurement this session: `RunIndex` walked over `corpus/public/govdocs1_013_013050.pdf`
  (40 pages, 3,000 runs); `plan_recipe` dry-run timing and refusal counts for `"the"→"a"` and
  `"mineral"→"minerals"`; bucket/state surveys across 15+ corpus documents to locate FIND-05
  fixtures; `python3 -c "unicodedata.normalize(...)"` and `node -e "...normalize(...)"` ligature
  parity check (Node 22.23.2)
- `tests/test_gate_g2b.py` — read; `_edited_run_pixel_mask` (:111-150), `_two_region_masked_diff`
  (:373-403), `render_all`/`_ENGINE_LABELS` usage (:238-250)
- `harness/masked_diff.py`, `harness/render_diff.py` — read; `masked_pixel_diff` single-mask
  signature, `RENDER_DPI`/`_SCALE` (`render_diff.py:31-32`)
- `harness/run_corpus_harness.py` — read; three-engine cross-comparison structure, `check_file`
  (:189-236)
- `tests/test_recipe.py` — grepped for existing coverage (`MAX_RECIPE_OPS` boundary test, the
  same-part regression tests at :950/:1063)
- `corpus/manifest.json` and `corpus/public/*` — measured page counts for all 217 entries; searched
  notes for "contract"/"agreement"/"lease" (none found, see Assumption A5)
- `CLAUDE.md` — read for stack/licensing constraints, confirmed nothing new is needed
- `client/package.json` (on `main`) — read; confirmed no test framework configured

### Secondary (MEDIUM confidence — this session's Phase 4 research, itself HIGH-confidence but
describing interfaces not yet implemented per A-4.1)
- `04-RESEARCH.md` §1.2 (recipe contract surface), §3.1 (run bounding box derivation — independent
  convergence with this session's own `tests/test_gate_g2b.py` finding), §3.4 (`MAX_RECIPE_OPS` as
  "a CLI-era number"), §4 (client MAY/MUST NOT table, proposed wire shape), §10.2 (VIEW-02's
  126-page/~96s measurement, reused directly for this phase's own search-cost analysis), §11
  (EDIT-05 undo store = one recipe per batch)
- `04-CONTEXT.md`, including the `## Amendments` section (A-4.1, A-4.2, A-4.3, A-4.4) — read in
  full this session

### Tertiary (LOW confidence — none. Every claim in this document is either a direct code read, a
live measurement, or an explicitly-flagged assumption in the Assumptions Log above.)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependency, and the one claim requiring runtime verification
  (JS/Python NFKD parity) was directly measured, not assumed.
- Architecture (batch-as-one-recipe, dry-run-then-filter): HIGH — derived from direct reads of
  `engine/recipe.py`'s own documented behavior and confirmed by live measurement against real
  corpus data, not inferred from requirements text alone.
- Pitfalls: HIGH for the engine-contract pitfalls (all reproduced live); MEDIUM for the
  concurrency-race pitfall (Pitfall 4), which is architecturally sound reasoning from real mutable
  state in `engine/index.py` but was not reproduced under actual concurrent load this session
  (no server exists yet to load-test).
- Validation Architecture: MEDIUM — test file paths and fixture choices are concrete and
  measurement-backed, but the client test framework itself does not exist yet (Wave 0), and no
  Phase 5 client code exists to anchor exact test file locations beyond the recommended structure.

**Research date:** 2026-08-31
**Valid until:** Tied to Phase 4's implementation landing, not a fixed calendar window — every
wire-shape claim here is explicitly flagged MEDIUM confidence pending Phase 4's actual server code
(per A-4.1, nothing is locked yet). The engine-contract findings (HIGH confidence) are stable until
`engine/recipe.py`/`engine/index.py`/`engine/classify_run.py` themselves change, which only Phase
3/4 work would do.
