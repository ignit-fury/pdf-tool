# Corpus Sources, Licensing, and Producer Diversity

Provenance and redistribution licence for every document in the public tier, plus the producer
breakdown that is the actual point of the harvest.

## Why producer diversity, not document count

Gate G0 asks for 100–300 documents. The number is a proxy. What Phase 2 actually needs is coverage
of the **forward-encoding decision table**, which has at least five branches selected by the
`/Symbolic` flag, `/Encoding` presence, and which cmap subtables the embedded font carries. Those
branches are exercised by *variety of generator*, not by volume — a hundred files from one producer
exercise one code path and leave the corpus looking healthy while testing almost nothing new.

So selection is by `/Producer` (falling back to `/Creator`), with a cap on any single producer's
share. Documents are otherwise taken as they come; the corpus is deliberately not curated for
prettiness.

## Sources

| Source | Documents | Licence | Notes |
|---|---|---|---|
| **govdocs1** (digitalcorpora.org) | 199 | Public domain — US government documents, released for forensics research | ~1M real files scraped from US government web servers. The primary source, and the reason this harvest is automatable: nobody curated it, so it is what real producers actually emit. Fetched from the `zipfiles/NNN.zip` thread archives. |
| **IRS** (irs.gov) | 7 | U.S. Government Work — Public Domain (17 U.S.C. § 105) | Forms 1040, W-9, W-4, publications and tax tables. Sourced by plan 01-02. |
| **veraPDF corpus** | 3 | CC BY 4.0 | Constructed conformance fixtures. Used only where no wild-harvested example could be found — see "Disclosed substitutions" below. |
| **Federal Acquisition Regulation** (acquisition.gov) | 1 | U.S. Government Work — Public Domain | |
| **Wikipedia / Wikimedia** | 1 | CC BY-SA | Chinese-language monthly magazine — CJK text through CID-keyed CFF fonts. |
| **Mutopia Project** | 1 | Public domain / CC | Engraved sheet music — vector-heavy, unusual font usage. |
| **Internet Archive** | 2 | Public domain (pre-1929) | Historical invoices, 1842 and 1905. |
| **NASA** | 1 | U.S. Government Work — Public Domain | Graphics Standards Manual. |

Anything whose redistribution terms could not be confirmed was skipped. An unlicensed document in
the repository is worse than a missing one.

## Producer distribution

Measured with `tools/harvest_public_corpus.py`'s `producer_of()`, which normalises away version
strings and punctuation so variants of one product collapse to a single key.

**Target: no single producer above ~15%. Met — 216 documents, 57 distinct producers, top producer
at 13.9%, with a long tail of 43 producers contributing one or two documents each.**

| Share | Docs | Producer |
|---|---|---|
| 13.9% | 30 | acrobat distiller windows |
| 12.0% | 26 | acrobat distiller macintosh |
| 7.9% | 17 | acrobat pdfwriter windows |
| 6.5% | 14 | adobe pdf library |
| 6.5% | 14 | acrobat pdfwriter windows nt |
| 6.5% | 14 | corel pdf engine |
| 5.6% | 12 | mac os x quartz pdfcontext |
| 3.7% | 8 | acrobat distiller power macintosh |
| 3.2% | 7 | unknown |
| 2.3% | 5 | designer |
| — | 1–4 each | 47 further producers, incl. Antenna House, iText, ESRI ArcMap, Paper Capture OCR, Ghostscript, TeX-era and library generators |

Regenerate with:

```
python -c "import sys,collections;sys.path.insert(0,'tools');import harvest_public_corpus as h;from pathlib import Path;c=collections.Counter(h.producer_of(p) for p in Path('corpus/public').glob('*.pdf'));t=sum(c.values());[print(f'{100*n/t:5.1f}%  {n:3d}  {p}') for p,n in c.most_common()]"
```

### A cap that was not binding

Worth recording, because the failure mode generalises. The first version of `_normalize_producer()`
stripped digits but left punctuation, so `Acrobat Distiller 4.0 for Windows` and
`Acrobat Distiller 5.0 (Windows)` landed in **different buckets**. Each read as ~14.4% — comfortably
under the cap — while the actual product sat at **28.8%**, nearly double it. The cap was enforcing
correctly against a key that did not represent what it claimed to.

A check that passes because it is measuring the wrong thing is more dangerous than one that fails.
The normaliser now strips punctuation and filler words (`for`, `version`, `by`), and with the cap
genuinely binding, further harvesting skipped Distiller documents once it hit quota — its share fell
from 28.8% to 13.9% purely by growing the tail — no Distiller document was removed.

## Disclosed substitutions

Two categories could not be sourced from any wild-harvested candidate and use veraPDF constructed
conformance fixtures instead. Recorded here rather than silently substituted, per D-04 — a corpus
whose coverage claims are wrong is worse than one that makes none.

| Category | File | Why |
|---|---|---|
| `inline_images` | `verapdf_inline_image_fixture.pdf` | Inline images (`BI…ID…EI`) are rare in modern real-world output; no wild candidate found in an extensive search. |
| `type3` | `verapdf_type3_font_fixture.pdf` | Type3 fonts are effectively obsolete outside TeX-era documents and specialised generators. |
| `vector_outlined_text` | `vector_outlined_text_sample.pdf` | See "Disclosed Substitutions" below — no wild candidate found; constructed from a bundled OFL font. |

## Disclosed Substitutions

`vector_outlined_text` had **zero** genuine documents after `nasa_graphics_standards_manual.pdf`
was correctly relabelled `ocr_scan` (it is an OCR'd scan drawn in render mode 3 over page images,
not vector-outlined text — see its manifest `notes`). 02-RESEARCH.md Section 7 documents an
exhaustive scan of all 216 corpus documents for a page with zero glyphs, image coverage < 0.2, and
more than 200 path objects, which returned **0 candidates**.

Plan 02-02 Task 1 re-ran an equivalent scan directly against the harvesting policy's criteria (zero
`/Resources/Font` entries, a content stream with over 200 fill-path operators — `re`, `f`/`f*`,
`m`/`l`/`c` — and no `BT` text-showing operator). It found exactly one candidate,
`govdocs1_007_007087.pdf` page index 57. Rendering that page showed it to be a marketing cover
graphic — a stock photo plus a dot-pattern gradient, drawn via nested Form XObjects that embed a
raster image — not outlined text at all. It was disqualified rather than mislabelled.

With no genuine candidate available, `vector_outlined_text_sample.pdf` was **constructed**: glyph
outlines for the string "OUTLINED VECTOR TEXT" were extracted from the already-bundled
`spike/fixtures/LiberationSans-Regular.ttf` (SIL OFL 1.1, licence file alongside) using
`fontTools.pens.qu2cuPen.Qu2CuPen` to convert the font's quadratic (`glyf`-table) curves to the
cubic Béziers PDF content streams require, then written directly as a page content stream of
`m`/`l`/`c`/`f` path-fill operators via pikepdf — no text-showing operator, no font resource, no
image XObject. `/Resources` is an empty dict (zero `/Font`, zero `/XObject`) and there is no `BT`.

**Revised 2026-08-16** after two rounds of task review on `engine/classify_page.py`: the first
construction (one line, 18 glyphs) classified `empty`, not `vector_outlined` — 18 path-fill
operators does not cross `classify_page.py`'s `P_PATH_OBJECT_THRESHOLD ~= 200`. A first
regeneration (12 lines, 216 fills) technically crossed it but only by an 8% margin, and its own
disclosure overstated the safety margin by citing a total-operator count (`m`+`l`+`c`+`f`) that
`classify_page.py` never computes — `_path_object_count` counts only path-**painting** operators
(`f`, ISO 32000-1 Table 60), never path-**construction** operators (`m`/`l`/`c`, Table 59's
segment-drawing commands). The number that matters is the fill count alone. Regenerated once more
at genuine page scale: 60 repeated lines, 1080 glyphs, **1080 `f` operators — 5.4x the threshold on
the only count the classifier actually uses.** `qpdf --check` passes clean and the page renders as
60 legible lines reading "OUTLINED VECTOR TEXT" with no other content. This is a from-scratch
content stream built for the corpus fixture, not the product's own text-rewrite path, and not an
annotation/overlay technique.

## Category labels

Every entry's `categories` come from `tools/probe_corpus.probe_file()` — D-04's independent
structural verifier — never from a source's description of what a document contains. If the prober
disagrees with an expectation, the prober is right.

This has already caught one real error: plan 01-02 labelled `nasa_graphics_standards_manual.pdf`
`subset_fonts`, but that document embeds only Base-14 Helvetica and Times, with no subset-tagged or
custom font in page resources, Form XObject resources, or the AcroForm `/DR`. The prober caught it
on its first live run and the label was removed.

`KNOWN_REAL_MANIFEST_ISSUES` in `tests/test_probe_corpus.py` must stay **empty**. It is not a place
to park labels the prober rejects.

## Integrity

- Every document's `sha256` is recorded in `corpus/manifest.json` and re-verified by
  `corpus/validate_manifest.py` on every CI run, so later drift fails loudly.
- Files are magic-byte checked (`%PDF-`) at harvest; a redirect page saved as `.pdf` is not a PDF.
- Size is capped at harvest so a decompression bomb does not enter the corpus.
- All PDFs are tracked with git-lfs per `.gitattributes`.

## What is still missing

The roadmap asks for weighting toward **invoices and contracts**. govdocs1 is US government
publications, so that weighting remains only partially met — the only unambiguous invoices are the
1842 and 1905 scans, which are not representative of what users will bring. The private tier
(D-01, `corpus/private-manifest.json`) is the intended home for real modern commercial invoices and
contracts. It is currently empty, and populating it remains worthwhile enrichment even though Gate
G0 now clears without it.
