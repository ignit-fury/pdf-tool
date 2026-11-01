# Auto-save and push-down — verification (2026-11-01)

Plan: `docs/superpowers/plans/2026-11-01-auto-save-push-down.md`. All checks below ran locally. Nothing was pushed.

## Automated

| Check | Command | Result |
|---|---|---|
| Engine and server | `uv run python -m pytest tests/test_push_down.py tests/test_paragraph_edit.py tests/test_paragraphs.py tests/test_source_text_box.py tests/test_text_boxes.py tests/test_text_box_api.py tests/test_worker.py tests/test_harness_baseline.py -q -m "not perf"` | 205 passed; 210 after final fixes |
| Types | `uv run python -m mypy engine/ server/` | No issues (43 files) |
| Client | `npm test` (client/) | 222 pass, 0 fail (after final fixes) |
| Build | `npm run build` (client/) | OK |

**Corpus acceptance:** `push_down` on page 0 of each `corpus/public` file, with the cut placed in a gap between text lines.

- 72 of 217 pages moved: 67 pixel-exact and 5 within 1.3e-4 pt. There were no wrong moves.
- The rest refused with a stated reason:
  - content crossing the cut: 112
  - unsupported constructs: 20
  - page full: 4
  - no text gap to cut at: 9

## Browser walkthrough

The app ran on its own ports (API 8004, client 5177) and used a one-page, single-column test document: a heading, a two-line paragraph, then two more sections.

1. Opened the document, chose Edit text, then Analyze text. Six paragraph outlines appeared.
2. **Small edit that fits** (the last character of "address mapping." changed to "!"), then a click away:
   - The app showed "Paragraph saved."
   - The new text was extracted correctly.
   - The content below did not move: "Learning Outcomes" stayed at 310 and "5.1 Basic Concept" at 390.
3. **Long edit** (a sentence appended to the first paragraph), then a click away. There was no prompt.
   - The paragraph wrapped to four lines.
   - The app showed "Paragraph saved; content below moved down."
   - The headings below moved down by 31px (310→341 and 390→421).
4. **Undo:**
   - The original sentence came back.
   - The headings returned to exactly 310 and 390.
   - Redo became available.

5. **Output check:** the same long edit was run directly through the engine (`prepare_paragraph_edit`) after the final fixes.
   - The plan was `rebuild`, with `pushed` = 26.89pt.
   - `qpdf --check` on the output reported "No syntax or stream encoding errors found".
   - The source file was byte-identical afterwards.

An earlier Undo attempt looked broken. That happened because Vite hot-reloaded the app in the middle of the session, which resets in-memory history. It is a development-server artefact, and Undo worked on a fresh load.

## Performance

With 26 native text boxes below the edited paragraph, a push takes 2.4–2.5 s of CPU. Before the final fix it took 13.6 s, against the 20 s worker limit. This is covered by a `perf`-marked test.

## Known limits

- Text that gets shorter does not pull the content below back up.
- Text never flows onto the next page. If there isn't enough room, the edit is refused with the message "Not enough room on this page".
- Multi-column pages refuse a growing edit. Edits that fit still save.
- A paragraph whose text sits more than 2pt outside the visible page edge is refused rather than clamped.
- Bookmarks and link destinations that point at moved content are not moved.
- A rebuilt paragraph uses a bundled Liberation font. Documents set in fonts such as Carlito will show a slightly different face for that paragraph.
