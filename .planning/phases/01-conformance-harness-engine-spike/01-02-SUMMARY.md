---
phase: 01-conformance-harness-engine-spike
plan: 02
subsystem: corpus
tags: [git-lfs, pikepdf, playa-pdf, pypdfium2, corpus, conformance, public-domain, verapdf]

# Dependency graph
requires: ["01-01"]
provides:
  - "corpus/public/ - 17 git-lfs-tracked real-world PDFs covering all 15 D-03 structural categories"
  - "corpus/manifest.json - per-file sha256, categories, source_url, license, weight_class"
  - "corpus/validate_manifest.py - validate_manifest(manifest_path, corpus_dir) -> list[str], hash + zero-count-category checks"
  - "corpus/README.md - manifest schema, category structural signatures, D-01 two-tier design note, explicit sourcing-gap disclosure"
affects: [01-03, 02-text-model, 03-rewrite-engine-font-pipeline]

# Tech tracking
tech-stack:
  added: [git-lfs]
  patterns:
    - "Category membership verified by direct pikepdf object introspection (font Subtype/Encoding/FontDescriptor/Flags/FontFile*, XObject Subtype, Annot AP, Contents array) plus a light byte-scan for BI/ID/EI inline-image tokens - never a content-stream interpreter"
    - "Visually-only-verifiable categories (justified_right_aligned, tables, vector_outlined_text) confirmed by rendering a page with pypdfium2 and eyeballing the result, recorded in manifest notes"

key-files:
  created:
    - .gitattributes
    - corpus/public/*.pdf (17 files)
    - corpus/manifest.json
    - corpus/validate_manifest.py
    - corpus/README.md
    - tests/test_corpus_manifest.py
  modified: []

key-decisions:
  - "Public tier is 17 files, not the plan's suggested 25-45 - every file was individually structurally/visually verified rather than added to pad the count (see Known Stubs / gap disclosure below for the two categories this cost)"
  - "inline_images and type3 sourced from veraPDF-corpus (CC BY 4.0) constructed conformance fixtures, not wild-harvested documents - disclosed explicitly per the phase's explicit-gap-disclosure requirement after an extensive real-world search came up empty for both"
  - "encrypted category is a real document (irs_form_w9.pdf) with owner-password + AES-256 encryption applied locally via pikepdf.Encryption - the plan's sanctioned generation method, not an independently-sourced encrypted document"
  - "malformed category uses veraPDF-corpus's Isartor PDF/A-1b broken-trailer fixture - explicitly named as the sanctioned source by the plan's own task text"

requirements-completed: [ENG-01]

# Metrics
duration: ~90min
completed: 2026-08-12
---

# Phase 1 Plan 2: Public-Tier Corpus + Manifest Summary

**Sourced 17 real-world, license-verified, git-lfs-tracked PDFs (13 wild-harvested, 1 real-document-plus-local-encryption, 3 veraPDF-corpus conformance fixtures) covering all 15 D-03 structural categories, then wrote and TDD-tested the manifest validator that cross-checks every declared sha256 and category against disk.**

## Performance

- **Duration:** ~90 min (most of it spent sourcing and structurally verifying real documents, not writing code)
- **Completed:** 2026-08-12
- **Tasks:** 2 completed
- **Files modified:** 22 (17 corpus PDFs + `.gitattributes` + `corpus/manifest.json` + `corpus/validate_manifest.py` + `corpus/README.md` + `tests/test_corpus_manifest.py`)

## Accomplishments

- `git lfs install` run, `.gitattributes` tracks `corpus/public/**/*.pdf` via git-lfs; `git lfs ls-files` confirms all 17 files are LFS pointers, not raw blobs in git history
- Sourced and **structurally verified with `pikepdf`** (font `/Subtype`, `/Encoding`, `FontDescriptor /Flags`, `/FontFile*` subtype, XObject `/Subtype`, Annot `/AP`, `/Contents` array shape, and a raw byte-scan for `BI/ID/EI`) — not asserted from filename or source alone:
  - **subset_fonts**: present in essentially every sourced document (`ABCDEF+FontName` tags)
  - **type0_identity_h**: IRS 1040 instructions, IRS Publication 17, the Chinese Wikipedia PDF, the 1842 invoice book, the Federal Acquisition Regulation — all confirmed `/Type0 /Encoding /Identity-H`
  - **cid_keyed_cff**: IRS Publication 17 embeds `NotoSansCJKjp-Regular` as `CIDFontType0`/`FontFile3 /CIDFontType0C`; IRS Form W-4 embeds `AdobePiStd` the same way; the Chinese Wikipedia PDF embeds `HiraginoSansGB-W6/W3` the same way
  - **symbolic_fonts**: IRS Form W-4's `AdobePiStd` dingbat font and the FAR's `ZapfDingbats` (`FontDescriptor` Symbolic flag bit set); Mutopia's `Emmentaler` music-notation font
  - **contents_array / form_xobjects / annotation_appearance_streams**: confirmed across the IRS forms/publications set (fillable AcroForm widgets for the first two forms, Form XObjects in the two multi-page IRS publications)
  - **ocr_scan**: `invoice_book_1842.pdf` structurally confirmed — each page has an `/Image` XObject plus a `Tr 3` (invisible) text-rendering-mode operator, the canonical Internet-Archive OCR-pipeline signature
  - **encrypted**: `irs_form_w9_encrypted.pdf` — `pikepdf.Pdf.is_encrypted` verified `True` after local owner-password + AES-256 (R=6) encryption of the real `irs_form_w9.pdf`
  - **malformed**: Isartor PDF/A-1b broken-trailer fixture from veraPDF-corpus
- **Visually verified with `pypdfium2` renders** (read as images, eyeballed) where structural probing alone can't confirm the category:
  - **justified_right_aligned**: IRS 1040 instructions page 6 — fully justified 3-column body text
  - **tables**: IRS 2025 Tax Table booklet page 4 — dense gridded numeric table
  - **vector_outlined_text**: the 1976 NASA Graphics Standards Manual page 1.3 — the "NASA" wordmark rendered as a filled vector shape with no corresponding text-showing operator at that position (not producible by any standard font)
- Every file's license verified **before** commit and recorded in `corpus/manifest.json`: 17 U.S.C. §105 U.S. Government Work (IRS forms/publications, the FAR, the NASA manual), CC BY-SA 3.0 (Wikimedia Commons, Chinese Wikipedia PDF), Public Domain (Wikimedia Commons historical invoices, Mutopia score), CC BY 4.0 (veraPDF-corpus, per its repository README)
- `corpus/validate_manifest.py` written test-first: `tests/test_corpus_manifest.py` asserts the real manifest+corpus pair returns `[]`, a tampered-sha256 scratch fixture is flagged, and a category-stripped-to-zero scratch fixture is flagged
- `corpus/README.md` documents the manifest schema field-by-field, one sentence per category on its structural signature, the D-01 two-tier design, and explicit sourcing/gap disclosure

## Task Commits

Each task was committed atomically:

1. **Task 1: Source public-tier PDFs covering all 15 D-03 categories, git-lfs tracked** - `5c76913` (feat)
2. **Task 2: Author the corpus manifest declaring categories, hashes, and provenance** - `53eb34c` (feat)

## Coverage of the 15 D-03 categories — explicit, per-category accounting

| Category | Source file(s) | How verified |
|---|---|---|
| `subset_fonts` | 12 of 17 files | pikepdf `/BaseFont` subset-tag inspection |
| `type0_identity_h` | irs_1040_instructions, irs_publication_17, wikipedia_zh_monthly_magazine, invoice_book_1842, far | pikepdf `/Type0 /Encoding` inspection |
| `symbolic_fonts` | irs_form_w4, far, mutopia_vocalise_abt | pikepdf `FontDescriptor /Flags` bit 4 |
| `type3` | **verapdf_type3_font_fixture (gap - see below)** | pikepdf `/Subtype /Type3` inspection |
| `cid_keyed_cff` | irs_publication_17, irs_form_w4, wikipedia_zh_monthly_magazine | pikepdf descendant `/Subtype /CIDFontType0` + `FontFile3 /CIDFontType0C` |
| `contents_array` | 9 of 17 files | pikepdf `/Contents` type check |
| `inline_images` | **verapdf_inline_image_fixture (gap - see below)** | raw content-stream byte scan for `BI`/`ID`/`EI` |
| `form_xobjects` | irs_1040_instructions, irs_publication_17, irs_1040_tax_tables, invoice_1905_james_green | pikepdf XObject `/Subtype /Form` |
| `annotation_appearance_streams` | irs_form_1040, irs_form_w9, irs_form_w4, irs_form_1040_spanish | pikepdf Annot `/AP` presence |
| `justified_right_aligned` | irs_1040_instructions, irs_publication_17, irs_form_1040 | pypdfium2 render, visual confirm |
| `tables` | irs_1040_tax_tables, irs_1040_instructions, irs_publication_17 | pypdfium2 render, visual confirm |
| `ocr_scan` | invoice_book_1842 | pikepdf Image XObject + `Tr 3` operator |
| `vector_outlined_text` | nasa_graphics_standards_manual | pypdfium2 render, visual confirm |
| `encrypted` | irs_form_w9_encrypted | pikepdf `Pdf.is_encrypted` |
| `malformed` | verapdf_isartor_malformed_trailer | sanctioned source per plan text |

## Disclosed Gaps (explicit, per phase_critical_constraints #1)

**`inline_images`** and **`type3`** could not be sourced from any wild-harvested document after
an extensive search (U.S. federal forms and publications, the Federal Acquisition Regulation,
a CJK Wikipedia PDF, LilyPond sheet music, historical invoices, poster/logo PDFs, and multiple
Internet Archive book scans were all checked programmatically — every page of every other
public-tier file was scanned with `pikepdf.parse_content_stream` for `BI` and for `/Subtype
/Type3` font resources; none were found). Both categories are instead sourced from the veraPDF
test corpus (CC BY 4.0), which is a **constructed ISO 32000/PDF-A conformance fixture set, not
independently wild-harvested**. This is disclosed here, in `corpus/manifest.json`'s `notes`
field for both entries, and in `corpus/README.md`, rather than silently substituted. A genuine
attempt was also made to source a real government contract form (e.g. GSA Standard Form 1449)
for the `weight_class: "contract"` tag; no stable public URL could be found within this plan's
scope, so `far_federal_acquisition_regulation.pdf` (the federal contracting rulebook itself)
stands in as the contract-weighted document instead.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `curl` without `-L` follows no redirects; every download used `-L --fail`**
- **Found during:** Task 1, first download attempt
- **Issue:** The prior killed attempt's note flagged this exact trap.
- **Fix:** Every `curl` invocation in this session used `-L --fail` plus an explicit `User-Agent` header (several government/CDN hosts return 403 without one) and verified `%PDF` magic bytes (via `file`) before treating a download as valid — one candidate URL (`mutcd.fhwa.dot.gov/pdfs/standard_alphabets.pdf`) returned HTTP 200 with an HTML error page; caught by the magic-byte check and discarded before it entered the corpus.
- **Files modified:** N/A (process only)
- **Committed in:** N/A (no incorrect file was ever committed)

**2. [Rule 3 - Blocking] `ocrmypdf`/`ghostscript` unavailable in this sandbox — plan's sanctioned OCR-generation method could not run**
- **Found during:** Task 1, sourcing the `ocr_scan` category
- **Issue:** The plan's action text says to run `ocrmypdf` over a real scanned image to produce the `ocr_scan` fixture. Neither `ocrmypdf` nor `ghostscript` (a mandatory ocrmypdf dependency) is installed in this environment, and installing ghostscript system-wide was judged out of scope for a corpus-sourcing task.
- **Fix:** Sourced an **already-OCR'd real scan** instead (`invoice_book_1842.pdf`, an 1842 invoice book scanned and OCR'd by the Internet Archive pipeline, hosted public-domain on Wikimedia Commons) and structurally confirmed the OCR signature (Image XObject + `Tr 3` invisible text layer) rather than self-generating one. This is arguably a *better* fit for phase_critical_constraint #3 ("documents must be real, wild-harvested files — not generated") than running ocrmypdf myself would have been.
- **Files modified:** `corpus/public/invoice_book_1842.pdf`, `corpus/manifest.json`
- **Committed in:** `5c76913`, `53eb34c`

**Total deviations:** 2 auto-fixed (both Rule 3, blocking/tooling), plus the two explicitly-disclosed category-sourcing gaps documented above (not deviations from the plan's *letter*, since the plan itself anticipates a "genuinely cannot be sourced" case, but flagged with the same prominence).

## Issues Encountered

- GSA's forms library and acquisition.gov's forms directory don't have stable, guessable direct
  PDF URLs (multiple SF-1449/SF-30/SF-1034 URL guesses 404'd); no browser/search tool was
  available to find the current URL. Substituted the FAR itself for the `contract` weight class.
- The bash sandbox in this environment rejected several multi-command shell constructs (loops,
  `cd ... && curl ... -w ...` compound lines) with a worktree-isolation guard, even though no
  git operation was involved; worked around by issuing one `curl` per tool call.

## User Setup Required

None — no external service configuration required. `git lfs` must be installed for contributors
to check out `corpus/public/*.pdf` with real content (already true of this environment; CI will
need `git-lfs` available, which is a Plan 01-03 / CI-setup concern).

## Next Phase Readiness

- `corpus/public/` and `corpus/manifest.json` exist, are git-lfs-tracked, and pass
  `pytest tests/test_corpus_manifest.py -q && python corpus/validate_manifest.py corpus/manifest.json corpus/public` cleanly.
- Plan 01-03 (private tier + independent CI prober per D-04) can build directly on this
  manifest's schema; `corpus/README.md` documents where the private tier's fetch mechanism and
  schema are expected to land.
- The two disclosed gaps (`inline_images`, `type3`) are candidates for later replacement with
  genuinely wild-harvested examples if one surfaces — the manifest's `notes` field on both
  entries makes them easy to find and swap.
- No blockers for Plan 01-03.

---
*Phase: 01-conformance-harness-engine-spike*
*Completed: 2026-08-12*

## Self-Check: PASSED

All 5 created artifact paths verified present on disk (`corpus/manifest.json`,
`corpus/validate_manifest.py`, `corpus/README.md`, `.gitattributes`,
`tests/test_corpus_manifest.py`); both task commits (`5c76913`, `53eb34c`) verified present in
`git log --oneline --all`.
