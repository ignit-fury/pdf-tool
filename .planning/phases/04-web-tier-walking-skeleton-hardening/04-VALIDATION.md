---
phase: 4
slug: web-tier-walking-skeleton-hardening
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-30
---

# Phase 4 — Validation Strategy

## Execution reconciliation — 2026-10-21

This document preserves the pre-implementation contract and proposed test names below.
Actual tests were consolidated into `test_web_contract.py`, `test_worker.py`,
`test_engine_passwords.py`, `test_engine_styles.py`, `test_boxes.py`, `test_ephemerality.py`,
`test_headers.py`, `test_isolation.py`, `test_hostile_input.py`, `test_linux_sandbox.py`,
`test_privacy_canary.py`, `test_cdn.py`, and the dependency-free client session tests.
HTTPX, markers, server typing, generated fixtures and local assets are implemented.
Browser journey rows are recorded UI checks; clipboard and deployment checks remain open.
`04-VERIFICATION.md` is the dated execution evidence and release-gate record; unchecked
Wave 0 rows and planned test paths below are historical planning statements, not current
absence claims. Linux/container and live CDN sign-off remain pending.

> Per-phase validation contract for feedback sampling during execution.
> Derived verbatim from `04-RESEARCH.md` § Validation Architecture. Task IDs are filled in by the
> planner; every command below was written to be runnable, and every file marked `❌ Wave 0` does not
> exist yet.

---

## Test Infrastructure

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

## Per-Task Verification Map

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

## Sampling Rate

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

## Wave 0 Requirements

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

---

## Manual-Only Verifications

| Check | Why it cannot be automated | Recorded where |
|---|---|---|
| CDN reports `BYPASS`/`DYNAMIC` for document routes (PRIV-06) | Requires a live deployment behind a real CDN. No deployment target is selected yet; the check is parameterized on a deployment URL (A-4.4). | A dated results doc, `PLAYA-DECISION.md` precedent |
| CVE re-verification against NVD | `STATE.md` records the PITFALLS.md attack table as partly aggregator-sourced and requires re-verification at implementation time. `04-RESEARCH.md` §12 is the content; it must land as a committed artifact. | `CVE-VERIFICATION.md` in this phase dir |
| G3-4 / G3-5 user journeys in a real browser | Per A-4.3: journey rows are recorded manual checks, data rows are automated. No e2e harness is being built. | A dated results doc with a `## Decision` header, per-check evidence, and an explicit "what was NOT tested" section |

Per amendment **A-4.3**, a journey row is never silently dropped because it is hard to automate —
it becomes a recorded manual check with the same evidentiary standard `G2B-GATE-RESULTS.md` set.

---

## Validation Sign-Off

- [ ] Every requirement ID in this phase appears in at least one row of the verification map
- [ ] Every `❌ Wave 0` file has an owning task in a plan
- [ ] Every manual-only check has a named results document and an owning task
- [ ] The phase gate rows (`G4-*`) run green in CI, on Linux
- [ ] No row was dropped for being inconvenient to automate — it became a manual check instead

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
