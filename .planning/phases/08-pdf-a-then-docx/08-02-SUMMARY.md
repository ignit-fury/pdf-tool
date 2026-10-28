---
phase: 08-pdf-a-then-docx
plan: "02"
subsystem: archival-conversion
tags: [pdfa, g7a, fonts, native-fidelity]
key-files:
  created: [engine/export/pdfa.py, engine/data/sRGB2014.icc, engine/data/sRGB2014-LICENSE.md, tests/test_pdfa.py, tests/test_gate_g7a.py]
metrics:
  completed: "2026-10-28"
  tests: 47
---

# 08-02 — Native archival conversion

`export_pdfa(pdf, source)` returns bounded PdfaResult bytes/notices or PdfaRefusal
with one of nine safe reason IDs. An explicit font/resource/operator/color policy
precedes sRGB output intent, controlled PDF/A-2b metadata and PDF 1.7 serialization.
The official unmodified ICC asset has its source/hash/copyright/license recorded.

| Commit | Result |
|---|---|
| `c718cbc` | 31 RED acceptance/refusal tests |
| `efb6b18` | Audited native converter and licensed ICC asset |
| `3964188` | RED real native/validator gate |
| `2ad0ec1` | Complete gate, review-limit guards, simple font/blank-page fixes |

47 focused/native gate tests pass. Sixteen PDFs validate externally; 57 exact
same-engine page comparisons and 32 structural validations pass. All twelve
frozen positives remain required. Two cross-engine discrepancies exactly match
source baselines. Full evidence and limitations: `08-G7A-RESULTS.md`.

## Deviations

Independent source review and executor were interrupted by an agent usage limit;
the orchestrator retained their work, reproduced/fixed confirmed findings and ran
the final gate. No claim of a completed independent whole-phase review is made.
The inherited-resource notice covers converter-performed normalization; pikepdf
may already normalize on open, so no second parse was added merely for a notice.
The valid missing-Contents blank-page branch was added after an actual current-byte
browser export refused it. Fixed inputs/floor and renderer tolerances are unchanged.

## Self-Check: PASSED

Owned implementation, audited asset, tests and real gate evidence exist. Local
G7a proof precedes DOCX. Actual hosted CI and release checks remain pending.
