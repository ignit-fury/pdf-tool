# Source text expansion plan and design

User-reported gap: original text still refuses line breaks while inserted containers
can wrap. Deliver the missing bridge, without pretending arbitrary PDFs have a
paragraph model or moving unrelated content automatically. Existing user instruction
authorizes implementation and tests; no deployment or new dependencies.

## Design

Original preserve-layout edits retain the existing writer. A Flexible text box
choice (also entered automatically for pasted/typed line breaks or tabs) converts
the selected original run into a managed native container. Replay the complete
committed recipe against immutable source bytes, replacing the selected run with
empty searchable content through the same guarded writer. Then insert native
wrapped text into the candidate. Neither intermediate state is published.

The existing text-box route gains finite `replace-source`: run_id, existing recipe,
new text/rect/style and auto_expand. It uses original source bytes for authoritative
IDs, while the preview controller remains bound to current materialized bytes,
session and edit version. Cache keys include the actual upload source. Passwords,
signature acknowledgement, isolation, limits and cache recovery remain unchanged.

New and selected managed containers default to Grow height to fit. Native layout
may expand height up to the visible page boundary; overlap checks run after actual
source removal. No clipping or automatic neighbor movement. Disabling growth keeps
the existing explicit overflow workflow. Candidate metadata updates displayed bounds.

The new drawing uses supported bundled font families, explicitly shown before Apply.
Tabs become four spaces, CRLF/paragraph separators become line breaks. Preview is
the real combined PDF. Apply publishes those exact bytes as one mixed Undo action;
Cancel/overflow/refusal preserve all working bytes/history. Existing unsafe source
instructions, managed-glyph edits or ambiguous addressing still refuse.

## Tasks

- [x] RED/GREEN native auto-height tests: free space grows, collisions/page bounds
  refuse without output; preserve default wire behavior when auto_expand is absent.
- [x] RED/GREEN source replacement composition tests: genuine source removal,
  multiline/searchable output, prior recipe retention, no intermediate publication,
  unsafe IDs/managed streams and collision failures preserve immutable input.
- [x] Wire operation through isolated worker and fixed public errors, with real API,
  password/signature/cache/strict-input tests. Warm trusted imports before restriction.
- [x] RED/GREEN controller/model tests for original-source upload versus current-byte
  publication capture, cache separation, growing bounds and explicit formatting.
- [x] Inline source-to-flexible UI bridge, auto line-break transition, growth control,
  accurate candidate bounds/disclosures, Apply/Cancel/Undo without another rewrite.
- [x] Actual browser/native output proof, focused regressions/build/types/license checks,
  one fresh final review, documentation and explicit owned-path local commits.

## Limits / review focus

50MiB source,48MiB candidate,1MiB request,10000 characters,200 boxes,2000 pages;
existing worker memory/CPU/deadline/history limits remain. No white-box overlays,
annotation text, persistent storage, deployment or AGPL dependencies. Unsupported
complex shaping/directed source state and space occupied by neighbors remain explicit.
Review source-hash/recipe identity, prior page/image/text states, double-removal,
original-font state restoration, canceled candidates and actual grown geometry.

Baseline `e8bc3f4`, clean existing feature branch. Execute inline with one final review.

Final evidence: `docs/verification/source-text-expansion-2026-10-29.md`.875 selected
Python tests,12 export/removal gates,197 client tests,40-file strict typing and build
pass. Actual source-expansion, existing viewer/image/Find/text-box/navigation/highlight
journeys and native download verifiers pass. Fresh review has no blocking findings.
Ruling: source IDs remain bound to immutable baseline + complete committed recipe;
publication is bound to current bytes. Avoid guessed new run IDs after materialization.
Ruling: auto-size only the temporary typing surface; native candidate font metrics
determine committed bounds, avoiding font-approximation-driven false collisions.
Ruling: current page follows largest visible height — closing a tall draft exposed
a nearest-top heuristic regression in actual page tools; test/fix verified.
