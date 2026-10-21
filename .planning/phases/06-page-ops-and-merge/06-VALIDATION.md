---
phase: 6
slug: page-ops-and-merge
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-30
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived verbatim from `06-RESEARCH.md` § Validation Architecture. Task IDs are filled in by the
> planner; every command below was written to be runnable, and every file marked `❌ Wave 0` does not
> exist yet.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| Framework (client unit) | `vitest` — not yet installed (Wave 0). No JS test framework exists in `client/package.json` today (confirmed by reading it directly: only `vite`/`@vitejs/plugin-react`/`@types/*` in devDependencies) |
| Framework (client E2E / network assertion) | `@playwright/test` — not yet installed (Wave 0) |
| Framework (three-engine bar on merged output) | `pytest` (existing, configured — `pyproject.toml`) driving the existing `harness/run_corpus_harness.py` / `harness/masked_diff.py`, unmodified |
| Config file (vitest) | none yet — Wave 0: create `client/vitest.config.ts` (or extend `vite.config.js` with a `test` block, the standard Vitest pattern for a Vite project) |
| Config file (playwright) | none yet — Wave 0: create `client/playwright.config.ts` |
| Quick run command (client unit) | `cd client && npx vitest run` |
| Quick run command (E2E) | `cd client && npx playwright test` |
| Full suite command | `cd client && npx vitest run && npx playwright test` + `uv run --frozen pytest -q -m "not corpus"` (Python side, for the merged-output three-engine check, once a Phase-6-specific test exists) |

## Per-Task Verification Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| PAGE-01 | Blank page inserted inherits adjacent page's MediaBox+rotation; UI discloses what was inherited | unit | `npx vitest run src/pageOps/insertBlankPage.test.ts` | ❌ Wave 0 |
| PAGE-01 | Never falls back to A4/Letter silently when an adjacent page exists | unit, negative case | `npx vitest run src/pageOps/insertBlankPage.test.ts -t "does not silently default"` | ❌ Wave 0 |
| PAGE-02 | Reorder works on any page regardless of editability classification | unit | `npx vitest run src/pageOps/reorder.test.ts` | ❌ Wave 0 |
| PAGE-03 | Rotate works on any page (incl. scanned/uneditable) | unit | `npx vitest run src/pageOps/rotate.test.ts` | ❌ Wave 0 |
| PAGE-04 | Delete works on any page | unit | `npx vitest run src/pageOps/deletePage.test.ts` | ❌ Wave 0 |
| PAGE-05 | Merge preserves per-page size by default; outlines nested; form-field collisions announced either way | unit + integration | `npx vitest run src/pageOps/mergePdf.test.ts` | ❌ Wave 0 |
| PAGE-06 | Merging two documents with same `/BaseFont`, different subsets, both render correctly — real corpus pair (`govdocs1_000_000010.pdf` + `govdocs1_001_001038.pdf`) | integration + three-engine | `npx vitest run src/pageOps/mergePdf.test.ts -t "font dedup"` (produces the merged file) then `uv run --frozen pytest tests/test_page6_merge_render.py::test_arial_subset_pair_renders_correctly -x` (three-engine check on the produced file) | ❌ Wave 0 (both sides) |
| PAGE-07 | PNG/JPEG/WebP merge as new page; transparency composited | unit | `npx vitest run src/pageOps/mergeImage.test.ts` | ❌ Wave 0 |
| PAGE-07 | HEIC merge as new page | **blocked** — pending Open Question 1's resolution | n/a | ❌ Wave 0, blocked |
| PAGE-08 | Place image on existing page with aspect-ratio lock; inherited-`/Resources` guard holds (D-6.4) | unit, using a **constructed** two-sibling-inherited-Resources fixture (corpus has none — Pitfall 2) | `npx vitest run src/pageOps/placeImage.test.ts -t "inherited resources"` | ❌ Wave 0 |
| PAGE-09 | Page-ops-only session produces its download with zero requests to document routes | E2E, observed network traffic | `npx playwright test tests/e2e/page09-zero-network.spec.ts` | ❌ Wave 0 |
| Gate G5 criterion 1 | (= PAGE-09) | E2E | same as above | ❌ Wave 0 |
| Gate G5 criterion 2 | (= PAGE-01 + PAGE-02/03/04 on uneditable pages) | unit | same as PAGE-01..04 rows | ❌ Wave 0 |
| Gate G5 criterion 3 | (= PAGE-06, "renders correctly in all three engines") | three-engine | `uv run --frozen pytest tests/test_page6_merge_render.py -x` | ❌ Wave 0 |
| Gate G5 criterion 4 | (= PAGE-05 outline/AcroForm/size + D-6.4 resource guard) | unit + constructed fixture | `npx vitest run src/pageOps/mergePdf.test.ts src/pageOps/placeImage.test.ts` | ❌ Wave 0 |
| Gate G5 criterion 5 | (= PAGE-07/08, incl. transparency composite + visible aspect-ratio lock) | unit + visual | `npx vitest run src/pageOps/mergeImage.test.ts src/pageOps/placeImage.test.ts` | ❌ Wave 0 |

## Sampling Rate

- **Per task commit:** `npx vitest run` (client-side, fast, no browser launch)
- **Per wave merge:** `npx vitest run && npx playwright test` (adds the E2E network-assertion
  suite) + `uv run --frozen pytest tests/test_page6_merge_render.py -x` (targeted, not the full
  corpus sweep — per this session's own instruction not to run full-corpus sweeps while other
  research runs concurrently)
- **Phase gate:** Full suite green, plus one manual/CI run of `harness/run_corpus_harness.py`
  against the actual PAGE-06 merged fixture output before `/gsd:verify-work`, satisfying ROADMAP
  criterion 3's three-engine bar on real merge output (not just the harness's existing corpus,
  which contains no merged files)

## Wave 0 Requirements

- [ ] `client/vitest.config.ts` (or a `test` block in the existing `client/vite.config.js`) —
      no JS test framework configured today
- [ ] `client/playwright.config.ts` + `npx playwright install chromium` — no E2E framework or
      browser binary installed today
- [ ] `client/src/pageOps/` — the entire module does not exist yet (Phase 4 hasn't built the SPA
      shell this phase's UI lives inside)
- [ ] `tests/test_page6_merge_render.py` — new Python test file, reusing
      `harness/masked_diff.py`/`harness/run_corpus_harness.py` unmodified against a Phase-6-produced
      merged fixture (the harness's existing corpus has no merged files — this phase must produce
      one and check it in, or generate it at test time)
- [ ] A constructed two-sibling-pages-sharing-inherited-`/Resources` PDF fixture for the D-6.4/
      PAGE-08 regression test — confirmed absent from the real corpus (Pitfall 2); build via
      `pikepdf` (same tool used to measure its absence) mirroring the minimal-fixture pattern
      `harness/g2b_fixture.py` already established for Phase 3's constructed G2b case
- [ ] `client/package.json` — add `license-checker` and a corresponding CI step, ahead of PAGE-07
      shipping any HEIC dependency (Pitfall 5)

---

## Manual-Only Verifications

| Check | Why it cannot be automated | Recorded where |
|---|---|---|
| Aspect-ratio locking is *visibly* surfaced (PAGE-08) | The requirement is explicitly about visibility — "not a hidden modifier key". A DOM assertion proves an affordance exists, not that it reads as one. | A dated results doc |
| Inserted blank page *shows the user* what it inherited (PAGE-01) | Same shape: the data assertion (MediaBox and rotation match the adjacent page) is automated; that the user is told is a visual check. | A dated results doc |
| Merged-document visual review in all three engines | The masked-diff assertion is automated; a human confirms the merged result reads correctly, following the `G2B-GATE-RESULTS.md` seam-review precedent. | A dated results doc |

---

## Validation Sign-Off

- [ ] Every requirement ID in this phase appears in at least one row of the verification map
- [ ] Every `❌ Wave 0` file has an owning task in a plan
- [ ] Every manual-only check has a named results document and an owning task
- [ ] The phase gate rows (`G6-*`) run green in CI, on Linux
- [ ] No row was dropped for being inconvenient to automate — it became a manual check instead

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
