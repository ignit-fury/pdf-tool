# Phase 4: Web Tier Walking Skeleton + Hardening - Research

**Researched:** 2026-08-30
**Domain:** FastAPI + React/Vite web tier over the Phase 3 recipe engine; untrusted-input hardening; structural ephemerality
**Confidence:** HIGH on the scaffold audit and engine contract (every claim below is a live measurement or a direct read of the real code); HIGH on the CVE re-verification (NVD API, fetched this session); MEDIUM-HIGH on CDN behaviour (official Cloudflare docs, fetched); MEDIUM on deployment specifics (no target selected yet)

---

<user_constraints>
## User Constraints (from 04-CONTEXT.md)

### Locked Decisions

- **D-4.1: Salvage the existing `server/` + `client/` prototype rather than replan clean.**
  (Maintainer decision, 2026-08-30.) A FastAPI + React/Vite scaffold already exists on `main`
  (commit `0acd3eb`). Phase 4 plans build **on** it — port the Phase 3 engine to it, fix its known
  defects, then harden — rather than starting from an empty directory.
  **Accepted cost:** every scaffold decision predates any review against PRIV-01..PRIV-07 and
  INGE-01..INGE-04. Salvage is not endorsement. Where the scaffold conflicts with a requirement,
  the requirement wins and the scaffold code is replaced.

- **D-4.2: The server owns text addresses; the client echoes run IDs and never invents them.**
  EDIT-01: hit-testing is against *server-issued boxes*, never pdf.js text items.

- **D-4.3: The edit path is the Phase 3 recipe contract, unchanged.** The client sends an operation
  log; the server calls `engine.recipe.plan_recipe` / `apply_recipe`. No fork, no reimplementation,
  no second rewrite path anywhere in `server/`.

- **D-4.4: Hardening lands before the mutating UI, not after.** The ephemerality canary, the
  isolated-worker limits, and the `no-store`/CSP posture are in force *before* the first byte of
  user document is accepted through a mutating route.

### Claude's Discretion

- Job/session identity and lifetime shape (opaque handle format, TTL values, content-addressed
  cache key derivation), subject to PRIV-02's testable claim.
- Worker isolation mechanism (per-job container vs. subprocess with `RLIMIT_AS` + wall clock),
  subject to PRIV-03 (tmpfs scratch) and PRIV-07 (parsing never in the request process).
- The undo/recipe store's shape and where it lives, subject to EDIT-05.
- Frontend state management, component decomposition, and styling approach.
- Whether CLAS-06 badges are computed server-side per page at index time or streamed.
- Streaming/progressive strategy for VIEW-02.
- CDN/deployment target specifics for PRIV-06's `BYPASS`/`DYNAMIC` verification.

### Deferred Ideas (OUT OF SCOPE)

- OCR of scanned pages (OCR-01..03) — v2. This phase ships only the refusal screen and the
  interest signal.
- Redaction (REDA-01/02) — v2.
- Accounts and edit history (ACCT-01/02) — v2.
- Multi-page find/replace UI — Phase 5. EDIT-05's storage model must *admit* a batch undo, but the
  batch producer is not built here.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INGE-01 | Uploads validated by magic-byte sniff + size cap, not extension | §2.1 (scaffold violates this today, file:line); §5.1 (corpus measurement: 217/217 files have `%PDF-` at offset 0) |
| INGE-02 | Open a password-protected PDF by supplying the password | §3.4 (engine API gap: no password parameter anywhere); §5.2 (measurement: **zero** corpus fixtures need a user password) |
| INGE-03 | Signed document detected; user warned rewrite invalidates the signature | §5.3 (measurement: **zero** corpus documents carry a real signature; 5 carry `/SigFlags 2` sig *fields* only) |
| INGE-04 | Decompression bomb / cyclic page tree / self-ref Form XObject fail on their own limits | §6 (isolation mechanism, with the measured macOS `RLIMIT_AS` blocker); §5.4 (all three fixtures must be built) |
| PRIV-01 | Per-operation local/server disclosure, backed by the empty-override-set structural rule | §7.1 (the structural rule as stated in ARCHITECTURE.md:588); §2.4 |
| PRIV-02 | No server state whose loss is observable; cache-kill leaves session working | §7.2 (`409 {missing:[...]}` contract from ARCHITECTURE.md:222); §2.3 (scaffold has no 409 path) |
| PRIV-03 | Scratch is tmpfs in a per-job container; queues carry opaque handles | §7.3 (**the correct answer is that no queue exists** — CLAUDE.md:89); §2.3 |
| PRIV-04 | No document content in logs or error reports | §2.5 (scaffold logs a raw filename at `ephemeral.py:157`) |
| PRIV-05 | Canary retention test in CI over 5 surfaces, success **and** crash path | §8 — the hardest item in the phase; two of five surfaces are proved by *absence* |
| PRIV-06 | `no-store` + verified CDN `BYPASS`/`DYNAMIC`; `isEvalSupported:false` + CSP forbidding eval | §9 — **`.PDF` confirmed in Cloudflare's default list**; **`isEvalSupported` no longer exists in pdfjs-dist 6.2.108** |
| PRIV-07 | PDF parsing never runs in the request process | §6.3 (scaffold parses in-process at `app.py:207`) |
| VIEW-01 | Pages rendered faithfully | §2.2 (two live-reproduced render defects); §10.1 |
| VIEW-02 | Page 1 interactive before the last page parses | §10.2 — **measured 1441× ratio**; the scaffold's eager loop actively prevents this |
| VIEW-03 | Select and copy text, browser find | §10.3 (`TextLayer` class verified present in the pinned pdf.js; scaffold is canvas-only) |
| VIEW-04 | Thumbnail rail with classification badges | §10.4 (`RunIndex.page(n).bucket` already supplies it) |
| CLAS-06 | Page classification badges in the thumbnail rail | §10.4 |
| CLAS-07 | Refusal screen names a specific external OCR route + one-click notify | §10.5 (OCR-03 makes the notify signal a *measurement*, so it cannot be a local state toggle) |
| EDIT-01 | Select a run in the browser, hit-tested against server-issued boxes | §4 — **measured: `RunRecord` carries no bbox and cannot produce a height**; the single biggest engine gap |
| EDIT-05 | Undo/redo, replace-all undoes as one step | §11 (storage model that already admits a batch) |
| FONT-07 | Change size, weight, style, colour on edited text | §3.3 — **`RecipeOp` is `{run_id, new_text}` only and `parse_recipe` rejects any third key.** FONT-07 has zero engine support today |
</phase_requirements>

---

## Summary

The single most useful thing this research produced is a file:line-grounded audit of the salvaged
scaffold against all 20 requirements (§2). The short version: **the scaffold is a demo shell, not a
partial implementation.** It satisfies zero of the seven privacy requirements and zero of the four
ingest requirements, and three of its four viewer requirements are unimplemented rather than
broken. Two of its 1,105 lines of `server/app.py` are load-bearing for Phase 4; roughly 700 lines
implement Phase 6/7/8 features (PDF/A, DOCX, compress, split, merge, rotate) that this phase must
not carry. `server/ephemeral.py` — the file whose docstring recites the privacy model verbatim — is
288 lines of **dead code that raises `NameError` on import**, imported by nothing.

All four defects named in D-4.1 were re-verified against the real code. Three reproduce exactly;
one is **misdescribed** in the `.hermes` document and is actually a different (and more
interesting) defect. Six further defects of equal or greater severity were found that the
`.hermes` list does not mention, including an INGE-01 violation, a D-11 violation, and a
`NameError` that makes the entire scratch subsystem non-functional outside the ASGI startup event.

Three findings change what the plan must contain rather than merely how it is written. **First:
FONT-07 has no engine support at all** — `RecipeOp` is a frozen two-field dataclass and
`parse_recipe` rejects any recipe op carrying a third key, so FONT-07 requires a Phase 3 contract
extension, not UI work. **Second: EDIT-01's server-issued boxes do not exist and cannot be derived
from `RunRecord` alone** — a run's width comes out of `GlyphRecord.x/advance` correctly (measured
40.0pt for a real run) but its height measures 0.0, because `advance` is purely horizontal and no
font size, ascent, or descent survives onto `RunRecord`. **Third: `isEvalSupported` was removed
from pdf.js** — it appears nowhere in the pinned `pdfjs-dist` 6.2.108, and all three browser
bundles contain zero `eval(` and zero `new Function(` occurrences, verified by grep. ROADMAP
criterion 3's `isEvalSupported: false` clause is a no-op against the pinned version; the CSP half
is real and now actually achievable.

**Primary recommendation:** treat the scaffold as a *route map and a dependency set*, not as an
implementation. Delete `server/engine_replace.py`, `server/ephemeral.py`, `server/diag*.py`, and
every export endpoint outside Phase 4's scope, then rebuild `server/app.py` around
`engine.recipe`. The port is smaller than the audit suggests because the engine already does the
hard part; what the scaffold contributes is a working Vite/pdf.js/FastAPI dependency graph and a
demonstration of which endpoint shapes the client wants.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Magic-byte sniff + size cap (INGE-01) | API / Backend | — | A trust boundary. Client-side checks are advisory only; the byte that matters is the one the server sees. |
| PDF parse / run index (VIEW-04, CLAS-06, EDIT-01) | Isolated worker | API relays only | PRIV-07 is explicit: never in the request process. The request process holds bytes transiently and dispatches. |
| Password unlock (INGE-02) | Isolated worker | Browser (prompt UI) | The password must reach `pikepdf.open`/`playa` in the worker; the browser only collects it and must never persist it. |
| Signature detection + warning (INGE-03) | Isolated worker (detect) | Browser (warn) | Detection is an object-graph read; the *warning before saving* is a UI gate. |
| Page rasterization (VIEW-01) | Browser (pdf.js) | API (server PNG fallback) | pdf.js already holds the authoritative bytes client-side. A server render endpoint is a second, avoidable copy of the document — prefer client rendering. |
| Text layer / select+copy/find (VIEW-03) | Browser | — | `TextLayer` is a pdf.js DOM construct. No server involvement. |
| Progressive first-page interactivity (VIEW-02) | Browser + API | — | Both halves must be lazy: pdf.js `getPage(1)` and the server's per-page `RunIndex.page(n)`. |
| Run bounding boxes (EDIT-01) | API / Backend | — | D-4.2 is settled: server owns text addresses. The client may never derive a box from pdf.js text items. |
| Recipe planning / dry-run report (D-03) | API → isolated worker | Browser (renders it) | D-03 exists so the UI renders the structured report rather than recomputing it. |
| Recipe application (EDIT-01, FONT-07) | Isolated worker | — | Writes bytes; D-11 all-or-nothing. |
| Undo/redo store (EDIT-05) | Browser | — | The client is the system of record (ARCHITECTURE.md Option C). A server-side undo log is durable state, which is the anti-feature. |
| Page ops materialization (PRIV-01's zero-upload path) | Browser (`@cantoo/pdf-lib`) | — | The structural rule: empty override set ⇒ client materializes with zero upload. Phase 6 depends on this being true in Phase 4. |
| `no-store` headers (PRIV-06) | API / Backend | CDN (verified) | Sending the header is backend; *verifying* `BYPASS`/`DYNAMIC` requires a live CDN check. |
| CSP (PRIV-06) | Frontend server / static host | — | Delivered as a response header on the HTML document, not by the API. |

---

## Section 1 — The Phase 3 engine port

`main` (commit `0acd3eb`) has `engine/` **without** `recipe.py`, `rewrite.py`, `fit.py`, `fonts.py`,
and **without** `fonts/`. Verified by directory listing on both checkouts.

### 1.1 What must move

| Item | On `main`? | Notes |
|---|---|---|
| `engine/recipe.py` (731 lines) | No | The contract surface. `plan_recipe` / `apply_recipe` / `parse_recipe`. |
| `engine/rewrite.py` (1,153 lines) | No | Content-stream surgery + D-04 runtime matrix guard. |
| `engine/fit.py` (390 lines) | No | The D-01 fit ladder. |
| `engine/fonts.py` (691 lines) | No | D-05/D-06 substitution routing, D-13 subsetting, Type0 embedding. |
| `fonts/` (12 TTFs + `LICENSE-OFL.txt`) | **No directory at all** | D-07 Liberation trio. |
| `tools/pdftool.py` `edit` subcommand | No (`index` only) | The reference renderer of the D-03 report (`_print_report`, lines 94–111). |
| `harness/g2b_fixture.py`, `masked_diff.py`, `render_diff.py`, `structural_diff.py` | Partially | Needed for the Gate G3 pixel-diff criterion. |
| 12 Phase 3 test files | No | `test_recipe.py`, `test_rewrite.py`, `test_fit.py`, `test_fonts.py`, `test_gate_g2a.py`, `test_gate_g2b.py`, `test_pdftool_edit.py`, and 5 others. Worktree has 34 test files; `main` has 24. |
| `Dockerfile.ci` `opentype-sanitizer` pin | Present on worktree (`OTS_VERSION=8.2.1+dfsg-2`) | Verify it survives the merge. |

`main` **adds** four dependencies the worktree's `pyproject.toml` does not have:
`fastapi==0.141.1`, `uvicorn==0.52.1`, `python-multipart==0.0.32`, `python-docx==1.2.0`
(verified by reading both `pyproject.toml` files). `uv.lock` will conflict on merge.
`python-docx` is a **Phase 8** dependency — it should not be added in Phase 4.

**Direction matters.** The branch is 45 commits ahead of `main` and carries the entire project
gate. Merging `main` *into* the Phase 3 branch (bringing ~2,900 lines of scaffold) is far smaller
and lower-risk than porting ~3,000 lines of proven engine plus `fonts/` onto `main`.
[VERIFIED: direct file inspection of both checkouts]

### 1.2 The server-side contract surface (do not re-derive)

```python
# engine/recipe.py
MAX_RECIPE_OPS = 50_000          # line 73
MAX_NEW_TEXT_CHARS = 10_000      # line 78

@dataclass(frozen=True, slots=True)
class RecipeOp:                  # line 81
    run_id: str
    new_text: str

class RecipeTooLargeError(Exception): ...        # line 89

def parse_recipe(data: bytes) -> tuple[RecipeOp, ...]: ...        # line 95
def plan_recipe(pdf_path, recipe) -> RecipeReport: ...            # line 369
def apply_recipe(pdf_path, recipe, output_path) -> RecipeReport:  # line 562

@dataclass(frozen=True, slots=True)
class ResolvedOp:                # line 133
    op: RecipeOp
    ok: bool
    reason: str | None = None
    strategy: str | None = None
    delta_pt: float | None = None
    run: RunRecord | None = None
    verdict: RunVerdict | None = None
    all_page_runs: tuple[RunRecord, ...] | None = None
    fit_result: FitResult | None = None
    substitution_key: tuple[BundledFamily, BundledVariant] | None = None

@dataclass(frozen=True, slots=True)
class RecipeReport:              # line 163
    ok: bool
    resolved: tuple[ResolvedOp, ...]
```

**`parse_recipe` is already the untrusted-input boundary** and is written as such: stdlib
`json.loads`, never `eval`; `set(item) != {"run_id","new_text"}` rejects unknown keys
(`recipe.py:117`); both size ceilings checked before any per-op object is constructed
(`recipe.py:110`, `:123`). The server should feed request bytes straight into it rather than
building `RecipeOp`s from a Pydantic model — that would duplicate the validation and drift from it.
[VERIFIED: engine/recipe.py read in full]

**Refusal vocabulary** (EDIT-04 — the UI must render these, never invent prose). Five fixed
strings minted by `engine/recipe.py`:
`"malformed_run_id"`, `"source_hash_mismatch"`, `"run_id_not_found"`, `"resolution_failed"`,
`"fit_refused"` (recipe.py:137–143), plus `"duplicate_run_id_in_recipe"` (line 423),
`"run_lost_after_earlier_edit"` and `"substitution_key_changed_after_earlier_edit"` (lines 626–631).
Everything else is an **unmodified pass-through** of `RunVerdict.reason`, `MappingVerdict.reason`,
or `FitResult.refusal_reason`.
**Plan implication:** the client needs a reason→copy mapping table with an explicit
unknown-reason fallback, and the server must never rewrite or prettify a reason string in transit.

**D-10 (`source_hash`).** `run_id` grammar (`engine/run_id.py:76–101`):
`{source_hash}:p{page}:c{part}[/x{objid}][/a{idx}:{state}][/t{n}][/y{name}]:o{byte_offset}[:g{s}-{e}]`
`plan_recipe` computes `sha256(path.read_bytes())` (recipe.py:429) and refuses any op whose embedded
hash differs — **no override flag exists and none may be added** (D-10 is explicit that Phase 4
would inherit it as an API parameter). This means the server's content-address and the run_id's
`source_hash` are the same value and must not be two separate concepts.

**D-11 (all-or-nothing).** `apply_recipe` returns `plan_recipe`'s report unchanged on success
(recipe.py:583–584: "a dry run and a commit of the same recipe are the same report by
construction") and on any failure returns **without reaching `save()`** (recipe.py:707–711), so no
output file exists at all. The API must expose dry-run and commit as the *same* response schema.

### 1.3 What G2b did NOT prove (carry into Phase 4 risk)

From `G2B-GATE-RESULTS.md` "What was NOT tested": only 3 of 12 candidate documents manually
reviewed; only Acrobat's copy-paste path checked; no glyph-level cross-viewer rendering parity;
**no non-Latin substitution exercised**. The last one matters for Phase 4 because a public endpoint
gets CJK and RTL input on day one. `engine/classify_run.py:172 _is_rtl` already refuses RTL runs
by name, so the failure mode is a named refusal rather than a wrong result — but the *rate* is
unmeasured. [CITED: G2B-GATE-RESULTS.md lines 73–93]

---

## Section 2 — Scaffold audit (the highest-value output)

Read-only inspection of `/Users/prempatel/Pictures/pdf-tool` on branch `main`, commit `0acd3eb`.
Sizes: `server/app.py` 1,105 lines, `server/engine_replace.py` 459, `server/ephemeral.py` 288,
`server/font_subsetter.py` 104, `server/smoke_test.py` 120, `server/diag{,2,3}.py` 95 combined,
`client/src/App.jsx` 692, `client/src/main.jsx` 10.

### 2.1 The four D-4.1 defects, re-verified against the code

| # | D-4.1 claim | Verdict | Evidence |
|---|---|---|---|
| 1 | `replace_text_in_pdf(...)` raises `UnboundLocalError` on `bundled_dir` | **CONFIRMED — reproduced live** | `server/engine_replace.py:285-289` declares the parameter `bundled_fonts_dir`; line 305 reads `bundled_dir = bundled_dir or _FONTS_DIR_DEFAULT`, making `bundled_dir` a local assigned on that same line. Ran: `UnboundLocalError: cannot access local variable 'bundled_dir' where it is not associated with a value`. |
| 2 | `page.render(dpi=...)` → HTTP 500 on pypdfium2 5.12.1 | **CONFIRMED — reproduced live** | `server/app.py:357` and `:390`. Measured signature: `render(self, scale=1, rotation=0, crop=..., ...)` — no `dpi`. Ran: `TypeError: _parse_renderopts() got an unexpected keyword argument 'dpi'`. |
| 3 | `client/src/App.jsx` **calls** `/jobs/{id}/runs`, which does not exist | **MISDESCRIBED — the real defect is worse** | The endpoint genuinely does not exist (`grep "runs" server/app.py` finds only `page.runs` at `:218`,`:228`). But `App.jsx` does **not** call it. `App.jsx:126-153` `doFindReplace` contains an **empty `for` loop over a comment** and then fabricates a UI message: *"the /jobs/{id}/runs endpoint needs to be added to the server."* So find-and-replace is not broken-and-wired, it is **cosmetic**. Nothing in the client can produce a `run_id`, so no edit can be submitted at all. |
| 4 | No CORS middleware | **CONFIRMED** | `grep "add_middleware" server/app.py` → no matches. Works only via the Vite dev proxy (`client/vite.config.js:8-13` proxies `/upload`, `/jobs`, `/fonts`, `/health`). |
| 5 | `client/node_modules/` committed to git | **CONFIRMED** | `git ls-files client/node_modules | wc -l` → **5,041 files**. |

### 2.2 Six further defects the `.hermes` list does not mention

| # | Defect | Severity | Evidence |
|---|---|---|---|
| 6 | **INGE-01 is violated by design.** Upload validates by **file extension**. | Blocks INGE-01 | `server/app.py:169-170`: `if not file.filename or not file.filename.lower().endswith(".pdf"): raise HTTPException(400, ...)`. No `%PDF` check exists anywhere in `server/`. |
| 7 | **`SCRATCH_ROOT` raises `NameError`, not `None`.** Both `app.py:49` and `ephemeral.py:40` write `SCRATCH_ROOT: Path` — a bare *annotation*, which binds no value. `_ensure_scratch()` then tests `if SCRATCH_ROOT is None`. | Breaks all non-ASGI use | Ran `server.app._ensure_scratch()` → `NameError: name 'SCRATCH_ROOT' is not defined`. Masked in production only because `@app.on_event("startup")` (`app.py:1096-1099`) assigns it. Any unit test, worker subprocess, or CLI entry point that touches scratch without the ASGI lifespan crashes. |
| 8 | **`server/ephemeral.py` is dead code that crashes on import.** | 288 lines of misleading provenance | `import server.ephemeral` → `NameError: name 'SCRATCH_ROOT' is not defined` (from `blob_store = BlobStore()` at line 280 → `_ensure_scratch()`). Nothing imports it — `app.py` imports only `server.engine_replace` and `server.font_subsetter` (`app.py:34-35`). Its docstring is the most accurate privacy statement in the repo and **none of it is in force.** |
| 9 | **D-11 violated: `replace_text_in_pdf` writes partial output.** It collects refusals into `refused_list` and then **saves anyway** (`engine_replace.py:331 pdf.save(...)`). | Contradicts a locked Phase 3 decision | This is the concrete reason D-4.1 says *delete, not patch*. Also note it calls `decode_run_id` (`:315`) but **never checks `source_hash`** — D-10 absent. |
| 10 | **PRIV-04: a raw user filename is written to the log.** | Blocks PRIV-04 | `server/ephemeral.py:157`: `log.info("job created: %s (digest=%s..., file=%s)", job_id, pdf_digest[:16], filename)`. `_sanitize_filename_for_log` is defined at `:209` and **never called** (grep: zero call sites). RETENTION-MAP's Logs row is explicit: *"Log statements never include filenames."* Currently latent because the module is dead — it becomes live the moment anyone "revives" it. |
| 11 | **Second live render defect, downstream of #2.** Even after `dpi=`→`scale=`, `app.py:358` calls `image.tobytes(format="png")` and `:395` calls `image.size`. | Both are HTTP 500 | Measured on pypdfium2 5.12.1: `PdfBitmap` has neither. Its real API is `.to_pil()`, `.width`, `.height`, `.buffer`, `.to_numpy()`. Correct call is `page.render(scale=dpi/72).to_pil()`. |

### 2.3 Privacy requirements vs. the scaffold

| Req | Scaffold status | Evidence |
|---|---|---|
| PRIV-01 | **Absent.** No local/server disclosure anywhere in `App.jsx`. `@cantoo/pdf-lib` is imported (`App.jsx:3`) but only used for a page-render helper — there is no zero-upload materialization path. | grep |
| PRIV-02 | **Absent.** `_jobs` is a module-level dict (`app.py:101`) holding `pdf_path`, `page_count`, `classification`, `output_path`. Losing it loses the session with no recovery. **No `409` anywhere** in `server/`. | `grep -n "409" server/app.py` → no matches |
| PRIV-03 | **Not satisfied.** Scratch is `tempfile.mkdtemp()` on the host FS (`app.py:57`) — on Linux `/tmp` is commonly a real disk. No tmpfs assertion, no per-job container. Uploads are written **directly into the scratch root**, not into the per-job dir (`app.py:177` vs. the unused `_scratch_dir` at `:70`). No queue exists (correct — see §7.3) but nothing asserts that. | read |
| PRIV-04 | **Violated** (defect #10) and unasserted. `app.py:172` logs `digest[:16]` + size, which RETENTION-MAP explicitly permits (hashes are one-way). | read |
| PRIV-05 | **Absent.** Zero tests exist for `server/` on either branch (`ls tests/` on `main` = 24 files, none server-related). | ls |
| PRIV-06 | **Absent.** No `Cache-Control` header anywhere in `server/` (grep: no matches). No CSP in `client/index.html`. No `isEvalSupported` in `App.jsx` (moot — see §9.2). | grep |
| PRIV-07 | **Violated.** `job_status` calls `RunIndex(job["pdf_path"])` (`app.py:207`) directly in a sync FastAPI route — same process, threadpool worker. Every parse of untrusted input runs in the request process. | read |

### 2.4 What the scaffold gets *right* (keep this)

- **Content-addressing is already correct in shape.** `_content_address` is `sha256(data).hexdigest()`
  (`app.py:79-80`) — the same digest `RunIndex.__init__` computes for `source_hash` (`index.py:118`).
  These are the same value and should stay unified.
- **Job IDs are opaque and unguessable** — `sha256(os.urandom(16))[:16]` (`app.py:103-104`), not
  sequential and not derived from content. ARCHITECTURE.md:229 warns against a user-visible document
  ID that is anything other than the content hash; an opaque session handle alongside it is fine.
- **`_scratch_dir` has the right `try/finally` + `shutil.rmtree` shape** (`app.py:70-77`) — it is just
  not used on the upload path.
- **The `/jobs/{id}/status` classification payload shape is close to what CLAS-06 needs**
  (`app.py:219-227`): per page `{page, bucket, runs, editable, substitution, not_editable}`.
  Its defect is eagerness (§10.2), not shape.
- **Dependency set is real and installed**: `fastapi 0.141.1`, `uvicorn 0.52.1`, `starlette 1.6.0`,
  `pydantic 2.13.4`, `python-multipart 0.0.32`, `pdfjs-dist 6.2.108`, `@cantoo/pdf-lib 2.8.1`,
  `vite 5.x`, `react 18.2`. Verified via `importlib.metadata` and `client/node_modules`.

### 2.5 Out-of-scope code carried by the scaffold

`server/app.py` implements endpoints for **PDF/A** (`:410`, EXPO-06, Phase 8), **compress**
(`:532`, EXPO-02, Phase 7), **split** (`:653`, EXPO-03, Phase 7), **merge** (`:733`, PAGE-04,
Phase 6), **rotate** (`:801`, PAGE-02, Phase 6), **DOCX** (`:867`, EXPO-07, Phase 8), **text**
(`:998`) and **HTML** (`:1046`, EXPO-05, Phase 7). That is roughly 700 of 1,105 lines.

Two specific hazards:
- `_pdf_to_docx` (`:912`) is a **second text-extraction path** — it walks `playa` glyphs and
  clusters them by y-proximity with its own `y_tolerance = 3.0` heuristic, bypassing
  `engine.clusterer` entirely. EXPO-05 states plainly that a second extraction path anywhere means
  the text model is under-specified. This must be deleted, not carried.
- `_convert_to_pdfa` (`:458`) has a `pass  # For now, skip` inside its font-embedding loop
  (`:484`) and produces files that will not pass veraPDF. Phase 8's gate is veraPDF-in-CI.

**Licensing is clean, verified.** No `import fitz`, no `pdf2docx`, no Ghostscript subprocess in
`server/`. `tools/license_gate.py` scans the resolved installed closure (not top-level metadata),
so it will catch a regression — but only if the server dependencies are added to `pyproject.toml`
and `uv sync --locked` runs in the license-gate workflow.

---

## Section 3 — Engine gaps the plan must close

### 3.1 There is no run bounding box (EDIT-01)

`RunRecord` (`engine/records.py:65-70`) has exactly four fields: `run_id`, `glyphs`,
`display_text`, `page`. No bbox, no font size, no colour.

Measured derivation attempt on a real run (`irs_form_w4.pdf` p0, text `'W-4'`):

```
derived bbox from x/y/advance: (56.2,53.1)-(96.2,53.1)   w=40.0  h=0.0
```

Width is correct and usable. **Height is 0.0** — `GlyphRecord.advance` is `(dx, dy)` and is purely
horizontal for horizontal writing mode, and `GlyphRecord`'s 13 fields (`records.py:19-33`) carry no
font size, ascent, or descent. `ClusterAttrs.effective_em` (`records.py:61`) holds the size the
clusterer used, but `ClusterAttrs` **is not retained on `RunRecord`** — it travels beside
`GlyphRecord` during clustering and is dropped.

Three viable sources for the missing height, in preference order:
1. Re-scan for the active `Tf` size. `engine/recipe.py:189 _active_font_name_and_size` and
   `engine/rewrite.py:947` already do exactly this, with a spec-correct regex
   (`_TF_NAME_SIZE_RE`, `recipe.py:186`). Reuse, do not re-implement.
2. The font descriptor's `/Ascent` / `/Descent`, via `engine.encoding_table.resolve_font`.
3. A fixed padding multiple of the font size. **There is precedent**: `tests/test_gate_g2b.py`
   already uses "a fixed padding standing in for real font ascent/descent" as a ponytail-tagged
   simplification (recorded in `G2B-GATE-RESULTS.md:65`).

**Recommendation:** option 1 for the size, option 3 for ascent/descent padding, tagged
`# ponytail:` with the upgrade path to option 2. A hit box does not need typographic precision; it
needs to be unambiguous between adjacent lines. But the derivation must live in **one** engine-side
module (e.g. `engine/boxes.py`) so the box the server issues and the box `apply_recipe` reasons
about cannot drift.

Also note the coordinate frame: PDF user space, origin bottom-left
(`irs_form_w4.pdf` MediaBox `[0, 0, 611.976, 791.968]`). pdf.js viewport is top-left. The pinned
`pdfjs-dist` 6.2.108 exports `PageViewport.convertToViewportPoint` and `convertToPdfPoint`
(verified present in `build/pdf.mjs`) — that is the transform, and it belongs on the client.

### 3.2 There is no password parameter (INGE-02)

`RunIndex.__init__` calls `pikepdf.open(path)` and `open_document(path)` (`index.py:113-114`) with
no password. `classify_document` (`classify_run.py:305`) and `plan_recipe` / `apply_recipe`
(`recipe.py:443`, `:646`) likewise. INGE-02 requires threading a password through
`RunIndex` → `_classify_one_page` → `plan_recipe` → `apply_recipe` → `pikepdf.open(password=...)`
and playa's equivalent.

**Constraint the plan must respect:** the password is document content by any reasonable reading of
PRIV-04. It must never be logged, never enter an error message, never be stored in the job record,
and never appear in an error-reporter frame local. Threading it as a parameter through five call
sites while keeping it out of every `repr()` and traceback is a real design problem, not a
signature change. A `SecretStr`-style wrapper with a redacting `__repr__` is the standard control.

### 3.3 FONT-07 has no representation in the recipe contract

`RecipeOp` is `{run_id, new_text}` (`recipe.py:81-86`) and `parse_recipe` enforces
`set(item) != {"run_id","new_text"}` → `ValueError` (`recipe.py:117-120`). `grep -rn "FONT-07"
engine/ tools/ tests/` returns **zero matches**. The only styling machinery in `engine/rewrite.py`
is the `Tf` name/size save-restore bracket (`:947-955`), which preserves the *original* size rather
than setting a new one.

So FONT-07 (size, weight, style, colour on edited text) needs, at minimum:
- A recipe schema extension — an optional `style` object on `RecipeOp`, and a matching relaxation of
  `parse_recipe`'s exact-key check. **This changes D-09's wire format**, which 03-CONTEXT.md calls
  "Phase 4's wire format, unchanged." Adding an *optional* key is a backward-compatible extension
  (old recipes still parse); the plan should say so explicitly rather than let it look like a
  violation.
- Size → the `Tf` operand, which **invalidates the fit**: the D-01 ladder measures against the
  original advance width. A size change makes every fit decision wrong unless `fit_run` is re-run
  with the new size. Weight/style → a *different bundled face*, i.e. a `(family, variant)` change,
  which routes through D-13's per-family subsetting. Colour → an `rg`/`g`/`k` operand, which
  `engine/rewrite.py:624` notes is already a run-breaking attribute.
- Every one of those interacts with a locked Phase 3 decision.

**This is the single largest under-estimation risk in the phase.** FONT-07 reads like one UI toolbar
and is in fact a four-way engine change touching D-01, D-05, D-09 and D-13. The plan should either
give it its own wave with its own acceptance criteria, or scope it explicitly (e.g. colour +
weight/style via bundled-variant routing; size deferred with a named refusal) and record the
scoping decision.

### 3.4 `MAX_RECIPE_OPS` is a CLI-era number

`MAX_RECIPE_OPS = 50_000` and `MAX_NEW_TEXT_CHARS = 10_000` were reasoned for "a single
`pdftool edit` invocation" with "a human operator" (`recipe.py:67-78`). On an anonymous public
endpoint they are the request-body DoS bound. 50,000 ops × 10,000 chars is a 500 MB worst-case
recipe — above `MAX_UPLOAD_BYTES` (50 MB) but the recipe route has no such cap. The plan needs a
separate request-body size limit on the recipe route, applied *before* `json.loads`.

---

## Section 4 — What the client may and may not do (D-4.2)

| Client MAY | Client MUST NOT |
|---|---|
| Hold the authoritative original `ArrayBuffer` (ARCHITECTURE.md Option C) | Derive a `run_id` from pdf.js text items |
| Echo a `run_id` byte-for-byte as received | Parse, split, or reconstruct a `run_id` (the grammar has 8 optional segments — `run_id.py:64-73`) |
| Transform a server-issued box through `convertToViewportPoint` | Compute a box from `getTextContent()` items |
| Render the `RecipeReport` fields verbatim | Recompute `delta_pt`, `strategy`, or any refusal reason (D-03) |
| Materialize page-ops output locally via `@cantoo/pdf-lib` (PRIV-01) | Apply a text edit locally |
| Hold the undo stack | Persist it server-side |

**Wire shape recommendation.** One endpoint returning both boxes and verdicts per page, so the
badge data and the hit-test data cannot disagree:

```
GET /jobs/{id}/pages/{n}/runs
→ { "page": n,
    "bucket": "editable",
    "runs": [ { "run_id": "<opaque, echo verbatim>",
                "text": "W-4",
                "box": [56.2, 53.1, 96.2, 65.1],   // PDF user space, bottom-left origin
                "state": "editable_original",
                "reason": null } ] }
```

`bucket` on the same response is what CLAS-06 renders. `state`/`reason` is CLAS-04's three-state
verdict, already computed by `engine/classify_run.py` — the client greys out `not_editable` runs
*before* the user clicks, which is CLAS-04's stated point.

---

## Section 5 — Fixture inventory (measured against the real corpus)

`corpus/manifest.json` has 217 entries, all present in `corpus/public/`. Category counts:
`contents_array` 114, `subset_fonts` 140, `symbolic_fonts` 133, `inline_images` 68,
`type0_identity_h` 33, `form_xobjects` 19, `malformed` 17, `type3` 12, `encrypted` 12,
`cid_keyed_cff` 12, `annotation_appearance_streams` 13, `tables` 3, `justified_right_aligned` 3,
`ocr_scan` 2, `vector_outlined_text` 1.

### 5.1 INGE-01 — magic bytes

**Measured: 217 / 217 files have `%PDF-` at byte offset 0.** Zero at a later offset within the
first 1024 bytes; zero missing.

```
%PDF- at offset 0: 217
%PDF- at offset >0 within first 1024B: 0
no %PDF- in first 1024B: 0
```

So the strict sniff `data[:5] == b"%PDF-"` is safe against every real document in the corpus,
including all 17 `malformed` fixtures. The PDF spec and Acrobat tolerate leading junk before the
header; a tolerant `head[:1024].find(b"%PDF-") >= 0` sniff is the permissive alternative. **Prefer
the strict form** — at a trust boundary, tolerance is attack surface, the corpus does not need it,
and a refusal here is a clean named error rather than a wrong result. Record it as a measured
decision, not a guess.

### 5.2 INGE-02 — password fixture: **must be built**

**Measured: zero corpus documents require a user password.** `irs_form_w9_encrypted.pdf` opens with
an empty password (owner-password-only, AES-256 R=6, V=5) — it is a *permissions* fixture, not an
INGE-02 fixture. Sweeping all 217 files for `pikepdf.PasswordError` returned an empty list.

Wave 0 must build a user-password fixture (`pikepdf.save(..., encryption=pikepdf.Encryption(user="…", owner="…", R=6))`).
Note PITFALLS.md's warning that owner-password-only encryption "is trivially strippable and is not
access control" — the UI must not present it as protection.

### 5.3 INGE-03 — signed fixture: **must be built**

**Measured: zero corpus documents carry an actual signature.** Five files
(`irs_form_1040.pdf`, `irs_form_w9.pdf`, `irs_form_w4.pdf`, `irs_form_1040_spanish.pdf`,
`irs_form_w9_encrypted.pdf`) have `/AcroForm /SigFlags 2`. Value 2 is bit 2 (`AppendOnly`) — bit 1
(`SignaturesExist`) is **not** set, and no `/FT /Sig` field carries a `/V`. These are forms with
signature *fields*, not signed documents.

This is a real trap: a detector written as `"/SigFlags" in acroform` fires on all five and reports
five signed IRS forms that are not signed. **INGE-03's detector must check for a `/FT /Sig` field
with a `/V` value (a signature dictionary with `/ByteRange` and `/Contents`), or `SigFlags & 1`** —
and the *correct negative* case is exactly these five files. Both fixtures are Wave 0 work.

### 5.4 INGE-04 — all three hostile fixtures must be built

The 17 `malformed` files are one Isartor broken-trailer conformance file plus 16 govdocs1 files
auto-categorized by `tools/probe_corpus.py` (its criteria at `:138`, `:143`, `:146`, `:174` are
"pikepdf raised", "missing trailer key", "opened but broken deeper"). **None of ROADMAP criterion
2's three named inputs exists as a fixture.**

| Input | Build approach | Notes |
|---|---|---|
| Decompression bomb | A `FlateDecode` stream whose decompressed size is orders of magnitude above the file. Also worth a PNG-predictor variant with absurd `/Columns`/`/Colors` (the CVE-2026-41312 shape). | Must be built as a *fixture generator* checked into `tests/fixtures/`, not a checked-in multi-GB artifact. Generate at test time from a small script. |
| Cyclic page tree | `/Pages /Kids` referencing an ancestor. | `pikepdf` will likely refuse to *write* this; build it with raw byte assembly. Note `qpdf`/`pikepdf` may itself detect the cycle at open — in which case the test asserts a clean named refusal rather than a worker kill, which still satisfies "fails on its own limits". |
| Self-referencing Form XObject | A Form XObject whose content stream contains `Do` naming itself. | This is the shape the run index actually walks — `engine/shared_xobjects.py` and `engine/walker.py` traverse `/XObject` graphs. Verify whether a visited set already exists there; if not, that is an engine fix, not just a worker limit. |

**Design the assertion carefully.** "Fails on its own limits rather than on the host" has three
acceptable outcomes: (a) the worker is killed by `RLIMIT_AS`/timeout and the API returns a named
error; (b) the engine detects the cycle/bomb and returns a named refusal without ever hitting the
limit; (c) an existing cap (`MAX_DOCUMENT_GLYPHS = 10_000_000`, `DocumentTooLargeError`,
`index.py:78-84`) fires first. All three satisfy the requirement. What must *not* happen is the
request process hanging or the host OOMing. Assert on **host survival + a named error**, not on a
specific kill mechanism — otherwise the test breaks whenever a cheaper guard fires first.

---

## Section 6 — Worker isolation (INGE-04, PRIV-07)

### 6.1 Measured platform constraint — this is decisive

On the dev machine (macOS 15.7.7, arm64):

| Call | Result |
|---|---|
| `setrlimit(RLIMIT_AS, (256MB, 256MB))` | `ValueError: current limit exceeds maximum limit` |
| `setrlimit(RLIMIT_AS, (256MB, RLIM_INFINITY))` | `ValueError: current limit exceeds maximum limit` |
| `setrlimit(RLIMIT_DATA, (256MB, 256MB))` | `ValueError: current limit exceeds maximum limit` |
| `setrlimit(RLIMIT_CPU, (2, 2))` | **SET OK** |
| `docker info` | `command not found` |

**`RLIMIT_AS` cannot be set at all on this machine**, in a child process, with both limits reported
as `RLIM_INFINITY` beforehand. This is not a permissions problem to work around — it is a
platform-behaviour difference, and it means:

- The `RLIMIT_AS` half of ROADMAP criterion 2 **is not exercisable on macOS dev** and must be
  `pytest.mark.skipif(sys.platform == "darwin")` with an explicit reason string.
- CI **is** `ubuntu-latest` on all four workflows (`corpus.yml`, `harness.yml`,
  `license-gate.yml`, `tests.yml`), and `harness.yml`/`corpus.yml` already build and run
  `Dockerfile.ci`. So the memory-cap clause is provable in CI. It must be *asserted* in CI, or it
  will silently never run.
- Docker is not installed locally, so the "per-job container" option in D-4.1's discretion list
  cannot be exercised on the dev machine either.
- **Wall-clock timeout is fully portable and is the control that must never be skipped.**
  `RLIMIT_CPU` also works on macOS, but note it caps *CPU* time, not wall time — a worker blocked
  on I/O never trips it. Use both: `RLIMIT_CPU` inside the child, and a parent-side wall-clock
  `subprocess.run(timeout=…)` / `process.join(timeout)` + `SIGKILL`.

### 6.2 Mechanism comparison

| Mechanism | INGE-04 memory cap | Wall clock | PRIV-03 tmpfs | macOS dev | Complexity |
|---|---|---|---|---|---|
| **`subprocess` + `preexec_fn` rlimits** | Linux only (measured) | Yes, parent-side | Needs an explicit tmpfs mount; not automatic | Partial (CPU only) | Low |
| **`multiprocessing` fork + rlimits** | Linux only | Yes | Same | Partial | Low, but forking a FastAPI process inherits its whole heap and open sockets — an argument against |
| **Per-job container** | Yes (`--memory`) | Yes (`--stop-timeout` + parent kill) | Yes (`--tmpfs /scratch`), read-only rootfs, no network, non-root, seccomp | **Not available** (no Docker) | High: image build, spawn latency, an orchestrator |

**Recommendation: a short-lived `subprocess` worker with a JSON-over-stdio protocol**, plus
`RLIMIT_AS` + `RLIMIT_CPU` set in the child (guarded by a `try/except ValueError` so macOS
degrades rather than crashes) and a parent-side wall-clock kill. Then run *that same worker* inside
the read-only-rootfs, tmpfs-scratch, no-network, non-root container in production and in CI.
Rationale: the subprocess boundary is what satisfies PRIV-07 and it is the only part testable on
both platforms; the container is what satisfies PRIV-03's "per-job container" and the seccomp/no-
egress posture, and it is testable in CI where Docker exists. Choosing one *or* the other leaves a
requirement unprovable. This also matches ARCHITECTURE.md:689's stated non-negotiable posture.

**Do not build a job queue for this.** See §7.3.

### 6.3 Making PRIV-07 testable rather than asserted

"PDF parsing never runs in the request process" is easy to write and easy to regress. Two
complementary checks, both cheap:

1. **Static:** a test that imports `server.app` and asserts no `engine.*` module is in
   `sys.modules` afterwards — i.e. the request process never even imports the parser. This is a
   strong structural form of the requirement and it is a one-line assertion. It also forces the
   worker protocol to be data-only, which is what keeps document bytes out of the request process.
2. **Dynamic:** a test that patches the worker entry point to record `os.getpid()` and asserts it
   differs from the test process's pid across a real request.

Check (1) is the valuable one — it fails the moment someone adds a convenience `from engine.index
import RunIndex` at the top of `app.py`, which is exactly how this regresses.

---

## Section 7 — Privacy architecture

### 7.1 PRIV-01 — the structural rule, verbatim

> "if `overrides` is empty and no font/format op is present, the client materializes and downloads
> with zero upload; otherwise the server produces it."
> — `.planning/research/ARCHITECTURE.md:588`

The disclosure indicator must be **derived from that predicate**, not hand-labelled. 04-CONTEXT.md's
Specific Ideas say this outright, and Phase 6's PAGE-09 ("zero requests to document routes") is only
achievable later if the predicate is the real dispatch decision in Phase 4. Concretely: one function
that takes the pending operation set and returns `"local" | "server"`, used *both* to route the
operation and to render the badge. One source of truth or the badge becomes a lie.

Phase 4 ships no page ops, so the local branch has no operations to route yet. It must still exist
and be tested, or Phase 6 inherits a retrofit.

### 7.2 PRIV-02 — the `409` contract

> "If a hash is missing from cache, respond `409 {missing: ["sha256:…"]}` and let the client re-POST
> the bytes. **This path must be exercised in tests, not just written** — it is the thing that keeps
> the cache honest." — `ARCHITECTURE.md:222`

Two details the plan must get right:

- **Every document-touching route needs the 409 branch**, not just status. If `/pages/{n}/runs`
  200s from a cached run index while `/edit` 409s, the cache is not honestly evictable.
- **The `409` must be reachable in a test by evicting the cache, not by faking it.** The RETENTION-MAP
  Server-cache row names the mechanism: TTL expiry or `maxmemory`+`allkeys-lru`. An in-process LRU
  is acceptable for v1 (ARCHITECTURE.md:221 lists it as an option) and makes the test trivial.

**Conflict to resolve, flagged:** ARCHITECTURE.md:199 describes a separate `fp` fingerprint on each
override, verified before applying, yielding `409 STALE_RUN`. Phase 3's **D-10 supersedes this** —
the `source_hash` is embedded in the `run_id` itself and mismatch is a hard refusal with no override.
Building both means two staleness mechanisms disagreeing. **Recommend: D-10 only.** `409 SOURCE_MISSING`
is about cache residency; `source_hash_mismatch` is about document identity. They are different
conditions and should stay different responses (`409` vs. a `RecipeReport` with `ok=false`).

### 7.3 PRIV-03 — there is no queue, and that is the answer

> "**ARQ** — Job queue — **only if needed**. Add *only* when LibreOffice-backed conversion exceeds
> request timeouts. Everything else should be synchronous. **A queue is durable state — an
> anti-feature for a no-retention product.**" — `CLAUDE.md:89`

Phase 4 has no LibreOffice, no conversion, and no operation that exceeds a request timeout.
**Therefore Phase 4 must not have a queue**, and PRIV-03's queue clause is satisfied structurally:
by proving no queue exists. The same is true of PRIV-05's "object store" surface — RETENTION-MAP's
Object-store row reads "**No — not used for document bytes at all**".

This matters because a planner reading "the canary covers scratch, queue, logs, object store and
error reporter" could reasonably add Redis and an S3 client in order to have something to inspect.
That would introduce the exact durable state the requirement forbids. **Two of PRIV-05's five
surfaces are proved by absence** — see §8.

For scratch itself the assertion is concrete and portable enough:

```python
# Linux/CI: assert the scratch mount is tmpfs, not a bind-mounted volume
# RETENTION-MAP: "`mount` inspection in CI confirms scratch path is tmpfs"
```

`os.statvfs` / `/proc/mounts` on Linux; skip with a reason on macOS (where the RETENTION-MAP and
`ephemeral.py:37-39` both already concede tmpfs is unavailable).

---

## Section 8 — PRIV-05, the canary test (the hardest item in the phase)

RETENTION-MAP is the specification. Its per-hop "How to verify deletion" column already names the
mechanism for every surface — the plan should quote it rather than invent assertions.

### 8.1 The five surfaces × two paths

| Surface | Success path assertion | Crash path assertion | Proof style |
|---|---|---|---|
| **Scratch** | After the request returns, the per-job scratch dir does not exist; no file anywhere under the scratch root contains the canary. | Kill/except mid-job; same assertion. RETENTION-MAP: *"kill the container mid-job, confirm no bytes survive"*. | Positive (walk the FS) |
| **Queue** | No queue module is importable / configured; `sys.modules` has no ARQ/Redis client. | Same. | **Negative — proof by absence** |
| **Logs** | `caplog` capture (and the raw log file if one exists) contains no canary substring, no filename, no decoded text. | Force an exception inside the worker with the canary in the input; same assertion over the traceback-driven log records. | Positive (grep captured output) |
| **Object store** | No S3/R2/GCS client exists in the dependency closure or is ever constructed. | Same. | **Negative — proof by absence** |
| **Error reporter** | Install a fake reporter (a `before_send`-shaped hook that records the event dict); assert no event captured on the success path, or if one is, no canary. | Trigger a real engine exception with the canary in the input; assert the captured event dict, including frame locals, contains no canary. RETENTION-MAP: *"`before_send` hook strips frame locals for engine modules; no attachments; no request bodies"*. | Positive (inspect captured event) |

### 8.2 What the canary marker must be

A high-entropy ASCII token embedded **in the document's own text content**, so it can only appear
in an artifact if document content leaked. Two properties matter:

1. It must survive the whole pipeline as *text*, so the run index and any error message that
   interpolates decoded text would carry it. Build the fixture by writing a real PDF with the
   canary as a text run (`pikepdf` + a bundled Liberation face, or edit a corpus doc through
   `apply_recipe` — the engine is right there).
2. It must **also** appear in the filename, so PRIV-04's "no filenames in logs" clause is covered
   by the same grep. Two distinct markers (one for content, one for filename) is better: it tells
   you *which* rule broke.

Do **not** use the content hash as the canary. RETENTION-MAP explicitly permits hashes in logs
("one-way and do not reveal content"), and `app.py:172` already logs one.

### 8.3 Infrastructure this test constrains

The canary test is not just a test — it pins design decisions, which is why D-4.4 puts it first:

- **The error reporter must be injectable.** If Sentry (or whatever) is imported and initialized at
  module scope, the test cannot capture events. The plan needs a reporter interface with a test
  double from the start. This is the single most likely thing to be retrofitted badly.
- **Logging must be capturable at the point the worker runs.** If the worker is a subprocess, its
  stderr must be piped and inspected — `caplog` will not see it. This is a concrete argument for
  the subprocess protocol carrying structured log records back to the parent rather than writing
  to its own stderr.
- **The crash path needs a deliberate injection point.** A fault-injection hook (env var or a
  patched engine function that raises) is cleaner than trying to find a real input that crashes.
  It must be test-only and must not exist as a live code path.
- **The scratch root must be discoverable from the test.** Today it is a module global assigned in
  an ASGI startup event (`app.py:1096-1099`) and `NameError` otherwise (defect #7). This must be
  fixed before the canary test can be written at all.

### 8.4 Honest limitation

A canary test proves the canary did not leak on the paths it exercised. It does not prove no
document content leaks anywhere. It is a regression tripwire, not a proof — say so in the test's
docstring. This matches the project's existing discipline (`G2B-GATE-RESULTS.md`'s "What was NOT
tested" section) and is worth more than an overclaimed assertion.

---

## Section 9 — PRIV-06: CDN and CSP

### 9.1 Cloudflare — ROADMAP criterion 3 is correct, and here is the precise mechanism

Fetched from Cloudflare's own documentation this session.

**`.PDF` IS in the default cached file-extension list.** Verbatim:

> 7Z | CSV | GIF | MIDI | PNG | TIF | ZIP | AVI | DOC | GZ | MKV | PPT | TIFF | ZST | AVIF | DOCX |
> ICO | MP3 | PPTX | TTF | APK | DMG | ISO | MP4 | PS | WEBM | BIN | EJS | JAR | OGG | RAR | WEBP |
> BMP | EOT | JPG | OTF | SVG | WOFF | BZ2 | EPS | JPEG | **PDF** | SVGZ | WOFF2 | CLASS | EXE | JS |
> PICT | SWF | XLS | CSS | FLAC | MID | PLS | TAR | XLSX

*(An initial WebSearch result claimed the opposite — that PDF is not in the default list. The
official docs contradict it. Recorded here because it is exactly the aggregator-vs-primary-source
trap STATE.md warns about.)*

**BYPASS vs DYNAMIC, verbatim from the same source:**

- **BYPASS** — "Cloudflare considered the asset eligible for cache at request time — either because
  it matches the default cached file extensions, or because a Cache Rule enabled caching for it —
  but the origin response was ultimately not cacheable." Produced by `Cache-Control: no-store`,
  `Cache-Control: private`, or `Vary: *`.
- **DYNAMIC** — "Cloudflare determined at request time that the asset is not eligible for cache, so
  the request went to the origin web server without a cache lookup."

**Two consequences the plan must encode:**

1. **The expected value depends on the URL.** A document route ending in `.pdf` → **BYPASS**
   (eligible by extension, then rejected by `no-store`). A route with no cacheable extension →
   **DYNAMIC** (never eligible). Both satisfy the requirement. The verification must assert
   `cf-cache-status ∈ {BYPASS, DYNAMIC}` **and** never `HIT`/`MISS`/`EXPIRED`/`REVALIDATED`/`STALE`.
   Asserting one specific value will break the first time a route is renamed.
   RETENTION-MAP's CDN row already recommends the belt-and-braces measure: *"no `.pdf`/`.docx`
   extension in URL paths"* — which forces DYNAMIC and removes the dependency on the header alone.
   **Recommend doing both.**
2. **`no-cache` and `max-age=0` are traps.** Verbatim: they "do **not** produce BYPASS; they produce
   `MISS` initially, then `REVALIDATED` or `EXPIRED`." A developer "hardening" the header by
   switching to `no-cache` would silently start caching at the edge. Pin the exact header string in
   a test: `Cache-Control: no-store, private`.

**Testability, honestly stated.** The header assertion is a normal integration test over every
document-bearing route and belongs in CI. The `cf-cache-status` assertion **requires a live
deployment behind Cloudflare** and cannot run in CI before one exists. Options, in order:
(a) a post-deploy smoke check in the deploy workflow; (b) a manual verification recorded in a
results document, following the `PLAYA-DECISION.md` / `G2B-GATE-RESULTS.md` precedent that this
project already uses for un-CI-able checks. **(b) is the honest answer for Phase 4** given no
deployment target is selected — but the route-list-to-header test must be automated so the
manual check only ever has to confirm CDN configuration, not application behaviour.

### 9.2 `isEvalSupported` no longer exists — and pdf.js 6.2.108 uses no `eval` at all

Measured against the installed `client/node_modules/pdfjs-dist@6.2.108`:

| Check | Result |
|---|---|
| `grep -rl "isEvalSupported" .` across the whole package (incl. `types/`) | **zero files** |
| `new Function(` in `pdf.mjs` / `pdf.worker.mjs` / `pdf.sandbox.mjs` | **0 / 0 / 0** |
| `eval(` in the same three | **0 / 0 / 0** |
| Every `eval` substring found | identifiers only: `#evaluateVisibilityExpression`, `evaluatorOptions`, `"Trump Mediaeval"` |
| Every `Function(` substring found | `#sRGBTransferFunction(` only |
| `TextLayer` class | present (`pdf.mjs:14819`) |
| `convertToViewportPoint` / `convertToPdfPoint` | both present |
| `disableAutoFetch` / `disableStream` / `disableRange` / `rangeChunkSize` | all present in `types/src/display/api.d.ts` |

So:

- **Passing `isEvalSupported: false` to `getDocument` is a no-op** on the pinned version — an
  unknown option, silently ignored. A task that sets it and marks PRIV-06 satisfied would be
  ceremony. It is harmless to pass for forward/backward compatibility, but it must not be the
  evidence.
- **The real, now-achievable control is the CSP**, and it can be strict: no `'unsafe-eval'`
  required. The known remaining `eval("require")` in pdf.js is in the **Node.js** worker-loading
  path (mozilla/pdf.js#19688, closed as not planned) — absent from the browser bundles measured
  above, and Vite bundles the worker via the `?url` import the scaffold already uses
  (`App.jsx:6`).
- **The testable assertion is behavioural, not configurational:** serve the app with a CSP lacking
  `'unsafe-eval'` and assert a document renders and its text layer populates. That proves the
  property; asserting the header alone does not.
- CVE-2024-4367 (the `/FontMatrix` injection the `isEvalSupported` guidance came from) was fixed in
  pdf.js **4.2.67**; the pinned 6.2.108 is far past it. [VERIFIED: NVD]

A starting CSP for the document-serving origin (needs `worker-src blob:` because pdf.js instantiates
its worker from a blob URL, and `'unsafe-inline'` for styles because `TextLayer` sets inline
positioning styles — verify both against the built app rather than trusting this line):

```
default-src 'self'; script-src 'self'; worker-src 'self' blob:;
style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:;
connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'
```

---

## Section 10 — Viewer requirements

### 10.1 VIEW-01 — prefer client-side rendering

`App.jsx:56-66` already renders via pdf.js to a canvas and that path works. The **server** render
endpoints are the broken ones (§2.1 defect #2, §2.2 defect #11). Since the client holds the
authoritative bytes (Option C), a server render endpoint is a second copy of the document over the
wire for no benefit. **Recommend deleting `/jobs/{id}/page/{n}/png` and `/jpeg` rather than fixing
them.** Fixing costs the same as deleting and leaves a document route to harden, log, and cache-
control. (If a server render is later needed for thumbnails of very large documents, the correct
call is `page.render(scale=dpi/72).to_pil()` — verified working.)

### 10.2 VIEW-02 — measured, and the scaffold actively prevents it

Measured on `corpus/public/irs_1040_instructions.pdf` (126 pages):

```
open+hash:               21 ms
page(0):                 46 ms          → first page ready at 67 ms
pages 1..125:          96.4 s
whole-document total:  96.5 s
RATIO first-page-ready : whole-doc = 1 : 1441
```

*(Measured on a loaded machine with concurrent work; Phase 2 recorded 21.0s for `classify_document`
on this same document. The absolute number is therefore soft — the **ratio** is the finding, and it
holds under any load.)*

`RunIndex` is already lazy per-page with LRU eviction (`index.py:162-174`) — the engine half of
VIEW-02 is done. The scaffold breaks it: `job_status` loops `for p in range(page_count): idx.page(p)`
(`app.py:206-217`) before returning anything. On this document the user waits ~96s for the first
byte of UI.

**Mechanism:** per-page endpoints (`/pages/{n}/runs`), fetched on demand, page 1 first. On the pdf.js
side, `getDocument()` resolves after the xref and page tree are read; `getPage(1)` and render can
then proceed while later pages are still unfetched. `disableAutoFetch: true` + `disableStream: false`
with HTTP range requests is the standard progressive configuration — but note it only helps if the
bytes are fetched over HTTP, and here the client already has the full `ArrayBuffer` from the user's
file input, so **for the primary flow pdf.js needs no streaming configuration at all**. VIEW-02's
real bottleneck is the *server run index*, not the raster.

**Acceptance criterion recommendation:** assert that a request for page 0's runs on a 126-page
document returns in under a fixed budget (e.g. 1s), and that no request performs whole-document
indexing. The second half is the durable one — a test that patches `RunIndex._parse_page`
(explicitly designed as "its own patchable method", `index.py:139-143`) and asserts it was called
once, not 126 times.

### 10.3 VIEW-03 — `TextLayer`, not implemented today

The scaffold renders to canvas only (`App.jsx:56-66`, `:227-232`); `grep -i textlayer client/src/`
returns nothing. Selection, copy, and browser find are therefore all absent.

pdf.js 6.2.108 exports a `TextLayer` class (verified, `pdf.mjs:14819`). The standard pattern is a
`<div>` absolutely positioned over the canvas containing transparent positioned spans; browser find
and copy then work natively because the text is real DOM. Requires the pdf.js text-layer CSS
(transparent colour, `transform-origin`) or selection is visible and misaligned.

**Note the interaction with EDIT-01.** VIEW-03 puts pdf.js text items into the DOM, and D-4.2
forbids hit-testing against them. Both layers coexist: the text layer is for selection/find only;
the *edit* hit-test uses a separate overlay of server-issued boxes. The plan must state this
explicitly or an implementer will reasonably reuse the text layer for hit-testing and violate D-4.2
without noticing.

### 10.4 VIEW-04 / CLAS-06 — the data already exists

`RunIndex.page(n)` returns `PageIndex(bucket, runs, glyph_count)` (`index.py:87-96`) where `bucket`
is one of six `Literal` values (`classify_page.py:78-85`): `scan_no_text`, `ocr_scan`,
`vector_outlined`, `empty`, `editable`, `mixed_degraded`. Per-run verdicts are the CLAS-04
three-state `RunVerdict(state, reason)` (`classify_run.py:70-78`).

**Discretion resolved (recommendation): compute badges per page at index time, served by the same
`/pages/{n}/runs` endpoint that serves hit boxes.** Reasons: the badge and the run verdicts must
agree, and one response makes disagreement structurally impossible; it is lazy by construction,
which VIEW-02 needs; and it avoids a streaming/SSE mechanism, which would be new infrastructure for
no requirement. Thumbnails render progressively as their pages are fetched — a "not yet classified"
badge state is honest and cheap, and is better than blocking the rail on a whole-document pass.

Six buckets is more than a UI wants. Recommend a documented collapse to three visual states
(editable / partly-editable / not-editable) with the exact bucket and reason available on hover or
in the refusal screen — never lost, just not shouted.

### 10.5 CLAS-07 — the notify signal is a measurement, not a toggle

REQUIREMENTS.md OCR-03: *"Interest in OCR is measured from the v1 refusal screen's notify signal
before this is built."* That is the requirement's whole purpose — it gates whether v2 OCR is built
at all. The `.hermes` plan proposes "no backend call; local state toggle" (its Task 6 Step 2),
which produces **zero** measurement and silently defeats OCR-03.

The plan needs a real, minimal endpoint that records a count. Two constraints pull against each
other and both are real: PRIV-04 says no document content in logs; ACCT says no accounts and no
linkage. **A bare counter with no payload** — no email, no document reference, no IP retention —
satisfies both and still answers "how many people wanted this." If an email capture is wanted, that
is a product decision with a privacy-posture cost and should be surfaced as a discretion item, not
assumed.

The "specific external OCR route" must be a named tool the user can actually go use today. That is a
content decision, not a technical one; the plan should require the name to be pinned before the
refusal screen ships, not left as `TODO`.

---

## Section 11 — EDIT-05: an undo store that already admits a batch

The forward constraint from Phase 5: replace-all produces one batch that must undo in **one**
Ctrl+Z. Design for that now or retrofit later.

**The shape follows from the engine.** A recipe is already `tuple[RecipeOp, ...]` — a *list* of ops —
and `apply_recipe` is all-or-nothing over the whole list (D-11). So the natural undo unit is
**one recipe**, and a single-run edit is simply a recipe of length 1. Phase 5's replace-all is a
recipe of length N. **No special batching mechanism is needed** — the batch is the recipe, and
EDIT-05's "replace-all undoes as one step" falls out for free.

```
undo stack : list of recipes (each `tuple[RecipeOp, ...]`)
redo stack : same
current document state = original bytes + concat(undo stack)
```

**Where it lives: the browser.** The client is the system of record (Option C); a server-side undo
log is durable per-session state, which is exactly PRIV-02's prohibition. The client re-sends the
concatenated recipe on each commit and the server is stateless with respect to history.

**The cost, stated honestly:** undo = re-apply the whole prefix from the original bytes. For a
40-page replace-all this is one full `apply_recipe` run per undo, not an incremental patch. That is
acceptable — it is the only model consistent with D-10 (run IDs address the *original* bytes, and
`engine/run_id.py`'s own model is "(original bytes, recipe) → output, and the output is a throwaway
that is never the input to the next edit"). Any incremental undo would need to address the *output*
bytes, which D-10 forbids. **Do not let anyone optimize this into an incremental model** — it looks
like a performance win and it breaks the addressing invariant the whole project rests on.

**Two subtleties for the plan:**
1. `plan_recipe` refuses a recipe containing a duplicate `run_id` outright, with every op marked
   `"duplicate_run_id_in_recipe"` (`recipe.py:419-426`). Editing the same run twice is therefore
   **not** two stack entries that concatenate — the second edit must *replace* the first in the
   stack, not append. This will otherwise surface as a baffling whole-recipe refusal after two
   edits to one run.
2. FONT-07 style ops must be part of the same recipe entries, or undo will revert text and style
   independently.

---

## Package Legitimacy Audit

Every runtime package in this phase is **already installed and pinned** in one of the two checkouts;
nothing new is being introduced from a name suggested by a model. Registry verification was
performed against the installed distributions.

| Package | Registry | Pinned version | Source | Verification | Disposition |
|---|---|---|---|---|---|
| `fastapi` | PyPI | 0.141.1 | `main` `pyproject.toml` | installed, `importlib.metadata` | Approved |
| `uvicorn` | PyPI | 0.52.1 | `main` `pyproject.toml` | installed | Approved |
| `python-multipart` | PyPI | 0.0.32 | `main` `pyproject.toml` | installed | Approved |
| `pydantic` | PyPI | 2.13.4 | transitive of fastapi | installed | Approved |
| `starlette` | PyPI | 1.6.0 | transitive of fastapi | installed | Approved |
| `pikepdf` | PyPI | 10.11.0 | both `pyproject.toml` | installed, in use since Phase 1 | Approved |
| `playa-pdf` | PyPI | 1.1.0 | both | installed, Phase 1 decision recorded in `PLAYA-DECISION.md` | Approved |
| `pypdfium2` | PyPI | 5.12.1 | both | installed; API measured this session | Approved |
| `fonttools` | PyPI | 4.63.0 | both | installed | Approved |
| `uharfbuzz` | PyPI | 0.56.0 | both | installed | Approved |
| `pillow` | PyPI | 12.3.0 | both | installed | Approved |
| `pdfjs-dist` | npm | 6.2.108 | `client/package.json` | installed; contents grepped this session | Approved |
| `@cantoo/pdf-lib` | npm | 2.8.1 | `client/package.json` | installed; named in CLAUDE.md stack | Approved |
| `react` / `react-dom` | npm | 18.2.x | `client/package.json` | installed | Approved |
| `vite` / `@vitejs/plugin-react` | npm | 5.4.x / 4.2.x | `client/package.json` | installed | Approved |
| `python-docx` | PyPI | 1.2.0 | `main` `pyproject.toml` | installed | **REMOVE from Phase 4** — Phase 8 (EXPO-07) dependency, pulled in only by the out-of-scope DOCX endpoint |
| `httpx` | PyPI | — | **not installed on either branch** | required by `fastapi.testclient.TestClient` | **[ASSUMED]** — Wave 0 must add it as a dev dependency and verify the resolved version |

**slopcheck:** not run this session (no new package names were sourced from a model; every entry
above except `httpx` was read from a checked-in `pyproject.toml` / `package.json` and confirmed
installed). `httpx` is tagged `[ASSUMED]` per the provenance rule and should be added through the
normal `uv add` + `tools/license_gate.py` path rather than pinned from this document.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

**Licensing gate.** `tools/license_gate.py` scans the resolved installed closure for
`agpl`/`affero` in `License` or any `Classifier`. Adding the server dependencies to
`pyproject.toml` puts them under that gate automatically, provided the `license-gate.yml` workflow
runs `uv sync --locked` first (it does, `:19`). No AGPL was found in the current `main`
environment. The `.hermes`-era hazard PITFALLS names — `pdf2docx` pulling `PyMuPDF>=1.26.7` — is
**not** present: the scaffold's DOCX path uses `python-docx` + `playa` (`app.py:912-923`), not
`pdf2docx`.

---

## Runtime State Inventory

This is a greenfield-service phase, not a rename/refactor. The categories are answered anyway
because the branch merge moves real state.

| Category | Items Found | Action Required |
|---|---|---|
| Stored data | None — no database, no Redis, no object store exists in either checkout. `_jobs` is an in-process dict (`app.py:101`) that dies with the process. | None |
| Live service config | None — no deployment exists. Cloudflare/CDN config will be *created* by this phase, not migrated. Note it lives outside git and must be recorded (RETENTION-MAP's CDN row: *"periodic check of CDN cache-rule config against route list"*). | Record CDN rule config in-repo as documentation |
| OS-registered state | None — no systemd units, no launchd plists, no scheduled tasks. Verified: no `*.service`, no `*.plist` in either checkout. | None |
| Secrets / env vars | `PDF_TOOL_JOB_TTL` and `PDF_TOOL_MAX_UPLOAD` are read in `server/ephemeral.py:45,49` — **dead code**, so neither is live. `server/app.py` hardcodes both (`:50`, `:53`). No secret store, no `.env`, no SOPS. | Decide whether config is env-driven; do not resurrect the dead module's names by accident |
| Build artifacts | **`client/node_modules/` — 5,041 files committed to git**, including built Vite dep bundles (defect #5). `server/__pycache__/`, `engine/__pycache__/` present in both checkouts. Two separate `.venv/` directories. | `git rm -r --cached client/node_modules`, add to `.gitignore`, verify `client/package-lock.json` is retained. Reinstall after merge. |
| Branch divergence | Phase 3 branch is 45 commits ahead of `main`; `main` adds 4 dependencies and ~2,900 lines of scaffold. `uv.lock` will conflict. | Merge `main` → Phase 3 branch (§1.1), resolve `uv.lock` by re-running `uv lock` |

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| Applying a text edit | Anything in `server/` | `engine.recipe.apply_recipe` | D-4.3. `server/engine_replace.py` is the existing counter-example: it skips D-10, violates D-11, and crashes. |
| Computing the dry-run report | A server-side summary | Render `RecipeReport` fields directly | D-03 exists for this. `tools/pdftool.py:94-111` is the reference renderer. |
| Parsing the recipe wire format | A Pydantic model mirroring `RecipeOp` | `engine.recipe.parse_recipe(request_body_bytes)` | It is already the hardened untrusted-input boundary with both DoS ceilings. A parallel model drifts. |
| Refusal messages | Prose generated server- or client-side | The fixed reason vocabulary (§1.2), mapped to copy in one table | EDIT-04 forbids invented prose. |
| Text selection / find | A custom selection overlay | pdf.js `TextLayer` | Native browser find and copy only work on real DOM text. |
| PDF↔viewport coordinates | Manual matrix math | `PageViewport.convertToViewportPoint` / `convertToPdfPoint` | Verified present in 6.2.108; handles rotation and the y-flip. |
| Per-page lazy indexing | A new cache | `engine.index.RunIndex` | Already lazy + LRU + glyph-budgeted + capped (`MAX_DOCUMENT_GLYPHS`). |
| Batch undo | A batching layer over single edits | One recipe = one undo step (§11) | The engine's unit is already a list. |
| A job queue | ARQ/Redis "for the canary to inspect" | Nothing — assert its absence | CLAUDE.md:89 calls a queue an anti-feature for a no-retention product. |
| Page rasterization on the server | Fixing the broken render endpoints | pdf.js in the browser | The client already holds the bytes. |
| Extension-based upload validation | `filename.endswith(".pdf")` | `data[:5] == b"%PDF-"` | INGE-01, and 217/217 corpus files satisfy the strict form. |

**Key insight:** almost every "build" item in this phase already exists in `engine/` and is proven
by Gate G2b. The genuinely new code is the transport, the isolation boundary, the run-box
derivation, and the UI — and the transport is thin by design because the recipe *is* the wire
format.

---

## Common Pitfalls

### Pitfall 1: Treating the scaffold as a partial implementation
**What goes wrong:** Plans scope tasks as "fix X" when the honest scope is "write X". `server/app.py`
looks like 1,105 lines of working server; roughly 700 lines are out-of-scope exports, ~290 are
Phase-4-shaped, and the privacy module is dead code that crashes on import.
**How to avoid:** scope from §2's per-requirement table, not from file size. Delete before adding.
**Warning sign:** a task description containing "already partially present" (the `.hermes` plan's
Task 4 uses exactly that phrase about ephemerality, which is implemented nowhere).

### Pitfall 2: Under-scoping FONT-07
**What goes wrong:** FONT-07 reads as a toolbar. It is a recipe-schema change plus interactions with
D-01 (size invalidates the fit), D-05/D-13 (weight/style is a different bundled face and a different
subset), and D-09 (the wire format).
**How to avoid:** give it its own wave, or scope it explicitly and record the scoping.
**Warning sign:** FONT-07 appearing as one bullet inside a UI task — as it does in the `.hermes`
plan's Task 7, bundled with EDIT-01, EDIT-05 and all four VIEW requirements.

### Pitfall 3: Accepting `isEvalSupported: false` as PRIV-06 evidence
**What goes wrong:** the option does not exist in pdfjs-dist 6.2.108 (§9.2). Setting it passes an
ignored key and proves nothing.
**How to avoid:** the assertion is behavioural — render a document under a CSP with no
`'unsafe-eval'` and confirm the text layer populates.

### Pitfall 4: A canary test that only walks the success path
**What goes wrong:** the crash path is where retention actually happens — a `finally` that does not
run, a traceback carrying frame locals, a dead-letter record. ROADMAP criterion 1 names both paths
explicitly.
**How to avoid:** a deliberate fault-injection hook, and an error reporter that is injectable from
the first commit rather than initialized at module scope (§8.3).

### Pitfall 5: Building infrastructure so the canary has something to inspect
**What goes wrong:** "the canary covers queue and object store" reads as "there must be a queue and
an object store." Adding either introduces the durable state the requirement forbids.
**How to avoid:** two of the five surfaces are proved by absence (§7.3, §8.1).

### Pitfall 6: Hit-testing against the pdf.js text layer
**What goes wrong:** VIEW-03 puts pdf.js text items in the DOM, and they are right there and
convenient. Using them violates D-4.2 and EDIT-01's explicit wording, and the run boundaries will
not match the clusterer's (`engine/clusterer.py` breaks runs on gap, font, size, colour, visibility
and per-glyph verdict — `rewrite.py:624`).
**How to avoid:** two overlays. Text layer for selection/find; a separate box overlay for editing.
Say so in the plan.

### Pitfall 7: Assuming `RLIMIT_AS` works on the dev machine
**What goes wrong:** measured — it cannot be set at all on macOS 15.7.7 arm64 (§6.1). A test written
without a skip guard fails locally and gets deleted or weakened.
**How to avoid:** `skipif(sys.platform == "darwin")` with a reason string, and a CI job that
actually runs the Linux path so the skip is not silent everywhere.

### Pitfall 8: A signature detector that fires on signature *fields*
**What goes wrong:** five IRS corpus forms carry `/AcroForm /SigFlags 2` with no signature (§5.3).
`"/SigFlags" in acroform` reports five false positives, and INGE-03's warning becomes noise users
learn to dismiss.
**How to avoid:** check `SigFlags & 1` or a `/FT /Sig` field with a `/V`. Use the five IRS forms as
the negative-case fixtures.

### Pitfall 9: Splitting the content hash from `source_hash`
**What goes wrong:** the server invents a cache key while `run_id` embeds
`sha256(original_bytes)` (D-10). Two identities for one document produce a `409` that a re-upload
cannot satisfy, or a `source_hash_mismatch` on a document the cache believes it has.
**How to avoid:** one value. `_content_address` (`app.py:79`) and `RunIndex._source_hash`
(`index.py:118`) already compute the same digest — keep them unified.

### Pitfall 10: Editing the same run twice and getting a whole-recipe refusal
**What goes wrong:** `plan_recipe` refuses any recipe with a duplicate `run_id`, marking *every* op
`"duplicate_run_id_in_recipe"` (`recipe.py:419-426`). A naive append-only undo stack produces this
after the second edit to one run.
**How to avoid:** the undo stack replaces, not appends, for a repeated `run_id` (§11).

### Pitfall 11: The password becoming document content in a traceback
**What goes wrong:** INGE-02 threads a password through five call sites; any `repr()`, log line, or
error-reporter frame local carrying it violates PRIV-04 and the canary will not catch it unless the
canary includes a password marker.
**How to avoid:** a redacting wrapper type, and a canary marker in the password field specifically.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| `getDocument({ isEvalSupported: false })` as the pdf.js hardening control | The option is gone; the browser bundles contain no `eval`/`Function` at all | Between the research pass and pdfjs-dist 6.2.108 (option absent; CVE-2024-4367 fixed in 4.2.67) | ROADMAP criterion 3's first clause is obsolete for the pinned version; the CSP clause is now genuinely achievable |
| `page.render(dpi=N)` (pypdfium2 ≤4.x) | `page.render(scale=dpi/72).to_pil()` | pypdfium2 5.x | Two live HTTP 500s in the scaffold |
| `@app.on_event("startup")` | `lifespan=` context manager | FastAPI ≥0.93 (deprecated since) | `app.py:1096`, `:1102` use the deprecated form; will warn on 0.141.1 |
| `fp` fingerprint per override + `409 STALE_RUN` (ARCHITECTURE.md:199) | `source_hash` embedded in the `run_id`, hard refusal, no override (D-10) | Phase 3 | Do not build both (§7.2) |

**Deprecated/outdated in the scaffold:**
- `server/engine_replace.py` — a pre-G2b fork of the rewrite logic. Delete (D-4.1).
- `server/ephemeral.py` — dead, crashes on import. Delete; re-derive from RETENTION-MAP.
- `server/diag.py`, `diag2.py`, `diag3.py` (95 lines) — ad-hoc debugging scripts, committed.
- `server/font_subsetter.py` — superseded by `engine/fonts.py` (D-13 union subsetting).
- `@app.on_event` — deprecated FastAPI API.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (already configured, both branches) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths=["tests"]`, `pythonpath=["."]`, `corpus` marker |
| Quick run command | `uv run --frozen pytest -q -m "not corpus"` |
| Full suite command | `uv run --frozen pytest -q` |
| Type check | `uv run --frozen mypy engine/` (strict, `files = ["engine"]`) — **note: `server/` is not currently under mypy; Phase 4 should extend `files` to `["engine", "server"]`** |

**New markers needed (Wave 0):** `linux_only` (rlimit tests, §6.1), `cdn` (live-deployment checks
that cannot run in CI, §9.1).
**New dev dependency needed (Wave 0):** `httpx` (required by `fastapi.testclient.TestClient`;
**not installed on either branch** — verified).

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| INGE-01 | Valid PDF bytes with a lying extension (`w9.pdf.exe`) are accepted | integration | `uv run --frozen pytest tests/test_ingest.py::test_accepts_pdf_bytes_regardless_of_extension -x` | ❌ Wave 0 |
| INGE-01 | Non-PDF bytes named `.pdf` are refused by magic-byte sniff | integration, negative | `uv run --frozen pytest tests/test_ingest.py::test_rejects_non_pdf_bytes_named_pdf -x` | ❌ Wave 0 |
| INGE-01 | Upload above the size cap is refused before the parser sees it | integration, negative | `uv run --frozen pytest tests/test_ingest.py::test_oversize_upload_refused_before_parse -x` | ❌ Wave 0 |
| INGE-01 | Every corpus file passes the strict `%PDF-` sniff (the measurement, pinned) | corpus | `uv run --frozen pytest -m corpus tests/test_ingest.py::test_corpus_all_files_have_pdf_magic_at_offset_zero -x` | ❌ Wave 0 |
| INGE-02 | A user-password PDF opens when the password is supplied | integration | `uv run --frozen pytest tests/test_ingest.py::test_user_password_pdf_opens_with_password -x` | ❌ Wave 0 (fixture must be built — §5.2) |
| INGE-02 | Wrong/absent password returns a named refusal, not a crash | integration, negative | `uv run --frozen pytest tests/test_ingest.py::test_wrong_password_named_refusal -x` | ❌ Wave 0 |
| INGE-02 | The password never appears in logs, error events, or the job record | unit | `uv run --frozen pytest tests/test_privacy_canary.py::test_password_never_leaves_the_worker -x` | ❌ Wave 0 |
| INGE-03 | A genuinely signed document is detected | unit | `uv run --frozen pytest tests/test_ingest.py::test_signed_document_detected -x` | ❌ Wave 0 (fixture must be built — §5.3) |
| INGE-03 | The five IRS forms with `/SigFlags 2` and no signature are **not** flagged | unit, negative | `uv run --frozen pytest tests/test_ingest.py::test_sigflags_appendonly_without_signature_is_not_signed -x` | ❌ Wave 0 |
| INGE-03 | Saving a signed document warns before writing | integration | `uv run --frozen pytest tests/test_ingest.py::test_signed_document_warns_before_save -x` | ❌ Wave 0 |
| INGE-04 | Decompression bomb: worker dies, host survives, named error returned | integration, `linux_only` | `uv run --frozen pytest -m linux_only tests/test_hostile_input.py::test_decompression_bomb_dies_in_worker -x` | ❌ Wave 0 |
| INGE-04 | Cyclic page tree: worker dies or engine refuses by name; host survives | integration | `uv run --frozen pytest tests/test_hostile_input.py::test_cyclic_page_tree_fails_on_own_limits -x` | ❌ Wave 0 |
| INGE-04 | Self-referencing Form XObject: same | integration | `uv run --frozen pytest tests/test_hostile_input.py::test_self_referencing_form_xobject_fails_on_own_limits -x` | ❌ Wave 0 |
| INGE-04 | `RLIMIT_AS` is actually in force in the worker child | unit, `linux_only` | `uv run --frozen pytest -m linux_only tests/test_hostile_input.py::test_worker_child_has_rlimit_as_set -x` | ❌ Wave 0 |
| INGE-04 | Wall-clock timeout kills a worker that hangs (portable — the non-skippable control) | unit | `uv run --frozen pytest tests/test_hostile_input.py::test_wall_clock_timeout_kills_hung_worker -x` | ❌ Wave 0 |
| PRIV-01 | The local/server predicate returns `"local"` for an empty override set and `"server"` otherwise | unit | `uv run --frozen pytest tests/test_disclosure.py::test_empty_override_set_routes_local -x` | ❌ Wave 0 |
| PRIV-01 | The badge and the dispatch decision come from the same function (no second predicate) | unit | `uv run --frozen pytest tests/test_disclosure.py::test_badge_and_dispatch_share_one_predicate -x` | ❌ Wave 0 |
| PRIV-02 | Killing the cache mid-session returns `409` with `{"missing": [...]}` | integration | `uv run --frozen pytest tests/test_ephemerality.py::test_cache_kill_midsession_returns_409_source_missing -x` | ❌ Wave 0 |
| PRIV-02 | Re-uploading the same bytes after a `409` restores the session | integration | `uv run --frozen pytest tests/test_ephemerality.py::test_reupload_after_409_restores_session -x` | ❌ Wave 0 |
| PRIV-02 | **Every** document-touching route has the `409` branch, not just status | integration | `uv run --frozen pytest tests/test_ephemerality.py::test_all_document_routes_409_on_missing_source -x` | ❌ Wave 0 |
| PRIV-03 | Scratch path is tmpfs (Linux/CI); skipped with a reason on macOS | integration, `linux_only` | `uv run --frozen pytest -m linux_only tests/test_ephemerality.py::test_scratch_is_tmpfs -x` | ❌ Wave 0 |
| PRIV-03 | Per-job scratch dir does not exist after the job returns (success **and** exception) | unit | `uv run --frozen pytest tests/test_ephemerality.py::test_per_job_scratch_removed_on_both_paths -x` | ❌ Wave 0 |
| PRIV-03 | **No queue exists** — no ARQ/Redis client is importable or configured | unit, proof-by-absence | `uv run --frozen pytest tests/test_ephemerality.py::test_no_job_queue_exists -x` | ❌ Wave 0 |
| PRIV-04 | No document content, filename, or decoded text in any log record on the success path | integration | `uv run --frozen pytest tests/test_privacy_canary.py::test_no_canary_in_logs_success_path -x` | ❌ Wave 0 |
| PRIV-04 | Static check: no `logger.*` call in `server/` or `engine/` interpolates a variable holding text/bytes | unit (AST scan) | `uv run --frozen pytest tests/test_privacy_canary.py::test_no_log_call_interpolates_document_content -x` | ❌ Wave 0 |
| PRIV-05 | Canary absent from **scratch** — success path | integration | `uv run --frozen pytest tests/test_privacy_canary.py::test_canary_absent_from_scratch_success -x` | ❌ Wave 0 |
| PRIV-05 | Canary absent from **scratch** — crash path | integration | `uv run --frozen pytest tests/test_privacy_canary.py::test_canary_absent_from_scratch_crash -x` | ❌ Wave 0 |
| PRIV-05 | **Queue** surface — proof by absence, asserted on both paths | unit | `uv run --frozen pytest tests/test_privacy_canary.py::test_no_queue_surface_exists -x` | ❌ Wave 0 |
| PRIV-05 | Canary absent from **logs** — success path | integration | `uv run --frozen pytest tests/test_privacy_canary.py::test_canary_absent_from_logs_success -x` | ❌ Wave 0 |
| PRIV-05 | Canary absent from **logs** — crash path (traceback included) | integration | `uv run --frozen pytest tests/test_privacy_canary.py::test_canary_absent_from_logs_crash -x` | ❌ Wave 0 |
| PRIV-05 | **Object store** surface — no S3/R2/GCS client in the closure or ever constructed | unit | `uv run --frozen pytest tests/test_privacy_canary.py::test_no_object_store_client_exists -x` | ❌ Wave 0 |
| PRIV-05 | Canary absent from **error reporter** event — success path | integration | `uv run --frozen pytest tests/test_privacy_canary.py::test_canary_absent_from_error_events_success -x` | ❌ Wave 0 |
| PRIV-05 | Canary absent from **error reporter** event **including frame locals** — crash path | integration | `uv run --frozen pytest tests/test_privacy_canary.py::test_canary_absent_from_error_events_crash -x` | ❌ Wave 0 |
| PRIV-05 | The whole canary suite runs in CI (not merely present in the repo) | CI config | `grep -q "test_privacy_canary" .github/workflows/tests.yml` | ❌ Wave 0 |
| PRIV-06 | Every document-bearing route sends exactly `Cache-Control: no-store, private` | integration | `uv run --frozen pytest tests/test_headers.py::test_document_routes_send_no_store -x` | ❌ Wave 0 |
| PRIV-06 | Route inventory is complete — no document route escapes the header check | integration | `uv run --frozen pytest tests/test_headers.py::test_every_document_route_is_covered_by_header_test -x` | ❌ Wave 0 |
| PRIV-06 | CSP header present and contains no `'unsafe-eval'` | integration | `uv run --frozen pytest tests/test_headers.py::test_csp_forbids_eval -x` | ❌ Wave 0 |
| PRIV-06 | pdf.js renders and its text layer populates **under** that CSP (the behavioural proof) | e2e (browser) | `uv run --frozen pytest -m e2e tests/test_viewer_e2e.py::test_renders_and_selects_text_under_strict_csp -x` | ❌ Wave 0 |
| PRIV-06 | pinned pdfjs-dist contains no `eval(` / `new Function(` (regression tripwire on upgrade) | unit | `uv run --frozen pytest tests/test_headers.py::test_pinned_pdfjs_contains_no_dynamic_eval -x` | ❌ Wave 0 |
| PRIV-06 | CDN reports `BYPASS` or `DYNAMIC`, never `HIT`/`MISS`/`EXPIRED`/`REVALIDATED`/`STALE` | manual, `cdn` marker — recorded in a results doc (§9.1) | `uv run --frozen pytest -m cdn tests/test_cdn.py::test_cf_cache_status_bypass_or_dynamic --deployment-url=$URL` | ❌ Wave 0 (requires a deployment) |
| PRIV-07 | `server.app` imports no `engine.*` module (structural proof) | unit | `uv run --frozen pytest tests/test_isolation.py::test_request_process_never_imports_engine -x` | ❌ Wave 0 |
| PRIV-07 | A real parse happens in a different pid from the request process | integration | `uv run --frozen pytest tests/test_isolation.py::test_parse_runs_in_separate_process -x` | ❌ Wave 0 |
| VIEW-01 | A corpus document uploads and returns page count + page 0 runs without error | integration | `uv run --frozen pytest tests/test_viewer_api.py::test_open_document_returns_page_zero_runs -x` | ❌ Wave 0 |
| VIEW-01 | Client renders page 1 of a real corpus document to canvas | e2e (browser) | `uv run --frozen pytest -m e2e tests/test_viewer_e2e.py::test_renders_page_one -x` | ❌ Wave 0 |
| VIEW-02 | Page 0's runs return without whole-document indexing (`_parse_page` called once, not N times) | unit | `uv run --frozen pytest tests/test_viewer_api.py::test_page_request_does_not_index_whole_document -x` | ❌ Wave 0 |
| VIEW-02 | First-page-ready under budget on the 126-page fixture (measured 67ms vs 96.5s whole-doc) | corpus, perf | `uv run --frozen pytest -m corpus tests/test_viewer_api.py::test_first_page_ready_under_budget -x` | ❌ Wave 0 |
| VIEW-03 | Text layer produces selectable DOM text matching the run index for a known page | e2e (browser) | `uv run --frozen pytest -m e2e tests/test_viewer_e2e.py::test_text_layer_is_selectable -x` | ❌ Wave 0 |
| VIEW-04 | Thumbnail rail lists every page with its bucket badge | e2e (browser) | `uv run --frozen pytest -m e2e tests/test_viewer_e2e.py::test_thumbnail_rail_shows_all_pages_with_badges -x` | ❌ Wave 0 |
| CLAS-06 | Per-page endpoint returns the `bucket` alongside the runs (one response, cannot disagree) | integration | `uv run --frozen pytest tests/test_viewer_api.py::test_page_response_carries_bucket_and_runs_together -x` | ❌ Wave 0 |
| CLAS-06 | All six `Bucket` literals map to a defined badge state (no unhandled bucket) | unit | `uv run --frozen pytest tests/test_viewer_api.py::test_every_bucket_literal_has_a_badge -x` | ❌ Wave 0 |
| CLAS-07 | An uneditable page's refusal names its reason from `RunVerdict.reason` / `Bucket`, never generic prose | integration | `uv run --frozen pytest tests/test_viewer_api.py::test_refusal_names_engine_reason_verbatim -x` | ❌ Wave 0 |
| CLAS-07 | The refusal screen names a specific external OCR route (non-empty, pinned string) | e2e (browser) | `uv run --frozen pytest -m e2e tests/test_viewer_e2e.py::test_refusal_screen_names_external_ocr_route -x` | ❌ Wave 0 |
| CLAS-07 | The notify signal records a count server-side (OCR-03's measurement), carrying no document data | integration | `uv run --frozen pytest tests/test_viewer_api.py::test_ocr_notify_records_count_without_payload -x` | ❌ Wave 0 |
| EDIT-01 | `/pages/{n}/runs` returns a box per run in PDF user space with non-zero width **and height** | integration | `uv run --frozen pytest tests/test_boxes.py::test_run_box_has_nonzero_width_and_height -x` | ❌ Wave 0 |
| EDIT-01 | Boxes for adjacent lines do not overlap (the property that makes hit-testing unambiguous) | corpus | `uv run --frozen pytest -m corpus tests/test_boxes.py::test_adjacent_line_boxes_do_not_overlap -x` | ❌ Wave 0 |
| EDIT-01 | A run_id echoed from the client resolves to the same run the box came from | integration | `uv run --frozen pytest tests/test_boxes.py::test_echoed_run_id_resolves_to_issued_box -x` | ❌ Wave 0 |
| EDIT-01 | Client never constructs a run_id — static check that no client source builds one | unit (source scan) | `uv run --frozen pytest tests/test_boxes.py::test_client_never_constructs_a_run_id -x` | ❌ Wave 0 |
| EDIT-01 | End-to-end: select a run in the browser, replace it, download, text changed | e2e (browser) | `uv run --frozen pytest -m e2e tests/test_edit_e2e.py::test_single_run_edit_round_trip -x` | ❌ Wave 0 |
| EDIT-05 | Ctrl+Z reverts a single-run edit | e2e (browser) | `uv run --frozen pytest -m e2e tests/test_edit_e2e.py::test_ctrl_z_reverts_single_edit -x` | ❌ Wave 0 |
| EDIT-05 | The undo unit is a whole recipe — a length-N recipe undoes in one step (Phase 5's forward constraint) | unit | `uv run --frozen pytest tests/test_undo.py::test_recipe_of_n_ops_undoes_as_one_step -x` | ❌ Wave 0 |
| EDIT-05 | Editing the same run twice replaces the stack entry rather than appending (no duplicate-run_id refusal) | unit | `uv run --frozen pytest tests/test_undo.py::test_second_edit_of_same_run_replaces_stack_entry -x` | ❌ Wave 0 |
| EDIT-05 | No undo state is stored server-side | unit | `uv run --frozen pytest tests/test_undo.py::test_no_server_side_undo_state -x` | ❌ Wave 0 |
| FONT-07 | Recipe schema accepts an optional style object; old two-key recipes still parse | unit | `uv run --frozen pytest tests/test_recipe.py::test_optional_style_key_is_backward_compatible -x` | ❌ Wave 0 (extends existing file) |
| FONT-07 | Weight/style routes to the correct bundled variant via D-05/D-13 | unit | `uv run --frozen pytest tests/test_fonts.py::test_style_change_routes_to_bundled_variant -x` | ❌ Wave 0 (extends existing file) |
| FONT-07 | A size change re-runs the fit ladder and refuses by name when it will not fit | unit, negative | `uv run --frozen pytest tests/test_fit.py::test_size_change_refits_or_refuses_by_name -x` | ❌ Wave 0 (extends existing file) |
| FONT-07 | Colour change emits a colour operator and does not disturb following text (D-04 guard holds) | unit | `uv run --frozen pytest tests/test_rewrite.py::test_colour_change_preserves_following_text_matrix -x` | ❌ Wave 0 (extends existing file) |
| **G3-1** | Gate criterion 1 — the full canary suite green on both paths, plus the exercised `409` path | phase gate | `uv run --frozen pytest tests/test_privacy_canary.py tests/test_ephemerality.py -q` | ❌ Wave 0 |
| **G3-2** | Gate criterion 2 — all three hostile inputs, parse out-of-process, magic-byte ingest | phase gate | `uv run --frozen pytest tests/test_hostile_input.py tests/test_isolation.py tests/test_ingest.py -q` | ❌ Wave 0 |
| **G3-3** | Gate criterion 3 — headers, CSP-behavioural render, no content in logs (CDN clause recorded manually) | phase gate | `uv run --frozen pytest tests/test_headers.py -q && uv run --frozen pytest -m e2e tests/test_viewer_e2e.py::test_renders_and_selects_text_under_strict_csp -q` | ❌ Wave 0 |
| **G3-4** | Gate criterion 4 — open (incl. password + signed), faithful render, page 1 first, select/copy/find, badges + refusal + OCR route | phase gate | `uv run --frozen pytest tests/test_ingest.py tests/test_viewer_api.py -q && uv run --frozen pytest -m e2e tests/test_viewer_e2e.py -q` | ❌ Wave 0 |
| **G3-5** | Gate criterion 5 — select, replace, restyle, per-op local/server disclosure, one Ctrl+Z | phase gate | `uv run --frozen pytest tests/test_boxes.py tests/test_undo.py tests/test_disclosure.py -q && uv run --frozen pytest -m e2e tests/test_edit_e2e.py -q` | ❌ Wave 0 |
| **G3-diff** | The Phase 4 edit path produces the same confined diff Phase 3 proved (no regression through the transport) | phase gate, corpus + pixel-diff | `uv run --frozen pytest -m corpus tests/test_gate_g2b.py::test_g2b_full_pipeline -x` | ✅ exists (Phase 3, worktree) |
| **G3-cve** | CVE re-verification recorded (STATE.md blocker) | doc artifact | `test -f .planning/phases/04-web-tier-walking-skeleton-hardening/CVE-VERIFICATION.md` | ❌ Wave 0 (§12 is the content) |

### Sampling Rate

- **Per task commit:** `uv run --frozen pytest -q -m "not corpus and not e2e and not cdn"` — the fast
  unit + integration set, hand-picked fixtures. Adding `server/` to mypy's `files` makes
  `uv run --frozen mypy engine/ server/` a per-commit check too.
- **Per wave merge:** `uv run --frozen pytest -q -m "not cdn"` (includes `corpus`, `linux_only` where
  the platform allows, and `e2e`) + `uv run --frozen mypy engine/ server/` +
  `uv run --frozen python tools/license_gate.py`.
- **Phase gate:** full suite green in **CI** (Linux — the `linux_only` rlimit clauses only actually
  execute there, §6.1), plus the three manually-recorded items that have no CI surface: the CDN
  `cf-cache-status` check (§9.1), the CVE re-verification document (§12), and a browser-based
  confirmation of the G3-4/G3-5 user journeys — following the `PLAYA-DECISION.md` /
  `G2B-GATE-RESULTS.md` precedent this project already uses.

### Wave 0 Gaps

- [ ] Merge `main` into the Phase 3 branch; resolve `uv.lock`; drop `python-docx` (§1.1)
- [ ] `git rm -r --cached client/node_modules` + `.gitignore` (5,041 files)
- [ ] Delete `server/engine_replace.py`, `server/ephemeral.py`, `server/diag{,2,3}.py`,
      `server/font_subsetter.py`, and every out-of-scope export endpoint (~700 lines of `app.py`)
- [ ] Add `httpx` as a dev dependency (`TestClient` requires it; not installed on either branch)
- [ ] Add pytest markers `linux_only`, `e2e`, `cdn` to `pyproject.toml`
- [ ] Extend mypy `files` to `["engine", "server"]`
- [ ] Choose and add an e2e browser harness (none exists; `@playwright/test` or `pytest-playwright`)
      — **or** explicitly convert every `e2e` row above to a recorded manual check
- [ ] `engine/boxes.py` — the run-bbox derivation (§3.1); no such module exists
- [ ] Password threading through `RunIndex` / `classify_document` / `plan_recipe` / `apply_recipe` (§3.2)
- [ ] Recipe schema extension for FONT-07 (§3.3)
- [ ] Fixtures: user-password PDF, genuinely-signed PDF, decompression bomb generator,
      cyclic page tree, self-referencing Form XObject, canary-marker PDF (§5)
- [ ] `tests/test_ingest.py`, `test_hostile_input.py`, `test_isolation.py`, `test_ephemerality.py`,
      `test_privacy_canary.py`, `test_headers.py`, `test_disclosure.py`, `test_boxes.py`,
      `test_undo.py`, `test_viewer_api.py` — all new
- [ ] `tests/conftest.py` additions: a `TestClient` fixture, a scratch-root fixture that works
      **without** the ASGI startup event (defect #7), an injectable error-reporter double,
      a fault-injection hook for the crash path
- [ ] An injectable error-reporter interface **before** any reporter is initialized at module scope (§8.3)
- [ ] `.github/workflows/tests.yml` — add the canary and hostile-input suites explicitly

---

## Section 12 — CVE re-verification against NVD

STATE.md line 82 records this as a blocker: *"CVE specifics in the research are partly
aggregator-sourced — re-verify against NVD when implementing Phase 4 hardening."* Done this
session, via the NVD REST API (`services.nvd.nist.gov/rest/json/cves/2.0?cveId=…`).

| CVE | PITFALLS.md claim | NVD verdict | Status |
|---|---|---|---|
| **CVE-2024-4367** | pdf.js `/FontMatrix` string injection → JS execution; fixed 4.2.67 | *"A type check was missing when handling fonts in PDF.js, which would allow arbitrary JavaScript execution in the PDF.js context."* CVSS 8.8 HIGH. References include the pdf.js v4.2.67 release. | ✅ **HOLDS** |
| **CVE-2026-3308** | MuPDF ≤1.27.0 `pdf_load_image_imp` integer overflow → heap OOB write | *"An integer overflow vulnerability in 'pdf-image.c' in Artifex's MuPDF version 1.27.0 … within the 'pdf_load_image_imp' function. This allows a heap out-of-bounds write…"* CVSS 7.8 HIGH, CWE-190, versions 0–1.27.0. | ✅ **HOLDS** (exact function name confirmed) |
| **CVE-2026-27628** | "Cyclic xref `/Prev` → infinite loop" (pypdf) | *"Prior to 6.7.2, an attacker who uses this vulnerability can craft a PDF which leads to an infinite loop."* CVSS 7.5 HIGH. **NVD does not mention `/Prev` or xref.** | ⚠️ **PARTIALLY VERIFIED** — the CVE and the infinite-loop class are real; the specific `/Prev` mechanism is **not corroborated by NVD**. The pypdf advisory list does contain *"Possible long runtimes for repeated malformed cross-reference entries"* (GHSA-55h5-xmcq-c37v), which is the closest match. Treat the mechanism as plausible, not established. |
| **CVE-2026-59935** | Unterminated inline image, ASCII85/ASCIIHex → CPU exhaustion; fixed 6.14.2 | *"…a page content stream containing a not terminated inline image that uses the ASCII85 or ASCIIHex filters, causing an infinite loop during parsing… fixed in version 6.14.2."* CVSS 7.5 HIGH. | ✅ **HOLDS** — filters and fix version both exact |
| **CVE-2026-59936** | (Paired with 59935 in PITFALLS, "fixed 6.14.2") | *"…a not terminated inline image, causing an infinite loop during inline image end marker detection… fixed in version 6.14.1."* CVSS 7.5 HIGH. | ⚠️ **MINOR CORRECTION** — fixed in **6.14.1**, not 6.14.2. PITFALLS gives one fix version for both. |
| **CVE-2026-41312** | "Predictor parameter bomb — FlateDecode PNG predictor, absurd `/Columns`/`/Colors`" | *"…versions prior to 6.10.2 can craft a PDF which leads to the RAM being exhausted."* CVSS 6.5 MEDIUM. **NVD does not mention predictors, `/Columns`, or `/Colors`.** | ⚠️ **PARTIALLY VERIFIED** — CVE and RAM-exhaustion class real; the predictor mechanism is **not corroborated**. |
| **CVE-2026-48155** | "Self-referencing Form XObject — `Do` recursion with no visited set" | *"An attacker who uses this vulnerability can craft a PDF which leads to large memory usage. This requires extracting text in layout mode with large character offsets."* Prior to 6.12.0, CVSS 5.5 MEDIUM. | ❌ **WRONG** — this CVE is about **layout-mode text extraction with large character offsets**, not Form XObject recursion. The attribution is incorrect. |
| **CVE-2026-54530** | "Text-extraction loop — layout-mode extraction loops with no exit" | *"Prior to 6.13.0 … can craft a PDF which leads to an infinite loop. This requires extracting the text in layout mode."* CVSS 6.9/5.5 MEDIUM. | ✅ **HOLDS** |
| **CVE-2023-36464** | "Lexer loop — comment not followed by a character" | *"An attacker may craft a PDF which leads to an infinite loop if `__parse_content_stream` is executed."* pypdf < 3.9.0, PyPDF2 ≥ 2.2.0. CVSS 5.5 MEDIUM. **NVD does not mention comments.** | ⚠️ **PARTIALLY VERIFIED** — CVE real, mechanism under-specified by NVD (the GitHub advisory carries the comment detail). |
| Ghostscript: CVE-2024-46952, -46956, CVE-2025-59798 | Buffer overflow / OOB → ACE | **Not re-verified this session.** Ghostscript is excluded from the runtime entirely (AGPL, CLAUDE.md), so these are not in Phase 4's threat surface. | ⏭️ **NOT VERIFIED — out of scope** |

**The one that matters for INGE-04.** PITFALLS.md cites CVE-2026-48155 as the self-referencing Form
XObject case, and that is wrong. Searching pypdf's advisory list, the genuine match is
**GHSA-763m-79hh-57f2** — *"Possible long runtimes/large memory usage when extracting XForm
objects"*, affecting `< 6.16.1`, CWE-834 (Excessive Iteration), described as occurring *"when
extracting the text of a page with lots of XForm objects, where some of them might be re-used."*
It has **no assigned CVE**.

So the *mechanism* INGE-04 names is real and recently patched in a comparable library — but under a
GHSA, not the CVE PITFALLS cites, and the advisory describes **re-use** rather than
**self-reference**. Both shapes need a visited set, so the mitigation is unchanged. The plan should
correct the PITFALLS attribution rather than propagate it.

**Net:** 6 of 9 in-scope claims hold as written; 1 is wrong (48155); 1 has a minor version error
(59936); 3 have mechanisms NVD does not corroborate (27628, 41312, 2023-36464). **Every CVE ID
cited exists** — none was hallucinated. The corrections should be written into a
`CVE-VERIFICATION.md` results document (following `PLAYA-DECISION.md` precedent) and STATE.md's
blocker line updated to cite it.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---|---|---|
| Python | everything | ✓ | 3.13 (`.python-version`) | — |
| `uv` | dependency management | ✓ | in use | — |
| pytest | all tests | ✓ | 9.1.1 | — |
| mypy | type gate | ✓ | 2.3.0 | — |
| fastapi / uvicorn / starlette / pydantic | web tier | ✓ (on `main` only) | 0.141.1 / 0.52.1 / 1.6.0 / 2.13.4 | — |
| `pypdfium2` | rendering | ✓ | 5.12.1 (API measured) | — |
| `pdfjs-dist` | viewer | ✓ | 6.2.108 (contents measured) | — |
| `@cantoo/pdf-lib` | PRIV-01 local materialization | ✓ | 2.8.1 | — |
| `httpx` | `fastapi.testclient.TestClient` | ✗ | — | none — **must be added** |
| Browser e2e harness | every `e2e` row above | ✗ | — | convert those rows to recorded manual checks |
| Docker | per-job container, `Dockerfile.ci` | ✗ **locally**, ✓ in CI (`harness.yml:16`) | — | subprocess+rlimits locally; container in CI |
| `RLIMIT_AS` | INGE-04 memory cap | ✗ **macOS** (measured `ValueError`), ✓ Linux CI | — | `RLIMIT_CPU` + wall-clock timeout (both portable) |
| `qpdf` / `ots-sanitize` / `pdftoppm` / `mutool` / `pdfcpu` | Phase 3 harness reuse for G3-diff | via `Dockerfile.ci` (all pinned) | see Dockerfile | — |
| Live CDN deployment | PRIV-06 `cf-cache-status` verification | ✗ | — | manual post-deploy check recorded in a results doc |
| Error reporter (Sentry or equivalent) | PRIV-05 error-reporter surface | ✗ not chosen | — | a test double satisfies the canary; the real one is a deployment concern |

**Missing dependencies with no fallback:**
- `httpx` — blocks every integration test. One-line fix, but it is a hard blocker for Wave 0.

**Missing dependencies with fallback:**
- Docker locally → subprocess + rlimits for dev, container for CI (§6.2)
- `RLIMIT_AS` on macOS → `RLIMIT_CPU` + wall clock; the memory clause runs in CI only (§6.1)
- Browser e2e harness → recorded manual verification, per project precedent
- Live CDN → manual post-deploy check (§9.1)

---

## Project Constraints (from CLAUDE.md)

Actionable directives extracted; the planner must verify compliance against each.

| Directive | Source | Bearing on Phase 4 |
|---|---|---|
| Content-stream editing only. **No white-box overlays.** No reflow. | CLAUDE.md:23-25 | Permanent anti-feature. No fallback path when a run refuses — the refusal *is* the behaviour. |
| Ephemerality is a **structural property**, not a retention policy | CLAUDE.md:27-29 | PRIV-02/03/05. The test is killing the cache, not a TTL. |
| **Never claim** "files never leave your device", "we never see your file", "deleted immediately" without stating the mechanism | CLAUDE.md:34-36 | Binding on the PRIV-01 UI copy. The first is *false* for the text engine. |
| Per-operation local/server disclosure is the novel claim | CLAUDE.md:32-33 | PRIV-01 must be derived from the dispatch predicate, not hand-labelled. |
| **No AGPL anywhere in the runtime tree, transitively.** CI fails on the resolved lockfile. | CLAUDE.md:37-42 | `tools/license_gate.py`; server deps must go through it. `pdf2docx` trap named explicitly. |
| GPL/LGPL only as a file-in/file-out subprocess | CLAUDE.md:38-40 | Keeps poppler/veraPDF available for the harness. |
| No accounts in v1; anyone can open the site and edit | CLAUDE.md:43 | No auth surface. CLAS-07's notify signal must not require an identity. |
| A queue is durable state — **an anti-feature for a no-retention product** | CLAUDE.md:89 | Do not add ARQ in Phase 4 (§7.3). |
| Bundled open-license fonts only; fixed set = fixed metrics | CLAUDE.md:25-26 | D-07 Liberation trio; no user-uploaded fonts. |
| Server holds no state whose loss is observable | CLAUDE.md:27-30 | Undo lives client-side (§11). |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | `httpx` is the correct dev dependency for `fastapi.testclient.TestClient` at fastapi 0.141.1 | Package audit, Env | Low — surfaces immediately on first test run; version unpinned here deliberately |
| A2 | The recommended CSP's `worker-src 'self' blob:` and `style-src 'unsafe-inline'` are what pdf.js 6.2.108 + `TextLayer` actually need | §9.2 | Medium — the CSP silently breaks rendering. **Mitigated by making the acceptance test behavioural** (render under the CSP) rather than header-only |
| A3 | Merging `main` → Phase 3 branch is lower-risk than porting the engine → `main` | §1.1 | Low — reversible; based on measured line counts and commit distance |
| A4 | A subprocess worker satisfies PRIV-07 without a container in dev | §6.2 | Medium — if a reviewer reads "per-job container" (PRIV-03) as required in *all* environments, the dev path is non-compliant. Flagged as a discretion item to confirm |
| A5 | The `.pdf` route naming choice (BYPASS vs DYNAMIC) is free to the product | §9.1 | Low — but if the download URL must end in `.pdf` for browser filename behaviour, DYNAMIC is unreachable and BYPASS is the only outcome |
| A6 | Colour is representable as a recipe style field without a new run-splitting rule | §3.3 | Medium — `engine/rewrite.py:624` says colour already breaks runs, so a colour change may be structurally a whole-run operation. Needs verification during planning |
| A7 | Six `Bucket` values collapse acceptably to three UI badge states | §10.4 | Low — a product/UI decision, reversible |
| A8 | The pypdf CVE class transfers to `pikepdf`/`playa` as a *shape*, not as a shared vulnerability | §12 | Low — the mitigations (visited sets, caps, isolation) are library-independent, which is PITFALLS' own stated point |
| A9 | A ~1s budget is the right VIEW-02 first-page threshold | §10.2 | Low — the measured value is 67ms; any budget in that neighbourhood works. The `_parse_page`-call-count assertion is the durable half |

---

## Open Questions

1. **Does `engine/walker.py` / `shared_xobjects.py` already carry a visited set for `Do` recursion?**
   - What we know: `engine/shared_xobjects.py` (116 lines) exists specifically to identify shared Form
     XObjects, and `run_id`'s grammar has an `xobj_path` tuple, implying traversal.
   - What's unclear: whether a self-referencing XObject is caught there or recurses. Not measured
     this session (no such fixture exists to test with — §5.4).
   - Recommendation: build the fixture first, run it against the *current* engine, and let the result
     decide whether INGE-04's third case is a worker-limit task or an engine-fix task. These are
     very different sizes.

2. **Is the deployment target Cloudflare?**
   - What we know: ROADMAP criterion 3 names Cloudflare's default extension list specifically.
   - What's unclear: no deployment target is selected anywhere in the planning docs.
   - Recommendation: treat "the CDN reports non-caching" as the requirement and Cloudflare as the
     assumed instance. Write the check parameterized on a deployment URL so it survives a change.

3. **What is the "specific external OCR route" (CLAS-07)?**
   - What we know: it must be named, and it gates OCR-03's measurement.
   - What's unclear: which tool. This is a product decision, not a technical one.
   - Recommendation: require it pinned before the refusal screen ships. A `TODO` here silently
     defeats the requirement.

4. **Does an e2e browser harness get added, or do the `e2e` rows become recorded manual checks?**
   - What we know: none exists; ~10 rows in the test map depend on the answer; this project has a
     working precedent for recorded manual verification (`G2B-GATE-RESULTS.md`).
   - Recommendation: **decide this before writing plans**, because it changes roughly a third of the
     validation architecture. Given D-4.4's ordering and the phase's size, recorded manual checks
     for the *journey* rows plus automated tests for every *data* row is the lazier and honest split.

5. **How much of FONT-07 ships in Phase 4?**
   - What we know: zero engine support; four locked Phase 3 decisions are implicated (§3.3).
   - Recommendation: surface as an explicit scoping decision. Colour and weight/style are tractable;
     size is the one that invalidates the fit ladder and may deserve a named refusal in v1.

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---|---|---|
| V2 Authentication | **No** | No accounts in v1 (CLAUDE.md:43). Anyone can open the site. |
| V3 Session Management | **Partially** | No login session, but there is a *document* session. Control: opaque, high-entropy, non-guessable handles (`sha256(os.urandom(16))[:16]`, `app.py:103` — already correct). Never a sequential or content-derived visible ID (ARCHITECTURE.md:229). |
| V4 Access Control | **Partially** | No multi-tenancy, but a job handle is a capability. Guessing one must not yield another user's document. Content-addressed cache entries are shared by design (same bytes = same entry), which is safe: you must already have the document to compute its hash. |
| V5 Input Validation | **Yes — the core of this phase** | Magic-byte sniff + size cap at ingest (INGE-01). `engine.recipe.parse_recipe` for the recipe (stdlib `json.loads`, exact-key check, two size ceilings). A separate request-body cap on the recipe route (§3.4). Password treated as a secret, not a string (§3.2). |
| V6 Cryptography | **Minimal** | SHA-256 for content addressing (not a security boundary — collision resistance is the only property needed) and `os.urandom` for handles. **PDF decryption is delegated to `pikepdf`; never hand-roll.** Owner-password-only encryption is not access control (PITFALLS) and must not be presented as such. |
| V7 Error Handling & Logging | **Yes** | PRIV-04/PRIV-05. Named refusal reasons only (EDIT-04); no document content, filenames, or passwords in logs or error events; `before_send` strips engine frame locals. |
| V12 Files & Resources | **Yes** | INGE-04. Isolated worker, `RLIMIT_AS` + wall clock, tmpfs scratch, no network egress, non-root, read-only rootfs, seccomp (ARCHITECTURE.md:689). Caps *before* parse. |
| V14 Configuration | **Yes** | PRIV-06 headers and CSP. `no-store, private` on every document route; CSP without `'unsafe-eval'`; CORS explicit (currently absent — defect #4). |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---|---|---|
| Hostile PDF exhausts memory/CPU in the parser (decompression bomb, cyclic page tree, XObject recursion) | Denial of Service | Isolated short-lived worker with `RLIMIT_AS` + hard wall clock; visited sets and depth caps on every graph traversal; existing `MAX_DOCUMENT_GLYPHS` cap. §6, §5.4 |
| Native-library memory corruption (pdfium/MuPDF class, CVE-2026-3308) | Elevation of Privilege | Same isolation. "Assume the parser will be exploited eventually; design so that it does not matter" (PITFALLS). No network egress from the worker. |
| Malicious font/`/FontMatrix` executing JS in the app origin (CVE-2024-4367) | Elevation of Privilege | pdf.js 6.2.108 (far past the 4.2.67 fix) + CSP without `'unsafe-eval'`; **measured: the pinned bundles contain no `eval`/`Function` at all** (§9.2) |
| Document bytes cached at the CDN edge because `.pdf` is a default-cacheable extension | Information Disclosure | `Cache-Control: no-store, private` **verified** to produce `BYPASS`/`DYNAMIC`; plus no `.pdf` extension in route paths. Never `no-cache`/`max-age=0` (§9.1) |
| Document content leaking into logs, tracebacks, or error-reporter frame locals | Information Disclosure | PRIV-04/05 canary on both paths; `before_send` stripping; named refusal reasons only; static AST check on `logger.*` calls |
| Extension-based upload validation accepting a non-PDF, or rejecting a valid PDF | Spoofing / DoS | Magic-byte sniff (INGE-01). **The scaffold currently does the wrong thing** (defect #6) |
| Recipe JSON with a huge op count / string length exhausting the request process | Denial of Service | `MAX_RECIPE_OPS` / `MAX_NEW_TEXT_CHARS` checked before per-op work (`recipe.py:110`,`:123`) **plus** a request-body size cap on the recipe route (§3.4) |
| Content-stream injection via `new_text` breaking out of the string literal | Tampering | Structurally prevented: `new_text` is written via `pikepdf.String` and `unparse_content_stream`, never string concatenation (03-RESEARCH.md Security Domain). Phase 4 must not build content-stream bytes by string formatting anywhere in `server/` |
| Password captured in a log, traceback, or job record | Information Disclosure | Redacting wrapper type; a dedicated canary marker in the password field (§3.2, Pitfall 11) |
| Active content (`/OpenAction`, `/AA`, `/JavaScript`, `/Launch`, `/EmbeddedFile`, XFA) surviving into output | Tampering (of the *recipient*) | PITFALLS/SUMMARY: strip on save, "or the product becomes a malware laundering service that returns a 'cleaned by' file." **Not currently a requirement in any phase** — flagged, see below |
| Missing CORS allowing any origin to drive the API once deployed | Spoofing | Explicit allowlist middleware (defect #4) |

**Gap worth surfacing to the maintainer:** SUMMARY.md:170 states that active content must be
stripped on save, and calls the failure mode "a malware laundering service." **No requirement ID
covers this** — it is not in INGE-01..04, not in PRIV-01..07, and not in the Out of Scope table. It
is not in Phase 4's scope as written, and I am not inventing scope. Flagging it as an unassigned
research finding rather than silently adding it or silently dropping it.

---

## Sources

### Primary (HIGH confidence — direct measurement or direct source read, this session)

- `engine/recipe.py` (731 lines), `engine/index.py`, `engine/records.py`, `engine/classify_run.py`,
  `engine/classify_page.py`, `engine/run_id.py`, `tools/pdftool.py`, `tools/license_gate.py`,
  `pyproject.toml`, `Dockerfile.ci`, `.github/workflows/*.yml` — read directly
- `server/app.py`, `server/engine_replace.py`, `server/ephemeral.py`, `client/src/App.jsx`,
  `client/vite.config.js`, `client/index.html`, `client/package.json` (branch `main`, `0acd3eb`) —
  read directly, read-only
- **Live reproduction** of `UnboundLocalError` in `replace_text_in_pdf` — executed
- **Live reproduction** of `TypeError: _parse_renderopts() got an unexpected keyword argument 'dpi'`
  on pypdfium2 5.12.1; `PdfBitmap` attribute inventory; `to_pil()` confirmed working — executed
- **Live reproduction** of `NameError: name 'SCRATCH_ROOT' is not defined` in both
  `server.app._ensure_scratch()` and `import server.ephemeral` — executed
- **`resource.setrlimit` measurement** on macOS 15.7.7 arm64: `RLIMIT_AS`/`RLIMIT_DATA` unsettable,
  `RLIMIT_CPU` settable — executed
- **Corpus measurements** over all 217 manifest entries: `%PDF-` offset distribution (217/217 at 0);
  user-password requirement (0 files); real signatures vs. `/SigFlags 2` fields (0 vs. 5);
  category counts — executed
- **`RunIndex` timing** on `irs_1040_instructions.pdf`: 21ms open, 46ms page(0), 96.4s for pages
  1–125 — executed
- **Run bbox derivation** on `irs_form_w4.pdf` p0: w=40.0pt, h=0.0pt — executed
- **`pdfjs-dist` 6.2.108 content grep**: `isEvalSupported` absent package-wide; zero `eval(` and
  zero `new Function(` across `pdf.mjs`/`pdf.worker.mjs`/`pdf.sandbox.mjs`; `TextLayer`,
  `convertToViewportPoint`, `convertToPdfPoint`, `disableAutoFetch`/`disableStream`/`disableRange`
  all present — executed
- `git ls-files client/node_modules | wc -l` → 5,041 — executed
- `.planning/` documents read in full: `04-CONTEXT.md`, `ROADMAP.md` (Phase 4 + Ordering),
  `REQUIREMENTS.md`, `STATE.md`, `RETENTION-MAP.md`, `03-CONTEXT.md` (D-01..D-15),
  `G2B-GATE-RESULTS.md`, `03-RESEARCH.md` (Validation Architecture + Security Domain),
  `PITFALLS.md` (attack table), `ARCHITECTURE.md` (§3 Option C, §4 addressing, isolation posture),
  `SUMMARY.md` (risk 6, differentiators), `CLAUDE.md`
- `.hermes/plans/2026-08-28_154500-phase-4-web-tier-plan.md` — read as prior art

### Secondary (HIGH confidence — authoritative external source fetched this session)

- **NVD REST API** (`services.nvd.nist.gov/rest/json/cves/2.0`) — CVE-2024-4367, CVE-2026-3308,
  CVE-2026-27628, CVE-2026-59935, CVE-2026-59936, CVE-2026-41312, CVE-2026-48155, CVE-2026-54530,
  CVE-2023-36464 — all nine fetched individually, descriptions quoted verbatim in §12
- **`developers.cloudflare.com/cache/concepts/default-cache-behavior/`** — the default cached
  file-extension list quoted verbatim; `.PDF` confirmed present
- **`developers.cloudflare.com/cache/concepts/cache-responses/`** — BYPASS vs DYNAMIC semantics and
  the exact directives producing each, quoted verbatim
- **`github.com/py-pdf/pypdf/security/advisories`** + `GHSA-763m-79hh-57f2` — the real XForm
  advisory (`< 6.16.1`, CWE-834, no assigned CVE)

### Tertiary (LOW confidence — flagged, not relied on)

- An initial WebSearch result claiming `.pdf` is **not** in Cloudflare's default cacheable list.
  **Contradicted by the official documentation** and discarded. Recorded because it is precisely the
  aggregator-vs-primary trap this research was asked to guard against.
- `mozilla/pdf.js` issue #19688 (closed as not planned) as evidence about `eval` in pdf.js — the
  issue concerns the **Node.js** worker-loading path. Superseded here by the direct grep of the
  installed browser bundles, which is stronger evidence.
- The recommended CSP header string (§9.2) — reasoned from pdf.js's known worker/blob and text-layer
  styling behaviour, **not** verified against a running build. Tagged A2.

---

## Metadata

**Confidence breakdown:**
- Scaffold audit: **HIGH** — every defect is either a live reproduction or a quoted file:line. Three
  of the four D-4.1 defects reproduce exactly; the fourth is corrected with evidence.
- Engine contract: **HIGH** — `engine/recipe.py` read in full; every signature, constant, and refusal
  string quoted from source.
- Requirement gaps (FONT-07, EDIT-01 bbox, INGE-02 password): **HIGH** — established by measurement
  and by grep returning zero matches, not by inference.
- Fixture inventory: **HIGH** — measured across all 217 corpus files with the commands shown.
- CVE re-verification: **HIGH** — NVD is the primary source and each ID was fetched individually.
- Cloudflare behaviour: **MEDIUM-HIGH** — official docs, fetched and quoted; not verified against a
  live deployment (none exists).
- pdf.js `eval` absence: **HIGH** — direct grep of the installed, pinned, unminified bundles.
- Platform limits (macOS `RLIMIT_AS`): **HIGH** for this machine; **MEDIUM** as a general macOS claim
  (one machine, one OS version, one arch).
- Isolation-mechanism recommendation: **MEDIUM** — reasoned from the measured constraints and
  ARCHITECTURE.md's stated posture; not prototyped this session.
- CSP header specifics: **LOW-MEDIUM** — reasoned, not verified against a build. Tagged A2 and
  deliberately gated behind a behavioural test rather than a header assertion.

**Research date:** 2026-08-30
**Valid until:** 2026-09-29 (30 days). Shorter for two items: the pdf.js `eval` finding is valid
only for the pinned 6.2.108 and must be re-checked on any upgrade (there is a test row for exactly
this); the CVE table should be re-run if Phase 4 execution slips more than a month.
