# Public PDF corpus compatibility — 2026-10-22

All 217 PDFs were tested. Reading covered all 8,254 pages. Editing was sampled: 164 PDFs had at least one independently verified edit; 53 had no verified edit in the sample. Every original PDF remained byte-for-byte unchanged. This is a local compatibility audit, not universal PDF editing or public-release certification.

Implementation: `5457863` plus the earlier page-scope fix `49f0074`. The final edit audit has one pipeline fingerprint across all 217 files, with no code changes during any file test. Read-critical files match every recorded read-audit stage; rewrite-only changes during that earlier pass do not affect its read results.

## Coverage and results

| Check | Result |
|---|---|
| Read/classification | 8,254 pages attempted; 8,253 classified; one malformed page |
| Read input integrity | All 217 before/after hashes match a fresh final hash check |
| Read pipeline | 21,402,659 glyphs; 1,149,462 runs; 207 PDFs contain classified editable candidates |
| Edit samples | 238 page samples; 764 candidate cases, each previewed and applied against the original |
| Verified identity + shorter pairs | 154 PDFs: 103 automatic and 51 with an explicit replacement font |
| Partially verified samples | 10 PDFs with at least one verified edit but no complete verified pair |
| Returned edited outputs | 346; 333 passed exact normalized full-page text replacement checks |
| Unverifiable output text | 13 output records: source text could not be matched independently; not counted as verified |
| Detected corrupt / wrong-text outputs | 0 / 0 |
| Preview/apply disagreements | 0 |
| Edit-worker crashes, timeouts or audit-process failures | None in final run |

Identity replacement and shorter replacement must both verify on the same run/font mode to earn a complete pair. A classified editable candidate can still fail a writer guard. A refused sample does not prove that every run or page in that PDF is uneditable.

Editing tries at most three candidate runs among the first three pages, stopping after a successful pair. The all-page read pass also found editable text on zero-based page 5 of `govdocs1_009_009097.pdf`, which was added explicitly. No claim that all pages were edit-tested.

## Fixes delivered

- Plan only the recipe-addressed pages, avoiding whole-document classification for one edit. The 2,026-page FAR document now passes identity and shorter edits in the final audit (27.8 seconds for inspection, preview/apply pairs and independent output checks combined).
- Supply legitimate omitted Standard 14 widths using known Adobe metrics and the actual encoding.
- Replace raw embedded Type1/CFF fonts through the bundled-font path when shaping requires it. Known names match exactly; unmapped names permit explicit Serif/Sans/Mono replacement. Planning and writing now use the same chosen font.
- Keep clustered run addresses within their physical content-stream part. Preserve empty showing instructions and numeric pen advances without shifting glyph-derived instruction ordinals.
- Reuse per-worker stream decoding and bounded font histories. The dense 006032 page response dropped from a killed 20.24 seconds to 1.27 seconds in the focused measurement.
- Map malformed parser syntax to `PDF_INVALID`, with no partial editable-page result.
- Disclose detectable structural refusals early and make browser preview run the actual splice/layout guards in disposable worker scratch, returning no output bytes.

## Remaining limits

| Sample outcome | PDFs |
|---|---|
| Edits refused by safety/fit/font guards | 35 |
| No editable candidate in sampled pages | 10 |
| Returned output, independent text never verified | 6 |
| Page input/resource refusal | 2 |

Known unsupported cases include split content-stream tokens, operators shared by several text runs, unresolved instruction correlation, quote-operator state effects, missing Unicode mappings, Type3/symbolic fonts, unavailable replacement glyphs, excessive width and edits that would move following text. These guards were retained.

`govdocs1_011_011089.pdf` returns `PDF_INVALID` for malformed inline-image termination. `govdocs1_002_002166.pdf` returns `DOCUMENT_LIMIT` on sampled pages; resource safeguards were retained. The raw read audit uses a different, diagnostic path and therefore reports no read-scan resource refusals; that does not override service limits.

Three sampled files retain a font-resolution refusal because their font dictionaries lack required width addressing (`/FirstChar`): `govdocs1_004_004130.pdf`, `govdocs1_010_010124.pdf`, and `govdocs1_014_014103.pdf`. Unknown source widths are not guessed.

Outputs marked text-unverifiable passed structural/render checks, but remain unproven text edits. They need manual inspection. They are not counted as successful independent verification.

## Verification boundaries

Each returned output was checked with pikepdf syntax/page count, qpdf (exit 0 or warning-only 3), and a PDFium render of the edited page at scale 0.25. PDFium extraction verifies exactly one requested replacement in the normalized full-page text, tolerating whitespace and compatibility ligatures. This does not prove pixel preservation, and the corpus audit performs no source/output pixel comparison.

- Final regression run: **473 passed, 5 skipped, 25 corpus tests deselected**. The skips are Linux resource/seccomp gates and the unavailable live CDN gate.
- Latest focused font/recipe/preview/render run: **94 passed**, including all three renderer/font gates. An earlier integrated fix run passed 143 tests; the complete historical five-page correlation sweep passed after its measured failure set shrank from 89 to 4 (no new failures).
- Initial full suite: 485 passed, 5 skipped, 5 failures. Four failures were sandbox-only mock HTTP binds and passed outside the sandbox; the fifth was the reduced historical correlation baseline, which passed after evidence-based updating. Read-critical code stayed unchanged afterward.
- Strict mypy: all 28 engine/server source files clean.
- Client helpers: 12 passed; production build passed (existing chunk-size warning).
- Independent code review found and verified correction of the font handoff mismatch; [review record](corpus-code-review-2026-10-22.md). Linux/container and live CDN release verification remain open.

## Reproduce

```sh
.venv/bin/python tools/audit_corpus_edits.py \
  --output .planning/audits/corpus-edits-2026-10-22.json \
  --extra-page govdocs1_009_009097.pdf:5
```

Per-attempt identifiers, refusal reasons, source hashes and output checks: [edit JSON](corpus-edits-2026-10-22.json). Every-page buckets, run counts and source hashes: [read JSON](corpus-read-2026-10-22.json). Detailed root causes: [debug record](../debug/corpus-compatibility.md).

## Per-file edit samples

Pages below are one-based. “Explicit font” means the audit supplied a replacement family in the recipe; it is not an automatic font identity claim.

| PDF | Sampled pages | Outcome | Verified outputs | Explicit font tested |
|---|---|---|---:|---|
| [far_federal_acquisition_regulation.pdf](../../corpus/public/far_federal_acquisition_regulation.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_000_000009.pdf](../../corpus/public/govdocs1_000_000009.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_000_000010.pdf](../../corpus/public/govdocs1_000_000010.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_000_000011.pdf](../../corpus/public/govdocs1_000_000011.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_000_000013.pdf](../../corpus/public/govdocs1_000_000013.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_000_000015.pdf](../../corpus/public/govdocs1_000_000015.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_000_000016.pdf](../../corpus/public/govdocs1_000_000016.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_000_000018.pdf](../../corpus/public/govdocs1_000_000018.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_000_000019.pdf](../../corpus/public/govdocs1_000_000019.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_000_000024.pdf](../../corpus/public/govdocs1_000_000024.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_000_000025.pdf](../../corpus/public/govdocs1_000_000025.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_000_000026.pdf](../../corpus/public/govdocs1_000_000026.pdf) | 1 | At least one edit verified; no complete pair | 1 | Yes |
| [govdocs1_000_000028.pdf](../../corpus/public/govdocs1_000_000028.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_000_000029.pdf](../../corpus/public/govdocs1_000_000029.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_000_000135.pdf](../../corpus/public/govdocs1_000_000135.pdf) | 1 | Output readable; independent text unverified | 0 | No |
| [govdocs1_000_000137.pdf](../../corpus/public/govdocs1_000_000137.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_001_001024.pdf](../../corpus/public/govdocs1_001_001024.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_001_001028.pdf](../../corpus/public/govdocs1_001_001028.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_001_001029.pdf](../../corpus/public/govdocs1_001_001029.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_001_001030.pdf](../../corpus/public/govdocs1_001_001030.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_001_001031.pdf](../../corpus/public/govdocs1_001_001031.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_001_001032.pdf](../../corpus/public/govdocs1_001_001032.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_001_001033.pdf](../../corpus/public/govdocs1_001_001033.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_001_001034.pdf](../../corpus/public/govdocs1_001_001034.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_001_001035.pdf](../../corpus/public/govdocs1_001_001035.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_001_001036.pdf](../../corpus/public/govdocs1_001_001036.pdf) | 1 | At least one edit verified; no complete pair | 1 | No |
| [govdocs1_001_001037.pdf](../../corpus/public/govdocs1_001_001037.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_001_001038.pdf](../../corpus/public/govdocs1_001_001038.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_002_002014.pdf](../../corpus/public/govdocs1_002_002014.pdf) | 1, 2, 3 | No editable candidate in sample | 0 | No |
| [govdocs1_002_002021.pdf](../../corpus/public/govdocs1_002_002021.pdf) | 1 | Identity + shorter pair verified | 3 | Yes |
| [govdocs1_002_002145.pdf](../../corpus/public/govdocs1_002_002145.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_002_002154.pdf](../../corpus/public/govdocs1_002_002154.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_002_002166.pdf](../../corpus/public/govdocs1_002_002166.pdf) | 1, 2, 3 | Page blocked by input/resource guard | 0 | No |
| [govdocs1_002_002167.pdf](../../corpus/public/govdocs1_002_002167.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_002_002168.pdf](../../corpus/public/govdocs1_002_002168.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_002_002169.pdf](../../corpus/public/govdocs1_002_002169.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_002_002173.pdf](../../corpus/public/govdocs1_002_002173.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_002_002174.pdf](../../corpus/public/govdocs1_002_002174.pdf) | 1 | Output readable; independent text unverified | 0 | No |
| [govdocs1_002_002176.pdf](../../corpus/public/govdocs1_002_002176.pdf) | 1, 2, 3 | No editable candidate in sample | 0 | No |
| [govdocs1_002_002177.pdf](../../corpus/public/govdocs1_002_002177.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_003_003005.pdf](../../corpus/public/govdocs1_003_003005.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_003_003039.pdf](../../corpus/public/govdocs1_003_003039.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_003_003049.pdf](../../corpus/public/govdocs1_003_003049.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_003_003060.pdf](../../corpus/public/govdocs1_003_003060.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_003_003063.pdf](../../corpus/public/govdocs1_003_003063.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_003_003064.pdf](../../corpus/public/govdocs1_003_003064.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_003_003065.pdf](../../corpus/public/govdocs1_003_003065.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_003_003066.pdf](../../corpus/public/govdocs1_003_003066.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_003_003067.pdf](../../corpus/public/govdocs1_003_003067.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_003_003072.pdf](../../corpus/public/govdocs1_003_003072.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_003_003073.pdf](../../corpus/public/govdocs1_003_003073.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_003_003074.pdf](../../corpus/public/govdocs1_003_003074.pdf) | 1 | At least one edit verified; no complete pair | 1 | Yes |
| [govdocs1_004_004050.pdf](../../corpus/public/govdocs1_004_004050.pdf) | 1, 2, 3 | No editable candidate in sample | 0 | No |
| [govdocs1_004_004116.pdf](../../corpus/public/govdocs1_004_004116.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_004_004117.pdf](../../corpus/public/govdocs1_004_004117.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_004_004119.pdf](../../corpus/public/govdocs1_004_004119.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_004_004121.pdf](../../corpus/public/govdocs1_004_004121.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_004_004122.pdf](../../corpus/public/govdocs1_004_004122.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_004_004124.pdf](../../corpus/public/govdocs1_004_004124.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_004_004125.pdf](../../corpus/public/govdocs1_004_004125.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_004_004126.pdf](../../corpus/public/govdocs1_004_004126.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_004_004130.pdf](../../corpus/public/govdocs1_004_004130.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_004_004132.pdf](../../corpus/public/govdocs1_004_004132.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_004_004133.pdf](../../corpus/public/govdocs1_004_004133.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_005_005000.pdf](../../corpus/public/govdocs1_005_005000.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_005_005004.pdf](../../corpus/public/govdocs1_005_005004.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_005_005005.pdf](../../corpus/public/govdocs1_005_005005.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_005_005009.pdf](../../corpus/public/govdocs1_005_005009.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_005_005010.pdf](../../corpus/public/govdocs1_005_005010.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_005_005012.pdf](../../corpus/public/govdocs1_005_005012.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_005_005013.pdf](../../corpus/public/govdocs1_005_005013.pdf) | 1 | At least one edit verified; no complete pair | 1 | Yes |
| [govdocs1_005_005015.pdf](../../corpus/public/govdocs1_005_005015.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_005_005020.pdf](../../corpus/public/govdocs1_005_005020.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_005_005021.pdf](../../corpus/public/govdocs1_005_005021.pdf) | 1 | Identity + shorter pair verified | 3 | No |
| [govdocs1_005_005084.pdf](../../corpus/public/govdocs1_005_005084.pdf) | 1, 2 | Identity + shorter pair verified | 2 | No |
| [govdocs1_005_005086.pdf](../../corpus/public/govdocs1_005_005086.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_006_006027.pdf](../../corpus/public/govdocs1_006_006027.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_006_006029.pdf](../../corpus/public/govdocs1_006_006029.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_006_006031.pdf](../../corpus/public/govdocs1_006_006031.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_006_006032.pdf](../../corpus/public/govdocs1_006_006032.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_006_006034.pdf](../../corpus/public/govdocs1_006_006034.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_006_006037.pdf](../../corpus/public/govdocs1_006_006037.pdf) | 1 | Output readable; independent text unverified | 0 | No |
| [govdocs1_006_006040.pdf](../../corpus/public/govdocs1_006_006040.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_006_006046.pdf](../../corpus/public/govdocs1_006_006046.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_006_006047.pdf](../../corpus/public/govdocs1_006_006047.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_006_006048.pdf](../../corpus/public/govdocs1_006_006048.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_006_006050.pdf](../../corpus/public/govdocs1_006_006050.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_006_006053.pdf](../../corpus/public/govdocs1_006_006053.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_007_007020.pdf](../../corpus/public/govdocs1_007_007020.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_007_007024.pdf](../../corpus/public/govdocs1_007_007024.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_007_007030.pdf](../../corpus/public/govdocs1_007_007030.pdf) | 1, 2, 3 | No editable candidate in sample | 0 | No |
| [govdocs1_007_007042.pdf](../../corpus/public/govdocs1_007_007042.pdf) | 1 | Output readable; independent text unverified | 0 | No |
| [govdocs1_007_007071.pdf](../../corpus/public/govdocs1_007_007071.pdf) | 1, 2 | At least one edit verified; no complete pair | 3 | Yes |
| [govdocs1_007_007074.pdf](../../corpus/public/govdocs1_007_007074.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_007_007075.pdf](../../corpus/public/govdocs1_007_007075.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_007_007081.pdf](../../corpus/public/govdocs1_007_007081.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_007_007083.pdf](../../corpus/public/govdocs1_007_007083.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_007_007084.pdf](../../corpus/public/govdocs1_007_007084.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_007_007087.pdf](../../corpus/public/govdocs1_007_007087.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_007_007089.pdf](../../corpus/public/govdocs1_007_007089.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_007_007091.pdf](../../corpus/public/govdocs1_007_007091.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_007_007092.pdf](../../corpus/public/govdocs1_007_007092.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_008_008006.pdf](../../corpus/public/govdocs1_008_008006.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_008_008008.pdf](../../corpus/public/govdocs1_008_008008.pdf) | 1 | At least one edit verified; no complete pair | 3 | Yes |
| [govdocs1_008_008009.pdf](../../corpus/public/govdocs1_008_008009.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_008_008010.pdf](../../corpus/public/govdocs1_008_008010.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_008_008012.pdf](../../corpus/public/govdocs1_008_008012.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_008_008015.pdf](../../corpus/public/govdocs1_008_008015.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_008_008016.pdf](../../corpus/public/govdocs1_008_008016.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_008_008022.pdf](../../corpus/public/govdocs1_008_008022.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_008_008024.pdf](../../corpus/public/govdocs1_008_008024.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_008_008025.pdf](../../corpus/public/govdocs1_008_008025.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_008_008028.pdf](../../corpus/public/govdocs1_008_008028.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_008_008029.pdf](../../corpus/public/govdocs1_008_008029.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_008_008032.pdf](../../corpus/public/govdocs1_008_008032.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_008_008034.pdf](../../corpus/public/govdocs1_008_008034.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_009_009001.pdf](../../corpus/public/govdocs1_009_009001.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_009_009002.pdf](../../corpus/public/govdocs1_009_009002.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_009_009011.pdf](../../corpus/public/govdocs1_009_009011.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_009_009013.pdf](../../corpus/public/govdocs1_009_009013.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_009_009015.pdf](../../corpus/public/govdocs1_009_009015.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_009_009052.pdf](../../corpus/public/govdocs1_009_009052.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_009_009055.pdf](../../corpus/public/govdocs1_009_009055.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_009_009057.pdf](../../corpus/public/govdocs1_009_009057.pdf) | 1 | Identity + shorter pair verified | 3 | Yes |
| [govdocs1_009_009059.pdf](../../corpus/public/govdocs1_009_009059.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_009_009060.pdf](../../corpus/public/govdocs1_009_009060.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_009_009067.pdf](../../corpus/public/govdocs1_009_009067.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_009_009069.pdf](../../corpus/public/govdocs1_009_009069.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_009_009077.pdf](../../corpus/public/govdocs1_009_009077.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_009_009097.pdf](../../corpus/public/govdocs1_009_009097.pdf) | 1, 2, 3, 6 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_010_010105.pdf](../../corpus/public/govdocs1_010_010105.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_010_010106.pdf](../../corpus/public/govdocs1_010_010106.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_010_010107.pdf](../../corpus/public/govdocs1_010_010107.pdf) | 1 | Output readable; independent text unverified | 0 | No |
| [govdocs1_010_010109.pdf](../../corpus/public/govdocs1_010_010109.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_010_010110.pdf](../../corpus/public/govdocs1_010_010110.pdf) | 1 | Output readable; independent text unverified | 0 | No |
| [govdocs1_010_010116.pdf](../../corpus/public/govdocs1_010_010116.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_010_010118.pdf](../../corpus/public/govdocs1_010_010118.pdf) | 1 | At least one edit verified; no complete pair | 2 | No |
| [govdocs1_010_010120.pdf](../../corpus/public/govdocs1_010_010120.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_010_010123.pdf](../../corpus/public/govdocs1_010_010123.pdf) | 1, 2, 3 | No editable candidate in sample | 0 | No |
| [govdocs1_010_010124.pdf](../../corpus/public/govdocs1_010_010124.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_010_010129.pdf](../../corpus/public/govdocs1_010_010129.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_010_010141.pdf](../../corpus/public/govdocs1_010_010141.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_010_010197.pdf](../../corpus/public/govdocs1_010_010197.pdf) | 1 | At least one edit verified; no complete pair | 3 | Yes |
| [govdocs1_010_010204.pdf](../../corpus/public/govdocs1_010_010204.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_011_011001.pdf](../../corpus/public/govdocs1_011_011001.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_011_011078.pdf](../../corpus/public/govdocs1_011_011078.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_011_011080.pdf](../../corpus/public/govdocs1_011_011080.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_011_011082.pdf](../../corpus/public/govdocs1_011_011082.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_011_011083.pdf](../../corpus/public/govdocs1_011_011083.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_011_011087.pdf](../../corpus/public/govdocs1_011_011087.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_011_011089.pdf](../../corpus/public/govdocs1_011_011089.pdf) | 1 | Page blocked by input/resource guard | 0 | No |
| [govdocs1_011_011093.pdf](../../corpus/public/govdocs1_011_011093.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_011_011095.pdf](../../corpus/public/govdocs1_011_011095.pdf) | 1 | At least one edit verified; no complete pair | 3 | Yes |
| [govdocs1_011_011097.pdf](../../corpus/public/govdocs1_011_011097.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_011_011098.pdf](../../corpus/public/govdocs1_011_011098.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_011_011099.pdf](../../corpus/public/govdocs1_011_011099.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_011_011105.pdf](../../corpus/public/govdocs1_011_011105.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_011_011133.pdf](../../corpus/public/govdocs1_011_011133.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_012_012014.pdf](../../corpus/public/govdocs1_012_012014.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_012_012053.pdf](../../corpus/public/govdocs1_012_012053.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_012_012082.pdf](../../corpus/public/govdocs1_012_012082.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_012_012084.pdf](../../corpus/public/govdocs1_012_012084.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_012_012087.pdf](../../corpus/public/govdocs1_012_012087.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_012_012098.pdf](../../corpus/public/govdocs1_012_012098.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_012_012102.pdf](../../corpus/public/govdocs1_012_012102.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_012_012103.pdf](../../corpus/public/govdocs1_012_012103.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_012_012156.pdf](../../corpus/public/govdocs1_012_012156.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_012_012158.pdf](../../corpus/public/govdocs1_012_012158.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_012_012159.pdf](../../corpus/public/govdocs1_012_012159.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_012_012166.pdf](../../corpus/public/govdocs1_012_012166.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_012_012170.pdf](../../corpus/public/govdocs1_012_012170.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_012_012172.pdf](../../corpus/public/govdocs1_012_012172.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_013_013043.pdf](../../corpus/public/govdocs1_013_013043.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_013_013047.pdf](../../corpus/public/govdocs1_013_013047.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_013_013048.pdf](../../corpus/public/govdocs1_013_013048.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_013_013050.pdf](../../corpus/public/govdocs1_013_013050.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_013_013064.pdf](../../corpus/public/govdocs1_013_013064.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_013_013079.pdf](../../corpus/public/govdocs1_013_013079.pdf) | 1 | Identity + shorter pair verified | 3 | Yes |
| [govdocs1_013_013083.pdf](../../corpus/public/govdocs1_013_013083.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_013_013085.pdf](../../corpus/public/govdocs1_013_013085.pdf) | 1 | Identity + shorter pair verified | 3 | Yes |
| [govdocs1_013_013093.pdf](../../corpus/public/govdocs1_013_013093.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_013_013097.pdf](../../corpus/public/govdocs1_013_013097.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_013_013100.pdf](../../corpus/public/govdocs1_013_013100.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_013_013104.pdf](../../corpus/public/govdocs1_013_013104.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_013_013107.pdf](../../corpus/public/govdocs1_013_013107.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_013_013110.pdf](../../corpus/public/govdocs1_013_013110.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_014_014009.pdf](../../corpus/public/govdocs1_014_014009.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_014_014010.pdf](../../corpus/public/govdocs1_014_014010.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_014_014027.pdf](../../corpus/public/govdocs1_014_014027.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_014_014091.pdf](../../corpus/public/govdocs1_014_014091.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [govdocs1_014_014103.pdf](../../corpus/public/govdocs1_014_014103.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_014_014114.pdf](../../corpus/public/govdocs1_014_014114.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_014_014115.pdf](../../corpus/public/govdocs1_014_014115.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_014_014118.pdf](../../corpus/public/govdocs1_014_014118.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_014_014222.pdf](../../corpus/public/govdocs1_014_014222.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_014_014226.pdf](../../corpus/public/govdocs1_014_014226.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_014_014228.pdf](../../corpus/public/govdocs1_014_014228.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_014_014229.pdf](../../corpus/public/govdocs1_014_014229.pdf) | 1 | Sampled edits refused | 0 | No |
| [govdocs1_014_014230.pdf](../../corpus/public/govdocs1_014_014230.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [govdocs1_014_014233.pdf](../../corpus/public/govdocs1_014_014233.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [invoice_1905_james_green.pdf](../../corpus/public/invoice_1905_james_green.pdf) | 1, 2, 3 | No editable candidate in sample | 0 | No |
| [invoice_book_1842.pdf](../../corpus/public/invoice_book_1842.pdf) | 1, 2, 3 | Identity + shorter pair verified | 2 | Yes |
| [irs_1040_instructions.pdf](../../corpus/public/irs_1040_instructions.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [irs_1040_tax_tables.pdf](../../corpus/public/irs_1040_tax_tables.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [irs_form_1040.pdf](../../corpus/public/irs_form_1040.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [irs_form_1040_spanish.pdf](../../corpus/public/irs_form_1040_spanish.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [irs_form_w4.pdf](../../corpus/public/irs_form_w4.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [irs_form_w9.pdf](../../corpus/public/irs_form_w9.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [irs_form_w9_encrypted.pdf](../../corpus/public/irs_form_w9_encrypted.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [irs_publication_17.pdf](../../corpus/public/irs_publication_17.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [mutopia_vocalise_abt.pdf](../../corpus/public/mutopia_vocalise_abt.pdf) | 1 | Identity + shorter pair verified | 2 | Yes |
| [nasa_graphics_standards_manual.pdf](../../corpus/public/nasa_graphics_standards_manual.pdf) | 1 | Identity + shorter pair verified | 2 | No |
| [vector_outlined_text_sample.pdf](../../corpus/public/vector_outlined_text_sample.pdf) | 1 | No editable candidate in sample | 0 | No |
| [verapdf_inline_image_fixture.pdf](../../corpus/public/verapdf_inline_image_fixture.pdf) | 1 | No editable candidate in sample | 0 | No |
| [verapdf_isartor_malformed_trailer.pdf](../../corpus/public/verapdf_isartor_malformed_trailer.pdf) | 1 | No editable candidate in sample | 0 | No |
| [verapdf_type3_font_fixture.pdf](../../corpus/public/verapdf_type3_font_fixture.pdf) | 1 | No editable candidate in sample | 0 | No |
| [wikipedia_zh_monthly_magazine.pdf](../../corpus/public/wikipedia_zh_monthly_magazine.pdf) | 1 | At least one edit verified; no complete pair | 2 | Yes |
