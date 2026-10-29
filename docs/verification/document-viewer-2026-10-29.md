# Document viewer editor — local verification

2026-10-29. Baseline `25775b1`; feature branch `feat/document-viewer-editor`.
Plan and design were written before implementation in `docs/superpowers/`.
Six implementation tasks delivered in the existing architecture. No deployment.

## Delivered behavior

Continuous pages use stable physical-size shells, with canvas/text layers mounted
only near the viewport or for a pinned draft. Thumbnails release distant canvases
too. Actual 12-page navigation from page 1 to page 12 keeps only two page canvases
mounted. Scroll tracking is separate from explicit navigation and draft ownership.

After explicit Analyze text, click a server-issued target in Edit text, or
double-click analyzed horizontal text in reading mode. A native inline textarea
supports selection, typing/insertion, copy/paste and native draft Undo. A contextual
toolbar exposes detected source formatting, bundled font choices, numeric size,
bold/italic, color picker/hex and character spacing. Preview validates the exact
full recipe; Apply publishes real rewritten PDF bytes and rerenders. The temporary
input is not written as an annotation, white rectangle or second text layer.

Size shrink/equal and character spacing use the native writer, real widths,
searchable Unicode and restoration of following text state. Logical Tf and
physical display size remain distinct; viewport transforms handle UserUnit.
Original-byte retention, original-font addressing and atomic recipe replay remain.

New native image placements have isolated verified drawing streams and persistent
managed IDs. Browser-local selection, pointer/keyboard move, aspect-locked/free
resize, numeric position/dimensions, rotation, file replacement and confirmed
removal share the existing page-worker transaction. Original shared/foreign
resources remain untouched. Supported compressed drawing streams are decoded with
strict allocation/size bounds and exact canonical-content verification.

Mixed exact-byte Undo/Redo restores text/page/image/batch states without automatic
upload. New mutations clear Redo only on successful publication. Entry admission
uses the resulting past stack; transient memory admission still includes Redo.
Explicit Analyze resumes a restored deferred session without requiring a second
Edit click. Ctrl/Cmd+Z, Shift+Ctrl/Cmd+Z, Ctrl+Y and Save work outside text inputs.

Find provides Previous/Next, separate Preview Replace One/All and explicit apply.
Both reuse complete indexing, exclusions, Unicode case/word matching and the
existing full-recipe validation. One replaces the current occurrence only and
selects the next available match. All applies once, then highlights accepted
source text areas in the real final PDF. The tour has pause/resume/next/stop and
reduced motion; stopping never undoes or partially applies a transaction.

Panels remain optional; choosing page text returns focus to the document. Desktop
and 760/320px layouts keep toolbar controls reachable and the page scrollable.
Mobile actions scroll horizontally without causing body overflow.

## Automated/native results

| Check | Actual result |
|---|---|
| Selected complete Python regression: `python -m pytest -q -m 'not corpus and not linux_only and not cdn'` | **787 passed**, 39 deselected, 2 warnings, 136.87s |
| Added mandatory combined-runtime regression: `tests/test_managed_image_native.py` | **1 passed** (added after that full run) |
| Full client: `npm --prefix client test` | **170 passed** |
| G6/G7a/literal DOCX-removal: `tests/test_gate_g6.py tests/test_gate_g7a.py tests/test_docx_cuttable.py` | **12 passed**, 44.80s; authenticated veraPDF env |
| Strict mypy engine/server | **38 files**, no issues |
| Vite production build | Passed; existing chunk-size advisory |
| Python/client runtime license closures | Both passed; no lockfile/dependency change |
| Client license controls / Unicode data | **19 passed** / Unicode 15.1.0 current |
| Node-only builder boundary | 12 image tests pass; native-only case explicitly skipped there and required in combined Python CI |
| Three actual browser PDF downloads | **6 structural validations**, **36 exact unrelated-pixel comparisons**, searchable text and neighboring glyph origins verified |

The first broad run found the existing G2a minimal-instruction gate failing after
redundant Tf wrappers were added. The implementation was corrected, the unchanged
gate passed, and the complete selected suite reran successfully. The initial
unbounded corpus run was stopped at 75 passes/one skip; it is not a completed
full-corpus claim. Prior full public-corpus audit evidence is retained separately.

Logs under `/private/tmp/`: `viewer-python-reviewed.log`,
`viewer-cross-runtime-final.log`, `viewer-client-final.log`, `viewer-native-gates.log`,
`viewer-types-reviewed.log`, `viewer-final-build.log`, `viewer-license.log`,
`viewer-client-license.log`, `viewer-client-license-tests.log`, `viewer-unicode.log`.
Native/browser downloads, screenshots, request summaries and JSON results are under
`/private/tmp/pdf-tool-viewer-20261029/`; they are temporary local evidence.

## Actual browser scripts

Existing Playwright connector, local Chromium. Prima/provider configuration was
unavailable, so the existing connector was reused without installing a framework.
Scripts in `tests/browser/` are executable function expressions for the connector.

- `viewer-inline.js`: 12 continuous page shells, bounded canvases, no upload on
  open, short edit, longer text at 9pt/0.1pt spacing, native text input, original
  source upload recovery after history, Undo/Redo and new-branch Redo clearing.
- `viewer-images.js`: source font selection, 7pt bold/italic/custom hex color at
  150% zoom, native image insert/move/resize/90° rotation/WebP replacement/remove,
  preserved replacement geometry and image Undo/Redo with no server requests.
- `viewer-image-after-text.js`: reopen an actual managed-image download, apply a
  native text edit, then select/update its now-compressed image through the real
  browser worker. The cross-runtime ownership regression passes in the UI too.
- `viewer-stale-selection.js`: opening Find releases the old inline draft.
- `viewer-find.js`: 24 initial matches; one replacement then 23 replacements in
  one batch; explicit fallback font; exactly two actual apply requests; reduced
  motion, next/resume/pause/stop tour and whole-batch Undo/Redo without extra writes.
- `viewer-responsive.js`: 1280/760/320px; body width matches viewport, inline focus
  retained and page area remains usable (336/329/237px at 900px viewport height).
  Native font growth and overflowing text refuse; Apply stays disabled.
- `viewer-image-pointer.js`: actual pointer movement/resizing by 20 physical
  points at 115% zoom; aspect ratio stays 1.6; cancel leaves PDF unchanged.
- `viewer-password-recovery.js`: Unicode password unlock remains local; explicit
  analysis, simulated SOURCE_MISSING response, exactly one recovery upload,
  successful inline apply; untouched encrypted original byte-identical and actual
  unlocked edited PDF searchable. Backend tests separately cover real cache loss.

Also observed: blank insertion creates 13 pages, Undo restores 12; actual local
PNG export decodes at **1250×1667** for the 600×800pt page at 150 DPI. Page and
export unit/native gates continue to pass. Wide/mobile screenshots were inspected.

`tools/verify_viewer_downloads.py` checks actual downloaded inline/image/batch PDFs
with qpdf and strict pdfcpu, PDFium searchable text/pixels and the authoritative
index for unchanged neighboring glyph positions. Styled output has bold/italic
7pt text. Final batch contains 24 `Hi` occurrences and no `Hello` occurrences.

## Independent review and fixes

Fresh review reproduced four concrete findings; all were fixed, nothing suppressed:

1. No-style edits could use a regex-guessed font size after q/Q restoration.
   Universal parsed-font validation now refuses ambiguous state atomically; native
   regression fails before the fix and passes after. Redundant unchanged-size Tf
   wrappers were separately removed, preserving the original G2a diff guarantee.
2. Native text saves compressed managed-image streams and broke ownership checks.
   Bounded Flate decoding plus canonical verification now survives a real
   Node→native engine→Node edit/remove round trip. Spoof/bomb controls still fail.
3. Replace All could leave a stale inline input over newly committed text. Opening
   Find and batch publication now clear it; the browser regression is RED→GREEN.
4. At 100 history entries, Undo could not make room for a new branch. Admission
   now counts final past entries while budgeting retained Redo bytes; tests cover
   99-past/one-future success, 100-past refusal and oversized Redo memory refusal.

## Explicit limitations

- Preserve-layout editing is delivered. Arbitrary source reflow, multiline source
  text, new independent text boxes, changing line/paragraph spacing/alignment,
  shifting neighbors and continuing source text onto another page are unavailable.
  The PDF has no sufficiently reliable block/obstacle ownership model for these
  operations. The UI names this; flexible reflow is disabled. No text is clipped
  or silently discarded. Use smaller text, another bundled font/shorter wording,
  or a structured source document for reflow.
- Source size growth beyond original Tf refuses because vertical ink/neighbor
  ownership is unproved. Shrink/equal and safe width fitting work. Unsafe fonts,
  glyph mappings, shaping, quote operators and fit cases retain named refusals.
- Inline input supports horizontal text on unrotated pages. Directed/rotated text
  is refused with an alternative; page tools and read/copy remain usable. Browser
  input font appearance is approximate when the original font is unavailable;
  native validation and the actual rendered PDF determine the saved result.
- Image manipulation applies to verified managed placements, including reopened
  tool-created PDFs. Arbitrary original/shared/clipped source images remain
  preserved and uneditable. PNG/JPEG/WebP decode remains bounded; HEIC production
  confinement remains gated. Image rotation is bounded to page corners.
- Walkthrough highlights source run areas, not a new per-character glyph-box model.
  It presents completed results; it does not pretend each occurrence is being
  rewritten separately. No Word/Acrobat/new cross-browser sign-off is claimed.

No package or migration changes. CI reuses the existing Node builder binary in
the combined test image for the mandatory cross-runtime regression. The Node-only
builder still tests the browser closure without requiring Python. Container/hosted
CI execution remains unobserved. Earlier G3 Linux/container/CDN, G4 literal
contract, hosted G7a and Word/Acrobat observations remain open. No deployment.

## Run / reproduce

Use the README startup commands. After `npm --prefix client run build`, run the
existing FastAPI app on a local port, e.g.:

```sh
.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8767 --no-access-log
.venv/bin/python tools/build_viewer_fixtures.py /private/tmp/pdf-tool-viewer-20261029
npm --prefix client test
.venv/bin/python -m pytest -q -m 'not corpus and not linux_only and not cdn'
.venv/bin/python -m mypy engine/ server/
```

The full PDF/A native gates need the existing authenticated `VERAPDF_CMD` and
`JAVA_HOME`. Native pixel/structural checks require the existing dev qpdf/pdfcpu.
For browser checks run the named scripts through the existing Playwright connector
with `filename`. Run inline→images→stale-selection→find in order. For another URL
set `page.__viewerBaseUrl`; for another fixture directory set
`page.__viewerFixtureRoot`. Responsive/pointer/password scripts are supplemental.
Then run `python tools/verify_viewer_downloads.py <fixture-directory>`.
