# Document viewer editing design

## Intent and constraints

Implement the user's 2026-10-29 editor upgrade incrementally in this repository.
The document becomes the editing surface: continuous pages, inline text input,
contextual formatting, image handles, find-one/all and a truthful results tour.
Preserve React/PDF.js/FastAPI, the authoritative run index/content-stream recipe,
original-byte retention, isolated workers, CSP, memory limits and license policy.
No deployment or new dependency is authorized or needed.

## Existing architecture

`App.jsx` owns browser sessions, exact-byte mixed-history snapshots, server cache
recovery, page-worker transactions, search and exports. `Viewer.jsx` renders one
PDF.js canvas/text layer and overlays server-issued run boxes. The inspector is
currently the only input surface. Text recipes replay against immutable analyzed
source bytes; page operations materialize current bytes and invalidate analysis.
`engine/recipe.py`, `rewrite.py` and `fit.py` jointly validate shape, pen position,
ink bounds and atomically publish. Size changes currently refuse unconditionally.
`pageOps/images.mjs` validates/decodes images locally and appends native image
content. History contains only Undo, not Redo. Search already has Unicode matching,
complete-index validation, individual exclusions and an atomic whole-recipe apply.

## Approach

Extend existing components rather than replace the editor or introduce a second
PDF rewriting engine. Rendering every page eagerly would exhaust canvas memory;
use stable page shells with near-viewport canvas/text-layer mounting. PDF.js text
remains for reading/copying. Editing targets use only authoritative server boxes
and IDs; PDF.js text is never used to invent an engine address.

A positioned native textarea is the temporary inline input, with a contextual
toolbar above the document. Editing exposes source formatting, local draft preview
and explicit server validation. The input is an editing affordance, never a white
rectangle written into exported PDF bytes. Successful application rerenders real
PDF output and closes the draft. Unsupported runs stay selectable with a reason.

Keep preserve-layout as the default. Longer/shorter text and insertion within a
run use existing width validation; supported size/spacing changes must restore
following text state and pass native ink/position checks. Flexible arbitrary-PDF
reflow is unavailable unless a reliable block ownership/obstacle model exists.
Line/paragraph alignment, wrapping and moving neighboring source content must
explicitly refuse instead of clipping or claiming unsupported reconstruction.

New images remain real native PDF image objects. Manage only placements whose
isolated owned content stream can be verified; never delete an arbitrary source
XObject shared by other content. Existing unowned images remain preserved and
uneditable with a clear limitation. Managed image move/resize/replace/delete
uses browser page-worker transactions and the same bounded history.

Undo/Redo stores exact snapshots, with both stacks included in admission limits;
new mutations clear Redo. History restoration never uploads automatically.
Replace One builds a one-occurrence candidate through the same complete-index
and server validation as Replace All. A post-commit walkthrough only highlights
actual accepted occurrences in the final output; pause/stop changes presentation,
not the already committed atomic transaction. Respect reduced motion.

## Interface

Quiet document chrome: existing dark ink `#213b5c`, white paper `#ffffff`, cool
workspace `#e3e8ef`, rules `#d4dce8`, existing blue action `#2458df`. Native system
UI type and source PDF typography. Top actions remain visible; contextual tools
wrap at narrow widths. Optional panels hold page operations/search/exports rather
than ordinary text input. No decorative cards, gradients or added font downloads.
Keyboard focus follows selection, apply/cancel, page navigation and result tours.

## Verification and limits

Test viewport transforms, bounded rendering, stale selection, snapshot budgets,
single-occurrence recipes, walkthrough state and image ownership. Test actual
PDF bytes for changed searchable text and unchanged neighboring content. Exercise
continuous scroll, inline edit, validation/refusal, formatting, history, images,
search/tour, exports and narrow/zoomed layouts through the local browser connector.
Keep full Python/client regressions, strict typing, build and license gates.
Existing release gates and no-deployment instruction remain unchanged.
