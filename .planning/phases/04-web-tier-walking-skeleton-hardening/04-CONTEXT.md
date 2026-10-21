# Phase 4: Web Tier Walking Skeleton + Hardening - Context

**Gathered:** 2026-08-30
**Status:** Ready for planning
**Source:** Batch planning pass (no `/gsd:discuss-phase` run). Phase boundary and constraints are
transcribed from `ROADMAP.md` and `REQUIREMENTS.md`, which already carry unusually specific,
pre-locked success criteria for this phase. Two decisions below (D-4.1, D-4.2) were taken by the
maintainer directly during this planning pass. Everything not listed as a decision is explicitly
Claude's Discretion — the researcher and planner are expected to resolve it, not to assume a
preference that was never expressed.

<domain>
## Phase Boundary

A stranger can open the site with an untrusted PDF, see it rendered faithfully, understand exactly
what is and is not editable and where each operation runs, edit one text run, and undo it — with
nothing about the session surviving on the server.

This is **Gate G3**, and its gate is one indivisible claim: *safe to hand a stranger*. It is the
project's first public-exposure boundary and the largest phase by requirement count (20),
deliberately so.

**In scope:** INGE-01..04, PRIV-01..07, VIEW-01..04, CLAS-06, CLAS-07, EDIT-01, EDIT-05, FONT-07.

**Explicitly NOT in scope:**
- Find-and-replace across all pages (Phase 5) — this phase ships a *single*-run edit round trip.
- Page ops and merge (Phase 6), exports (Phase 7), PDF/A + DOCX (Phase 8).
- A second rewrite implementation. The server calls the Phase 3 `engine.recipe` contract. A
  `POST /find-replace`-shaped bulk endpoint is named in REQUIREMENTS.md "Out of Scope".
- White-box overlay editing as a fallback (permanent anti-feature, `CLAUDE.md`).
- Accounts, cloud-storage OAuth, AI chat over documents (all v2 or out of scope).

## Hard Dependency

Phase 3 (Gate G2b) has **passed** — see
`.planning/phases/03-rewrite-engine-font-pipeline/G2B-GATE-RESULTS.md` (GO, 2026-08-28, all D-15
clauses: five automated, one extended-scope automated, three human-verified). The roadmap's "no web
tier before G2b" constraint is therefore satisfied and this phase is unblocked.

**However, the Phase 3 engine is not on `main`.** It lives on branch
`worktree-gsd-phase-3-rewrite-engine-font-pipeline` (HEAD `0d53320`), which is 45 commits ahead of
`main`. `main` has `pdftool index` but not `pdftool edit`, and no `engine/recipe.py`,
`engine/rewrite.py`, `engine/fit.py`, `engine/fonts.py`, or `fonts/`. Porting the Phase 3 engine
onto the web tier's branch is a **prerequisite task inside this phase**, not an assumption.

</domain>

<decisions>
## Implementation Decisions

### Pre-existing scaffold

- **D-4.1: Salvage the existing `server/` + `client/` prototype rather than replan clean.**
  (Maintainer decision, 2026-08-30.) **AMENDED 2026-08-30 after research — see
  `## Amendments` at the end of this file. The salvage boundary is now explicitly "route map
  and dependency set", not "partial implementation". Read the amendment before planning.** A FastAPI + React/Vite scaffold already exists on `main`
  (commit `0acd3eb`): `server/app.py` (~40KB), `server/engine_replace.py`, `server/ephemeral.py`,
  `server/font_subsetter.py`, `client/` with pdfjs-dist and `@cantoo/pdf-lib`. It was written
  ahead of the roadmap's intended order (before G2b) and is not GSD-planned. Phase 4 plans build
  **on** it — port the Phase 3 engine to it, fix its known defects, then harden — rather than
  starting from an empty directory.

  **Accepted cost, and the planner must design against it:** every scaffold decision predates any
  review against PRIV-01..PRIV-07 and INGE-01..INGE-04. Salvage is not endorsement. The plans must
  audit the scaffold against each privacy and ingest requirement explicitly rather than assume the
  existing shape already satisfies them. Where the scaffold conflicts with a requirement, the
  requirement wins and the scaffold code is replaced.

  **Known defects in the scaffold that plans must close (documented in
  `.hermes/plans/2026-08-28_154500-phase-4-web-tier-plan.md`, an earlier non-GSD plan on `main`,
  and to be re-verified against the code rather than trusted):**
  1. `server/engine_replace.py` / `server/app.py` `replace_text_in_pdf(...)` raises
     `UnboundLocalError` on `bundled_dir` — it crashes before writing. This is a pre-G2b fork of
     the rewrite logic and must be **deleted**, not patched: the corrected path is
     `engine.recipe.apply_recipe`.
  2. Page-render endpoints call `page.render(dpi=...)`; the installed `pypdfium2` 5.12.1 exposes
     `page.render(scale=...)` — HTTP 500.
  3. `client/src/App.jsx` calls a `/jobs/{id}/runs` endpoint that **does not exist** on the server.
     This endpoint is load-bearing for EDIT-01 (server-issued hit boxes) and CLAS-06/CLAS-07.
  4. No CORS middleware — works through the Vite dev proxy, breaks on any non-proxied deploy.
  5. `client/node_modules/` is **committed to git** (thousands of files, including built Vite dep
     bundles). This is a repo-hygiene defect the plans should close.

### Architecture (settled upstream — do not relitigate)

- **D-4.2: The server owns text addresses; the client echoes run IDs and never invents them.**
  Recorded as SETTLED in `STATE.md`'s Accumulated Context and restated in `ROADMAP.md`. EDIT-01
  says this in its own wording: hit-testing is against *server-issued boxes*, never pdf.js text
  items. The client is a thin viewer and edit surface; the authoritative bytes and the run index
  live on the server.

- **D-4.3: The edit path is the Phase 3 recipe contract, unchanged.** The client sends an operation
  log; the server calls `engine.recipe.plan_recipe` / `apply_recipe`. No fork, no reimplementation,
  no second rewrite path anywhere in `server/`. Phase 3's D-03 (structured-data-first dry-run
  report) exists precisely so the UI renders that data rather than recomputing it.

- **D-4.4: Hardening lands before the mutating UI, not after.** PRIV-01..07 and INGE-01..04 are
  gate criteria 1–3; EDIT-01/EDIT-05/FONT-07 are criteria 4–5. Wave ordering should reflect that
  the ephemerality canary, the isolated-worker limits, and the `no-store`/CSP posture are in force
  *before* the first byte of user document is accepted through a mutating route.

### Claude's Discretion

The researcher and planner decide these; no maintainer preference was expressed:

- Job/session identity and lifetime shape (opaque handle format, TTL values, content-addressed
  cache key derivation), subject to PRIV-02's testable claim: killing the cache mid-session leaves
  the session working via an exercised `409 SOURCE_MISSING` re-upload path.
- Worker isolation mechanism (per-job container vs. subprocess with `RLIMIT_AS` + wall clock),
  subject to PRIV-03 (tmpfs scratch) and PRIV-07 (parsing never in the request process).
- The undo/recipe store's shape and where it lives, subject to EDIT-05 (replace-all undoes as one
  step — the storage model must already admit a batch, because Phase 5 will produce one).
- Frontend state management, component decomposition, and styling approach.
- Whether CLAS-06 badges are computed server-side per page at index time or streamed.
- Streaming/progressive strategy for VIEW-02 (page 1 interactive before the last page parses).
- CDN/deployment target specifics for PRIV-06's `BYPASS`/`DYNAMIC` verification.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level constraints
- `CLAUDE.md` — project guidelines, including the permanent anti-features
- `.planning/ROADMAP.md` — Phase 4 section: goal, the five success criteria, and the "Deviations
  from the research sequence" note explaining why EDIT-01 and CLAS-06/07 are here and not Phase 2/3
- `.planning/REQUIREMENTS.md` — INGE-01..04, PRIV-01..07, VIEW-01..04, CLAS-06/07, EDIT-01,
  EDIT-05, FONT-07, plus the "Out of Scope" table
- `.planning/STATE.md` — Accumulated Context: settled decisions and open blockers

### Privacy posture (load-bearing for PRIV-01..07)
- `.planning/phases/01-conformance-harness-engine-spike/RETENTION-MAP.md` — the one-page data-flow
  retention map, written before infrastructure was selected per ENG-06. This is the source of truth
  for what may hold document bytes and for how long. PRIV-05's canary test asserts against it.
- `.planning/research/PITFALLS.md` — the attack table. **Its CVE specifics are partly
  aggregator-sourced; `STATE.md` requires re-verifying them against NVD at implementation time.**
  Treat that re-verification as a task, not a research pass.
- `.planning/research/ARCHITECTURE.md`, `.planning/research/STACK.md` — settled architecture and
  stack decisions

### The engine this phase wraps
- `.planning/phases/03-rewrite-engine-font-pipeline/03-CONTEXT.md` — D-01..D-15, especially D-03
  (dry-run-first structured report the UI renders), D-05/D-06 (substitution routing), D-10
  (`source_hash`), D-11 (all-or-nothing apply), D-13 (one subset per family per document)
- `.planning/phases/03-rewrite-engine-font-pipeline/G2B-GATE-RESULTS.md` — what G2b actually proved
  and, in "What was NOT tested", what it did not
- `.planning/phases/03-rewrite-engine-font-pipeline/03-VALIDATION.md` — the Phase 3 validation
  architecture; Phase 4's own VALIDATION.md should not duplicate what is already pinned here
- `engine/recipe.py`, `engine/rewrite.py`, `engine/index.py`, `engine/classify_page.py`,
  `engine/classify_run.py`, `tools/pdftool.py` (on branch
  `worktree-gsd-phase-3-rewrite-engine-font-pipeline`) — the real contract surface
- `.planning/phases/02-text-model/02-VERIFICATION.md` — Gate G1 evidence; the run index and
  classification behaviour the UI surfaces

### The scaffold being salvaged (read as prior art, verify every claim against the code)
- `/Users/prempatel/Pictures/pdf-tool/server/app.py`, `server/engine_replace.py`,
  `server/ephemeral.py`, `server/font_subsetter.py` — on branch `main` only
- `/Users/prempatel/Pictures/pdf-tool/client/src/` — React/Vite SPA, on branch `main` only
- `/Users/prempatel/Pictures/pdf-tool/.hermes/plans/2026-08-28_154500-phase-4-web-tier-plan.md` —
  an earlier non-GSD Phase 4 plan. **Prior art, not authority.** Its defect list is a useful
  starting point; its task breakdown has not been through a plan-checker and its claims must be
  re-verified.

</canonical_refs>

<specifics>
## Specific Ideas

- ROADMAP criterion 1 names the exact surfaces the PRIV-05 canary must cover: scratch, queue, logs,
  object store, error reporter — on **both** the success path and the crash path. A canary test
  that only covers the success path does not satisfy it.
- ROADMAP criterion 2 names three specific hostile inputs that must each fail inside the isolated
  worker: a decompression bomb, a cyclic page tree, a self-referencing Form XObject. The Phase 1
  corpus already contains malformed-file fixtures (`corpus/manifest.json`).
- ROADMAP criterion 3 names the specific CDN trap: Cloudflare's default cacheable-extension list
  includes `.pdf`, so `Cache-Control: no-store` must be *verified* to produce `BYPASS`/`DYNAMIC`,
  not merely sent. It also requires `isEvalSupported: false` on the pdf.js side plus a CSP
  forbidding `eval`.
- ROADMAP criterion 4 requires the refusal screen (CLAS-07) to name a **specific external OCR
  route** and offer a one-click "tell me when OCR ships" signal. REQUIREMENTS.md OCR-03 explains
  why: that signal is the measurement that gates whether v2 OCR gets built at all.
- ROADMAP criterion 5 requires per-operation local/server disclosure (PRIV-01), backed by the
  structural rule that an empty override set means the client materializes the file with zero
  upload. That structural rule is what makes Phase 6's PAGE-09 ("zero requests to document routes")
  achievable later — the disclosure must not be a hand-maintained label.
- INGE-02 (password-protected) and INGE-03 (signed document warns that rewrite invalidates the
  signature) are both in criterion 4 and are easy to drop; they need their own acceptance criteria.

</specifics>

<deferred>
## Deferred Ideas

- OCR of scanned pages (OCR-01..03) — v2. This phase ships only the refusal screen and the
  interest signal.
- Redaction (REDA-01/02) — v2, deferred for legal-exposure reasons.
- Accounts and edit history (ACCT-01/02) — v2.
- Multi-page find/replace UI — Phase 5. EDIT-05's storage model must *admit* a batch undo, but the
  batch producer is not built here.

</deferred>

---
*Phase: 04-web-tier-walking-skeleton-hardening*
*Context assembled: 2026-08-30 during batch planning of Phases 4–8*

---

## Amendments

### 2026-08-30 — post-research rulings (maintainer decisions)

`04-RESEARCH.md` measured the scaffold against all 20 requirements and produced findings that
change what these plans must contain. Three decisions were taken by the maintainer in response.
They **supersede** the corresponding text above.

#### A-4.1 — D-4.1's salvage boundary is "route map and dependency set", not "partial implementation"

**Supersedes D-4.1's build-on-it framing.** The audit measured the scaffold satisfying **zero of
seven** privacy requirements and **zero of four** ingest requirements. Specifics that decided it:

- `server/app.py:169-170` validates uploads by **file extension**, not magic bytes — INGE-01 is
  violated by design, and no `%PDF` check exists anywhere in `server/`.
- `server/app.py:207` calls `RunIndex(...)` directly in a sync FastAPI route — PRIV-07 ("PDF
  parsing never runs in the request process") is violated on every upload.
- `server/ephemeral.py` — the file whose docstring is the most accurate privacy statement in the
  repo — is 288 lines of **dead code that raises `NameError` on import**, imported by nothing.
  None of the privacy model it describes is in force.
- `server/engine_replace.py:331` saves output **after** collecting refusals, violating Phase 3's
  D-11 all-or-nothing decision, and never checks `source_hash` (D-10 absent).
- `server/app.py:912` `_pdf_to_docx` is a **second text-extraction path** with its own
  `y_tolerance = 3.0` clustering heuristic, bypassing `engine.clusterer` — the exact thing EXPO-05
  names as a signal the text model is under-specified.
- Roughly **700 of 1,105 lines** of `server/app.py` implement Phase 6/7/8 endpoints (PDF/A,
  compress, split, merge, rotate, DOCX, text, HTML) that Phase 4 must not carry.

**Ruling:** plans keep `client/` and its working dependency graph, keep the four things the audit
measured as correct — content-addressing (`app.py:79-80`, already the same digest as
`RunIndex`'s `source_hash`), opaque job IDs (`app.py:103-104`), the `_scratch_dir`
`try/finally` + `rmtree` shape (`app.py:70-77`), and the `/jobs/{id}/status` classification
payload shape (`app.py:219-227`) — and **delete** `server/engine_replace.py`,
`server/ephemeral.py`, `server/diag*.py`, and every endpoint outside Phase 4's scope, rebuilding
`server/app.py` around `engine.recipe`.

Deleting is not the same as ignoring: the deleted endpoints' *shapes* are prior art for Phases 6–8
and the client already expects several of them. Record what is removed and why.

#### A-4.2 — FONT-07 ships colour and weight/style; a size change is refused with a named reason

FONT-07 has **zero engine support**: `RecipeOp` is a frozen two-field dataclass and `parse_recipe`
rejects any op carrying a third key, so this is a Phase 3 contract extension, not UI work.

**Ruling:** extend `RecipeOp` with colour and weight/style. **A font-size change gets a named
refusal** in the EDIT-04 refusal vocabulary, surfaced in the UI like any other refusal. Reason:
changing size invalidates the fit ladder's premise — the ladder fits replacement text into the
*original run's measured width*, and a size change makes that target a design decision rather than
a measurement. Refusing it visibly is consistent with EDIT-04, CLAS-04, and FIND-05.

Weight/style interacts with D-13 (one subset per family per document): a bold variant is a second
face in the same family. The plan must confront that rather than discover it at execution.

#### A-4.3 — journey rows are recorded manual checks; data rows are automated

*(Controller decision, taken on the researcher's recommendation — Open Question 4. Not escalated:
it follows an existing project precedent rather than setting a new policy.)*

No e2e browser harness exists, and ~10 rows of the test map depend on whether one is built.
**Ruling:** automated tests for every *data* row (API contracts, headers, refusal reasons,
classification payloads, canary surfaces); **recorded manual verification** for the *journey* rows,
following the `G2B-GATE-RESULTS.md` precedent — a dated results document with a `## Decision`
header, per-check evidence, and an explicit "what was NOT tested" section. Do not silently drop a
journey row because it is hard to automate.

#### A-4.4 — the CDN check is parameterized on a deployment URL

*(Controller decision — Open Question 2. No deployment target is selected anywhere in the planning
docs; ROADMAP criterion 3 names Cloudflare only as the instance whose default extension list
includes `.pdf`.)* The requirement is "the CDN reports non-caching for document routes". Write the
check against a configurable deployment URL so it survives a change of provider. Cloudflare is the
assumed instance, not a locked dependency.

#### Still open, and must be pinned before the relevant plan ships

- **CLAS-07's "specific external OCR route"** is a product decision with no technical answer. It
  must be named before the refusal screen ships — a `TODO` there silently defeats the requirement,
  and OCR-03's measurement depends on it.
- **Whether a self-referencing Form XObject already terminates** in `engine/walker.py` /
  `engine/shared_xobjects.py` is unmeasured (no such fixture exists). Build the fixture first and
  let the result decide whether INGE-04's third case is a worker-limit task or an engine-fix task.
  These are very different sizes.

#### Engine gaps the plans must close (from research, not decisions — listed so they are not lost)

- **EDIT-01 has no run bounding box and one cannot be derived from `RunRecord` alone.** A run's
  width comes out of `GlyphRecord.x`/`advance` correctly (measured 40.0pt on a real run) but its
  height measures **0.0**, because `advance` is purely horizontal and no font size, ascent, or
  descent survives onto `RunRecord`. Server-issued hit boxes require an index extension.
- **`isEvalSupported` no longer exists in pdf.js.** It appears nowhere in the pinned `pdfjs-dist`
  6.2.108, and all three browser bundles contain zero `eval(` and zero `new Function(`, verified by
  grep. ROADMAP criterion 3's `isEvalSupported: false` clause is a **no-op** against the pinned
  version — the CSP half is the real requirement, and it is now achievable. Re-check on any pdf.js
  upgrade; the test map has a row for exactly this.
- **`MAX_RECIPE_OPS` is a CLI-era number** and was not chosen against a web workload.
- **`INGE-02` has no password parameter** anywhere in the engine's open path.
- **Fixtures that must be built** (measured absent from the corpus): a password-protected fixture,
  a signed fixture, and all three INGE-04 hostile fixtures (decompression bomb, cyclic page tree,
  self-referencing Form XObject).
