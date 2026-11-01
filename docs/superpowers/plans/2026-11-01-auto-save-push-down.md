# Auto-save and Push-down Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Paragraph edits save on their own, with no "does not fit" prompt. When a rebuilt paragraph needs more height, the content below it on the same page moves down, the way it does in a word processor.

**User decisions (2026-11-01):**
- Scope is "auto-save + push down": no flowing onto the next page.
- Simple pages only. Complex pages refuse with a clear reason.
- The project rule changed. It is recorded in `CLAUDE.md` and `.planning/PROJECT.md` under **Editing fidelity**.

**Architecture:**
- A new pure-engine module, `engine/push_down.py`, translates every top-level drawing item that lies entirely below a cut line. It wraps each item in a `cm` / inverse-`cm` pair, so items are moved but never redrawn.
- The paragraph rebuild path (`engine/paragraph_edit.py` → `engine/source_text_box.py`) calls it when the rebuilt box needs more height than the original paragraph had.
- The client always commits with `allow_rebuild: true`.

**Spike result (validated before planning):** `/private/tmp/claude-501/-Users-prempatel-Pictures-pdf-tool/56309e34-15c2-4a51-880f-849eccda7aae/scratchpad/spike_shift.py`
- On the export fixture, items below the cut moved by exactly `dy`, the content above was byte-for-byte unchanged in the render, and a cut through the right column was refused.
- On `far_federal_acquisition_regulation.pdf`, the region above the cut was pixel-identical and the region below matched the original shifted by `dy`.
- Most real pages were refused only because one `BT…ET` block spans the whole page. That is what Task 1's line-level split fixes.

## Global Constraints

- Content-stream editing only. No white-box overlays. No silent clipping. Never redraw or re-encode existing content when moving it: translate only.
- Moving content must leave everything above the cut pixel-identical (same-engine render) and everything below identical up to the translation.
- Every refusal is atomic: the current PDF bytes and history are unchanged, and the user sees a stated reason.
- One successful commit equals exactly one Undo/Redo entry.
- No reflow across pages. No new dependencies. No AGPL.
- Existing worker isolation, 20 s CPU limit, stream limits, collision checks and signature acknowledgement stay unchanged.
- Python tests run with `uv run python -m pytest` (plain `uv run pytest` hits a system pytest). Client tests run with `npm test` in `client/`.
- Commit messages are conventional and end with a `Co-Authored-By:` trailer. Never stage files you did not change. Never `git add -A`.

---

### Task 1: `engine/push_down.py` — translate content below a cut

**Files:** create `engine/push_down.py` and `tests/test_push_down.py`.

**Interface:**
```python
class PushDownRefused(ValueError):
    code: str   # 'PUSH_DOWN_STRADDLE' | 'PUSH_DOWN_PAGE_FULL' | 'PUSH_DOWN_MANAGED_IMAGE'
                # | 'PUSH_DOWN_UNSUPPORTED' (clip text, marked content split, unbalanced q/Q, parse failure)
def push_down(pdf: pikepdf.Pdf, page_index: int, y_cut: float, dy: float, *,
              keep: Callable[[str], bool] = lambda _: False) -> int
    """Translate every top-level drawing item whose top lies at or below `y_cut`
    (default user space, PDF y-up) down by `dy` points. Mutates the page in place and
    returns the number of moved items. Raises PushDownRefused without mutating anything."""
```

**Rules (from the spike):**
- **Content:** coalesce `/Contents` arrays first. Parse with `pikepdf.parse_content_stream`. Track the CTM through `q`, `Q` and `cm`.
- **Items:** an item is one of the following:
  - a path from construction through its paint operator;
  - a `Do`;
  - an inline image `BI…EI`;
  - a text line inside `BT…ET`.
  A text line is one positioning operator (`Td`, `TD`, `Tm`, `T*`, `'`, `"`), or the start of the block, plus the text-showing operators that follow it until the next positioning operator.
- **Item extent:**
  - Paths: transformed coordinates.
  - `Do`: the CTM applied to the unit square for images. For forms, the CTM × form `/Matrix` applied to `/BBox`.
  - Text lines: baseline y from `Tm`×CTM, from −0.25·size to +1.0·size. Use the effective vertical scale.
- **Moving a non-text item:** insert `X cm` before it and `X⁻¹ cm` after it, where `X = CTM·T(0,−dy)·CTM⁻¹`. This is what `spike_shift.py` does. It keeps graphics state intact, with no `q`/`Q` reset.
- **Moving text lines:** close the text object and reopen it around each group of consecutive moving lines:
  - Before the group: `ET`, then `X cm`, `BT`, then `<tlm> Tm` (the text line matrix in effect just before the group).
  - After the group: `ET`, then `X⁻¹ cm`, `BT`, then `<tlm> Tm`.
  - Text state (`Tf`, `Tc`, `Tw`, `Tz`, `TL`, `Ts`, `Tr`) survives `ET`/`BT`, so only `Tm` needs restoring.
  - Refuse with `PUSH_DOWN_UNSUPPORTED` if a split point falls inside an open `BDC`/`BMC` sequence, or if text render mode ≥ 4 (clipping) is active in that block.
- **Classification:**
  - An item entirely below the cut (`top ≤ y_cut`) moves.
  - An item entirely above stays.
  - A background item stays: it spans more than 80% of the page height and also covers the cut, such as a page-filling rectangle or a full-height column rule.
  - Anything else that crosses the cut raises `PUSH_DOWN_STRADDLE`.
- **Annotations:** any annotation whose `/Rect` lies fully below the cut has its `/Rect` translated by `−dy`. One that crosses the cut raises `PUSH_DOWN_STRADDLE`.
- **Page full:** if any moved item's new bottom is below the cropbox bottom, raise `PUSH_DOWN_PAGE_FULL`.
- **Managed content:**
  - Managed images (`engine/image_index.py` / the managed image marker) below the cut raise `PUSH_DOWN_MANAGED_IMAGE`.
  - Native text box parts (`engine/text_boxes.py` owned streams) are not moved by this module. Leave them in place and report their ids through the `keep` callback, so the caller can move them by re-upserting (Task 2).
- **Atomicity:** compute every change first, then apply. Never leave a partially mutated page.

**Tests (TDD):**
- Export fixture (`tools/build_export_fixtures.py`):
  - A cut at y=470 with dy=40 moves "Bold body", "Italic body" and "- First item" by exactly 40 (pdfium text rects).
  - The heading and both columns are unchanged.
  - A cut at 495 raises `PUSH_DOWN_STRADDLE`.
- A single `BT` block spanning several lines, with a cut between lines: only the lower lines move, and pdfium extracts the same text.
- A `BDC` spanning the split point raises `PUSH_DOWN_UNSUPPORTED`.
- `dy` too large raises `PUSH_DOWN_PAGE_FULL`, and the page bytes are unchanged.
- A link annotation below the cut moves with its text.
- Real corpus pages, rendered with pdfium at the same scale:
  - Above the cut is pixel-identical.
  - The region below, shifted by `dy`, matches the original.
  - Use `far_federal_acquisition_regulation.pdf` and at least two `govdocs1_*` pages that become movable after the line split (the spike shows `govdocs1_000_000009.pdf` and `govdocs1_000_000013.pdf` failing only on whole-page `BT` blocks).
- `qpdf --check` passes on every output.
- Report the corpus acceptance rate. For page 0 of each `corpus/public` file, with the cut at the middle of a gap between text lines, record moved vs refused per reason. This is a script result in the report, not a test.

### Task 2: Use push-down in the paragraph rebuild

**Files:** modify `engine/paragraph_edit.py`, `engine/source_text_box.py` and `engine/text_boxes.py` (only if a helper is needed), plus their tests.

**Behaviour:**
- `allow_rebuild` stays in the payload for compatibility, but the server treats the rebuild as always allowed. `PARAGRAPH_NEEDS_REBUILD` is no longer raised.
- **Rebuild height:** the rebuilt box gets the paragraph's rect. If the wrapped text needs more height (layout `required_height`), or the box would collide with content below (`TEXT_BOX_OVERLAP`), compute `dy = required_height − rect.height`, plus one line gap if the collision persists. Then:
  1. On the intermediate PDF (with the source runs already removed), call `push_down(pdf, page, y_cut=<paragraph bottom in PDF y-up user space>, dy)`.
  2. Native text boxes reported below the cut are re-upserted with their `rect.top` increased by `dy`, using `prepare_text_box`, so ownership proofs stay valid.
  3. Insert the rebuilt box with the needed height.
- When the text gets shorter, nothing moves up. That is a known limit, stated in the report.
- **Errors:** map `PushDownRefused` codes to `TextBoxError` codes. Add them to `engine/text_boxes.py` `ERROR_CODES` and `server/errors.py` `TEXT_BOX_ERROR_CODES`. Messages:
  - `PUSH_DOWN_PAGE_FULL`: "Not enough room on this page."
  - `PUSH_DOWN_STRADDLE`: "Content beside this paragraph can't be moved."
  - `PUSH_DOWN_MANAGED_IMAGE`: "An inserted image below would have to move."
  - `PUSH_DOWN_UNSUPPORTED`: "This page's layout can't be moved safely."
- **Tests:**
  - On a two-paragraph fixture (paragraph + "Keep neighbor" below), a long edit rebuilds, "Keep neighbor" moves down by the extra height, and the text is intact.
  - A page-full case refuses, and the source bytes are unchanged.
  - The line plan is still used when the edit fits.
  - Existing tests are updated where they asserted `PARAGRAPH_NEEDS_REBUILD`.

### Task 3: Client auto-save

**Files:** modify `client/src/viewer/paragraphs.mjs` (`paragraphPayload` always sends `allow_rebuild:true`), `client/src/App.jsx` (`commitParagraph`) and `client/src/viewer/InlineEditor.jsx` (`TextToolbar`), plus `client/src/session.mjs` (`explainTextBoxError` messages).

**Behaviour:**
- Remove the "does not fit" message and the **Rebuild as text box** button.
- A refusal shows its stated reason (the four codes above) with **Revert**.
- Success messages:
  - Line plan: "Paragraph saved."
  - Rebuild without push: "Paragraph saved as wrapped text."
  - Rebuild with push: "Paragraph saved; content below moved down."
- Update the client tests that assert `allow_rebuild:false` or the rebuild button.

### Task 4: Verify end to end

- Run the full Python and client suites.
- Browser walkthrough on a corpus-like page:
  1. Type a long sentence into a body paragraph and click away.
  2. The content below moves down, with no prompt.
  3. Undo restores the original.
  4. Download and check with `qpdf --check`.
- Write evidence to `docs/verification/auto-save-push-down-2026-11-01.md`.
