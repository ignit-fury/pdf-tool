---
phase: 05-find-and-replace-across-all-pages
reviewed: 2026-10-24T17:04:29Z
depth: standard
diff_base: e5f9323
reviewed_head: 630ca28
files_reviewed: 39
files_reviewed_list:
  - Dockerfile
  - Dockerfile.ci
  - client/package.json
  - client/vite.config.js
  - client/src/App.jsx
  - client/src/Viewer.jsx
  - client/src/session.mjs
  - client/src/session.test.mjs
  - client/src/style.css
  - client/src/find/FindPanel.jsx
  - client/src/find/buildRecipe.mjs
  - client/src/find/buildRecipe.test.mjs
  - client/src/find/indexing.mjs
  - client/src/find/indexing.test.mjs
  - client/src/find/preview.mjs
  - client/src/find/preview.test.mjs
  - client/src/find/replaceAll.mjs
  - client/src/find/replaceAll.test.mjs
  - client/src/find/search.mjs
  - client/src/find/search.test.mjs
  - engine/data/search-unicode-15.1.json
  - engine/fit.py
  - engine/fonts.py
  - engine/part_snapshot.py
  - engine/playa_boundary.py
  - engine/recipe.py
  - engine/rewrite.py
  - engine/search.py
  - server/worker.py
  - tools/build_search_unicode.py
  - tests/test_find_normalize_parity.py
  - tests/test_find_replace_performance.py
  - tests/test_find_replace_recipe.py
  - tests/test_gate_g4.py
  - tests/test_part_snapshot.py
  - tests/test_recipe_snapshots.py
  - tests/test_batch_ink_bounds.py
  - tests/test_fit.py
  - tests/test_recipe.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
resolved_findings:
  critical: 3
  warning: 0
  total: 3
status: clean
---

# Phase 5: Code Review Report

**Reviewed:** 2026-10-24T17:04:29Z  
**Depth:** Standard, with cross-file tracing of critical guards  
**Files reviewed:** 39  
**Status:** No remaining proven findings through `630ca28`

## Narrative Findings (AI reviewer)

Three BLOCKER findings were reproduced and fixed during this review: source-address collisions (`88702ec`), source-TJ envelope fitting (`a49976a`), and narrow serialized-space reversal (`630ca28`). Their corrections have been reviewed. No additional concrete BLOCKER or WARNING remains in the production snapshot through `630ca28`. Counts above describe remaining findings; resolved defects are retained below for traceability.

### Resolved CR-03 — BLOCKER: Inter-word compression can reverse narrow serialized spaces

**Status:** Fixed in `630ca28`, after RED regression `68b9911`. Corrective code and end-to-end regression reviewed.

**Files:**

- `/Users/prempatel/Pictures/pdf-tool/engine/fit.py:348-372`
- `/Users/prempatel/Pictures/pdf-tool/engine/recipe.py:438-449`
- Regression: `/Users/prempatel/Pictures/pdf-tool/tests/test_batch_ink_bounds.py:97`

**Issue:** The corrected recipe supplies actual serialized replacement advances to `fit_run`, but its compression budget still comes from `space_width_pt` on the font program. PDF dictionary `/Widths` are authoritative and may declare a narrower space. Accepted positive kerns can then exceed the entire actual space advance, moving the next word backward over the space. The new maximum-envelope guard does not detect interior reversal because the total extent still fits.

**Reproduction and impact:** A valid embedded Arial font classified as `editable_original` has PDF dictionary advances of 4pt for `a` and 0.1pt for a space at 12pt size. A 36.9pt source is replaced by ten `a` glyphs and nine spaces, totaling 40.9pt. The bundled/program space is 3.333984375pt, so the fit accepts nine 37.037037 TJ numbers, tightening each gap by 0.444444pt. The actual 0.1pt space becomes a negative gap. The engine owner's end-to-end reproduction at `/private/tmp/phase5-narrow-space.pdf` confirms that output text decodes adjacent words as joined `aa`. There is no classification invariant excluding this dictionary/program mismatch. The reviewer independently verified the fit arithmetic with a lightweight helper.

**Fix implemented:** The recipe now supplies the actual serialized PDF space advance for original fonts, or the rounded serialized bundled-space width for substituted fonts. `fit_run` uses that width for its compression budget. The reproducer consequently selects bounded Tz rather than reversing narrow spaces. The regression checks the complete replacement remains readable as one expected run, its extent remains contained, and every following glyph advances beyond the preceding space origin.

**Verification:** Reviewed `630ca28` and RED regression `68b9911`. Independently reran the lightweight fit helper with the actual 0.1pt space budget: strategy `tz`, scale 90.2200488997555%, not refused. The engine owner reports the end-to-end regression and 133 focused tests passed, with 30 modules passing mypy; those heavier commands were not rerun by this reviewer. The earlier successful G4 corpus run does not exercise this narrow-space dictionary case; the focused regression supplies that coverage.

### Resolved CR-02 — BLOCKER: Successful fit can write text beyond the original run bounds

**Status:** Fixed in `a49976a`, after RED regression `fd8484d`. Static patch review and recorded G4 evidence reviewed. CR-03 was a separate issue found and corrected while reviewing this correction.

**Files:**

- `/Users/prempatel/Pictures/pdf-tool/engine/fit.py:348-375`
- `/Users/prempatel/Pictures/pdf-tool/engine/rewrite.py:424`, `:436`, `:1010`, and `:1038`
- `/Users/prempatel/Pictures/pdf-tool/engine/part_snapshot.py:394`
- Runtime witness: `/Users/prempatel/Pictures/pdf-tool/tests/test_gate_g4.py:315-336`

**Issue:** The real batch replacement on corpus page 6 reports a successful 12pt `inter_word_kern` fit with zero residual delta, and passes the following-glyph guard, while replacement text extends beyond the original run's right boundary. The following text uses an absolute line position, so its unchanged position cannot detect this run's visible overflow. A reported successful fit is therefore insufficient evidence that the emitted replacement stays within the edited region.

**Reproduction and impact:** In the G4 `the` to `a` replacement, the original right boundary is 440.94pt; reported written boundaries are 447.445pt and 451.105pt, approximately 6.5pt and 10.2pt beyond it. The strict existing mask detects 76 changed pixels outside the allowed edited region. The orchestrator retained the image at `/private/tmp/phase5-g4-crop-page6.png`. The real corpus regression identifies page index 5 operator offsets 3749 and 5086, plus page index 8 offset 10861. Source TJ adjustments compressed the actual page-6 spans to 386.964/387.000pt, whereas the previous fit used nominal dictionary sums of 394.248/398.580pt and widened replacement spacing to those larger sums.

**Fix implemented:** Derive the source's actual glyph envelope independently of its final pen advance, including leading/trailing TJ positioning and the effective baseline transform. Fit replacement glyph advances from the serialized font dictionary, including rounded subset widths. Keep underflow after the final glyph instead of widening word gaps. Preserve leading positioning and independently correct the final pen for all strategies, clearing and restoring inherited character/word spacing while writing. A fresh first-glyph anchor and maximum-envelope check now runs through both PartSnapshot and complete-snapshot fallback paths, in addition to the existing following-glyph check.

**Verification:** Reviewed `a49976a` across fit, recipe, writer, fast guard, fallback guard, and regressions. Regression coverage includes the real compressed TJ lines, scaled/rotated matrices, multiple source operators, Tc/Tw/Tz preservation, a dependent follower, and deliberately corrupted output with an absolute-positioned follower in both guard paths. The recorded corrected G4 log `/private/tmp/pdf-tool-phase5-g4-20261024.log` reports 12 passed in 101.38s with 675 operations. The reviewer independently parsed all 120 per-page renderer records: 28 changed pages, 12 unchanged pages, PDFium/Poppler/MuPDF, and zero outside-mask changed pixels. The summary's original `changed_pages:40` was a report-only defaultdict-count error; per-page records establish the actual 28/12 split. No heavy rerun was launched by this reviewer.

### Resolved CR-01 — BLOCKER: Shared PDF addresses collapsed distinct search occurrences

**Status:** Fixed in `88702ec`; regression test introduced in `e200666`.

**Files:**

- `/Users/prempatel/Pictures/pdf-tool/client/src/find/search.mjs:5` and `:63-82`
- `/Users/prempatel/Pictures/pdf-tool/client/src/App.jsx:233`
- `/Users/prempatel/Pictures/pdf-tool/client/src/find/FindPanel.jsx:52`
- Regression: `/Users/prempatel/Pictures/pdf-tool/client/src/find/search.test.mjs`

**Issue:** One PDF text-showing instruction can produce multiple spatial runs with the same `run_id`. Previously, match IDs omitted page/run order, and navigation metadata used a map keyed only by `run_id`. Distinct occurrences could therefore share an ID and navigate to the wrong fragment. They were also advertised as replaceable even though the engine cannot safely address one fragment independently. Recipe construction grouped these fragments together and could throw before preview, preventing safe matches elsewhere from proceeding.

**Reproduction:** A cached page containing two editable `Hello` fragments with the same `run_id`, followed by one independently addressed editable `Hello`, produced three replaceable matches with only two distinct IDs. Building the replacement recipe failed before the server preview. The engine fixture `[(Hello) -10000 (Other)] TJ` independently demonstrates how one instruction can yield spatial fragments sharing an address.

**Fix implemented:** Count source addresses across all cached runs, including fragments without query matches. Keep ambiguous occurrences visible but locked with `operator_shared_by_multiple_runs`. Include page and run order in occurrence IDs. Resolve navigation and row metadata through `sourceRunForMatch`, which selects the exact page/run position and verifies its source ID. Safe occurrences remain eligible for recipe construction.

**Verification:** The focused command `node --test src/find/search.test.mjs`, run from `client/` against `88702ec`, passed all six tests. The regression covers distinct IDs, locked ambiguous occurrences, exact fragment navigation, a nonmatching sibling fragment, and continued construction of safe replacements. The production fix was also traced through App and FindPanel.

## Review coverage and limits

Engine tracing covered the fresh per-splice interpreter path, complete operator-domain consumption, frozen yielded graphics state, current instruction/state/font binding checks, shared-fragment refusal, following-glyph witnesses, subset reuse and restoration, and atomic failure behavior. The `805eff2` in-memory projection and `b943c9e` per-measurement CID width cache were reviewed in their callers. The initial static analysis did not expose CR-02; subsequent runtime evidence above supersedes its earlier no-additional-finding conclusion.

Client tracing covered review freshness, mutation locking and stale callbacks, viewer publication and one-batch undo, existing recipe/style preservation, stopped-index visibility, Unicode projection and inverse UTF-16/grapheme boundaries, source-address ambiguity, refusal filtering and re-preview, and recipe/body limits. Generated Unicode data was assessed through its generator, consumers, and parity tests rather than a raw dump of the generated table.

The integration tests were first reviewed while the gate worker was completing execution; the subsequent G4 runtime evidence and committed final gate changes through `5321df6` were also inspected. The G4 log cited above was produced after `a49976a`, before the final narrow-space correction `630ca28`. Final regression and performance evidence for that last correction remain the orchestrator's responsibility. No heavy Python worker, full pytest suite, or renderer batch was launched by this reviewer. Later source changes require their own recorded evidence; this review does not close deployment/CDN verification or authorize deployment.

Only this review artifact was written by the reviewer. Production and test source files were not modified.

### Post-review test-only verification

The final broad run against the reviewed production engine `630ca28` passed 556
tests, including G4, and exposed one obsolete refusal expectation. Test-only
`1f9af02` replaces that corpus expectation with independent text/anchor, all 663
following glyphs and outside-region pixel assertions, while separately injecting
a real terminal-TJ error into the disposable worker to prove late D04 refusal and
no partial output. The phase goal verifier inspected the change and independently
ran its three tests successfully; the final root rerun passed three tests in 2.41s.
No production guard changed after the reviewed head. The raw broad run and focused
correction are recorded separately in 05-G4-RESULTS, without relabeling the former
as a zero-failure run.

---

_Reviewer: Codex (gsd-code-reviewer)_  
_Depth: standard_

