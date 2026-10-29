# Compact viewer toolbars

User-reported problem: navigation/formatting consumes half the screen.
Before on a 1,000px-high desktop viewport: header 72px, document actions 121px,
viewer navigation 66px, formatting 295px; PDF viewport 353px.

Implementation direction: preserve existing visual identity and every operation;
compact the three persistent rows, keep common editing/actions directly accessible,
and move layout/spacing/reference prose into keyboard-accessible anchored disclosures.
Disclosures overlay rather than shrink the PDF. Critical errors/status remain visible.
Mobile uses a native tool picker, 44px control heights and independently scrolling action rows.
No backend/engine/dependency/deployment changes. Verification results recorded below.

## Verified result

| Viewport | PDF reading area | PDF editing area | Formatting height |
| --- | ---: | ---: | ---: |
| 1280 × 1000 | 823px | 728px | 96px |
| 760 × 900 | — | 529px | 169px |
| 390 × 900 | — | 529px | 169px |
| 320 × 900 | — | 510px | 169px |

Browser inspection confirmed no document-level horizontal overflow at these sizes.
The PDF itself remains independently scrollable at the selected zoom. Download stays
visible while secondary actions scroll horizontally. Mobile formatting and primary
actions also scroll horizontally to retain readable controls. Layout & spacing and
Edit details overlay the page without reducing its scroll area; Escape/Done restore
focus. Important errors, fit results, and signature/preview notices remain visible.

Changed modules: App chrome; shared ToolbarDetails; compactChrome stylesheet;
InlineEditor, ImageEditor and TextBoxEditor toolbar composition. Existing handlers,
edit identifiers, PDF engine and immutable history are unchanged. Font and upload
explanations remain available through Edit details and existing description IDs.

## Checks

- Production Vite build: passed; existing large-chunk advisory remains.
- Client automated suite: 197 passed, 0 failed.
- `tests/browser/compact-toolbars.js`: passed, including desktop/mobile geometry,
  popup bounds, keyboard focus, native PDF preview, Apply/Undo/Redo, tool selection
  and page navigation. Screenshots inspected at desktop, 390px and 320px widths.
- `tests/browser/source-expansion.js`: passed; updated to open disclosed controls
  and use explicit hidden-input locators for read-only assertions. Verifies original
  removal, retained prior recipe, cancellation, history, collision refusal and growth.
- `tools/verify_source_expansion_downloads.py`: passed, 3 byte-identity checks,
  4 structural validations (qpdf/pdfcpu), 24 unrelated-page pixel comparisons.
- Impeccable final detector for changed UI: `[]`; no suppressions or standing findings.
- `git diff --check`: passed.

The fast responsive test can encounter existing `429 WORKER_BUSY` admission while
canceled background analysis workers drain after resizing. The test retries only that
response, bounded to four attempts with the server's one-second admission delay.
This does not relax production isolation or resource limits. No backend fix is claimed.

Run `npm --prefix client test` and `npm --prefix client run build`. The local server
at `http://127.0.0.1:8768/` serves the updated build. Browser scripts use the 12-page
fixture at `/private/tmp/pdf-tool-source-expansion-20261029/source.pdf`; see
`tools/build_text_box_fixtures.py` to regenerate it. No deployment was performed.
