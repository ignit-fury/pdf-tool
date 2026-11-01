# Sejda-style inline paragraph editing: verification, 2026-10-31

Branch `feat/document-viewer-editor`, HEAD f2675d5 plus the uncommitted working tree.
Fixture: `build_export_fixture()` from `tools/build_export_fixtures.py` (3 pages, page 1 has "Left first / Left second").

## 1. Automated suites

| Suite | Command | Result |
|---|---|---|
| Python | `uv run python -m pytest -q` | 964 passed, 6 skipped, 6 failed (see below) |
| Client | `cd client && npm test` | 220 tests, 220 pass, 0 fail |
| Build | `cd client && npm run build` | succeeds (chunk-size warning only) |

The six Python failures, none touching paragraph editing:

- `test_docx_cuttable.py::test_every_other_export_gate_without_docx`, `test_gate_g7a.py::test_full_frozen_g7a`, `test_gate_g7a.py::test_supplemental_font_branch_and_limit_boundaries`: need an authenticated veraPDF (`VERAPDF_CMD` unset here, e.g. "G7a requires authenticated VERAPDF_CMD"). Environment, not code.
- `test_find_replace_performance.py::test_40page_batch_worker_preview`, `::test_40page_batch_worker_apply`, `test_gate_g4.py::test_g4_full_40page_batch_text_and_all_renderer_pages`: `{'error': 'WORKER_FAILED'}`, the child-CPU limit failure recorded in `.planning/audits/corpus-compatibility-2026-10-30.md`. The full run overlapped with the Vite build, a server and a browser. Rerun alone, the same three tests passed (3 passed, 150 s). So they are load-sensitive, as the audit baseline already says, not regressions.

## 2. Browser journey

Own API on port 8002 and Vite on port 5175, proxied via a temporary config (deleted afterwards). Driven with Playwright against `fixture.pdf`.

| Step | Result |
|---|---|
| 1. Open, Edit text, Analyze text | Pass. Page 1 reports "Editable text"; paragraph outlines present. |
| 2. Hover the paragraph | Pass. `.paragraph-outline` has a dashed border; a light tint fills the box. |
| 3. Click inside "second", type `!` | Pass. `.paragraph-editor` (contenteditable) opens with the caret in line 2; text reads "Left secon!d". The caret lands one character before the click because glyph widths are treated as even (known shortcut). |
| 4. Click empty space | Pass. "Saving paragraph on the server…", then toast "Paragraph saved. Undo restores the previous PDF."; editor gone; page shows "Left secon!d". |
| 5. Undo, then Redo | Pass. Undo returns "Left second"; Redo returns "Left secon!d". Undo button shows the "paragraph edit" label. |
| 6. Long text, click away | Pass. `POST /jobs/{id}/text-box` returned 422 and the UI shows "This text does not fit the original lines." with **Revert** and **Rebuild as text box**. Esc closed the editor with no request. |
| 6b. Rebuild as text box | Pass for a moderate edit ("Left first and some more words"): paragraph rewrapped in the original width with the toast "Paragraph rebuilt as a text box"; the analyze gate reappeared only briefly and cleared; the next click on the paragraph opened the native text-box editor. |
| 7. Download | Pass. `qpdf --check`: no syntax or stream errors. pdfium text: old "Left first" / "Left second" lines are replaced by the wrapped block; "Export heading", "Right first", "Right second", "Bold body", "Italic body", "- First item" and page 2 ("A1 B1 A2 B2") unchanged. |

Download text for page 1 (rebuilt state): `Export heading | Right first | Right second | Bold body | Italic body | - First item | Left first | and some | more | words Left | second`.

## 3. Observations (not fixed)

1. A very long first-line edit (about 70 characters) hit Rebuild and was refused: "This area contains visible content or an annotation. Move or resize the box, or explicitly allow transparent overlap." The rebuilt box grew into the "Right first" column. The refusal is correct and keeps the draft, but the rebuild offers no way to wrap within the original width.
2. Rebuild joins the paragraph's lines with a space ("words Left second"); original line breaks are not kept.
3. The hover tint appears to hide the underlying page text in the hover screenshot (fill is opaque enough to cover the glyphs). Purely visual.
4. After an edit, the document viewport jumped (scrolled toward page 2 or 3) once or twice during scripted runs, which made coordinate clicks miss. Could not pin down a reliable trigger; likely the first click after commit or focus handling.
5. Playwright `Home` did not move the caret in the editor (caret stayed after the first character). May be an automation artefact; not investigated.
