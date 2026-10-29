# Precise search highlights — local verification

2026-10-29; baseline `d93653c`, branch `feat/document-viewer-editor`.
Design/plan preceded implementation. This client-only stage reuses the existing
PDF.js layer, canonical Unicode projection, source-run index and atomic writer.
No backend/API/engine changes, dependencies, migration or deployment.

## Delivered

- The active result highlights its selected characters rather than the entire run.
  The current effective full-run text is mapped canonically to actual DOM text nodes;
  UTF16 offsets are measured with DOM Range. Multiple occurrences in one run and
  ranges across split text nodes remain distinct.
- Source geometry must agree with every full-run/selected constituent rectangle and
  identify one unique candidate. Ambiguous/unsupported mappings show an explicitly
  labeled dashed original text area, rather than pretending another occurrence is
  exact. Rectangles are pointer-transparent; no selection, canvas or PDF mutation.
- Replacement review now captures output spans for each included occurrence, handling
  shorter/longer replacements and exclusions. The already-committed tour consumes
  those spans and current after-text. Empty replacements show removed-text locations.
  Timed advance waits for the actual page/text layer/highlight to render. Pause,
  resume, next, stop, reduced motion and whole-batch Undo are retained.
- PDF proxy, scale, target identity/range and completed text-layer binding prevent
  stale rectangles. Query/case/word-mode changes stop an unrelated old tour. Closing
  or opening another document cannot publish a previous highlight.
- A discovered UserUnit bug is fixed: the text layer now uses viewport scale ×
  UserUnit, aligning selection with the canvas on cropped/rotated scaled pages.
  Page/result scrolling targets only the continuous viewport. It no longer scrolls
  the app's outer overflow container and hides the header/toolbars.

Bounds: 100000 visible and normalized UTF16 units, 20000 source units, 10000 text
nodes, 64 candidate occurrences/rectangles and 64 consecutive non-starter combining
marks after decomposition. Limits return a labeled fallback. Canonical expansion and
reordering are budgeted before allocating the projection; invalid candidate attempts
count toward the limit as well. Geometry results retain no DOM nodes or PDF copies.

## Observed verification

| Check | Result |
|---|---|
| Full client suite | **193 passed**, including 6 new Find/highlight cases |
| Production Vite build | Passed; existing chunk-size advisory |
| Runtime Python/client license closures | Passed; unchanged dependencies/lockfiles |
| Client license controls / Unicode data | **19 passed** / Unicode 15.1.0 current |
| New actual browser journeys | **2 passed** |
| Existing browser regression | **10 journeys passed** on the final build |
| New actual downloads | **3 byte-identity checks**, **8 independent structural validations**, **12 unrelated-pixel comparisons** |
| Existing download regressions | Viewer 6 structural/36 pixel; navigation 12 structural/13 pixel/5 byte identities; text-box 10 structural/49 pixel checks passed |

No full Python suite, new cross-browser run or full public-corpus scan was performed
for this client-only stage. Earlier Python/gate evidence remains separate. Native
checks here inspect actual browser outputs with qpdf, strict pdfcpu and PDFium, plus
unchanged neighboring glyph origins through the existing engine reader.

### Browser proof

`tests/browser/highlights.js` uses a synthetic three-page PDF: repeated words in one
operator, precomposed accented text, a 90-degree cropped UserUnit2 page and overprinted
ambiguous text. Direct measurements independently compare the highlight rectangle
union with the selected DOM Range within 0.25px at 115%/200% zoom. It also splits an
actual text node without changing its content. The two identical words receive
different rectangles substantially narrower than their full source run.

Decomposed query `cafe\u0301` finds and highlights actual `CAFÉ`. Ambiguous overprint
shows a dashed source area and visible approximation status. Query changes remove
old rectangles. A longer `cat`→`otter` batch highlights the new output offsets on
both ordinary and rotated pages. Deletion has a distinct removed-area marker. Two
batch actions cause exactly two destructive writes; highlighting/touring adds none.
One Undo restores the exact previous PDF.

`tests/browser/highlight-lifecycle.js` holds real PDF.js text-content RPCs. The tour
stays on its first result for 1.8 seconds while the actual layer is held, then advances
after release/render. A query change while zoom rendering is pending clears the
tour/range. Opening another source before releasing a pending layer publishes no old
rectangles and downloads the exact new source. Instrumentation exists only in tests.

Screenshots were inspected. A new assertion catches outer-app scrolling that hid the
fixed chrome; measured viewport-only scrolling fixes it and keeps header position 0.
The precise and approximate styles remain visibly distinct without obscuring text.

Final existing regressions: `viewer-inline.js`, `viewer-images.js`, `viewer-find.js`,
`navigation.js`, `navigation-cancel.js`, `navigation-privacy.js`, `text-boxes.js`,
`text-boxes-safety.js`, `text-boxes-mixed.js`, `text-boxes-geometry.js`. They cover
source formatting/longer text, native images, One/All and tour, mixed exact history,
no-upload navigation, stale restores, native multiline containers and geometry.

### Review and corrections

One fresh read-only final review identified two Important defects, each reproduced
RED then fixed and GREEN:

1. Adversarial descending combining marks passed the character cap and made the
   existing canonical insertion reorder quadratic. Preflight now limits decomposed
   combining sequences. The review's 100000-character probe returned `limit` in
   **0.64ms** locally after the fix, versus its recorded 27-second blocking result.
   This is a measured probe, not a general browser-performance guarantee.
2. The union of disconnected text rectangles could cover an empty source location.
   Every constituent rectangle must now overlap the source geometry; disconnected
   joins fall back instead of being labeled precise.

No review findings remain deferred. Integration additionally reproduced/fixed the
UserUnit text-layer scale, old-tour query retention and outer-app scroll issue.
Tests retain explicit fallback behavior; no validator, edit-fit or security guard
was weakened to make the results pass. Raw failures remain in temporary evidence.

## Files and reproduction

New `client/src/find/highlight.mjs`, `highlightDom.mjs`, `FindHighlight.jsx` and
`highlight.test.mjs`; new shared `viewer/scroll.mjs`. Modified `Viewer.jsx`, `App.jsx`,
`ContinuousViewer.jsx`, viewer CSS and Find builder/walkthrough plus their tests.
New fixture/native-verifier tools and two browser scripts accompany design/plan,
README and planning updates.

Use the existing README local build/start instructions. Open a PDF, Find/index it,
select individual results and zoom. Preview/apply a batch to inspect actual output
spans. Approximate/deletion states identify the limitations on the page.

```sh
npm --prefix client test
npm --prefix client run build
.venv/bin/python tools/build_highlight_fixtures.py
# Existing browser connector: highlights.js then highlight-lifecycle.js.
# Defaults: http://127.0.0.1:8768/ and /private/tmp/pdf-tool-highlights-20261029.
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python tools/verify_highlight_downloads.py
```

Temporary artifacts: `/private/tmp/pdf-tool-highlights-20261029/` and
`/private/tmp/highlights-{client-final,build-final,native-final,review-red,review-green,license,license-tests,client-license,unicode,viewer-downloads,navigation-downloads,text-box-downloads}.log`.
Source fixtures are synthetic; no corpus/user document was modified.

## Remaining limits

“Precise” means a measured PDF.js text-layer range, not a glyph-ink contour or proof
that every PDF font/extractor agrees. Missing/normalized-different text, overlapping
or disconnected mappings, crop-excluded text and resource limits can require an
approximate area. A deleted span has no surviving glyphs; the original source area
is identified explicitly. If a page cannot render, automatic tour advance waits;
the page error and manual Next/Stop controls remain available.

Search still uses authoritative individual runs. It does not join fragmented or
overprinted runs, or native managed-container glyph runs into new cross-run matches.
The overprint fixture intentionally exposes that boundary; only four complete `cat`
matches on the first two pages are replaced, while fragment-only source text remains
unchanged. No expanded replacement coverage is claimed. Existing arbitrary-source
paragraph reflow/height growth, neighbor movement and foreign-image editing remain
unsupported. All prior Linux/container/CDN, contract-specimen, hosted G7a, HEIC
confinement and Word/Acrobat release observations remain open. Nothing deployed.
