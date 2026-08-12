# Conformance Corpus

Two-tier corpus of real-world PDFs used to validate the engine's structural handling, per
Phase 1's decisions (see `.planning/phases/01-conformance-harness-engine-spike/01-CONTEXT.md`,
D-01 through D-04).

## Two-tier design (D-01)

- **Public tier** (`corpus/public/`, this directory): committed to the repo, git-lfs tracked,
  runs on every PR including fork PRs with no CI secrets. Every structural category required by
  D-03 has at least one public-tier example, so a fork PR still exercises every engine code path.
- **Private tier**: never committed. Holds real invoices and contracts that carry third-party
  personal data. Fetched from a bucket via CI secrets, gates `main` and release branches, and is
  skipped where credentials are absent. The private tier adds volume and real-world messiness —
  never unique structural categories (D-02, D-03).

## Private tier: fetch mechanism and manifest (Plan 01-03)

`corpus/private-manifest.json` — same schema as `corpus/manifest.json` (see table above) with
two differences: `tier` is always `"private"`, and there is no `source_url` field (private-tier
files are not independently redistributable, so there is no public URL to record). It is
checked into git; the PDF bytes it describes are not. It starts as `[]` — the maintainer
populates it by hand as real documents are added to the private bucket (see Plan 01-03's
blocking checkpoint).

`tools/fetch_private_corpus.py` downloads every file `corpus/private-manifest.json` declares
from a bearer-token-gated HTTPS object store (any of S3/R2/GCS work — stdlib
`urllib.request` only, no cloud SDK) into `corpus/private/` (gitignored — never committed),
verifying each download's sha256 against the manifest entry. Reads
`PRIVATE_CORPUS_BASE_URL`/`PRIVATE_CORPUS_TOKEN` from the environment
(`${{ secrets.PRIVATE_CORPUS_BASE_URL }}`/`${{ secrets.PRIVATE_CORPUS_TOKEN }}` in CI). Absent
credentials (fork PRs, fresh clones) is a normal, non-failing state (D-02): the script prints
`status=skipped` and exits 0, never a warning-level failure. Present-but-wrong credentials or a
hash mismatch is a genuine, distinguishable `status=error` (nonzero exit) — absence and error
never collapse into the same outcome.

Once fetched, `corpus/private-manifest.json` + `corpus/private/` are run through the same two
checks as the public tier — `tools/probe_corpus.py ... --no-coverage-check` (D-04; coverage-check
disabled because D-03 never requires the private tier to independently cover all 15 categories)
and `harness/run_corpus_harness.py` (render/validate, reused unmodified) — wired as the
`corpus-private-gate` CI job in `.github/workflows/corpus.yml`, conditioned on the fetch step's
`status=ok` output.

`tools/check_corpus_size.py` is the mechanical Gate G0 floor check: combined
`corpus/manifest.json` + `corpus/private-manifest.json` entry count must reach 100 before Gate G0
can be signed off (roadmap's 100-300 target) — wired as the `corpus-size-gate` CI job, blocking
on `main`/`release/*`.

## `corpus/manifest.json` schema

A JSON array. Each entry:

| Field | Type | Meaning |
|---|---|---|
| `filename` | string | Relative to `corpus/public/` |
| `sha256` | string | `hashlib.sha256(open(path,'rb').read()).hexdigest()` of the file on disk |
| `tier` | string | Always `"public"` in this file |
| `categories` | array of string | Which of the 15 canonical categories (below) this file demonstrates |
| `source_url` | string | Where the document was retrieved from |
| `license` | string | Redistribution license/basis, verified before the file was committed |
| `weight_class` | string | One of `invoice`, `contract`, `other` — tracks the ENG-01 invoice/contract weighting |
| `notes` | string | How the category tag was verified (structural probe, visual render, or both), and any caveats |

Independently re-verified by `corpus/validate_manifest.py` (sha256 + zero-count-category check
against the manifest+corpus pair) and, in Plan 01-03, by a CI prober that re-derives categories
from the PDF bytes themselves rather than trusting the manifest's self-reported tags (D-04).

## The 15 canonical categories (D-03)

Every category has at least one public-tier example. One sentence per category on its
structural signature:

| Category | Structural signature |
|---|---|
| `subset_fonts` | Font `/BaseFont` carries a 6-uppercase-letter subset tag (`ABCDEF+FontName`) |
| `type0_identity_h` | A `/Type0` composite font with `/Encoding /Identity-H` |
| `symbolic_fonts` | `FontDescriptor /Flags` has the Symbolic bit (bit 3, value 4) set |
| `type3` | Font `/Subtype /Type3` — glyphs defined by content-stream procedures, not an embedded font program |
| `cid_keyed_cff` | `/Type0` descendant `/Subtype /CIDFontType0` with `FontDescriptor /FontFile3 /Subtype /CIDFontType0C` |
| `contents_array` | Page `/Contents` is an array of stream references rather than a single stream |
| `inline_images` | A content stream contains a literal `BI ... ID <data> EI` inline image operator sequence |
| `form_xobjects` | Page `/Resources /XObject` contains an entry with `/Subtype /Form` |
| `annotation_appearance_streams` | A page `/Annots` entry has an `/AP` (appearance stream) dictionary — typical of fillable AcroForm widgets |
| `justified_right_aligned` | Body text visibly aligns flush on both left and right margins (verified by rendering, not structurally inferable alone) |
| `tables` | Visibly gridded rows/columns of data (verified by rendering) |
| `ocr_scan` | A page `/Image` XObject (the scan) plus an invisible text layer (`Tr 3` render mode) positioned over it |
| `vector_outlined_text` | Letterforms drawn as filled vector paths with no corresponding `Tj`/`TJ` text-showing operator at that position — i.e. the "text" is not extractable text at all |
| `encrypted` | Document has a `/Encrypt` dictionary (`pikepdf.Pdf.is_encrypted is True`) |
| `malformed` | Intentionally violates PDF structural requirements (e.g. a broken file trailer) — an ISO PDF/A conformance test fixture |

## Sourcing notes and disclosed gaps

Thirteen of the seventeen public-tier files are independently wild-harvested real-world
documents (U.S. federal government forms/publications/regulations — public domain under
17 U.S.C. §105 — plus Wikimedia-Commons-hosted historical invoices, a CC-BY-SA Chinese
Wikipedia PDF, a public-domain LilyPond music score, and the public-domain 1976 NASA Graphics
Standards Manual). One further file (`irs_form_w9_encrypted.pdf`, see below) is one of those
wild-harvested documents with encryption applied locally. The remaining three files are
constructed ISO 32000/PDF-A conformance fixtures from the veraPDF test corpus (CC BY 4.0): one
— `malformed` — is explicitly sanctioned as a source by the phase's own task text; the other
two are disclosed gaps, **flagged here explicitly per the phase's explicit-gap-disclosure
requirement rather than silently substituted:**

- **`inline_images`** — no wild-harvested document in the sourced set contained a literal
  `BI/ID/EI` sequence (verified by scanning every page of every other public-tier file with
  `pikepdf.parse_content_stream`). Sourced from `veraPDF-corpus`'s inline-image-dictionary
  conformance fixture instead.
- **`type3`** — no wild-harvested document in the sourced set embedded a Type3 font (checked
  government forms/publications, sheet music, CJK documents, and a historic graphics-standards
  manual). Sourced from `veraPDF-corpus`'s Unicode-character-map conformance fixture instead.

One additional file, `irs_form_w9_encrypted.pdf`, is a real document (the sourced
`irs_form_w9.pdf`) with owner-password encryption applied locally via `pikepdf.Encryption` —
the sanctioned generation method for the `encrypted` category (see the phase's Task 1 action
text), not an independently sourced encrypted document.

The public tier is intentionally smaller than the plan's suggested 25-45 file range (17 files):
every file here was individually structurally verified (via `pikepdf` object introspection
and, for the two rendering-dependent categories, a `pypdfium2` visual spot-check) rather than
added to pad the count. See the Plan 01-02 SUMMARY for the full sourcing/verification log.

## Weighting toward invoices and contracts (ENG-01)

`weight_class: "invoice"` — `invoice_1905_james_green.pdf`, `invoice_book_1842.pdf`.
`weight_class: "contract"` — `far_federal_acquisition_regulation.pdf` (the Federal Acquisition
Regulation, the federal government's contracting rulebook — a genuine attempt was made to
source an actual filled contract form, e.g. GSA Standard Form 1449, but no stable public URL
could be found within this plan's scope).
