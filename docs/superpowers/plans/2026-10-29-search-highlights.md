# Precise Search Highlights Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline; one fresh final review.

**Goal:** Highlight the actual selected text range and actual committed replacement
results, with explicit approximate/deletion fallbacks.

**Architecture:** Bounded canonical offset mapping plus DOM Range measurement reuse
PDF.js text layers and source-run geometry. Replacement builder emits output spans;
the walkthrough consumes only accepted spans after the atomic apply.

**Tech Stack:** Existing React/PDF.js/Unicode projection and Node/browser tests.
**Spec:** `docs/superpowers/specs/2026-10-29-search-highlights-design.md`.

## Global constraints

- No PDF rewrite/upload for highlighting, persisted documents, new dependency or deployment.
- Preserve source-issued addresses, existing fit/complete-index validation, atomic Apply,
  exports, source retention, Undo/Redo, original security limits and prior release gates.
- Bounds: visible100000/source20000 UTF16 units,nodes10000,candidates/rectangles64.
- Ambiguous/unmapped results show an explicitly approximate source area; deletion shows
  a removed-text location. No fabricated exactness or automatic arbitrary source reflow.

## Review focus

- Repeated words in one run and repeated identical runs at distinct/overlapping positions.
- Ligatures, composed/decomposed Unicode and UTF16 surrogate/normalization boundaries.
- Changed replacement lengths, exclusions and empty replacement output offsets.
- Zoom/rotation/crop/UserUnit, stale text layers and source/query changes while rendering.
- Tour timing, malformed/large content, pointer selection and PDF download integrity.

## Task1 — Bounded text/range model and actual replacement spans

Files: `find/highlight.mjs`, `highlight.test.mjs`, `buildRecipe.mjs`/tests,
`walkthrough.mjs`/tests.
- [x] Observe RED for projected range mapping, source glyph boundaries, limits and
  geometric disambiguation/fallback; implement pure bounded helpers and observe GREEN.
- [x] Observe RED for output spans with longer/shorter/excluded/deleted occurrences;
  emit spans from the authoritative builder and use accepted after-text in the tour.
- [x] Run focused Find tests; preserve unchanged replacement/recipe contracts.

## Task2 — Actual rendered text-layer highlights

Files: `find/highlightDom.mjs`, `FindHighlight.jsx`, `Viewer.jsx`, `App.jsx`, viewer CSS.
- [x] Build bounded DOM text-node ranges and measured local rectangles; use geometry
  to require one unique full-run candidate. No fuzzy text matching or proportional boxes.
- [x] Bind rectangles/status to completed current PDF/scale/target; cancel stale work.
- [x] Show precise/approximate/removed labels; preserve text selection and navigation.
- [x] Gate timed walkthrough advance on the actual rendered result. Keep manual controls,
  reduced motion and existing safe one-write batch/history semantics.
- [x] Full client tests and production build pass.

## Task3 — Integrated verification and final review

Files: synthetic fixture, browser script, verification report, README/planning updates.
- [x] Actual browser: repeated same-run matches, Unicode, geometry/zoom, edits and batch
  output spans/deletions; query/source changes, explicit fallback, reduced motion/Undo.
- [x] Verify temporary highlights never change/download PDF bytes; run relevant existing
  viewer/Find/navigation/text-box regressions and native download validation.
- [x] One fresh review; reproduce/fix real findings once and record evidence/limits.
- [x] Commit explicit owned paths; clean temporary artifacts; no deployment.

## Ledger

Baseline `d93653c`, clean existing feature branch. Native inline execution is retained
for efficiency; no per-task implementer agents. Final review only.
Ruling: DOM Range geometry rather than invented character-width interpolation — it
measures the rendered text layer, supports split nodes/rotation and fails explicitly.
Ruling: record output spans in replacement review rather than infer changes later —
this keeps walkthrough geometry tied to the actual validated/committed recipe.

Task1 complete: projected mapping, UTF16/canonical closure, bounds, geometric
disambiguation and actual output-span tests observed RED then GREEN.
Task2 complete: DOM Range highlights, explicit fallbacks, UserUnit selection alignment,
actual-render-gated tour and viewport-only scroll integrated. Full193 client tests
and build pass.
Task3 complete:2 new plus10 existing browser journeys pass on the final build;
actual outputs pass native integrity checks. One fresh review's2 Important findings
were reproduced and fixed in one pass; no deferred findings.
Ruling: cap decomposed non-starter sequences at64 before canonical projection —
prevents existing quadratic Unicode reordering from blocking the new highlight path.
Ruling: require constituent geometry agreement, not just an enclosing union —
prevents a disconnected text join from being labeled precise in empty space.
Ruling: share viewport-only scroll between page navigation and highlights — actual
visual evidence showed scrollIntoView moving outer chrome; a browser regression
now proves the header remains visible. Added `viewer/scroll.mjs` at that seam.
Final evidence: `docs/verification/search-highlights-2026-10-29.md`.
