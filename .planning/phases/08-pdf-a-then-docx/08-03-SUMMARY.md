---
phase: 08-pdf-a-then-docx
plan: "03"
subsystem: archival-product-flow
tags: [api, react, pdfa, isolation]
key-files:
  modified: [server/app.py, server/errors.py, server/isolation.py, server/worker.py, tests/test_export_api.py, client/src/exports/controller.mjs, client/src/exports/controller.test.mjs, client/src/exports/ExportPanel.jsx]
metrics:
  completed: "2026-10-28"
  api_tests: 33
  controller_tests: 9
---

# 08-03 — Local PDF/A export flow

Commit `e86468f` adds explicit server-side PDF/A-2b to the existing export panel.
`POST /exports?operation=pdfa` uses the existing isolated worker/admission/password
transport. The artifact envelope remains unchanged: archival.pdf, application/pdf,
changed_images=0. Nine finite worker errors map to safe public reason IDs and
literal client copy. ICC/module loading occurs before syscall restriction.

**Verification:** 12 API and two client RED tests failed before integration.
Final API **33 passed** (one existing warning), controller **9 passed**, production
build passed, strict engine/server typing **36 files** passed. A malformed
changed_images response also failed RED before its explicit PDF/A guard.

Actual browser proof at localhost:8767 records no eager API calls on opening or
choosing PDF/A. One explicit prepare posts current bytes. The original remains
9866 bytes with identical SHA-256 before/after export. After local blank insertion,
the posted 10046-byte two-page source matches both working downloads exactly
(`65764bd9e9d33ea15fd4a69203a6ea0e3505ae43c5e4a6177d3cd27950c96b67`).
The actual returned one-/two-page downloads independently pass veraPDF, **nine
exact native comparisons** and **four structural validations**.

Settled Undo clears the prepared link. Holding an actual server response then
cancelling creates zero links and restores focus to Prepare PDF/A-2b. Missing
fonts show the fixed refusal, with zero download links; the document stays open.
At 320/760px, scrollWidth equals viewport and the error heading receives focus.
The 320px screenshot was visually inspected. Password/signature paths and invalid
options are tested; no per-download certification claim appears in the UI.

Artifacts: `/private/tmp/pdf-tool-phase8-browser-20261028/` contains raw sanitized
network observations, downloaded PDFs, hashes/native/validator evidence and mobile
screenshots. Four initial locator/timing observations were corrected using the
observed UI; they are not product failures. The real blank-page refusal was fixed
in the converter, recorded in 08-02, and reverified through this actual flow.

## Self-Check: PASSED

No history writes, eager analysis, runtime validator, deployment or dependency
change. Browser document/observers closed after testing. Hosted CI remains pending.
DOCX implementation follows this verified PDF/A slice.
