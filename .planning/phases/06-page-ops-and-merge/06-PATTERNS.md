# Phase 6: Page Ops and Merge — Pattern Map

**Mapped:** 2026-10-24, against production baseline `630ca28` and local delivery records through `0f9167a`.
**Scope:** PAGE-01..09, including the settled HEIC-only server exception. Read-only analysis; this document is the only file written by the mapper.
**Files classified:** 25 proposed implementation/config/test entries. Names below are recommendations for the planner, not claims that these files already exist.
**Strong analog families:** five: session transforms, guarded mutation transactions, controlled UI/viewer, bounded HTTP/subprocess boundary, and Node/pytest fidelity tests.

The August research correctly identifies structural PDF hazards but describes an obsolete application. The current SPA, recipe editor, find panel, source recovery and Node test suite are delivered. There are no current server merge/rotate/export endpoints to reuse. No Phase 6 work should change the text engine or silently close the existing G3/G4 verification debt.

## File Classification

Use the existing `.mjs`/`.jsx` conventions; a TypeScript migration is not required by this phase.

| New/modified entry | Role | Data flow | Closest current analog | Match quality |
|---|---|---|---|---|
| `client/src/pageOps/pdfDocument.mjs` | service | file-I/O, transform | `App.jsx:75–96` prepared viewer lifecycle | role-match; structural PDF API is new |
| `client/src/pageOps/insertBlankPage.mjs` | utility | transform | `session.mjs:1–5` explicit immutable state transforms | partial; library geometry from research |
| `client/src/pageOps/reorder.mjs` | utility | transform | `session.mjs:1–5` | partial |
| `client/src/pageOps/rotate.mjs` | utility | transform | `session.mjs:1–5` | partial |
| `client/src/pageOps/deletePage.mjs` | utility | transform | `session.mjs:1–5` | partial |
| `client/src/pageOps/mergePdf.mjs` | service | file-I/O, transform | No existing structural merge service | none; research must supply outlines/form rules |
| `client/src/pageOps/mergeImage.mjs` | service | file-I/O, transform | No image decode/composite service | none |
| `client/src/pageOps/placeImage.mjs` | service | transform | No PDF image placement/resource-copy service | none; `viewportBox` is coordinate-conversion precedent only |
| `client/src/pageOps/documentHistory.mjs` | store | event-driven, immutable snapshots | `session.mjs:4–5`, `App.jsx:205–228` | role-match; snapshot shape must expand |
| `client/src/pageOps/applyPageOperation.mjs` | controller | async transaction | `find/replaceAll.mjs:6–32` | strong role/data-flow match |
| `client/src/pageOps/PageOpsPanel.jsx` | component | controlled events | `find/FindPanel.jsx`, `App.jsx:244–251` | strong controlled-form match |
| `client/src/App.jsx` | controller | event-driven, file-I/O, request-response | Existing App lifecycle/transaction callbacks | exact integration site |
| `client/src/session.mjs` | utility/store | transforms, request-response | Existing source retry, queue, password and disposal helpers | exact compatibility surface |
| `client/src/Viewer.jsx` | component | asynchronous rendering/events | Existing `PageCanvas` and `Thumbnail` | exact integration site |
| `client/src/style.css` | config/presentation | responsive layout | Existing workstation and find-panel rules | exact design-system surface |
| `server/app.py` | route/controller | bounded request-response | Existing `_body`, middleware and `dispatch` | strong boundary match for HEIC only |
| `server/image_conversion.py` (name to finalize) | service | subprocess/file-I/O | No HEIC decoder service; `isolation.py` supplies transport/cleanup patterns | no codec analog |
| `server/errors.py` | model/utility | fixed-code events | Existing `ERROR_CODES` and `report_error` | exact error convention |
| `tools/client_license_gate.mjs` | utility | resolved dependency graph scan | `tools/license_gate.py`, `tests/test_license_gate.py` | role/data-flow match, different manifest format |
| `client/package.json` | config | test discovery/dependency resolution | Existing `test` script and lockfile | exact |
| `.github/workflows/license-gate.yml` | config | CI batch | Existing Python gate job; `.github/workflows/tests.yml:43–44` | exact workflow analog |
| `client/src/pageOps/*.test.mjs` | tests | pure transforms/deferred transactions | `session.test.mjs`, `find/replaceAll.test.mjs` | exact runner/async-test pattern |
| `tests/test_page6_merge_render.py` | tests | actual file generation/rendering | `test_gate_g4.py` and `harness/render_diff.py` | strong fidelity-test match |
| `tests/test_image_conversion.py` | tests | request-response/process failure | `test_web_contract.py`, `test_isolation.py` | strong boundary/negative-control match |
| Browser network journey/test for PAGE-09 | tests | observed browser traffic/download | No checked-in E2E runner; Phase 5 local browser evidence is precedent only | no automated runner analog |

## Pattern Assignments

### 1. Local transforms and whole-document history

**Applies to:** page operation utilities, `documentHistory.mjs`, and App integration.

**Analog:** `client/src/session.mjs:1–6`.

```js
export function upsertOperation(recipe, operation) {
  return recipe.some(item => item.run_id === operation.run_id) ? recipe.map(item => item.run_id === operation.run_id ? operation : item) : [...recipe, operation];
}
export function commitRecipe(state, recipe) {return {recipe, history: [...state.history, state.recipe]};}
export function previousRecipe(state) {return state.history.length ? {recipe: state.history.at(-1), history: state.history.slice(0,-1)} : state;}
export function operationLocation(operations) {return operations.length ? 'server' : 'local';}
```

Copy the small pure-function contract and testable immutable updates. Do not copy the recipe-only state shape as the entire page-op history model. Existing history contains recipe arrays, not PDFs, page order, baseline source identities or passwords. `operationLocation([])` only describes existing text-recipe replay; an empty recipe no longer proves that the current document equals the initially opened PDF after a local page mutation.

**Planner must settle one authoritative Undo model.** A history entry crossing a page operation needs the complete prior materialized bytes, text baseline/source identity, recipe/style state, page selection and relevant disclosure/signature state. The opened-original bytes and the current immutable text-replay baseline need distinct ownership. Restoring a snapshot must construct a fresh live request controller/queue, not reuse an aborted target. Avoid two unrelated history stacks whose top entries disagree.

The existing cache recovery contract must remain correct (`session.mjs:18–25`):

```js
if (error.status !== 409 || error.code !== 'SOURCE_MISSING') throw error;
if (!session.restoring) session.restoring = upload(session.original,session.password).then(result => {session.jobId=result.job_id;}).finally(()=>{session.restoring=null;});
await session.restoring;
return operation(session.jobId);
```

Here `session.original` currently means the immutable server replay source. If Phase 6 introduces `sourceBytes` or another name, update this helper and its tests atomically. A local page op must operate on current displayed bytes (`output` when present), then make its successful materialized output the next text baseline. Old server-issued run IDs/index boxes cannot be patched or reused after reordering/rotation/merge; invalidate index, selection, find review/progress and text recipe against that new baseline. Never run these source transitions before output preparation succeeds.

**Tests to extend:** `session.test.mjs:25–35` (font/style Undo), `61–90` (same-address replacement and cache recovery). Add text → page op → text → Undo sequences; both same-session and cache-evicted restoration must restore the correct bytes and style, not just a page count.

### 2. One guarded mutation and prepared publication

**Applies to:** `applyPageOperation.mjs`, document open/rebase/Undo and App callbacks.

**Analog imports:** `client/src/find/replaceAll.mjs` is dependency-injected and framework-free. UI modules import helpers by relative `.mjs` paths; no service locator or independent global store is present.

**Core transaction:** `client/src/find/replaceAll.mjs:18–31`.

```js
const accepted=freeze(structuredClone({recipe,selectedCount:review.selectedCount,changedPages:review.changedPages}));
let output;
try{
  const result=await requestApply(accepted.recipe);
  if(!fresh())return {status:'stale'};
  if(result?.ok!==true||!result.pdf)return {status:'refused',result};
  output=await loadOutput(result.pdf);
  if(!fresh()){await output?.dispose?.();return {status:'stale'};}
  if(!output)throw new Error('The edited PDF could not be prepared.');
  commit(output,accepted.recipe);
  return {status:'applied',selectedCount:accepted.selectedCount,changedPages:accepted.changedPages};
}catch(error){
  await output?.dispose?.();
  return fresh()?{status:'failed',error}:{status:'stale'};
}
```

For local page ops, replace the injected server request with the actual client transform. Preserve the capture → transform → freshness check → prepare → freshness check → synchronous commit shape. Helpers return results; App owns busy state, session identity, viewer publication and history. Reject a signed mutation without acknowledgement before transforming; the existing signature gate is not merely a text-tool condition.

**Mutation ownership:** `App.jsx:42–44`.

```js
const beginWork=(kind,label)=>{if(busyOwnerRef.current)return null;const owner={kind};busyOwnerRef.current=owner;setBusy(label);return owner;};
const finishWork=owner=>{if(busyOwnerRef.current===owner){busyOwnerRef.current=null;setBusy('');}};
const invalidateBatch=()=>{editVersion.current++;setBatchReview(null);setBatchError('');};
```

Extend the existing owner; do not introduce a second lock for page ops. App's current freshness predicate combines current controller, exact session object, busy owner and edit version (`App.jsx:164–165`, `183–184`, `208–209`). Apply it around every asynchronous load/decode/conversion/save. A canceled old operation's `finally` must not unlock a newer operation.

**Prepared viewer:** `App.jsx:75–96` uses `pdfjs.getDocument({data:bytes.slice(), ...})`, shared password prompting, and returns `{document,bytes,dispose}`. `publishViewer` disposes the previous published document only after a fresh prepared one exists. Copy this boundary, including `session.mjs:33–36` disposal through `document.loadingTask.destroy()` for pdf.js 6. Do not replace the viewer/history/download early and attempt rollback afterward.

### 3. Local-first open, lazy analysis and controlled page UI

**Applies to:** App, PageOpsPanel, Viewer/Thumbnail and all PAGE-09 paths.

The current open is not local: `App.jsx:97–110` starts `loadViewer(target,bytes)` and `upload(target)` in parallel. The following independent request paths must all be gated by explicit text-analysis activation:

1. `openFile`: unconditional upload at `106`.
2. `useEffect` at `119`: `if(meta)fetchRuns(page,0)`.
3. Thumbnail `onSelect` at `242`: selects then `fetchRuns`.
4. Thumbnail `onVisible` at `242` and `Viewer.jsx:49`: triggers classification as thumbnails become visible.
5. `showFind`/index producer at `128`, and direct edit-mode/inspector entry, once lazy analysis is introduced.

The viewer already works from browser-owned bytes without `jobId`. Local page count can come from the loaded pdf.js document. Distinguish viewer metadata from server analysis metadata; setting a local page count must not accidentally satisfy `if(meta)` and start classification. The current default inspector says 'Preparing document analysis…'; a local page session needs truthful neutral/unanalyzed state and an explicit server-analysis action. Update opening/footer/password disclosure copy because opening and unlocking for local viewing will no longer necessarily upload anything.

**Controlled UI analog:** `FindPanel.jsx` takes data/handlers and owns only small presentation state, while App owns mutations. Keep page commands, selected page, inherited-size notice, form-field result notices and aspect-lock controls as explicit props/events. Native buttons and labeled fields are the existing convention; keyboard up/down page controls can supply accessible reorder without a mandatory drag implementation. Do not put interactive controls inside `Thumbnail`'s existing outer `<button>` (`Viewer.jsx:58`).

**Rendering lifecycle:** `Viewer.jsx:8–25` cancels old page render/TextLayer tasks; `40–57` lazy-renders thumbnails. Reorder/rotate/insert/delete should publish a new prepared PDF proxy so those effects and fingerprint keys refresh coherently. Classification is optional metadata, never a permission check for a page op.

**Coordinate precedent:** `session.mjs:27–30` transforms all four corners through pdf.js viewport conversion; it does not assume unrotated letter-sized pages. PAGE-08 needs the corresponding inverse viewport mapping or explicit PDF-space numeric semantics, accounting for rotation and nonzero CropBox/MediaBox origins. The locked-aspect state must be visible; changing image width/height must not silently alter the other dimension when unlocked.

### 4. HEIC-only bounded server boundary

**Applies to:** the new conversion service, its route, error codes and tests. This is a pattern assignment, not a recommendation to extend the PDF rewrite engine.

**Route analog:** `server/app.py:210–222` validates content type, bounded request body and magic before dispatch; returns fixed codes and no user-controlled diagnostic text. `_body` (`app.py:59` onward) validates Content-Length, stream byte limits and deadlines. The process-facing imports remain lazy in `dispatch`; the request process does not import the PDF engine.

```python
source = await _body(request, max_upload_bytes, body_timeout)
if source[:5] != b'%PDF-':
    raise HTTPException(400, {'code': 'INVALID_PDF_MAGIC'})
result = await dispatch('inspect', source, request)
```

Copy the validation/boundary shape with HEIC-specific sniffing and limits, not PDF validation or source-cache insertion. Conversion should not create a PDF job, recipe history or persisted image session. PNG/JPEG/WebP must never take this route. The already-settled HEIC exception needs a visible server disclosure before its upload.

**Admission is easy to miss:** `app.py:137–145` currently admits only `/upload` and `/jobs/…`; adding a conversion route elsewhere without extending that shared admission predicate bypasses ingress limits even though privacy headers still run. Its work must also join the shared slot/task lifecycle (`171–204`) so client disconnect does not release worker capacity while native conversion still runs.

**Process analog:** `server/isolation.py:130–153`.

```python
with tempfile.TemporaryDirectory(prefix='pdf-worker-', dir=_scratch_root()) as scratch:
    # request payload is bounded before this point
    allowed = {'PATH', 'TZ', 'LANG', 'LC_ALL'}
    environment = {name: value for name, value in os.environ.items() if name in allowed}
    environment.update({'PDF_TOOL_WORKER_SCRATCH': scratch, 'TMPDIR': scratch,
                        'TEMP': scratch, 'TMP': scratch})
    process = subprocess.Popen(_worker_command(), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment,
        cwd=Path(__file__).resolve().parent.parent, start_new_session=True, close_fds=True)
    try:
        response = _exchange(process, payload, timeout)
    finally:
        _kill_group(process)
```

The excerpt preserves the actual process options/cleanup pattern; image file-in/file-out codec details belong to the research update. Current `_exchange` enforces wall/output bounds and `_kill_group` kills descendants. Current PDF worker actions, PDF magic and seccomp/exec assumptions cannot be blindly reused for a native decoder child. Preserve the boundary's fixed-code reporting and environment filtering rather than importing a decoder into FastAPI or shipping LGPL WASM to browsers.

**Errors/auth:** anonymous app; no user auth convention should be invented. `server/errors.py:23–32` reports only `{code, action}` from allowlists and suppresses reporter exceptions. HTTP errors use `{'detail': {'code': ...}}`. `app.py:156–160` applies no-store/CSP/nosniff/referrer/frame headers to errors as well as success. Extend fixed codes deliberately; never log subprocess stderr, image/document bytes, passwords or original filenames.

### 5. Tests, license gate and reproducible fidelity

**Node imports/structure:** `client/src/session.test.mjs:1–3`.

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { upsertOperation, commitRecipe, previousRecipe, withSourceRetry, viewportBox, createRequestQueue, retryWorkerBusy } from './session.mjs';
```

Use real `@cantoo/pdf-lib` transformations in page utility tests, plus independent readback/renderer checks. `find/replaceAll.test.mjs:8–15` injects request/load/commit seams and records calls; its `44–58` deferred promises prove old viewer/history ownership after stale response/load. Copy those adversarial branches for local save failure, corrupt import, canceled native conversion and mixed-history transitions, rather than asserting only command labels.

`client/package.json` currently runs `node --test src/*.test.mjs src/find/*.test.mjs`; explicitly add `src/pageOps/*.test.mjs` if that directory is selected. August validation's 'no JS framework exists' is obsolete. Do not add Vitest merely to satisfy its old command examples. Installed and lockfile `@cantoo/pdf-lib` are both **2.9.1**; declared range is `^2.8.1`.

**HTTP/process negatives:** `tests/test_web_contract.py:48–65` checks input validation before worker use and no-store/security headers on failures. `tests/test_isolation.py:21–67` injects crash/timeout/output/invalid-JSON workers, asserts scratch emptiness and sanitized events, and proves the worker PID differs from the parent. New HEIC tests should follow those exact lifecycle assertions, including unavailable codec and failed/truncated/oversized output.

**Renderer analog:** `harness/render_diff.py:126–132` is the sole three-engine entry:

```python
def render_all(pdf_path: str | Path, page_index: int, output_dir: str | Path) -> list[Path]:
    return [
        render_pdfium(pdf_path, page_index, output_dir),
        render_poppler(pdf_path, page_index, output_dir),
        render_mupdf(pdf_path, page_index, output_dir),
    ]
```

`tests/test_gate_g4.py:46–68` separately computes same-engine unmasked/outside-region differences, requires outside count zero, and proves visible change is nonvacuous. Cross-engine comparisons alone use `_cross_engine_pair_ok` from the existing harness. Adapt page-operation expectations: reordered/copied output pages must compare against their exact corresponding original page; unchanged siblings stay fully unmasked; placed-image masks cover only the intended image region. Never mask a whole unrelated page to hide a resource mutation. Preserve the real source bytes/digests. Use the already measured same-name/different-subset corpus pair, plus a constructed inherited-Resources sibling fixture as required by the context.

**Licensing:** `tools/license_gate.py:20–32` scans every resolved installed Python distribution, not just direct dependencies, and matches AGPL/Affero in metadata. It has no npm visibility. The client sibling must traverse actual resolved production closure and fail on forbidden/unknown licensing per its explicit policy, with transitive negative fixtures. `.github/workflows/license-gate.yml:21–22` and `tests.yml:43–44` currently run only the Python gate. A new client gate must run after lockfile installation; do not mistake package.json direct-dependency labels for transitive coverage.

## PAGE-09 Observed-Network Clarification

Measured current configuration: `App.jsx:16` defines `API=import.meta.env.VITE_API_URL||''`; default API base is same-origin root. `server/app.py:256–258` mounts only `/assets`; `App.jsx:77–78` places pdf.js CMaps/fonts/WASM below `BASE_URL + 'assets/pdfjs/'`. There is no currently mounted standalone `/pdfjs` namespace to exempt.

Per orchestration clarification, begin the actual request observer **before Open PDF**, after app navigation/static boot. Observe `fetch`/`xhr` requests against the resolved configured API origin/path prefix, conservatively rejecting any new API path. Exempt only explicitly served static asset namespaces (currently `/assets/`, including `/assets/pdfjs/`), not an enumerated historical list of document endpoints. With an empty API base, matching the whole origin without these resource-type/static distinctions falsely counts renderer assets as API traffic. Do not migrate server routes to `/api` solely to simplify this test.

The local proof must include opening, thumbnail visibility/selection, insert/reorder/rotate/delete, PDF merge, local image operations, Undo and download, with zero matched document API requests throughout. HEIC conversion is the single named exclusion, observed and disclosed separately. A mocked `fetch` in a pure Node helper cannot prove App does not eagerly upload/classify. Existing agent-operated browser network capture can provide local evidence; a persistent CI browser runner, if introduced, needs its own explicit test-only dependency/config rather than a claim that a checked-in runner already exists.

## No Close Domain Analog Found

| Entry | Missing domain behavior | Required source |
|---|---|---|
| `mergePdf.mjs` | Outline destination remapping, nested outline structure, AcroForm/widget ownership and collision handling | Current installed library plus research update; preserve and test result notices on both collision/no-collision paths |
| `mergeImage.mjs` | MIME/magic/decode validation, orientation and transparent-image compositing | Browser APIs/current research; size/pixel bounds and real output proof |
| `placeImage.mjs` | Copy-on-write page resources and rotated/cropped image geometry | Library-source findings and constructed sibling fixture; viewport conversion precedent is not a complete implementation |
| Native HEIC conversion | Codec executable/protocol and native process restrictions | Research update; reuse bounded lifecycle, not an in-process codec import |
| Browser network test | No checked-in Playwright/CUA test runner | Planner must choose reproducible runner or record exact agent-operated local evidence without inventing CI coverage |

## Shared Compatibility Checklist

- Keep the original user download, current materialized viewer bytes and server replay baseline distinct.
- Retain captured session/generation/owner checks, prepare-before-publish and one authoritative Undo entry per action.
- After any structural mutation, old page numbers, boxes, hashes and run IDs are stale; lazy analysis starts from the new immutable materialized baseline.
- Signed inputs require acknowledgement before local as well as server mutations. The pre-analysis local signature/encryption detection strategy must be supplied by research; it cannot depend on uploading a supposedly local session first.
- Do not call encrypted bytes safe merely because pdf.js renders them or a parser accepts `ignoreEncryption`; genuine password/decryption support is a research question, not an established current pattern.
- Release all document references, controller/queue work, image bitmaps/object URLs and password/history state on close. Client-only page ops do not consult text editability.
- Preserve existing recipe font/style, cache-loss and native-input-Undo tests; add structural mutations to their interleavings rather than replacing those earlier guarantees.
- G3 Linux/container/CDN and Phase 5 literal contract-specimen verification remain open. No deployment is part of this phase work.

## Metadata

**Search scope:** current `client/src`, `client/package*.json`, `server`, relevant `tests`, `harness`, `tools/license_gate.py`, `.github/workflows`, Phase 6 context/research/validation and requirement records.
**Project-local instruction discovery:** no root `AGENTS.md` file and no project `.Codex/skills`/`.agents/skills` indexes were present in this checkout during mapping; inherited user instructions and `CLAUDE.md` constraints apply.
**Edits:** only this file. No source changes, installations, heavy test runs, commits or deployments were performed.
