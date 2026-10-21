# Phase 4 execution — 2026-10-21

The user authorized completion of the next milestone: integrate Phase 3 and deliver the
Phase 4 browser editor and hardening. Governing design: the Phase 3 worktree's
`04-CONTEXT.md`, `04-PLAN-OUTLINE.md`, and `04-VALIDATION.md`.

## Execution plan

1. Integrate the existing Phase 3 source, fonts, tests and supporting harness into this
   checkout. Preserve the original worktree and its local edits. Fix its refusal vocabulary
   regression; restore the OTS gate dependency. This is source integration, leaving branch
   history untouched until the result is reviewable.
2. Extend the engine for passwords, server-issued geometry, and optional colour and
   weight/style changes. Size changes get a named refusal. Retain atomic recipe replay.
3. Replace the obsolete server fork with isolated workers, bounded input, ephemeral
   content-addressed cache, cache-miss recovery, signature warnings, exact no-store headers,
   CSP, sanitized reporting, and automated hostile-input/privacy checks.
4. Connect the browser viewer and selectable text layer, progressive thumbnails and
   classification, server-box edit selection, style toolbar, local recipe undo, retry on
   cache eviction, and honest per-operation disclosure. OCR route defaults to OCRmyPDF's
   official documentation; links never transmit the document.
5. Verify engine/server/client, exercise the real browser journey, update README and
   planning state with evidence. Keep external deployment/CDN and Linux-only checks
   explicitly pending until actually exercised; do not fabricate a public deployment.

## Ownership and sequencing

GSD execution delegates disjoint engine and isolated-worker modules after integration.
The controller owns integration, configuration, server API and final verification. The
client is implemented after the worker privacy controls and API contracts are established.
All contributors share this checkout and must preserve each other's changes. Test-first
checks precede new behavior. No new parallel rewrite path, queue, object store, OCR engine,
bulk replacement feature or later-phase export work.

## Verification

- Phase 3 gates and recipe/font/rewrite regression tests; strict mypy.
- Phase 4 ingest, worker isolation, hostile inputs, cache loss, signature/password,
  headers, API contracts and success/crash canary tests.
- Frontend production build and real browser open/edit/style/download/undo journeys.
- Full pytest suite, reporting every failure and any unexercised environmental gate.

## Plan adaptations

The installed GSD entry point references a stale `~/.Codex/get-shit-done` path; use the
installed `~/.claude/get-shit-done` workflow. Phase 4 has a detailed 14-plan outline but no
individual executable plans; this execution record supplies task sequencing and ownership.
HTTPX was verified against its official documentation before adding it as a dev dependency.
The existing source worktree is preserved rather than merged while it contains local edits.

## Execution evidence and corrections

Implementation tasks 1–5 are delivered locally; final evidence and the remaining public-release
gates are tracked in `04-VERIFICATION.md`. The full suite exited 0 (423 passed, 5 skipped);
two subsequently added tests passed focused checks. Frontend build and strict typing pass.
After final review fixes, the full non-corpus rerun passed (420 passed, 5 skipped,
19 deselected), as did all three renderer/font gates and ten client helper tests.
The review and fix record is `04-REVIEW.md`.
Local browser journeys were performed in Safari/Firefox, including a real downloaded PDF
and recovery after restarting the server. Review fixes cover stroke colour, positive
word-space preservation, pdf.js loading-task disposal, idle TTL expiry, request-body
admission/deadlines, cancellation-safe worker permits, and admission held through bounded
response streaming. The latter prevents slow downloads from accumulating large responses.

A sampled long-running corpus process showed repeated qpdf LZW stream decoding. A regression
test demonstrated 26 identical font resolutions for one showing operator. Page-local stream
and operator caches eliminate repeated decoding while retaining complete provenance keys and
per-glyph verdict checks. Classifier/geometry/style tests and Phase 3 renderer gates pass.
This is a narrow performance correction on the existing reader, not a second parser.

All edits remain in this checkout for review. Original worktree source was preserved.
Linux/production and CDN outcomes must not be inferred from configured CI jobs.
