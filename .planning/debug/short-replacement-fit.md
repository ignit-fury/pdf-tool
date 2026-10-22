---
status: resolved
trigger: Short replacement refused with delta -209.98pt, shown twice
created: 2026-10-22
---

# Short replacement fit

Expected: a shorter replacement remains at the original start, with unused space after
it and unchanged subsequent text. Actual: engine.fit refuses negative deltas larger
than bounded trailing/inter-word absorption. Client shows the raw reason as both text
and code. User reported this while trying the explicit font replacement feature.

## Current Focus

Hypothesis: the fit ladder applies a visual gap-expansion budget to a trailing unpainted
advance, incorrectly refusing underflow. Longer replacements still require existing fit
limits. Reproduce with a short single word against a substantially longer run, then
preserve following text using a terminal TJ adjustment, without widening glyphs.

Plan: engine/fit.py plus focused fit/rewrite regression tests; client plain-language
reason presentation shown once. Preserve structural and Unicode refusal gates.

## Reasoning checkpoint

Evidence: `fit_run` refuses large negative deltas, while `_show_instruction` writes
`trailing_kern` after the complete replacement string. A terminal negative adjustment
therefore preserves unused advance without stretching its glyphs. Keep existing moderate
fit rungs; add only underflow fallback. Falsifier: next glyph moves, replacement's start
or natural advance changes, or output fails extraction/rendering. The user's actual PDF
is not available, so verify constructed independent cases rather than claim exact-file proof.

GSD references under `~/.Codex` are stale; the installed workflow is under
`~/.claude/get-shit-done`. Controller handles client display; debugger owns engine tests.

## Width-basis evidence

The real follower regression exposed a second issue: fitting uses unrounded hmtx metrics,
while written PDF font widths may be rounded. Tiny produced a 0.00192pt follower shift,
correctly refused by the existing guard. Controller corrects the terminal adjustment from
the actual written font dictionary's /Widths or /W; no guard tolerance is loosened and
test strings are not changed to hide the mismatch.

## Resolution and verification

Large negative deltas now use a terminal TJ adjustment after the replacement; the
unused original width remains blank. Existing moderate fit behavior and positive-delta
compression/refusal limits remain unchanged. Trailing corrections use the actual written
font widths; the geometry guard remains strict. Client fit feedback now uses plain copy,
with prose displayed once rather than repeated as a code.

Nine regression cases failed before the changes. Eight real-PDF cases now prove original
bytes unchanged, natural glyph widths/no Tz, fixed start/follower positions, explicit
Serif and embedded/unembedded paths, and searchable output verified with PDFium.

- Complete non-corpus suite: 445 passed, 5 skipped, 19 deselected in 88.24s.
- Two corpus-marked G2b renderer gates: 2 passed in 3.92s.
- Controller rewrite/new-regression run: 43 passed; strict mypy: 28 files clean.
- Client helpers: 12 passed; production build passed (existing bundle-size warning).
- Targeted design detector and diff whitespace checks: clean.
- Live localhost HTTP: large shrink with explicit Serif preview/apply passed and the
  downloaded bytes extracted Tiny and FOLLOWER through independent PDFium.
- Debugger reviewed the written-width correction; no guard relaxation or exact-width
  fixture substitution was used to conceal the original failure.

The original user PDF was not supplied. Linux/CDN release holds are unchanged.
