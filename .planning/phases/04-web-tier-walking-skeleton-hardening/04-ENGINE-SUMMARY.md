---
phase: 04-web-tier-walking-skeleton-hardening
plan: engine-03-05
subsystem: engine
tags: [passwords, styles, geometry, recipe]
requires: [phase-3-rewrite-engine]
provides: [password-threading, style-recipes, pdf-user-space-boxes]
affects: [isolated-worker, browser-editor]
tech-stack:
  added: []
  patterns: [graphics-state-bracketing, inverse-page-transform]
key-files:
  created: [engine/boxes.py, tests/test_boxes.py, tests/test_engine_passwords.py, tests/test_engine_styles.py]
  modified: [engine/index.py, engine/classify_run.py, engine/records.py, engine/recipe.py, engine/rewrite.py, tests/test_recipe.py]
key-decisions:
  - Preserve existing device-space glyph semantics; retain page CTM and effective-em metadata on runs and invert CTM in run_box.
  - Bracket RGB edits with q/Q to restore original Gray/RGB/CMYK or inherited pattern state while retaining fitted text advance.
  - Subset once per family/variant pair so distinct requested faces remain distinct.
completed: 2026-10-21
---

# Phase 4 Engine Slice Summary

Password-protected sources, optional style recipes, and authoritative selection boxes now use the existing atomic rewrite pipeline.

## Delivered

- Optional `password=""` on `RunIndex`, `classify_document`, `plan_recipe`, and `apply_recipe`, threaded through both parsers. Failed second-parser initialization closes the first handle.
- Backward-compatible optional recipe `style` object with normalized finite RGB color, boolean bold/italic, strict unknown-field/type rejection, and a named `font_size_change_unsupported` refusal. Weight/style forces the selected bundled face without changing the older optional-substitution-target semantics.
- `active_font_name_and_size` promoted to public API with the pinned Phase 3 private alias preserved.
- `run_box(run, raw_bytes, resources)` returns bottom-left, unrotated PDF user coordinates with positive extent. Rotation, offset MediaBox, and text scaling are covered.
- Refusal-vocabulary regression fixed for `character_has_no_glyph_in_bundled_font` and the new size refusal.

## Verification

Test-first additions initially produced 10 expected failures before implementation. Final command:

`.venv/bin/python -m pytest tests/test_engine_passwords.py tests/test_engine_styles.py tests/test_boxes.py tests/test_recipe.py tests/test_fonts.py tests/test_rewrite.py tests/test_fit.py tests/test_gate_g2b.py -q`

**135 passed in 25.58s.** Includes AES256 encryption, style parsing, no-output size refusal, unaffected glyph positions, Gray/RGB/CMYK restoration, multiple face subsets, all four page rotations, offset MediaBox, scaled text matrix, Phase 3 font checks and G2b pipeline.

`.venv/bin/python -m mypy --strict engine`: **Success, 19 source files.** No new placeholder or TODO stubs in the new modules/tests.

## Deviations and limits

- The outline assumed glyph coordinates were already user space. Installed playa defaults to screen space. RunRecord therefore retains optional geometry metadata beside the fixed GlyphRecord provenance; existing glyph coordinates and prior gate semantics remain unchanged.
- Selection height remains an intentional 0.8em ascent / 0.2em descent approximation, documented `# ponytail:` in `engine/boxes.py`; boxes are not exact glyph-outline bounds, especially for unusually sheared text.
- Parent installed the documented `playa-pdf[crypto]` extra and configured packaged `ots-sanitize` visibility; initial environmental failures were rerun successfully after those dependencies became available.
- No task commits: controller explicitly owns reviewable integration and commits in this shared main checkout.

## Self-Check: PASSED

All created modules and test files exist. Final focused suite and strict engine type checking passed. No claims of external deployment or browser verification are made by this engine slice.
