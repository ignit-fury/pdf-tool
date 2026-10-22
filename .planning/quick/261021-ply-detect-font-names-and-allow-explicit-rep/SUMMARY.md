---
status: complete
completed: 2026-10-22
---

# Font detection and explicit replacement

The reported `Times New Roman` lookup now recognizes exact spaced aliases, including
bold/italic variants and Courier New. Unknown names still receive no guessed automatic
match; the inspector now displays the actual source name and offers Automatic, Liberation
Serif, Liberation Sans, and Liberation Mono. Choosing a family explicitly bypasses the
missing mapping and forces content-stream replacement, including for embedded originals.

The optional recipe field is `style.font_family`, strictly limited to `Sans`, `Serif`,
or `Mono`. Bold/italic selection, fit preview, whole-recipe undo, immutable-source replay,
glyph coverage, searchable Unicode and structural refusal checks remain in force. Unknown
source names now have an actionable prompt instead of duplicated technical mapping text.
No font files are uploaded and no external fonts or dependencies are fetched.

## Verification

- Original regression run reproduced seven failures (spaced aliases, explicit family,
  and missing API metadata) before implementation.
- Engine/font/style/recipe/rewrite/worker/HTTP and renderer gates: **160 passed**.
- Two later added positive cases pin automatic Times New Roman editing and known-family
  metadata; the final dedicated font-choice suite passed **17 tests**.
- Client helpers: **11 passed**, including font selection/removal and recipe undo.
- Production client build passed, with the existing bundle-size warning.
- Strict mypy passed across all **28** engine/server files; diff whitespace check passed.
- Targeted Impeccable detector returned no findings.
- Independent read-only review found no actionable Important or Critical issues.

The local editor was restarted on port 8765. A manual browser attempt was stopped before
interaction because the user was actively using Firefox; no isolated browser provider
was available. No manual UI journey is claimed for this task. The real-worker HTTP tests
prove upload, source detection, explicit-family preview/apply, embedded selected face, and
searchable replacement output.

## Scope and execution notes

Unknown *font names* can now be replaced; scanned/outlined text, unreadable encodings,
unsupported glyphs/shaping, unsafe operators and overflowing replacements remain explicit
refusals. These controls preserve the surrounding PDF rather than silently corrupting it.
The bundled trio is the controller's implementation choice for the requested font-kind
selector, building on the existing installed fonts; arbitrary font-file support is separate.
The planning agent wrote PLAN.md before hitting its quota; the controller completed the
existing GSD quick plan inline with regression tests. Phase 4's external release gates
remain unchanged.
