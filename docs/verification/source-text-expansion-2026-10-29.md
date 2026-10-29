# Original source text expansion — verified fix

2026-10-29; baseline `e8bc3f4`, existing `feat/document-viewer-editor` branch.

The reported warning was real: multiline expansion existed for inserted containers,
while selected original runs still used only the one-line preserve-layout path.
This fix connects original editing to the managed native layout engine.

## Delivered behavior

- Type/paste line breaks in supported original text and the draft moves directly to
  a flexible text box. Text, selection/caret, physical font size/color/style and all
  committed recipe edits are retained. An explicit Expand text box button and
  enabled Flexible layout choice also support longer single-line drafts/font growth.
- The typing surface grows immediately; PDF preview computes actual font layout and
  expands height when enabled. Grown candidate metadata updates the displayed bounds.
  Existing managed boxes also default to automatic height growth when selected.
  Disable Grow height to fit for the existing explicit overflow/manual-expand path.
- The combined candidate first removes the selected original text through the guarded
  recipe writer, then inserts genuine native wrapped text. Both happen privately in
  the disposable worker; no intermediate PDF is published. No white rectangle or text
  annotation covers the original. Apply publishes the exact preview bytes once and
  adds one mixed-history action. Cancel/failed fit/collision preserve current bytes.
- Nearby source content remains fixed. Grown bounds are checked against actual rendered
  content, annotations and the page boundary. Overflow never clips committed text.
  Users can adjust width/position/size or target another page when space is insufficient.
- Flexible layout uses the selected Liberation family; the original font and replacement
  are disclosed. Pasted tabs become four spaces; CRLF/paragraph separators become line
  breaks. Literal Tab keeps ordinary accessible focus navigation.

## Source identity and architecture

`replace-source` is a finite operation on the existing text-box route. The server-issued
run ID is resolved against immutable source bytes. The complete committed recipe is
replayed with the selected run replaced by empty text, then the existing native box
writer lays out the replacement. Unsafe source instructions and managed glyph streams
remain protected by the existing engine's rewrite/ownership checks.

The preview controller uploads the source baseline for this operation, rather than
trying old edit IDs against materialized working bytes. Its cache key includes the
actual upload-source reference. Publication remains bound to the current session,
working bytes, version and exact payload. Admission counts the larger original upload
before any network request. Normal inserted-box operations continue to use current
materialized bytes. Cache-loss retry, Unicode passwords, signature acknowledgement,
fixed notices, original-byte retention and bounded disposable processing are retained.

New trusted code imports finish before worker confinement. Limits remain source50MiB,
candidate48MiB, request1MiB, text10000 characters, boxes200/pages2000 and existing
memory/CPU/deadline/history bounds. No runtime dependency, migration, persistent document
storage, deployment or security-limit change.

## Verification

| Check | Observed result |
|---|---|
| Complete selected Python regression, excluding corpus/Linux/CDN markers | **875 passed**,39 deselected,2 existing warnings,176.89s |
| Existing G6/G7a/DOCX-removal gates | **12 passed**,44.25s |
| Full client after the page-tracking integration fix | **197 passed** |
| Strict engine/server mypy | **40 files**, no issues |
| Production build | Passed; existing chunk-size advisory |
| Python/client runtime license closures | Passed; no dependencies/lockfile changes |
| Client license controls / Unicode data | **19 passed** / Unicode15.1.0 current |
| New actual source-expansion browser journey | Passed |
| New actual PDF downloads | **3 byte identities**, **4 qpdf/strict-pdfcpu validations**, **24 exact unrelated-pixel comparisons** |
| Existing browser regressions | Inline/image/Find, four text-box, three navigation and two highlight journeys passed |
| Existing download regressions | Viewer/text-box/navigation/highlight native verifiers passed |

The backend run includes the final native/API changes. The later integration correction
affects only client current-page tracking; the client suite/build and affected actual
browser flows were rerun after it. No new full217-PDF audit, Linux/container/CDN run,
Safari/Firefox pass or Word/Acrobat observation is claimed.

`tests/browser/source-expansion.js` first applies an ordinary neighboring source edit.
It then types two lines in the original title, verifies automatic transition and visual
growth, previews real source removal plus the prior edit, cancels and downloads identical
working bytes. Repeating and applying makes no second rewrite. One Undo restores the
exact previous source/recipe state; Redo restores the exact expanded PDF. Adding a third
line correctly refuses collision with existing text; moving into free space permits
automatic subsequent growth. Source, image and URI-annotation content outside edited
areas remain unchanged. `tools/verify_source_expansion_downloads.py` checks the downloads.

Native/API tests independently verify prior recipe retention, source-hash binding,
genuine searchable source removal, unsafe IDs/collisions, existing managed-box ownership,
Unicode password transport and signature acknowledgement/notices. Controller/model tests
cover original-source versus current-byte binding, resource admission and normalized text.

One fresh read-only review found no Important/Critical defects; its49 focused native
tests passed. The Tab-key observation is intentional accessible behavior, with pasted
tabs explicitly normalized. No blocking review findings remain.

An integration regression was reproduced: closing an auto-sized draft exposed the next
page, and the old nearest-page-top heuristic could select it despite the prior page
occupying most of the viewport. A RED/GREEN visible-area test and fresh DOM geometry now
keep the largest visible page current; the actual mixed page/image/text-box flow passes.
Old browser expectations were updated to assert the new multiline transition. The
manual-overflow browser case explicitly disables auto-growth, preserving that safety path.

## Files and running

New `engine/source_text_box.py` and its tests compose the existing engine. Native
`text_boxes.py` gains optional `auto_expand` (absent retains prior wire behavior).
Worker/error wiring, text-box controller/model/toolbar, source inline editor/App and
history labels provide the bridge. Current-page tracking uses a tested visible-area
helper. Browser scripts/native verifier, README and planning records carry evidence.

Reload the editor after rebuilding. The local test server on127.0.0.1:8768 was restarted
with the new server error vocabulary. For another running local server, restart it
using the README command, then refresh. Nothing was deployed externally.

```sh
npm --prefix client test
npm --prefix client run build
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest -q tests/test_source_text_box.py tests/test_text_boxes.py tests/test_text_box_api.py
.venv/bin/python -m mypy engine server
# Browser: build_text_box_fixtures into /private/tmp/pdf-tool-source-expansion-20261029,
# then run tests/browser/source-expansion.js with the existing connector.
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python tools/verify_source_expansion_downloads.py
```

Temporary logs `/private/tmp/source-expansion-{full,export-gates,client-final,types-final,build-final,native-final,license,license-tests,client-license,unicode}.log` and
artifacts `/private/tmp/pdf-tool-source-expansion-20261029/` contain synthetic fixtures.

## Remaining limits

This is bounded reconstruction of the selected source run, not automatic reflow of
an arbitrary PDF paragraph or movement of unrelated objects. Multiple neighboring
runs are not silently combined. Occupied space/backgrounds/annotations can require
manual positioning or explicit transparent overlap; page boundaries and missing glyphs/
unsupported shaping still refuse safely. Converted text uses bundled fonts, not every
original embedded font. Rotated/directed source selection retains existing UI restrictions.
Managed-container selection after Apply uses its full layout editor. Search across its
individual glyph runs is still an existing cross-run-search limitation. Removal is not
certified forensic redaction. Earlier external release/HEIC/contract/hosted-CI gates remain.
