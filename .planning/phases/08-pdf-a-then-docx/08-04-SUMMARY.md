---
phase: 08-pdf-a-then-docx
plan: "04"
subsystem: docx-projection
tags: [ooxml, shared-model, images, warnings]
key-files:
  created: [engine/image_index.py, engine/export/docx.py, tests/test_export_docx.py]
  modified: [engine/index.py, engine/blocks.py]
metrics:
  completed: "2026-10-28"
  focused_tests: 38
---

# 08-04 — Shared facts and direct OOXML

Commit `c7ee70f` adds opt-in image discovery to the existing RunIndex page cache,
shared ImagePlacement/LayoutFact records, and an isolated stdlib OOXML writer.
Ordinary text indexing keeps image discovery off. Supported raw/Flate/DCT RGB/gray
placements become metadata-free PNGs; forms, masks, clipping and unknown image
coverage are disclosed. Counts/pixels/encoded bytes are bounded cumulatively.

`prepare_docx(DocumentBlocks)` copies one immutable output projection;
`snapshot_digest` binds text/styles/order/tables/image hashes/geometry and review
facts; `serialize_docx` emits fixed inert ZIP parts, relationships and escaped XML.
Columns/ambiguous layouts become geometry-ordered plain paragraphs. Ruled tables,
known emphasis and supported images survive. Annotation omission is explicit.
Invalid XML text refuses with a fixed code. No optional writer import is added to
the shared model or export package initializer.

Verification: six initial RED tests; final **38 passed**, covering DOCX and the
unchanged blocks/text/single-path tests. Strict typing passes **38 source files**.
Two serializations are byte-identical. macOS textutil independently reads the
three-page layout DOCX with expected row-wise fallback and table text. ZIP/CRC/XML,
styles, image parts, unknown-count facts, limits and no eager image analysis pass.
The actual Word client is unavailable; this is not Word visual verification.

Deviation: image parsing lives in a focused core helper, `engine/image_index.py`,
rather than growing index.py; it is independent of DOCX and opt-in. New shared
contract tests live beside the DOCX tests, while prior block tests stay unchanged.
No table detector changes, PDF text extractor, package install or runtime AGPL.

## Self-Check: PASSED

All declared ceiling features have package assertions; fixed part paths contain
no external relationships, macros, OLE or active HTML. Public API/UI follow next.
