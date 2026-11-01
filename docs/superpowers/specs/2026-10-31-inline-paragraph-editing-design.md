# Sejda-style inline paragraph editing — design

Date: 2026-10-31. Status: approved in conversation, pending spec review.

## Goal

Make inline text editing feel like the Sejda PDF editor: hover shows editable
paragraphs, a click puts the caret where you clicked inside the paragraph, you
type in place, and clicking away saves. No per-edit Preview fit / Apply step.

Decisions taken with the user:

| Question | Decision |
|---|---|
| Sejda behaviours wanted | Save on click-away (no Preview/Apply), hover outlines, caret at click point, compact floating toolbar |
| When an edit enters the PDF | On click-away (blur/Tab), one Undo entry per paragraph edit. Not batched. |
| Edit unit | Whole paragraph |
| Mixed-style paragraphs | Keep per-line original runs when text fits; rebuild as one style only when wrapping is required, with a toolbar warning |
| Architecture | Server decides: one new `replace-paragraph` operation |

## 1. User experience

- **Hover (Edit mode).** Each editable paragraph shows a faint dashed outline.
  Non-editable paragraphs show a grey outline and a one-line reason tooltip.
- **Click.** The caret lands at the clicked character offset. The paragraph
  becomes a contenteditable area overlaying the page, matching original font,
  size, colour and line positions.
- **Toolbar.** One floating row above the paragraph (existing
  `FloatingTextTools`): font, size −/+, Bold, Italic, colour, delete paragraph,
  and an overflow menu holding character spacing and layout. The long
  guidance texts and Preview fit / Apply / Cancel buttons are removed.
- **Keys.** Esc discards the draft. Click outside or Tab commits.
- **Saving.** Outline pulses while the server works. On success the page
  re-renders from the new bytes. On refusal the editor stays open with a red
  outline, one line of reason, and two actions: Revert, Rebuild as text box.
- **Mixed-style warning.** If commit would need the rebuild plan and the
  paragraph is not single-style, the toolbar shows "Wrapping will make this
  paragraph one style" before the request is sent; the user confirms with a
  second click-away or chooses Revert.

## 2. Paragraph data (server)

`GET /jobs/{id}/pages/{n}/runs` gains a `paragraphs` array. Each entry:

```json
{
  "paragraph_id": "p_<hash of ordered run ids>",
  "box": [x0, y0, x1, y1],
  "lines": [{"run_ids": ["..."], "text": "...", "box": [x0, y0, x1, y1]}],
  "single_style": true,
  "state": "editable" | "not_editable",
  "reason": null | "<existing reason code>"
}
```

- Grouping reuses `engine/blocks.py` line/paragraph logic (the same model the
  text/Markdown/HTML exports use), extracted into a function callable per page
  without building a whole `DocumentBlocks`.
- `paragraph_id` is a hash of its ordered run IDs. Run IDs address the original
  immutable bytes, so paragraph IDs are stable across edits.
- A paragraph is `not_editable` if any member run is `not_editable`, if it is a
  table cell, or if runs span different streams/XObjects. The first failing
  run's reason is reported.

## 3. Commit (server)

New recipe operation sent through the existing `/jobs/{id}/edit` endpoint:

```json
{"operation": "replace-paragraph", "paragraph_id": "...", "run_ids": ["..."],
 "text": "new paragraph text", "style": {}}
```

The server re-derives the paragraph from current bytes and refuses with
`PARAGRAPH_STALE` if `run_ids` no longer form `paragraph_id`. It then tries,
in order:

1. **Per-line plan.** A pure function `split_paragraph_edit(old_lines,
   new_text) -> list[str] | None` maps the edit onto the original lines: the
   common prefix and suffix stay on their lines; the changed middle is
   distributed over the lines it originally covered. Returns `None` if the
   line count must change. Each changed line becomes an existing per-run
   replacement with its original font/style. Mixed styles survive. If every
   line passes the existing width/fit checks, this plan is used.
2. **Rebuild plan.** Otherwise, remove all paragraph source runs and insert one
   flexible wrapped native text box at the paragraph box. This generalises
   `engine/source_text_box.py` `prepare_source_text_box` from one run or the
   two-run initial pair to N runs of one validated paragraph.

Either plan is atomic and passes through the existing guarded writer: neighbour
and annotation collision checks, page bounds, stream limits, 20 s worker CPU
limit. The result is one Undo/Redo entry. Toolbar style changes travel in the
same operation.

## 4. Client changes

- `client/src/viewer/InlineEditor.jsx`: `InlineInput` becomes a contenteditable
  paragraph editor that preserves line positions and maps a click point to a
  caret offset. `TextToolbar` is reduced to the compact row.
- `client/src/App.jsx`: replace `checkFit`/`apply` for inline editing with one
  `commitParagraph()` fired on blur/Tab, reusing snapshot, `requireBudget`,
  `prepareViewer`, `publishViewer` and history. Selection works on paragraphs.
- Hover outlines rendered in the existing `renderOverlay` from `paragraphs`.
- Find/Replace, native text boxes, page ops and exports are unchanged.

## 5. Errors and edge cases

- Existing refusal reasons (rotated/directed text, Type3/symbolic fonts,
  shared Form XObjects, unreadable tables/columns) appear on hover instead of
  after a click.
- Text too long even for the rebuild (would collide with content below) is
  refused; the draft is kept so the user can shorten it.
- Signed PDFs keep the current acknowledgement before the first commit.
- Stale paragraph (bytes changed underneath): refuse `PARAGRAPH_STALE`,
  refetch the page, keep the draft.
- No silent clipping; no white-box overlays.

## 6. Testing

- Engine: paragraph grouping per page; `split_paragraph_edit` table-driven
  cases (prefix/suffix edits, mid-line edits, line-count change → `None`,
  Unicode graphemes); N-run rebuild on corpus fixtures with masked pixel diff
  proving unrelated regions are unchanged; stale-paragraph refusal.
- Client: click-point → caret offset; blur commits, Esc reverts; refusal keeps
  draft.
- Browser journey: hover, click mid-word, type, click away, Undo, download,
  structural validation and byte check.

## Out of scope

Dragging/resizing paragraphs, adding links, reflow into the next paragraph or
page, batch "Apply changes", rotated text editing.
