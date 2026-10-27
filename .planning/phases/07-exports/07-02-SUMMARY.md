---
phase: 07-exports
plan: "02"
subsystem: isolated-native-pdf-and-text-exports
requirements-completed: [EXPO-02, EXPO-04, EXPO-05]
completed: 2026-10-27
---

# Phase 7 Plan 2 — Isolated server exports

Native compression/flattening and all three text formats now export the submitted
current PDF through the existing bounded disposable worker. No source cache entry,
new parser in the request process, new dependency or changed runtime limit is used.

## Contracts and behavior

`POST /exports?operation=compress|flatten|text|markdown|html&downsample=false&acknowledge_signature=false`
accepts raw application/pdf bytes and the existing Unicode-safe password headers.
Only literal true/false options and known single query parameters are accepted.
Response: data(base64), media_type, filename, before_bytes, after_bytes, notices,
changed_images and location=server. Fixed filenames are compressed.pdf, flattened.pdf,
document.txt, document.md, document.html. Text is UTF-8 and uses exactly one RunIndex
through engine.export.text.export_document_result (the same single model as the
public string-returning export_document); HTML is a download, never app markup.

`engine.export.pdf.export_pdf(pdf,source,operation,downsample=False)` returns PdfExport
with data/notices/changed_images. Default structural compression uses native object
streams/Flate recompression and returns exact source bytes when no reduction is achieved.
Explicit lossy reduction only processes safe 8-bit RGB/Gray images, at most 16M pixels,
1600px longest edge, JPEG quality80; unsupported shapes stay intact and are disclosed.
Native flatten preflights selected normal appearances, geometry and XFA, then verifies
widgets are gone before removing the interactive form root. Nonvisual links/popups
without saved appearance may remain. Missing/ambiguous appearance states refuse.

Artifact output is capped at 48MiB during writing; existing 50MiB input, 80MiB JSON
transport, CPU/memory/wall limits, worker admission and scratch lifecycle remain intact.
Rewriting requires signed acknowledgement and reports unlocked copies. Exact-original
no-reduction results retain protection; text-only extraction does not invalidate signatures.

## Verification

- Initial tests failed because export modules and endpoint were absent; retained RED
  logs: /private/tmp/07-02-pdf-red.log and /private/tmp/07-02-api-red.log.
- Final focused export/worker/ephemerality/header suite: **45 passed**, one existing
  Starlette deprecation warning, 12.08s; /private/tmp/07-02-focused-green-final.log.
- Strict typing: **35 source files clean**, /private/tmp/07-02-types.log.
- Actual API tests exercise all five formats, Unicode encrypted input, signature
  acknowledgement, cache-free current bytes, magic/body/query/output limits,
  decompression refusal, real missing widget appearance and parser-free ASGI import.
- One intermediate negative test used the security fixture's orphan signature field
  rather than a visible widget. Its 200 result was correct for that input. The fixture
  now attaches a page widget to test the intended missing-appearance refusal; no
  production assertion or limit was weakened. Raw intermediate log is retained.

Native all-page pixels, exact downsample preview and actual browser downloads remain
owned by 04. No deployment, Linux/CDN verification, literal-contract G4 closure or
production HEIC confinement claim follows from this implementation.

Commits: 99b1dbd (native RED), 78c5a35 (native GREEN), 357eec5 (API RED),
778df23 (endpoint/transport), 55b2d74 (soft-mask RED), and 2bbebe2 (review fixes).

## Review corrections

Soft-mask/alternative image roles are discovered across indirect objects and nested
direct containers before any resampling; their identities remain protected even when
aliased as ordinary images. Both image /SMask and direct ExtGState luminosity-Form
regressions preserve dimensions and exact alpha bytes. Final native suite:14 passed.
Empty text is detected from actual blocks rather than serialized HTML/Markdown; typed
index/output limits report EXPORT_LIMIT. Real API coverage checks both blank formats.
The integrated review suite passed33 before the final direct-mask case; consolidated
final regression evidence is in07-G6-RESULTS.md. Existing isolation limits remain intact.
