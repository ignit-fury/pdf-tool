# Whole-word selection for split PDF initials

The first title in `corpus/public/far_federal_acquisition_regulation.pdf` is
stored as separate `F` and `EDERAL` text instructions (75 pt and 60 pt). The
viewer previously drew a target for each instruction. It now shows one target
for a touching, consecutive initial and letter-only tail on the same baseline.
Clicking that target opens a native text container with the complete word.

The server reclassifies the immutable source and checks that both identifiers
refer to consecutive, editable, horizontal instructions in the same physical
stream with touching glyph positions. It refuses arbitrary pairs. Preview
atomically removes both instructions through the existing guarded recipe writer,
then inserts one searchable text container. Apply uses that exact candidate;
Undo restores the original bytes. Since the two source runs use different sizes,
the user chooses one replacement font and size. The toolbar explains this.

This source has 2,026 pages. The native text-box page bound increased from 2,000
to 2,048 in both engine and client validation. Existing byte, output, memory,
worker, and container-count limits remain. No dependencies or migrations changed.

Verification: browser on the actual 2,026-page file showed one `Edit text:
FEDERAL` target, a full-word text field, a rendered exact PDF preview, one-step
Apply and Undo. Focused Python/API suite passed 42 tests; focused split-source
suite passed 4 after the formatting-only recipe case was added; client suite
passed 198 tests; Vite production build passed. The output passed `qpdf --check`
and strict type checking passed for the two changed engine files. `pdfcpu`
strict mode rejects an outline `/Count` in both the original and output PDFs;
the original file has the same malformed outline count. The change does not
repair the source outline tree.

To verify locally: start the FastAPI app, open that corpus PDF, choose Edit text,
Analyze text, and click the title word. Preview before Apply, then use Undo.
