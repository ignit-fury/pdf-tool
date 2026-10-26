# Phase 6 — Local G5 evidence

Date: 2026-10-26. Final application source: `f8fc3e4` (including the mobile CSS fix),
with PDF worker `3b96f3b`, integration `8a0b532`, and gate assertions `b68eb3c`.
No deployment, container installation, dependency addition or corpus mutation occurred.

## Automated evidence

| Check | Observed result |
|---|---|
| `.venv/bin/python -m pytest -q -m 'not corpus and not linux_only and not cdn'` | 560 passed, 36 deselected, 2 fixture warnings, 103.07s; includes all seven G5 tests |
| `npm --prefix client test` | 125 passed, zero failures/skips |
| `.venv/bin/python -m mypy` | 31 source files clean |
| `npm --prefix client run build` after CSS correction | Passed in 1.97s; existing chunk-size advisory |
| `node --test tools/client_license_gate.test.mjs` | 19 passed, zero failures/skips |
| `node tools/client_license_gate.mjs` | Resolved installed runtime closure and bundled notices passed |
| `.venv/bin/python tools/license_gate.py` | Passed |
| `.venv/bin/python tools/build_search_unicode.py --check` | Unicode 15.1.0 artifact current |
| `.venv/bin/python -m pytest -q tests/test_gate_g4.py` | 7 passed, 1 deprecation warning, 93.68s; technical proxy only |

Logs are `/private/tmp/pdf-tool-phase6-final-{python,client,types,build}-20261026.log`,
`pdf-tool-phase6-{license-tests,client-license,python-license}-20261026.log`, and
`pdf-tool-phase6-g4-regression-20261026.log` in the same directory. The only change
following the 560/125/type runs was one CSS selector, verified by rebuilding and
repeating the actual responsive browser checks; unchanged suites were not rerun.

## Independent native fidelity

The permanent gate materializes actual production JavaScript outputs, with independent
Python graph and pixel oracles. See `06-06-GATE-SUMMARY.md` for complete source hashes,
negative controls, command results and renderer versions.

- 24 actual output PDFs / 53 pages, rendered by PDFium, Poppler and MuPDF.
- 159 exact mapped same-engine comparisons; intended image regions alone masked.
- 24 additional exact independent RGB image comparisons and six exact controlled-name
  source comparisons. Corrupt-font, dangling-widget/destination and sibling-mutation
  controls establish nonvacuity.
- All 24 outputs pass qpdf and pdfcpu relaxed validation. Forty source/oracle file
  digests remain unchanged.
- Both real Arial programs remain distinct when both BaseFont and descriptor FontName
  are deliberately identical. Wrong page-0 font sharing visibly fails all three engines.
- Existing cross-engine comparator: **95 pass / 64 fail**. All 64 disagreements also
  occur in the unchanged source baseline: UserUnit=2 sizes differ between PDFium/Poppler
  and MuPDF. This is not reported as 159 cross-engine passes; no tolerance was widened.

Artifacts: `/private/tmp/pdf-tool-phase6-g5-20261026/`.

## Actual built-browser evidence

Used the connected Playwright browser plugin against `http://127.0.0.1:8766/`,
Chrome 156.0.0.0 on macOS. The observer begins before opening documents and watches
all same-origin HTTP request types, including workers and navigation, excluding only
served `/assets/` resources and favicon. The current empty API base resolves to this
same origin. It does not enumerate historical API endpoints. Negative controls counted
both `GET /phase6-observer-new-api` (fetch) and
`GET /jobs/phase6-observer/download` (document/navigation).

| Journey | Actual outcome |
|---|---|
| Open mixed/scanned 40-page PDF, switch panels, page controls | Zero API requests; page tools available without text classification |
| Insert, move, rotate, delete and Undo | 40 → 41 → 40 → 41 pages; actual minified worker deletion succeeds |
| Download original after page Undo | Exact opened-source digest restored |
| Merge plain PDF | No-fields/no-bookmarks notices; size normalization visibly unchecked; apply and Undo succeed, zero API requests |
| Merge graph fixture into itself | Eight duplicate field names announced with import prefix; bookmarks nested under filename; 2 → 4 → 2 pages, zero API requests |
| Signed import into plain PDF | No-collision notice; explicit imported-signature acknowledgement; merge disabled until acknowledged; discard preserves document |
| PNG / JPEG / WebP | Native decode, add-page and current-page placement succeed, zero API requests; oriented JPEG is 60 × 120 after EXIF rotation |
| Rotated/cropped image destination | 90° / 200 × 260 pt page; checked aspect lock, white-composited live preview, physical-point controls; placement/download local |
| HEIC select / success | Selection sends nothing. Explicit Convert sends one 548-byte `image/heic` POST with `ftypheic`, no PDF/password/auth header; real sips conversion then local placement/download |
| HEIC late response | Real response held while changing page; draft inherits current page 1 when conversion completes |
| HEIC refusal / unavailable / cancel | Metadata-bearing unsupported source refuses without document mutation; injected 503 displays HEIC_UNAVAILABLE guidance; dismiss/discard preserve document |
| Unicode-password local PDF | Unlock, insert, original/current downloads and Undo all local; unlocked-copy warning visible; edited two-page PDF independently opens without password |
| Signed local PDF | Page modifications disabled before explicit acknowledgement; insert and Undo succeed after acknowledgement; final-page deletion disabled |
| Explicit text analysis | Merely showing inspector makes no API request; Analyze makes upload + page-runs requests |
| Styled text → page → Undo | Bold/color #994333 and exact styled PDF bytes restored; page operation/Undo/download add no API traffic |
| Stopped Find → page → Undo → Resume | Undo makes zero requests and restores stopped 0-of-40 state (not 0-of-0). Explicit Resume uploads/reacquires and completes all 40 pages; partial nonzero cache restoration also covered by permanent tests |
| Responsive/focus | Final built CSS has scrollWidth = viewport at both 320 and 760 px; checked lock and placement controls visible; keyboard Tab gives Place image a visible outline |

The first mobile screenshots exposed a real specificity bug: `.page-ops input` made
visually hidden file inputs full width and widened the document to 519 px at 320 px.
The narrow `.page-ops input.visually-hidden` rule fixes their geometry. The actual
rebuilt app, without an injected style, was rechecked at 320/760 and photographed.
No new automated test mirrors this one-rule CSS correction.

Some early connector waits targeted already-present headings or outdated summary/button
text. Those harness waits timed out; corrected selectors/state waits confirmed the final
outcomes. They are not counted as product failures or silently relabeled passing runs.
Expected browser HTTP errors were the unsupported HEIC, injected unavailable response,
and deliberate observer-control 404; fixture font/ICC warnings were also observed.

## Download identities and preserved evidence

Browser captures, test inputs, screenshots and a 12-file `download-sha256.json` are in
`/private/tmp/pdf-tool-phase6-browser-20261026/`, outside Git. Final responsive images
are `phase6-final-320.png` and `phase6-final-760.png`.

- Opened pre-delete source and restored original:
  `5553718fed8755a06bfb23fb24c9d3a8088ab695465953add148309bd5f2bf58`.
- Styled output and page-Undo output:
  `a415c76bb50ef20337da43458ec8295ce01b794e5bd722485e5729d6e80c645b`.
- Encrypted source, untouched original and Undo-original downloads:
  `0427f6ccd3d3f7837a69d2e8a0fac0fbcc504677736c7f15a208d0b055cc7c15`.

Six downloaded App outputs (merge, PNG, JPEG, HEIC, rotated placement, unlocked copy)
also pass qpdf and pdfcpu independently. Their page counts are 4, 3, 2, 3, 2 and 2;
see `native-validation.json`. Observers/routes were removed and documents closed.

## Scope and remaining limits

This evidence establishes local PAGE-01 through PAGE-09 behavior. Worker timeouts,
retained/transient-memory refusal, stale-close ownership, unsupported merge graphs,
and nonzero partial-index restoration have permanent automated coverage; they were not
all forced in the browser. Earlier Phase 5 browser-find/input-Undo/cache-loss journeys
are preserved rather than claimed as fresh Phase 6 repetitions. This run used Chromium;
it does not claim a new Phase 6 Safari/Firefox certification.

G3 Linux/container/live-CDN checks, G4's literal legal-contract specimen, and production
Linux HEIC confinement remain open. Production HEIC conversion fails closed until that
confinement is verified. Native validation is not cryptographic signature attestation.

Design-hook triage: the historical `side-tab` finding has no current thick one-sided
card accent; current left borders are ordinary 1 px structural dividers. No suppression
was added, no intentional divider removed, and no matching issue remains standing.
