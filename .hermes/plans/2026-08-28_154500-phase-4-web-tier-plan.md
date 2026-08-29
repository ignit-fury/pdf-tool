# Phase 4: Web Tier Walking Skeleton + Hardening — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Deliver a stranger-proof web app — open an untrusted PDF, see it rendered faithfully with per-page editability badges, replace one text run (server-issued hit boxes, not pdf.js text items), restyle it, see per-operation local/server disclosure, undo with one Ctrl+Z — with nothing about the session surviving on the server, and a structural-ephemerality canary passing in CI.

**Architecture:** FastAPI server owns the authoritative bytes and the text addresses (per ROADMAP decision "Server owns text addresses; the client echoes run IDs, never invents them"); the React/Vite SPA is a thin viewer + edit surface. The server exposes a `/jobs/{id}/runs` endpoint that the current `client/` mock references but does not yet exist; the edit path reuses the Phase 3 `engine.recipe` contract unchanged (the client sends the operation log, not the mutated file). Hardening (ephemeral scratch on tmpfs, hostile-input limits, no-store + CSP) is wired into the server before any mutating UI ships.

**Tech Stack:** Python 3.13 + FastAPI + uvicorn (server already in `server/app.py`); pikepdf / playa-pdf / fontTools / uharfbuzz (engine, already passing Gate G2b in the `gsd-phase-3-rewrite-engine-font-pipeline` worktree); React 18 + Vite + pdfjs-dist + `@cantoo/pdf-lib` (client already in `client/`); pytest + the existing three-engine `harness/`. Phase 3 engine must be merged to `main` first (see Task 0).

**Gate:** This phase's success is **Gate G3** — one indivisible claim: *safe to hand a stranger*. The per-page classification badges, the single-run edit round trip with undo, per-operation local/server disclosure, and the structural-ephemerality canary all land here, not later.

---

## Current context / assumptions

- We are officially in **Phase 3** (Gate G2b engine work lives in worktree `gsd-phase-3-rewrite-engine-font-pipeline` and its gate tests pass: `test_gate_g2a.py`, `test_gate_g2b.py`, `test_recipe.py`, `test_rewrite.py`, `test_fit.py`, `test_pdftool_edit.py` — 118 passed). Main branch still has only `pdftool index`; `edit` is not on main.
- A premature `client/` (React) and `server/` (FastAPI) scaffold already exists on `main`, **untracked** (never committed). It is why "upload works but edit doesn't" — it was started ahead of the roadmap's intended order ("No web tier before G2b").
- Observed defects in the current main-branch scaffold (must be fixed, not worked around):
  1. `server/app.py` `replace_text_in_pdf(...)` has an `UnboundLocalError` on `bundled_dir` (proven by calling it directly — it crashes before writing). This is the Phase 3 `server/engine_replace.py` copy on main; the worktree's `engine.recipe` is the corrected path and should replace it.
  2. `server/app.py` page-render endpoints call `page.render(dpi=...)`; installed pypdfium2 5.12.1 uses `page.render(scale=...)` → **HTTP 500**. Bug is in main's `server/`, not the client (client renders with pdf.js anyway).
  3. `client/src/App.jsx` `doFindReplace` references a `/jobs/{id}/runs` endpoint that **does not exist** on the server — it's a placeholder. This endpoint is the load-bearing piece for the edit UI.
  4. No CORS middleware on the server — fine through the Vite proxy, but must be added before any non-proxied/static deploy.
- The roadmap constraint is explicit: **Phase 4 depends on Phase 3 (Gate G2b) passing**. So Task 0 (port Phase 3 engine to main) is a prerequisite; without it the edit path has no working backend.

## What this plan deliberately does NOT do

- Build Find-and-Replace-across-all-pages (Phase 5), page ops/merge (Phase 6), exports (Phase 7), or PDF/A+DOCX (Phase 8). Those are later phases.
- Re-implement a second rewrite engine. The server calls `engine.recipe` (the Phase 3 contract), never a fork.

---

## Task 0: Port the Phase 3 rewrite engine onto `main` (prerequisite)

**Objective:** Make `pdftool edit` and the `engine.recipe` / `engine.rewrite` / `engine.fit` / `engine.fonts` modules available on `main` so the Phase 4 server has a working edit backend.

**Files:**
- Merge / copy from worktree `gsd-phase-3-rewrite-engine-font-pipeline/`: `engine/recipe.py`, `engine/rewrite.py`, `engine/fit.py`, `engine/fonts.py`, `engine/encoding_table.py` (if changed), `tools/pdftool.py` (add `edit` subcommand), `tests/test_gate_g2a.py`, `tests/test_gate_g2b.py`, `tests/test_recipe.py`, `tests/test_rewrite.py`, `tests/test_fit.py`, `tests/test_pdftool_edit.py`, `fonts/` (Liberation .ttf set).
- Test: the copied gate tests above.

**Step 1: Bring the Phase 3 modules onto main**

Copy the engine modules and `edit` CLI from the worktree into the main repo, preserving paths. Verify they import.

**Step 2: Run the gate tests on main**

Run: `uv run pytest tests/test_gate_g2a.py tests/test_gate_g2b.py tests/test_recipe.py tests/test_rewrite.py tests/test_fit.py tests/test_pdftool_edit.py -q`
Expected: PASS (the worktree reported 118 passed for this subset; confirm on main).

**Step 3: Fix the `server/engine_replace.py` `bundled_dir` UnboundLocalError**

Replace the broken `replace_text_in_pdf` usage with a thin server adapter that calls `engine.recipe.apply_recipe` (the corrected path). Keep the server's ephemeral scratch/job-store wrapping. Do not re-implement rewriting in the server.

**Step 4: Commit**

```bash
git add engine/ tools/pdftool.py tests/ fonts/ server/engine_replace.py
git commit -m "feat(phase4): port Phase 3 rewrite engine + edit to main, drop broken engine_replace"
```

## Task 1: Add the missing `/jobs/{id}/runs` endpoint (load-bearing for the edit UI)

**Objective:** Expose per-page run lists (run_id, display_text, verdict state + reason) so the client can enumerate editable runs and build a recipe — closing the placeholder gap in `App.jsx`.

**Files:**
- Modify: `server/app.py` (add route after `job_status`, ~line 248).
- Test: `tests/test_server_runs.py` (new).

**Step 1: Write failing test**

```python
def test_runs_endpoint_returns_classified_runs():
    # upload a known PDF, then GET /jobs/{id}/runs?page=0
    resp = client.post("/upload", files={"file": ("w9.pdf", w9_bytes, "application/pdf")})
    job_id = resp.json()["job_id"]
    r = client.get(f"/jobs/{job_id}/runs?page=0")
    assert r.status_code == 200
    body = r.json()
    assert "runs" in body and len(body["runs"]) > 0
    run = body["runs"][0]
    assert set(run) >= {"run_id", "display_text", "state"}
    # editable runs carry no reason; not_editable runs carry a reason
```

**Step 2: Run test to verify failure**

Run: `uv run pytest tests/test_server_runs.py -q`
Expected: FAIL — 404 (endpoint absent).

**Step 3: Implement the endpoint**

In `server/app.py`, add:

```python
@app.get("/jobs/{job_id}/runs")
def job_runs(job_id: str, page: int = Query(0, ge=0)):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    with RunIndex(job["pdf_path"]) as idx:
        if page < 0 or page >= idx.page_count:
            raise HTTPException(400, "page out of range")
        page_obj = idx.page(page)
        runs = [
            {
                "run_id": str(run.run_id),
                "display_text": run.display_text,
                "state": verdict.state,
                "reason": verdict.reason if verdict.state == "not_editable" else None,
            }
            for run, verdict in page_obj.runs
        ]
    return {"page": page, "runs": runs}
```

**Step 4: Run test to verify pass**

Run: `uv run pytest tests/test_server_runs.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add server/app.py tests/test_server_runs.py
git commit -m "feat(phase4): add /jobs/{id}/runs endpoint for client run enumeration"
```

## Task 2: Wire the client Find & Replace flow to the real endpoints

**Objective:** Replace the `App.jsx` placeholder so "Find Matches" lists editable runs containing the find string, and "Apply Replacements" posts a real recipe and downloads the result.

**Files:**
- Modify: `client/src/App.jsx` (`doFindReplace`, `executeReplace`, `downloadOutput`).
- Test: manual browser check + `tests/test_server_edit_loop.py` (server-side round trip).

**Step 1: Write server-side edit-loop test (proves the full path without a browser)**

```python
def test_edit_loop_upload_plan_apply_download():
    up = client.post("/upload", files={"file": ("w9.pdf", w9_bytes, "application/pdf")})
    job_id = up.json()["job_id"]
    runs = client.get(f"/jobs/{job_id}/runs?page=0").json()["runs"]
    target = next(r for r in runs if r["state"] == "editable_original")
    plan = client.post(f"/jobs/{job_id}/replace",
                       json={"replacements": [{"run_id": target["run_id"], "new_text": "EDITED"}]})
    assert plan.status_code == 200
    out_id = plan.json()["output_job_id"]
    dl = client.get(f"/jobs/{out_id}/download")
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "application/pdf"
```

**Step 2: Run test to verify failure (endpoint/flow not wired)**

Run: `uv run pytest tests/test_server_edit_loop.py -q`
Expected: FAIL (replace endpoint uses broken `engine_replace` / or recipe not integrated).

**Step 3: Implement `executeReplace` server-side** — point `server/app.py` `/jobs/{job_id}/replace` at `engine.recipe.apply_recipe` (Task 0), returning `output_job_id`. (If already wired in Task 0, this step confirms.)

**Step 4: Rewrite `doFindReplace` in `App.jsx`** to fetch `/jobs/{job_id}/runs?page=N` for all pages, filter editable runs whose `display_text` contains `findText`, and populate `replacements` with `{run_id, new_text: replaceText}`; `executeReplace` already posts the recipe and sets `outputJobId`; `downloadOutput` already downloads.

**Step 5: Run test + manual browser check**

Run: `uv run pytest tests/test_server_edit_loop.py -q` → PASS.
Manual: `uv run uvicorn server.app:app --port 8000` + `cd client && npm run dev`; open http://127.0.0.1:5173; upload a PDF; Find a string present in an editable run; Apply; Download; confirm the edited text is present.

**Step 6: Commit**

```bash
git add server/app.py client/src/App.jsx tests/test_server_edit_loop.py
git commit -m "feat(phase4): wire client find/replace to real runs + recipe endpoints"
```

## Task 3: Fix the server PNG/JPEG render bug (pypdfium2 `dpi` → `scale`)

**Objective:** Make `/jobs/{id}/page/{n}/png` and `/jpeg` return 200 (currently 500: `page.render(dpi=...)` is invalid in pypdfium2 5.12.1). Not on the default client path (client uses pdf.js) but required for Gate G3's "faithful render" and any server-side thumbnail.

**Files:**
- Modify: `server/app.py` (render_page, render_page_jpeg, ~lines 341–402).
- Test: `tests/test_server_render.py` (new).

**Step 1: Write failing test**

```python
def test_page_png_returns_image():
    up = client.post("/upload", files={"file": ("w9.pdf", w9_bytes, "application/pdf")})
    job_id = up.json()["job_id"]
    r = client.get(f"/jobs/{job_id}/page/0/png?dpi=100")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
```

**Step 2: Run test to verify failure**

Run: `uv run pytest tests/test_server_render.py -q` → FAIL (500).

**Step 3: Fix the render call**

Replace `page.render(dpi=dpi)` with `page.render(scale=dpi/72)` in both render endpoints (pypdfium2 5.12.1 API).

**Step 4: Run test to verify pass** → PASS.

**Step 5: Commit**

```bash
git add server/app.py tests/test_server_render.py
git commit -m "fix(phase4): pypdfium2 render uses scale= not dpi= (5.12.1)"
```

## Task 4: Structural ephemerality — tmpfs scratch + canary test (PRIV-01..07)

**Objective:** Prove in CI that nothing about a session survives: scratch on tmpfs (or a per-job temp dir unlinked in `finally`), no document bytes in logs/errors, and a `409 SOURCE_MISSING` re-upload path when the content-addressed cache is killed mid-session.

**Files:**
- Modify: `server/app.py` (`_init_scratch`, `_scratch_dir`, upload/download — already partially present; make cache-kill → `409` explicit).
- Test: `tests/test_ephemerality.py` (new), wired into CI `.github/workflows/*.yml`.

**Step 1: Write failing test for canary**

```python
def test_kill_cache_mid_session_returns_409_then_reupload_survives():
    up = client.post("/upload", files={"file": ("w9.pdf", w9_bytes, "application/pdf")})
    job_id = up.json()["job_id"]
    # simulate cache eviction
    shutil.rmtree(SCRATCH_ROOT, ignore_errors=True)
    r = client.get(f"/jobs/{job_id}/status")
    assert r.status_code == 409  # SOURCE_MISSING
    # re-upload same bytes restores the session
    up2 = client.post("/upload", files={"file": ("w9.pdf", w9_bytes, "application/pdf")})
    assert up2.status_code == 200
```

**Step 2: Run test to verify failure** → FAIL (no 409 path).

**Step 3: Implement** — on `job_status`/`download`, if `job["pdf_path"]` is missing, raise `HTTPException(409, "SOURCE_MISSING")`. Ensure `_scratch_dir` unlinks in `finally` and no `log` call includes `raw`/`file.filename` content beyond the digest prefix (already the convention).

**Step 4: Run test to verify pass** → PASS.

**Step 5: Add to CI** — extend `.github/workflows/tests.yml` (or the worktree's equivalent) to run `tests/test_ephemerality.py`.

**Step 6: Commit**

```bash
git add server/app.py tests/test_ephemerality.py .github/workflows/tests.yml
git commit -m "feat(phase4): structural ephemerality canary (tmpfs scratch, 409 re-upload)"
```

## Task 5: Hostile-input hardening (INGE-01..04)

**Objective:** A decompression bomb, cyclic page tree, and self-referencing Form XObject each fail inside an isolated worker with `RLIMIT_AS` + wall-clock timeout; uploads accepted by magic-byte sniff + size cap, never extension; PDF parsing never runs in the request process.

**Files:**
- Modify: `server/app.py` (upload magic-byte sniff; offload parse to a worker with `RLIMIT_AS`/`timeout` — or at minimum guard `RunIndex` open with the existing `DocumentTooLargeError` + a size cap already present as `MAX_UPLOAD_BYTES`).
- Test: `tests/test_hardening.py` (new) using fixtures `tests/fixtures/mixed_scanned.pdf` etc.

**Step 1: Write failing test** (upload by extension-only is currently rejected; prove magic-byte path and that a bogus extension with valid PDF bytes is accepted)

```python
def test_upload_accepted_by_magic_bytes_not_extension():
    bad_ext = ("w9.pdf.exe", w9_bytes, "application/octet-stream")
    r = client.post("/upload", files={"file": bad_ext})
    assert r.status_code == 200  # bytes are PDF; extension lies
```

**Step 2: Run test to verify behavior** — if it already passes (current code checks `.pdf` suffix, so it will FAIL here). Adjust `upload()` to sniff magic bytes (`%PDF`) and drop the extension check.

**Step 3: Implement magic-byte sniff + keep `MAX_UPLOAD_BYTES` cap; document that full `RLIMIT_AS` isolation is a follow-up container task (note in plan, do not over-build).**

**Step 4: Run test** → PASS.

**Step 5: Commit**

```bash
git add server/app.py tests/test_hardening.py
git commit -m "feat(phase4): upload by magic-byte sniff + size cap; extension ignored"
```

## Task 6: Per-page classification badges + refusal screen (CLAS-06, CLAS-07)

**Objective:** The viewer shows per-page badges (editable / substitution / not-editable with reason) in the thumbnail rail, and a one-click "tell me when OCR ships" route for scanned pages.

**Files:**
- Modify: `client/src/App.jsx` (classification panel → thumbnail-rail badges; refusal screen for `not_editable` pages naming the reason + OCR external route).
- Test: `tests/test_server_runs.py` already covers the data; add `tests/test_client_badges.py` only if a component test harness exists (otherwise manual browser check).

**Step 1: Extend the classification panel** into a thumbnail rail: render one badge per page using the existing `/jobs/{id}/status` `classification` array (already fetched). Clicking a page jumps to it (reuse `goToPage`).

**Step 2: Refusal screen** — when a page's bucket is `scan`/`not_editable`, show a panel: reason + "OCR is not yet available — tell me when it ships" (no backend call; local state toggle).

**Step 3: Manual browser check** — upload `tests/fixtures/mixed_scanned.pdf`; confirm editable pages show green badges, scanned page shows the OCR route.

**Step 4: Commit**

```bash
git add client/src/App.jsx
git commit -m "feat(phase4): per-page classification badges + OCR refusal screen (CLAS-06/07)"
```

## Task 7: Single-run edit with browser hit-testing + restyle + undo (EDIT-01, EDIT-05, VIEW-01..04, FONT-07)

**Objective:** User selects a text run hit-tested against server-issued boxes (never pdf.js text items), replaces it, restyles (size/weight/style/colour), sees per-operation local/server disclosure, and reverts with one Ctrl+Z.

**Files:**
- Modify: `client/src/App.jsx` (selection overlay from server run boxes; restyle controls; undo stack).
- Server: `engine.recipe` already supports `new_text`; restyle needs `font_size`/`color` added to `RecipeOp` (engine change in Phase 3 modules — extend `parse_recipe` + `apply_recipe` to accept optional style fields; keep backward-compatible).
- Test: `tests/test_recipe_restyle.py` (new, server-side).

**Step 1: Write failing test for restyle op**

```python
def test_recipe_op_accepts_style():
    op = parse_recipe(b'[{"run_id":"x:y:z","new_text":"Hi","font_size":12,"color":"#ff0000"}]')
    assert op[0].font_size == 12
```

**Step 2: Run test to verify failure** → FAIL (`parse_recipe` requires exactly `run_id`+`new_text`).

**Step 3: Extend `engine.recipe.parse_recipe` to allow optional `font_size`/`color`/`weight`/`style` keys; `apply_rewrite`/`rewrite_run` emits the `Tf`/color operators. (This is an engine change — keep it minimal and add a unit test in `tests/test_recipe.py`.)

**Step 4: Client selection overlay** — render run boxes from `/jobs/{id}/runs`; on click, open a small popover with text + restyle inputs; on apply, post the recipe (Task 2 path) and push the prior state onto an undo stack.

**Step 5: Undo** — Ctrl+Z pops the stack and re-applies the previous recipe (or the identity recipe) via `apply_recipe`.

**Step 6: Per-operation disclosure** — label each applied edit "server" (all text edits are server-side per architecture) in the message bar.

**Step 7: Run tests + manual check** → PASS; browser: select a run, change text + size, Apply, Ctrl+Z reverts.

**Step 8: Commit**

```bash
git add engine/recipe.py client/src/App.jsx tests/test_recipe_restyle.py
git commit -m "feat(phase4): single-run edit, restyle, hit-test boxes, undo (EDIT-01/05)"
```

## Task 8: No-store + CSP + CORS (PRIV-03, and the CORS gap found earlier)

**Objective:** Document routes send `Cache-Control: no-store`; a CSP forbidding `eval` is in force (`isEvalSupported: false` on pdf.js); CORS middleware added so non-proxied/static deploys don't break.

**Files:**
- Modify: `server/app.py` (add `CORSMiddleware` + `Cache-Control` response header middleware; pdf.js `isEvalSupported:false` already set in `client/src/main.jsx`? verify).
- Test: `tests/test_security_headers.py` (new).

**Step 1: Write failing test**

```python
def test_no_store_and_cors_present():
    r = client.get("/health")
    assert r.headers.get("cache-control") == "no-store"
    # CORS preflight
    pre = client.options("/upload", headers={"Origin": "http://example.com",
                       "Access-Control-Request-Method": "POST"})
    assert pre.headers.get("access-control-allow-origin") is not None
```

**Step 2: Run test to verify failure** → FAIL.

**Step 3: Add `CORSMiddleware` (allow the Vite dev origin + configurable `VITE_API_URL`) and a response middleware setting `Cache-Control: no-store` on `/jobs` and `/upload`.

**Step 4: Run test** → PASS.

**Step 5: Commit**

```bash
git add server/app.py tests/test_security_headers.py
git commit -m "feat(phase4): no-store + CSP + CORS middleware (PRIV-03)"
```

## Task 9: Gate G3 verification — three-engine pixel diff on a real edit + full test run

**Objective:** Prove the web edit path produces output that satisfies Gate G3's "faithful render, nothing else moves" using the existing `harness/run_corpus_harness.py` + `masked_diff.py`.

**Files:**
- New: `tests/test_gate_g3.py` (reuses `harness.masked_pixel_diff`, `harness.render_diff`).
- Test: full suite `uv run pytest tests/ -m "not corpus"` then `-m corpus`.

**Step 1: Write a G3 test** that uploads a fixture, applies one editable run replacement via the real endpoints, renders the output through pdfium/poppler/mupdf, and asserts pixel-identical outside the edited run's box (same technique as `test_gate_g2a.py`).

**Step 2: Run** `uv run pytest tests/test_gate_g3.py -q` → PASS.

**Step 3: Run the whole suite** `uv run pytest tests/ -m "not corpus" -q` (expect green) and `uv run mypy engine/ server/ client` not applicable (client is JS) — run `uv run mypy engine/ server/`.

**Step 4: Commit**

```bash
git add tests/test_gate_g3.py
git commit -m "feat(phase4): Gate G3 verification — three-engine pixel diff on web edit"
```

---

## Files likely to change (summary)

- `server/app.py` — `/jobs/{id}/runs`, fix render `scale=`, ephemerality 409, magic-byte upload, CORS/no-store, recipe-backed replace.
- `engine/recipe.py`, `engine/rewrite.py`, `engine/fit.py`, `engine/fonts.py` — port from worktree (Task 0) + optional restyle fields (Task 7).
- `server/engine_replace.py` — replaced by `engine.recipe` adapter (Task 0).
- `client/src/App.jsx` — real find/replace, badges, refusal screen, hit-test selection, restyle, undo, disclosure.
- `tools/pdftool.py` — add `edit` subcommand (Task 0).
- `tests/` — `test_server_runs.py`, `test_server_edit_loop.py`, `test_server_render.py`, `test_ephemerality.py`, `test_hardening.py`, `test_security_headers.py`, `test_recipe_restyle.py`, `test_gate_g3.py`.
- `.github/workflows/tests.yml` — include new tests.
- `fonts/` — Liberation .ttf set (from worktree).

## Tests / validation (commands)

- Unit/integration (no corpus): `uv run pytest tests/ -m "not corpus" -q`
- Corpus sweeps: `uv run pytest tests/ -m corpus -q` (slow — runs in CI, not per commit)
- Types: `uv run mypy engine/ server/`
- Manual: `uv run uvicorn server.app:app --port 8000` + `cd client && npm run dev`, open http://127.0.0.1:5173

## Risks, tradeoffs, open questions

- **Phase 3 not yet on main.** Task 0 is a hard prerequisite; if the worktree's engine doesn't copy cleanly, the edit path has no backend. Mitigation: copy verified-passing modules + run the gate tests on main before any UI work.
- **Type1/CFF and Type0/CID coverage gap.** Observed during hand-testing: `load_font` (fontTools `TTFont`) only handles TrueType; CFF/Type0 runs get `resolution_failed`. The roadmap treats this as Phase 3's remaining font-format work, NOT Phase 4. Phase 4 should refuse these honestly (named reason) and not attempt to edit them. Flag to user: full corpus coverage needs the CFF/Type0 shaping work, which is a Phase 3 follow-up, not in scope here.
- **`RLIMIT_AS` isolation** is a container-level concern; Task 5 does the upload-surface half (magic-byte + size cap) and documents the worker-isolation follow-up rather than over-building it in-process.
- **Restyle fields** extend the Phase 3 `RecipeOp` contract; keep additive/optional so the CLI recipe format and Phase 4 wire format stay identical (ROADMAP requirement).
- **No second extraction path.** All text-derived features must consume `engine.index`/`engine.recipe`; do not introduce a parallel text extractor in the client.
- **Web scaffold is untracked.** First commit of `client/`/`server/` should happen deliberately (Task 1+), not as part of Task 0's engine port, so history stays reviewable.
