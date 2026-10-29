# Precise search highlights

Next slice of the user's existing viewer objective, after local Outline/History.
Keep the current architecture, source-run addresses, atomic recipes, memory-only
documents, original bytes and no-deployment constraint. No dependencies or backend
changes. Execute the user's existing plan-then-build instruction without another
approval round; implementation choices here are ours.

Use the actual rendered PDF.js text layer. Match the current effective full run
through existing canonical Unicode projection, map its selected UTF16 span back to
DOM text nodes, and measure Range rectangles. Source run geometry disambiguates
repeated text. More than one plausible candidate, missing text or unsupported mapping
produces a clearly labeled approximate original text-area highlight. Never guess a
different occurrence or change the PDF to draw a highlight.

Show one active occurrence at a time, including multiple occurrences within one run,
split text nodes, Unicode normalization, zoom and page rotation/crop/UserUnit. Range
rectangles follow the text layer; they are not exact glyph-ink contours. Mapping is
bounded to100000 visible UTF16 units,10000 text nodes,64 candidates/rectangles and
20000 source-run UTF16 units. Decomposition expansion and combining sequences
are preflighted; at most64 consecutive non-starter marks are projected. Missing/degraded mappings remain navigable and explicit.

Replacement review retains committed output offsets for each included occurrence.
The already-applied batch walkthrough highlights those output characters. Deletions
show a labeled original location, never pretend removed text still exists. Timed
advance waits for the current result to render; pause/resume/next/stop/reduced motion
and one-step batch Undo retain their behavior. No extra destructive rewrite or upload.

Rendering is bound to PDF proxy, scale, target identity/range and completed text layer.
Late work after query/navigation/close/source change cannot show stale rectangles.
Highlights are temporary pointer-transparent viewer elements, never annotations or
exported content. New source paragraphs/reflow, cross-run search, managed-text-box
batch rewriting, foreign images and prior release gates remain out of scope.
