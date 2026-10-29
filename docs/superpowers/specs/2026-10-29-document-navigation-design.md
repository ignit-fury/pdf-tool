# Document navigation and history

Next slice of the user's existing editor objective, after native inserted text boxes.
The user requested incremental implementation and testing without another approval
round. Implementation choices below are ours; no deployment is authorized.

## Outcome and approach

Add optional Outline and History panels beside the continuous viewer. Use PDF.js's
current committed document for bookmarks and the existing exact-byte timeline for
history. Opening/navigating either panel requires no upload or PDF rewrite.

Alternatives considered: a second PDF parser duplicates authoritative page mapping;
persisted history violates the current memory-only lifecycle; sequential Undo calls
would expose intermediate states and repeat expensive renders. Reuse the existing
PDF.js proxy and prepare/publish lifecycle, with one atomic jump to a retained state.

## Acceptance

- Outline loads current PDF bookmarks locally, displays nested titles with collapse
  controls, and resolves explicit/named internal destinations to actual page numbers.
  Page navigation preserves zoom and focuses the document. Destination coordinates
  and destination-specified zoom are intentionally not applied in this stage.
- No bookmarks, unsupported/external actions, parser failures and truncated trees
  have clear text. Never execute document JavaScript, open URLs or attachments.
  Bounds: 1000 nodes, 16 levels, titles256 characters, destination names2048.
- Late outline/destination responses after close, source replacement, Undo or another
  selection cannot navigate or expose the previous document's outline.
- History lists Original document, applied changes, the current state and undone
  states available to redo. Only committed operations appear. A retained state can
  be restored in one publication; intermediate states are never rendered/uploaded.
- Keyboard Undo/Redo and history jumps share stack/action semantics, exact source
  bytes, recipes, local metadata, page selection, password/cache recovery and existing
  memory admission. Failed/stale preparation changes no bytes or stack entries.
- Successful new edits after a jump clear the abandoned future only on publication.
  No eviction, persistent storage, dependency, engine/API changes or relaxed limits.
- Panels have accessible headings/focus, close controls, responsive scrolling and
  explicit Browser disclosure. Existing thumbnails, Find, page tools, exports, inline
  drafts and native text-box previews continue to coordinate with panel selection.

## Non-goals

Bookmark editing, browser history integration, external links/actions, persisted edit
logs, arbitrary source reflow, foreign image editing and exact substring highlights.
Earlier release gates and the no-deployment constraint stay open.
