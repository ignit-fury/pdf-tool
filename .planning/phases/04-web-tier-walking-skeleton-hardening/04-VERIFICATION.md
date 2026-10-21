---
phase: 04
status: locally_verified_release_gates_pending
verified_at: 2026-10-21
release_status: hold_for_linux_and_cdn
---

# Phase 4 verification

## Decision

The local implementation is delivered and the browser round trip is exercised.
**Public-release Gate G3 remains on hold** until actual Linux/container enforcement
and live CDN behavior are verified. This macOS workstation has neither Docker nor
Podman and no deployment URL has been supplied. These checks are implemented in CI;
configured checks are not recorded as executed checks.

## Delivered behavior

- Phase 3 recipe/fit/rewrite/font source, fonts, gates and CLI integrated into this
  checkout. The original worktree, including its local edits, was preserved.
- Optional passwords and style recipes; size changes explicitly refused. Server-issued
  boxes handle rotated pages, MediaBox offsets and scaled text. Both fill and stroke
  colours restore the following text's graphics state and matrix.
- Isolated parser processes, bounded ingress/output, body deadlines, admission limits,
  cancellation-safe worker limits, response admission held through backpressure, and private per-operation scratch. Linux adds memory,
  tmpfs and seccomp enforcement. Child environments exclude parent credentials.
- Bounded expiring memory cache; source loss is recoverable by reuploading browser-held
  originals. No server undo history, queue, object store, filename/password cache fields,
  content logging or exception-frame reporting.
- Viewer, native text layer, progressive thumbnails/classification, hit boxes, edit/fit
  preview, colour/weight/style, PDF download, atomic recipe undo, password prompt,
  signature warning, local/server disclosure and external OCR guidance.
- Obsolete rewrite/export scaffold removed, installed node_modules untracked while
  preserving its lockfile, production container and explicit Linux privacy CI gates added.

## Automated evidence

Fresh focused runs during implementation:

| Check | Result |
|---|---|
| Engine passwords/styles/geometry plus Phase 3 regression subset | 135 passed before final browser fixes |
| Final fit/style/recipe/rewrite/G2a/G2b subset | 112 passed |
| HTTP, headers, isolation, hostile inputs, canary and cache recovery | 49 passed; 4 Linux-only skips |
| Classifier cache plus classification/geometry/style regression subset | 48 passed |
| Strict mypy across engine and server | 28 files, no issues |
| Client recipe/retry/queue/disposal/disclosure/password helpers | 10 passed |
| Production frontend build | passed; large-bundle warning remains |
| Installed Python dependency license gate | no AGPL/Affero distributions found |
| Full corpus glyph provenance rerun | passed |
| Full corpus raw-walker alignment rerun | passed |
| Full corpus clustering rerun | passed |

The first complete suite attempt was interrupted after 379 passes and four failures.
Three failures were stale encryption exclusions after adding the required crypto extra;
the correlation baseline also retained Phase 2's zero source hash. The source-hash baseline
now uses independent manifest digests, keeping every measured stream/operator/refusal.
The now-readable encrypted W-9 has its own positive regression check. The corpus scans
also exposed repeated LZW decompression per glyph. A measured operator-level cache and
page-local stream cache remove repeated reads without changing address or verdict logic.
Final complete-suite evidence is recorded below.

## Observed browser journeys — Safari and Firefox

All files were synthetic fixtures, uploaded only to localhost.

| Journey | Observed result |
|---|---|
| Open and first-page render before classification completes | passed in both browsers |
| Select server-issued text box and inspect its original text | passed |
| Preview text and bold style, then apply | passed after fixing pdf.js disposal and spacing |
| Download edited PDF and open it in Firefox's native PDF viewer | passed, no repair UI |
| Re-extract downloaded text and validate PDF | `Hallo world`; qpdf clean |
| Cmd+Z restores original text and removes edited-download state | passed in Safari |
| Password prompt, unlock, render and classify | passed in Safari |
| Restart server mid encrypted session, preview without reopening file | passed; browser restored source/password transparently |
| Signed fixture warns and offers explicit acknowledgement | passed; fixture is structurally signed, not cryptographically attested |
| Browser find over actual DOM text layer | passed in Safari |

The browser checks are agent-operated UI observations, not an assertion that a person
approved the document. Clipboard contents were not separately inspected. Linux kernel
limits/seccomp, container startup, remote CI and live edge-cache behavior were not executed
here. Native same-engine pixel comparisons remain the Phase 3 gate proof; screenshots
alone are not treated as pixel-diff evidence.

## Remaining release gates

1. Run the committed CI environment on Linux, including actual memory allocation failure,
   tmpfs fail-closed checks and kernel syscall denial. The container must start as nonroot
   with a read-only root and tmpfs scratch.
2. Supply `PDF_TOOL_DEPLOYMENT_URL` and run the repeated CDN-cache probe through the actual
   production edge. Confirm request bodies are not durably buffered by any reverse proxy.
3. Record the deployment-specific browser journey and clipboard check before public sign-off.

## Complete-suite result before final review

`.venv/bin/python -m pytest -q --durations=10` exited 0: **423 passed, 5 skipped,
3 warnings in 1352.13 seconds**. Skips cover Linux-specific enforcement and the live CDN
gate, whose environments are unavailable here. Warnings are the upstream Starlette/httpx
deprecation and two expected malformed/form corpus warnings.

Two tests were added after that run collected its 428 cases: distinct operator font changes
sharing one stream decode, and admission retained during slow response sending. Both passed
in subsequent focused runs (49 passed, 4 skipped for the combined backend/cache checks;
21 passed for the transport/header checks). A final direct run of
`tests/test_operator_font_cache.py tests/test_web_contract.py` also exited 0: **13 passed**.
That collection contained 430 cases including the two later additions. Final review then
added password transport and safe-refusal regression cases, recorded below.

The final client production build exited 0. Its 646 kB application chunk still triggers
Vite's size warning. Strict mypy passed across all 28 engine/server files. Local/server
undo disclosure uses the same client predicate that chooses local restore or server replay;
worker API results also explicitly identify server processing.

## Final code review

An independent read-only review reproduced three Important correctness bugs. Regression
tests failed before their fixes:

- Raw password headers rejected Unicode and normalized edge whitespace. The client now
  sends UTF-8/base64 in `X-PDF-Password-B64`; the server strictly decodes bounded values.
  A real Unicode-password PDF opens and classifies through HTTP. Legacy plaintext headers
  remain supported; ambiguous double headers are rejected.
- Replacing quote text operators could discard implicit line movement or spacing. Plan
  and runtime now return `stateful_text_showing_unsupported` for any touched quote operator,
  including later operators in a clustered run. No output is written.
- Shaped glyph clusters could truncate searchable Unicode, or one shared CID could acquire
  conflicting source characters. Per-op and grouped-face checks now return named refusals
  before embedding, with runtime guards. Precomposed accents remain supported; multi-character
  clusters and ambiguous shared-glyph mappings are explicitly unsupported.

After all review fixes, `.venv/bin/python -m pytest -q -m 'not corpus' --durations=5`
exited 0: **420 passed, 5 skipped, 19 deselected, 2 warnings in 87.17 seconds**.
The final renderer/font gate rerun (`tests/test_gate_g2a.py tests/test_gate_g2b.py`) also
exited 0: **3 passed**, including the two corpus-marked G2b cases. The remaining full-corpus
reader checks above precede these narrow transport/rewrite fixes; they have not been
re-labelled as a later run. Current collection: **444 cases**.

Strict mypy again passed across all 28 engine/server files. All **10** client helper tests
and the final frontend build passed. A live check against the restarted localhost server
confirmed UI/no-store headers, PDF upload, bold edit, PDF output, and Unicode-password
upload/classification. The independent reviewer rechecked the fixes with **25 passing**
focused tests and no remaining Important findings in those fixes.
