# playa-pdf vs pdfminer.six Decision

**Date:** 2026-08-12
**Requirement:** ENG-04 / research/SUMMARY.md Risk #3 ("playa-pdf is the least-corroborated
choice on the critical path... prototype against 3-4 real-world PDFs in Phase 1 before
committing")

## Decision

**`playa-pdf` is the primary library Phase 2 will build the content-stream interpreter's
read side on.** No swap to `pdfminer.six`. `pyproject.toml` is unchanged — `playa-pdf==1.1.0`
remains the sole runtime dependency for the read side; `pdfminer.six` is **not** installed,
since the fallback code path in `spike/playa_decode_probe.py` (`--engine pdfminer`) was not
needed and there is no reason to carry an unused runtime dependency.

## Evidence (from `spike/playa_decode_probe.py`, run 2026-08-12)

Command: `python spike/playa_decode_probe.py --manifest corpus/manifest.json --min-files 4`
— exit 0.

| File | Required categories exercised | Engine | Decoded OK | Glyph count | Sane |
|---|---|---|---|---|---|
| `irs_form_1040.pdf` | subset_fonts | playa | ok | 9,387 | yes |
| `irs_1040_instructions.pdf` | subset_fonts, type0_identity_h | playa | ok | 10,657 | yes |
| `irs_form_w9.pdf` | subset_fonts | playa | ok | 34,400 | yes |
| `irs_form_w4.pdf` | subset_fonts | playa | ok | 24,510 | yes |

`irs_1040_instructions.pdf` covers the required `type0_identity_h` category; all four files
are real, wild-harvested, subset-font documents (`ABCDEF+FontName`-tagged embedded fonts).
No unhandled exception on any file; no timeout fired (30s cap, all four completed well under
1s each).

### Type0/Identity-H CID resolution — spot-checked against known visible text

`irs_1040_instructions.pdf` uses `/Type0 /Encoding /Identity-H` with `CIDFontType2`
(TrueType) descendants (`JDHUQF+TimesNewRomanPSMT`). Decoded text from page 1:

```
'Userid: CPMSchema: i1040xLeadpct: 100%Pt. size: 10 Draft  Ok to PrintAH XSL/XMLFileid:
… -form-1040/2025/a/xml/cycle08/source(Init. & Date) _______Page 1 of 126  15:15 -
25-Feb-2026The type and rule a...'
```

This is a well-known IRS boilerplate proof-sheet header, and "Page 1 of 126" matches the
document's actual page count (126 pages, confirmed independently via `pypdfium2`). Per-glyph
inspection confirms the `P` in "Page" resolves to `CIDFont(basefont='JDHUQF+TimesNewRomanPSMT',
cidcoding='Adobe-Identity')`, `cid=51` — a single, stable, sane CID for a single visible glyph,
not garbage.

**Additional Type0/Identity-H + CID-keyed CFF evidence beyond the required minimum**, checked
interactively during Task 1 (not part of the committed 4-file selection, but corroborating):

- `irs_publication_17.pdf` embeds `WHERZU+NotoSansCJKjp-Regular` as `Type0/CIDFontType0`
  (`FontFile3 /CIDFontType0C`, i.e. CID-keyed CFF). playa decoded a Chinese/Korean-language
  caption on page 1 to `'中'`, `'文'`, `'한'`, `'국'`, `'어'` — real, correct CJK
  characters ("Chinese", "Korean language"), not `.notdef` boxes or garbage.
- `wikipedia_zh_monthly_magazine.pdf` (Type0/CID-keyed CFF, `QWGNKM+STXihei`) decoded its
  page-1 title to `'维基人 2013年04月13日 第5期'` ("Wikipedian, 2013-04-13, Issue 5") —
  fully correct real-world Chinese text.

### Subset-font resolution

All four selected files, and every corpus file checked interactively, carry
`XXXXXX+FontName`-tagged subset fonts (the standard PDF subset-tag convention). Simple-font
(`Type1Font`) glyph decode spot-checked on `irs_form_w9.pdf`: code for `'R'` resolves to
`cid=82`, `text='R'` — correct, not empty or garbage. No `/Differences`-related decode
failures observed on any selected or spot-checked file.

## Why GO, not SWAP

- Zero decode exceptions across 4 required + 3 corroborating real documents, spanning simple
  Type1 subset fonts, Type0/Identity-H with CIDFontType2 (TrueType), and Type0 with
  CID-keyed CFF (`CIDFontType0C`) including live CJK text.
- Per-glyph output already carries every field research/ARCHITECTURE.md's run record needs:
  `cid`, `text` (ToUnicode-derived, used here for display/sanity only — see PITFALLS.md
  Pitfall 1, never as a decode input), `bbox`, `origin`, `displacement` (advance), `font`
  (with `basefont`, `subtype`/`cidcoding` for CID fonts).
- `pdfminer.six` fallback path exists in the same module (`--engine pdfminer`) and was never
  needed — no file in the required or corroborating set produced zero glyphs or an exception
  with `playa`.
- research/SUMMARY.md's stated bar ("3-4 real-world PDFs... `pdfminer.six` is the drop-in
  fallback") is met with margin: 4 required + 3 corroborating, one of which is full CJK
  Type0/CID-keyed-CFF text, the specific case the fallback exists to catch.

## What was NOT tested (explicitly out of scope for this spike)

- Symbolic dingbat fonts in glyph-level detail (`irs_form_w4.pdf`'s `AdobePiStd` CIDFont
  resource is present but unused by any glyph in the 5-page sample this probe reads — Phase
  2 should re-check this specific font if/when symbolic-font editing is implemented).
- Full-document decode (each fixture is capped at its first `MAX_PAGES_PER_FILE=5` pages;
  see `spike/playa_decode_probe.py`'s module docstring for why a page cap is the right
  scope for this spike).
- `Type3` and `inline_images` category fixtures (both are constructed veraPDF conformance
  fixtures per `corpus/manifest.json`'s disclosed gap, not required by this plan's minimum).

These are Phase 2 concerns, not blockers for this decision — the question this spike answers
("can playa decode encodings and glyph geometry on real documents") is answered yes, with
evidence.
