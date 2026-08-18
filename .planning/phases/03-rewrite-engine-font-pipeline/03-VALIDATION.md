---
phase: 3
slug: rewrite-engine-font-pipeline
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-18
planned: 2026-08-18
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `03-RESEARCH.md` § Validation Architecture. Task IDs are filled in by the planner.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest ≥9.1.1 (already configured) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths=["tests"]`, `corpus` marker registered |
| **Quick run command** | `uv run --frozen pytest -q -m "not corpus"` |
| **Full suite command** | `uv run --frozen pytest -q` |
| **Type check** | `uv run --frozen mypy engine/` (strict; zero `# type: ignore` in `engine/`) |
| **Estimated runtime** | ~150s quick (184 tests as of Phase 2 close); full suite dominated by the 217-document corpus sweeps (~50 min) |

---

## Sampling Rate

- **After every task commit:** `uv run --frozen pytest -q -m "not corpus"` + `uv run --frozen mypy engine/`
- **After every plan wave:** `uv run --frozen pytest -q` (includes `corpus`-marked sweeps)
- **Before `/gsd:verify-work`:** full suite green, plus the actual G2a/G2b harness runs reusing
  `harness/masked_diff.py` and `harness/render_diff.py` **unmodified**
- **Max feedback latency:** ~150s for the per-task quick loop

---

## Per-Task Verification Map

Task IDs are assigned by the planner; the requirement→test mapping below is fixed by research and
must be preserved. Every row's command is the acceptance evidence for that requirement.

| Plan | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-06 | EDIT-02 | T-03-06-01 | Text matrix after the edited run unchanged within epsilon (D-04 runtime guard) | unit + corpus | `pytest tests/test_rewrite.py::test_edit02_matrix_invariant_holds_after_fit -x` | ❌ W0 | ⬜ pending |
| 03-06 | EDIT-02 | — | Multi-operator run consolidates correctly (Pitfall 1/2 — 10.6% of runs, up to 167 ops) | unit | `pytest tests/test_rewrite.py::test_multi_operator_run_consolidates_to_one_instruction -x` | ❌ W0 | ⬜ pending |
| 03-06 | EDIT-02 | — | **Non-contiguous run: a foreign run's interleaved operator survives unedited** (~1.1% of editable runs) | unit, negative case | `pytest tests/test_rewrite.py::test_foreign_interleaved_operator_survives_unedited -x` | ❌ W0 | ⬜ pending |
| 03-03 | EDIT-03 | — | Tz condensing within 90–95%, scale restored after the run, subsequent text unaffected | unit | `pytest tests/test_fit.py::test_tz_condensing_restores_scale_after_run -x` | ❌ W0 | ⬜ pending |
| 03-07 | EDIT-03 | — | Dry-run report matches the actual commit outcome (D-03) | integration (CLI) | `pytest tests/test_pdftool_edit.py::test_dry_run_matches_commit -x` | ❌ W0 | ⬜ pending |
| 03-07 | EDIT-04 | T-03-07-* | Named refusal reasons for every failure mode; never generic | unit | `pytest tests/test_recipe.py::test_refusal_reasons_are_named_not_generic -x` | ❌ W0 | ⬜ pending |
| 03-04 | FONT-01 | T-03-04-01 | Static mapping table, exact-match only, no fuzzy/heuristic fallback | unit | `pytest tests/test_fonts.py::test_mapping_table_is_exact_match_no_fuzzy_logic -x` | ❌ W0 | ⬜ pending |
| 03-04 | FONT-01 | — | Corpus-wide substitution coverage measured and reported (Pitfall 10) | corpus | `pytest -m corpus tests/test_fonts.py::test_corpus_substitution_coverage_report -x` | ❌ W0 | ⬜ pending |
| 03-05 | FONT-02 | — | Subsetting covers the whole-recipe glyph union, once per family (D-13) | unit | `pytest tests/test_fonts.py::test_subset_covers_union_across_recipe -x` | ❌ W0 | ⬜ pending |
| 03-09 | FONT-02 | — | AMENDED 2026-08-18 (plan-checker finding): re-homed from the pre-planning guess `tests/test_rewrite.py` — no plan's scope actually fit that literal file (03-06 has no whole-recipe view of which other runs share a bundled family). A shared bundled-family re-subset serves every edited run that uses it: two edits into the same family produce exactly one embedded subset object, and both edits' display text and untouched-elsewhere pixels stay correct (roadmap criterion 3) | corpus + pixel-diff | `pytest -m corpus tests/test_gate_g2b.py::test_shared_family_resubset_serves_both_edited_runs -x` | ❌ W0 | ⬜ pending |
| 03-05 | FONT-03 | T-03-05-* | Emitted font passes OTS (`ots-sanitize`, exit 0) | unit (subprocess) | `pytest tests/test_fonts.py::test_emitted_font_passes_ots -x` | ❌ W0 | ⬜ pending |
| 03-05 | FONT-03 | — | `/ToUnicode` round-trips (copy-paste-out-of-Acrobat proxy) | unit | `pytest tests/test_fonts.py::test_tounicode_cmap_roundtrips_ascii_and_accented -x` | ❌ W0 | ⬜ pending |
| 03-05 | FONT-04 | — | `/W` entries match the subset's own `hmtx`; no silent `/MissingWidth`-of-0 fallthrough | unit, negative case | `pytest tests/test_fonts.py::test_font04_missing_width_never_falls_through_silently -x` | ❌ W0 | ⬜ pending |
| 03-05 | FONT-05 | — | Two subsets of the same family in one document get distinct tags | unit | `pytest tests/test_fonts.py::test_fresh_subset_tag_per_family -x` | ❌ W0 | ⬜ pending |
| 03-04 | FONT-06 | T-03-04-02 | **The new edit-time glyph-availability check fires on `editable_original` runs too**, not only `editable_substitution` (research Pattern 4 — this trigger does not exist in Phase 2); AMENDED 2026-08-18 (plan-checker finding): a Type0/CIDFontType2 font (branch_id `"C-*"`) always substitutes without ever calling the simple-font-only `reverse_encoding_map` — see `test_type0_cid_font_always_substitutes_without_reverse_map_lookup` | unit, negative case | `pytest tests/test_fonts.py::test_editable_original_run_still_substitutes_on_missing_glyph -x` | ❌ W0 | ⬜ pending |
| 03-08 | G2a | — | Confined-diff check is a **targeted structural comparison**, not a whole-file `qpdf --qdf` diff (see Manual-Only note below) | integration | `pytest tests/test_gate_g2a.py::test_confined_diff_isolated_to_edited_stream -x` | ❌ W0 | ⬜ pending |
| 03-09 | G2b | T-03-09-* | Full pipeline with a character absent from the subset: same-engine zero-tolerance + cross-engine tolerant pixel diff, reusing `harness/` | corpus + pixel-diff | `pytest -m corpus tests/test_gate_g2b.py::test_g2b_full_pipeline -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` — add the `uharfbuzz.*` mypy override **before** any `engine/` module imports
      uharfbuzz (Pitfall 6 — reproduced this session; uharfbuzz ships no type stubs and has never
      been imported inside `engine/`)
- [ ] `fonts/` directory — does not exist. Needs Liberation Sans (Bold/Italic/BoldItalic; Regular
      already exists at `spike/fixtures/`), Serif (all 4), Mono (all 4), one shared OFL license
      file, and the `fsType` verification run against all of them (Pitfall 11; Liberation Sans
      already verified `fsType == 0`)
- [ ] `Dockerfile.ci` — add the pinned `opentype-sanitizer` package for the OTS gate
- [ ] `tests/test_fit.py` — the width-fit ladder, porting `tests/test_tj_refit_prototype.py`'s
      proven cases (same fixture text, same expected deltas) onto the real module, per
      `TJ-REFIT-RESULTS.md`'s own carry-forward instruction
- [ ] `tests/test_fonts.py` — mapping table, subsetting, Type0/CIDFontType2 embedding, OTS
- [ ] `tests/test_rewrite.py` — content-stream surgery, using the **exact** multi-operator and
      non-contiguous-run examples measured during research as named regression fixtures
      (`irs_form_1040.pdf` p0 run `:o1391`, `irs_form_w4.pdf` p0/p4 runs)
- [ ] `tests/test_recipe.py` — JSON recipe parsing, D-10 hash refusal, D-11 all-or-nothing
- [ ] `tests/test_pdftool_edit.py` — CLI integration, dry-run vs commit
- [ ] `tests/test_gate_g2a.py`, `tests/test_gate_g2b.py` — both gates as explicit named tests,
      never informal manual verification

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Output opens without a repair prompt in Acrobat Reader, macOS Preview, and Chrome | G2b | No headless API for "did this viewer show a repair prompt"; the three viewers are the check closest to real user experience and cannot run in CI | Open each G2b output artifact in all three viewers; record pass/fail per viewer in a results document, following the `PLAYA-DECISION.md` / `TJ-REFIT-RESULTS.md` precedent (D-15) |
| Copy-paste out of Acrobat yields correct Unicode | G2b | Requires a real Acrobat clipboard interaction; the automated `/ToUnicode` round-trip test above is the CI proxy, not a substitute | Select the edited run in Acrobat, copy, paste into a plain-text editor, compare against the recipe's `new_text` |
| Substituted run shows no visible seam mid-paragraph at 100% zoom | Roadmap criterion 4 / Risk #4 | Identical advance widths do not guarantee identical appearance — differing stroke weight or x-height reads as a seam even when metrics match exactly (D-08) | Generate the rendered before/after contact sheet across corpus samples; review once; record the verdict. The advance-delta metric gate is the automated half and **does** run in CI |

**Note on G2a's literal wording.** Research measured that a whole-file `qpdf --qdf` diff does **not**
work as the roadmap literally states: coalescing an 8-part `/Contents` array (the pattern
`identity_rewrite.py` already establishes) produced a **13,689-line diff for a single-word edit**,
purely from object renumbering — and 52.5% of the corpus has array `/Contents`. The criterion's
*intent* (the diff is confined to the edited operators) is preserved by a targeted structural
comparison, and the rewrite must never reshape `/Contents`. This mirrors the Phase 1 correction to
the "pixel-identical across all three engines" wording and should be recorded the same way.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or a Wave 0 dependency — confirmed across all 9
      committed plans
- [x] Sampling continuity: no 3 consecutive tasks without an automated verify
- [x] Wave 0 (03-01) covers every ❌ reference above
- [x] No watch-mode flags in any command
- [x] Feedback latency < 150s for the per-task loop
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned 2026-08-18 — plan-checker ran a full cross-plan seam review (9 plans, chunked
authorship) and returned CONCERNS: two blockers (a Type0/CIDFontType2 font silently mishandled by
the FONT-06 substitution trigger; the FONT-02/criterion-3 test pinned above with no owning task).
Both closed same-day via targeted plan amendments (03-04, 03-06, 03-09 — see their own AMENDED
blocks) rather than a re-plan. Re-verification of the amended plans' frontmatter/structure passed;
the fixes were not re-run through a second full plan-checker pass given their narrow,
source-grounded scope. Execution may proceed.
