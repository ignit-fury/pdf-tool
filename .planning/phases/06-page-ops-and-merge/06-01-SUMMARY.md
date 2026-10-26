---
phase: 06-page-ops-and-merge
plan: "01"
subsystem: client-pdf-core
tags: [pdf, history, transactions, workers, signatures, encryption, cantoo, tdd]
requires:
  - phase: 04-web-tier-walking-skeleton-hardening
    provides: Existing client dependency closure and prepared-viewer transaction pattern
  - phase: 05-find-and-replace-across-all-pages
    provides: Freshness guards and whole-recipe text state to preserve in snapshots
provides:
  - Local password-aware PDF inspection and isolated resource mutation
  - Catalog-preserving insert, move, rotate and bounded safe delete
  - Exact document snapshots, explicit buffer admission and guarded publication
  - Terminable PDF worker transport with disposable input copies
affects: [06-03, 06-04, 06-05, 06-06]
tech-stack:
  added: []
  patterns: [Node built-in tests, same-document page-tree edits, prepare-before-commit, explicit buffer ownership]
key-files:
  created:
    - client/src/pageOps/pdfDocument.mjs
    - client/src/pageOps/pdfDocument.test.mjs
    - client/src/pageOps/documentHistory.mjs
    - client/src/pageOps/documentHistory.test.mjs
    - client/src/pageOps/applyPageOperation.mjs
    - client/src/pageOps/applyPageOperation.test.mjs
    - client/src/pageOps/pdfWorker.mjs
    - client/src/pageOps/pdfWorker.test.mjs
  modified: [client/package.json, client/package-lock.json]
key-decisions:
  - Pin the existing installed cantoo closure at exactly 2.9.1 without installing dependencies.
  - Keep opened-original bytes outside history snapshots; copy snapshot backing stores and retain separate current/replay baseline state.
  - Refuse memory admission without evicting any history; caller admits known snapshot copies before captureSnapshot allocates.
  - Redirect only recognized affected destinations to the nearest surviving page and refuse unknown catalog references.
  - Clean only independently verified obsolete XRef parser artifacts after actual password decryption.
  - Preserve acknowledged signatures across successive same-document edits; imported signature acknowledgement must be explicit.
requirements-completed: [PAGE-01, PAGE-02, PAGE-03, PAGE-04, PAGE-08, PAGE-09]
duration: 9min implementation; final handoff resumed after quota interruption
completed: 2026-10-25
---

# Phase 6 Plan 1: Local PDF Core and Exact History Summary

**Password-aware local page-tree edits preserve catalog references, complete document snapshots and atomic prepared publication, with bounded admission and terminable worker transport.**

All three implementation tasks are complete. Requirement IDs above identify the core contracts supplied by this plan; PAGE-08 image placement and PAGE-09 observed zero-network/browser behavior remain downstream acceptance work, not claims established by Node tests.

## Task Commits

| Task | RED | GREEN | Result |
| --- | --- | --- | --- |
| 1: Local PDF/resource contracts | `af62ee2` | `33989ad` | Real AES Unicode password decryption, geometry, signatures, resource isolation and exact existing dependency pin |
| 2: Complete history/atomic publication | `29e68ac` | `05182e0` | Snapshot data, unique backing-store admission and freshness-guarded preparation/publication |
| 3: Structural transforms/worker lifetime | `014ca6d` | `2b687aa` | Same-document transforms, form/destination deletion handling, encrypted-output readback and terminating transport |
| Review: unknown signatures/repeated signed edits | `3737f5b` | `3b39594` | Fail closed before transform; acknowledgement preserved for the acknowledged signed source |
| Review: geometry/import integration | `b2fabf5` | `27c3370` | Finite physical geometry, fixed import refusal codes and prepared-metadata acknowledgement |
| Review: stream dictionary catalog safety | `f9a25f9` | `7255abc` | Refuse unknown references to a removed page inside serialized stream dictionaries; preserve safe surviving references |
| Browser: minified named destinations | `c2f2b7b` | `3b96f3b` | Keep existing named GoTo targets valid after bundling; real 40-page insert/move/rotate/delete sequence returns to 40 pages |

Tests were executed and observed failing before each associated implementation/fix. No tracked files were deleted. No App, Viewer, session, server, STATE, ROADMAP or REQUIREMENTS file was changed by this executor. The root orchestrator owns shared planning metadata and later integration.

## Exported Contracts

| Module | Exports and behavior |
| --- | --- |
| `pdfDocument.mjs` | `loadLocalPdf(bytes,{password})` actually decrypts, never uses ignoreEncryption; `describePage(pdf,index)` returns raw MediaBox/CropBox, UserUnit, normalized rotation and physical visible dimensions from effective crop intersection; `inspectLocalPdf(bytes,{password})` returns `{pageCount,pages,signed,encrypted}`; `inspectSignatures(pdf)` is bounded and fail closed; `isolatePageResources(page)` clones resolved Resources and mutable Font/XObject/ExtGState/ColorSpace/Pattern/Shading/Properties dictionaries; `pdfError(code)` constructs fixed errors. |
| `pdfDocument.mjs` | `transformPages(bytes,command,{password,acknowledged=false})` accepts `command.type`: `insertBlank` with `{adjacentIndex,position:'before'|'after'}`, `move` with `{from,to}`, `rotate` with `{index,quarterTurns}`, `delete` with `{index}`. All indices are zero-based. Returns `{bytes,selectedPage,notices,localMetadata}`. Identity move/full-turn rotation returns `noop:true` and the unchanged input reference without saving. |
| `documentHistory.mjs` | `captureSnapshot(state)`, `admitHistory({openedBytes,current,history=[],candidateBytes,temporaryBytes=0,retainSnapshot=true})`, `pushSnapshot(history,snapshot)`, `peekSnapshot(history)` (null when empty), `popSnapshot(history)`. Admission returns `{ok:true,retainedBytes,transientBytes}` or `{ok:false,code}` without mutation or eviction. Use `retainSnapshot:false` for Undo admission before pop. Numeric temporaryBytes admits known future copies; buffer collections count existing stores once. |
| `applyPageOperation.mjs` | `applyPageOperation({snapshot,transform,prepare,isCurrent,admit,commit})` returns `applied`, `refused`, `failed` or `stale`. `admit` receives `{snapshot,candidateBytes,temporaryBytes,stage}` at `before-transform`, `before-prepare`, `after-prepare`; caller closes over all live opened/current/history/import buffers. `prepare(bytes,result)` returns a prepared viewer; `commit(prepared,next,snapshot)` is the caller's single synchronous publication callback. Caller owns the existing lock and freshness predicate. Abandoned prepared objects are disposed. |
| `pdfWorker.mjs` | `runPdfJob({workerFactory,command,payload,signal,timeoutMs=30000,errorCodes=[]})`. The **actual option name is `errorCodes`**. Caller may add constant uppercase named codes; unknown/error-message content becomes `PDF_JOB_FAILED`. Post `{id,command,payload}` and reply `{id,ok:true,result}` or `{id,ok:false,error:{code}}`. Payload buffers are structured-cloned, then only disposable copies are transferred. A single maximum/default 30-second deadline covers the job; completion, timeout, abort, worker error, messageerror, malformed envelope and post/factory failure clean up handlers and terminate the worker. |

Snapshots whitelist `{bytes,sourceBytes,password,recipe,selectedPage,style,selection,localMetadata,analysis,findState,acknowledged,action}`. `analysis` independently whitelists `{enabled,sourceIdentity,meta,index}`. Plain serializable data is cloned/frozen; controllers, promises, queues, PDF proxies, cycles and nonplain live objects are rejected. Copied typed arrays remain immutable **by ownership**, since JavaScript cannot freeze their indexed bytes. Never transfer or mutate retained/opened buffers. `captureSnapshot` allocates copies; the caller must admit known unique backing-store copy sizes **before calling it**, including full backing stores of alias views. Opened-original download bytes stay separately immutable for the file lifetime.

A successful page mutation rebases sourceBytes to its output bytes, clears password/recipe/selection/find and server analysis/index state, and returns independent local metadata. Output signed metadata preserves acknowledgement only for the already acknowledged signed source or `result.acknowledged===true`; prepared local metadata is supported when a transform does not supply it. Unknown input signature metadata refuses before any transform. Undo reconstructs fresh controllers/queues in integration and admits/prepares before popping history.

## Limits and Refusals

- `MAX_LOCAL_PDF_BYTES` and `MAX_PDF_BYTES`: 50 MiB logical local input/current PDF; `MAX_RETAINED_BYTES`: 200 MiB unique backing stores across opened/current/baseline/history/candidate; `MAX_TRANSIENT_BYTES`: 300 MiB known transaction-owned backing stores; `MAX_HISTORY_ENTRIES`: 100 snapshots. Equality passes; exceeding a limit refuses without dropping history. Larger existing server text output remains untouched and locally refused; the existing server output limit is unchanged.
- `GRAPH_MAX_DEPTH=64`, `GRAPH_MAX_NODES=100000`. Signature field traversal rejects repeated/cyclic/malformed fields. Deletion traversals are bounded and preflight before applying edits. UserUnit must be positive and at most 75000; physical dimensions must be finite and positive, including after multiplication.
- These are application-owned buffer limits, not whole-JS-heap/native-renderer/parser-allocation guarantees. The wrapper caps known payload copies; integration must admit imports, image decode/output, snapshot copies and renderer copies. Browser parsing/transforms/save must run inside the concrete module worker supplied by plan 05.
- Named core refusals include `PASSWORD_REQUIRED`, `PASSWORD_INVALID`, `PDF_INVALID`, `LOCAL_PDF_TOO_LARGE`, `SIGNATURE_UNKNOWN`, `SIGNATURE_ACK_REQUIRED`, `CATALOG_UNSAFE`, `FINAL_PAGE`, `PAGE_INDEX_INVALID`, `PAGE_COMMAND_INVALID`, `PAGE_GEOMETRY_INVALID`, `RESOURCES_UNSAFE`, `HISTORY_LIMIT`, `RETENTION_LIMIT`, `TRANSIENT_LIMIT`. Transport errors include `PDF_JOB_ABORTED`, `PDF_JOB_TIMEOUT`, `PDF_WORKER_CRASH`, `PDF_WORKER_RESULT_INVALID`, `PDF_JOB_FAILED`.

## Verification

- Final `node --test client/src/pageOps/pdfDocument.test.mjs client/src/pageOps/documentHistory.test.mjs client/src/pageOps/applyPageOperation.test.mjs client/src/pageOps/pdfWorker.test.mjs`: **22 passed, 0 failed**. Recorded in `/tmp/06-01-focused-tests.log` on the resumed handoff.
- Subsequent review-fix execution of the same focused command: **23 passed, 0 failed**, recorded in `/tmp/06-01-review-fix-tests.log`. The new actual serialized fixture first failed with `Missing expected rejection` before implementation, then proved both unsafe-target refusal and safe surviving-target preservation. No broad suite, corpus run or build loop was required for this bounded traversal fix.
- Browser regression follow-up on 2026-10-26: the same focused command passed **25 tests, 0 failures**, recorded in `/tmp/06-01-minified-delete-tests.log`. The actual `tests/fixtures/mixed_scanned.pdf` sequence (40 → insert 41 → move 41 → rotate 41 → delete 40) passes with unchanged source bytes and restored page geometry. It also passes with PDF string constructor names changed as production minification does. Before the fix, that minified-name case failed `CATALOG_UNSAFE`, while ordinary source execution passed; the existing production worker independently reproduced the same refusal. The root orchestrator owns the refreshed build and single browser delete retest.
- `npm --prefix client test`: recorded broad run **65 passed, 0 failed** in `/tmp/06-01-client-tests.log` before the final three review tests were added. An earlier concurrent run reported 63/65 while other executors were editing tests; the recorded rerun passed. No new broad run was performed while plan 03 was actively in RED. Final 22 focused tests include all plan 01 review additions.
- Final `npm --prefix client run build`: **passed**, recorded in `/tmp/06-01-build.log`; existing bundle-size warning remains. Early build intentionally has no concrete job-worker/parser imports from future modules.
- Manifest, lock root declaration and resolved installed lock version independently checked: **2.9.1 / 2.9.1 / 2.9.1**. No package installation, closure upgrade or new dependency.
- `git diff --check`: passed. Owned production/test files scanned for TODO/FIXME/placeholder stubs: none. No new network route, persistence, auth or server trust boundary introduced.

Fixtures exercise real saved/reloaded PDFs: AES Unicode passwords, signed flags/inherited FT, malformed/deep signature graphs, directly shared/inherited resources, all four rotations, nonzero boxes, crop/UserUnit geometry, existing page refs/custom catalog/OpenAction, surviving widget identity, pruned removed widgets/fields and redirected outline/name destinations. Deferred fake workers prove retained input buffers remain attached and all terminal handlers are removed. Deferred transaction tests prove stale preparation never publishes and discarded viewers are disposed.

## Decisions Made

Moving reattaches the **existing** leaf reference after cantoo's removePage deletes it from the context; inherited page attributes are materialized before reparenting. Blank pages explicitly inherit MediaBox origin/size, rotation, UserUnit and effective crop. Structural saves always use `updateFieldAppearances:false`.

Deletion supports standard field/widget hierarchies and recognized outline, name-tree, legacy named-destination, OpenAction and internal-link targets. Removed widgets/empty fields are pruned; only affected destinations redirect to the nearest surviving page, with notices. Surviving outline topology/counts and form references remain unchanged. Unsupported XFA/scripts, malformed/cyclic/ambiguous graph cases or unrecognized catalog references to the deleted page return `CATALOG_UNSAFE`; the implementation does not silently remove unrelated objects.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Cantoo decrypted XRef artifact reintroduced encryption on output.**
- Found during Task 3 real encrypted-output readback: cantoo 2.9.1 successfully decrypts content but treats an original unencrypted XRef stream as PDFInvalidObject, then saves that obsolete `/Encrypt` trailer into the rewritten file.
- Fix: after genuine password decryption, independently parse original source serialization and remove only invalid artifacts whose original ref resolves to a genuine `/Type /XRef` stream. Other invalid objects refuse `PDF_INVALID`. No encryption bypass, catalog rebuild or dependency patch. Covered by unlocked output readback in `2b687aa`.

**2. [Rule 2 - Correctness] Fail closed on unknown input signature metadata and preserve explicit acknowledgement.**
- Root fresh review identified missing/null/nonboolean metadata and repeated signed-edit/Undo integration risks. Added RED tests `3737f5b`, fix `3b39594`; prepared-result metadata acknowledgement additionally covered by `b2fabf5` → `27c3370`.

**3. [Rule 2 - Correctness] Bound physical geometry and allow fixed downstream refusal codes.**
- Root review identified finite UserUnit values overflowing physical dimensions and stripped merge/image named errors. Added RED tests `b2fabf5`, fix `27c3370`; new optional worker `errorCodes` contains only caller-constant uppercase codes and leaves unknown errors generic.

**4. [Rule 1 - Bug] Catalog safety traversal skipped PDF stream dictionaries.**
- A fresh review reproduced a metadata stream dictionary containing an unknown `PageTarget` reference to the page being deleted. The prior walker traversed dictionaries and arrays but skipped stream dictionaries, allowing a dangling reference in saved output.
- Added a saved/reloaded two-page metadata-stream fixture and observed the unsafe deletion fail to reject in RED `f9a25f9`. Fix `7255abc` visits every `PDFStream.dict` through the same visited identities, depth limit and node budget. Unknown references to the removed page now refuse `CATALOG_UNSAFE` before edits/save; a stream referring to the surviving page retains both its bytes and valid reference. Exported APIs and existing guards are unchanged.

**5. [Rule 1 - Bug] Production minification falsely rejected valid named destinations on deletion.**
- Browser observation found deletion of a newly inserted/moved/rotated blank failed on the 40-page mixed scanned fixture. The identical production-source Node sequence passed. Running the existing built worker reproduced the refusal and its diagnostic stack identified a surviving annotation's GoTo named destination.
- The destination validator compared `constructor.name` with PDFString/PDFHexString names, which production minification changes. RED `c2f2b7b` exercises the actual serialized fixture with both normal and minified constructor names. Fix `3b96f3b` imports the concrete PDF string classes and checks `instanceof`, preserving valid type identity through bundling. All 25 core tests pass, including the strict unknown stream-reference regression; no guard or exported interface was weakened.

### Workflow Adjustments

The referenced mandatory-initial-read/project-skills-discovery files were absent under the configured .Codex/.cursor paths; available plan, context, patterns, refreshed research, UI contract, installed version-specific library source and executing-plans/TDD skill instructions supplied execution context. Context7 tools and ctx7 CLI were absent, so existing installed source and its actual I/O behavior supplied version-specific API evidence. The root orchestrator owns global state/roadmap/requirements updates; this executor intentionally commits only owned task files and this summary. A quota interruption delayed final summary handoff after implementation, without redoing completed implementation.

## Remaining Verification

No known stub prevents this core plan's goal. App integration, concrete importing module worker, mixed live text/page Undo and fresh controller reconstruction, actual browser network observation, image placement and independent three-renderer G5 checks belong to later plans. These Node/structural checks do not certify those later acceptance gates, general arbitrary-PDF interoperability, or Linux/deployment behavior. The 100000-node bound is implemented; the permanent test exercises the depth bound rather than allocating a 100001-node fixture.

## Self-Check: PASSED

All eight created module/test files and both modified package files exist. All fourteen listed RED/GREEN/fix commit hashes were independently verified in git history, including browser regression `c2f2b7b` and fix `3b96f3b`. Exact dependency pin, final 25 focused tests, prior final build and whitespace checks passed. No unexpected tracked deletion or owned untracked generated artifact remains. The root orchestrator is responsible for the refreshed production build/browser retest following the final minification fix.
