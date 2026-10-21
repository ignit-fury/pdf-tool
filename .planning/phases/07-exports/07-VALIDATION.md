---
phase: 7
slug: exports
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-30
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived verbatim from `07-RESEARCH.md` § Validation Architecture. Task IDs are filled in by the
> planner; every command below was written to be runnable, and every file marked `❌ Wave 0` does not
> exist yet.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| Framework | pytest ≥9.1.1 (already configured) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths=["tests"]`, `corpus` marker for full-corpus-sweep tests |
| Quick run command | `uv run --frozen pytest -q -m "not corpus"` |
| Full suite command | `uv run --frozen pytest -q` |
| Type check | `uv run --frozen mypy engine/` (strict; zero `# type: ignore`) |

## Per-Task Verification Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| EXPO-05 | No second extraction path — static AST scan (generalizes the pre-existing, currently-unenforced docstring convention) | unit | `pytest tests/test_export_single_path.py::test_only_playa_boundary_imports_playa -x` | ❌ Wave 0 |
| EXPO-05 | No second extraction path — runtime call-count proof that export functions reuse an already-open `RunIndex` | unit | `pytest tests/test_export_single_path.py::test_export_reuses_open_run_index_no_second_parse -x` | ❌ Wave 0 |
| EXPO-05 | Plain text export matches `RunRecord.display_text` joined per page, in reading order | unit | `pytest tests/test_export_text.py::test_plain_text_matches_display_text -x` | ❌ Wave 0 |
| EXPO-05 | Markdown export: headings inferred from font-size clustering, on a fixture with a known, hand-measured size ratio | unit + corpus | `pytest tests/test_blocks.py::test_heading_detected_from_font_size_ratio -x` | ❌ Wave 0 |
| EXPO-05 | HTML export reuses the SAME `engine.blocks` output Markdown does — no second structure-inference pass | unit | `pytest tests/test_export_html.py::test_html_and_markdown_share_block_structure -x` | ❌ Wave 0 |
| EXPO-01 | PNG/JPEG export at 150 (screen) and 300 (print) DPI defaults, per-page | unit | `pytest tests/test_export_images.py::test_dpi_defaults_150_and_300 -x` | ❌ Wave 0 |
| EXPO-01 | All-pages-as-zip contains one file per page, correctly named | unit | `pytest tests/test_export_images.py::test_all_pages_zip_contains_every_page -x` | ❌ Wave 0 |
| EXPO-02 | Compress is lossless by default — `masked_pixel_diff(before, after) == 0` when downsampling is not selected | unit + pixel-diff | `pytest tests/test_compress.py::test_lossless_compress_zero_pixel_diff -x` | ❌ Wave 0 |
| EXPO-02 | Compress reduces size on a real corpus document (structural: object-stream packing + Flate recompression) | corpus | `pytest -m corpus tests/test_compress.py::test_corpus_compress_reduces_size -x` | ❌ Wave 0 |
| EXPO-02 | Image downsampling is explicit/labelled and shows before/after size — negative case: downsampling never fires unless explicitly requested | unit, negative case | `pytest tests/test_compress.py::test_downsample_never_fires_by_default -x` | ❌ Wave 0 |
| EXPO-03 | Split output passes `qpdf --check` | unit + subprocess | `pytest tests/test_split.py::test_split_output_passes_qpdf_check -x` | ❌ Wave 0 |
| EXPO-03 | Split — masked differential diff confined to the intended change (each retained page pixel-identical, same-engine, to its original render) in all three engines | corpus + pixel-diff | `pytest -m corpus tests/test_gate_g6.py::test_split_confined_diff_three_engines -x` | ❌ Wave 0 |
| EXPO-04 | Flatten output passes `qpdf --check` | unit + subprocess | `pytest tests/test_flatten.py::test_flatten_output_passes_qpdf_check -x` | ❌ Wave 0 |
| EXPO-04 | Flatten — masked differential diff confined to the union of flattened annotation Rects (Pattern 4's precise definition), in all three engines | corpus + pixel-diff | `pytest -m corpus tests/test_gate_g6.py::test_flatten_confined_diff_three_engines -x` | ❌ Wave 0 |
| G6 criterion 1 | Codebase-wide: a search finds no second extraction path (the ROADMAP's own literal wording, as a repo-wide sweep beyond just the export modules) | unit | `pytest tests/test_export_single_path.py::test_only_playa_boundary_imports_playa -x` (same test as EXPO-05's first row — this IS the criterion, not a separate check) | ❌ Wave 0 |
| G6 criterion 3 | Compress before/after size reported; preview required when downsampling selected (UI-adjacent, server computes the numbers) | unit | `pytest tests/test_compress.py::test_compress_report_includes_before_after_size -x` | ❌ Wave 0 |

## Sampling Rate

- **Per task commit:** `uv run --frozen pytest -q -m "not corpus"` (fast unit tests — hand-picked
  fixtures, including the AST-scan and call-count single-path proofs, which need no corpus at all and
  should run on every commit as cheaply as `mypy`)
- **Per wave merge:** `uv run --frozen pytest -q` (includes `corpus`-marked full-sweep tests) +
  `uv run --frozen mypy engine/`
- **Phase gate:** Full suite green, plus the actual G6 split/flatten harness runs (reusing
  `harness/masked_diff.py` and `harness/run_corpus_harness.py`'s cross-engine machinery unmodified,
  per Don't Hand-Roll), before `/gsd:verify-work`

## Wave 0 Requirements

- [ ] `engine/records.py`, `engine/clusterer.py`, `engine/index.py`, `engine/encoding_table.py` —
      the Pattern 1 index extension (font_size_pt, base_font/style, page geometry) — **blocks every
      other Wave in this phase transitively via `engine.blocks`**
- [ ] `engine/blocks.py` — D-7.2's own module, plus its test file `tests/test_blocks.py`
- [ ] `engine/export/` package (text.py, markdown.py, html.py, images.py, compress.py, split.py,
      flatten.py) — does not exist yet, confirmed by `find . -iname "*export*"` this session
- [ ] `tests/test_export_single_path.py` — both the static AST scan and the runtime call-count proof
- [ ] `tests/test_gate_g6.py` — the phase gate as an explicit, named test, matching Phase 3's
      `test_gate_g2a.py`/`test_gate_g2b.py` precedent
- [ ] Corpus fixture gap: no multi-column-tagged document, only 3 `tables`-tagged documents, in the
      current 217-document public corpus (`corpus/manifest.json`, measured this session) — construct
      or source fixtures for the block-structure layer's tests, following Phase 2's own
      `tools/build_mixed_fixture.py` precedent for a deliberately-constructed fixture where the corpus
      lacked real-world coverage
- [ ] A2's empirical verification (does `pikepdf.Pdf.new()` + `dst.pages.append()` deep-copy shared
      `/Resources`?) — cheap, corpus-testable, should land before `remove_unreferenced_resources()` is
      called anywhere in the split path

---

## Manual-Only Verifications

| Check | Why it cannot be automated | Recorded where |
|---|---|---|
| Compress before/after **preview** is faithful (EXPO-02) | ROADMAP criterion 3 requires a preview when image downsampling is selected. Size numbers are automated; that the preview represents the actual output is a visual check. | A dated results doc |
| Markdown/HTML output reads correctly on a heading-heavy document | The block-structure layer's inference quality is a judgement call above the level any assertion reaches. Structural assertions (block types, ordering) are automated. | A dated results doc |
| Flatten output is visually correct where it *intends* to change | D-7.4's "confined to the intended change" is asserted mechanically, but flatten changes rendering by design; a human confirms the change is the intended one. | A dated results doc |

---

## Validation Sign-Off

- [ ] Every requirement ID in this phase appears in at least one row of the verification map
- [ ] Every `❌ Wave 0` file has an owning task in a plan
- [ ] Every manual-only check has a named results document and an owning task
- [ ] The phase gate rows (`G7-*`) run green in CI, on Linux
- [ ] No row was dropped for being inconvenient to automate — it became a manual check instead

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
