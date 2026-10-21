---
phase: 8
slug: pdf-a-then-docx
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-31
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived verbatim from `08-RESEARCH.md` § Validation Architecture. Task IDs are filled in by the
> planner; every command below was written to be runnable, and every file marked `❌ Wave 0` does not
> exist yet.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| Framework | pytest ≥9.1.1 (already configured — `pyproject.toml` `[dependency-groups] dev`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths=["tests"]`, `pythonpath=["."]`, `corpus` marker for full-corpus-sweep tests |
| Quick run command | `uv run --frozen pytest -q -m "not corpus"` |
| Full suite command | `uv run --frozen pytest -q` |
| Type check | `uv run --frozen mypy engine/` (strict; `files = ["engine"]`; zero `# type: ignore`) |
| New mypy override required | `python-docx` ships no `py.typed`; add a **scoped** `[[tool.mypy.overrides]] module = ["docx.*"]` `ignore_missing_imports = true`, matching the existing `fontTools.*` / `uharfbuzz.*` precedent. Never a blanket override |
| Validator (CI) | `docker run --rm -v "$PWD:/data" verapdf/cli@sha256:d5ee329657cf9bc4b2400392dd54c7d0a0ce9980ff6fa2da5590eebeec007cdb --flavour 2b --format json` |
| Validator (local) | `VERAPDF_CMD` env var → the greenfield JAR (Java 26.0.1 present; Docker is **not** available locally) |

## Per-Task Verification Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| **G7b** | The ceiling document exists **before** any DOCX work, names all five in-scope clauses and all four exclusions, and carries a `## Decision` header and an out-of-scope section (`PLAYA-DECISION.md` precedent) | unit (file assertion) | `pytest tests/test_gate_g7b.py::test_g7b_ceiling_document_exists_and_names_every_exclusion -x` | ❌ Wave 0 |
| **G7b** | No plan task widens the ceiling — the four excluded capabilities appear in no module docstring or function name under `engine/export/docx*` | unit, negative case | `pytest tests/test_gate_g7b.py::test_no_docx_module_claims_an_excluded_capability -x` | ❌ Wave 0 |
| EXPO-06 | Emitted Type0/CIDFontType2 satisfies the font rules: `/CIDToGIDMap` present, `cmap` non-empty, `/W` within 1 unit of `hmtx` (rules 6.2.11.3.2-1, 6.2.11.6-1, 6.2.11.5-1) | unit | `pytest tests/test_pdfa.py::test_emitted_type0_font_satisfies_pdfa2b_font_rules -x` | ❌ Wave 0 |
| EXPO-06 | `.notdef` never reaches a text-showing operator — `shape_glyph_names` refuses by name instead of returning `.notdef` (rule 6.2.11.8-1; **the defect measured this session**) | unit, negative case | `pytest tests/test_fonts.py::test_shape_glyph_names_refuses_rather_than_emitting_notdef -x` | ❌ Wave 0 |
| EXPO-06 | Converted output carries XMP with `pdfaid:part=2`/`conformance=B`, packet header has no `bytes=` or `encoding=` attribute (rules 6.6.2.1-1/-2/-3, 6.6.4-*) | unit | `pytest tests/test_pdfa.py::test_output_xmp_declares_pdfa_2b_and_omits_forbidden_attrs -x` | ❌ Wave 0 |
| EXPO-06 | Output intent is `/S /GTS_PDFA1` (**not** `/GTS_PDFA2`) with an `mntr`/`RGB `/v<5.0 ICC profile (rules 6.2.3-1, 6.2.4.2-1) | unit | `pytest tests/test_pdfa.py::test_output_intent_subtype_is_gts_pdfa1_with_srgb_profile -x` | ❌ Wave 0 |
| EXPO-06 | File header is `%PDF-1.[0-7]` + four bytes >127; trailer has `/ID` and no `/Encrypt`; no data after final EOF (rules 6.1.2-1/-2, 6.1.3-1/-2/-3) | unit | `pytest tests/test_pdfa.py::test_saved_file_structure_satisfies_clause_6_1 -x` | ❌ Wave 0 |
| EXPO-06 | Prohibited features deleted: `/Names /JavaScript`, catalog+page `/AA`, `/Requirements`, `/AlternatePresentations`, `/PresSteps`, `/XFA`, `/NeedAppearances` (rules 6.5.1-1, 6.5.2-1/-2, 6.11-1, 6.10-1/-2, 6.4.2-1, 6.4.1-3) | unit | `pytest tests/test_pdfa.py::test_prohibited_features_removed_and_each_removal_reported -x` | ❌ Wave 0 |
| EXPO-06 | Non-embedded **mapped** font is embedded via the identity-edit path; layout does not move (text matrix after the run unchanged) | unit + pixel-diff | `pytest tests/test_pdfa.py::test_nonembedded_base14_font_embedded_without_moving_layout -x` | ❌ Wave 0 |
| EXPO-06 | Non-embedded **unmapped** font refuses, reusing `lookup_bundled_font`'s own reason string (`/ZapfDingbats`, `/Symbol`) | unit, negative case | `pytest tests/test_pdfa.py::test_unmapped_basefont_refuses_by_name_not_substituted -x` | ❌ Wave 0 |
| EXPO-06 | Encrypted input refuses by rule ID; **never** silently saved decrypted (rule 6.1.3-2) | unit, negative case | `pytest tests/test_pdfa.py::test_encrypted_input_refuses_and_never_writes_output -x` | ❌ Wave 0 |
| EXPO-06 | Every refusal reason string begins with a veraPDF `clause-testNumber` ID (Pattern 3) | unit | `pytest tests/test_pdfa.py::test_every_refusal_reason_is_prefixed_with_a_rule_id -x` | ❌ Wave 0 |
| **G7a** | veraPDF reports `isCompliant="true"` at `--flavour 2b` for **every** tier-A fixture's converted output — the corpus assertion, not a spot check | corpus + subprocess | `pytest -m corpus tests/test_gate_g7a.py::test_every_tier_a_conversion_validates_at_pdfa_2b -x` | ❌ Wave 0 |
| **G7a** | Conversion success count ≥ the baseline floor — stops the gate passing vacuously by refusing everything (Pitfall 4) | corpus | `pytest -m corpus tests/test_gate_g7a.py::test_conversion_success_rate_meets_baseline_floor -x` | ❌ Wave 0 |
| **G7a** | The gate can fail: a known-non-conformant veraPDF fixture is reported `isCompliant="false"` | corpus + subprocess, negative case | `pytest -m corpus tests/test_gate_g7a.py::test_gate_detects_a_known_nonconformant_fixture -x` | ❌ Wave 0 |
| **G7a** | Exit codes ∉ {0,1} are surfaced as infrastructure failure, not as a conformance regression (Pitfall 1) | unit (mocked subprocess) | `pytest tests/test_verapdf_gate.py::test_nonvalidation_exit_codes_are_not_reported_as_conformance_failures -x` | ❌ Wave 0 |
| EXPO-07 | DOCX opens as a valid OOXML package: required parts present, `word/document.xml` well-formed | unit | `pytest tests/test_export_docx.py::test_output_is_a_valid_ooxml_package -x` | ❌ Wave 0 |
| EXPO-07 | Headings inferred by font-size clustering on a fixture with a hand-measured size ratio (body vs heading) | unit | `pytest tests/test_export_docx.py::test_heading_level_inferred_from_font_size_ratio -x` | ❌ Wave 0 |
| EXPO-07 | Bold/italic runs carry through to DOCX run formatting | unit | `pytest tests/test_export_docx.py::test_bold_and_italic_survive_to_docx_runs -x` | ❌ Wave 0 |
| EXPO-07 | Inline images placed; ruled table becomes a table | unit | `pytest tests/test_export_docx.py::test_inline_image_and_ruled_table_round_trip -x` | ❌ Wave 0 |
| EXPO-07 | **Ceiling held:** an unruled table and a 2-column page emit plain paragraphs, not a table / not reordered text | unit, negative case | `pytest tests/test_export_docx.py::test_unruled_table_and_multicolumn_degrade_to_paragraphs -x` | ❌ Wave 0 |
| EXPO-07 | No second extraction path — `engine.export.docx` consumes `engine.blocks`, never re-parses (extends A-7.5's scan to the DOCX module) | unit | `pytest tests/test_export_single_path.py::test_docx_reuses_open_run_index_no_second_parse -x` | ❌ Wave 0 |
| EXPO-08 | Warning counts are computed from the **same** `list[Block]` the writer consumes — writer output and warning cannot disagree | unit | `pytest tests/test_export_docx.py::test_warning_counts_match_what_the_writer_actually_emitted -x` | ❌ Wave 0 |
| EXPO-08 | Warning names *this* document's degradations ("3 tables and a 2-column section detected"), not a generic string | unit | `pytest tests/test_export_docx.py::test_warning_names_this_documents_specific_degradations -x` | ❌ Wave 0 |
| EXPO-08 | A document with no degradations produces no warning (negative case — prevents a permanently-on banner) | unit, negative case | `pytest tests/test_export_docx.py::test_clean_document_produces_no_warning -x` | ❌ Wave 0 |
| **D-8.5** | Nothing outside `engine/export/docx*` imports it or imports `docx` (AST scan) | unit | `pytest tests/test_docx_cuttable.py::test_nothing_outside_the_docx_subtree_imports_it -x` | ❌ Wave 0 |
| **D-8.5** | `python-docx` is an optional dependency group, not a core dependency | unit | `pytest tests/test_docx_cuttable.py::test_python_docx_is_optional_not_core -x` | ❌ Wave 0 |
| **D-8.5** | The literal criterion: deleting the DOCX modules leaves the rest of the suite green | corpus (phase gate only) | `pytest -m corpus tests/test_docx_cuttable.py::test_suite_passes_with_docx_modules_deleted -x` | ❌ Wave 0 |
| ENG-07 | The DOCX optional extra is actually scanned by the AGPL gate (`uv sync --locked --all-extras`) | unit | `pytest tests/test_license_gate.py::test_optional_extras_are_installed_before_the_gate_runs -x` | ❌ Wave 0 |

## Sampling Rate

- **Per task commit:** `uv run --frozen pytest -q -m "not corpus"` — the whole unit tier above,
  including both cheap cuttability assertions (AST scan + `pyproject.toml` check) and the G7b file
  assertion. All run without Docker, so they are green on the local machine where Docker is absent.
- **Per wave merge:** `uv run --frozen pytest -q` (adds the `corpus`-marked veraPDF fixture sweep
  and the delete-and-run cuttability proof) + `uv run --frozen mypy engine/` +
  `uv run --frozen python tools/license_gate.py`.
- **Phase gate:** full suite green, **plus** the real G7a run — `harness/verapdf_gate.py` over the
  complete tier-A/B/C fixture corpus through the pinned image in CI (not the local JAR), and the
  conversion-success floor re-measured and recorded — before `/gsd:verify-work`.

## Wave 0 Requirements

- [ ] **`DOCX-CEILING.md` + `tests/test_gate_g7b.py`** — ordered **first**, before any DOCX task.
      This is the gate, not documentation of it.
- [ ] **The unmodified-baseline measurement** — run veraPDF over the tier-A fixtures *before* the
      converter exists, to establish the success floor Pitfall 4's assertion needs. Cannot be
      recovered later; once the converter exists there is no baseline.
- [ ] `engine/export/pdfa.py`, `tests/test_pdfa.py`, `tests/test_gate_g7a.py`,
      `harness/verapdf_gate.py`, `tests/test_verapdf_gate.py` — none exist
      (`find . -iname "*pdfa*"` returns nothing)
- [ ] `engine/export/docx.py` (+ warning), `tests/test_export_docx.py`,
      `tests/test_docx_cuttable.py` — none exist
- [ ] `.github/workflows/verapdf.yml` — new workflow; `Dockerfile.ci` unchanged
- [ ] `pyproject.toml` — `[project.optional-dependencies] docx`; the scoped `docx.*` mypy override;
      and `license-gate.yml` changed to `uv sync --locked --all-extras`
- [ ] **Fixture gap inherited from A-7.4:** the 217-document corpus has zero multi-column documents,
      three `tables`, and no `headings` category. EXPO-07's heading test and EXPO-08's
      "2-column section detected" test both need constructed fixtures
      (`tools/build_mixed_fixture.py` is the precedent). **If Phase 7 builds these under A-7.4,
      Phase 8 reuses them — the planner should check before duplicating.**
- [ ] **Phase 7 dependency, stated sharply:** A-7.1's `RunRecord` extension (`font_size_pt`, font
      identity/style, page geometry) must have landed. Phase 8's heading inference is unbuildable
      without it, and it is a Phase 7 *Wave 0* item, not a Phase 7 headline deliverable.
- [ ] **Phase 3 defect:** the `.notdef` guard in `shape_glyph_names`. Small, but it changes Phase 3
      behaviour and should be flagged to the maintainer rather than folded in silently.

---

## Manual-Only Verifications

| Check | Why it cannot be automated | Recorded where |
|---|---|---|
| G7b: the DOCX scope ceiling is written down BEFORE work starts | The gate is satisfied by a document existing with the right content. Automatable only as a file assertion; that it says the right thing is human review. | `DOCX-CEILING.md`, following the `PLAYA-DECISION.md` / `G2B-GATE-RESULTS.md` shape |
| A converted DOCX opens correctly in Word and looks like the source | No headless Word. Structural assertions on the OOXML are automated; visual fidelity is not. | A dated results doc |
| The EXPO-08 pre-conversion warning names the right degradations for a specific document | The warning's *content* is derived from the block-structure layer and asserted; that it matches what a human sees degrade is a review. | A dated results doc |
| PDF/A output opens without complaint in Acrobat's own preflight | veraPDF is the CI gate; Acrobat is the second opinion the market actually cares about. Same pattern as G2b's viewer checks. | A dated results doc |

---

## Validation Sign-Off

- [ ] Every requirement ID in this phase appears in at least one row of the verification map
- [ ] Every `❌ Wave 0` file has an owning task in a plan
- [ ] Every manual-only check has a named results document and an owning task
- [ ] The phase gate rows run green in CI, on Linux
- [ ] No row was dropped for being inconvenient to automate — it became a manual check instead

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
