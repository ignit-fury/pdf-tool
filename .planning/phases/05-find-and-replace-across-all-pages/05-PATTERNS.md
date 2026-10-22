# Phase 5: Find and Replace Across All Pages — Pattern Map

**Mapped:** 2026-10-22  
**Files classified:** 19 candidate new/modified files, including conditional normalization/config seams  
**Analogs:** 17 / 19 (9 exact, 8 role-match, 2 without a close analog)

This map describes the current Phase 4 implementation. The August research/validation documents predate it. Phase 4 G3 remains pending; this artifact neither passes G3 nor authorizes deployment. Build FIND-01..05 before wiring FIND-06. Names below adapt the research's proposed TypeScript files to the existing JSX/MJS codebase; they are ownership suggestions for the planner, not additional requirements.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `client/src/App.jsx` | controller/component | request-response, event-driven | Existing `App.jsx:52-104` | exact |
| `client/src/Viewer.jsx` | component | event-driven | Existing `PageCanvas`, `Viewer.jsx:5-30` | exact |
| `client/src/style.css` | config | transform | Existing `.run-box`, `.run-list`, `.fit-result`, responsive rules | role-match |
| `client/src/session.mjs` | utility | request-response, transform | Existing helpers, lines 1-98 | exact |
| `client/src/session.test.mjs` | test | event-driven | Existing Node tests, lines 16-119 | exact |
| `client/src/features/find-replace/search.mjs` | utility | transform | No matcher or normalized-offset mapper exists | none |
| `client/src/features/find-replace/search.test.mjs` | test | transform | `session.test.mjs:1-14,84-86` | role-match |
| `client/src/features/find-replace/buildRecipe.mjs` | utility | transform | `session.mjs:1-5`; `App.jsx:86-87` | exact |
| `client/src/features/find-replace/buildRecipe.test.mjs` | test | transform | `session.test.mjs:16-27,52-58` | role-match |
| `client/src/features/find-replace/MatchList.jsx` | component | event-driven | Inspector/run-list JSX, `App.jsx:117-118` | role-match |
| `client/src/features/find-replace/useReplaceAll.js` | hook/controller | request-response | `App.jsx:88-103` preview/apply/undo | role-match |
| `client/src/features/find-replace/useReplaceAll.test.mjs` | test | request-response, event-driven | `session.test.mjs:60-119` async helpers | role-match |
| `engine/search_text.py` (conditional canonical normalization helper) | utility | transform | `clusterer.py:260-270` supplies input, not normalization/offset mapping | none |
| `engine/records.py` (conditional search metadata) | model | transform | Existing `RunRecord`, lines 65-75 | exact |
| `server/worker.py` (conditional search metadata exposure) | controller | request-response | Existing page serialization, lines 175-201 | exact |
| `tests/test_find_normalize_parity.py` | test | batch, transform | `test_worker.py:36-59` real boundary; Node helper tests | role-match |
| `tests/test_find_replace_recipe.py` | test | request-response, batch | `test_worker.py:29-59`; `test_recipe_page_scope.py:15-37` | exact |
| `tests/test_gate_g4.py` | test | batch, file-I/O | `test_gate_g2b.py:111-158,373-403` | exact |
| `client/package.json` (optional test script only) | config | batch | Existing scripts, lines 6-10 | role-match |

Research-only proposals already superseded: reuse `session.mjs:38-56` instead of creating a second `reasonCopy.ts`; retain Node's existing test runner instead of adding `vitest.config.ts`, Vitest/Jest, TypeScript, or a lockfile change solely for pure-function tests. Component/browser verification may need a separate existing/manual route; Node alone does not render JSX.

## Pattern Assignments

### Page indexing and cancellation: `App.jsx`, `session.mjs`

**Analog:** `client/src/App.jsx:52-53,64,76-82`; `client/src/session.mjs:63-98`.

Imports follow existing relative ESM (`App.jsx:6-7`):

```javascript
import {PageCanvas,Thumbnail} from './Viewer.jsx';
// Pure session helpers are imported from './session.mjs'.
```

The actual page contract is `GET /jobs/{job_id}/pages/{zeroBasedPage}/runs`. Browser page keys are **one-based**, worker `page` is zero-based. `meta.page_count` bounds the all-page walk. The session already holds `pages: new Map()` of pending/resolved promises and a queue with concurrency 2. Copy this cache/priority seam (`App.jsx:76-81`):

```javascript
if(target.pages.has(number)){target.pages.get(number).promote?.(priority);return;}
const pending=documentRequest(target,`/pages/${number-1}/runs`,{},priority);
target.pages.set(number,pending);
pending.then(data=>{if(current(target))setIndex(previous=>({...previous,[number]:data}));})
```

**Required integration adaptation:** `fetchRuns` currently returns `undefined` on both paths. Give callers the existing/new promise so the all-page loop can await it, count completed pages, and reuse thumbnail/selected-page requests. Preserve its failure eviction (`target.pages.delete(number)`). Do not introduce a second uncached fetch loop. Background search uses lower priority than selected-page analysis; one sequential search producer through the existing queue is sufficient. Never announce complete document coverage while a page is still pending or failed.

`documentRequest` already composes queue → bounded 429 retry → source recovery → fetch (`App.jsx:53`):

```javascript
target.queue.run(()=>retryWorkerBusy(()=>withSourceRetry(target,
  jobId=>request(`/jobs/${encodeURIComponent(jobId)}${suffix}`,{
    ...options,signal:target.controller.signal,
    headers:{...passwordHeaders(target.password),...options.headers}
  }), (bytes,password)=>upload(target,bytes,password)
),{signal:target.controller.signal}),priority)
```

Use the same path for every analysis, batch preview, and apply. `clear()` aborts the document controller, clears the source/password and index, and increments `editVersion` (`App.jsx:28-33`). Active fetches receive its signal; pending queue work rejects with `AbortError` (`session.mjs:70-75`). A search-generation token must additionally reject stale query results without aborting the entire open document. Closing/reopening must clear match opt-outs, preview verdicts, progress and active match. An aborted browser request does not instantly stop the server child; server admission stays held until actual completion (`server/app.py:97-103,191-195`).

**Tests to copy:** `session.test.mjs:88-119` verifies priority promotion, bounded concurrency, queued abort and bounded 429 retry. Extend for cached-promise reuse, incomplete-page failures, new-document cancellation, and stale search results.

### Search text and original addresses: `search.mjs`, conditional engine metadata

**Analog input:** `server/worker.py:194-201`:

```python
runs.append({"run_id": run.run_id, "text": run.display_text,
    "box": run_box(run, raw, resources), "state": verdict.state,
    "reason": verdict.reason, "source_font": source_font,
    "suggested_font_family": suggested_family})
```

The HTTP response has `page`, `bucket`, `runs`, dimensions, rotation and `view_box`. There is no `display_text` wire key, no per-run `page` wire key, no `resolved.op`, and no normalized search field. Attach the page from the response/cache rather than decoding `run_id` in browser code. Keep every refused run in the match input. Empty/no-text pages remain valid completed pages.

The interpreter's existing TJ/synthetic-space treatment is exactly `engine/clusterer.py:265-270`:

```python
parts: list[str] = []
for i, (record, _attrs) in enumerate(fragment):
    if i > 0 and K_EM < gaps[i] <= BREAK_EM:
        parts.append(" ")
    parts.append(record.unicode or "")
return "".join(parts)
```

**No close analog for ligature normalization or source-offset mapping exists.** `RunRecord` currently contains `run_id`, glyphs, `display_text`, page and optional geometry (`records.py:65-75`). Do not change `display_text` semantics as a search shortcut: the recipe engine uses the original text model for resolution/correlation. D-5.3 requires an explicit canonical normalization contract; expose it from the interpreter layer if needed, with `server/worker.py` only serializing it. Keep this conditional work together under one owner. Research's two independent NFKD examples are not evidence that the current interpreter already normalizes ligatures.

The new pure matcher needs substring default, match-case/whole-word options, per-instance identity, original-string start/end offsets, context, `run_id`, page, reason/state, and opt-out state. Normalized positions cannot directly slice source text: `ﬁ`→`fi`, `ﬃ`→`ffi`, astral characters and combining sequences change lengths or indexing units. Cover match-case ligatures too; the old research example skips normalization when match-case is enabled. Python casefold and JS lowercase are not equivalent; Python `\b` is not ASCII-only by default. The planner must pin behavior rather than copy these old claims as tested contracts.

**Current edited view:** copy `App.jsx:86`:

```javascript
const existing=recipeState.recipe.find(op=>op.run_id===run.run_id);
setDraft(existing?.new_text??run.text);
setStyle(existing?.style||{});
```

Search committed recipe overlays (`existing?.new_text ?? run.text`), not stale original-only text and not an uncommitted inspector draft. Keep original cached rows/boxes/IDs immutable. Recompute matches after single edits, batch commits and undo. A second replace-all must operate on the visible edited spelling while still targeting its original server-issued ID. The server always replays against the original bytes.

### Recipe assembly: `buildRecipe.mjs`

**Analog:** `client/src/session.mjs:1-5`:

```javascript
export function upsertOperation(recipe, operation) {
  return recipe.some(item => item.run_id === operation.run_id)
    ? recipe.map(item => item.run_id === operation.run_id ? operation : item)
    : [...recipe, operation];
}
export function commitRecipe(state, recipe) {return {recipe, history: [...state.history, state.recipe]};}
export function previousRecipe(state) {return state.history.length ? {recipe: state.history.at(-1), history: state.history.slice(0,-1)} : state;}
```

Group included match instances by `run_id`; replace their source spans from right to left (or concatenate original slices) to construct one full `new_text` per run. Opting out one occurrence must preserve that occurrence while replacing others in the same run. Merge each result into the **entire current recipe** with `upsertOperation`; keep unrelated operations and the current operation's `style`. The existing upsert replaces an operation wholesale, so omitting `style` would erase earlier styling. Preserve order consistently for preview keys and engine replay.

`engine/recipe.py:542-549` refuses every operation in a recipe containing any duplicate ID. The wire accepts only `run_id`, `new_text`, optional `style` (`recipe.py:152-165`), so match offsets, reasons, selection flags and page numbers never go in recipe objects. A no-op batch must not add an undo step. Do not delete an existing styled op merely because its text now matches the original.

**Tests to copy:** immutable recipe/style restoration in `session.test.mjs:16-27,52-58`; duplicate refusal in `tests/test_recipe.py:1147`; multi-op same-part regressions at `tests/test_recipe.py:940,1053`. Add per-instance opt-out, deduplication, literal replacement containing `$`, length-changing normalization, prior styled edit, and batch→single edit→undo→undo cases.

### Match UI and jump/highlight: `MatchList.jsx`, `Viewer.jsx`, `style.css`, `App.jsx`

**Analogs:** current inspector/run list (`App.jsx:117-118`), page navigation (`115-116`), and `PageCanvas` (`Viewer.jsx:5-30`). Copy readable refusal rendering with `explainReason`/`refusalCode` from `session.mjs:38-54`; reuse `explainFit` for successful preview rows. Keep classify-time and latest preview-time refusal visible in the same result list. Unknown reasons already fall back safely (`explainReason:50`); do not create a second refusal vocabulary.

Geometry must reuse `viewportBox` (`session.mjs:27-30`) and the server `run.box`:

```javascript
const points=[[box[0],box[1]],[box[2],box[1]],[box[2],box[3]],[box[0],box[3]]]
  .map(([x,y])=>viewport.convertToViewportPoint(x,y));
const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]),left=Math.min(...xs),top=Math.min(...ys);
return {left,top,width:Math.max(...xs)-left,height:Math.max(...ys)-top};
```

`PageCanvas` currently highlights only the selected edit run, only in edit mode (`Viewer.jsx:28`). Add a separate active-find target/highlight state so search works while selecting/copying and while viewing refused matches. Existing geometry supports a run highlight; it does not supply exact glyph boxes for individual substring spans. Do not derive mutation addresses or search runs from pdf.js `TextLayer` items. Keep any visual search layer separate from document contents.

**Jump hazard:** `App.jsx:84` clears selection/preview whenever `page` changes. Calling `setPage` and `choose(run)` together can have the effect clear the chosen run afterward. Hold active find target separately, await page/index readiness, then focus/scroll its run highlight. Existing `.canvas-stage` scrolls internally; navigation alone may leave a lower-page target offscreen. Preserve transformed geometry at zoom/rotation. Full match IDs contain punctuation; use refs or safe DOM selection rather than interpolating raw IDs into selectors.

Use current page/inspector responsive CSS (`style.css:2,4-7`), status live region (`App.jsx:120`) and labelled controls. Show total/selected/refused counts separately from indexing progress. Match-row opt-out must not accidentally trigger navigation. FIND-03 click-to-jump, legibility and browser shortcut behavior retain recorded browser verification.

### Batch preview/apply/undo: `useReplaceAll.js`, `App.jsx`, `session.mjs`

**Analog:** `App.jsx:88-103`. Actual routes are one `POST /jobs/{job_id}/edit` with `application/json` body containing the **full recipe array**, `dry_run=true` for preview and `dry_run=false&acknowledge_signature=...` for apply (`server/app.py:237-247`).

The actual preview path (`server/worker.py:215-226`) is stronger than the old research:

```python
if action == "plan":
    report = plan_recipe(path, recipe, password=secret.get_secret_value())
else:
    report = apply_recipe(path, recipe, output, password=secret.get_secret_value())
return {"ok": report.ok, "resolved": [
    {"run_id": resolved.op.run_id, "ok": resolved.ok, "reason": resolved.reason,
     "strategy": resolved.strategy, "delta_pt": resolved.delta_pt}
    for resolved in report.resolved], "pdf": base64.b64encode(output.read_bytes()).decode("ascii")
    if request.get("dry_run") is not True and output.exists() and report.ok else None}
```

The web route dispatches `edit` even for dry runs: preview actually rewrites in disposable scratch and discards output. It has no PDF payload; match verdicts join by `resolved.run_id`. `action=plan` is an internal worker capability, not a new public endpoint to invent.

Preserve the current preview snapshot pattern (`App.jsx:89-94`):

```javascript
const version=++editVersion.current,recipe=candidate();
// After awaiting preview:
if(current(target)&&version===editVersion.current)
  setPreview({result,recipe,key:JSON.stringify(recipe)});
// Apply checks result.ok and the current candidate's serialized key.
```

A batch key/version must cover current recipe, replacement, query/options, instance opt-outs and indexed match set. Single-edit previews and batch previews must invalidate each other when their input recipe changes. Share the app's mutation/busy ownership; a hook must not independently race apply, undo or another editor. Carry the accepted immutable snapshot through the awaited apply and push history once only after `result.ok`, a returned PDF, viewer load and current-session check (`App.jsx:96`). Failed/stale operations must not change output or undo history.

**Filter and re-preview:** show refused runs, remove only proposed batch overrides for refused runs, restore their previous recipe op if one existed, and retain unrelated committed ops. Re-preview the resulting full candidate before enabling apply. `apply_recipe` is all-or-nothing and late splice/re-derivation failures can report one refused op while others still have successful planning verdicts (`recipe.py:829-865`); an `ok` row in an overall failed report does not prove the filtered batch successfully applies. Show any further refusals, and never silently commit a different recipe from the accepted preview.

Signature guard is existing session state: `meta.signed && !acknowledged` blocks apply (`App.jsx:94,113`); worker permits preview before acknowledgement but guards commit (`server/worker.py:203-204`). Reuse its acknowledgement for batch and undo replay. Untouched original download remains byte-exact.

Undo restores one prior **whole recipe** via `previousRecipe`; empty recipe uses browser-held original, nonempty recipe replays server-side (`App.jsx:99-104`). Commit a batch once with `commitRecipe`, never once per matched run. Ctrl/Cmd+Z intentionally leaves text-input native undo alone (`App.jsx:104`); test document undo with focus outside replacement inputs as well as using the Undo button.

## Shared Patterns

**Source recovery/password:** `session.mjs:18-25` retries only `409 SOURCE_MISSING`, coalesces concurrent reuploads through `session.restoring`, uploads `session.original` with `session.password`, updates `jobId` and retries once. `passwordHeaders:7-9` preserves UTF-8 via base64. Keep these paths for all-page indexing and every replay; never upload edited output as a new authoritative source. See `session.test.mjs:29-35,60-82` and `tests/test_web_contract.py:9-45,58-64`.

**No account/auth layer:** this remains anonymous. Document handles, original-source binding, password headers, and signed-document acknowledgement are the existing guards. The HTTP parent imports no engine; all parsing stays in disposable workers (`server/app.py:171-195`, `server/isolation.py:112-169`). Preserve fixed-code transport errors and no-store headers; do not log search/replacement text.

**Bounded work:** server slots=2 (`app.py:93`), HTTP recipe limit=1 MiB (`app.py:30,244`), child CPU=20 seconds/1 GiB (`worker.py:23-41`), default child wall deadline=30 seconds (`isolation.py:112-114`). The recipe cap remains 50,000 ops and 10,000 characters per `new_text` (`recipe.py:79-84`). Old plan-only corpus timings do not measure today's full dry-run rewrite, including repeated same-part re-derivation. Measure preview AND apply for the real 40-page candidate through this boundary; limits are not permission to split one atomic batch into partial commits or bypass isolation.

**Page scope:** `plan_recipe` now collects pages from valid source-bound IDs and calls `RunIndex.page` only for those pages (`recipe.py:554-573`). It no longer invokes an eager whole-document classifier. Existing `tests/test_recipe_page_scope.py:15-37` protects this for one/multiple requested pages. Each HTTP page request creates its own isolated `RunIndex`; old research's shared-live-index race assumption is false. Browser cache/queue reuse is still needed to avoid repeated work and keep selected-page responsiveness.

**Testing:** 12 Node built-in tests already exist in `client/src/session.test.mjs`. Run `node --test client/src/session.test.mjs`; add feature `.test.mjs` paths explicitly or a minimal npm script. Current `package.json` has no `test` script. Do not copy stale Vitest-specific commands from 05-VALIDATION without updating their owning plan. Python tests use pytest and real `run_worker` or `TestClient(create_app())` boundaries; monkeypatch only private test seams where necessary.

### Gate test reuse: `tests/test_gate_g4.py`

Copy mask construction from `tests/test_gate_g2b.py:111-158`, retaining outward rounding and measured **device-space y-down** orientation. Browser `run.box` and raw glyph mask coordinates use different transforms; do not interchange them. Generalize the existing two-region technique at `373-403`:

```python
for index, source in enumerate((png_a, png_b)):
    target = scratch_dir / f"{index}.png"
    with Image.open(source) as image:
        rgb = image.convert("RGB")
        rgb.paste((0, 0, 0), mask_a)
        rgb.save(target)
    masked.append(target)
return int(masked_pixel_diff(masked[0], masked[1], mask=mask_b))
```

Paint each changed run region on both renders, retain comparison outside all regions, and prove non-vacuous edited text/counts separately. Render/check every changed page in pdfium, poppler and mupdf; preserve the gate's content-free assertion-message convention (`test_gate_g2b.py:37-39`). Research's 40-page fixture is `corpus/public/govdocs1_013_013050.pdf` (a USGS guide, not a legal contract); shared-XObject refusal fixture is `irs_1040_tax_tables.pdf` / `CAUTION`. Keep that fixture distinction explicit. Exercise an opt-out, true multi-page edits and one batch undo; passing an engine-only test does not prove browser Ctrl+Z or HTTP resource-limit feasibility.

## Task Partition Boundaries

| Owner/task | Owned files/seam | Dependency |
|---|---|---|
| Search text contract + pure matching | Conditional `engine/search_text.py`, `engine/records.py`, `server/worker.py` exposure; `search.mjs`, matcher/parity tests | Pin normalization and original-span shape first; do not touch rewriting |
| Pure batch assembly | `buildRecipe.mjs` and tests | Consume agreed match shape and current recipe; preserve style/IDs |
| Find UI/integration | `App.jsx`, `Viewer.jsx`, `style.css`, `MatchList.jsx`, any `session.mjs` queue/cache adaptation and tests | Own shared app state, page jumping and cancellation; avoid concurrent App edits by other owners |
| Replace orchestration | `useReplaceAll.js` + pure orchestration tests; integration changes through App owner | After find/preview works; use existing documentRequest/loadViewer/commit seams |
| Verification | `test_find_replace_recipe.py`, `test_gate_g4.py`, existing-worker/page-scope regressions and recorded browser checks | After final interfaces; no deployment or G3 status changes |

`server/app.py`, `server/isolation.py`, `engine/recipe.py`, font/rewrite modules are consumed interfaces, not default Phase 5 edit targets. Add their modification only for a reproduced integration defect, with focused regression coverage. No new bulk endpoint, server history or rewrite implementation is implied.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `search.mjs` | utility | transform | No existing query matcher, normalized-span map, or per-instance exclusion model |
| Conditional `engine/search_text.py` | utility | transform | Existing interpreter only emits display text; no canonical Unicode search normalization/offset helper |

Use the locked decisions plus an explicit tested text/span contract for these gaps; old research snippets need the corrections above.

## Metadata

**Search scope:** `client/src`, `server`, `engine`, existing recipe/worker/web/page-scope/gate tests, Phase 5 context/research/validation and roadmap requirement references.  
**Source/test/config files inspected:** 21 (reads or targeted symbol/excerpt inspection); primary reusable implementation analogs: App, session helpers, Viewer, worker serializer, recipe contract.  
**Project instructions:** No repository-root `AGENTS.md` or local `.Codex/skills` / `.agents/skills` entries found; supplied AGENTS rule only triggers graphify on `/graphify`. `CLAUDE.md` requires GSD workflow; this artifact is produced inside plan-phase mapping.  
**Verification performed:** source inspection only; no product edits, test execution, commits or deployment in this mapping task.
