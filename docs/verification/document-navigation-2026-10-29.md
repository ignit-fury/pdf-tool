# Document navigation and history — local verification

2026-10-29; baseline `83ba6e2`, feature branch `feat/document-viewer-editor`.
Design and plan were saved before implementation. No deployment, dependency,
migration, backend/engine/API change or persistent document storage was introduced.

## Implemented

Outline and History are optional panels beside the continuous document. They reuse
the committed PDF.js proxy and existing exact-byte history; neither rewrites a PDF
or uploads document content to navigate.

The outline renders nested, collapsible bookmarks with plain-text titles. Explicit
and named internal destinations resolve against the current document, including
after page insertion. Navigation keeps the current zoom; destination coordinates and
destination-specified zoom are ignored. No URLs, document scripts, attachments or
other actions are executed. Empty/error/retry states and bounded-tree notices are
explicit. Limits: 1000 nodes, 16 levels, titles of 256 characters, named destinations of 2048.

PDF identity, page/navigation/edit version and a selection token reject late
destinations after newer navigation, draft changes, close, source replacement or
another bookmark. Outline reads also reject stale document results. Opening Outline
or History defers automatic text analysis and stops indexing; explicit Edit text or
Find resumes it. Already requested server work may finish; navigation initiates no
new analysis or cache-recovery upload.

History presents Original document, applied operations, current state and undone
states. A jump moves references through existing one-step transition semantics,
preserving operation labels, source bytes, recipe, metadata and mixed text/page/image
history. One snapshot is prepared/published, rather than rendering intermediate
documents. Existing memory admission occurs before copying/preparation. Failed or
stale preparation publishes no bytes and changes no stack entries. Successful new
edits discard the abandoned future. Keyboard Undo/Redo use the same restoration path.

Opening a panel focuses its heading. Bookmark navigation focuses the document;
restoration returns focus to History and scrolls its current marker into view.
Switching from another panel to Page tools now opens the requested panel correctly.
Current PDF snapshots, original downloads, drafts/previews and optional panels remain
separate. No additional PDF buffers are retained by the history display model.

## Evidence

| Check | Observed result |
|---|---|
| Full client regression | **187 passed**, including 7 new outline/history tests |
| Production Vite build | Passed; existing chunk-size advisory |
| Python/client runtime license closures | Passed, unchanged dependencies/lockfiles |
| Client license negative controls | **19 passed** |
| Search Unicode data | Unicode 15.1.0 current |
| New actual browser journeys | All 3 passed in local Chromium |
| Actual new history downloads | **5 byte-identity checks**, **12 qpdf/strict-pdfcpu validations**, **13 exact unrelated-pixel comparisons** |
| Existing browser regression | Inline source text, image insert/edit/remove, Find One/All/tour, native text-box insert/edit/remove/overflow/cancel/mixed history passed |
| Existing actual-download regression | Viewer6 structural/36 unrelated-pixel and text-box10 structural/49 unrelated-pixel checks passed |

No complete backend suite was rerun for this client-only phase. The prior native
text-box phase's 867 broad/114 final focused Python evidence remains separate; it is
not reported as a new run here. The new native verifier independently checks actual
browser artifacts, source image/link preservation and the remapped named bookmark.

### Browser journeys

`tests/browser/navigation.js` uses a synthetic 12-page bookmarked PDF with nested,
named, external and script destinations. It verifies local navigation/zoom/collapse,
page insertion moving a named destination to page 5, and four committed operations:
blank insertion, rotation, native text insertion, native image placement. Jumping
back to Original prepares exactly one PDF; jumping forward restores the identical
latest bytes. Forced PDF.js preparation failure leaves the state/download unchanged.
Partial jump followed by keyboard Redo preserves the complete latest state. A new
successful edit after a jump clears the undone future. Responsive checks at 760,
320 and 1280px show matching body widths and 663/570.5/606.2px viewer heights. The
screenshot was inspected for hierarchy, current-state visibility and document space.

The script also holds a named-destination RPC, chooses Next page, then releases the
old response; the newer page remains selected. Another held destination released
after opening a different PDF cannot expose the old outline or navigate that PDF.
The browser worker instrumentation is test-only; no production hook was added.

`tests/browser/navigation-cancel.js` holds a multi-state restore preparation and
opens a new PDF before releasing it. The new source keeps empty history, disabled
Undo and an exact source download.

`tests/browser/navigation-privacy.js` explicitly analyzes first, then installs a
SOURCE_MISSING response for uncached page analysis. Navigating through Outline to
page 12 makes **zero server requests**, including zero uploads. Choosing Edit text
then explicitly resumes analysis and obtains that page's editable runs.

The earlier viewer scripts `viewer-inline.js`, `viewer-images.js`, `viewer-find.js`
and `text-boxes.js`, `text-boxes-safety.js`, `text-boxes-mixed.js` all pass against
the updated build. Replacement still performs only two real writes for One plus All;
the tour introduces none. Bounded canvas rendering remains two canvases for 12 pages.

### Findings and corrections

One fresh read-only final review found two Important issues. Both were reproduced
in browser before fixing: a pending bookmark overrode newer navigation; an analyzed
cache miss caused a new page request and source upload. Navigation freshness and
deferred analysis now close both paths, with the complete browser journeys green.
The review's minor copy issue is also corrected to “Only committed edits.” No
review findings are deferred. Browser checks additionally fixed heading focus,
panel-switch behavior, restore-error visibility and focus after restoration.

The initial synthetic fixture declared PDF 1.7 with a minimal Base14 font dictionary,
which strict pdfcpu refused before any editing. The fixture now declares PDF 1.6,
which supports every feature it uses and passes the unchanged strict validator.
No production PDF rewrite or validation policy was changed to mask this failure.
Raw failures remain in temporary evidence. The initial old browser URL 8767 was
unavailable; regressions ran against the existing local server 8768 without deployment.

## Files and reproduction

New client modules: `viewer/outline.mjs`, `OutlinePanel.jsx`, `history.mjs`,
`HistoryPanel.jsx` and their two test files. Integrated in `App.jsx` and
`viewer/viewer.css`. New fixture/download tools and 3 browser scripts accompany the
spec/plan and README/planning updates.

Use the README build/run commands, open a bookmarked PDF and choose Outline. Apply
several page/text/image operations and choose History to jump between saved states.

```sh
npm --prefix client test
npm --prefix client run build
.venv/bin/python tools/build_navigation_fixtures.py
# With the existing browser connector, run navigation.js, navigation-cancel.js,
# then navigation-privacy.js. Scripts default to 127.0.0.1:8768.
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python tools/verify_navigation_downloads.py
```

Temporary evidence: `/private/tmp/pdf-tool-navigation-20261029/`,
`/private/tmp/navigation-{client-final,build-final,native-final,license,license-tests,client-license,unicode,viewer-downloads,text-box-downloads}.log`.
Actual browser source files are synthetic; corpus/user files were not modified.

## Remaining limits

Bookmark editing and external/document actions are unavailable. Outline navigation
uses destination pages only. History exists only for retained in-memory states;
closing/reopening starts a new timeline and does not recover an earlier session.
Automatic arbitrary-source paragraph reflow/height growth, moving neighboring
content, foreign original-image editing and exact substring glyph highlights remain
outside this phase. No new Safari/Firefox, full real-world corpus or Word/Acrobat
observations are claimed. Prior Linux/container/CDN, contract-specimen, hosted G7a
and HEIC confinement release checks remain open. Nothing deployed.
