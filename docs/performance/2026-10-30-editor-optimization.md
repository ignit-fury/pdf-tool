# Editor performance pass — 2026-10-30

Measured against commit `2c881453d3556298a5891c36c46fe231936c6f86` on the local macOS development machine. These are component benchmarks, not claims that every document or export becomes equally faster.

## Implemented

- Search checks for a candidate before building Unicode grapheme/word boundaries and inverse normalization mappings. Nonmatching runs still participate in duplicate-address detection. Matching runs retain all replacement safety checks.
- Search creates at most one grapheme and one word segmenter per invocation, rather than per matching run. No document text cache survives the search.
- Page text detection resolves font style and identity per text-showing operator rather than per glyph. Keys retain stream path, part and operator offset; font changes and resource ownership remain distinct.
- Export layout calculates each run's glyph bounds once per page and shares them across line grouping, spacing and table layout. Geometry is discarded at the end of the page; subsequent exports observe edited runs.
- CID width lookup indexes the requested width directly instead of copying the complete nested width array. Defaults, malformed-tail handling and first-match semantics are unchanged.

No dependency, API, deployment or worker-count changes. Worker isolation, the 20-second CPU limit, stream limits, atomic editing and geometry checks remain in place. Original corpus files are not modified.

## Measurements

| Component/workload | Before | After | Scope |
| --- | ---: | ---: | --- |
| Rare-word search: 20,001 indexed runs, two hits | ~597 ms | 2–5 ms | Synthetic, cached server projections; excludes indexing/network |
| Common-word search: 20,000 matching runs | ~644 ms | ~411 ms | Synthetic, one match per run; segmenter reuse compared with candidate-skipping already enabled |
| Detection: all 40 pages, 3,000 runs | 1.406 CPU s | 1.313 CPU s | Median of three fresh RunIndex instances |
| Export layout: 40 already-indexed pages | 353 CPU ms | 56 CPU ms | Median of three; excludes parsing and file packaging |
| CID widths: 1,000 lookups in a 20,000-entry array | 583 ms | 5 ms | Synthetic microbenchmark, not end-to-end replacement |
| Bounded 675-edit batch | Previous audit exceeded 20 CPU s | Preview 17.873–18.279 CPU s; apply 18.093 CPU s | Actual isolated worker, unchanged limits |

Real-PDF workload: `corpus/public/govdocs1_013_013050.pdf`, SHA-256 `d0a3b06606378733a2ec96cfa01e3b12c111d13059d070e3e039b751347a4529`.

Detection before/after hashes matched for all run IDs, text, font/style/identity metadata and editability results. Plain-text, Markdown and HTML export bytes matched exactly before/after the geometry optimization. The batch performance tests verify refusal counts, atomic apply, unchanged source bytes and preview/apply agreement.

## Verification

- Frontend: 205 tests passed.
- Production build passed; existing bundle-size warning remains.
- Strict mypy: 40 source files passed.
- Targeted encoding, fit and real-worker batch tests: 65 passed. Final-code batch rerun: both tests passed in 59.30 seconds (675 accepted edits; preview and apply stayed below the unchanged 20-second per-worker CPU limit).
- New search, layout and font-lookup regression tests were observed failing before their respective changes and passing afterward.
- Regular Python regression suite: 879 passed, six sandbox-related failures, five skipped, 34 corpus tests deselected. Rerunning the affected two test modules with local permissions passed all 26 tests, resolving all six failures: 885 unique regular-suite tests passed overall. The failures were four loopback socket bindings, process inspection (`/bin/ps`), and the macOS HEIC codec probe; application code was not changed to bypass them.
- The unrestricted Python suite was stopped during the long all-corpus clustering sweep: 76 passed, one skipped before interruption. This is not a completed all-corpus rerun.
- No fresh manual browser journey was run for this performance pass.

Commands:

```sh
npm --prefix client test
npm --prefix client run build
.venv/bin/python -m mypy engine server --no-incremental
.venv/bin/python -m pytest -m 'not corpus'
.venv/bin/python -m pytest tests/test_encoding_table.py tests/test_fit.py tests/test_find_replace_performance.py -q -s
```

PDF/A integration checks additionally use the existing local `VERAPDF_CMD` and `JAVA_HOME` configuration. Linux and deployed-CDN gates require their corresponding environments; no deployment was attempted.

## Remaining limits

This pass does not speed up every operation equally. Raster image exports, compression, PDF/A conversion and browser PDF loading have no newly measured speedup. The batch test is still close to the CPU ceiling on this machine; large or complex batches can still exceed the existing limit. Full re-interpretation after each text edit remains necessary to verify that surrounding content has not moved. The number of disposable server workers is unchanged; these changes reduce work within them rather than retaining document parsers across requests.
