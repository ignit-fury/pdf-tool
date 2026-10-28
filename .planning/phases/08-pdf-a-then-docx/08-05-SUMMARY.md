---
phase: 08-pdf-a-then-docx
plan: "05"
subsystem: docx-review-api
tags: [review, cors, isolation, optional-export]
key-files:
  created: [tests/test_docx_api.py]
  modified: [server/app.py, server/worker.py, server/isolation.py, server/errors.py]
metrics:
  completed: "2026-10-28"
  focused_tests: 45
---

# 08-05 — Review before generation

Implementation commit: `bc4f20b`.

The optional capability endpoint performs file-presence lookup without parsing a
PDF. Explicit docx-review opens one RunIndex with images enabled, projects shared
blocks once and returns only safe review facts and source/snapshot/policy digests.
It never calls the OOXML serializer, proven with an in-process canary.

Conversion requires a strict ASCII acknowledgement of at most 256 bytes in
X-DOCX-Review. Parent validation rejects malformed/duplicate/extra fields and
changed source before dispatch. The worker independently rebuilds one snapshot,
checks the complete digest and serializes that exact snapshot. No receipt secret,
expiry service, cache, document history or new dependency exists.

Twelve RED API tests failed before implementation. Final **45 API tests pass**
(DOCX plus prior exports); strict typing passes **38 files**. Actual CORS
OPTIONS→review→conversion and rejected origins, bad/missing acknowledgements,
changed source, changed projection, no eager serialization and optional-capability
failure are covered. Existing export requests keep their prior transport keys;
review digests are sent to workers only for conversion. Conditional warmup/import
allows removing the writer without breaking other operations; literal removal
of the module and full non-DOCX gate proof remain Plan 06.

## Self-Check: PASSED

The successful artifact is the established eight-key envelope, document.docx and
its exact OOXML MIME. Fixed errors/notices disclose limits/passwords/signatures;
raw source text/images never enter review responses or acknowledgement headers.
Hosted CI/deployment and Word visual checks remain unperformed.
