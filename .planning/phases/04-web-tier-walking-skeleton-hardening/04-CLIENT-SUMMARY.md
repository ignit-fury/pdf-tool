# Phase 4 browser editor

Implemented the React workstation with pdf.js canvas rendering and a separate native
text layer; editing uses server-issued PDF-space boxes transformed by the viewport.
Progressive thumbnails request classification through a two-worker queue, prioritize
the selected page, retry busy workers with bounded backoff and cancel stale sessions.

The browser retains immutable source bytes, password and whole-recipe undo snapshots
in memory. Cache eviction reuploads the original once. Repeated edits upsert an original
run address. Text, colour and face changes undo together. Signature acknowledgement,
password prompt, named refusal fallback and explicit local/server action labels are present.
The OCR guide and anonymous interest counter are separate actions.

pdf.js CMaps/fonts/decoder WASM are served locally. The production build succeeds;
the ten dependency-free session regression tests pass. Actual browser verification
in Safari and Firefox caught and fixed pdf.js 6 disposal through `loadingTask.destroy()`.
A bold edit/download exposed unsafe positive inter-word kern absorption; the engine now
uses the bounded Tz rung or refusal while preserving readable word spaces and Unicode.
The corrected downloaded PDF opened in Firefox, re-extracted as `Hallo world`, and passed
`qpdf --check`. Cmd+Z restored original text and removed the edited-download state.

No external document upload, account, persistent browser storage or built-in OCR was added.
Final review added UTF-8/base64 password transport to preserve Unicode and edge whitespace;
plain header encoding had rejected otherwise valid protected PDFs. Named copy explains
the engine's safe refusals for stateful quote operators and unsupported shaping mappings.
