# DOCX scope ceiling — Gate G7b

## Decision

Recorded 2026-10-28, before Phase 8 product implementation. This records the existing
Phase 8 roadmap and context decisions; it does not widen them.

DOCX is best-effort interchange: **single-column body text, headings by font-size
clustering, bold/italic, inline images, ruled tables only, everything else as plain
paragraphs**. Explicitly excluded: **unruled tables, multi-column reading order,
header/footer reconstruction, round-trip back into the tool**. DOCX is not a
pixel-faithful PDF representation. Unsupported content must be disclosed before
conversion using findings for the current document, without inventing text or
structure. Image-only pages do not acquire text without OCR.

PDF/A-2b ships first and remains validator-gated. DOCX comes after that gate and
is independently cuttable: removing DOCX leaves all other export gates passing.
The writer consumes the existing RunIndex and shared block model, with no second
text extraction, LibreOffice, pdf2docx, or AGPL runtime dependency. Any proposed
improvement to table detection or reconstruction beyond this ceiling is a future
phase, not a prerequisite for completing this one.

## Evidence

- `.planning/ROADMAP.md`, Phase 8 success criteria 2–5 and ordering constraint 10.
- `.planning/phases/08-pdf-a-then-docx/08-CONTEXT.md`, D-8.1 through D-8.6.
- `.planning/REQUIREMENTS.md`, EXPO-07, EXPO-08 and Out of Scope.
- Before this document, this checkout contains no Phase 8 PLAN/SUMMARY or
  `engine/export/pdfa.py` / `engine/export/docx.py` implementation.

## What was NOT tested

This document locks the scope and its ordering. It is not evidence that any DOCX
opens in Word, that layout inference is correct, or that PDF/A validation passes.
Those require their own implementation and verification evidence.
