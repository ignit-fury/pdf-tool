# Native inserted text containers — local verification

2026-10-29; baseline `35c9307`, branch `feat/document-viewer-editor`.
The design and implementation plan preceded code. This is the next working stage
of the requested editor upgrade. No deployment, dependency installation, migration
or new runtime dependency occurred. Existing release gates remain open.

## Delivered and architectural decisions

- **Direct insertion and editing:** Insert text, click a page, type multiline text
  in place, set geometry/page/font/size/color/bold/italic/alignment and character,
  line and paragraph spacing. Text wraps inside its own container. Explicit height
  expansion is offered on overflow when page bounds permit it.
- **Genuine searchable PDF content:** existing bundled font subset/embed pipeline
  generates Type0 glyph operations in separately owned content streams. Source
  content is retained under validated graphics-state isolation. No white rectangles,
  text annotations, page rasterization or automatic paragraph reconstruction.
- **Exact preview and atomic publication:** a separate controller uploads the
  current materialized PDF only after an explicit action. It uses a separate
  cache-recovery context and immutable session/bytes/version capture. The exact
  candidate PDF renders in the viewer; committed PDF/thumbnails/exports/history
  remain separate. Apply publishes that candidate without another server rewrite
  and adds one mixed-history entry. Cancel/stale/overflow publish nothing.
- **Ownership and geometry:** canonical bounded stream/font/spec proof protects
  edit/removal, including compressed streams, shared resources and malicious
  metadata. Page insertion/move/delete and quarter-turn transforms project verified
  metadata into current visible coordinates. Browser source-text targets redirect
  verified managed runs to the full container; direct recipe edits refuse them.
- **Safety/privacy:** existing raw upload/cache/password/signature/resource/process
  protections remain. List is read-only; signed mutations require acknowledgement.
  Successful mutation discloses signature invalidation/unlocked copy. Strict finite
  JSON/envelopes, source hash checks and candidate memory admission remain bounded.
  Default collision checks use rendered pixels and annotation rectangles; explicit
  overlap adds transparent content and never removes the underlying source.

## Verification results

| Check | Observed result |
|---|---|
| Selected complete Python suite, excluding corpus/Linux/CDN markers | **867 passed**, 39 deselected, 2 existing warnings, 169.09s |
| Final native/API/recipe focused suite after the PDF-version correction | **114 passed**, including one additional version regression, 28.83s |
| Full client suite | **180 passed** |
| Existing G6/G7a/DOCX-removal gates | **12 passed**, 47.72s |
| Strict engine/server mypy | **39 files**, no issues |
| Vite production build | Passed; existing chunk-size advisory |
| Python/client runtime license closure | Passed; no dependency/lockfile changes |
| Client license negative controls / Unicode data | **19 passed** / Unicode 15.1.0 current |
| Actual browser downloads | **10 independent structural validations**, 49 unrelated-pixel comparisons, searchable text, preserved original image/link |

The broad run includes the browser-wrapper fix. The subsequent final focused run
also covers the minimum PDF-version fix for UserUnit; the broad suite is not
misrepresented as containing that later additional test. Existing corpus evidence
is retained; no new complete 217-PDF audit was run for this stage.

Independent review found PDF primitive-type confusion in font proof, invalidation
after legitimate page transformations, and unbounded accumulated isolation wrappers.
All were reproduced/fixed with regressions. Integration then found the legitimate
browser image writer's outer q/Q wrapper was refused; preserving/validating it fixes
the actual mixed browser journey. Strict pdfcpu validation exposed UserUnit in an
older PDF header; output now declares at least PDF1.6 when that entry is present.
A browser redirect race caused version-only rendering to cancel a just-started
current-byte list; source changes still invalidate, and controller capture checks
continue to reject stale versions. The complete mixed journey passes after the fix. A final lifecycle regression also
proved canceled overlapping PDF.js preparations were undercounted; independent
per-generation accounting now retains each allocation until its own completion.

The first broad run recorded **1 failed / 865 passed**: the newly intentional
`managed_text_box` refusal was missing from the fixed test vocabulary. That test
list now includes the explicit reason; the safety refusal remains enforced. Raw
failures are retained in the temporary logs, not relabeled as passing runs.

## Browser and download evidence

Existing Playwright connector, local Chromium at 127.0.0.1:8768. No framework install.
Prima/provider configuration was unavailable; the existing connector was reused.

- `tests/browser/text-boxes.js`: 12 pages, no upload on open, multiline/wrapping,
  Serif/bold/custom color/center alignment/line and paragraph spacing, actual PDF
  preview, unchanged Cancel download/history, Apply without another request, font
  growth/right alignment/edit/removal and Undo/Redo.
- `tests/browser/text-boxes-safety.js`: occupied-content refusal, explicit transparent
  overlap, numeric overflow facts, explicit expand-to-fit and late-response Cancel.
- `tests/browser/text-boxes-mixed.js`: insert blank page, project box onto page2,
  rotate/refuse unsupported box-layout editing/Undo rotation, change original title,
  redirect a managed source run, insert image, edit box, retain source/title/image,
  and edit the managed image after the native rewrite.
- `tests/browser/text-boxes-geometry.js`: cropped/90-degree/UserUnit2 page supports
  new upright editable text; 760/320/1280px body widths stay within the viewport,
  with 403/310.5/439px usable stage heights. The SHA256 of the actual downloaded
  candidate matches the server-prepared preview, with no second write.
- `tools/verify_text_box_downloads.py`: actual inserted/updated/removed/mixed files
  pass qpdf and strict pdfcpu; 48 exact pixel comparisons outside allowed edits,
  12/13-page counts, original image bytes and URI annotation unchanged. Canceled
  output is byte-identical. Removal restores source rendering on all12pages.
- Additional actual rotated download: qpdf/strict pdfcpu pass, new text searchable,
  verified physical rectangle400/300/300/120pt, original pixels unchanged outside
  that rectangle. Exact candidate/download SHA256 was
  `035d6442707661153f3d82a1ae6fdebb3f2568cdd91845291b407cd33f331e0d`.

Screenshots were inspected: exact native text aligns inside the selected rectangle;
the active draft/preview is scrolled into view after toolbar layout changes.
The historical side-tab design-hook finding has no thick colored card edge in the
current stylesheet. No suppression was added; the thin header separator remains.

Temporary raw evidence: `/private/tmp/pdf-tool-text-boxes-20261029/` and
`/private/tmp/text-box-{python-full,python-final,final-focused,client-full,types-full,export-gates,final-build,downloads,license,client-license,client-license-tests,unicode}.log`.
These local files are not persistent document storage or committed user content.

## Reproduction and changed modules

Run the existing README local build/start instructions. Choose Insert text, click
blank space, type multiple paragraphs, Preview, then Apply. Load inserted text boxes
to edit/remove a saved box. Undo/Redo includes text/page/image operations.

```sh
.venv/bin/python tools/build_text_box_fixtures.py /private/tmp/pdf-tool-text-boxes-20261029
npm --prefix client test
.venv/bin/python -m pytest -q tests/test_text_boxes.py tests/test_text_box_api.py tests/test_recipe.py
.venv/bin/python -m mypy engine server
npm --prefix client run build
# Run browser function expressions in order: text-boxes, safety, mixed, geometry.
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python tools/verify_text_box_downloads.py
# Optional second argument after fixture directory: candidateSha256 returned by geometry script.
```

Engine: `engine/text_boxes.py`, guarded `engine/recipe.py`.
API: `server/app.py`, `server/worker.py`, `server/errors.py`.
Client: `client/src/textBoxes/*`, `App.jsx`, `session.mjs`, test script.
Evidence: focused Python/client tests, four browser scripts, fixture/download tools,
design/plan, README and planning state.

## Remaining limits

Original arbitrary PDF paragraphs still have no reliable layout structure: source
multiline/reflow/growth, automatic neighbor movement and continuation onto another
page remain unavailable. Inserted containers support those bounded multiline/size/
spacing operations only within a chosen page rectangle; no text is silently lost.
Only bundled Liberation Sans/Serif/Mono variants are offered for new boxes; missing
glyphs/unsupported complex shaping/RTL/control text refuse. No arbitrary font upload.
Existing boxes rotated relative to the current page require rotating back for layout
editing; list/removal and creating upright new boxes still work. Forged/modified
ownership or changed resources refuse safely. Removal is not certified redaction.
Find/replace uses source-run rules and cannot batch-rewrite a managed container's
individual glyph runs; use its complete layout editor. Unowned original images,
document outline/history panels and exact substring glyph highlighting remain future
work. Safari/Firefox were not rerun for these new controls; prior viewer evidence
does not imply new cross-browser verification. Large real-world new-box corpus and
Word/Acrobat visual observations remain unperformed.

Earlier Linux/container/live-CDN, literal contract specimen, hosted G7a CI and
production HEIC confinement gates remain open. No deployment or container setup.
